"""Evidence-led temporal reconstruction for Mnemos digital forensics.

This module deliberately separates observed facts, derived findings, and unknowns.
It is offline-only and reads existing records without changing the evidence store.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import analyze_graph
from .integrity import compare_snapshot_histories
from .store import MemoryStore

SCHEMA = "mnemos-forensic-case-v1"


def _meta(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("metadata")
    return value if isinstance(value, dict) else {}


def _scope(snapshot: dict[str, Any]) -> tuple[str, ...]:
    meta = _meta(snapshot)
    paths = meta.get("scope_path")
    if not isinstance(paths, list):
        scan = meta.get("scan")
        paths = scan.get("scope", []) if isinstance(scan, dict) else []
    return tuple(sorted(str(Path(p).expanduser().resolve()) for p in paths if isinstance(p, str) and p))


def _observed_time(snapshot: dict[str, Any]) -> tuple[int, str | None]:
    meta = _meta(snapshot)
    raw = meta.get("observation_ts_ns")
    try:
        ns = int(raw)
    except (TypeError, ValueError):
        ns = 0
    iso = None
    if ns > 0:
        iso = datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc).isoformat()
    return ns, iso


def reconstruct_case(store: MemoryStore, paths: list[str] | None = None) -> dict[str, Any]:
    """Build a read-only case view from stored snapshots, graph links and analysis."""
    memories = store.list_all()
    links = store.links()
    by_id = {item.get("id"): item for item in memories if isinstance(item.get("id"), str)}
    selected = tuple(sorted(str(Path(p).expanduser().resolve()) for p in (paths or []) if isinstance(p, str)))
    snapshots = [item for item in memories if item.get("kind") == "device_snapshot"]
    if selected:
        snapshots = [item for item in snapshots if _scope(item) == selected]

    groups: dict[tuple[str, str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        meta = _meta(snapshot)
        scope = _scope(snapshot)
        if not scope:
            # Preserve legacy observations but do not merge them into a known scope.
            scope = ("<unknown-scope>",)
        identity = (
            str(meta.get("device_id") or "unknown-device"),
            str(meta.get("host_env") or "unknown-host"),
            scope,
        )
        groups.setdefault(identity, []).append(snapshot)

    timelines = []
    incomplete_count = 0
    artifact_ids_by_snapshot: dict[str, set[str]] = {}
    for link in links:
        if link.get("relation") == "contains_artifact" and isinstance(link.get("source_id"), str):
            artifact_ids_by_snapshot.setdefault(link["source_id"], set()).add(link.get("target_id"))

    for (device_id, host_env, scope), entries in sorted(groups.items(), key=lambda pair: pair[0]):
        entries.sort(key=lambda item: (_observed_time(item)[0], item.get("created_at", ""), item["id"]))
        observations = []
        previous_fingerprint = None
        previous_complete = None
        has_previous = False
        for snapshot in entries:
            meta = _meta(snapshot)
            scan = meta.get("scan") if isinstance(meta.get("scan"), dict) else {}
            complete = scan.get("complete") is True
            if not complete:
                incomplete_count += 1
            timestamp_ns, timestamp = _observed_time(snapshot)
            fingerprint = meta.get("fingerprint")
            if not has_previous:
                change = "baseline"
            elif not complete or not previous_complete or not fingerprint or not previous_fingerprint:
                change = "change_indeterminate"
            elif fingerprint == previous_fingerprint:
                change = "unchanged_fingerprint"
            else:
                change = "fingerprint_changed"
            previous_fingerprint = fingerprint
            previous_complete = complete
            has_previous = True
            ids = artifact_ids_by_snapshot.get(snapshot["id"], set())
            artifact_count = sum(1 for item_id in ids if item_id in by_id and by_id[item_id].get("kind") == "binary_artifact")
            observations.append({
                "snapshot_id": snapshot["id"],
                "observed_at": timestamp or snapshot.get("created_at"),
                "observation_ts_ns": timestamp_ns or None,
                "fingerprint": fingerprint,
                "change_from_previous": change,
                "scan_complete": complete,
                "scan_limit_reached": bool(scan.get("limit_reached")),
                "depth_limit_reached": bool(scan.get("depth_limit_reached")),
                "artifact_count": artifact_count,
                "limitations": [
                    key for key in ("limit_reached", "depth_limit_reached", "skipped_symlink_roots")
                    if scan.get(key)
                ],
            })
        timelines.append({
            "device_id": device_id,
            "host_env": host_env,
            "scope": [] if scope == ("<unknown-scope>",) else list(scope),
            "scope_known": scope != ("<unknown-scope>",),
            "observation_count": len(observations),
            "observations": observations,
        })

    histories = compare_snapshot_histories(snapshots, links, by_id)
    analysis, _ = analyze_graph(store, paths=list(selected) if selected else None, persist=False)
    analysis_meta = analysis.get("metadata") if isinstance(analysis.get("metadata"), dict) else {}
    findings = analysis_meta.get("findings") if isinstance(analysis_meta.get("findings"), list) else []
    integrity_findings = []
    for history in histories:
        for node in history.get("nodes", []):
            if node.get("status") not in {"UNCHANGED", "MATCH", "PRESENT"}:
                integrity_findings.append({
                    "source": "snapshot_history",
                    "snapshot_scope": history.get("scope_label"),
                    **node,
                })

    limitations = [
        "This reconstruction uses only evidence already stored in the local Mnemos database; it performs no new acquisition.",
        "A sampled fingerprint is not equivalent to a full-file SHA-256 and cannot prove byte-for-byte identity.",
        "Incomplete scans and parser limitations prevent absence claims; UNKNOWN is not evidence of safety or compromise.",
        "Observed timestamps order recorded observations and do not independently prove when an underlying change occurred.",
        "A fingerprint change establishes that the recorded inventory differs, not that the change is malicious.",
    ]
    if not snapshots:
        case_status = "NO_EVIDENCE"
    elif incomplete_count:
        case_status = "PARTIAL_RECONSTRUCTION"
    elif len(snapshots) < 2:
        case_status = "BASELINE_ONLY"
    else:
        case_status = "RECONSTRUCTED_WITH_LIMITS"

    return {
        "schema": SCHEMA,
        "product": "Mnemos",
        "purpose": "evidence-led digital forensic reconstruction",
        "status": case_status,
        "read_only": True,
        "offline": True,
        "scope_filter": list(selected),
        "summary": {
            "snapshot_count": len(snapshots),
            "scope_count": len(timelines),
            "incomplete_snapshot_count": incomplete_count,
            "integrity_observation_count": sum(len(item.get("nodes", [])) for item in histories),
            "integrity_finding_count": len(integrity_findings),
            "analysis_finding_count": len(findings),
            "unknown_scope_status": analysis_meta.get("scope_status", "unknown_scope_incomplete"),
        },
        "timelines": timelines,
        "integrity_findings": integrity_findings,
        "derived_findings": findings,
        "analysis_provenance": {
            "rule_set": analysis_meta.get("rule_set"),
            "input_fingerprint": analysis_meta.get("input_fingerprint"),
            "source_snapshot_ids": analysis_meta.get("source_snapshot_ids", []),
            "scope_status": analysis_meta.get("scope_status", "unknown_scope_incomplete"),
        },
        "limitations": limitations,
    }
