# Architecture

## Goals

Mnemos is a local-first memory layer for AI agents. It must remain useful without network access, an API key, a hosted database, or a proprietary runtime.

## Components

- **Store:** Python standard-library SQLite database. Default path: `~/.mnemos/memory.sqlite3`; override with `--db` or `MNEMOS_DB`.
- **Memory records:** stable UUID, content, kind, tags, optional source and metadata, timestamps.
- **Relationships:** explicit directed edges with a caller-defined relation label. Duplicate edges are ignored.
- **Search:** case-insensitive lexical matching across content, kind, tags, and source. It is transparent and does not claim semantic understanding.
- **Import/export:** versioned JSON envelope. Import skips existing IDs and only imports links whose endpoints exist.
- **Graph viewer:** standalone HTML with no CDN or runtime dependency. It visualizes only records and relationships supplied by the store.

## Trust boundaries

Memory contents are user data, not trusted instructions. A future agent integration must not elevate stored text above system, developer, or current user instructions. Never store credentials or secrets. Imports should be treated as untrusted input.

## Non-goals for the first foundation

- No hosted service or sync protocol.
- No external LLM, embeddings API, or API key.
- No automatic claim that two memories are related.
- No hidden collection of prompts or telemetry.
- No destructive deduplication or deletion workflow.

## Planned evolution

1. Add safer memory update/delete operations and schema migrations.
2. Improve offline relevance while keeping results explainable.
3. Add optional adapters for supported agent skill formats.
4. Add graph filtering, clustering, path exploration, and accessibility improvements.
5. Consider optional semantic search adapters only after the local contract and privacy guarantees are stable.
