# Mnemos Knowledge API Contract

Portable exchange object:

```json
{"schema_version":1,"workspace_id":"UUID","nodes":[],"links":[]}
```

A node is validated by `schemas/memory.schema.json`; a link by `schemas/link.schema.json`. The cloud adapter uses the tables in `schemas/supabase.sql`.

- **Search:** use the existing Mnemos lexical search locally; do not assume embeddings are configured.
- **Capture:** create a stable node ID, concise content, provenance, and SHA-256 when source bytes are available.
- **Link:** create a typed directed edge only when evidence supports it.
- **Push:** `node knowledge/plugins/supabase-sync/sync.js push bundle.json`.
- **Pull:** `node knowledge/plugins/supabase-sync/sync.js pull [ISO_TIMESTAMP] [--output file.json]`.
- **Media:** shared nodes contain source category, hash, extraction metadata, and bounded text—not binary bytes.

The sync client uses a user access token and Supabase RLS. Never use a service-role key in an agent, skill, mobile app, or committed configuration. This is a JSON bundle boundary, not a claim that existing SQLite rows automatically synchronize.
