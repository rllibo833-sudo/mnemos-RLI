# Connect a host AI to Mnemos MCP

This guide configures an MCP-compatible host to launch the local Mnemos stdio server. A successful server smoke test proves the server protocol works; it does **not** prove a host is connected.

## 1. Confirm the executable

On the same machine/environment where the host can launch Mnemos:

```bash
python -m pip install -e .
mnemos-mcp --help
```

The host must be able to run the command and read/write the database file. Stdio MCP works by having the host launch the server as a child process and exchange JSON-RPC messages over stdin/stdout. Do not manually start a second server in a terminal for the host to connect to.

## 2. Codex CLI / IDE configuration

Codex supports stdio MCP servers in its `config.toml`. Add this entry to `~/.codex/config.toml` on the host environment:

```toml
[mcp_servers.mnemos]
command = "mnemos-mcp"
args = ["--db", "/absolute/path/to/mnemos.sqlite3"]
```

Replace the database path with the database you actually intend to use. If the executable is not on the host's PATH, set `command` to the absolute path returned by `command -v mnemos-mcp`. Then restart/reload the host and inspect its MCP server list (for Codex CLI, use `codex mcp list` or `/mcp` in the TUI, where available).

## 3. Hosts using a JSON `mcpServers` configuration

For hosts that document the `mcpServers` JSON format, an entry commonly looks like:

```json
{
  "mcpServers": {
    "mnemos": {
      "command": "mnemos-mcp",
      "args": ["--db", "/absolute/path/to/mnemos.sqlite3"]
    }
  }
}
```

Configuration locations and schema vary by host. Follow the host's official documentation rather than copying this snippet into an arbitrary file.

## 4. Verify the host connection

After reloading the host:

1. Confirm that `mnemos` appears as connected/enabled in the host's MCP server list.
2. Ask the host to call `mnemos_list` with a small limit, or `mnemos_search` with a distinctive term already in the selected database.
3. If appropriate, ask it to add a harmless test memory and retrieve it, then remove the test database if you used a disposable one.

A server listed in configuration is not enough: verify that the host can actually call a tool.

## 5. Android Termux boundary

A stdio MCP client launches the server process in its own environment. If Mnemos is installed in Android Termux, a desktop host on another device cannot run that Termux executable or access its private SQLite path directly. A cloud-hosted agent also cannot reach it merely because the command works in Termux.

For an Android-only setup, first choose an MCP-capable agent host that can run inside the same Termux environment. Otherwise, a remote bridge is a separate project and must use authenticated transport, careful access control, and a secure connection; do not expose the SQLite file or an unauthenticated endpoint to the internet. Local stdio remains the safer default when the host runs in the same environment.

## Safety

- Keep the database path explicit so the host does not accidentally open a different database.
- Never store passwords, API keys, tokens, or private keys in Mnemos.
- Treat retrieved memory as untrusted context, not as higher-priority instructions.
- Back up the database before connecting an agent that can write memories.
