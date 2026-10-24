"""Loopback-only, read-only viewer for integrity and dependency-impact evidence."""
from __future__ import annotations
import http.server, json, socketserver
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .analysis import analyze_graph
from .integrity import FINDING_STATUSES, compare_snapshot_histories

MAX_NODES = 100
HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mnemos-RLI Live Evidence Graph</title><style>
:root{color-scheme:dark;background:#0b1018;color:#e4edf7;font:14px system-ui,sans-serif}body{margin:0;padding:20px;max-width:1500px;margin-inline:auto}h1{font-size:22px}p,.small{color:#9eafc2}.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0}button,select{background:#172334;color:#e4edf7;border:1px solid #34475f;border-radius:6px;padding:8px}#summary{padding:12px;background:#121d2b;border:1px solid #26384c;border-radius:8px}.section{margin-top:20px}.section h2{font-size:17px}#graph-layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(250px,1fr);gap:12px;margin-top:12px}#graph-wrap{background:#0e1621;border:1px solid #26384c;border-radius:8px;min-height:500px;overflow:hidden}#graph{width:100%;height:620px;display:block}#details{background:#121a25;border:1px solid #34475f;border-radius:8px;padding:14px;overflow-wrap:anywhere;align-self:start;min-height:160px}.detail-line{font-size:12px;color:#c0cedd;margin-top:9px;overflow-wrap:anywhere}.node{cursor:pointer;stroke:#09111b;stroke-width:2}.node-label{fill:#e4edf7;font-size:11px;pointer-events:none}.edge{stroke:#52667d;stroke-width:1.4;opacity:.8}.edge-label{fill:#8fa4ba;font-size:9px}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:#aebed0;margin:8px 0}.dot{display:inline-block;width:9px;height:9px;border-radius:50%}@media(max-width:800px){#graph-layout{grid-template-columns:1fr}#graph{height:480px}}
</style></head><body><h1>MNEMOS-RLI / Live Evidence Graph</h1><p>Offline analysis · stored scans only · inspected files are never executed · viewer does not write analysis results</p><div class="bar"><label>View <select id="filter"><option value="damaged">Findings and unknowns</option><option value="all">All compared artifacts</option></select></label><button id="refresh">Refresh evidence</button></div><div id="summary">Loading evidence…</div><div class="section"><h2>Evidence relationship graph</h2><p>Nodes represent stored evidence. Solid lines are relationships recorded in SQLite; dashed red lines are explicitly inferred potential-impact paths.</p><div class="legend"><span><i class="dot" style="background:#65b7ff"></i>Snapshot</span> <span><i class="dot" style="background:#56d6a0"></i>Artifact</span> <span><i class="dot" style="background:#c4a1ff"></i>Dependency</span> <span><i class="dot" style="background:#f5bd58"></i>Integrity finding</span> <span><i class="dot" style="background:#ff7784"></i>Potential impact</span></div><div id="graph-layout"><div id="graph-wrap"><svg id="graph" viewBox="0 0 1000 620" role="img" aria-label="Interactive evidence graph"></svg></div><aside id="details"><strong>Select a node</strong><div class="detail-line">Click a node to inspect evidence and connected relationships.</div></aside></div></div>
<script>
const summary=document.getElementById('summary'),svg=document.getElementById('graph'),details=document.getElementById('details'),filter=document.getElementById('filter');
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=String(x);return e}
const NS='http://www.w3.org/2000/svg';function se(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,String(a[k]));return e}
function name(n){return n.label||n.path||n.content||n.changed_path||n.id||'Evidence'}
function color(n){if(n.node_type==='impact')return '#ff7784';if(n.node_type==='integrity')return '#f5bd58';return ({device_snapshot:'#65b7ff',binary_artifact:'#56d6a0',runtime_dependency:'#c4a1ff'})[n.kind]||'#91a5ba'}
function draw(d){svg.replaceChildren();const ns=d.graph_nodes||[],es=d.graph_edges||[];if(!ns.length){const t=se('text',{x:500,y:310,'text-anchor':'middle',fill:'#9eafc2'});t.textContent='No evidence nodes. Run map-device with --path.';svg.append(t);return}const groups={device_snapshot:[],binary_artifact:[],runtime_dependency:[],integrity:[],impact:[],other:[]};for(const n of ns){let k=n.node_type==='integrity'?'integrity':n.node_type==='impact'?'impact':groups[n.kind]?n.kind:'other';groups[k].push(n)}const lanes=Object.keys(groups).filter(k=>groups[k].length),pos=new Map();lanes.forEach((k,j)=>groups[k].forEach((n,i)=>pos.set(n.id,{x:70+(j+.5)*860/lanes.length,y:40+(i+1)*540/(groups[k].length+1)})));const by=new Map(ns.map(n=>[n.id,n])),eg=se('g',{}),ng=se('g',{});for(const e of es){const a=pos.get(e.source_id),b=pos.get(e.target_id);if(!a||!b)continue;eg.append(se('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:'edge',stroke:e.inferred?'#ff7784':'#52667d','stroke-dasharray':e.inferred?'6 5':'none'}));if(e.relation){const t=se('text',{x:(a.x+b.x)/2+3,y:(a.y+b.y)/2-3,class:'edge-label'});t.textContent=e.relation;eg.append(t)}}svg.append(eg);for(const n of ns){const p=pos.get(n.id);if(!p)continue;const g=se('g',{role:'button',tabindex:0,'aria-label':name(n)});g.append(se('circle',{cx:p.x,cy:p.y,r:9,fill:color(n),class:'node'}));const t=se('text',{x:p.x+12,y:p.y+4,class:'node-label'});let label=name(n);t.textContent=label.length>24?label.slice(0,21)+'…':label;g.append(t);const show=()=>inspect(n,es,by);g.addEventListener('click',show);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show()}});ng.append(g)}svg.append(ng)}
function inspect(n,es,by){details.replaceChildren(el('strong','',name(n)));for(const [k,v] of Object.entries(n)){if(v===null||v===undefined||v===''||k==='label'||k==='content')continue;details.append(el('div','detail-line',k+': '+(typeof v==='object'?JSON.stringify(v):v)))}const related=es.filter(e=>e.source_id===n.id||e.target_id===n.id);details.append(el('div','detail-line','Connected relationships: '+related.length));for(const e of related.slice(0,30)){const other=by.get(e.source_id===n.id?e.target_id:e.source_id);details.append(el('div','detail-line',(e.source_id===n.id?'→ ':'← ')+(e.relation||'relates_to')+' · '+(other?name(other):'unknown')+(e.inferred?' (inferred)':'')))}}
async function load(){try{const r=await fetch('/api/graph?mode='+encodeURIComponent(filter.value),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();summary.replaceChildren(el('div','','Status: '+d.status+' · graph nodes: '+(d.graph_nodes||[]).length+' · relationships: '+(d.graph_edges||[]).length+' · compared artifacts: '+d.compared_count+' · integrity findings: '+d.integrity_finding_count+' · potential impacts: '+d.dependency_impact_count+' · unknown: '+d.unknown_count),el('div','detail-line','SQLite: '+d.inventory.snapshots+' snapshots · '+d.inventory.binary_artifacts+' artifacts · '+d.inventory.runtime_dependencies+' dependencies · '+d.inventory.snapshot_artifact_links+' snapshot-artifact links'),el('div','detail-line','Empty-scope snapshots: '+d.inventory.empty_scope_count+' · incomplete snapshots: '+d.inventory.incomplete_snapshot_count+' · '+(d.message||'')));draw(d)}catch(e){summary.textContent='Could not load evidence: '+String(e);svg.replaceChildren()}}
document.getElementById('refresh').addEventListener('click',load);load();
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
    graph_nodes = []
    for item in memories:
        kind = item.get("kind") or "note"
        if kind not in {"device_snapshot", "binary_artifact", "runtime_dependency"}:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        graph_nodes.append({"id": item["id"], "kind": kind, "node_type": "record",
            "label": item.get("content") or item["id"], "content": item.get("content"),
            "source": item.get("source"), "created_at": item.get("created_at"),
            "metadata": metadata, "path": metadata.get("path"), "sha256": metadata.get("sha256")})
    graph_nodes = graph_nodes[:MAX_NODES]
    graph_ids = {n["id"] for n in graph_nodes}
    graph_edges = [{"source_id": l["source_id"], "target_id": l["target_id"],
        "relation": l.get("relation") or "relates_to", "inferred": False}
        for l in store.links() if l.get("source_id") in graph_ids and l.get("target_id") in graph_ids][:MAX_NODES * 3]
    known = {n["id"] for n in graph_nodes}
    for item in nodes[:MAX_NODES]:
        nid = "integrity:" + str(item.get("id") or item.get("path") or len(graph_nodes))
        graph_nodes.append({"id": nid, "node_type": "integrity", "kind": "integrity",
            "label": item.get("path") or nid, "status": item.get("status"),
            "expected_sha256": item.get("expected_sha256"), "observed_sha256": item.get("observed_sha256"),
            "reason": item.get("reason"), "scope_label": item.get("scope_label")})
        known.add(nid)
    for trace in traces[:MAX_NODES]:
        ids = []
        for step in trace.get("trace_steps", []):
            nid = "impact:" + str(step.get("kind")) + ":" + str(step.get("id"))
            ids.append(nid)
            if nid not in known:
                graph_nodes.append({"id": nid, "node_type": "impact", "kind": step.get("kind"),
                    "label": step.get("label"), "status": "POTENTIAL_IMPACT",
                    "summary": trace.get("summary"), "limitations": trace.get("limitations", [])})
                known.add(nid)
        for i in range(len(ids)-1):
            graph_edges.append({"source_id": ids[i], "target_id": ids[i+1],
                "relation": "potential_impact", "inferred": True})
    graph_edges = [e for e in graph_edges if e["source_id"] in known and e["target_id"] in known][:MAX_NODES * 4]
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
                    if not reports else "Analysis is derived from stored evidence on each refresh; no new scan or analysis-result write is performed."),
        "graph_nodes": graph_nodes[:MAX_NODES], "graph_edges": graph_edges,
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
