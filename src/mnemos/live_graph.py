"""Loopback-only, read-only viewer for integrity and dependency-impact evidence."""
from __future__ import annotations
import http.server, json, socketserver
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .analysis import analyze_graph
from .integrity import FINDING_STATUSES, compare_snapshot_histories

MAX_NODES = 100
HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mnemos-RLI Live Evidence Graph</title><style>
:root{color-scheme:dark;background:#0b1018;color:#e4edf7;font:14px system-ui,sans-serif}body{margin:0;padding:20px;max-width:1150px;margin-inline:auto}h1{font-size:22px}p,.small{color:#9eafc2}.bar{display:flex;gap:10px;margin:14px 0}button,select{background:#172334;color:#e4edf7;border:1px solid #34475f;border-radius:6px;padding:8px}#summary{padding:12px;background:#121d2b;border:1px solid #26384c;border-radius:8px}.section{margin-top:20px}.section h2{font-size:17px}#nodes,#traces{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:10px;margin-top:12px}.card{background:#121a25;border:1px solid #34475f;border-left:4px solid #8094aa;border-radius:7px;padding:12px;overflow-wrap:anywhere}.bad{border-left-color:#ff626c}.warn{border-left-color:#f4bd50}.ok{border-left-color:#4fca9a}.impact{border-left-color:#b18cff}.path{font-weight:700;overflow-wrap:anywhere}.small{font-size:12px;margin-top:6px;overflow-wrap:anywhere}.chain{display:flex;flex-direction:column;gap:6px;margin-top:10px}.step{border:1px solid #34475f;border-radius:5px;padding:8px;background:#0e1621;overflow-wrap:anywhere}.arrow{text-align:center;color:#9eafc2}.tag{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#c7b0ff}
</style></head><body><h1>MNEMOS-RLI / Live Evidence Graph</h1><p>Offline analysis · stored scans only · inspected files are never executed · viewer does not write analysis results</p><div class="bar"><label>View <select id="filter"><option value="damaged">Findings and unknowns</option><option value="all">All compared artifacts</option></select></label><button id="refresh">Refresh evidence</button></div><div id="summary">Loading evidence…</div><div class="section"><h2>Dependency impact traces</h2><p>Changed evidence → candidate dependency → active consumer. A basename match is potential impact, not proof of runtime loading or breakage.</p><div id="traces"></div></div><div class="section"><h2>Integrity observations</h2><div id="nodes"></div></div>
<script>
const summary=document.getElementById('summary'),nodes=document.getElementById('nodes'),traces=document.getElementById('traces'),filter=document.getElementById('filter');
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e}
function integrityCard(n){const bad=['MISSING','HASH_MISMATCH'].includes(n.status),warn=['NEW_FILE','PERM_CHANGE','SIZE_CHANGE','SAMPLED_MISMATCH','OWNER_CHANGE','FILE_TYPE_CHANGE','UNKNOWN','BASELINE_ONLY'].includes(n.status);const c=el('article','card '+(bad?'bad':warn?'warn':'ok'));c.append(el('div','path',n.path||'(path unavailable)'),el('div','small','Status: '+n.status),el('div','small','Expected SHA-256: '+(n.expected_sha256||'unavailable')),el('div','small','Observed SHA-256: '+(n.observed_sha256||'unavailable')),el('div','small','OS: '+(n.os||'unknown')+' · arch: '+(n.architecture||'unknown')+' · sandbox: '+(n.sandbox_id||'unknown')),el('div','small','Changes: '+((n.change_flags||[]).join(', ')||'none recorded')),el('div','small','Baseline: '+(n.baseline_snapshot_id||'none')+' · current: '+(n.current_snapshot_id||'none')),el('div','small',n.reason||''));return c}
function impactCard(n){const c=el('article','card impact');c.append(el('div','tag','Potential dependency impact'),el('div','path',n.changed_path||'(changed path unavailable)'),el('div','small','Status: '+n.status+' · match: '+n.match_method),el('div','small',n.summary||''));const chain=el('div','chain');for(let i=0;i<(n.trace_steps||[]).length;i++){const s=n.trace_steps[i];chain.append(el('div','step',s.label+' ['+s.kind+']'));if(i<n.trace_steps.length-1)chain.append(el('div','arrow','↓'));}c.append(chain,el('div','small','Baseline snapshot: '+(n.baseline_snapshot_id||'unknown')),el('div','small','Current snapshot: '+(n.current_snapshot_id||'unknown')),el('div','small','Scope: '+(n.scope_label||'unknown')),el('div','small','Evidence sources: '+((n.evidence_sources||[]).map(x=>x.artifact_path||x.source||x.method||JSON.stringify(x)).join('; ')||'not recorded')));for(const limit of (n.limitations||[]))c.append(el('div','small','Limit: '+limit));return c}
async function load(){try{const r=await fetch('/api/graph?mode='+encodeURIComponent(filter.value),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();summary.replaceChildren(el('div','','Status: '+d.status+' · compared artifacts: '+d.compared_count+' · integrity findings: '+d.integrity_finding_count+' · potential dependency impacts: '+d.dependency_impact_count+' · unknown: '+d.unknown_count),el('div','small','SQLite inventory: '+d.inventory.snapshots+' snapshots · '+d.inventory.binary_artifacts+' artifacts · '+d.inventory.runtime_dependencies+' dependencies · '+d.inventory.snapshot_artifact_links+' snapshot-artifact links'),el('div','small','Scope errors: '+d.inventory.empty_scope_count+' empty-scope snapshots · incomplete snapshots: '+d.inventory.incomplete_snapshot_count),el('div','small','Latest scan: '+(d.last_scan||'none')+' · baseline: '+(d.baseline_scan||'none')),el('div','small','Scope(s): '+(d.scope_label||'none')),el('div','small','Analysis scope: '+(d.analysis_scope_status||'unknown')+' · source snapshots: '+((d.analysis_source_snapshot_ids||[]).join(', ')||'none')),el('div','small',d.message||''));traces.replaceChildren(...d.traces.map(impactCard));nodes.replaceChildren(...d.nodes.map(integrityCard));}catch(e){summary.textContent='Could not load evidence: '+String(e);nodes.replaceChildren();traces.replaceChildren()}}
filter.addEventListener('change',load);document.getElementById('refresh').addEventListener('click',load);load();
</script></body></html>"""

def _impact_trace(finding: dict) -> dict:
    evidence = finding.get("evidence") or {}
    dependency_id = evidence.get("dependency_id") or finding.get("subject_id")
    dependency_name = evidence.get("dependency_name") or dependency_id or "unknown dependency"
    changed_path = evidence.get("changed_path") or "(path unavailable)"
    changed_id = evidence.get("changed_artifact_id") or changed_path
    dependents = evidence.get("dependent_artifacts") or []
    steps = [
        {"kind": "changed_artifact", "id": changed_id, "label": f"Changed evidence: {changed_path}"},
        {"kind": "runtime_dependency", "id": dependency_id, "label": f"Candidate dependency: {dependency_name}"},
    ]
    edges = [{"source_id": changed_id, "target_id": dependency_id, "relation": "potentially_affects"}]
    for item in dependents:
        artifact_id = item.get("artifact_id") or item.get("path") or "unknown artifact"
        artifact_path = item.get("path") or artifact_id
        steps.append({"kind": "dependent_artifact", "id": artifact_id, "label": f"Potential consumer: {artifact_path}"})
        edges.append({"source_id": dependency_id, "target_id": artifact_id, "relation": "potential_consumer"})
    return {
        "id": f"{changed_id}:{dependency_id}:{evidence.get('change_current_snapshot_id') or 'unknown'}",
        "status": "POTENTIAL_IMPACT", "summary": finding.get("summary"),
        "changed_path": changed_path, "change_status": evidence.get("change_status"),
        "dependency_id": dependency_id, "dependency_name": dependency_name,
        "match_method": evidence.get("match_method", "unknown"),
        "baseline_snapshot_id": evidence.get("change_baseline_snapshot_id"),
        "current_snapshot_id": evidence.get("change_current_snapshot_id"),
        "scope_label": ", ".join(evidence.get("scope") or []),
        "dependent_artifacts": dependents, "evidence_sources": evidence.get("evidence_sources") or [],
        "limitations": evidence.get("limitations") or [], "trace_steps": steps, "edges": edges,
    }

def _evidence(store, mode):
    memories = store.list_all()
    by_id = {item["id"]: item for item in memories if isinstance(item.get("id"), str)}
    snapshots = [item for item in memories if item.get("kind") == "device_snapshot"]
    inventory = store.forensic_inventory()
    reports = compare_snapshot_histories(snapshots, store.links(), by_id)
    analysis_result, _ = analyze_graph(store, persist=False)
    analysis_meta = analysis_result.get("metadata") or {}
    findings = analysis_meta.get("findings") or []
    traces = [_impact_trace(item) for item in findings if item.get("rule_id") == "potential_dependency_impact"]
    nodes = []
    for report in reports:
        for node in report.get("nodes", []):
            item = {**node, "node_type": "integrity", "scope_label": report.get("scope_label")}
            if mode == "all" or item.get("status") in FINDING_STATUSES or item.get("status") in {"UNKNOWN", "BASELINE_ONLY"}:
                nodes.append(item)
    latest = reports[0] if reports else {}
    integrity_count = sum(int(item.get("finding_count") or 0) for item in reports)
    unknown_count = sum(int(item.get("unknown_count") or 0) for item in reports)
    compared_count = sum(int(item.get("compared_count") or 0) for item in reports)
    status = ("NO_EVIDENCE" if not reports else
              "INCOMPLETE_SCAN" if any(item.get("status") == "INCOMPLETE_SCAN" for item in reports) else
              "COMPARED" if any(item.get("status") == "COMPARED" for item in reports) else "BASELINE_ONLY")
    return {
        "status": status, "inventory": inventory,
        "unscoped_snapshot_ids": inventory["empty_scope_snapshot_ids"],
        "compared_count": compared_count, "finding_count": integrity_count + len(traces),
        "integrity_finding_count": integrity_count, "dependency_impact_count": len(traces),
        "unknown_count": unknown_count, "current_snapshot_id": latest.get("current_snapshot_id"),
        "baseline_snapshot_id": latest.get("baseline_snapshot_id"), "last_scan": latest.get("last_scan"),
        "baseline_scan": latest.get("baseline_scan"),
        "scope_label": " | ".join(item.get("scope_label") or "" for item in reports) or None,
        "analysis_scope_status": analysis_meta.get("scope_status", "unknown_scope_incomplete"),
        "analysis_source_snapshot_ids": analysis_meta.get("source_snapshot_ids", []),
        "analysis_counts": analysis_meta.get("counts", {}),
        "dependency_states": analysis_meta.get("dependency_states", []),
        "message": ("No device snapshot exists yet. Run map-device with an explicit --path; two complete scans of the same scope are needed for comparisons."
                    if not reports else
                    "Analysis is derived from stored evidence on each refresh; no new scan or analysis-result write is performed."),
        "traces": traces[:MAX_NODES], "nodes": nodes[:MAX_NODES],
        "edges": [edge for trace in traces for edge in trace.get("edges", [])][:MAX_NODES * 3],
    }

def make_handler(store):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/mnem"):
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/graph":
                mode = parse_qs(parsed.query).get("mode", ["damaged"])[0]
                if mode not in ("damaged", "all"):
                    mode = "damaged"
                try:
                    body = json.dumps(_evidence(store, mode), ensure_ascii=False).encode("utf-8")
                except Exception:
                    self.send_error(500, "Unable to read stored integrity and dependency evidence")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)
        def log_message(self, fmt, *args):
            return
    return Handler

class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def serve_live_graph(store, output=None, port=8765, host="127.0.0.1"):
    """Serve the read-only evidence viewer on loopback only."""
    if not 1 <= int(port) <= 65535:
        raise ValueError("port must be between 1 and 65535.")
    if host not in ("127.0.0.1", "::1"):
        raise ValueError("live graph binds to loopback only.")
    if output:
        target = Path(output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HTML, encoding="utf-8")
    server = _Server((host, int(port)), make_handler(store))
    print(f"Mnemos-RLI Live Evidence Graph: http://127.0.0.1:{port}/mnem")
    print("Read-only view of stored scans and dynamically derived analysis. Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
