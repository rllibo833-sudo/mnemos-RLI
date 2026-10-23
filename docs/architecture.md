# Architecture

## Product direction

Mnemos is a **Living Knowledge Network**: a durable, inspectable memory graph that can be used by different agents and devices. Its target storage strategy is **hybrid local + server from the outset**. Local use must continue when offline; server storage is for cross-device and cross-agent continuity. PusingCuk is an optional client, not a foundation dependency.

## Existing components (reviewed at current main)

- **Local store:** Python standard-library SQLite at `~/.mnemos/memory.sqlite3`, overridable via `--db` or `MNEMOS_DB`.
- **Memory records:** stable ID, content, kind, tags, optional source and metadata, timestamps.
- **Relationships:** explicit directed edges with a relation label.
- **Search:** explainable lexical matching across content, kind, tags, and source.
- **Import/export:** versioned JSON envelope; additive import validates data and skips existing IDs/duplicate links.
- **Graph viewer:** standalone HTML built from actual store records and links.
- **Local MCP:** stdio adapter exposing search/add/get/list/link/export.
- **Cloud MCP:** Supabase Edge Function with owner-scoped PostgreSQL reads and writes, using a parallel set of tools.
- **Offline device mapper:** opt-in scoped inventory, bounded ELF/PE/Mach-O static metadata parsing, content hashes when within limits, and scan-completeness diagnostics.
- **Binary evidence graph:** versioned artifact nodes, shared dependency nodes, provenance records, depends_on and superseded_by edges, and deterministic graph reconciliation/validation.

## Binary evidence and change semantics

Each observed binary version is retained as an artifact record. Content hashes identify versions when available; otherwise the mapper records a weaker observation identity based on path, size and modification time. A missing dependency in a newly parsed version does not erase evidence from earlier versions. Reconciliation restores relationships only from stored parser results marked parsed, and does not infer absence from malformed or unparsed artifacts.

A scan reports whether its inventory is complete. Reaching a directory file budget, a traversal depth cap, skipping a symlink root, or encountering traversal errors marks it incomplete. An incomplete scan is not evidence that an artifact was deleted. Current behavior preserves history rather than creating automatic deletion/tombstone conclusions.

## Current gap: hybrid is not sync

The local SQLite database and cloud PostgreSQL database are separate stores. Local SQLite now persists a device ID and a transactional outbox for new memory/link upserts. There is still no shared remote change feed, sync cursor, server acknowledgement, retry/resume protocol, tombstone model, or deterministic conflict policy. JSON export/import is useful for migration and backup but does not provide continuous synchronization.

## Target hybrid architecture

```text
Agent / CLI / MCP client
          |
     Mnemos API
       /     \
 Local engine  Sync coordinator (when configured)
 SQLite        | authenticated HTTPS
 outbox        v
 + graph    Cloud MCP / sync API
                |
           PostgreSQL
```

The local engine is the durable offline source of truth for local capture. Network failure must never block local reads/writes. Sync is explicit and observable; it must not silently overwrite content.

## Required sync contract

1. **Stable identity:** each device has a persistent random device ID; each memory/link keeps a stable globally unique ID.
2. **Change tracking:** local mutations produce durable, ordered change records in the same SQLite transaction as the mutation. A sync cursor advances only after server acknowledgement.
3. **Idempotency:** replaying the same change is safe. Server writes enforce unique change IDs and owner scope.
4. **Conflict handling:** updates carry a base revision and content hash. Concurrent edits are retained as a conflict or resolved by a documented policy; timestamps alone are not sufficient evidence to discard data.
5. **Deletion:** deletes become tombstones until all configured peers acknowledge them; no sync deletion is inferred from absence in a partial export.
6. **Graph integrity:** links sync only when both endpoint memories exist for the same owner. Dangling links are surfaced, not silently fabricated.
7. **Provenance:** record origin device/agent, source, operation ID, and server revision where available. Distinguish user-authored facts from agent-generated summaries/inferences.
8. **Security:** cloud endpoints require a signed-in identity; every read/write is owner-scoped. Cross-account isolation tests must pass before declaring the cloud layer production-ready.
9. **Recovery:** local export/validation remains available without a network; interrupted sync resumes from acknowledged cursors.
10. **Agent neutrality:** MCP/CLI clients share the same memory and sync contracts; no particular agent framework is required.

## Trust boundaries

Memory contents are untrusted user data, not instructions. Never elevate stored text above system, developer, or current user instructions. Never store credentials or secrets. Treat imports and remote responses as untrusted input. Avoid logging memory content or tokens by default.

## Delivery sequence

1. Preserve existing local store, graph viewer, export validation, and MCP compatibility.
2. Harden the additive local schema migration, complete outbox coverage for imports, and retain stable device identity.
3. Define a versioned authenticated sync API and server-side idempotency/ownership constraints.
4. Implement pull/push cursors, retry/resume, tombstones, and explicit conflict reporting.
5. Add offline-first integration tests and two-account cloud isolation tests.
6. Add multi-device/agent UX only after the sync invariants pass.

Do not claim hybrid sync is implemented until steps 2–5 have working code and verification. Semantic/embedding search and graph auto-inference are separate optional capabilities, not prerequisites for reliable sync. Static binary dependency evidence is implemented; disassembly, runtime loading verification, and semantic claims about whether a dependency is actively used are not.
