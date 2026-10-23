# Living Knowledge Network: audited implementation plan

## Decision

Mnemos is an independent, agent-neutral Living Knowledge Network with **hybrid local + server storage from the outset**. PusingCuk can integrate later through CLI/MCP, but Mnemos must not depend on it.

## Repository audit

Audit target: `main` at the current repository head; re-audit after each implementation phase.

### Already present—preserve it

- `src/mnemos/store.py`: SQLite memory records, lexical search, explicit links, JSON export/import, diagnostics, export validation, persistent device identity, and a transactional local outbox for new memory/link upserts.
- `src/mnemos/graph.py`: dependency-free HTML graph rendered from real memory/link records.
- `src/mnemos/mcp_server.py`: local stdio MCP adapter with search/add/get/list/link/export.
- `supabase/functions/mnemos-mcp/index.ts`: separate authenticated cloud MCP implementation using PostgreSQL and owner-scoped operations.
- `tests/test_store.py` and `tests/test_mcp_server.py`: baseline local store/adapter tests.
- src/mnemos/device_mapper.py: opt-in offline binary inventory, bounded ELF/PE/Mach-O metadata parsing, hashing limits, and explicit scan completeness.
- src/mnemos/evolution.py: deterministic, idempotent dependency graph reconstruction and validation, preserving historical artifact evidence.
- Existing docs for data format, cloud connection, agent integration, and recovery.

### Binary evidence graph — current implementation

The mapper extracts ELF sections/symbols/dynamic dependencies, PE sections/imports/exports, and Mach-O load-command dependencies using bounded static parsing. Artifact versions and provenance are retained; reconciliation reconstructs missing depends_on edges from persisted parsed metadata and validates history. Incomplete scans are explicitly marked when budgets, depth caps, skipped symlink roots, or traversal errors prevent a complete inventory. Missing artifacts are not automatically deleted or marked absent, and missing dependencies in a replacement do not erase older evidence.

Full SHA-256 identifies versions when available. Oversized/unhashable files also receive a bounded first/middle/last sample fingerprint, used with path and size to distinguish many content changes even when mtime is preserved. This is not a full-content hash: changes confined to unsampled regions can remain undetected, so it cannot prove byte-for-byte identity. Each observation also records a nanosecond capture timestamp to order versions whose filesystem metadata and store timestamps tie.

## Confirmed gap

Local SQLite and cloud PostgreSQL are separate. Similar MCP tool names do not synchronize data. Current export/import is a portable snapshot, not continuous sync. The local transactional outbox and persistent device identity now exist for new memory/link upserts. Remote sync cursors, server idempotency ledger, conflict records, and tombstones are still not implemented.

The cloud docs report a successful single-account authenticated round trip but explicitly say cross-account isolation is unverified. That status must remain visible until tested.

## Implementation contract

### Phase A — local sync foundation

- Add a versioned SQLite schema migration without destroying existing user databases.
- Create a persistent random device ID.
- Record each create/update/link/delete in an outbox within the same database transaction.
- Give every operation a stable operation ID and monotonic local sequence.
- Keep unacknowledged operations across restarts; never advance a cursor before acknowledgement.
- Represent deletes as tombstones; never interpret missing data in a partial batch as deletion.
- Add diagnostics for outbox backlog, failed attempts, and migration version.

### Phase B — cloud sync contract

- Require a valid authenticated user and derive owner identity only from verified auth context.
- Store idempotency keys and server revisions; replaying a request must not duplicate data.
- Scope all rows and conflict queries by owner.
- Push changes in bounded batches and pull changes after an acknowledged server cursor.
- Preserve local usability on network failure; retries must be safe.
- Add a real two-account isolation test before claiming security verification.

### Phase C — conflict-safe graph

- Use base revision/content hash to detect concurrent edits; wall-clock timestamps alone are insufficient.
- Keep conflicting variants inspectable until a user or explicit policy resolves them.
- Sync link endpoints and edges with referential integrity; surface unresolved endpoints.
- Keep source/provenance fields distinct from agent-authored summaries and inferred relationships.
- Expose sync status and conflict inspection through CLI/MCP before adding a polished control center.

## Acceptance criteria

1. Existing SQLite databases migrate without losing memories or links.
2. Local add/search/link/export/graph and local MCP still work offline.
3. A mutation creates exactly one durable outbox operation, atomically.
4. Restart/retry does not duplicate server records or lose unacknowledged changes.
5. Two devices converge after push/pull when there are no concurrent edits.
6. Concurrent edits are surfaced, not silently lost.
7. Deletion propagates via tombstones only.
8. One account cannot read, modify, link, or infer another account's records.
9. Export validation and restore remain available without cloud access.
10. CI exercises migrations, replay, offline behavior, conflicts, tombstones, and ownership isolation.

## Non-goals for sync foundation

- Rewriting the current graph viewer.
- Requiring PusingCuk or a particular agent framework.
- Requiring an LLM, embedding service, or proprietary runtime.
- Treating semantic similarity or an agent's guess as a verified relationship.

This document records the audited boundary and contract; it does not claim that the sync implementation already exists. Binary graph reconciliation is implemented independently of cloud sync; it does not claim runtime dependency usage or infer deletion from incomplete scans.
