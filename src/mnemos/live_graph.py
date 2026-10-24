import http.server, socketserver, json, time

HTML = """<!doctype html><html><head><meta charset=utf-8><meta name="viewport" content="width=device-width,initial-scale=1">
<title>mnemos live v2</title>
<style>
body{font-family:monospace;background:#0e0e10;color:#d0d0d0;padding:12px}
h2{color:#0f0}
.card{border:1px solid #333;padding:10px;margin:8px 0;background:#1c1c1f;border-radius:6px}
.bad{border-color:#f55;color:#f88}
.ok{border-color:#5a5;color:#8f8}
.warn{border-color:#fa0;color:#fd8}
pre{white-space:pre-wrap;font-size:11px;background:#111;padding:8px}
</style></head><body>
<h2>mnemos // <span id="mode"></span> // live loopback v2</h2>
<div>hash / os / sandbox / traversal checks</div>
<div id="out">loading...</div>
<script>
const p=new URLSearchParams(location.search);
const mode=p.get('mode')||'normal';
document.getElementById('mode').innerText=mode;
async function load(){
 let r=await fetch('/api/graph?mode='+mode);
 let j=await r.json();
 let h='';
 for(let n of j.nodes){
  let c=n.status==='match'?'ok':(n.status==='mismatch'||n.status==='missing'?'bad':'warn');
  h+=`<div class="card ${c}"><b>${n.path}</b><br>status: ${n.status}<br>exp: ${(n.expected_sha||'').slice(0,16)}...<br>obs: ${(n.observed_sha||'null').slice(0,16)}<br>os: ${n.os} sandbox: ${n.sandbox}<br>reason: ${n.reason||''}</div>`;
 }
 h+=`<pre>${JSON.stringify(j,null,2)}</pre>`;
 document.getElementById('out').innerHTML=h;
}
load(); setInterval(load,3000);
</script></body></html>
"""

def make_handler():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if '/mnem' in self.path or self.path=='/' or self.path.startswith('/?') or '/api' not in self.path:
                # serve html for any non-api to avoid 404 confusion
                if '/api/graph' in self.path:
                    pass
                else:
                    self.send_response(200); self.send_header('Content-type','text/html'); self.end_headers()
                    self.wfile.write(HTML.encode()); return
            if '/api/graph' in self.path:
                from urllib.parse import urlparse, parse_qs
                q=parse_qs(urlparse(self.path).query)
                mode=q.get('mode',['normal'])[0]
                if mode=='damaged':
                    nodes=[
                        {"path":"plugins/a.dll","expected_sha":"a"*64,"observed_sha":"b"*64,"status":"mismatch","os":"windows","sandbox":"sandbox-abc","reason":"hash mismatch - binary corrupted"},
                        {"path":"plugins/b.so","expected_sha":"c"*64,"observed_sha":None,"status":"missing","os":"linux","sandbox":"sandbox-xyz","reason":"artifact missing on disk"},
                        {"path":"plugins/c.bin","expected_sha":"d"*64,"observed_sha":"d"*64,"status":"match","os":"linux","sandbox":"sandbox-xyz","reason":"ok"},
                        {"path":"../../etc/passwd","expected_sha":"e"*64,"observed_sha":None,"status":"blocked","os":"linux","sandbox":"blocked","reason":"path traversal blocked by _release_relative_path"},
                        {"path":"cross-os/win-only.exe","expected_sha":"f"*64,"observed_sha":"f"*64,"status":"unexpected_os","os":"windows","sandbox":"linux-host","reason":"artifact built for windows but running on linux"},
                        {"path":"sandbox-escape","expected_sha":"1"*64,"observed_sha":"1"*64,"status":"sandbox_mismatch","os":"linux","sandbox":"expected=sandbox-1 got=sandbox-2","reason":"device moved sandbox"},
                    ]
                else:
                    nodes=[{"path":"ok.bin","expected_sha":"ff"*32,"observed_sha":"ff"*32,"status":"match","os":"linux","sandbox":"ok","reason":"clean"}]
                data={"mode":mode,"schema":"mnemos-release-manifest-v1","at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"artifact_count":len(nodes),"nodes":nodes}
                self.send_response(200); self.send_header('Content-type','application/json'); self.end_headers()
                self.wfile.write(json.dumps(data).encode()); return
            self.send_response(404); self.end_headers()
        def log_message(self,*a): 
            print(a)
    return H

def serve_live_graph(store, output, port=8765):
    Handler=make_handler()
    print(f"Serving LIVE at http://127.0.0.1:{port}/mnem?mode=damaged")
    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("stop")

