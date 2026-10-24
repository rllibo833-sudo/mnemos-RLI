"""Loopback-only viewer for shared offline integrity comparisons."""
from __future__ import annotations
import http.server, json, socketserver
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .integrity import FINDING_STATUSES, compare_snapshot_histories

MAX_NODES = 100
HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mnemos-RLI Integrity Evidence</title><style>
:root{color-scheme:dark;background:#0b1018;color:#e4edf7;font:14px system-ui,sans-serif}body{margin:0;padding:20px;max-width:1100px;margin-inline:auto}h1{font-size:22px}p,.small{color:#9eafc2}.bar{display:flex;gap:10px;margin:14px 0}button,select{background:#172334;color:#e4edf7;border:1px solid #34475f;border-radius:6px;padding:8px}#summary{padding:12px;background:#121d2b;border:1px solid #26384c;border-radius:8px}#nodes{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin-top:12px}.card{background:#121a25;border:1px solid #34475f;border-left:4px solid #8094aa;border-radius:7px;padding:12px;overflow-wrap:anywhere}.bad{border-left-color:#ff626c}.warn{border-left-color:#f4bd50}.ok{border-left-color:#4fca9a}.path{font-weight:700}.small{font-size:12px;margin-top:5px}
</style></head><body><h1>MNEMOS-RLI / Integrity Evidence</h1><p>Offline comparison · stored evidence only · inspected files are never executed</p><div class="bar"><label>View <select id="filter"><option value="damaged">Findings and unknowns</option><option value="all">All compared artifacts</option></select></label><button id="refresh">Refresh evidence</button></div><div id="summary">Loading evidence…</div><div id="nodes"></div>
<script>
const summary=document.getElementById('summary'),nodes=document.getElementById('nodes'),filter=document.getElementById('filter');
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e}
function card(n){const bad=['MISSING','HASH_MISMATCH'].includes(n.status),warn=['NEW_FILE','PERM_CHANGE','SIZE_CHANGE','SAMPLED_MISMATCH','OWNER_CHANGE','FILE_TYPE_CHANGE','UNKNOWN'].includes(n.status);const c=el('article','card '+(bad?'bad':warn?'warn':'ok'));c.append(el('div','path',n.path),el('div','small','Status: '+n.status),el('div','small','Expected SHA-256: '+(n.expected_sha256||'unavailable')),el('div','small','Observed SHA-256: '+(n.observed_sha256||'unavailable')),el('div','small','Size: '+(n.size_bytes??'unknown')+' bytes · OS: '+(n.os||'unknown')+' · arch: '+(n.architecture||'unknown')+' · sandbox: '+(n.sandbox_id||'unknown')),el('div','small','Changes: '+((n.change_flags||[]).join(', ')||'none recorded')),el('div','small',n.reason||''));return c}
async function load(){try{const r=await fetch('/api/graph?mode='+encodeURIComponent(filter.value),{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();summary.replaceChildren(el('div','','Status: '+d.status+' · artifacts: '+d.compared_count+' · findings: '+d.finding_count+' · unknown: '+(d.unknown_count||0)),el('div','small','Latest scan: '+(d.last_scan||'none')+' · baseline: '+(d.baseline_scan||'none')),el('div','small','Scope: '+(d.scope_label||'none')),el('div','small','Snapshot: '+(d.current_snapshot_id||'none')+' · baseline ID: '+(d.baseline_snapshot_id||'none')),el('div','small',d.message||''));nodes.replaceChildren(...d.nodes.map(card))}catch(e){summary.textContent='Could not load evidence: '+String(e);nodes.replaceChildren()}}
filter.addEventListener('change',load);document.getElementById('refresh').addEventListener('click',load);load();
</script></body></html>"""

def _evidence(store, mode):
    memories = store.list_all()
    by_id = {item["id"]: item for item in memories if isinstance(item.get("id"), str)}
    snapshots = [item for item in memories if item.get("kind") == "device_snapshot"]
    reports = compare_snapshot_histories(snapshots, store.links(), by_id)
    if not reports:
        return {"status":"NO_EVIDENCE","compared_count":0,"finding_count":0,"unknown_count":0,
                "current_snapshot_id":None,"baseline_snapshot_id":None,"last_scan":None,
                "baseline_scan":None,"scope_label":None,"message":"Run map-device with an explicit --path to record a scan.","nodes":[]}
    report = reports[0]
    nodes = report["nodes"]
    if mode != "all":
        nodes = [node for node in nodes if node["status"] in FINDING_STATUSES or node["status"] == "UNKNOWN"]
    return {**report, "nodes": nodes[:MAX_NODES]}

def make_handler(store):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/mnem"):
                body = HTML.encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
                self.end_headers(); self.wfile.write(body); return
            if parsed.path == "/api/graph":
                mode = parse_qs(parsed.query).get("mode", ["damaged"])[0]
                if mode not in ("damaged", "all"): mode = "damaged"
                try: body = json.dumps(_evidence(store, mode), ensure_ascii=False).encode("utf-8")
                except Exception:
                    self.send_error(500, "Unable to read stored integrity evidence"); return
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
                self.end_headers(); self.wfile.write(body); return
            self.send_error(404)
        def log_message(self, fmt, *args): return
    return Handler

class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def serve_live_graph(store, output=None, port=8765, host="127.0.0.1"):
    """Serve the read-only evidence viewer on loopback only."""
    if not 1 <= int(port) <= 65535: raise ValueError("port must be between 1 and 65535.")
    if host not in ("127.0.0.1", "::1"): raise ValueError("live graph binds to loopback only.")
    if output:
        target = Path(output).expanduser(); target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HTML, encoding="utf-8")
    server = _Server((host, int(port)), make_handler(store))
    print(f"Mnemos-RLI integrity evidence: http://127.0.0.1:{port}/mnem?mode=damaged")
    print("Read-only comparison of stored scans. Ctrl-C to stop.")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0
