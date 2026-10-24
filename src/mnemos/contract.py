"""Portable graph contract and conservative local/remote merge helpers."""
from __future__ import annotations
import hashlib, json
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
