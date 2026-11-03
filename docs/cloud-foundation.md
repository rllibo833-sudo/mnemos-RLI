# Mnemos Cloud Foundation

## Canonical storage boundary

The `Knowledge` branch of this repository is the durable, inspectable graph snapshot and canonical publication target. Supabase is **temporary transport only**; it must not be treated as the long-term graph archive.

Steadfast and other authorized producers enqueue graph events in `public.mnemos_outbox`. The outbox stores a bounded payload, a stable idempotency key, and a checksum while delivery is pending. The workflow definition lives on the repository default branch (`main`) so GitHub schedule and repository-dispatch events actually execute. It checks out `Knowledge` for graph data and commits. It is triggered immediately by repository dispatch and also polls every 10 minutes as a recovery path.

## Delivery protocol

1. Producer writes one complete graph event to `mnemos_outbox`.
2. The producer dispatches `sync-supabase-to-knowledge` to this repository.
3. The Knowledge workflow reads pending events in creation order and verifies each canonical JSON SHA-256 checksum.
4. Nodes and edges are written as deterministic, upsertable files. Existing Knowledge files are never deleted by this transport importer.
5. The manifest generator verifies unique node IDs and that every edge endpoint exists in the resulting Knowledge snapshot.
6. The workflow commits and pushes the graph to branch `Knowledge`.
7. Only after the Git push step succeeds does the workflow acknowledge the exact outbox event IDs and payload checksums in Supabase.

If validation, commit, push, or acknowledgement fails, the event remains pending and the next scheduled run retries it. Replaying an event is safe: node filenames are derived from stable node IDs and relation files from stable event IDs. The acknowledgement is guarded by both event ID and payload checksum.

## Supabase boundary

- `public.mnemos_outbox` is a private transport table; only the service role can access it.
- RLS is enabled and public/anonymous/authenticated access is revoked.
- No graph query, permanent graph table, or media archive is required for this delivery path.
- Supabase may temporarily retain unacknowledged messages. Successful deliveries are marked with the exact Knowledge commit SHA; periodic cleanup can remove delivered rows after a short retention window.
- The previous `knowledge_nodes` / `knowledge_links` shared-graph tables are legacy and are not the destination of new Steadfast graph writes.

## Secrets and automation

Configure these GitHub Actions repository secrets in `rllibo833-sudo/mnemos-RLI`:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Configure these Supabase Edge Function secrets in Steadfast:

- `MNEMOS_GITHUB_TOKEN`: token with permission to dispatch workflows in `rllibo833-sudo/mnemos-RLI`.
- `MNEMOS_GITHUB_REPOSITORY`: optional; defaults to `rllibo833-sudo/mnemos-RLI`.
- `SUPABASE_SERVICE_ROLE_KEY`: server-only key used to enqueue events. Never expose it to a browser.

The workflow's 10-minute schedule is a recovery mechanism, not the primary trigger. Normal delivery is event-driven. The schedule prevents an expired/missing dispatch token or transient GitHub API failure from leaving an event permanently stranded.

## Local use

The local Mnemos SQLite engine remains independent and local-first. The optional sync plugin now follows the same boundary: `push` and `sync` enqueue a bounded graph event through the authenticated outbox policy; `pull` reads the committed `Knowledge` branch snapshot directly. The `sync` command reports that delivery is asynchronous and does not claim an immediate local round trip. Original SQLite database files and binary media are never uploaded.

## Verification requirements

A production-ready cycle is verified only after:
- Supabase is active and the outbox migration is applied.
- The Steadfast Edge Function is deployed with the transport implementation.
- The GitHub Actions secrets and Supabase function secrets are present.
- A test event is enqueued, automatically delivered to `Knowledge`, and acknowledged with the commit SHA.
- A replay of the same event creates no duplicate nodes or edges.
- A failed dispatch leaves the event pending for scheduled retry.

Do not claim end-to-end automation based on a successful workflow syntax check alone.
