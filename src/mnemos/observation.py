"""Persisted scan coverage and conservative asset timeline reconstruction."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import time
import uuid


@dataclass
class Observation:
    """One scan episode; completeness is distinct from whether findings were found."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    scan_type: str = "filesystem_scan"
    paths: list[str] = field(default_factory=list)
    max_files: int = 0
    files_attempted: int = 0
    files_scanned: int = 0
    files_failed: int = 0
    dirs_failed: list[str] = field(default_factory=list)
    hit_max_files_limit: bool = False
    truncated_due_to: str | None = None
    event_monitor_active: bool = False
    event_monitor_type: str | None = None
    event_monitor_errors: list[str] = field(default_factory=lambda: ["No OS event backend is configured; periodic scans only."])
    coverage_complete: bool = False
    confidence_level: str = "unknown"

    @classmethod
    def from_scan(cls, report: dict[str, Any], *, paths: list[str], max_files: int) -> "Observation":
        scan = report.get("scan") if isinstance(report.get("scan"), dict) else {}
        errors = scan.get("traversal_errors") if isinstance(scan.get("traversal_errors"), list) else []
        dirs_failed = sorted({
            str(item.get("path") or "<unknown-path>")
            for item in errors if isinstance(item, dict)
        })
        hit_limit = bool(scan.get("limit_reached"))
        files_attempted = max(0, int(scan.get("examined_files") or 0))
        file_errors = scan.get("file_errors") if isinstance(scan.get("file_errors"), list) else []
        files_failed = len(file_errors)
        files_scanned = max(0, files_attempted - files_failed)
        complete = (
            scan.get("complete") is True and files_failed == 0 and not dirs_failed
            and not hit_limit and not scan.get("depth_limit_reached")
            and not scan.get("skipped_symlink_roots")
        )
        confidence = "high" if complete else ("medium" if files_scanned and not hit_limit else "low")
        return cls(
            timestamp=time.time(), paths=list(paths), max_files=int(max_files),
            files_attempted=files_attempted, files_scanned=files_scanned,
            files_failed=files_failed, dirs_failed=dirs_failed,
            hit_max_files_limit=hit_limit,
            truncated_due_to="max_files" if hit_limit else
                "permission_denied" if dirs_failed or files_failed else None,
            coverage_complete=complete, confidence_level=confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def trace_execution_path(store, asset_id: str, time_range: tuple[float, float] | None = None) -> dict[str, Any]:
    """Build a read-only asset timeline from persisted observations and integrity comparisons."""
    from .integrity import compare_snapshot_histories

    start_ts, end_ts = time_range or (0.0, time.time() + 1.0)
    memories = store.list_all()
    by_id = {item.get("id"): item for item in memories if isinstance(item.get("id"), str)}
    links = store.links()
    matches = []
    for item in memories:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        path = meta.get("path")
        if item.get("id") == asset_id or path == asset_id:
            matches.append(item)
    asset = matches[0] if matches else None
    asset_path = ((asset or {}).get("metadata") or {}).get("path", asset_id)
    timeline: list[dict[str, Any]] = []
    unobserved_gaps: list[dict[str, Any]] = []
    observations = store.observations(limit=10000)
    normalized_asset = Path(str(asset_path)).expanduser()
    for observation in reversed(observations):
        ts = float(observation.get("timestamp") or 0)
        if not start_ts <= ts <= end_ts:
            continue
        scope = observation.get("paths", [])
        relevant_scope = False
        for root in scope if isinstance(scope, list) else []:
            try:
                normalized_root = Path(root).expanduser().resolve()
                candidate = normalized_asset.expanduser().resolve()
                if candidate == normalized_root or normalized_root in candidate.parents:
                    relevant_scope = True
                    break
            except (OSError, RuntimeError):
                continue
        if not relevant_scope:
            continue
        timeline.append({
            "timestamp": ts, "event": "observation", "observation_id": observation.get("id"),
            "scope": scope, "coverage_complete": observation.get("coverage_complete", False),
            "confidence": observation.get("confidence_level", "unknown"),
            "files_scanned": observation.get("files_scanned", 0),
            "reason": observation.get("truncated_due_to") or (
                "; ".join(observation.get("event_monitor_errors", []))
                if not observation.get("event_monitor_active") else None
            ),
        })
        if not observation.get("event_monitor_active"):
            unobserved_gaps.append({
                "period": [ts, min(end_ts, ts)],
                "reason": "; ".join(observation.get("event_monitor_errors", []))
                    or "Event monitoring unavailable; changes between polls may be missed.",
            })

    snapshots = [item for item in memories if item.get("kind") == "device_snapshot"]
    histories = compare_snapshot_histories(snapshots, links, by_id)
    for history in histories:
        for node in history.get("nodes", []):
            if node.get("path") != asset_path:
                continue
            status = node.get("status")
            ts_ns = 0
            snapshot = by_id.get(history.get("current_snapshot_id")) or {}
            metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
            try:
                ts_ns = int(metadata.get("observation_ts_ns") or 0)
            except (TypeError, ValueError):
                ts_ns = 0
            ts = ts_ns / 1_000_000_000 if ts_ns else time.time()
            if not start_ts <= ts <= end_ts:
                continue
            confidence = "high" if status in {"HASH_MISMATCH", "MISSING", "NEW_FILE"} and metadata.get("scan", {}).get("complete") is True else "low"
            timeline.append({
                "timestamp": ts, "event": "integrity_finding", "finding_type": status,
                "finding_id": f"{history.get('current_snapshot_id')}:{asset_path}",
                "snapshot_id": history.get("current_snapshot_id"), "confidence": confidence,
                "reason": node.get("reason"), "hash_before": node.get("expected_sha256"),
                "hash_after": node.get("observed_sha256"),
            })
            if status == "HASH_MISMATCH":
                artifact_id = node.get("artifact_id")
                has_dependencies = any(
                    link.get("source_id") == artifact_id and link.get("relation") == "depends_on"
                    for link in links
                )
                risk_level = "info" if confidence != "high" else ("high" if has_dependencies else "medium")
                reasoning = (
                    "Low-confidence integrity evidence; no high-risk conclusion is justified."
                    if risk_level == "info" else
                    "Full-hash mismatch with recorded downstream dependencies."
                    if has_dependencies else
                    "Full-hash mismatch with complete scan evidence; no downstream dependency link was recorded."
                )
                timeline.append({
                    "timestamp": ts, "event": "risk_assessment", "risk_level": risk_level,
                    "confidence": confidence, "reasoning": reasoning,
                })
                timeline.append({
                    "timestamp": ts, "event": "alert_generated",
                    "severity": "warning" if risk_level in {"medium", "high"} else "info",
                    "reason": "Derived from stored integrity evidence; this is not a malware verdict.",
                })
    timeline.sort(key=lambda item: (item["timestamp"], item["event"]))
    return {
        "asset": {"id": (asset or {}).get("id"), "path": asset_path, "found_in_store": asset is not None},
        "timeline": timeline,
        "unobserved_gaps": unobserved_gaps,
        "limitations": [
            "Only persisted scan observations and snapshot links are represented.",
            "No OS event backend is configured; short-lived changes between polls may be missed.",
            "Risk assessment and alert entries are derived for this trace, not persisted as independent records.",
            "The mapper records binary artifacts, not arbitrary non-binary files; an untracked path may have no integrity finding.",
            "Missing timeline entries do not establish that an asset was unchanged or safe.",
        ],
        "read_only": True,
    }
