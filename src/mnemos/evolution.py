"""Deterministic graph reconciliation for Mnemos binary evidence.

Repairs only relationships that can be derived from persisted static evidence.
Historical nodes and evidence are never deleted.
"""
from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from .store import MemoryStore
from .integrity import snapshot_artifact_map, snapshot_is_complete, snapshot_order_key, snapshot_scope_identity, would_create_cycle


def _dependencies(details: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize parser-specific dependency metadata to one graph contract."""
    fmt = details.get("format")
    result: list[dict[str, Any]] = []
    if fmt in {"ELF", "Mach-O"}:
        for item in details.get("dependencies", []):
            if isinstance(item, dict):
                result.append({
                    "name": item.get("name", ""),
                    "kind": item.get("kind", "needed" if fmt == "ELF" else "load"),
                    "format": fmt,
                })
    elif fmt == "PE":
        for item in details.get("imports", []):
            if isinstance(item, dict):
                result.append({
                    "name": item.get("library", ""),
                    "kind": "import",
                    "format": "PE",
                    "symbols": item.get("symbols", []),
                })
    return [
        item for item in result
        if isinstance(item.get("name"), str) and item["name"].strip()
    ]


def _evidence(artifact: dict[str, Any], details: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_sha256": artifact.get("sha256"),
        "sample_sha256": artifact.get("sample_sha256"),
        "artifact_path": artifact.get("path"),
        "observed_mtime_ns": artifact.get("mtime_ns") if artifact.get("sha256") is None else None,
        "file_size_bytes": artifact.get("size_bytes") if artifact.get("sha256") is None else None,
        "parser_status": details.get("status"),
        "analysis_limits": details.get("analysis_limits", []),
        "method": "static-file-metadata",
        "execution_performed": False,
        "network_used": False,
    }


def _evidence_key(item: dict[str, Any]) -> tuple[Any, ...]:
    # The hash identifies content. For oversized/unhashable artifacts, include
    # observed metadata so different observations at one path do not collapse.
    return (
        item.get("artifact_path"),
        item.get("artifact_sha256"),
        item.get("sample_sha256") if item.get("artifact_sha256") is None else None,
        item.get("observed_mtime_ns") if item.get("artifact_sha256") is None else None,
        item.get("file_size_bytes") if item.get("artifact_sha256") is None else None,
    )


def evolve_graph(store: MemoryStore) -> dict[str, Any]:
    """Repair missing evidence-derived links and validate graph invariants.

    The operation is offline and idempotent. It never removes historical links;
    an incomplete parse is not interpreted as proof that a dependency vanished.
    """
    memories = store.list_all()
    links = store.links()
    artifacts = [item for item in memories if item.get("kind") == "binary_artifact"]
    dependency_records: dict[tuple[str, str], dict[str, Any]] = {}
    for item in memories:
        metadata = item.get("metadata") or {}
        if item.get("kind") != "runtime_dependency":
            continue
        if metadata.get("schema") != "mnemos-dependency-evidence-v1":
            continue
        name, fmt = metadata.get("name"), metadata.get("format")
        if isinstance(name, str) and name.strip() and isinstance(fmt, str) and fmt:
            dependency_records.setdefault((fmt, name.casefold()), item)

    existing = {
        (link["source_id"], link["target_id"], link["relation"])
        for link in links
    }
    existing_successors: dict[str, set[str]] = defaultdict(set)
    for link in links:
        if link["relation"] == "superseded_by":
            existing_successors[link["source_id"]].add(link["target_id"])

    repaired_history = 0
    by_id_for_history = {item["id"]: item for item in memories}
    snapshots_by_scope: dict[tuple[str, str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for snapshot in memories:
        if snapshot.get("kind") != "device_snapshot":
            continue
        identity = snapshot_scope_identity(snapshot)
        if identity[2]:
            snapshots_by_scope[identity].append(snapshot)
    for history in snapshots_by_scope.values():
        history.sort(key=snapshot_order_key)
        complete_history = [item for item in history if snapshot_is_complete(item)]
        for previous_snapshot, current_snapshot in zip(complete_history, complete_history[1:]):
            previous_by_path = snapshot_artifact_map(previous_snapshot, by_id_for_history, links)
            current_by_path = snapshot_artifact_map(current_snapshot, by_id_for_history, links)
            for path in sorted(set(previous_by_path) & set(current_by_path)):
                previous = previous_by_path[path]
                current = current_by_path[path]
                if previous["id"] == current["id"] or existing_successors.get(previous["id"]):
                    continue
                key = (previous["id"], current["id"], "superseded_by")
                if key in existing or would_create_cycle(previous["id"], current["id"], existing_successors):
                    continue
                store.link(previous["id"], current["id"], relation="superseded_by")
                existing.add(key)
                existing_successors[previous["id"]].add(current["id"])
                repaired_history += 1

    repaired_dependency_links = 0
    dependency_nodes_created = 0
    evidence_records_updated = 0
    skipped_unparsed_artifacts = 0
    for artifact in artifacts:
        metadata = artifact.get("metadata") or {}
        details = metadata.get("binary_details")
        if not isinstance(details, dict) or details.get("status") != "parsed":
            skipped_unparsed_artifacts += 1
            continue
        for dependency in _dependencies(details):
            name = dependency["name"].strip()
            fmt = dependency["format"]
            key = (fmt, name.casefold())
            dep_record = dependency_records.get(key)
            source_evidence = _evidence(metadata, details)
            if dep_record is None:
                dep_record = store.add(
                    f"Runtime dependency: {name}",
                    kind="runtime_dependency",
                    tags=[fmt.lower(), dependency["kind"]],
                    source="mnemos-static-binary-metadata",
                    metadata={
                        "schema": "mnemos-dependency-evidence-v1",
                        "name": name,
                        "format": fmt,
                        "kind": dependency["kind"],
                        "kinds": [dependency["kind"]],
                        "symbols": dependency.get("symbols", []),
                        "evidence": source_evidence,
                        "evidence_sources": [source_evidence],
                    },
                )
                dependency_records[key] = dep_record
                dependency_nodes_created += 1
            else:
                dep_metadata = dict(dep_record.get("metadata") or {})
                evidence_sources = dep_metadata.get("evidence_sources")
                if not isinstance(evidence_sources, list):
                    legacy = dep_metadata.get("evidence")
                    evidence_sources = [legacy] if isinstance(legacy, dict) else []
                normalized = [
                    item for item in evidence_sources if isinstance(item, dict)
                ]
                incoming_key = _evidence_key(source_evidence)
                if not any(
                    _evidence_key(item) == incoming_key
                    for item in normalized
                ):
                    normalized.append(source_evidence)
                kinds = set(dep_metadata.get("kinds", [])) if isinstance(dep_metadata.get("kinds"), list) else set()
                if isinstance(dep_metadata.get("kind"), str):
                    kinds.add(dep_metadata["kind"])
                kinds.add(dependency["kind"])
                dep_metadata["kinds"] = sorted(kinds)
                dep_metadata["evidence_sources"] = normalized
                symbols = dep_metadata.get("symbols", [])
                if not isinstance(symbols, list):
                    symbols = []
                symbol_map = {
                    json.dumps(item, sort_keys=True): item
                    for item in symbols + (dependency.get("symbols", []) if isinstance(dependency.get("symbols"), list) else [])
                    if isinstance(item, dict)
                }
                dep_metadata["symbols"] = [symbol_map[symbol_key] for symbol_key in sorted(symbol_map)]
                # Avoid rewriting unchanged metadata: repeated scans should be
                # idempotent and must not continually enqueue outbox updates.
                before_metadata = json.dumps(
                    dep_record.get("metadata") or {}, sort_keys=True, separators=(",", ":")
                )
                after_metadata = json.dumps(
                    dep_metadata, sort_keys=True, separators=(",", ":")
                )
                if after_metadata != before_metadata:
                    dep_record = store.update_metadata(dep_record["id"], dep_metadata)
                    evidence_records_updated += 1
                dependency_records[key] = dep_record

            link_key = (artifact["id"], dep_record["id"], "depends_on")
            if link_key not in existing:
                store.link(artifact["id"], dep_record["id"], relation="depends_on")
                existing.add(link_key)
                repaired_dependency_links += 1

    # Re-read because reconciliation can add nodes and links.
    memories = store.list_all()
    links = store.links()
    by_id = {item["id"]: item for item in memories}
    violations: list[dict[str, Any]] = []
    outgoing_supersession: dict[str, int] = defaultdict(int)
    for link in links:
        source = by_id.get(link["source_id"])
        target = by_id.get(link["target_id"])
        relation = link["relation"]
        if source is None or target is None:
            violations.append({"type": "dangling_link", "link_id": link["id"]})
            continue
        if relation == "depends_on":
            if source.get("kind") != "binary_artifact" or target.get("kind") != "runtime_dependency":
                violations.append({
                    "type": "invalid_dependency_edge", "link_id": link["id"],
                    "source_kind": source.get("kind"), "target_kind": target.get("kind"),
                })
        elif relation == "superseded_by":
            outgoing_supersession[source["id"]] += 1
            if source.get("kind") != "binary_artifact" or target.get("kind") != "binary_artifact":
                violations.append({"type": "invalid_supersession_edge", "link_id": link["id"]})
    for memory_id, count in outgoing_supersession.items():
        if count > 1:
            violations.append({
                "type": "multiple_successors", "artifact_id": memory_id,
                "successor_count": count,
            })

    superseded: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link["relation"] == "superseded_by":
            superseded[link["source_id"]].append(link["target_id"])
    # Iterative three-colour DFS avoids Python recursion limits on long
    # histories while still detecting cycles deterministically.
    state: dict[str, int] = {}
    has_cycle = False
    for start in superseded:
        if state.get(start, 0) != 0:
            continue
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node_id, exiting = stack.pop()
            if exiting:
                state[node_id] = 2
                continue
            color = state.get(node_id, 0)
            if color == 1:
                has_cycle = True
                break
            if color == 2:
                continue
            state[node_id] = 1
            stack.append((node_id, True))
            for child in superseded.get(node_id, []):
                child_color = state.get(child, 0)
                if child_color == 1:
                    has_cycle = True
                    break
                if child_color == 0:
                    stack.append((child, False))
            if has_cycle:
                break
        if has_cycle:
            break
    if has_cycle:
        violations.append({"type": "supersession_cycle"})

    dependency_ids_by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    artifact_ids_by_content: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item in memories:
        metadata = item.get("metadata") or {}
        if item.get("kind") == "runtime_dependency" and metadata.get("schema") == "mnemos-dependency-evidence-v1":
            name, fmt = metadata.get("name"), metadata.get("format")
            if isinstance(name, str) and name.strip() and isinstance(fmt, str) and fmt:
                dependency_ids_by_key[(fmt, name.casefold())].append(item["id"])
        elif item.get("kind") == "binary_artifact":
            path, digest = metadata.get("path"), metadata.get("sha256")
            if isinstance(path, str) and path and isinstance(digest, str) and digest:
                artifact_ids_by_content[(path, digest)].append(item["id"])
    for (fmt, name), ids in dependency_ids_by_key.items():
        if len(ids) > 1:
            violations.append({
                "type": "duplicate_dependency_nodes", "format": fmt,
                "name": name, "node_ids": sorted(ids),
            })
    for (path, digest), ids in artifact_ids_by_content.items():
        if len(ids) > 1:
            violations.append({
                "type": "duplicate_artifact_versions", "path": path,
                "sha256": digest, "node_ids": sorted(ids),
            })
    for link in links:
        if link["relation"] == "contains_artifact":
            source = by_id.get(link["source_id"])
            target = by_id.get(link["target_id"])
            if source is not None and target is not None and (
                source.get("kind") != "device_snapshot" or target.get("kind") != "binary_artifact"
            ):
                violations.append({
                    "type": "invalid_contains_artifact_edge", "link_id": link["id"],
                    "source_kind": source.get("kind"), "target_kind": target.get("kind"),
                })

    return {
        "schema": "mnemos-graph-evolution-v1",
        "offline": True,
        "memories": len(memories),
        "links": len(links),
        "binary_artifacts": sum(item.get("kind") == "binary_artifact" for item in memories),
        "runtime_dependencies": sum(item.get("kind") == "runtime_dependency" for item in memories),
        "supersession_edges_repaired": repaired_history,
        "dependency_edges_repaired": repaired_dependency_links,
        "dependency_nodes_created": dependency_nodes_created,
        "evidence_records_updated": evidence_records_updated,
        "unparsed_artifacts_skipped": skipped_unparsed_artifacts,
        "violations": violations,
        "ok": not violations,
    }
