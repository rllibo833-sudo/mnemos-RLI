import json, hashlib, uuid, os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def _now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

class MemoryStore:
    def __init__(self, db_path=None):
        p = Path(os.path.expanduser(str(db_path or os.environ.get("MNEMOS_DB") or "~/.mnemos/memory.sqlite3"))).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = p
        self.conn = sqlite3.connect(str(p), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
    def _init_db(self):
        self.conn.execute("""CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY, content TEXT, kind TEXT,
            tags_json TEXT, source TEXT, metadata_json TEXT,
            created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS links (
            id TEXT PRIMARY KEY, source_id TEXT, target_id TEXT,
            relation TEXT, created_at TEXT)""")
        try:
            mcols=[r[1] for r in self.conn.execute("PRAGMA table_info(memories)").fetchall()]
            if "tags" in mcols and "tags_json" not in mcols:
                self.conn.execute("ALTER TABLE memories ADD COLUMN tags_json TEXT")
            if "metadata" in mcols and "metadata_json" not in mcols:
                self.conn.execute("ALTER TABLE memories ADD COLUMN metadata_json TEXT")
        except: pass
        self.conn.commit()
    @contextmanager
    def _connect(self):
        try:
            yield self.conn
            self.conn.commit()
        finally:
            pass
    def _row_to_mem(self, row):
        if row is None: return None
        tr = row["tags_json"] if "tags_json" in row.keys() and row["tags_json"] is not None else "[]"
        mr = row["metadata_json"] if "metadata_json" in row.keys() and row["metadata_json"] is not None else "{}"
        try: tags = json.loads(tr) if isinstance(tr,str) else (tr or [])
        except: tags=[]
        try: meta = json.loads(mr) if isinstance(mr,str) else (mr or {})
        except: meta={}
        return {"id": row["id"],"content": row["content"],"kind": row["kind"] or "note","tags": tags,"source": row["source"] or "","metadata": meta,"created_at": row["created_at"],"updated_at": row["updated_at"] or row["created_at"],"deleted": row["deleted"] if "deleted" in row.keys() else 0}
    def add(self, content, kind="note", tags=None, source=None, metadata=None):
        if not isinstance(content,str) or not content.strip():
            raise ValueError("content must be non-empty")
        tags = tags or []; metadata = metadata or {}
        if not isinstance(tags,list) or any(not isinstance(t,str) for t in tags):
            raise ValueError("'tags' must be array of strings")
        if not isinstance(metadata,dict):
            raise ValueError("'metadata' must be object")
        nid = uuid.uuid4().hex[:16]; now=_now()
        self.conn.execute("INSERT INTO memories (id,content,kind,tags_json,source,metadata_json,created_at,updated_at,deleted) VALUES (?,?,?,?,?,?,?,?,?)",
            (nid, content.strip(), str(kind), json.dumps(tags), source, json.dumps(metadata), now, now, 0))
        self.conn.commit()
        return self.get(nid)
    def get(self, mem_id):
        cur=self.conn.execute("SELECT * FROM memories WHERE id=?",(str(mem_id),))
        row=cur.fetchone()
        if not row: raise KeyError(f"memory {mem_id} not found")
        return self._row_to_mem(row)
    def list(self, limit=10000, q=None):
        cur=self.conn.execute("SELECT * FROM memories WHERE deleted=0 OR deleted IS NULL ORDER BY created_at DESC LIMIT ?",(limit,))
        return [self._row_to_mem(r) for r in cur.fetchall()]
    def search(self, query, limit=20):
        if not isinstance(query,str): raise ValueError("query must be string")
        q=query.lower()
        all_mems=self.list(limit=10000)
        out=[]
        for m in all_mems:
            hay=(m.get("content","")+" "+" ".join(m.get("tags",[]))).lower()
            if q in hay:
                out.append(m)
            if len(out)>=limit: break
        return out
    def link(self, source_id, target_id, relation="relates_to"):
        s=str(source_id); t=str(target_id)
        if s==t: raise ValueError("cannot link to self")
        if not self.conn.execute("SELECT 1 FROM memories WHERE id=?",(s,)).fetchone():
            raise KeyError(f"source {s} not found")
        if not self.conn.execute("SELECT 1 FROM memories WHERE id=?",(t,)).fetchone():
            raise KeyError(f"target {t} not found")
        lid=hashlib.sha256((s+"\0"+t+"\0"+str(relation)).encode()).hexdigest()[:32]
        now=_now()
        self.conn.execute("INSERT OR IGNORE INTO links (id,source_id,target_id,relation,created_at) VALUES (?,?,?,?,?)",(lid,s,t,str(relation),now))
        self.conn.commit()
        cur=self.conn.execute("SELECT * FROM links WHERE id=?",(lid,))
        r=cur.fetchone()
        return {"id": r["id"],"source_id": r["source_id"],"target_id": r["target_id"],"relation": r["relation"],"created_at": r["created_at"]}
    def links(self, mem_id=None):
        if mem_id is None:
            cur=self.conn.execute("SELECT * FROM links ORDER BY created_at DESC LIMIT 10000")
        else:
            cur=self.conn.execute("SELECT * FROM links WHERE source_id=? OR target_id=? ORDER BY created_at DESC LIMIT 10000",(str(mem_id),str(mem_id)))
        return [dict(r) for r in cur.fetchall()]
    def export_data(self):
        return {"format":"mnemos-export-v1","memories":self.list(limit=10000),"links":self.links()}
    def import_data(self, payload):
        if not isinstance(payload,dict): raise ValueError("bundle must be object")
        if "format" in payload and payload["format"]!="mnemos-export-v1":
            raise ValueError(f"unsupported format {payload['format']}")
        if "memories" not in payload or "links" not in payload:
            if "nodes" not in payload: raise ValueError("bundle requires memories/links")
        mems=payload.get("memories") or payload.get("nodes") or []
        links=payload.get("links") or []
        added_m=0; added_l=0
        for m in mems:
            if not isinstance(m,dict): continue
            mid=str(m.get("id") or uuid.uuid4().hex[:16])
            if self.conn.execute("SELECT 1 FROM memories WHERE id=?",(mid,)).fetchone(): continue
            content=str(m.get("content","")).strip()
            if not content: continue
            tags=m.get("tags",[])
            if not isinstance(tags,list): tags=[]
            meta=m.get("metadata",{})
            if not isinstance(meta,dict): meta={}
            created=m.get("created_at") or _now()
            updated=m.get("updated_at") or created
            self.conn.execute("INSERT OR IGNORE INTO memories (id,content,kind,tags_json,source,metadata_json,created_at,updated_at,deleted) VALUES (?,?,?,?,?,?,?,?,?)",
                (mid, content, str(m.get("kind","note")), json.dumps(tags), m.get("source"), json.dumps(meta), created, updated, 0))
            added_m+=1
        for l in links:
            if not isinstance(l,dict): continue
            src=l.get("source_id") or l.get("src") or ""
            dst=l.get("target_id") or l.get("dst") or ""
            if not src or not dst or src==dst: continue
            if not self.conn.execute("SELECT 1 FROM memories WHERE id=?",(str(src),)).fetchone(): continue
            if not self.conn.execute("SELECT 1 FROM memories WHERE id=?",(str(dst),)).fetchone(): continue
            rel=str(l.get("relation") or "relates_to")
            lid=str(l.get("id") or hashlib.sha256((str(src)+"\0"+str(dst)+"\0"+rel).encode()).hexdigest()[:32])
            cur=self.conn.execute("INSERT OR IGNORE INTO links (id,source_id,target_id,relation,created_at) VALUES (?,?,?,?,?)",(lid,str(src),str(dst),rel,str(l.get("created_at") or _now())))
            added_l+=cur.rowcount
        self.conn.commit()
        return (added_m, added_l)
Store=MemoryStore
