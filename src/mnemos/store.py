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
        return {"format": "mnemos-export-v1", "exported_at": utc_now(),
                "memories": self.list(limit=10000), "links": self.links()}

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
                added_links += cursor.rowcount
        return added_memories, added_links
