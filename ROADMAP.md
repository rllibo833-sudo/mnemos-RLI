# Mnemos Roadmap — Living Knowledge Network

**Status:** canonical product roadmap for Mnemos-RLI. This document describes target outcomes and distinguishes them from implemented capabilities. It does not imply a phase is complete merely because its design exists.

## Product north star

Mnemos is an independent, portable memory platform: one durable knowledge model and open data format, many devices, host environments, and AI agents. A person can capture knowledge once, inspect its provenance and relationships, move it between machines, and grant agents controlled access without surrendering ownership of the underlying data.

The reference vision has two complementary surfaces:

- **Living Knowledge Network:** an inspectable graph of memories, concepts, projects, people, tools, files, events, and relationships, with activity, search, sync, and agent surfaces.
- **Portable Memory Platform:** a stable API shared by CLI, desktop applications, mobile/native clients, MCP, skills, and external applications, backed by a local database and optional self-hosted/cloud synchronization.

These are product goals, not claims that all UI surfaces, semantic reasoning, or synchronization already exist.

## Current verified baseline

Present in the repository today:

- Python CLI and local SQLite memory store.
- Stable memory IDs, timestamps, tags, source/metadata, explicit directed links, lexical search, and portable JSON export/import validation.
- HTML graph generated from real stored nodes and links.
- Local stdio MCP adapter.
- Persistent device identity and a transactional local outbox for memory/link upserts.
- Separate authenticated Supabase Edge Function and owner-scoped PostgreSQL operations.
- Opt-in offline device mapper and bounded static ELF, PE, and Mach-O metadata parsing.
- Artifact history, provenance-bearing dependency graph reconciliation, scan-completeness diagnostics, and deterministic analysis records.
- Documentation for architecture, data format, cloud boundary, recovery, and agent integration.

### Explicit gaps — do not describe as implemented

- Local SQLite and cloud PostgreSQL are separate stores; there is no complete automatic push/pull synchronization protocol.
- The outbox does not yet provide the full acknowledged cursor, retry/resume, idempotency ledger, conflict, or tombstone lifecycle required for safe sync.
- One-account authenticated cloud round-trip was reported successful; cross-account isolation remains **unverified** because the two-account flow stopped at authentication.
- Core search is lexical. Semantic/vector retrieval, evidence-grounded synthesis, and inferred semantic links are not current core guarantees.
- The binary mapper is bounded static metadata analysis, not disassembly, execution, or proof of runtime dependency use.
- The repository does not yet provide complete native desktop/mobile applications for all pictured operating systems.
- Skills and MCP are integration surfaces, not proof that every AI host is connected or that all agents share live data.

## Architecture rules

1. **Local-first, offline-capable:** capture, search, links, export, graph, and recovery continue without a network.
2. **One domain contract:** CLI, MCP, skills, future native clients, and cloud adapters call the same memory semantics; adapters must not invent divergent models.
3. **Portable data:** versioned JSON plus metadata is the migration/interchange boundary. Schema changes are additive and migrations preserve existing databases.
4. **Explicit provenance:** distinguish user-authored statements, imported source material, agent summaries, hypotheses, and verified observations.
5. **Honest graph:** persist explicit relationships and label any future inferred edge with method, confidence, and evidence. Never present a guess as a recorded fact.
6. **Safe synchronization:** stable operation IDs, per-owner isolation, idempotent replay, acknowledged cursors, conflict visibility, and tombstones; timestamps alone must not silently discard concurrent edits.
7. **Permission-scoped device mapping:** no automatic whole-disk scans, binary execution, or upload. Partial scans cannot imply deletion.
8. **Agent-neutral:** no dependency on PusingCuk, LynOS, a particular model provider, or a proprietary runtime.
9. **Privacy by default:** no hidden prompt collection or telemetry; secrets are not memories; imported/remote memory is untrusted data, never higher-priority instructions.
10. **One canonical roadmap:** architecture and integration docs state contracts and boundaries; this file owns sequencing and completion criteria. Avoid duplicate roadmaps that drift.

## Delivery roadmap

### Phase 0 — Repository and contract alignment
**Goal:** make current behavior, boundaries, and future work consistent across the repo.

- Treat this roadmap as the canonical sequence.
- Keep README status honest and link to architecture, data format, sync contract, cloud verification boundary, and roadmap.
- Ensure CLI, MCP, cloud docs, skill, and export/import describe the same memory fields, IDs, link semantics, and trust boundary.
- Remove or consolidate contradictory/duplicated plans rather than appending another status document.
- Verify that every claimed capability points to an implementation path; label planned behavior explicitly.
- Preserve the current working local foundation and existing tests. Do not create new tests solely to document progress; use existing suites and manual/integration verification where appropriate.

**Exit:** one coherent product description; no documentation claims automatic sync, semantic retrieval, cross-account security, or native apps without working evidence.

### Phase 1 — Harden the portable local core
**Goal:** make the local database a dependable offline source of truth.

- Audit schema versions and migrations against real existing databases; preserve records and links during upgrades.
- Make mutation semantics consistent across CLI, Python API, and MCP.
- Complete atomic change tracking for all supported mutations, including update and delete; give each operation a stable ID and local sequence.
- Make diagnostics show schema version, device identity, outbox backlog, and actionable storage errors without leaking memory contents.
- Keep import idempotent and transactional; retain export validation and recovery.
- Ensure graph and analysis are deterministic and explicitly report incomplete inputs.

