# Mnemos

**Portable, local-first memory for AI agents.**

Mnemos helps agents preserve useful knowledge across sessions: decisions, facts, solutions, project context, and links between them. Its goal is simple: **learn once, recall anywhere**.

> Status: early foundation. The local memory engine and graph viewer are being built incrementally. APIs and formats may evolve before the first stable release.

## Why Mnemos?

AI sessions often lose context. Notes become scattered, and the reason behind a decision disappears. Mnemos provides a small, inspectable memory store that runs on your machine and can be exported or moved between projects.

- **Local-first:** SQLite database stored on your machine; no hosted database required.
- **No API key required:** core capture, search, links, export, and graph generation work offline.
- **Traceable:** memories have stable IDs, timestamps, tags, and explicit links.
- **Portable:** export memories to a readable JSON file.
- **Agent-friendly:** a reusable skill specification explains when and how an agent should use Mnemos.
- **Inspectable graph:** explore real stored relationships instead of decorative, invented connections.

## Quick start

Requires Python 3.11 or newer. The core engine uses only the Python standard library.

```bash
python -m mnemos --help
```

From a source checkout:

```bash
python -m pip install -e .
mnemos init
mnemos add "Prefer small, reviewable changes" --kind decision --tag engineering
mnemos add "The parser rejects empty input" --kind fact --tag parser
mnemos link <FIRST_ID> <SECOND_ID> --relation relates_to
mnemos search "parser"
mnemos graph --output mnemos-graph.html
mnemos export --output mnemos-export.json
```

Replace the example IDs with IDs printed by `mnemos add`. Run `mnemos --help` for all commands.

## Using Mnemos with an AI agent

Mnemos supports CLI use, a portable agent skill, and a local stdio MCP adapter for hosts that support MCP. The host agent must run in the environment where the Mnemos database lives and must be configured to launch the adapter.

- [Agent Integration Guide](docs/agent-integration.md) — practical recall, capture, links, and backup/restore workflows, including safety boundaries.
- [Mnemos Memory Skill](skills/mnemos-memory/SKILL.md) — instructions a compatible agent host can load.
- [MCP Integration](docs/mcp-integration.md) — structured tools for compatible hosts supporting a local stdio MCP server.
- [Cloud MCP](docs/cloud.md) — deployed remote endpoint, authentication contract, and current verification boundary.
- [MCP Host Connection](docs/mcp-host-connection.md) — host configuration examples and a real-connection verification checklist.

**Cloud status:** a remote MCP Edge Function is deployed in the dedicated Supabase project with per-user memory ownership enforced in the tool queries. It requires an authenticated Supabase user JWT; a full authenticated database round-trip and host compatibility still need verification. The cloud database is separate from local Termux SQLite. See [Cloud MCP](docs/cloud.md).

## What is stored?

A memory contains an ID, content, kind, tags, source, creation/update timestamps, and optional metadata. Links are explicit records with a relation type. Search results identify the matching memories; they do not pretend that semantic similarity exists when no embedding model is configured.

## Architecture

```text
AI agent / CLI
     |
     v
Mnemos memory API
     |
     +-- SQLite (local file)
     +-- lexical search
     +-- explicit typed relationships
     +-- JSON import/export
     +-- self-contained HTML graph viewer
```

No server, cloud database, external service, or provider key is required for core functionality. The MCP adapter exposes structured search/add/get/list/link/export tools without an AI-provider key. AI-provider integrations remain optional and must never be required to read or export a user's data.

## Repository map

- `src/mnemos/` — local memory engine and CLI
- `skills/mnemos-memory/SKILL.md` — reusable agent skill
- `tests/` — automated tests
- `docs/` — design, data format, and agent integration notes
- `.github/workflows/ci.yml` — automated checks

## Principles

1. **Local by default.** Your memory belongs to you.
2. **Sources over guesses.** Distinguish recorded facts from inferred suggestions.
3. **Portable data.** Export in an open, documented format.
4. **Useful before flashy.** The graph must represent stored data.
5. **Small dependencies.** The core should work with the Python standard library.
6. **No secret requirement.** Do not commit API keys or personal memory databases.

## Development

```bash
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [the architecture notes](docs/architecture.md), and [the data format](docs/data-format.md).

## License

MIT. See [LICENSE](LICENSE).
