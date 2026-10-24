"""Shared, conservative comparison of persisted artifact observations."""
from __future__ import annotations
from pathlib import Path
from typing import Any

FINDING_STATUSES = {"MISSING", "HASH_MISMATCH", "NEW_FILE", "PERM_CHANGE", "SIZE_CHANGE", "SAMPLED_MISMATCH"}

def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("metadata")
    return value if isinstance(value, dict) else {}

def snapshot_scan(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = _metadata(snapshot).get("scan")
    return value if isinstance(value, dict) else {}

def snapshot_is_complete(snapshot: dict[str, Any]) -> bool:
    return snapshot_scan(snapshot).get("complete") is True

def snapshot_scope(snapshot: dict[str, Any]) -> tuple[str, ...]:
    metadata = _metadata(snapshot)
    raw = metadata.get("scope_path")
    if not isinstance(raw, list) or not raw:
        raw = snapshot_scan(snapshot).get("scope", [])
    if not isinstance(raw, list):
        return ()
    values = []
    for value in raw:
        if not isinstance(value, str) or not value:
            continue
        try:
            values.append(str(Path(value).expanduser().resolve()))
        except (OSError, RuntimeError):
            values.append(str(Path(value).expanduser()))
    return tuple(sorted(set(values)))

def snapshot_scope_identity(snapshot: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    metadata = _metadata(snapshot)
    device = metadata.get("device")
    device = device if isinstance(device, dict) else {}
    return (str(metadata.get("device_id") or "legacy-device"),
            str(metadata.get("host_env") or device.get("os_type") or device.get("os") or "legacy-host"),
            snapshot_scope(snapshot))

def snapshot_order_key(snapshot: dict[str, Any]) -> tuple[int, str, str]:
    metadata = _metadata(snapshot)
    try:
        observed = int(metadata.get("observation_ts_ns") or 0)
    except (TypeError, ValueError):
        observed = 0
    return observed, str(snapshot.get("created_at") or ""), str(snapshot.get("id") or "")

def snapshot_artifact_map(snapshot: dict[str, Any], by_id: dict[str, dict[str, Any]],
                          links: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for link in links:
        if link.get("source_id") != snapshot.get("id") or link.get("relation") != "contains_artifact":
            continue
        artifact = by_id.get(link.get("target_id"))
        if not artifact or artifact.get("kind") != "binary_artifact":
            continue
        path = _metadata(artifact).get("path")
        if not isinstance(path, str) or not path:
            continue
        previous = result.get(path)
        if previous is None or (str(artifact.get("created_at") or ""), str(artifact.get("id") or "")) > (
            str(previous.get("created_at") or ""), str(previous.get("id") or "")):
            result[path] = artifact
    return result

def _artifact_node(path: str, status: str, current: dict[str, Any] | None,
                   previous: dict[str, Any] | None, current_snapshot: dict[str, Any],
                   previous_snapshot: dict[str, Any] | None, reason: str,
                   flags: list[str] | None = None) -> dict[str, Any]:
    now, before = _metadata(current or {}), _metadata(previous or {})
    current_meta = _metadata(current_snapshot)
    device = current_meta.get("device")
    device = device if isinstance(device, dict) else {}
    return {
        "path": path, "status": status, "artifact_id": (current or previous or {}).get("id"),
        "expected_sha256": before.get("sha256"), "observed_sha256": now.get("sha256"),
        "expected_sample_sha256": before.get("sample_sha256"), "observed_sample_sha256": now.get("sample_sha256"),
        "size_bytes": now.get("size_bytes", before.get("size_bytes")), "expected_size_bytes": before.get("size_bytes"),
        "expected_mode": before.get("mode"), "observed_mode": now.get("mode"),
        "os": current_meta.get("host_env") or device.get("os_type") or device.get("os") or "unknown",
        "architecture": device.get("architecture") or "unknown", "sandbox_id": device.get("sandbox_id") or "unknown",
        "current_snapshot_id": current_snapshot.get("id"),
        "baseline_snapshot_id": (previous_snapshot or {}).get("id"),
        "change_flags": flags or [], "reason": reason,
    }

def compare_snapshot_histories(snapshots: list[dict[str, Any]], links: list[dict[str, Any]],
                               by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare only like-for-like scopes; incomplete scans cannot prove absence."""
    grouped: dict[tuple[str, str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        if snapshot.get("kind") != "device_snapshot":
            continue
        identity = snapshot_scope_identity(snapshot)
        if identity[2]:
            grouped.setdefault(identity, []).append(snapshot)
    reports = []
    for identity, history in grouped.items():
        history.sort(key=snapshot_order_key)
        current_snapshot = history[-1]
        previous_snapshot = next((item for item in reversed(history[:-1]) if snapshot_is_complete(item)), None)
        current_complete = snapshot_is_complete(current_snapshot)
        current = snapshot_artifact_map(current_snapshot, by_id, links)
        previous = snapshot_artifact_map(previous_snapshot, by_id, links) if previous_snapshot else {}
        nodes = []
        if not current_complete:
            for path in sorted(current):
                nodes.append(_artifact_node(path, "UNKNOWN", current[path], None, current_snapshot, previous_snapshot,
                    "The latest scan is incomplete; absence and integrity conclusions are withheld."))
            status = "INCOMPLETE_SCAN"
        elif previous_snapshot is None:
            for path in sorted(current):
                nodes.append(_artifact_node(path, "BASELINE_ONLY", current[path], None, current_snapshot, None,
                    "No earlier complete scan exists for this exact device and scope."))
            status = "BASELINE_ONLY"
        else:
            for path in sorted(set(current) | set(previous)):
                now, before = current.get(path), previous.get(path)
                if now is None:
                    nodes.append(_artifact_node(path, "MISSING", None, before, current_snapshot, previous_snapshot,
                        "Present in the previous complete scan but absent from the latest complete scan."))
                    continue
                if before is None:
                    nodes.append(_artifact_node(path, "NEW_FILE", now, None, current_snapshot, previous_snapshot,
                        "First observed against this baseline; newness alone is not proof of damage."))
                    continue
                now_meta, before_meta = _metadata(now), _metadata(before)
                flags = []
                if now_meta.get("size_bytes") != before_meta.get("size_bytes"):
                    flags.append("size_change")
                if now_meta.get("mode") != before_meta.get("mode"):
                    flags.append("permission_change")
                now_hash, before_hash = now_meta.get("sha256"), before_meta.get("sha256")
                now_sample, before_sample = now_meta.get("sample_sha256"), before_meta.get("sample_sha256")
                if isinstance(now_hash, str) and isinstance(before_hash, str):
                    if now_hash != before_hash:
                        node_status, reason = "HASH_MISMATCH", "Full SHA-256 differs from the prior complete scan; cause is not inferred."
                    elif "size_change" in flags:
                        node_status, reason = "SIZE_CHANGE", "Full hashes match but recorded size differs; stored metadata is inconsistent."
                    elif "permission_change" in flags:
                        node_status, reason = "PERM_CHANGE", "Full SHA-256 matches but permission bits differ."
                    else:
                        node_status, reason = "MATCH", "Full SHA-256 and recorded size/permission metadata match the baseline."
                elif isinstance(now_sample, str) and isinstance(before_sample, str) and now_sample != before_sample:
                    node_status, reason = "SAMPLED_MISMATCH", "Sampled fingerprint differs; this is not a full-content hash proof."
                elif "size_change" in flags:
                    node_status, reason = "SIZE_CHANGE", "Recorded file size differs; full-content hash evidence is unavailable."
                elif "permission_change" in flags:
                    node_status, reason = "PERM_CHANGE", "Permission bits differ; full-content hash evidence is unavailable."
                else:
                    node_status, reason = "UNKNOWN", "Full SHA-256 evidence is unavailable; sampled fingerprints cannot prove byte equality."
                nodes.append(_artifact_node(path, node_status, now, before, current_snapshot, previous_snapshot, reason, flags))
            status = "COMPARED"
        current_meta = _metadata(current_snapshot)
        reports.append({
            "status": status, "device_id": identity[0], "host_env": identity[1], "scope": list(identity[2]),
            "scope_label": ", ".join(identity[2]), "current_snapshot_id": current_snapshot.get("id"),
            "baseline_snapshot_id": (previous_snapshot or {}).get("id"),
            "latest_observation_ts_ns": snapshot_order_key(current_snapshot)[0],
            "last_scan": current_meta.get("captured_at") or current_snapshot.get("created_at"),
            "baseline_scan": (_metadata(previous_snapshot).get("captured_at") if previous_snapshot else None)
                or ((previous_snapshot or {}).get("created_at")),
            "compared_count": len(nodes),
            "finding_count": sum(node["status"] in FINDING_STATUSES for node in nodes),
            "unknown_count": sum(node["status"] == "UNKNOWN" for node in nodes),
            "nodes": nodes,
            "message": ("Latest scan is incomplete; no missing-file or damage conclusion is supported."
                if status == "INCOMPLETE_SCAN" else
                "No previous complete scan exists for this exact device and scope."
                if status == "BASELINE_ONLY" else
                "Compared with the latest earlier complete scan for the same device, host environment, and scope."),
        })
    reports.sort(key=lambda item: (item["latest_observation_ts_ns"], item["current_snapshot_id"] or ""), reverse=True)
    return reports

def would_create_cycle(source_id: str, target_id: str, successors: dict[str, set[str]]) -> bool:
    """Return true when adding source -> target would make supersession cyclic."""
    pending, seen = [target_id], set()
    while pending:
        current = pending.pop()
        if current == source_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(successors.get(current, ()))
    return False
