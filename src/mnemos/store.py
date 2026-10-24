"""SQLite-backed memory store with explicit, traceable relationships."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .contract import Change, GraphStore, Provenance

DEFAULT_DB = Path(os.environ.get("MNEMOS_DB", Path.home() / ".mnemos" / "memory.sqlite3"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_db(path: str | Path | None = None) -> Path:
    return Path(path).expanduser() if path is not None else DEFAULT_DB


class MemoryStore(GraphStore):
    """A small local memory database. No network access or third-party packages."""

    def __init__(self, path: str | Path | None = None):
        self.path = resolve_db(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL CHECK(length(trim(content)) > 0),
                    kind TEXT NOT NULL DEFAULT 'note',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    source TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS links (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    target_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL DEFAULT 'relates_to',
                    created_at TEXT NOT NULL,
                    UNIQUE(source_id, target_id, relation),
                    CHECK(source_id <> target_id)
                );
                CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
                CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id);
                CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_id);
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, visibility TEXT NOT NULL DEFAULT 'private'
                    CHECK(visibility IN ('private','shared','public')), created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id), user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('reader','writer','admin')),
                    PRIMARY KEY(workspace_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS sync_changes (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL CHECK(entity_type IN ('memory','link','node','relation')),
                    entity_id TEXT NOT NULL, op TEXT NOT NULL CHECK(op IN ('upsert','delete')),
                    payload_json TEXT NOT NULL, lamport_clock INTEGER NOT NULL, actor TEXT NOT NULL,
                    created_at TEXT NOT NULL, acknowledged_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sync_changes_pending
                    ON sync_changes(workspace_id,acknowledged_at,lamport_clock);
                CREATE TABLE IF NOT EXISTS mnemos_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_outbox (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL UNIQUE,
                    entity_type TEXT NOT NULL CHECK(entity_type IN ('memory', 'link')),
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL CHECK(operation IN ('upsert')),
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending
                    ON sync_outbox(acknowledged_at, seq);
                INSERT OR IGNORE INTO mnemos_meta(key, value)
                    VALUES ('schema_version', '2');
                INSERT OR IGNORE INTO mnemos_meta(key, value)
                    VALUES ('device_id', lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(4))));
            """)
            # Additive migration: existing memory and link rows are preserved.
            for table in ("memories", "links"):
                columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
                for name, declaration in {
                    "workspace_id": "TEXT NOT NULL DEFAULT 'default'",
                    "provenance_json": "TEXT NOT NULL DEFAULT '{}'",
                    "lamport": "INTEGER NOT NULL DEFAULT 0",
                    "deleted": "INTEGER NOT NULL DEFAULT 0",
                }.items():
                    if name not in columns:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
            db.execute("INSERT OR IGNORE INTO workspaces(id,visibility,created_at) VALUES('default','private',?)",(utc_now(),))
            db.execute("CREATE INDEX IF NOT EXISTS idx_memories_workspace ON memories(workspace_id,deleted)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_links_workspace ON links(workspace_id,deleted)")
            version_row = db.execute("SELECT value FROM mnemos_meta WHERE key='schema_version'").fetchone()
            version = int(version_row["value"]) if version_row else 1
            if version > 3:
                raise ValueError(f"Database schema version {version} is newer than this Mnemos build (3).")
            db.execute("UPDATE mnemos_meta SET value='3' WHERE key='schema_version'")

    def add(
        self, content: str, *, kind: str = "note", tags: Iterable[str] = (),
        source: str | None = None, metadata: dict[str, Any] | None = None,
        workspace_id: str = "default", provenance: dict[str, Any] | Provenance | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        content = content.strip()
        if not content:
            raise ValueError("Memory content must not be empty.")
        now = utc_now()
        provenance_value = (provenance.to_dict() if isinstance(provenance, Provenance) else provenance)
        provenance_value = provenance_value or {
            "actor": actor or self.device_id(), "source": source or "local",
            "created_at": now, "verification": "inferred",
        }
        item = {
            "id": str(uuid.uuid4()), "content": content, "kind": kind.strip() or "note",
            "tags": sorted({str(tag).strip() for tag in tags if str(tag).strip()}),
            "source": source, "metadata": metadata or {}, "workspace_id": workspace_id,
            "provenance": provenance_value, "created_at": now, "updated_at": now,
        }
        with self._connect() as db:
            db.execute("""INSERT INTO memories
                (id,content,kind,tags_json,source,metadata_json,created_at,updated_at,
                 workspace_id,provenance_json,lamport,deleted)
                VALUES(?,?,?,?,?,?,?,?,?,?,0,0)""",
                (item["id"],content,item["kind"],json.dumps(item["tags"]),source,
                 json.dumps(item["metadata"],ensure_ascii=False,sort_keys=True),now,now,
                 workspace_id,json.dumps(provenance_value,ensure_ascii=False,sort_keys=True)))
            self._enqueue(db,"memory",item["id"],item,workspace_id=workspace_id,actor=actor)
        return self.get(item["id"]) or item

    @staticmethod
    def _memory(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "content": row["content"], "kind": row["kind"],
            "tags": json.loads(row["tags_json"]), "source": row["source"],
            "metadata": json.loads(row["metadata_json"]),
            "workspace_id": row["workspace_id"] if "workspace_id" in row.keys() else "default",
            "provenance": json.loads(row["provenance_json"] or "{}") if "provenance_json" in row.keys() else {},
            "lamport": row["lamport"] if "lamport" in row.keys() else 0,
            "deleted": bool(row["deleted"]) if "deleted" in row.keys() else False,
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    @staticmethod
    def _relation(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        raw = item.pop("provenance_json", "{}")
        item["provenance"] = json.loads(raw or "{}") if isinstance(raw, str) else (raw or {})
        item["deleted"] = bool(item.get("deleted", 0))
        return item

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id = ? AND deleted=0", (memory_id,)).fetchone()
        return self._memory(row) if row else None

    def update_metadata(self, memory_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        """Replace a memory's metadata and enqueue the same local change atomically."""
        if not isinstance(metadata, dict):
            raise ValueError("Memory metadata must be an object.")
        metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        with self._connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row is None:
                raise KeyError(f"Memory not found: {memory_id}")
            item = self._memory(row)
            if item["deleted"]:
                raise KeyError(f"Memory not found: {memory_id}")
            if item["metadata"] == metadata:
                return item
            workspace_id = item["workspace_id"]
            updated_at = utc_now()
            db.execute(
                "UPDATE memories SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (metadata_json, updated_at, memory_id),
            )
            item["metadata"] = metadata
            item["updated_at"] = updated_at
            self._enqueue(db, "memory", memory_id, item, workspace_id=workspace_id)
        return self.get(memory_id) or item


    def add_once(
        self, content: str, *, kind: str, fingerprint: str,
        tags: Iterable[str] = (), source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically insert a fingerprinted record once and enqueue it with the record."""
        content = content.strip()
        if not content or not fingerprint.strip():
            raise ValueError("Content and fingerprint must not be empty.")
        metadata_value = dict(metadata or {})
        metadata_value["fingerprint"] = fingerprint
        tags_value = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM memories WHERE kind = ? AND deleted=0 ORDER BY created_at, id", (kind,)
            ).fetchall()
            for row in rows:
                existing = self._memory(row)
                if (existing.get("metadata") or {}).get("fingerprint") == fingerprint:
                    return existing, False
            now = utc_now()
            item = {
                "id": str(uuid.uuid4()), "content": content,
                "kind": kind.strip() or "note", "tags": tags_value,
                "source": source, "metadata": metadata_value,
                "created_at": now, "updated_at": now,
            }
            db.execute(
                """INSERT INTO memories
                (id, content, kind, tags_json, source, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (item["id"], item["content"], item["kind"], json.dumps(item["tags"]),
                 item["source"], json.dumps(item["metadata"], ensure_ascii=False, sort_keys=True), now, now),
            )
            self._enqueue(db, "memory", item["id"], item)
        return item, True

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM memories WHERE deleted=0 ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 10000)),)
            ).fetchall()
        return [self._memory(row) for row in rows]

    def list_all(self, *, kind: str | None = None) -> list[dict[str, Any]]:
        """Return every memory for graph reconciliation; unlike list(), never truncates at 10k."""
        with self._connect() as db:
            if kind is None:
                rows = db.execute("SELECT * FROM memories WHERE deleted=0 ORDER BY created_at, id").fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM memories WHERE kind = ? AND deleted=0 ORDER BY created_at, id", (kind,)
                ).fetchall()
        return [self._memory(row) for row in rows]

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Case-insensitive lexical search; no embeddings or remote model required."""
        terms = [term.casefold() for term in query.split() if term.strip()]
        if not terms:
            return []
        # Search the complete local graph; the recent-list limit must not hide older knowledge.
        candidates = self.list_all()
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for item in candidates:
            haystack = " ".join([item["content"], item["kind"], *item["tags"], item["source"] or ""]).casefold()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append((score, item["created_at"], item))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [item for _, _, item in scored[:max(1, min(limit, 1000))]]

    def link(self, source_id: str, target_id: str, *, relation: str = "relates_to",
             workspace_id: str = "default", provenance: dict[str, Any] | None = None,
             actor: str | None = None) -> dict[str, Any]:
        if source_id == target_id:
            raise ValueError("A memory cannot link to itself.")
        relation = relation.strip()
        if not relation:
            raise ValueError("Relationship type must not be empty.")
        now = utc_now()
        link_id = str(uuid.uuid4())
        with self._connect() as db:
            for memory_id in (source_id,target_id):
                if not db.execute("SELECT 1 FROM memories WHERE id=? AND workspace_id=? AND deleted=0",
                                  (memory_id,workspace_id)).fetchone():
                    raise KeyError(f"Memory not found in workspace {workspace_id}: {memory_id}")
            db.execute("""INSERT OR IGNORE INTO links
                (id,source_id,target_id,relation,created_at,workspace_id,provenance_json,lamport,deleted)
                VALUES(?,?,?,?,?,?,?,0,0)""",
                (link_id,source_id,target_id,relation,now,workspace_id,
                 json.dumps(provenance or {"actor":actor or self.device_id(),"source":"local",
                 "created_at":now,"verification":"inferred"},sort_keys=True)))
            row=db.execute("""SELECT * FROM links WHERE source_id=? AND target_id=? AND relation=?
                AND workspace_id=? AND deleted=0""",(source_id,target_id,relation,workspace_id)).fetchone()
            if row and row["id"] == link_id:
                self._enqueue(db,"link",row["id"],dict(row),workspace_id=workspace_id,actor=actor)
        return dict(row)

    @staticmethod
    def _next_lamport(db: sqlite3.Connection, workspace_id: str) -> int:
        clocks = []
        for table, column in (("memories", "lamport"), ("links", "lamport")):
            row = db.execute(
                f"SELECT COALESCE(MAX({column}), 0) FROM {table} WHERE workspace_id=?",
                (workspace_id,),
            ).fetchone()
            clocks.append(int(row[0]))
        row = db.execute(
            "SELECT COALESCE(MAX(lamport_clock), 0) FROM sync_changes WHERE workspace_id=?",
            (workspace_id,),
        ).fetchone()
        clocks.append(int(row[0]))
        return max(clocks, default=0) + 1

    def _enqueue(self, db: sqlite3.Connection, entity_type: str, entity_id: str,
                 payload: dict[str, Any], *, workspace_id: str = "default",
                 op: str = "upsert", actor: str | None = None) -> dict[str, Any]:
        actor = actor or self.device_id()
        clock = self._next_lamport(db, workspace_id)
        table = "memories" if entity_type in ("memory","node") else "links"
        db.execute(f"UPDATE {table} SET workspace_id=?,lamport=?,deleted=? WHERE id=?",
                   (workspace_id,clock,int(op=="delete"),entity_id))
        row = db.execute(f"SELECT * FROM {table} WHERE id=?",(entity_id,)).fetchone()
        if row is not None:
            payload = self._memory(row) if entity_type in ("memory","node") else self._relation(row)
        change = {"id":str(uuid.uuid4()),"workspace_id":workspace_id,"entity_type":entity_type,
                  "entity_id":entity_id,"op":op,"payload":payload,"lamport_clock":clock,
                  "actor":actor,"timestamp":utc_now()}
        db.execute("""INSERT INTO sync_changes
            (id,workspace_id,entity_type,entity_id,op,payload_json,lamport_clock,actor,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (change["id"],workspace_id,entity_type,entity_id,op,
             json.dumps(payload,ensure_ascii=False,sort_keys=True),clock,actor,change["timestamp"]))
        return change

    def delete(self, entity_id: str, *, entity_type: str = "memory",
               workspace_id: str = "default", actor: str | None = None) -> dict[str, Any]:
        if entity_type not in ("memory","link"):
            raise ValueError("entity_type must be memory or link")
        table="memories" if entity_type=="memory" else "links"
        with self._connect() as db:
            row=db.execute(f"SELECT * FROM {table} WHERE id=? AND workspace_id=?",(entity_id,workspace_id)).fetchone()
            if row is None: raise KeyError(f"{entity_type} not found: {entity_id}")
            if row["deleted"]: return {"id":entity_id,"deleted":True,"workspace_id":workspace_id}
            payload=self._memory(row) if entity_type=="memory" else self._relation(row)
            self._enqueue(db,entity_type,entity_id,payload,workspace_id=workspace_id,op="delete",actor=actor)
        return {"id":entity_id,"deleted":True,"workspace_id":workspace_id}

    @staticmethod
    def _as_change(change: Change | dict[str, Any]) -> dict[str, Any]:
        if isinstance(change,Change):
            return {"id":change.id,"workspace_id":change.workspace_id,"entity_type":change.entity_type,
                    "entity_id":change.entity_id,"op":change.op,"payload":change.payload,
                    "lamport_clock":change.lamport_clock,"actor":change.actor,"timestamp":change.timestamp}
        if not isinstance(change,dict): raise ValueError("Change must be a Change or dictionary")
        required=("id","workspace_id","entity_type","entity_id","op","payload","lamport_clock","actor","timestamp")
        if any(k not in change for k in required): raise ValueError("Change is missing contract fields")
        if change["op"] not in ("upsert","delete") or change["entity_type"] not in ("memory","link","node","relation"):
            raise ValueError("Invalid change operation or entity type")
        if not isinstance(change["lamport_clock"],int) or isinstance(change["lamport_clock"],bool) or change["lamport_clock"]<0:
            raise ValueError("lamport_clock must be a non-negative integer")
        return dict(change)

    def push(self, since_lamport: int = 0, workspace_id: str = "default") -> list[Change]:
        """Return pending local changes and acknowledge them as a local sync cycle."""
        del since_lamport
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT * FROM sync_changes
                   WHERE workspace_id=? AND acknowledged_at IS NULL
                   ORDER BY lamport_clock,id""",
                (workspace_id,),
            ).fetchall()
            if rows:
                db.executemany(
                    "UPDATE sync_changes SET acknowledged_at=? WHERE id=? AND acknowledged_at IS NULL",
                    [(utc_now(), row["id"]) for row in rows],
                )
        return [
            Change(
                id=row["id"], workspace_id=row["workspace_id"], entity_type=row["entity_type"],
                entity_id=row["entity_id"], op=row["op"], payload=json.loads(row["payload_json"]),
                lamport_clock=row["lamport_clock"], actor=row["actor"], timestamp=row["created_at"],
            )
            for row in rows
        ]

    def apply_change(self, change: Change | dict[str, Any]) -> dict[str, Any]:
        c=self._as_change(change); ws=str(c["workspace_id"]); et=str(c["entity_type"])
        et={"node":"memory","relation":"link"}.get(et,et)
        eid=str(c["entity_id"]); payload=c["payload"]; clock=c["lamport_clock"]
        if et not in ("memory","link") or not eid or not ws or not isinstance(payload,dict):
            raise ValueError("Invalid graph change")
        table="memories" if et=="memory" else "links"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            timestamp = c["timestamp"]
            if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
                timestamp = datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat()
            else:
                timestamp = str(timestamp or utc_now())
            db.execute(
                """INSERT OR IGNORE INTO sync_changes
                   (id,workspace_id,entity_type,entity_id,op,payload_json,lamport_clock,actor,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    str(c["id"]), ws, str(c["entity_type"]), eid, str(c["op"]),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True), clock,
                    str(c["actor"]), timestamp,
                ),
            )
            local=db.execute(f"SELECT * FROM {table} WHERE id=? AND workspace_id=?",(eid,ws)).fetchone()
            if local and clock < int(local["lamport"]): return {"status":"skipped"}
            if local and clock == int(local["lamport"]):
                current = self._memory(local) if et == "memory" else self._relation(local)
                if c["op"] == "delete" and local["deleted"]:
                    return {"status": "skipped"}
                if json.dumps(current, sort_keys=True, default=str) == json.dumps(payload, sort_keys=True, default=str):
                    return {"status": "skipped"}
                provenance = json.loads(local["provenance_json"] or "{}")
                provenance.update({
                    "actor": c["actor"], "source": "sync-conflict",
                    "created_at": str(c["timestamp"]), "verification": "contradicted",
                })
                db.execute(
                    "UPDATE " + table + " SET provenance_json=? WHERE id=?",
                    (json.dumps(provenance, sort_keys=True), eid),
                )
                if et == "memory":
                    for candidate in db.execute(
                        "SELECT id,metadata_json FROM memories WHERE workspace_id=? AND deleted=0",
                        (ws,),
                    ).fetchall():
                        try:
                            metadata = json.loads(candidate["metadata_json"] or "{}")
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if metadata.get("_mnemos_conflict_change_id") == c["id"]:
                            return {"status": "contradicted"}
                    incoming = dict(payload)
                    metadata = dict(incoming.get("metadata") or {})
                    metadata["_mnemos_conflict_change_id"] = c["id"]
                    incoming_provenance = dict(incoming.get("provenance") or {})
                    incoming_provenance.update({
                        "actor": c["actor"], "source": "sync-conflict",
                        "created_at": str(c["timestamp"]), "verification": "contradicted",
                    })
                    incoming_id = str(uuid.uuid4())
                    created_at = str(incoming.get("created_at") or utc_now())
                    updated_at = str(incoming.get("updated_at") or created_at)
                    db.execute(
                        """INSERT INTO memories
                           (id,content,kind,tags_json,source,metadata_json,created_at,updated_at,
                            workspace_id,provenance_json,lamport,deleted)
                           VALUES(?,?,?,?,?,?,?,?,?,?,0,0)""",
                        (
                            incoming_id, str(incoming.get("content") or "[conflicting version]"),
                            str(incoming.get("kind") or "note"), json.dumps(incoming.get("tags") or []),
                            incoming.get("source"), json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                            created_at, updated_at, ws,
                            json.dumps(incoming_provenance, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                    existing_row = db.execute("SELECT * FROM memories WHERE id=?", (eid,)).fetchone()
                    incoming_row = db.execute("SELECT * FROM memories WHERE id=?", (incoming_id,)).fetchone()
                    self._enqueue(db, "memory", eid, self._memory(existing_row), workspace_id=ws, actor=c["actor"])
                    self._enqueue(db, "memory", incoming_id, self._memory(incoming_row), workspace_id=ws, actor=c["actor"])
                    conflict_id = str(uuid.uuid4())
                    now = utc_now()
                    db.execute(
                        """INSERT INTO links
                           (id,source_id,target_id,relation,created_at,workspace_id,provenance_json,lamport,deleted)
                           VALUES(?,?,?,'conflicts_with',?,?,?,0,0)""",
                        (
                            conflict_id, eid, incoming_id, now, ws,
                            json.dumps({"actor": c["actor"], "source": "sync-conflict",
                                        "created_at": now, "verification": "contradicted"}, sort_keys=True),
                        ),
                    )
                    conflict_row = db.execute("SELECT * FROM links WHERE id=?", (conflict_id,)).fetchone()
                    self._enqueue(db, "link", conflict_id, self._relation(conflict_row),
                                  workspace_id=ws, actor=c["actor"])
                return {"status": "contradicted"}
            if c["op"]=="delete":
                if local:
                    db.execute(f"UPDATE {table} SET deleted=1,lamport=? WHERE id=?",(clock,eid))
                elif et=="memory":
                    now=str(payload.get("created_at") or utc_now())
                    db.execute("""INSERT INTO memories(id,content,kind,tags_json,source,metadata_json,created_at,
                        updated_at,workspace_id,provenance_json,lamport,deleted) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)""",
                        (eid,str(payload.get("content") or "[deleted]"),str(payload.get("kind") or "note"),
                         json.dumps(payload.get("tags",[])),payload.get("source"),json.dumps(payload.get("metadata",{})),
                         now,str(payload.get("updated_at") or now),ws,json.dumps(payload.get("provenance",{})),clock))
                else: return {"status":"skipped"}
                return {"status":"applied"}
            if et=="memory":
                now=str(payload.get("updated_at") or payload.get("created_at") or utc_now())
                vals=(str(payload.get("content") or ""),str(payload.get("kind") or "note"),
                    json.dumps(payload.get("tags",[])),payload.get("source"),json.dumps(payload.get("metadata",{})),
                    str(payload.get("created_at") or now),now,ws,json.dumps(payload.get("provenance",{}),sort_keys=True),clock,eid)
                if local:
                    db.execute("""UPDATE memories SET content=?,kind=?,tags_json=?,source=?,metadata_json=?,created_at=?,
                        updated_at=?,workspace_id=?,provenance_json=?,lamport=?,deleted=0 WHERE id=?""",vals)
                else:
                    db.execute("""INSERT INTO memories(content,kind,tags_json,source,metadata_json,created_at,updated_at,
                        workspace_id,provenance_json,lamport,deleted,id) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",vals)
            else:
                src,dst=payload.get("source_id"),payload.get("target_id")
                if not src or not dst or src==dst: raise ValueError("Link requires distinct endpoints")
                for mid in (src,dst):
                    if not db.execute("SELECT 1 FROM memories WHERE id=? AND workspace_id=? AND deleted=0",(mid,ws)).fetchone():
                        raise ValueError("Link endpoints must exist in workspace")
                vals=(src,dst,str(payload.get("relation") or "relates_to"),str(payload.get("created_at") or utc_now()),
                      ws,json.dumps(payload.get("provenance",{}),sort_keys=True),clock,eid)
                if local:
                    db.execute("""UPDATE links SET source_id=?,target_id=?,relation=?,created_at=?,workspace_id=?,
                        provenance_json=?,lamport=?,deleted=0 WHERE id=?""",vals)
                else:
                    db.execute("""INSERT INTO links(source_id,target_id,relation,created_at,workspace_id,provenance_json,
                        lamport,deleted,id) VALUES(?,?,?,?,?,?,?,0,?)""",vals)
        return {"status":"applied"}

    def pull(self, changes: Sequence[Change | dict[str, Any]] | None = None) -> dict[str, int]:
        """Replay the local journal (or an explicitly supplied batch) idempotently."""
        if changes is None:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT * FROM sync_changes ORDER BY lamport_clock,id"
                ).fetchall()
            changes = [
                {
                    "id": row["id"], "workspace_id": row["workspace_id"],
                    "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                    "op": row["op"], "payload": json.loads(row["payload_json"]),
                    "lamport_clock": row["lamport_clock"], "actor": row["actor"],
                    "timestamp": row["created_at"],
                }
                for row in rows
            ]
        result = {"applied": 0, "skipped": 0, "contradicted": 0}
        for change in changes:
            status = self.apply_change(change)["status"]
            result[status] += 1
        return result

    def traverse_neighbors(self, node_id: str, depth: int = 1,
                           workspace_id: str = "default") -> dict[str,Any]:
        depth=max(0,min(int(depth),32)); seen={node_id}; queue=[(node_id,0)]
        nodes={}; edges={}
        with self._connect() as db:
            while queue:
                cur,level=queue.pop(0)
                if level>=depth: continue
                rows=db.execute("""SELECT * FROM links WHERE workspace_id=? AND deleted=0 AND
                    (source_id=? OR target_id=?) ORDER BY created_at,id""",(workspace_id,cur,cur)).fetchall()
                for edge in rows:
                    edges[edge["id"]]=self._relation(edge)
                    nxt=edge["target_id"] if edge["source_id"]==cur else edge["source_id"]
                    if nxt not in seen:
                        seen.add(nxt); queue.append((nxt,level+1))
                        row=db.execute("SELECT * FROM memories WHERE id=? AND workspace_id=? AND deleted=0",(nxt,workspace_id)).fetchone()
                        if row: nodes[nxt]=self._memory(row)
            origin=db.execute("SELECT * FROM memories WHERE id=? AND workspace_id=? AND deleted=0",(node_id,workspace_id)).fetchone()
            if origin: nodes[node_id]=self._memory(origin)
        return {"nodes":list(nodes.values()),"edges":list(edges.values()),"depth":depth}

    def traverse_path(self, src: str, dst: str, max_depth: int = 4,
                      workspace_id: str = "default") -> list[dict[str,Any]] | None:
        max_depth=max(0,min(int(max_depth),4))
        if src==dst: return []
        queue=[(src,[])]; seen={src}
        with self._connect() as db:
            while queue:
                cur,path=queue.pop(0)
                if len(path)>=max_depth: continue
                rows=db.execute("""SELECT * FROM links WHERE workspace_id=? AND deleted=0 AND
                    (source_id=? OR target_id=?) ORDER BY created_at,id""",(workspace_id,cur,cur)).fetchall()
                for edge in rows:
                    nxt=edge["target_id"] if edge["source_id"]==cur else edge["source_id"]
                    if nxt in seen: continue
                    next_path=path+[self._relation(edge)]
                    if nxt==dst: return next_path
                    seen.add(nxt); queue.append((nxt,next_path))
        return None

    def device_id(self) -> str:
        with self._connect() as db:
            row = db.execute("SELECT value FROM mnemos_meta WHERE key = 'device_id'").fetchone()
        return str(row["value"])

    def sync_status(self) -> dict[str, Any]:
        with self._connect() as db:
            pending=db.execute("SELECT COUNT(*) FROM sync_changes WHERE acknowledged_at IS NULL").fetchone()[0]
            total=db.execute("SELECT COUNT(*) FROM sync_changes").fetchone()[0]
            last=db.execute("SELECT created_at FROM sync_changes ORDER BY rowid DESC LIMIT 1").fetchone()
            version=db.execute("SELECT value FROM mnemos_meta WHERE key='schema_version'").fetchone()
        return {"device_id":self.device_id(),"schema_version":int(version["value"]) if version else 3,
                "outbox_pending":pending,"outbox_total":total,
                "last_change_at":last["created_at"] if last else None,
                "remote_sync_implemented":False,"online_required":False}

    def pending_changes(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows=db.execute("""SELECT rowid AS seq,id AS operation_id,entity_type,entity_id,
                op AS operation,payload_json,created_at,lamport_clock,actor
                FROM sync_changes WHERE acknowledged_at IS NULL ORDER BY lamport_clock LIMIT ?""",
                (max(1,min(limit,1000)),)).fetchall()
        return [{**{k:row[k] for k in ("seq","operation_id","entity_type","entity_id","operation","created_at","lamport_clock","actor")},
                 "payload":json.loads(row["payload_json"])} for row in rows]

    def links(self, memory_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if memory_id:
                rows = db.execute(
                    """SELECT l.* FROM links l
                       JOIN memories s ON s.id=l.source_id AND s.deleted=0
                       JOIN memories t ON t.id=l.target_id AND t.deleted=0
                       WHERE l.deleted=0 AND (l.source_id=? OR l.target_id=?)
                       ORDER BY l.created_at,l.id""",
                    (memory_id, memory_id),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT l.* FROM links l
                       JOIN memories s ON s.id=l.source_id AND s.deleted=0
                       JOIN memories t ON t.id=l.target_id AND t.deleted=0
                       WHERE l.deleted=0 ORDER BY l.created_at,l.id"""
                ).fetchall()
        return [self._relation(row) for row in rows]

    def diagnostics(self) -> dict[str, Any]:
        """Inspect local SQLite integrity without modifying data or using the network."""
        with self._connect() as db:
            integrity_rows = db.execute("PRAGMA integrity_check").fetchall()
            foreign_key_rows = db.execute("PRAGMA foreign_key_check").fetchall()
            memories = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            links = db.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        integrity = [row[0] for row in integrity_rows]
        violations = [
            {"table": row[0], "rowid": row[1], "parent": row[2], "fkid": row[3]}
            for row in foreign_key_rows
        ]
        return {
            "database": str(self.path),
            "network_required": False,
            "integrity_check": integrity,
            "foreign_key_violations": violations,
            "memories": memories,
            "links": links,
            "ok": integrity == ["ok"] and not violations,
        }

    def export_data(self) -> dict[str, Any]:
        """Export every memory and link; portable snapshots must never be silently truncated."""
        with self._connect() as db:
            rows = db.execute("SELECT * FROM memories ORDER BY created_at DESC, id").fetchall()
        memories = [self._memory(row) for row in rows]
        return {
            "format": "mnemos-export-v1",
            "exported_at": utc_now(),
            "memories": memories,
            "links": self.links(),
        }

    @staticmethod
    def validate_export(payload: Any) -> dict[str, Any]:
        """Validate an export before importing it; never changes the database."""
        errors: list[str] = []
        if not isinstance(payload, dict):
            return {"ok": False, "errors": ["Top-level JSON value must be an object."]}
        if payload.get("format") != "mnemos-export-v1":
            errors.append("Unsupported export format; expected mnemos-export-v1.")
        memories = payload.get("memories")
        links = payload.get("links")
        if not isinstance(memories, list):
            errors.append("memories must be an array.")
            memories = []
        if not isinstance(links, list):
            errors.append("links must be an array.")
            links = []
        ids: set[str] = set()
        for index, item in enumerate(memories):
            if not isinstance(item, dict):
                errors.append(f"memories[{index}] must be an object.")
                continue
            memory_id = item.get("id")
            if not isinstance(memory_id, str) or not memory_id.strip():
                errors.append(f"memories[{index}].id must be a non-empty string.")
            elif memory_id in ids:
                errors.append(f"Duplicate memory ID: {memory_id}.")
            else:
                ids.add(memory_id)
            if not isinstance(item.get("content"), str) or not item["content"].strip():
                errors.append(f"memories[{index}].content must be non-empty text.")
            if "tags" in item and (not isinstance(item["tags"], list) or not all(isinstance(tag, str) for tag in item["tags"])):
                errors.append(f"memories[{index}].tags must be an array of strings.")
            if "metadata" in item and not isinstance(item["metadata"], dict):
                errors.append(f"memories[{index}].metadata must be an object.")
        seen_links: set[tuple[str, str, str]] = set()
        for index, item in enumerate(links):
            if not isinstance(item, dict):
                errors.append(f"links[{index}] must be an object.")
                continue
            source_id, target_id = item.get("source_id"), item.get("target_id")
            relation = item.get("relation", "relates_to")
            if not isinstance(source_id, str) or source_id not in ids:
                errors.append(f"links[{index}].source_id does not reference an exported memory.")
            if not isinstance(target_id, str) or target_id not in ids:
                errors.append(f"links[{index}].target_id does not reference an exported memory.")
            if source_id and source_id == target_id:
                errors.append(f"links[{index}] cannot link a memory to itself.")
            if not isinstance(relation, str) or not relation.strip():
                errors.append(f"links[{index}].relation must be non-empty text.")
            key = (str(source_id), str(target_id), str(relation))
            if key in seen_links:
                errors.append(f"Duplicate link at links[{index}].")
            seen_links.add(key)
        return {
            "ok": not errors,
            "memories": len(memories),
            "links": len(links),
            "errors": errors,
        }

    def import_data(self, payload: dict[str, Any]) -> tuple[int, int]:
        """Import a complete, validated export atomically; reject malformed input."""
        report = self.validate_export(payload)
        if not report["ok"]:
            details = "; ".join(report["errors"])
            raise ValueError(f"Invalid Mnemos export: {details}")

        memories = payload["memories"]
        links = payload["links"]
        added_memories = added_links = 0
        # The connection context rolls back the whole import if any insert fails.
        with self._connect() as db:
            for item in memories:
                exists = db.execute(
                    "SELECT 1 FROM memories WHERE id = ?", (item["id"],)
                ).fetchone()
                if exists:
                    continue
                created_at = item.get("created_at") or utc_now()
                db.execute(
                    """INSERT INTO memories
                    (id, content, kind, tags_json, source, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item["id"], item["content"], item.get("kind", "note"),
                     json.dumps(item.get("tags", [])), item.get("source"),
                     json.dumps(item.get("metadata", {})), created_at,
                     item.get("updated_at") or created_at),
                )
                self._enqueue(db, "memory", item["id"], {
                    "id": item["id"],
                    "content": item["content"],
                    "kind": item.get("kind", "note"),
                    "tags": item.get("tags", []),
                    "source": item.get("source"),
                    "metadata": item.get("metadata", {}),
                    "created_at": created_at,
                    "updated_at": item.get("updated_at") or created_at,
                })
                added_memories += 1
            for item in links:
                source_id, target_id = item["source_id"], item["target_id"]
                cursor = db.execute(
                    """INSERT OR IGNORE INTO links
                    (id, source_id, target_id, relation, created_at)
                    VALUES (?, ?, ?, ?, ?)""",
                    (str(item.get("id") or uuid.uuid4()), source_id, target_id,
                     item.get("relation", "relates_to"), item.get("created_at") or utc_now()),
                )
                if cursor.rowcount:
                    row = db.execute(
                        "SELECT * FROM links WHERE source_id = ? AND target_id = ? AND relation = ?",
                        (source_id, target_id, item.get("relation", "relates_to")),
                    ).fetchone()
                    if row:
                        self._enqueue(db, "link", row["id"], dict(row))
                    added_links += 1
        return added_memories, added_links
