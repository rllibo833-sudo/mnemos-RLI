# Mnemos RLI Knowledge

This directory is the portable, versioned knowledge layer for Mnemos RLI. It sits beside the frozen offline SQLite core and evolves independently on the `Knowledge` branch.

## Five knowledge layers

The canonical graph uses one shared node/edge model with five explicit knowledge layers. Their schema, metadata requirements, evidence rules, and typed relationship vocabulary are defined in [layers/manifest.json](layers/manifest.json), explained in [layers/README.md](layers/README.md), and enforced by the graph manifest generator.

- **Historical Knowledge** — events, discoveries, people, institutions, and timelines.
- **Philosophical Knowledge** — questions, assumptions, principles, arguments, ethics, and consequences.
- **Scientific Knowledge** — theories, laws, claims, methods, observations, and evidence status.
- **Cross-Disciplinary Relations** — justified mappings across two or more disciplines.
- **Experimental Knowledge** — hypotheses, protocols, simulations, measurements, results, replications, and failures.

Legacy nodes and edges remain valid. A record opts into strict layer validation by declaring `metadata.knowledge_layer` and its corresponding `metadata.knowledge` object.

## Data flow

1. Keep original files on the device by default.
2. Extract bounded knowledge locally: text, OCR, captions, timestamps, document metadata, and content hashes.
3. Normalize results into memory nodes and typed links using `schemas/` and the five-layer contract.
4. Sync the small knowledge payload to Supabase using `plugins/supabase-sync/sync.js`.
5. Load agent capabilities from `skills/<name>/manifest.json`; treat `core/` as owner-controlled policy, not agent-editable memory.
6. Validate the complete graph and layer-specific metadata before the canonical `Knowledge` snapshot is published.

The sync client sends JSON metadata and bounded text only. It rejects common binary/base64 payload fields. It does not upload originals, thumbnails, embeddings, or arbitrary file bytes.

## Beyond-Light integration

Beyond-Light is a research client and producer of research runs, source records, evidence reports, and cross-domain ideas. It should publish these as typed graph nodes and edges through the existing authenticated Supabase Outbox transport. The Outbox is temporary delivery only; the durable destination remains this branch.

The mapping and evidence semantics are specified in [layers/README.md](layers/README.md). A simulation or analytical benchmark must not be represented as a successful physical experiment.

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
```

Bundle shape: `{ "schema_version": 1, "workspace_id": "<uuid>", "nodes": [], "links": [] }`. Apply the SQL and verify authentication before treating the remote workflow as live.

## Media and size

A 100 MB video cannot become a tiny file without discarding information. Process it locally into a small searchable representation: metadata, transcript, OCR from selected frames, timestamps, scene summaries, and SHA-256. Keep the original local; optionally generate a lower-resolution derivative with an approved media tool. The graph stores provenance and references, not a claim that a derivative is identical to the source.

Supported source categories: images, documents, video, audio, code, and generic files. Extraction depends on locally installed tools and explicit permissions. No whole-disk scan, silent upload, automatic file execution, face identification, or secret collection.

## PusingCuk boundary

PusingCuk's versioned IR and bytecode contracts are useful models for deterministic interchange, not media compression. `pusingcuk-loader/loader.cuk` is a language-side envelope example; Supabase HTTP is handled by the JavaScript adapter until a stable PusingCuk host I/O contract exists.


## Beyond-Light research import

The Beyond-Light research archive has been imported into [`sources/beyond-light/`](sources/beyond-light/README.md) from source commit `8fac43391796e3c61b2faa9ae42eb29415190c1f`.

- 10 source files are preserved verbatim.
- 207 source records are indexed across eight collection-level graph nodes.
- The graph nodes preserve source links, evidence status, limitations, and record indexes.
- Synthetic fixtures, computational benchmarks, model runs, published-report summaries, and source-linked NASA/NIST records remain explicitly distinguished.
- Beyond-Light's original repository files were not removed or modified by this import.

The import manifest is [`sources/beyond-light/IMPORT_MANIFEST.json`](sources/beyond-light/IMPORT_MANIFEST.json).