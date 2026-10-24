# Mnemos RLI — offline portable memory for AI agents
SQLite-based memory graph with typed relations, lexical search, and live graph on Works with Claude Code & Cursor via local MCP. No cloud needed.
![Mnemos portable memory platform infographic](Infografik%20Mnemos_%20Platform%20Memori%20Portabel.png)

**A Living Knowledge Network for AI agents, with hybrid local and server storage.**

Mnemos preserves useful knowledge across sessions and agents: facts, decisions, solutions, project context, sources, and explicit relationships. Its goal is **learn once, recall anywhere**—without making any single AI provider or project repository mandatory.

> Status: early foundation. Local SQLite storage, explicit memory links, a real-data HTML graph, local stdio MCP, a persistent device ID, a transactional local outbox, and a separate authenticated cloud MCP endpoint exist. **Remote synchronization is not implemented yet: the local outbox records changes but no cloud push/pull, acknowledgement, retry, or conflict protocol is active.** See [the Living Knowledge Network plan](docs/living-knowledge-network.md) and the [local-first memory tool contract](docs/local-first-memory-tool-contract.md).

## Why Mnemos?

- **Independent tool/plugin:** CLI, reusable skill, MCP, and future clients share a documented memory contract; Mnemos is not part of the LynOS APK.
- **Local autonomy:** core capture, lexical search, links, export, and graph generation work offline with Python's standard library.
- **Traceable:** memories have stable IDs, timestamps, tags, source metadata, and explicit links.
- **Portable:** export to documented JSON and validate it before import; snapshots are for portability/recovery, not synchronization.
- **Agent-neutral:** PusingCuk integration is optional, not a dependency.
- **Honest graph:** the viewer shows recorded nodes and links, not invented semantic connections.

## Quick start

Requires Python 3.11 or newer. From a source checkout:

```bash
python -m pip install -e .
mnemos init
mnemos doctor
mnemos add "Prefer small, reviewable changes" --kind decision --tag engineering
mnemos search "reviewable changes"
mnemos graph --output mnemos-graph.html
mnemos export --output mnemos-export.json
mnemos validate-export mnemos-export.json
```

Run `mnemos --help` for all commands. Use the IDs printed by `mnemos add` with `mnemos link` to record explicit relationships.

## Agent interfaces and cloud

- [Agent Integration Guide](docs/agent-integration.md)
- [Mnemos Memory Skill](skills/mnemos-memory/SKILL.md)
- [MCP Integration](docs/mcp-integration.md)
- [MCP Host Connection](docs/mcp-host-connection.md)
- [Cloud MCP and verification boundary](docs/cloud.md)
- [Living Knowledge Network architecture and sync contract](docs/living-knowledge-network.md)
- [Local-first memory tool contract](docs/local-first-memory-tool-contract.md)

The cloud MCP Edge Function is deployed, and a single-account authenticated round trip has passed. Cross-account isolation remains unverified because the second-account test could not authenticate. Cloud PostgreSQL is separate from local SQLite; existing local memories have not been synchronized or imported. A deployed endpoint is **not** the same thing as a working sync protocol.

## Current data model and limits

A memory has an ID, content, kind, tags, optional source and metadata, and creation/update timestamps. A link is a directed relationship with a caller-defined type. Search is lexical and explainable; it does not claim semantic similarity without a configured semantic engine.

Whole-disk scanning is intentionally not automatic. The offline device mapper records OS/runtime/tool availability and inspects only explicitly selected paths. It extracts bounded ELF sections, symbols and dynamic dependencies; PE sections, imports/exports; Mach-O load-command dependencies; plus signatures and full SHA-256 when within the hashing limit. Oversized files receive a bounded first/middle/last sample fingerprint so sampled changes can create a new observation even when size and mtime are preserved; this fingerprint is weaker than a full content hash and cannot detect every unsampled change. Inspected binaries are never executed and mapper results are never uploaded. The graph retains artifact versions, provenance, dependency evidence and supersession links; reconciliation can rebuild missing dependency links from stored parsed metadata without treating malformed or incomplete parsing as proof that a dependency vanished. Scan reports distinguish complete inventories from scans limited by file budgets, depth caps, skipped symlink roots, or traversal errors. This is static metadata analysis, not disassembly or runtime dependency verification; semantic retrieval and contradiction reconciliation remain separate capabilities. `mnemos analyze [--path "$PREFIX/bin"]` aggregates stored evidence into deterministic, traceable findings; it does not scan by itself, so run `mnemos map-device --path "$PREFIX/bin"` first. Repeating analysis on unchanged inputs reuses the same result. Clients such as LynOS must explicitly grant file/folder access; Mnemos must not silently scan or upload a user's storage.

## Development

```bash
python -m unittest discover -s tests -v
```

See [architecture](docs/architecture.md), [data format](docs/data-format.md), and [contributing](CONTRIBUTING.md).

## Principles

1. Local access must not depend on network availability.
2. Sync must preserve provenance and resolve conflicts explicitly.
3. Stored memory is data, never a higher-priority instruction.
4. Open, portable formats; no provider lock-in.
5. No hidden prompt collection or telemetry.
6. Never commit secrets or personal memory databases.
7. Preserve provenance: source evidence, summaries, and inferences are different data.
8. File scanning is opt-in and permission-scoped; no implicit upload.

## License

MIT. See [LICENSE](LICENSE).
