"""Deterministic aggregation and provenance-preserving conclusions for binary graph evidence."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .store import MemoryStore

RULE_SET = "mnemos-analysis-rules-v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("metadata")
    return value if isinstance(value, dict) else {}


def _scan(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = _metadata(snapshot).get("scan")
    return value if isinstance(value, dict) else {}


def _scan_complete(snapshot: dict[str, Any]) -> bool:
    return _scan(snapshot).get("complete") is True


def _scope(snapshot: dict[str, Any]) -> tuple[str, ...]:
    raw = _scan(snapshot).get("scope", [])
    if not isinstance(raw, list):
        return ()
    return tuple(sorted(str(Path(item).expanduser()) for item in raw if isinstance(item, str)))


def _artifact_identity(artifact: dict[str, Any]) -> dict[str, Any]:
    meta = _metadata(artifact)
    if isinstance(meta.get("sha256"), str) and meta["sha256"]:
        return {"kind": "full_sha256", "value": meta["sha256"]}
    if isinstance(meta.get("sample_sha256"), str) and meta["sample_sha256"]:
        return {"kind": "sampled_fingerprint", "value": meta["sample_sha256"]}
    return {"kind": "weak_observation", "value": {
        "size_bytes": meta.get("size_bytes"),
        "mtime_ns": meta.get("mtime_ns"),
        "observed_at_ns": meta.get("observed_at_ns"),
    }}


def _artifact_evidence(artifact: dict[str, Any], snapshot_ids: list[str]) -> dict[str, Any]:
    meta = _metadata(artifact)
    details = meta.get("binary_details") if isinstance(meta.get("binary_details"), dict) else {}
    return {
        "artifact_id": artifact["id"],
        "path": meta.get("path"),
        "identity": _artifact_identity(artifact),
        "size_bytes": meta.get("size_bytes"),
        "mtime_ns": meta.get("mtime_ns"),
        "observation_ts_ns": meta.get("observed_at_ns"),
        "parser_status": details.get("status", "unknown"),
        "format": details.get("format"),
        "snapshot_ids": sorted(snapshot_ids),
    }


def _active_snapshot_ids_for(artifact_id: str, snapshot_artifacts: dict[str, list[dict[str, Any]]]) -> list[str]:
    return sorted(snapshot_id for snapshot_id, artifacts in snapshot_artifacts.items()
                  if any(item["id"] == artifact_id for item in artifacts))


def _dependencies_for_artifacts(
    artifacts: list[dict[str, Any]], links: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]
) -> dict[tuple[str, str], list[str]]:
    artifact_ids = {item["id"] for item in artifacts}
    result: dict[tuple[str, str], list[str]] = {}
    for link in links:
        if link.get("relation") != "depends_on" or link.get("source_id") not in artifact_ids:
            continue
        dep = by_id.get(link.get("target_id"))
        if not dep or dep.get("kind") != "runtime_dependency":
            continue
        meta = _metadata(dep)
        name, fmt = meta.get("name"), meta.get("format")
        if isinstance(name, str) and name and isinstance(fmt, str) and fmt:
            result.setdefault((fmt, name.casefold()), []).append(dep["id"])
    return result


def _library_version(name: str) -> str | None:
    match = re.search(r"(?<![A-Za-z0-9])(?:v)?(\d+\.\d+(?:\.\d+)?)(?!\d)", name, re.IGNORECASE)
    return match.group(1) if match else None


def analyze_graph(
    store: MemoryStore,
    *,
    paths: list[str] | None = None,
    critical_threshold: int = 20,
    churn_threshold: int = 3,
    window_days: int = 30,
) -> tuple[dict[str, Any], bool]:
    """Analyze stored graph evidence and atomically persist one result per input fingerprint."""
    if critical_threshold < 1 or churn_threshold < 1 or window_days < 1:
        raise ValueError("Analysis thresholds and window must be positive integers.")

    memories = store.list_all()
    links = store.links()
    by_id = {item["id"]: item for item in memories}
    snapshots = [item for item in memories if item.get("kind") == "device_snapshot"]
    selected_paths = tuple(sorted(str(Path(path).expanduser()) for path in (paths or [])))
    if selected_paths:
        snapshots = [item for item in snapshots if _scope(item) == selected_paths]

    by_scope: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        scope = _scope(snapshot)
        if scope:
            by_scope.setdefault(scope, []).append(snapshot)
    for items in by_scope.values():
        items.sort(key=lambda item: (item.get("created_at", ""), item["id"]))
    latest_by_scope = {scope: items[-1] for scope, items in by_scope.items()}
    source_snapshot_ids = sorted(item["id"] for item in latest_by_scope.values())

    snapshot_artifacts: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        contained = {
            link["target_id"] for link in links
            if link.get("source_id") == snapshot["id"] and link.get("relation") == "contains_artifact"
        }
        snapshot_artifacts[snapshot["id"]] = [
            by_id[item_id] for item_id in sorted(contained)
            if item_id in by_id and by_id[item_id].get("kind") == "binary_artifact"
        ]

    latest_complete = {scope: snap for scope, snap in latest_by_scope.items() if _scan_complete(snap)}
    active_artifact_ids: set[str] = set()
    for snapshot in latest_complete.values():
        active_artifact_ids.update(item["id"] for item in snapshot_artifacts.get(snapshot["id"], []))

    dep_nodes = [
        item for item in memories
        if item.get("kind") == "runtime_dependency"
        and _metadata(item).get("schema") == "mnemos-dependency-evidence-v1"
    ]
    dep_links: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        if link.get("relation") == "depends_on" and link.get("source_id") in by_id and link.get("target_id") in by_id:
            dep_links.setdefault(link["target_id"], []).append(by_id[link["source_id"]])

    findings: list[dict[str, Any]] = []
    dependency_states: list[dict[str, Any]] = []
    for dep in dep_nodes:
        all_users = dep_links.get(dep["id"], [])
        active_users = [item for item in all_users if item["id"] in active_artifact_ids]
        active_ids = {item["id"] for item in active_users}
        active_snapshot_ids = sorted(
            snapshot_id for snapshot_id, artifacts in snapshot_artifacts.items()
            if any(artifact["id"] in active_ids for artifact in artifacts)
        )
        if active_users:
            status = "active_dependency"
        elif latest_by_scope and len(latest_complete) != len(latest_by_scope):
            status = "unknown"
        elif all_users:
            status = "historical_dependency"
        else:
            status = "unknown"
        dependency_states.append({
            "dependency_id": dep["id"], "name": _metadata(dep).get("name", dep.get("content", "")),
            "format": _metadata(dep).get("format"), "status": status,
            "active_artifact_count": len(active_ids),
            "evidence": [{
                "artifact_id": item["id"], "path": _metadata(item).get("path"),
                "identity": _artifact_identity(item),
            } for item in sorted(active_users, key=lambda item: item["id"])],
            "snapshot_ids": active_snapshot_ids,
        })
        if len(active_ids) > critical_threshold:
            findings.append({
                "rule_id": "critical_dependency", "severity": "review", "subject_id": dep["id"],
                "summary": f"{_metadata(dep).get('name', dep['id'])} is used by {len(active_ids)} active artifact versions",
                "confidence": "high",
                "evidence": {
                    "dependency_id": dep["id"], "artifact_count": len(active_ids),
                    "threshold_exclusive": critical_threshold,
                    "artifacts": [_artifact_evidence(item, _active_snapshot_ids_for(item["id"], snapshot_artifacts))
                                  for item in sorted(active_users, key=lambda item: item["id"])],
                },
            })
        name = str(_metadata(dep).get("name", ""))
        version = _library_version(name)
        if version:
            findings.append({
                "rule_id": "outdated_lib_needs_review", "severity": "needs_review",
                "subject_id": dep["id"],
                "summary": f"{name} exposes version {version}; no trusted local baseline is available to prove it outdated",
                "confidence": "low",
                "evidence": {
                    "dependency_id": dep["id"], "name": name, "version": version,
                    "active_artifact_ids": sorted(active_ids), "snapshot_ids": active_snapshot_ids,
                    "needs_review": True, "outdated_status": "unknown_without_baseline",
                },
            })

    for artifact in sorted((item for item in memories if item.get("kind") == "binary_artifact"), key=lambda item: item["id"]):
        meta = _metadata(artifact)
        if not meta.get("sha256") and meta.get("sample_sha256"):
            findings.append({
                "rule_id": "sampled_only_risk", "severity": "review", "subject_id": artifact["id"],
                "summary": f"{meta.get('path', artifact['id'])} is identified by sampled fingerprint only",
                "confidence": "high",
                "evidence": _artifact_evidence(artifact, _active_snapshot_ids_for(artifact["id"], snapshot_artifacts)),
            })

    now_ns = time.time_ns()
    window_ns = window_days * 86400 * 1_000_000_000
    churn_by_path: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        if link.get("relation") != "superseded_by":
            continue
        source, target = by_id.get(link.get("source_id")), by_id.get(link.get("target_id"))
        if not source or not target or source.get("kind") != "binary_artifact" or target.get("kind") != "binary_artifact":
            continue
        source_meta, target_meta = _metadata(source), _metadata(target)
        path = str(source_meta.get("path", ""))
        if not path or path != str(target_meta.get("path", "")):
            continue
        observed = target_meta.get("observed_at_ns") or source_meta.get("observed_at_ns")
        in_window = isinstance(observed, int) and now_ns - window_ns <= observed <= now_ns
        if not isinstance(observed, int):
            try:
                timestamp = datetime.fromisoformat(target["created_at"].replace("Z", "+00:00")).timestamp()
                in_window = time.time() - window_days * 86400 <= timestamp <= time.time()
            except (ValueError, TypeError, KeyError):
                in_window = False
        if in_window:
            churn_by_path.setdefault(path, []).append({
                "from": _artifact_evidence(source, _active_snapshot_ids_for(source["id"], snapshot_artifacts)),
                "to": _artifact_evidence(target, _active_snapshot_ids_for(target["id"], snapshot_artifacts)),
                "link_id": link["id"],
            })
    for path, edges in sorted(churn_by_path.items()):
        if len(edges) > churn_threshold:
            findings.append({
                "rule_id": "churny_artifact", "severity": "review", "subject_id": path,
                "summary": f"{path} has {len(edges)} supersessions in the last {window_days} days",
                "confidence": "high",
                "evidence": {"path": path, "supersessions": edges, "threshold_exclusive": churn_threshold},
            })

    missing_results: list[dict[str, Any]] = []
    unknown_scopes: list[dict[str, Any]] = []
    for scope, items in sorted(by_scope.items()):
        current = items[-1]
        if not _scan_complete(current):
            unknown_scopes.append({"scope": list(scope), "snapshot_id": current["id"], "reason": "scope_incomplete"})
            continue
        if len(items) < 2:
            unknown_scopes.append({"scope": list(scope), "snapshot_id": current["id"], "reason": "no_previous_snapshot"})
            continue
        previous = items[-2]
        if not _scan_complete(previous):
            unknown_scopes.append({"scope": list(scope), "snapshot_id": current["id"],
                                   "previous_snapshot_id": previous["id"], "reason": "previous_scope_incomplete"})
            continue
        current_artifacts = snapshot_artifacts.get(current["id"], [])
        failed = [item for item in current_artifacts
                  if (_metadata(item).get("binary_details") or {}).get("status") != "parsed"]
        if failed:
            unknown_scopes.append({"scope": list(scope), "snapshot_id": current["id"],
                                   "reason": "failed_validation", "artifact_ids": sorted(item["id"] for item in failed)})
            continue
        previous_deps = _dependencies_for_artifacts(snapshot_artifacts.get(previous["id"], []), links, by_id)
        current_deps = _dependencies_for_artifacts(current_artifacts, links, by_id)
        for key in sorted(set(previous_deps) - set(current_deps)):
            fmt, name = key
            missing_results.append({
                "rule_id": "missing_dependency", "severity": "review", "subject_id": f"{fmt}:{name}",
                "summary": f"{name} was present in the previous complete snapshot but absent from the latest complete snapshot",
                "confidence": "high",
                "evidence": {
                    "format": fmt, "name": name, "previous_snapshot_id": previous["id"],
                    "current_snapshot_id": current["id"], "scope": list(scope),
                    "status": "proven_absent", "previous_dependency_ids": sorted(previous_deps[key]),
                    "current_dependency_ids": sorted(current_deps.get(key, [])),
                },
            })
    findings.extend(missing_results)
    if not latest_by_scope:
        unknown_scopes.append({"scope": list(selected_paths), "reason": "no_snapshot_for_scope"})

    findings.sort(key=lambda item: (item["rule_id"], str(item["subject_id"]), _canonical(item["evidence"])))
    dependency_states.sort(key=lambda item: (str(item["format"]), str(item["name"]), item["dependency_id"]))
    graph_fingerprint = _hash({
        "snapshots": [{"id": item["id"], "fingerprint": _metadata(item).get("fingerprint"),
                       "complete": _scan_complete(item), "scope": _scope(item)}
                      for item in sorted(latest_by_scope.values(), key=lambda item: item["id"])],
        "artifacts": [{"id": item["id"], "metadata": _metadata(item)}
                      for item in sorted((item for item in memories if item.get("kind") == "binary_artifact"), key=lambda item: item["id"])],
        "dependencies": [{"id": item["id"], "metadata": _metadata(item)} for item in sorted(dep_nodes, key=lambda item: item["id"])],
        "links": [{key: link[key] for key in ("source_id", "target_id", "relation")}
                  for link in sorted(links, key=lambda link: (link["source_id"], link["target_id"], link["relation"]))
                  if link.get("relation") in {"contains_artifact", "depends_on", "superseded_by"}],
    })
    input_fingerprint = _hash({
        "rule_set": RULE_SET, "graph_fingerprint": graph_fingerprint,
        "source_snapshot_ids": source_snapshot_ids,
        "thresholds": {"critical_dependency": critical_threshold, "churny_artifact": churn_threshold, "window_days": window_days},
        "selected_paths": list(selected_paths),
    })
    result_metadata = {
        "schema": "mnemos-analysis-result-v1", "rule_set": RULE_SET,
        "input_fingerprint": input_fingerprint, "graph_fingerprint": graph_fingerprint,
        "source_snapshot_ids": source_snapshot_ids, "selected_paths": list(selected_paths),
        "scope_status": "known" if latest_by_scope and len(latest_complete) == len(latest_by_scope) else "unknown_scope_incomplete",
        "unknown_scopes": sorted(unknown_scopes, key=_canonical),
        "dependency_states": dependency_states, "findings": findings,
        "counts": {
            "findings": len(findings),
            "critical_dependencies": sum(item["rule_id"] == "critical_dependency" for item in findings),
            "churny_artifacts": sum(item["rule_id"] == "churny_artifact" for item in findings),
            "missing_dependencies": len(missing_results),
            "sampled_only_risks": sum(item["rule_id"] == "sampled_only_risk" for item in findings),
            "libraries_needing_review": sum(item["rule_id"] == "outdated_lib_needs_review" for item in findings),
            "unknown_scopes": len(unknown_scopes),
        },
    }
    return store.add_once(
        f"Analysis result {input_fingerprint[:12]}", kind="analysis_result",
        fingerprint=input_fingerprint, tags=["analysis", RULE_SET],
        source="mnemos-analyze", metadata=result_metadata,
    )
