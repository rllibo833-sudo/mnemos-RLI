# Mnemos Cloud Foundation

## Current boundary

SQLite remains the local source of work. The optional Knowledge-branch sync plugin transfers bounded text and graph metadata to Supabase only when explicitly invoked. It does not upload original media or run automatically. The local stdio MCP server remains independent; this plugin is not a deployed remote MCP endpoint.

## Shared graph model

- `public.knowledge_workspaces` defines a workspace and its owner.
- `public.knowledge_workspace_members` grants reader, writer, or admin access.
- `public.knowledge_nodes` and `public.knowledge_links` are keyed by workspace and stable local IDs, so authorized members read and write the same graph rather than separate per-user copies.
- Row-level security derives access from workspace membership. The public anon key alone does not grant access; use a signed-in user's access token.
- Source references are reduced to safe metadata. Secrets, local paths, and binary payloads are not synchronized.

The older private `mnemos` schema migration is a separate legacy foundation and is not the table contract used by `knowledge/plugins/supabase-sync/sync.js`.

## Local use

Dry-run the local graph bundle without network access:

```bash
python -m mnemos.cli sync --dry-run
```

For live push/pull, configure `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_ACCESS_TOKEN`, and `MNEMOS_WORKSPACE_ID`. Apply `supabase/migrations/20261024100000_shared_knowledge_graph.sql` before syncing. Create a workspace as an authenticated user; its owner is automatically assigned admin. Add collaborators to `public.knowledge_workspace_members` as reader, writer, or admin.

The sync plugin compares timestamps and content hashes, batches requests, and resolves equal-timestamp content conflicts using a canonical fingerprint, then advances the winning row's remote update timestamp so a subsequent pull converges. It refuses truncated pulls or bundles with unsupported tombstones. It does not acknowledge a transactional SQLite outbox; retries rely on idempotent workspace-keyed upserts. Deletion propagation is deliberately not enabled until a local tombstone protocol exists.

## Security and verification

Never put a service-role key in a device, skill, agent, or repository. Use the authenticated user's JWT and RLS. The repository code can be syntax-checked offline, but a live round trip and cross-account isolation must be verified against the configured Supabase project before claiming production readiness. No local SQLite data has been uploaded as part of these code changes.
