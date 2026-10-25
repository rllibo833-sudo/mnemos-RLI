"""Evidence-led temporal reconstruction for Mnemos digital forensics.

This module deliberately separates observed facts, derived findings, and unknowns.
It is offline-only and reads existing records without changing the evidence store.
"""
from __future__ import annotations

import json

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
            scope_known = bool(_scope(snapshot))
            complete = scan.get("complete") is True and scope_known
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
                "limitations": (
                    [key for key in ("limit_reached", "depth_limit_reached", "skipped_symlink_roots")
                     if scan.get(key)]
                    + (["missing_explicit_scope"] if not scope_known else [])
                ),
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
        "Snapshots without an explicit scan scope are retained for auditability but are never treated as complete evidence.",
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


def render_timeline_html(report: dict[str, Any], asset: str | None = None) -> str:
    """Render a self-contained, escaped HTML timeline from an existing case report."""
    import html

    events: list[dict[str, Any]] = []

    def add(timestamp: Any, kind: str, title: str, detail: dict[str, Any], color: str, size: int = 12) -> None:
        events.append({
            "timestamp": str(timestamp or "Timestamp unavailable"),
            "kind": kind, "title": title, "detail": detail, "color": color, "size": size,
        })

    trace = report.get("execution_trace")
    if isinstance(trace, dict):
        for item in trace.get("timeline", []):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("event") or "event")
            confidence = str(item.get("confidence") or "unknown").lower()
            if kind == "observation":
                color = "#24965b" if item.get("coverage_complete") else "#d5a018"
                title = "Observation"
            elif kind == "integrity_finding":
                color = "#dc4545" if confidence == "high" else "#e8892e"
                title = "Finding · " + str(item.get("finding_type") or kind)
            elif kind == "risk_assessment":
                level = str(item.get("risk_level") or "unknown").lower()
                color, size = {
                    "critical": ("#8e2020", 24), "high": ("#d83232", 21),
                    "medium": ("#e8892e", 17), "low": ("#d5a018", 13),
                    "info": ("#5288bd", 10),
                }.get(level, ("#7a8492", 11))
                add(item.get("timestamp"), "RiskAssessment", "Risk · " + level.upper(), item, color, size)
                continue
            elif kind == "filesystem_event":
                color, title = "#6686a8", "Filesystem event · " + str(item.get("event_type") or "change")
            elif kind == "alert_generated":
                color, title = "#dc4545", "Alert · " + str(item.get("severity") or "unknown")
            else:
                color, title = "#7a8492", kind.replace("_", " ").title()
            add(item.get("timestamp"), kind, title, item, color)
    else:
        for group in report.get("timelines", []):
            if not isinstance(group, dict):
                continue
            for item in group.get("observations", []):
                if isinstance(item, dict):
                    complete = item.get("scan_complete") is True
                    add(item.get("observed_at"), "Observation", "Observation · " + ("complete coverage" if complete else "partial coverage"),
                        {**item, "scope": group.get("scope", []), "device_id": group.get("device_id")},
                        "#24965b" if complete else "#d5a018")
        for item in report.get("integrity_findings", []):
            if isinstance(item, dict):
                confidence = str(item.get("confidence") or "unknown").lower()
                add(item.get("timestamp") or item.get("observed_at"), "Finding", "Finding · " + str(item.get("status") or item.get("finding_type") or "integrity"),
                    item, "#dc4545" if confidence == "high" else "#e8892e")
        for item in report.get("derived_findings", []):
            if isinstance(item, dict):
                confidence = str(item.get("confidence") or "unknown").lower()
                add(item.get("timestamp"), "Finding", "Derived finding · " + str(item.get("rule") or item.get("type") or "analysis"),
                    item, "#dc4545" if confidence == "high" else "#e8892e")

    def esc(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        return html.escape(str(value), quote=True)

    def timestamp_key(event: dict[str, Any]) -> str:
        return event["timestamp"]

    events.sort(key=timestamp_key)
    cards = []
    for event in events:
        detail_rows = "".join(
            f'<div class="detail"><span>{esc(key.replace("_", " ").title())}</span><pre>{esc(value)}</pre></div>'
            for key, value in event["detail"].items()
            if value is not None and value != "" and key not in {"event"}
        )
        cards.append(
            f'<article class="event" style="--event-color:{event["color"]};--dot-size:{event["size"]}px">'
            f'<div class="marker" aria-hidden="true"></div><div class="card" tabindex="0">'
            f'<div class="meta"><time>{esc(event["timestamp"])}</time><span>{esc(event["kind"])}</span></div>'
            f'<h2>{esc(event["title"])}</h2><div class="details">{detail_rows or "<p>No additional details recorded.</p>"}</div>'
            f'</div></article>'
        )
    title = "Mnemos Forensic Timeline"
    subtitle = f"Asset: {asset}" if asset else f"Case status: {report.get('status', 'unknown')}"
    summary = report.get("summary", {})
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>
:root{{color-scheme:light dark;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;background:#10151d;color:#e8edf4}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(145deg,#10151d,#171f2b);padding:28px 16px 56px}}
main{{max-width:980px;margin:auto}}header{{margin:0 0 30px}}h1{{font-size:clamp(1.6rem,4vw,2.4rem);margin:0 0 8px}}.sub{{color:#aab7c8;overflow-wrap:anywhere}}
.summary{{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}}.pill{{padding:8px 12px;border:1px solid #344255;border-radius:10px;background:#1b2634;color:#d8e2ee;font-size:.9rem}}
.legend{{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0;color:#b7c4d4;font-size:.85rem}}.key{{display:inline-flex;align-items:center;gap:6px}}.swatch{{width:9px;height:9px;border-radius:50%;background:var(--c)}}
.timeline{{position:relative;padding:2px 0 2px 28px}}.timeline:before{{content:"";position:absolute;left:9px;top:0;bottom:0;width:2px;background:#344255}}
.event{{position:relative;margin:0 0 20px;--event-color:#7a8492;--dot-size:12px}}.marker{{position:absolute;left:-25px;top:23px;width:var(--dot-size);height:var(--dot-size);border-radius:50%;background:var(--event-color);box-shadow:0 0 0 4px #10151d,0 0 0 5px var(--event-color)}}
.card{{border:1px solid #303d4f;border-left:3px solid var(--event-color);border-radius:12px;padding:16px 18px;background:#192330;outline:none;transition:transform .15s,border-color .15s}}
.card:hover,.card:focus{{transform:translateX(3px);border-color:var(--event-color)}}.meta{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;color:#aab7c8;font-size:.78rem}}h2{{font-size:1.05rem;margin:10px 0 0;color:#f2f5f9}}
.details{{display:none;margin-top:14px;border-top:1px solid #303d4f;padding-top:10px}}.card:hover .details,.card:focus .details,.card:focus-within .details{{display:block}}.detail{{margin:10px 0}}.detail span{{display:block;color:#aab7c8;font-size:.78rem;margin-bottom:4px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font: .82rem/1.5 ui-monospace,SFMono-Regular,monospace;margin:0;color:#dce5ef}}.empty{{padding:20px;border:1px dashed #455368;border-radius:12px;color:#aab7c8}}
footer{{margin-top:32px;color:#8492a5;font-size:.8rem}}@media(prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
</style></head><body><main><header><h1>{esc(title)}</h1><div class="sub">{esc(subtitle)}</div>
<div class="summary"><span class="pill">Status: {esc(report.get("status", "unknown"))}</span>
<span class="pill">Snapshots: {esc(summary.get("snapshot_count", 0))}</span>
<span class="pill">Findings: {esc(summary.get("integrity_finding_count", 0))}</span>
<span class="pill">Timeline events: {len(events)}</span></div>
<div class="legend"><span class="key"><i class="swatch" style="--c:#24965b"></i>Complete observation</span>
<span class="key"><i class="swatch" style="--c:#d5a018"></i>Partial observation</span>
<span class="key"><i class="swatch" style="--c:#e8892e"></i>Low/unknown confidence finding</span>
<span class="key"><i class="swatch" style="--c:#dc4545"></i>High confidence finding</span>
<span class="key"><i class="swatch" style="--c:#8e2020"></i>High/critical risk</span></div>
<p class="sub">Hover or focus an event card to inspect reasoning, timestamp, and unobserved scope. Evidence is historical; a missing event is not proof that no change occurred.</p></header>
<section class="timeline" aria-label="Forensic event timeline">{''.join(cards) if cards else '<div class="empty">No timeline events were found in the stored evidence for this selection.</div>'}</section>
<footer>Generated locally by Mnemos from stored evidence. No external resources or network requests are required.</footer></main></body></html>
"""
