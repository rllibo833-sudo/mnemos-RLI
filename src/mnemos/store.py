"""SQLite-backed memory store with explicit, traceable relationships."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB = Path(os.environ.get("MNEMOS_DB", Path.home() / ".mnemos" / "memory.sqlite3"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_db(path: str | Path | None = None) -> Path:
    return Path(path).expanduser() if path is not None else DEFAULT_DB


class MemoryStore:
    """A small local memory database. No network access or third-party packages."""

    def __init__(self, path: str | Path | None = None):
        self.path = resolve_db(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
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
            """)

    def add(
        self,
        content: str,
        *,
        kind: str = "note",
        tags: Iterable[str] = (),
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content = content.strip()
        if not content:
            raise ValueError("Memory content must not be empty.")
        now = utc_now()
        item = {
            "id": str(uuid.uuid4()),
            "content": content,
            "kind": kind.strip() or "note",
            "tags": sorted({str(tag).strip() for tag in tags if str(tag).strip()}),
            "source": source,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as db:
            db.execute(
                """INSERT INTO memories
                (id, content, kind, tags_json, source, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (item["id"], item["content"], item["kind"], json.dumps(item["tags"]),
                 item["source"], json.dumps(item["metadata"]), now, now),
            )
        return item

    @staticmethod
    def _memory(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "content": row["content"], "kind": row["kind"],
            "tags": json.loads(row["tags_json"]), "source": row["source"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def get(self, memory_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._memory(row) if row else None

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 10000)),)
            ).fetchall()
        return [self._memory(row) for row in rows]

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Case-insensitive lexical search; no embeddings or remote model required."""
        terms = [term.casefold() for term in query.split() if term.strip()]
        if not terms:
            return []
        candidates = self.list(limit=10000)
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for item in candidates:
            haystack = " ".join([item["content"], item["kind"], *item["tags"], item["source"] or ""]).casefold()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append((score, item["created_at"], item))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [item for _, _, item in scored[:max(1, min(limit, 1000))]]

    def link(self, source_id: str, target_id: str, *, relation: str = "relates_to") -> dict[str, Any]:
        if source_id == target_id:
            raise ValueError("A memory cannot link to itself.")
        relation = relation.strip()
        if not relation:
            raise ValueError("Relationship type must not be empty.")
        now = utc_now()
        link_id = str(uuid.uuid4())
        with self._connect() as db:
            for memory_id in (source_id, target_id):
                if not db.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,)).fetchone():
                    raise KeyError(f"Memory not found: {memory_id}")
            db.execute(
                "INSERT OR IGNORE INTO links (id, source_id, target_id, relation, created_at) VALUES (?, ?, ?, ?, ?)",
                (link_id, source_id, target_id, relation, now),
            )
            row = db.execute(
                "SELECT * FROM links WHERE source_id = ? AND target_id = ? AND relation = ?",
                (source_id, target_id, relation),
            ).fetchone()
        return dict(row)

    def links(self, memory_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if memory_id:
                rows = db.execute(
                    "SELECT * FROM links WHERE source_id = ? OR target_id = ? ORDER BY created_at",
                    (memory_id, memory_id),
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM links ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def export_data(self) -> dict[str, Any]:
        return {"format": "mnemos-export-v1", "exported_at": utc_now(),
                "memories": self.list(limit=10000), "links": self.links()}

    def import_data(self, payload: dict[str, Any]) -> tuple[int, int]:
        if payload.get("format") != "mnemos-export-v1":
            raise ValueError("Unsupported export format; expected mnemos-export-v1.")
        memories = payload.get("memories", [])
        links = payload.get("links", [])
        if not isinstance(memories, list) or not isinstance(links, list):
            raise ValueError("Export memories and links must be arrays.")
        added_memories = added_links = 0
        with self._connect() as db:
            for item in memories:
                if not isinstance(item, dict) or not item.get("id") or not str(item.get("content", "")).strip():
                    continue
                exists = db.execute("SELECT 1 FROM memories WHERE id = ?", (item["id"],)).fetchone()
                if exists:
                    continue
                db.execute(
                    """INSERT INTO memories
                    (id, content, kind, tags_json, source, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(item["id"]), str(item["content"]), str(item.get("kind", "note")),
                     json.dumps(item.get("tags", [])), item.get("source"),
                     json.dumps(item.get("metadata", {})), item.get("created_at", utc_now()),
                     item.get("updated_at", item.get("created_at", utc_now()))),
                )
                added_memories += 1
            for item in links:
                if not isinstance(item, dict):
                    continue
                source_id, target_id = item.get("source_id"), item.get("target_id")
                if not source_id or not target_id or source_id == target_id:
                    continue
                if not all(db.execute("SELECT 1 FROM memories WHERE id = ?", (mid,)).fetchone()
                           for mid in (source_id, target_id)):
                    continue
                cursor = db.execute(
                    """INSERT OR IGNORE INTO links
                    (id, source_id, target_id, relation, created_at) VALUES (?, ?, ?, ?, ?)""",
                    (str(item.get("id") or uuid.uuid4()), source_id, target_id,
                     str(item.get("relation", "relates_to")), str(item.get("created_at", utc_now()))),
                )
                added_links += cursor.rowcount
        return added_memories, added_links
