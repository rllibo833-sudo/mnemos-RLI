"""Evidence-backed offline integrity viewer for Mnemos-RLI."""
from __future__ import annotations
import http.server, json, socketserver
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_NODES = 100
HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mnemos-RLI Integrity Evidence</title><style>
:root{color-scheme:dark;background:#0b1018;color:#e4edf7;font:14px system-ui,sans-serif}body{margin:0;padding:20px;max-width:1100px;margin-inline:auto}h1{font-size:22px}p,.small{color:#9eafc2}.bar{display:flex;gap:10px;margin:14px 0}button,select{background:#172334;color:#e4edf7;border:1px solid #34475f;border-radius:6px;padding:8px}#summary{padding:12px;background:#121d2b;border:1px solid #26384c;border-radius:8px}#nodes{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin-top:12px}.card{background:#121a25;border:1px solid #34475f;border-left:4px solid #8094aa;border-radius:7px;padding:12px;overflow-wrap:anywhere}.bad{border-left-color:#ff626c}.warn{border-left-color:#f4bd50}.ok{border-left-color:#4fca9a}.path{font-weight:700}.small{font-size:12px;margin-top:5px}
</style></head><body><h1>MNEMOS-RLI / Integrity Evidence</h1><p>Offline comparison of stored complete scans · read-only</p><div class="bar"><label>View <select id="filter"><option value="damaged">Findings only</option><option value="all">All artifacts</option></select></label><button id="refresh">Refresh evidence</button></div><div id="summary">Loading evidence…</div><div id="nodes"></div>
<script>
const summary=document.getElementById('summary'),nodes=document.getElementById('nodes'),filter=document.getElementById('filter');
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e}
function card(n){const c=el('article','card '+(['MISSING','HASH_MISMATCH'].includes(n.status)?'bad':n.status==='NEW_FILE'?'warn':'ok'));c.append(el('div','path',n.path),el('div','small','Status: '+n.status),el('div','small','Expected SHA-256: '+(n.expected_sha256||'unavailable')),el('div','small','Observed SHA-256: '+(n.observed_sha256||'unavailable')),el('div','small','Size: '+(n.size_bytes??'unknown')+' bytes · OS: '+(n.os||'unknown')+' · sandbox: '+(n.sandbox_id||'unknown')),el('div','small',n.reason||''));return c}
async function load(){try{const r=await fetch('/api/graph?mode='+encodeURIComponent(filter.value),{cache:'no-store'}),d=await r.json();summary.replaceChildren(el('div','','Status: '+d.status+' · compared: '+d.compared_count+' · findings: '+d.finding_count),el('div','small','Latest: '+(d.last_scan||'none')+' · baseline: '+(d.baseline_scan||'none')),el('div','small','Scope: '+(d.scope||'none')),el('div','small',d.message||''));nodes.replaceChildren(...d.nodes.map(card))}catch(e){summary.textContent='Could not load evidence: '+String(e);nodes.replaceChildren()}}
filter.addEventListener('change',load);document.getElementById('refresh').addEventListener('click',load);load();
</script></body></html>"""

def _artifacts(store, snapshot, records):
    ids={e.get("target_id") for e in store.links() if e.get("source_id")==snapshot.get("id") and e.get("relation")=="contains_artifact"}
    out={}
    for aid in ids:
        rec=records.get(aid)
        if rec and rec.get("kind")=="binary_artifact":
            meta=rec.get("metadata") or {}; path=meta.get("path")
            if isinstance(path,str) and path: out[path]=meta
    return out

def _evidence(store, mode):
    all_records=store.list_all()
    records={x["id"]:x for x in all_records if isinstance(x.get("id"),str)}
    snapshots=[]
    for x in all_records:
        if x.get("kind")=="device_snapshot" and (x.get("metadata") or {}).get("scan",{}).get("complete") is True:
            snapshots.append(x)
    snapshots.sort(key=lambda x:(int((x.get("metadata") or {}).get("observation_ts_ns") or 0),str(x.get("created_at") or "")),reverse=True)
    if not snapshots:
        return {"status":"NO_EVIDENCE","compared_count":0,"finding_count":0,"nodes":[],"message":"Run map-device with an explicit --path to record a complete scan."}
    latest=snapshots[0]; lm=latest.get("metadata") or {}; scope=lm.get("scope_path") or (lm.get("scan") or {}).get("scope") or []
    identity=(lm.get("device_id"),lm.get("host_env"),sorted(str(v) for v in scope)); baseline=None
    for x in snapshots[1:]:
        m=x.get("metadata") or {}; s=m.get("scope_path") or (m.get("scan") or {}).get("scope") or []
        if (m.get("device_id",identity[0]),m.get("host_env",identity[1]),sorted(str(v) for v in s))==identity:
            baseline=x;break
    current=_artifacts(store,latest,records); previous=_artifacts(store,baseline,records) if baseline else {}; nodes=[]
    for path in sorted(set(current)|set(previous)):
        now,before=current.get(path),previous.get(path)
        if now is None: status,observed,expected,reason="MISSING",None,before.get("sha256"),"Present in prior complete scan but absent from latest complete scan."
        elif before is None: status,observed,expected,reason="NEW_FILE",now.get("sha256"),None,"First observed in latest scan; not proof of corruption."
        else:
            expected,observed=before.get("sha256"),now.get("sha256")
            if expected and observed: status,reason=("MATCH","Full SHA-256 matches the prior complete scan.") if expected==observed else ("HASH_MISMATCH","Full SHA-256 differs from the prior complete scan of the same device and scope.")
            else: status,reason="UNKNOWN","Full SHA-256 unavailable; sampled hashes do not prove byte equality."
        meta=now or before or {}
        nodes.append({"path":path,"status":status,"expected_sha256":expected,"observed_sha256":observed,"size_bytes":meta.get("size_bytes"),"os":lm.get("host_env") or (lm.get("device") or {}).get("os"),"sandbox_id":(lm.get("device") or {}).get("sandbox_id") or "unknown","reason":reason})
    findings=[n for n in nodes if n["status"]!="MATCH"]
    selected=nodes if mode=="all" else findings
    bm=(baseline or {}).get("metadata") or {}
    return {"status":"COMPARED" if baseline else "BASELINE_ONLY","compared_count":len(nodes),"finding_count":len(findings),"last_scan":lm.get("captured_at") or latest.get("created_at"),"baseline_scan":bm.get("captured_at") or (baseline or {}).get("created_at"),"scope":", ".join(str(v) for v in scope),"message":"Compared with the previous complete scan of the same device and scope." if baseline else "Only one complete scan exists for this scope; no damage conclusion is possible yet.","nodes":selected[:MAX_NODES]}

def make_handler(store):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed=urlparse(self.path)
            if parsed.path in ("/","/mnem"):
                body=HTML.encode()
                self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body);return
            if parsed.path=="/api/graph":
                mode=parse_qs(parsed.query).get("mode",["damaged"])[0]
                if mode not in ("damaged","all"):mode="damaged"
                body=json.dumps(_evidence(store,mode),ensure_ascii=False).encode()
                self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body);return
            self.send_error(404)
        def log_message(self,fmt,*args): return
    return Handler

class _Server(socketserver.ThreadingMixIn,http.server.HTTPServer):
    daemon_threads=True
    allow_reuse_address=True

def serve_live_graph(store, output=None, port=8765, host="127.0.0.1"):
    """Serve the read-only evidence viewer on loopback only."""
    if not 1<=int(port)<=65535: raise ValueError("port must be between 1 and 65535.")
    if host not in ("127.0.0.1","::1","localhost"): raise ValueError("live graph binds to loopback only.")
    if output:
        target=Path(output).expanduser();target.parent.mkdir(parents=True,exist_ok=True);target.write_text(HTML,encoding="utf-8")
    server=_Server((host,int(port)),make_handler(store))
    print(f"Mnemos-RLI integrity evidence: http://127.0.0.1:{port}/mnem?mode=damaged")
    print("Read-only comparison of stored scans. Ctrl-C to stop.")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0