**Exit:** existing user data survives upgrades; offline CRUD, search, links, graph, export/import, MCP, and recovery remain usable; each supported mutation has an auditable local history.

### Phase 2 — Complete authenticated sync protocol
**Goal:** safely converge independent devices while preserving offline operation.

- Define a versioned sync contract with bounded push batches and pull-after-cursor.
- Add server-side idempotency/change ledger, owner-scoped revisions, and acknowledgements.
- Advance local cursors only after acknowledgement; retain pending operations across restart, timeout, and server errors.
- Implement retry/resume with bounded backoff and visible error state.
- Represent deletes as tombstones; expire them only under an explicit peer-acknowledgement/retention rule.
- Detect concurrent changes using base revision/content hash and preserve inspectable conflicts; never silently use wall-clock last-write-wins.
- Enforce link endpoint ownership and existence; surface unresolved references.
- Validate account isolation with two real authenticated accounts before making a security claim. An auth login failure is not evidence of either a leak or successful isolation.
- Keep manual export/import available as recovery and migration even after sync exists.

**Exit:** two devices converge after interrupted/retried sync; duplicates are not created; conflicts remain inspectable; tombstones propagate safely; owner isolation is verified; offline writes never wait for cloud availability.

### Phase 3 — Knowledge graph and evidence-quality retrieval
**Goal:** make the graph useful without confusing evidence with inference.

- Stabilize node/link types for memories, concepts, projects, people, tools, files, events, and relationships without forcing every client to implement every visual category.
- Add explainable graph traversal and query filters over recorded relationships.
- Define a provider-neutral retrieval interface so lexical search remains the no-dependency baseline.
- Add optional semantic/vector retrieval only behind a documented engine/provider boundary; expose ranking explanations and provenance.
- Keep inferred relationships separate from explicit/user-confirmed edges and retain supporting evidence, method, and confidence.
- Make contradiction and supersession handling explicit; preserve history instead of silently rewriting facts.
- Add evidence-grounded synthesis only when each claim can point to source records and uncertainty is represented.

**Exit:** a result can be traced to stored evidence; semantic features can be disabled without breaking the core; graph views never manufacture relationships.

### Phase 4 — Agent interoperability: MCP, Skills, APIs, SDKs
**Goal:** make any compatible agent an optional client of the same platform.

- Keep MCP tools aligned with the stable domain contract and expose actionable validation errors.
- Document host configuration, permissions, local database location, and cloud credentials without publishing secrets.
- Keep the reusable Mnemos skill focused on when/how to recall and capture durable knowledge, not duplicating the whole manual.
- Add versioned REST/API and typed SDKs only when there is a concrete client requirement; do not duplicate business logic in adapters.
- Establish adapter compatibility/version policy and clear offline-vs-cloud behavior.
- Keep PusingCuk integration optional and make no assumption that LynOS bundles Mnemos.

**Exit:** multiple hosts use the same memory semantics and identity rules; removing one adapter does not affect stored data or other clients.

### Phase 5 — Native desktop and mobile experiences
**Goal:** deliver the application surfaces shown in the vision while retaining portability.

- Build a desktop control plane for Windows and macOS, then Linux/Ubuntu, over the shared data/API contract.
- Build Android and iOS native clients with platform-appropriate storage and permissions; do not assume Python or shell access inside an APK.
- Provide consistent search, add, get, link, graph, import/export, sync status, conflicts, and agent connections.
- Use platform adapters for filesystem/device mapping; permission must be explicit and revocable.
- Support local-only mode without account setup and optional self-hosted/cloud sync.
- Keep UI state separate from canonical memory data so clients can be replaced without data migration.

**Exit:** each supported client can operate offline, import/export the same portable format, and clearly show sync/conflict status. Platform support is claimed only after actual build and runtime verification on that platform.

### Phase 6 — Operations, security, and scale
**Goal:** make self-hosted/cloud deployment maintainable and trustworthy.

- Publish deployment, backup/restore, migration, retention, account recovery, and incident procedures.
- Verify authorization and row-level ownership boundaries across every cloud operation.
- Define API limits, payload limits, timeouts, audit events, and data-retention rules.
- Add observability for sync health and operational errors without logging memory contents or credentials.
- Establish schema/API compatibility and migration policy before supporting multiple deployed versions.
- Add load/performance measurement against representative data before optimizing storage or adding infrastructure.
- Keep distributed replication and managed cloud optional; do not introduce them before single-server sync correctness.

**Exit:** documented backup/restore, owner isolation evidence, migration guarantees, observable failure recovery, and measured capacity limits.

## Cross-phase completion policy

A phase is complete only when its implementation, existing verification evidence, operational documentation, and status statements agree. A diagram, plan, deployed endpoint, passing unit suite, or successful single-account request alone does not prove an end-to-end product capability.

Do not expand the test suite merely to make the roadmap look complete. Reuse the existing suite and perform focused manual or existing integration verification; report any unverified acceptance condition honestly.

## Immediate priority order

1. Align repository documentation and contracts around this roadmap.
2. Complete the local outbox lifecycle for every supported mutation.
3. Implement and verify the authenticated sync protocol end to end.
4. Verify cross-account isolation before describing cloud sync as secure/production-ready.
5. Improve graph/retrieval explainability.
6. Stabilize MCP/skill/client compatibility.
7. Deliver native desktop/mobile surfaces.
8. Scale operations only after correctness and recovery are proven.
