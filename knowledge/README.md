# Mnemos RLI Knowledge

This directory is the portable, versioned knowledge layer for Mnemos RLI. It sits beside the frozen offline SQLite core and evolves independently on the `Knowledge` branch.

## Data flow

1. Keep original files on the device by default.
2. Extract bounded knowledge locally: text, OCR, captions, timestamps, document metadata, and content hashes.
3. Normalize results into memory nodes and typed links using `schemas/`.
4. Sync the small knowledge payload to Supabase using `plugins/supabase-sync/sync.js`.
5. Load agent capabilities from `skills/<name>/manifest.json`; treat `core/` as owner-controlled policy, not agent-editable memory.

The sync client sends JSON metadata and bounded text only. It rejects common binary/base64 payload fields. It does not upload originals, thumbnails, embeddings, or arbitrary file bytes.

## Supabase setup

Apply `schemas/supabase.sql` to the target Supabase project. Set these environment variables in the trusted runtime; never commit their values:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_ACCESS_TOKEN` — signed-in user's access token, not the service-role key
- `MNEMOS_WORKSPACE_ID` — UUID shared by devices that should share this workspace

Commands:

```sh
node knowledge/plugins/supabase-sync/sync.js push bundle.json
node knowledge/plugins/supabase-sync/sync.js pull
node knowledge/plugins/supabase-sync/sync.js pull 2026-01-01T00:00:00.000Z --output remote-bundle.json
```

Bundle shape: `{ "schema_version": 1, "workspace_id": "<uuid>", "nodes": [], "links": [] }`. Apply the SQL and verify authentication before treating the remote workflow as live.

## Media and size

A 100 MB video cannot become a tiny file without discarding information. Process it locally into a small searchable representation: metadata, transcript, OCR from selected frames, timestamps, scene summaries, and SHA-256. Keep the original local; optionally generate a lower-resolution derivative with an approved media tool. The graph stores provenance and references, not a claim that a derivative is identical to the source.

Supported source categories: images, documents, video, audio, code, and generic files. Extraction depends on locally installed tools and explicit permissions. No whole-disk scan, silent upload, automatic file execution, face identification, or secret collection.

## PusingCuk boundary

PusingCuk's versioned IR and bytecode contracts are useful models for deterministic interchange, not media compression. `pusingcuk-loader/loader.cuk` is a language-side envelope example; Supabase HTTP is handled by the JavaScript adapter until a stable PusingCuk host I/O contract exists.
