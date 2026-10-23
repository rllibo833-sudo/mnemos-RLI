"""Deterministic graph reconciliation for Mnemos binary evidence.

Repairs only relationships that can be derived from persisted static evidence.
Historical nodes and evidence are never deleted.
"""
from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from .store import MemoryStore


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
    artifacts_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in artifacts:
        path = (item.get("metadata") or {}).get("path")
        if isinstance(path, str) and path:
            artifacts_by_path[path].append(item)

    for versions in artifacts_by_path.values():
        versions.sort(key=lambda item: (
            item.get("created_at", ""),
            int((item.get("metadata") or {}).get("mtime_ns") or 0),
            item["id"],
        ))
        for previous, current in zip(versions, versions[1:]):
            # Never manufacture a competing successor if history already
            # records one. Integrity validation below will flag conflicts.
            if existing_successors.get(previous["id"]):
                continue
            key = (previous["id"], current["id"], "superseded_by")
            if key not in existing:
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
                updated = store.update_metadata(dep_record["id"], dep_metadata)
                if updated.get("updated_at") != dep_record.get("updated_at"):
                    evidence_records_updated += 1
                dep_record = updated
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
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        cyclic = any(visit(child) for child in superseded.get(node_id, []))
        visiting.remove(node_id)
        visited.add(node_id)
        return cyclic

    if any(visit(node_id) for node_id in list(superseded) if node_id not in visited):
        violations.append({"type": "supersession_cycle"})

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
