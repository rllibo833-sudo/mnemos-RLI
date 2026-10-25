"""Loopback-only, read-only viewer for integrity and dependency-impact evidence."""
from __future__ import annotations
import http.server, json, socketserver, sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from .analysis import analyze_graph
from .integrity import (
    FINDING_STATUSES, compare_snapshot_histories,
    snapshot_is_complete, snapshot_order_key, snapshot_scope_identity,
)

MAX_NODES = 100
MAX_SNAPSHOTS = 16

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mnemos-RLI Live Evidence Graph</title><style>
:root{color-scheme:dark;background:#0b1018;color:#e4edf7;font:14px system-ui,sans-serif}body{margin:0;padding:20px;max-width:1500px;margin-inline:auto}h1{font-size:22px}p,.small{color:#9eafc2}.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0}button,select{background:#172334;color:#e4edf7;border:1px solid #34475f;border-radius:6px;padding:8px}#summary{padding:12px;background:#121d2b;border:1px solid #26384c;border-radius:8px}.section{margin-top:20px}.section h2{font-size:17px}#graph-layout{display:grid;grid-template-columns:minmax(0,3fr) minmax(250px,1fr);gap:12px;margin-top:12px}#graph-wrap{background:#0e1621;border:1px solid #26384c;border-radius:8px;min-height:500px;overflow:hidden}#graph{width:100%;height:620px;display:block}#details{background:#121a25;border:1px solid #34475f;border-radius:8px;padding:14px;overflow-wrap:anywhere;align-self:start;min-height:160px}.detail-line{font-size:12px;color:#c0cedd;margin-top:9px;overflow-wrap:anywhere}.node{cursor:pointer;stroke:#09111b;stroke-width:2}.node-label{fill:#e4edf7;font-size:11px;pointer-events:none}.edge{stroke:#52667d;stroke-width:1.4;opacity:.8}.edge-label{fill:#8fa4ba;font-size:9px}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:#aebed0;margin:8px 0}.dot{display:inline-block;width:9px;height:9px;border-radius:50%}@media(max-width:800px){#graph-layout{grid-template-columns:1fr}#graph{height:480px}}
</style></head><body><h1>MNEMOS-RLI / Live Evidence Graph</h1><p>Offline analysis · stored scans only · inspected files are never executed · viewer does not write analysis results</p><div class="bar"><label>View <select id="filter"><option value="damaged">Findings and unknowns</option><option value="all">All compared artifacts</option></select></label><button id="refresh">Refresh evidence</button></div><div id="summary">Loading evidence…</div><div class="section"><h2>Evidence relationship graph</h2><p>Nodes represent stored evidence. Solid lines are relationships recorded in SQLite; dashed red lines are explicitly inferred potential-impact paths.</p><div class="legend"><span><i class="dot" style="background:#65b7ff"></i>Snapshot</span> <span><i class="dot" style="background:#56d6a0"></i>Artifact</span> <span><i class="dot" style="background:#c4a1ff"></i>Dependency</span> <span><i class="dot" style="background:#f5bd58"></i>Integrity finding</span> <span><i class="dot" style="background:#ff7784"></i>Potential impact</span></div><div id="graph-layout"><div id="graph-wrap"><svg id="graph" viewBox="0 0 1000 620" role="img" aria-label="Interactive evidence graph"></svg></div><aside id="details"><strong>Select a node</strong><div class="detail-line">Click a node to inspect evidence and connected relationships.</div></aside></div></div>
<script>
const summary=document.getElementById('summary'),svg=document.getElementById('graph'),details=document.getElementById('details'),filter=document.getElementById('filter');
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=String(x);return e}
const NS='http://www.w3.org/2000/svg';function se(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,String(a[k]));return e}
function name(n){return n.label||n.path||n.content||n.changed_path||n.id||'Evidence'}
function color(n){if(n.node_type==='impact')return '#ff7784';if(n.node_type==='integrity')return '#f5bd58';return ({device_snapshot:'#65b7ff',binary_artifact:'#56d6a0',runtime_dependency:'#c4a1ff'})[n.kind]||'#91a5ba'}
function draw(d){svg.replaceChildren();const ns=d.graph_nodes||[],es=d.graph_edges||[];if(!ns.length){const t=se('text',{x:500,y:310,'text-anchor':'middle',fill:'#9eafc2'});t.textContent='No evidence nodes. Run map-device with --path.';svg.append(t);return}
const by=new Map(ns.map(n=>[n.id,n])),pos=new Map(),W=1000,H=620;
const snapshots=ns.filter(n=>n.kind==='device_snapshot').sort((a,b)=>Number(a.observation_ts_ns||0)-Number(b.observation_ts_ns||0));
const artifacts=ns.filter(n=>n.kind==='binary_artifact'),deps=ns.filter(n=>n.kind==='runtime_dependency');
const findings=ns.filter(n=>n.node_type==='integrity'||n.node_type==='impact');
function seed(n){const group=n.kind==='device_snapshot'?0:n.kind==='binary_artifact'?1:n.kind==='runtime_dependency'?2:n.node_type==='integrity'?3:4;const peers=ns.filter(x=>(x.kind==='device_snapshot'?0:x.kind==='binary_artifact'?1:x.kind==='runtime_dependency'?2:x.node_type==='integrity'?3:4)===group);const j=peers.findIndex(x=>x.id===n.id),angle=(j/Math.max(1,peers.length))*Math.PI*2;const centers=[[500,100],[500,260],[500,430],[750,340],[250,450]],radius=[115,185,130,185,120][group];return {x:centers[group][0]+Math.cos(angle)*radius,y:centers[group][1]+Math.sin(angle)*radius}}
ns.forEach(n=>pos.set(n.id,seed(n)));
const validEdges=es.filter(e=>pos.has(e.source_id)&&pos.has(e.target_id));
for(let step=0;step<55;step++){const forces=new Map(ns.map(n=>[n.id,{x:0,y:0}]));for(let i=0;i<ns.length;i++){const a=ns[i],pa=pos.get(a.id),fa=forces.get(a.id);for(let j=i+1;j<ns.length;j++){const b=ns[j],pb=pos.get(b.id);let dx=pa.x-pb.x,dy=pa.y-pb.y,dist=Math.max(1,Math.hypot(dx,dy));const push=1800/(dist*dist);fa.x+=dx/dist*push;fa.y+=dy/dist*push;const fb=forces.get(b.id);fb.x-=dx/dist*push;fb.y-=dy/dist*push}}for(const e of validEdges){if(e.source_id===e.target_id)continue;const a=pos.get(e.source_id),b=pos.get(e.target_id),dx=b.x-a.x,dy=b.y-a.y,dist=Math.max(1,Math.hypot(dx,dy)),pull=(dist-105)*0.009,fa=forces.get(e.source_id),fb=forces.get(e.target_id);fa.x+=dx/dist*pull;fa.y+=dy/dist*pull;fb.x-=dx/dist*pull;fb.y-=dy/dist*pull}const cooling=1-step/65;for(const n of ns){const p=pos.get(n.id),f=forces.get(n.id);p.x=Math.max(35,Math.min(W-35,p.x+Math.max(-10,Math.min(10,f.x*cooling))));p.y=Math.max(35,Math.min(H-35,p.y+Math.max(-10,Math.min(10,f.y*cooling))))}}
const eg=se('g',{}),ng=se('g',{});
for(const e of es){const a=pos.get(e.source_id),b=pos.get(e.target_id);if(!a||!b)continue;const line=se('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:'edge',stroke:e.inferred?'#ff7784':e.evidence_type==='temporal_order'?'#65b7ff':'#52667d','stroke-dasharray':e.inferred?'6 5':'none','stroke-width':e.evidence_type==='temporal_order'?2:1.4});eg.append(line);if(e.relation){const t=se('text',{x:(a.x+b.x)/2+3,y:(a.y+b.y)/2-3,class:'edge-label'});t.textContent=e.relation;eg.append(t)}}
svg.append(eg);
for(const n of ns){const p=pos.get(n.id);if(!p)continue;const g=se('g',{role:'button',tabindex:0,'aria-label':name(n)});g.append(se('circle',{cx:p.x,cy:p.y,r:n.kind==='device_snapshot'?12:9,fill:color(n),class:'node'}));const t=se('text',{x:p.x+12,y:p.y+4,class:'node-label'});let label=name(n);t.textContent=label.length>22?label.slice(0,19)+'…':label;g.append(t);const show=()=>inspect(n,es,by);g.addEventListener('click',show);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show()}});ng.append(g)}
svg.append(ng);
for(const [label,y] of [['SNAPSHOT TIMELINE',28],['ARTIFACTS',195],['RUNTIME DEPENDENCIES',355],['CHANGES / IMPACT',485]]){const t=se('text',{x:16,y,fill:'#7f95ad','font-size':10});t.textContent=label;svg.append(t)}
}function inspect(n,es,by){details.replaceChildren(el('strong','',name(n)));for(const [k,v] of Object.entries(n)){if(v===null||v===undefined||v===''||k==='label'||k==='content')continue;details.append(el('div','detail-line',k+': '+(typeof v==='object'?JSON.stringify(v):v)))}const related=es.filter(e=>e.source_id===n.id||e.target_id===n.id);details.append(el('div','detail-line','Connected relationships: '+related.length));for(const e of related.slice(0,30)){const other=by.get(e.source_id===n.id?e.target_id:e.source_id);details.append(el('div','detail-line',(e.source_id===n.id?'→ ':'← ')+(e.relation||'relates_to')+' · '+(other?name(other):'unknown')+(e.inferred?' (inferred)':'')))}}
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
    links = store.links()
    by_id = {item["id"]: item for item in memories if isinstance(item.get("id"), str)}
    snapshots = [item for item in memories if item.get("kind") == "device_snapshot"]
    inventory = store.forensic_inventory()
    reports = compare_snapshot_histories(snapshots, links, by_id)
    analysis_result, _ = analyze_graph(store, persist=False)
    analysis_meta = analysis_result.get("metadata") or {}
    findings = analysis_meta.get("findings") or []
    traces = [_impact_trace(item) for item in findings if item.get("rule_id") == "potential_dependency_impact"]

    # Prioritize recent snapshots and evidence directly connected to them so a
    # large knowledge store cannot push the actual forensic timeline off-screen.
    ordered_snapshots = sorted(snapshots, key=snapshot_order_key)
    required_snapshot_ids = {
        snapshot_id
        for report in reports
        for snapshot_id in (report.get("current_snapshot_id"), report.get("baseline_snapshot_id"))
        if snapshot_id
    }
    recent_snapshots = [
        item for item in reversed(ordered_snapshots)
        if item.get("id") in required_snapshot_ids
    ][:MAX_SNAPSHOTS]
    selected_snapshot_ids = {item.get("id") for item in recent_snapshots}
    for item in reversed(ordered_snapshots):
        if len(recent_snapshots) >= MAX_SNAPSHOTS:
            break
        if item.get("id") not in selected_snapshot_ids:
            recent_snapshots.append(item)
            selected_snapshot_ids.add(item.get("id"))
    recent_snapshots.sort(key=snapshot_order_key)
    snapshot_ids = {item["id"] for item in recent_snapshots}
    artifact_ids = {link.get("target_id") for link in links
                    if link.get("relation") == "contains_artifact" and link.get("source_id") in snapshot_ids}
    dependency_ids = {link.get("target_id") for link in links
                      if link.get("relation") == "depends_on" and link.get("source_id") in artifact_ids}
    artifact_items = [by_id[item_id] for item_id in artifact_ids if item_id in by_id
                      and by_id[item_id].get("kind") == "binary_artifact"]
    dependency_items = [by_id[item_id] for item_id in dependency_ids if item_id in by_id
                        and by_id[item_id].get("kind") == "runtime_dependency"]
    priority_paths = {
        node.get("path")
        for report in reports for node in report.get("nodes", [])
        if node.get("path") and (
            node.get("status") in FINDING_STATUSES
            or node.get("status") in {"UNKNOWN", "BASELINE_ONLY"}
        )
    }
    artifact_items.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")), reverse=True)
    artifact_items.sort(key=lambda item: (str((item.get("metadata") or {}).get("path") or "") not in priority_paths))
    dependency_items.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")), reverse=True)

    graph_nodes = []
    for item in recent_snapshots:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        scan = meta.get("scan") if isinstance(meta.get("scan"), dict) else {}
        graph_nodes.append({
            "id": item["id"], "kind": "device_snapshot", "node_type": "record",
            "label": str(meta.get("captured_at") or item.get("created_at") or item["id"])[:16],
            "content": item.get("content"), "created_at": item.get("created_at"),
            "observed_at": str(meta.get("captured_at") or item.get("created_at") or ""),
            "observation_ts_ns": _safe_int(meta.get("observation_ts_ns")),
            "fingerprint": meta.get("fingerprint"), "device_id": meta.get("device_id"),
            "host_env": meta.get("host_env"), "scope": meta.get("scope_path") or scan.get("scope") or [],
            "scan_complete": snapshot_is_complete(item) and bool(meta.get("scope_path") or scan.get("scope")),
            "unscoped": not bool(meta.get("scope_path") or scan.get("scope")),
            "limit_reached": bool(scan.get("limit_reached")),
            "depth_limit_reached": bool(scan.get("depth_limit_reached")),
        })
    for item in artifact_items[:24]:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        graph_nodes.append({
            "id": item["id"], "kind": "binary_artifact", "node_type": "record",
            "label": str(meta.get("path") or item.get("content") or item["id"]),
            "content": item.get("content"), "path": meta.get("path"), "sha256": meta.get("sha256"),
            "sample_sha256": meta.get("sample_sha256"), "size_bytes": meta.get("size_bytes"),
            "file_type": meta.get("file_type"), "created_at": item.get("created_at"),
            "observed_at": str(meta.get("observed_at_ns") or item.get("created_at") or ""),
        })
    for item in dependency_items[:16]:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        graph_nodes.append({
            "id": item["id"], "kind": "runtime_dependency", "node_type": "record",
            "label": str(meta.get("name") or item.get("content") or item["id"]),
            "content": item.get("content"), "name": meta.get("name"), "format": meta.get("format"),
            "dependency_kind": meta.get("kind"), "created_at": item.get("created_at"),
            "evidence": meta.get("evidence"),
        })

    graph_ids = {node["id"] for node in graph_nodes}
    graph_edges = []
    # Preserve the exact stored relationships and identify them as recorded.
    for link in links:
        source, target = link.get("source_id"), link.get("target_id")
        if source in graph_ids and target in graph_ids:
            graph_edges.append({
                "source_id": source, "target_id": target,
                "relation": link.get("relation") or "relates_to",
                "inferred": False, "evidence_type": "stored_relationship",
            })

    # Reconstruct temporal order only within the same device/host/exact scope.
    histories = {}
    for snapshot in recent_snapshots:
        identity = snapshot_scope_identity(snapshot)
        if not identity[2]:
            continue
        histories.setdefault(identity, []).append(snapshot)
    for history in histories.values():
        history.sort(key=snapshot_order_key)
        for previous, current in zip(history, history[1:]):
            if previous["id"] in graph_ids and current["id"] in graph_ids:
                graph_edges.append({
                    "source_id": previous["id"], "target_id": current["id"],
                    "relation": "observed_after", "inferred": False,
                    "evidence_type": "temporal_order",
                })

    nodes = []
    for report in reports:
        for node in report.get("nodes", []):
            enriched = {**node, "scope_label": report.get("scope_label"),
                        "report_status": report.get("status")}
            if mode == "all" or enriched.get("status") in FINDING_STATUSES or enriched.get("status") in {"UNKNOWN", "BASELINE_ONLY"}:
                nodes.append(enriched)

    # Attach each comparison result to the two observations it compares and,
    # when available, to the persisted artifact record for that exact path.
    snapshot_by_id = {item["id"]: item for item in snapshots}
    for item in nodes:
        current_id, baseline_id = item.get("current_snapshot_id"), item.get("baseline_snapshot_id")
        artifact_id = item.get("artifact_id")
        nid = "integrity:" + str(current_id or "unknown") + ":" + str(item.get("path") or item.get("id") or len(graph_nodes))
        graph_nodes.append({
            "id": nid, "node_type": "integrity", "kind": "integrity",
            "label": str(item.get("status") or "UNKNOWN") + ": " + str(item.get("path") or "unknown path"),
            "path": item.get("path"), "status": item.get("status"), "reason": item.get("reason"),
            "expected_sha256": item.get("expected_sha256"), "observed_sha256": item.get("observed_sha256"),
            "expected_size_bytes": item.get("expected_size_bytes"), "size_bytes": item.get("size_bytes"),
            "change_flags": item.get("change_flags") or [], "scope_label": item.get("scope_label"),
            "baseline_snapshot_id": baseline_id, "current_snapshot_id": current_id,
        })
        if current_id in graph_ids:
            graph_edges.append({"source_id": current_id, "target_id": nid,
                "relation": "current_observation", "inferred": False, "evidence_type": "comparison"})
        if baseline_id in graph_ids:
            graph_edges.append({"source_id": baseline_id, "target_id": nid,
                "relation": "baseline_observation", "inferred": False, "evidence_type": "comparison"})
        if artifact_id in graph_ids:
            graph_edges.append({"source_id": artifact_id, "target_id": nid,
                "relation": "integrity_status", "inferred": False, "evidence_type": "comparison"})

    for trace in traces[:MAX_NODES]:
        ids = []
        for step in trace.get("trace_steps", []):
            nid = "impact:" + str(step.get("kind")) + ":" + str(step.get("id"))
            ids.append(nid)
            if not any(node.get("id") == nid for node in graph_nodes):
                graph_nodes.append({
                    "id": nid, "node_type": "impact", "kind": "impact",
                    "label": step.get("label"), "status": "POTENTIAL_IMPACT",
                    "summary": trace.get("summary"), "limitations": trace.get("limitations", []),
                })
        for index in range(len(ids) - 1):
            graph_edges.append({"source_id": ids[index], "target_id": ids[index + 1],
                "relation": "potential_impact", "inferred": True, "evidence_type": "derived_impact"})

    # Cap the payload after prioritizing timeline nodes, then prune every edge
    # to the exact node set that is actually rendered.
    comparison_artifact_ids = {item.get("artifact_id") for item in nodes if item.get("artifact_id")}
    def _node_priority(node):
        kind = node.get("kind")
        if kind == "device_snapshot":
            return (0, str(node.get("observed_at") or ""), str(node.get("id") or ""))
        if kind == "integrity":
            status = node.get("status")
            rank = 1 if status in FINDING_STATUSES or status in {"UNKNOWN", "BASELINE_ONLY"} else 4
            return (rank, str(node.get("path") or ""), str(node.get("id") or ""))
        if kind == "binary_artifact":
            rank = 2 if node.get("id") in comparison_artifact_ids else 3
            return (rank, str(node.get("path") or ""), str(node.get("id") or ""))
        if kind == "runtime_dependency":
            return (5, str(node.get("name") or ""), str(node.get("id") or ""))
        return (6, str(node.get("label") or ""), str(node.get("id") or ""))
    prioritized_nodes = sorted(graph_nodes, key=_node_priority)
    category_limits = {
        "device_snapshot": MAX_SNAPSHOTS,
        "integrity": 38,
        "binary_artifact": 24,
        "runtime_dependency": 16,
        "impact": 6,
    }
    graph_nodes, category_counts = [], {}
    for node in prioritized_nodes:
        category = node.get("kind") if node.get("kind") in category_limits else "impact"
        if category_counts.get(category, 0) >= category_limits[category]:
            continue
        graph_nodes.append(node)
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(graph_nodes) >= MAX_NODES:
            break
    if len(graph_nodes) < MAX_NODES:
        selected_ids = {node["id"] for node in graph_nodes}
        graph_nodes.extend(
            node for node in prioritized_nodes
            if node["id"] not in selected_ids
        )
        graph_nodes = graph_nodes[:MAX_NODES]
    rendered_ids = {node["id"] for node in graph_nodes}
    deduped_edges, seen_edges = [], set()
    for edge in graph_edges:
        key = (edge["source_id"], edge["target_id"], edge.get("relation"))
        if edge["source_id"] in rendered_ids and edge["target_id"] in rendered_ids and key not in seen_edges:
            seen_edges.add(key)
            deduped_edges.append(edge)
    graph_edges = deduped_edges[:MAX_NODES * 4]

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
                    if not reports else "Graph is rebuilt from persisted snapshots, artifact links, dependency evidence, and deterministic comparisons. No new scan or database write occurs."),
        "graph_nodes": graph_nodes, "graph_edges": graph_edges,
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
        def handle_error(self, request, client_address):
            # Browsers may cancel an in-flight navigation or refresh while a
            # response is being written. Treat that as a disconnected client,
            # not as a server failure; preserve tracebacks for real exceptions.
            exc_type, exc, _ = sys.exc_info()
            if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
                return
            super().handle_error(request, client_address)

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
