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

Mnemos currently integrates through its CLI and a portable agent skill, rather than an automatic background service. The host agent must be able to run shell commands in the environment where the Mnemos database lives.

- [Agent Integration Guide](docs/agent-integration.md) — practical recall, capture, links, and backup/restore workflows, including safety boundaries.
- [Mnemos Memory Skill](skills/mnemos-memory/SKILL.md) — instructions a compatible agent host can load.

**Important environment boundary:** installing Mnemos in Android Termux makes it available to commands running in Termux. It does not automatically make that local database accessible to ChatGPT or a cloud-hosted agent. Cross-device access requires a separate, deliberately designed secure bridge; do not upload a private memory database casually.

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

No server, cloud database, external service, or provider key is required for core functionality. AI-provider integrations, if added later, will be optional adapters and must never be required to read or export a user's data.

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
