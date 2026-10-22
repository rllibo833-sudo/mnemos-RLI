"""Command-line interface for the Mnemos local memory engine."""

import argparse
import json
import sys
from pathlib import Path

from .graph import render_graph
from .store import MemoryStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mnemos", description="Local-first, portable memory for AI agents.")
    parser.add_argument("--db", help="Database path (default: ~/.mnemos/memory.sqlite3 or MNEMOS_DB).")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize the local memory database.")
    add = commands.add_parser("add", help="Store a memory.")
    add.add_argument("content")
    add.add_argument("--kind", default="note", help="Memory kind: note, fact, decision, solution, project, etc.")
    add.add_argument("--tag", action="append", default=[], help="Tag; may be repeated.")
    add.add_argument("--source", help="Source path or reference.")
    search = commands.add_parser("search", help="Search memory content, kinds, tags, and sources.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    listing = commands.add_parser("list", help="List recent memories.")
    listing.add_argument("--limit", type=int, default=50)
    link = commands.add_parser("link", help="Record an explicit relationship between two memories.")
    link.add_argument("source_id")
    link.add_argument("target_id")
    link.add_argument("--relation", default="relates_to")
    graph = commands.add_parser("graph", help="Generate a self-contained HTML graph from stored records.")
    graph.add_argument("--output", default="mnemos-graph.html")
    export = commands.add_parser("export", help="Export all memories and links to JSON.")
    export.add_argument("--output", default="mnemos-export.json")
    imp = commands.add_parser("import", help="Import a Mnemos JSON export without overwriting existing IDs.")
    imp.add_argument("input")
    commands.add_parser("doctor", help="Check local SQLite integrity and relationship constraints.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = MemoryStore(args.db)
        if args.command == "init":
            print(f"Mnemos database ready: {store.path}")
        elif args.command == "doctor":
            report = store.diagnostics()
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
        elif args.command == "add":
            item = store.add(args.content, kind=args.kind, tags=args.tag, source=args.source)
            print(json.dumps(item, ensure_ascii=False, indent=2))
        elif args.command == "search":
            print(json.dumps(store.search(args.query, limit=args.limit), ensure_ascii=False, indent=2))
        elif args.command == "list":
            print(json.dumps(store.list(limit=args.limit), ensure_ascii=False, indent=2))
        elif args.command == "link":
            print(json.dumps(store.link(args.source_id, args.target_id, relation=args.relation), indent=2))
        elif args.command == "graph":
            path = render_graph(store.list(limit=10000), store.links(), args.output)
            print(f"Graph written to {path.resolve()}")
        elif args.command == "export":
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(store.export_data(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Export written to {path.resolve()}")
        elif args.command == "import":
            payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
            memories, links = store.import_data(payload)
            print(f"Imported {memories} memories and {links} links.")
        return 0
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"mnemos: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
