"""Generate a dependency-free HTML graph from actual Mnemos records."""

import json
from html import escape
from pathlib import Path
from typing import Any


def render_graph(memories: list[dict[str, Any]], links: list[dict[str, Any]], output: str | Path) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"nodes": memories, "links": links}, ensure_ascii=False).replace("</", "<\\/")
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mnemos Memory Graph</title>
<style>
:root{color-scheme:dark;--bg:#080b12;--panel:#101725;--line:#26354b;--text:#e8efff;--muted:#94a3b8;--accent:#7dd3fc}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 50% 45%,#101c30 0,#080b12 65%);color:var(--text);font:14px system-ui,sans-serif;overflow:hidden}
header{position:absolute;z-index:2;top:16px;left:18px;pointer-events:none}h1{font-size:20px;margin:0 0 5px;letter-spacing:.04em}p{margin:0;color:var(--muted)}#stats{position:absolute;top:18px;right:18px;color:var(--muted);text-align:right;z-index:2}
#graph{width:100vw;height:100vh;display:block}line{stroke:#4a6a8b;stroke-opacity:.58;stroke-width:1}line:hover{stroke:var(--accent);stroke-opacity:1}
.node{cursor:pointer;stroke:#b9e9ff;stroke-opacity:.7;stroke-width:1.2}.node:hover{stroke:#fff;stroke-width:2.5}text{fill:#cfe8ff;font-size:10px;pointer-events:none}
#detail{position:absolute;bottom:16px;left:16px;max-width:min(420px,calc(100vw - 32px));background:#101725ee;border:1px solid var(--line);border-radius:12px;padding:14px;display:none;backdrop-filter:blur(12px)}
#detail strong{display:block;margin-bottom:6px}#detail small{color:var(--muted)}#empty{position:absolute;inset:45% 0 auto;text-align:center;color:var(--muted);display:none}
</style></head><body><header><h1>MNEMOS / MEMORY GRAPH</h1><p>Every node and edge comes from your local memory export.</p></header>
<div id="stats"></div><svg id="graph" role="img" aria-label="Interactive graph of memory records"></svg><div id="empty">No memories yet. Add memories and generate the graph again.</div><section id="detail"></section>
<script>
const data = __DATA__;
const svg = document.getElementById('graph'), detail = document.getElementById('detail');
const NS='http://www.w3.org/2000/svg';
document.getElementById('stats').textContent = data.nodes.length+' memories · '+data.links.length+' recorded links';
if(!data.nodes.length) document.getElementById('empty').style.display='block';
const width=()=>innerWidth, height=()=>innerHeight;
const nodes=data.nodes.map((d,i)=>({...d,x:width()/2+(Math.random()-.5)*width()*.7,y:height()/2+(Math.random()-.5)*height()*.7,vx:0,vy:0,r:Math.max(4,Math.min(10,4+Math.log2(1+(d.tags||[]).length)*2))}));
const byId=new Map(nodes.map(n=>[n.id,n]));
const edges=data.links.filter(e=>byId.has(e.source_id)&&byId.has(e.target_id)).map(e=>({...e,a:byId.get(e.source_id),b:byId.get(e.target_id)}));
const lineEls=edges.map(e=>{const el=document.createElementNS(NS,'line');svg.appendChild(el);el.setAttribute('aria-label',e.relation);return {e,el}});
const nodeEls=nodes.map(n=>{const g=document.createElementNS(NS,'g');const c=document.createElementNS(NS,'circle');c.setAttribute('r',n.r);c.setAttribute('class','node');c.setAttribute('fill',n.kind==='decision'?'#f59e0b':n.kind==='solution'?'#34d399':n.kind==='fact'?'#60a5fa':'#a78bfa');g.appendChild(c);const t=document.createElementNS(NS,'text');t.textContent=(n.content||'').slice(0,38);t.setAttribute('x',n.r+5);t.setAttribute('y',4);g.appendChild(t);g.addEventListener('click',()=>{detail.style.display='block';detail.replaceChildren();const title=document.createElement('strong');title.textContent=n.content;const meta=document.createElement('small');meta.textContent='Kind: '+n.kind+' · Tags: '+(n.tags||[]).join(', ')+' · ID: '+n.id+(n.source?' · Source: '+n.source:'');detail.append(title,meta);for(const e of edges.filter(e=>e.a===n||e.b===n)){const p=document.createElement('p');p.textContent=(e.a===n?'→ ':'← ')+e.relation+': '+(e.a===n?e.b.content:e.a.content);p.style.marginTop='8px';detail.appendChild(p)}});svg.appendChild(g);return {n,g}});
let dragging=null, last=null;
svg.addEventListener('pointerdown',e=>{const target=e.target.closest('g');if(target){dragging=nodeEls.find(x=>x.g===target)?.n;if(dragging){last={x:e.clientX,y:e.clientY};svg.setPointerCapture(e.pointerId)}}});
svg.addEventListener('pointermove',e=>{if(!dragging||!last)return;dragging.x+=e.clientX-last.x;dragging.y+=e.clientY-last.y;dragging.vx=dragging.vy=0;last={x:e.clientX,y:e.clientY};draw()});
svg.addEventListener('pointerup',()=>{dragging=null;last=null});
function draw(){for(const {e,el} of lineEls){el.setAttribute('x1',e.a.x);el.setAttribute('y1',e.a.y);el.setAttribute('x2',e.b.x);el.setAttribute('y2',e.b.y)}for(const {n,g} of nodeEls)g.setAttribute('transform','translate('+n.x+','+n.y+')')}
function tick(){const w=width(),h=height();for(let i=0;i<nodes.length;i++){const a=nodes[i];if(a===dragging)continue;a.vx+=(w/2-a.x)*.0005;a.vy+=(h/2-a.y)*.0005;for(let j=i+1;j<nodes.length;j++){const b=nodes[j],dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+30,f=100/d2;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}}
for(const e of edges){const dx=e.b.x-e.a.x,dy=e.b.y-e.a.y,d=Math.hypot(dx,dy)||1,f=(d-100)*.0008;e.a.vx+=dx/d*f;e.a.vy+=dy/d*f;e.b.vx-=dx/d*f;e.b.vy-=dy/d*f}
for(const n of nodes){if(n===dragging)continue;n.vx*=.88;n.vy*=.88;n.x=Math.max(20,Math.min(w-20,n.x+n.vx));n.y=Math.max(40,Math.min(h-20,n.y+n.vy))}draw();requestAnimationFrame(tick)}
addEventListener('resize',draw);draw();requestAnimationFrame(tick);
</script></body></html>"""
    target.write_text(document.replace("__DATA__", payload), encoding="utf-8")
    return target
