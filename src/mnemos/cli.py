"""Command-line interface for the Mnemos local memory engine."""

import argparse
import json
import sys
from pathlib import Path

from .graph import render_graph
from .store import MemoryStore
from .contract import bundle_from_snapshot, snapshot_graph, unbundle_to_store, roundtrip_snapshot
from .supabase_sync import sync_minimal


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
    bundle = commands.add_parser("bundle", help="Write a portable full graph snapshot.")
    bundle.add_argument("--output", required=True)
    unbundle = commands.add_parser("unbundle", help="Import a graph snapshot with updated_at conflict protection.")
    unbundle.add_argument("input")
    sync = commands.add_parser("sync", help="Snapshot locally and optionally sync with Supabase.")
    sync.add_argument("--dry-run", action="store_true", help="Plan minimal Supabase payload offline; never contacts Supabase.")
    commands.add_parser("simulate-supabase-sync", help="Simulate minimal Supabase sync offline.")
    simulate = commands.add_parser("simulate-bundle", help="Run an offline bundle/unbundle round trip.")
    simulate.add_argument("--input", help="Existing export JSON; defaults to local SQLite.")
    simulate.add_argument("--output", help="Optional round-trip output JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = MemoryStore(args.db)
        if args.command == "init":
            print(f"Mnemos database ready: {store.path}")
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
        elif args.command == "bundle":
            path = bundle_from_snapshot(snapshot_graph(store), args.output)
            print(f"Bundle written to {path}")
        elif args.command == "unbundle":
            print(json.dumps(unbundle_to_store(args.input, store, protect_updated_at=True), ensure_ascii=False, indent=2))
        elif args.command == "simulate-bundle":
            snapshot = json.loads(Path(args.input).read_text(encoding="utf-8")) if args.input else snapshot_graph(store)
            result, _ = roundtrip_snapshot(snapshot)
            if args.output:
                target = Path(args.output).expanduser().resolve(); target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            memories = result.get("memories", [])
            preserved = sum(isinstance(item.get("tags"), list) for item in memories if isinstance(item, dict))
            links_count = len(result.get("links", []))
            print(f"SIM: {len(memories)} memories, {links_count} links, tags_arrays_preserved: {preserved}")
        elif args.command == "sync":
            if not args.dry_run:
                raise ValueError("Supabase network sync is disabled; run sync --dry-run")
            result = sync_minimal(store, dry_run=True)
            print("payload KB: {:.2f}".format(result["payload_kb"]))
            print("memories baru: {}".format(result["new_memories"]))
            print("memories pending: {}".format(result["pending_memories"]))
            print("links filtered: {}".format(result["links_filtered"]))
            print("outbox changes: {}".format(result["changed_items"]))
        elif args.command == "simulate-supabase-sync":
            result = sync_minimal(store, dry_run=True)
            print("{} local -> {} to push ({:.2f} KB) -> {} links filtered".format(result["local_memories"], result["pending_memories"], result["payload_kb"], result["links_filtered"]))
            print("memories baru: {}; outbox changes: {}".format(result["new_memories"], result["changed_items"]))
        return 0
    except (ValueError, KeyError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"mnemos: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
