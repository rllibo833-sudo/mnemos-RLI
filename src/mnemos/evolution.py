"""Deterministic reconciliation and integrity checks for Mnemos' binary graph."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .store import MemoryStore


def evolve_graph(store: MemoryStore) -> dict[str, Any]:
    """Repair missing artifact-version edges without deleting or rewriting evidence.

    Artifact history is ordered by the time Mnemos observed each version. The
    operation is idempotent: running it repeatedly creates no duplicate links.
    """
    memories = store.list_all()
    links = store.links()
    by_id = {item["id"]: item for item in memories}
    artifacts_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in memories:
        if item.get("kind") != "binary_artifact":
            continue
        metadata = item.get("metadata") or {}
        path = metadata.get("path")
        if isinstance(path, str) and path:
            artifacts_by_path[path].append(item)

    existing = {
        (link["source_id"], link["target_id"], link["relation"])
        for link in links
    }
    repaired = 0
    for versions in artifacts_by_path.values():
        versions.sort(key=lambda item: (item.get("created_at", ""), item["id"]))
        for previous, current in zip(versions, versions[1:]):
            key = (previous["id"], current["id"], "superseded_by")
            if key not in existing:
                store.link(previous["id"], current["id"], relation="superseded_by")
                existing.add(key)
                repaired += 1

    # Re-read after repairs so diagnostics describe the resulting graph.
    links = store.links()
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
                    "type": "invalid_dependency_edge",
                    "link_id": link["id"],
                    "source_kind": source.get("kind"),
                    "target_kind": target.get("kind"),
                })
        elif relation == "superseded_by":
            outgoing_supersession[source["id"]] += 1
            if source.get("kind") != "binary_artifact" or target.get("kind") != "binary_artifact":
                violations.append({"type": "invalid_supersession_edge", "link_id": link["id"]})
    for memory_id, count in outgoing_supersession.items():
        if count > 1:
            violations.append({
                "type": "multiple_successors",
                "artifact_id": memory_id,
                "successor_count": count,
            })

    # A cycle is not valid version history. Check the supersession subgraph only.
    superseded = defaultdict(list)
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
        "supersession_edges_repaired": repaired,
        "violations": violations,
        "ok": not violations,
    }
