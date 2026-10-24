# Mnemos Knowledge API Contract

Portable exchange object:

```json
{"schema_version":1,"workspace_id":"UUID","nodes":[],"links":[]}
```

A node is validated by `schemas/memory.schema.json`; a link by `schemas/link.schema.json`. The sync adapter uses `public.knowledge_workspaces`, `public.knowledge_workspace_members`, `public.knowledge_nodes`, and `public.knowledge_links` from `schemas/supabase.sql`. Workspace membership is the access boundary; the owner receives admin role when a workspace is created.

- **Search:** use the existing Mnemos lexical search locally; do not assume embeddings are configured.
- **Capture:** create a stable node ID, concise content, provenance, and SHA-256 when source bytes are available.
- **Link:** create a typed directed edge only when evidence supports it.
- **Push:** `node knowledge/plugins/supabase-sync/sync.js push bundle.json`.
- **Pull:** `node knowledge/plugins/supabase-sync/sync.js pull [ISO_TIMESTAMP] [--output file.json]`.
- **Workspace:** `node knowledge/plugins/supabase-sync/sync.js workspace create --name "Workspace name"` creates a workspace; `workspace member-add WORKSPACE_UUID USER_UUID --role writer` grants a collaborator access.
- **Local sync entry point:** `python -m mnemos.cli sync --dry-run` delegates to the same plugin without network access; omit `--dry-run` only after configuring authenticated Supabase access.
- **Media:** shared nodes contain source category, hash, extraction metadata, and bounded text—not binary bytes.

The sync client uses a user access token and Supabase RLS. Never use a service-role key in an agent, skill, mobile app, or committed configuration. Local SQLite data is not uploaded automatically. Deletion propagation remains disabled until the local store has a reliable tombstone protocol.
