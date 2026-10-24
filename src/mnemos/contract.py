"""Portable graph contract and conservative local/remote merge helpers."""
from __future__ import annotations
import hashlib, json, os, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
OUTBOX_TABLE = """CREATE TABLE IF NOT EXISTS sync_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL, ack_at TEXT, attempts INTEGER NOT NULL DEFAULT 0)"""
def _now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def ensure_outbox(store):
    with store._connect() as db:
        db.execute(OUTBOX_TABLE); db.execute("CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending ON sync_outbox(ack_at, id)")
def snapshot_graph(store):
    snapshot=store.export_data()
    if not isinstance(snapshot.get("memories"),list) or not isinstance(snapshot.get("links"),list): raise ValueError("store.export_data() must return memories and links arrays")
    return snapshot
def _normalize_export(payload):
    if not isinstance(payload,dict): raise ValueError("bundle must be a JSON object")
    if isinstance(payload.get("memories"),list) and isinstance(payload.get("links"),list):
        result=dict(payload); result.setdefault("format","mnemos-export-v1")
        if result["format"]!="mnemos-export-v1": raise ValueError("unsupported export format")
        return result
    if isinstance(payload.get("nodes"),list) and isinstance(payload.get("links"),list):
        memories=[]
        for node in payload["nodes"]:
            if isinstance(node,dict): memories.append({k:node.get(k) for k in ("id","content","kind","tags","source","metadata","created_at","updated_at")})
        return {"format":"mnemos-export-v1","memories":memories,"links":payload["links"]}
    raise ValueError("bundle requires memories/links or nodes/links arrays")
def bundle_from_snapshot(snapshot,out_path):
    payload=_normalize_export(snapshot); target=Path(out_path).expanduser().resolve(); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return target
def roundtrip_snapshot(snapshot):
    """Exercise JSON bundle + SQLite import/unbundle in an isolated temporary database."""
    import tempfile
    from .store import MemoryStore
    payload = _normalize_export(snapshot)
    with tempfile.TemporaryDirectory(prefix="mnemos-bundle-sim-") as tmp:
        simulated_store = MemoryStore(Path(tmp) / "simulation.sqlite3")
        simulated_store.import_data(payload)
        bundle_path = Path(tmp) / "roundtrip.json"
        bundle_from_snapshot(snapshot_graph(simulated_store), bundle_path)
        unbundle_to_store(bundle_path, simulated_store, protect_updated_at=True)
        result = snapshot_graph(simulated_store)
    return result, payload
