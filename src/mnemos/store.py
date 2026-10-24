import json, hashlib
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def _now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

class MemoryStore:
    def __init__(self, db_path=None):
        import os
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
        # migrate old schema
        try:
            cols=[r[1] for r in self.conn.execute("PRAGMA table_info(memories)").fetchall()]
            if "tags" in cols and "tags_json" not in cols:
                self.conn.execute("ALTER TABLE memories ADD COLUMN tags_json TEXT")
            if "metadata" in cols and "metadata_json" not in cols:
                self.conn.execute("ALTER TABLE memories ADD COLUMN metadata_json TEXT")
            if "updated_at" not in cols:
                self.conn.execute("ALTER TABLE memories ADD COLUMN updated_at TEXT")
        except: pass
        # old links table with src/dst -> migrate
        try:
            lcols=[r[1] for r in self.conn.execute("PRAGMA table_info(links)").fetchall()]
            if "src" in lcols:
                self.conn.execute("DROP TABLE IF EXISTS links_old")
                self.conn.execute("ALTER TABLE links RENAME TO links_old")
                self.conn.execute("""CREATE TABLE links (id TEXT PRIMARY KEY, source_id TEXT, target_id TEXT, relation TEXT, created_at TEXT)""")
                for r in self.conn.execute("SELECT * FROM links_old").fetchall():
                    sid = r["src"] if "src" in r.keys() else ""
                    tid = r["dst"] if "dst" in r.keys() else ""
                    if sid and tid:
                        lid = hashlib.sha256((sid+"\0"+tid).encode()).hexdigest()[:32]
                        self.conn.execute("INSERT OR IGNORE INTO links(id,source_id,target_id,relation,created_at) VALUES(?,?,?,?,?)",(lid,sid,tid,"relates_to",_now()))
        except: pass
        self.conn.commit()

    @contextmanager
    def _connect(self):
        try:
            yield self.conn
            self.conn.commit()
        finally:
            pass

    def _col(self,row,*names,default=None):
        if row is None: return default
        keys=row.keys() if hasattr(row,'keys') else []
        for n in names:
            if n in keys and row[n] is not None: return row[n]
        return default

    def _memory(self,row):
        tr=self._col(row,"tags_json","tags",default="[]")
        mr=self._col(row,"metadata_json","metadata",default="{}")
        try: tags=json.loads(tr) if isinstance(tr,str) else (tr or [])
        except: tags=[]
        try: meta=json.loads(mr) if isinstance(mr,str) else (mr or {})
        except: meta={}
        return {"id":self._col(row,"id"),"content":self._col(row,"content",default=""),"kind":self._col(row,"kind",default="note"),"tags":tags,"source":self._col(row,"source",default=""),"metadata":meta,"created_at":self._col(row,"created_at"),"updated_at":self._col(row,"updated_at","created_at",default=self._col(row,"created_at")),"deleted":self._col(row,"deleted",default=0)}

    def list(self,limit=10000,q=None):
        cur=self.conn.execute("SELECT * FROM memories WHERE deleted=0 OR deleted IS NULL ORDER BY created_at DESC LIMIT ?",(limit,))
        return [self._memory(r) for r in cur.fetchall()]

    def links(self):
        cur=self.conn.execute("SELECT id,source_id,target_id,relation,created_at FROM links LIMIT 10000")
        return [dict(r) for r in cur.fetchall()]

    def export_data(self):
        return {"format":"mnemos-export-v1","memories":self.list(limit=10000),"links":self.links()}

    def import_data(self,payload):
        mems=payload.get("memories",[]); links=payload.get("links",[])
        self.conn.execute("DELETE FROM memories"); self.conn.execute("DELETE FROM links")
        for m in mems:
            self.conn.execute("INSERT OR REPLACE INTO memories (id,content,kind,tags_json,source,metadata_json,created_at,updated_at,deleted) VALUES (?,?,?,?,?,?,?,?,?)",
                (str(m.get("id")),str(m.get("content","")),str(m.get("kind","note")),json.dumps(m.get("tags",[]) if isinstance(m.get("tags",[]),list) else []),m.get("source"),json.dumps(m.get("metadata",{})),m.get("created_at") or _now(),m.get("updated_at") or m.get("created_at") or _now(), m.get("deleted",0)))
        for l in links:
            src=l.get("source_id") or l.get("src") or ""; dst=l.get("target_id") or l.get("dst") or ""
            if not src or not dst or src==dst: continue
            lid=str(l.get("id") or hashlib.sha256((src+"\0"+dst+"\0"+str(l.get("relation","relates_to"))).encode()).hexdigest()[:32])
            self.conn.execute("INSERT OR REPLACE INTO links(id,source_id,target_id,relation,created_at) VALUES(?,?,?,?,?)",(lid,str(src),str(dst),str(l.get("relation","relates_to")),str(l.get("created_at") or _now())))
        self.conn.commit()

Store = MemoryStore
