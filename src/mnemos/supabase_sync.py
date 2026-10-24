"""Minimal, offline-only Supabase sync planner.

No HTTP client is used here. This module prepares a bounded payload and stages
content hashes in a local SQLite outbox; it never contacts Supabase.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

ALLOWED_RELATIONS = frozenset({"fixed_by", "resolved_by", "leads_to"})
MAX_LINKS = 299
MAX_CONTENT = 500


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _tags(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            value = []
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(tag for tag in value if isinstance(tag, str)))


def _rows(conn, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def _memory_payload(mem: dict[str, Any]) -> dict[str, Any] | None:
    mid = str(mem.get("id") or "")
    if len(mid) != 16:
        # Do not truncate IDs: truncation could merge distinct memories.
        return None
    content = str(mem.get("content") or "").strip()[:MAX_CONTENT]
    if not content:
        return None
    updated = mem.get("updated_at") or mem.get("created_at") or "1970-01-01T00:00:00+00:00"
    return {
        "id": mid,
        "content": content,
        "kind": str(mem.get("kind") or "note"),
        # Local tags_json is sent as the remote JSONB column "tags".
        "tags": _tags(mem.get("tags", mem.get("tags_json", []))),
        "updated_at": str(updated),
    }


def _link_payloads(conn, memory_ids: set[str]) -> list[dict[str, str]]:
    try:
        rows = _rows(conn, "links")
    except Exception:
        return []
    found: dict[str, dict[str, str]] = {}
    for row in rows:
        relation = str(row.get("relation") or "")
        if relation not in ALLOWED_RELATIONS:
            continue
        src = str(row.get("source_id") or row.get("src") or "")
        dst = str(row.get("target_id") or row.get("dst") or "")
        if not src or not dst or src == dst or src not in memory_ids or dst not in memory_ids:
            continue
        key = src + chr(0) + dst + chr(0) + relation
        link_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        found[key] = {
            "id": link_id, "source_id": src, "target_id": dst, "relation": relation,
        }
    return [found[key] for key in sorted(found)[:MAX_LINKS]]


def sync_minimal(store, dry_run: bool = True) -> dict[str, Any]:
    """Stage changed minimal rows and report size; never performs network I/O."""
    if not dry_run:
        raise ValueError("network sync is disabled; use --dry-run only")

    conn = store.conn
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_outbox (
            id TEXT NOT NULL,
            op TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            PRIMARY KEY (id, op)
        )
    """)

    all_local = store.list(limit=100000)
    memories = []
    for item in all_local:
        payload = _memory_payload(item)
        if payload is not None:
            memories.append(payload)
    memories.sort(key=lambda item: item["id"])
    memory_ids = {item["id"] for item in memories}
    links = _link_payloads(conn, memory_ids)

    candidates = [(item["id"], "upsert_memory", item) for item in memories]
    candidates.extend((item["id"], "upsert_link", item) for item in links)
    newly_queued_memories = 0
    changed_items = 0
    for item_id, op, payload in candidates:
        digest = _hash(payload)
        old = conn.execute(
            "SELECT payload_hash FROM sync_outbox WHERE id=? AND op=?",
            (item_id, op),
        ).fetchone()
        if old is None or old[0] != digest:
            conn.execute(
                """INSERT INTO sync_outbox (id, op, payload_hash) VALUES (?, ?, ?)
                   ON CONFLICT(id, op) DO UPDATE SET payload_hash=excluded.payload_hash""",
                (item_id, op, digest),
            )
            changed_items += 1
            if op == "upsert_memory" and old is None:
                newly_queued_memories += 1

    # Hash-only outbox entries stay pending until a future uploader confirms
    # remote success. Dry-run must never mark anything as uploaded.
    pending_memories = []
    for item in memories:
        row = conn.execute(
            "SELECT payload_hash FROM sync_outbox WHERE id=? AND op='upsert_memory'",
            (item["id"],),
        ).fetchone()
        if row and row[0] == _hash(item):
            pending_memories.append(item)
    pending_links = []
    for item in links:
        row = conn.execute(
            "SELECT payload_hash FROM sync_outbox WHERE id=? AND op='upsert_link'",
            (item["id"],),
        ).fetchone()
        if row and row[0] == _hash(item):
            pending_links.append(item)

    payload = {"memories": pending_memories, "links": pending_links}
    payload_bytes = len(_canonical(payload).encode("utf-8"))
    conn.commit()
    return {
        "local_memories": len(all_local),
        "eligible_memories": len(memories),
        "new_memories": newly_queued_memories,
        "changed_items": changed_items,
        "pending_memories": len(pending_memories),
        "links_filtered": len(links),
        "pending_links": len(pending_links),
        "payload_bytes": payload_bytes,
        "payload_kb": payload_bytes / 1024,
        "payload": payload,
    }