def _time(value): return str(value or "")
def unbundle_to_store(bundle_path,store,protect_updated_at=True):
    payload=_normalize_export(json.loads(Path(bundle_path).expanduser().read_text(encoding="utf-8"))); added=updated=preserved=added_links=0
    with store._connect() as db:
        for item in payload["memories"]:
            if not isinstance(item,dict) or not item.get("id") or not str(item.get("content","")).strip(): continue
            row=db.execute("SELECT * FROM memories WHERE id=?",(str(item["id"]),)).fetchone(); incoming=_time(item.get("updated_at") or item.get("created_at"))
            if row is not None:
                local=dict(row); local_time=_time(local.get("updated_at") or local.get("created_at"))
                if protect_updated_at and (not incoming or local_time>=incoming): preserved+=1; continue
                db.execute("UPDATE memories SET content=?,kind=?,tags_json=?,source=?,metadata_json=?,updated_at=? WHERE id=?",(str(item["content"]),str(item.get("kind","note")),json.dumps(item.get("tags",[]) if isinstance(item.get("tags",[]),list) else []),item.get("source"),json.dumps(item.get("metadata",{})),incoming or local_time or _now(),str(item["id"]))); updated+=1
            else:
                created=_time(item.get("created_at")) or incoming or _now()
                db.execute("INSERT INTO memories(id,content,kind,tags_json,source,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(str(item["id"]),str(item["content"]),str(item.get("kind","note")),json.dumps(item.get("tags",[]) if isinstance(item.get("tags",[]),list) else []),item.get("source"),json.dumps(item.get("metadata",{})),created,incoming or created)); added+=1
        for link in payload["links"]:
            if not isinstance(link,dict): continue
            source,target=link.get("source_id"),link.get("target_id")
            if not source or not target or source==target: continue
            if not all(db.execute("SELECT 1 FROM memories WHERE id=?",(x,)).fetchone() for x in (source,target)): continue
            link_id=str(link.get("id") or hashlib.sha256((str(source)+"\0"+str(target)+"\0"+str(link.get("relation","relates_to"))).encode()).hexdigest()[:32])
            cur=db.execute("INSERT OR IGNORE INTO links(id,source_id,target_id,relation,created_at) VALUES(?,?,?,?,?)",(link_id,str(source),str(target),str(link.get("relation","relates_to")),str(link.get("created_at") or _now()))); added_links+=max(0,cur.rowcount)
    return {"memories_added":added,"memories_updated":updated,"memories_preserved_local":preserved,"links_added":added_links,"local_deletes":0}
def _request(base,token,key,table,query="",method="GET",body=None,prefer=None):
    url=base.rstrip("/")+"/rest/v1/"+table+(("?"+query) if query else ""); headers={"apikey":key,"Authorization":"Bearer "+token,"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    if prefer: headers["Prefer"]=prefer
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=10) as response:
            raw=response.read(); return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc: raise RuntimeError("Supabase "+method+" "+table+" HTTP "+str(exc.code)+": "+exc.read().decode("utf-8","replace")[:250]) from exc
    except (urllib.error.URLError,TimeoutError) as exc: raise RuntimeError("Supabase network failure: "+str(exc)) from exc
def sync_snapshot(store,out_path,supabase_url=None):
    snapshot=snapshot_graph(store); target=bundle_from_snapshot(snapshot,out_path)
    report={"snapshot":str(target),"memories":len(snapshot["memories"]),"links":len(snapshot["links"]),"network_attempted":False,"outbox_ack":"deferred"}
    if not supabase_url: report["remote"]="skipped (no --supabase-url)"; return report
    base=supabase_url.strip().rstrip("/"); key=os.environ.get("SUPABASE_ANON_KEY","").strip(); token=os.environ.get("SUPABASE_ACCESS_TOKEN","").strip(); workspace=os.environ.get("WORKSPACE_ID","").strip()
    if not key or not token or not workspace: raise RuntimeError("SUPABASE_ANON_KEY, SUPABASE_ACCESS_TOKEN, and WORKSPACE_ID are required for remote sync")
    report["network_attempted"]=True; quoted=urllib.parse.quote(workspace,safe=""); remote_memories=[]; offset=0
    while True:
        page=_request(base,token,key,"memories","select=id,workspace_id,kind,content,tags,source,metadata,created_at,updated_at&workspace_id=eq."+quoted+"&order=updated_at.asc,id.asc&limit=500&offset="+str(offset)) or []; remote_memories.extend(page)
        if len(page)<500: break
        offset+=len(page)
    remote_by_id={str(x["id"]):x for x in remote_memories}; upserts=[]
    for item in snapshot["memories"]:
        remote=remote_by_id.get(str(item["id"]))
        if remote and _time(remote.get("updated_at"))>=_time(item.get("updated_at")): continue
        content=str(item.get("content","")); upserts.append({"id":str(item["id"]),"workspace_id":workspace,"kind":str(item.get("kind","note")),"content":content,"tags":item.get("tags",[]) if isinstance(item.get("tags",[]),list) else [],"source":item.get("source"),"metadata":item.get("metadata",{}),"content_sha256":hashlib.sha256(content.encode()).hexdigest(),"schema_version":1,"created_at":item.get("created_at") or _now(),"updated_at":item.get("updated_at") or item.get("created_at") or _now()})
    for i in range(0,len(upserts),100): _request(base,token,key,"memories","on_conflict=id","POST",upserts[i:i+100],"resolution=merge-duplicates,return=minimal")
    remote_links=[]; offset=0
    while True:
        page=_request(base,token,key,"links","select=id,workspace_id,source_id,target_id,relation,created_at,updated_at&workspace_id=eq."+quoted+"&order=updated_at.asc,id.asc&limit=500&offset="+str(offset)) or []; remote_links.extend(page)
        if len(page)<500: break
        offset+=len(page)
    known={(str(x.get("source_id")),str(x.get("target_id")),str(x.get("relation"))) for x in remote_links}; link_rows=[]
    for link in snapshot["links"]:
        key_tuple=(str(link.get("source_id")),str(link.get("target_id")),str(link.get("relation","relates_to")))
        if key_tuple in known: continue
        link_rows.append({"id":str(link.get("id") or hashlib.sha256("\0".join(key_tuple).encode()).hexdigest()[:32]),"workspace_id":workspace,"source_id":key_tuple[0],"target_id":key_tuple[1],"relation":key_tuple[2],"created_at":link.get("created_at") or _now(),"updated_at":link.get("updated_at") or link.get("created_at") or _now()})
    for i in range(0,len(link_rows),100): _request(base,token,key,"links","on_conflict=id","POST",link_rows[i:i+100],"resolution=merge-duplicates,return=minimal")
    pulled={"format":"mnemos-export-v1","memories":[],"links":[]}
    for table,fields in [("memories","id,workspace_id,kind,content,tags,source,metadata,created_at,updated_at"),("links","id,workspace_id,source_id,target_id,relation,created_at,updated_at")]:
        offset=0
        while True:
            page=_request(base,token,key,table,"select="+fields+"&workspace_id=eq."+quoted+"&order=updated_at.asc,id.asc&limit=500&offset="+str(offset)) or []
            for row in page:
                if table=="memories": pulled["memories"].append({k:row.get(k) for k in ("id","content","kind","tags","source","metadata","created_at","updated_at")})
                else: pulled["links"].append({k:row.get(k) for k in ("id","source_id","target_id","relation","created_at")})
            if len(page)<500: break
            offset+=len(page)
    pull_path=target.with_suffix(target.suffix+".pull.json"); pull_path.write_text(json.dumps(pulled,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    merged=unbundle_to_store(pull_path,store,protect_updated_at=True)
    report.update({"remote":"push-pull completed","remote_memories_read":len(pulled["memories"]),"remote_links_read":len(pulled["links"]),"local_merge":merged,"outbox_ack":"deferred; no ACK issued"})
    return report