"""Command-line interface for the Mnemos local memory engine."""

import argparse
import json
import sys
from pathlib import Path

from .device_mapper import collect_device_map
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
    mapping = commands.add_parser("map-device", help="Inventory this device offline; scan only explicitly supplied paths.")
    mapping.add_argument("--path", action="append", default=[], help="File or directory to inspect for binary artifacts; repeatable.")
    mapping.add_argument("--max-files", type=int, default=2000, help="Maximum files inspected across selected directories.")
    commands.add_parser("doctor", help="Check local SQLite integrity and relationship constraints.")
    commands.add_parser("sync-status", help="Show device identity and locally queued changes.")
    pending = commands.add_parser("outbox", help="List pending local changes awaiting sync.")
    pending.add_argument("--limit", type=int, default=100)
    validate = commands.add_parser("validate-export", help="Validate an export JSON before importing it.")
    validate.add_argument("input")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = MemoryStore(args.db)
        if args.command == "init":
            print(f"Mnemos database ready: {store.path}")
        elif args.command == "map-device":
            report = collect_device_map(args.path, max_files=args.max_files)
            snapshot = store.add(
                f"Device map: {report['device']['os']} {report['device']['os_release']} ({report['device']['architecture']})",
                kind="device_snapshot",
                source="mnemos-device-mapper",
                metadata=report,
            )
            artifact_ids = []
            dependency_ids = {}
            existing_dependency_ids = {}
            for existing in store.list(limit=10000):
                metadata = existing.get("metadata") or {}
                if existing.get("kind") != "runtime_dependency" or metadata.get("schema") != "mnemos-dependency-evidence-v1":
                    continue
                existing_name = str(metadata.get("name", "")).strip()
                existing_format = str(metadata.get("format", "")).strip()
                if existing_name and existing_format:
                    existing_dependency_ids[(existing_format, existing_name.casefold())] = existing["id"]
            dependency_records_created = 0
            dependency_links = 0
            for artifact in report["artifacts"]:
                record = store.add(
                    f"Binary artifact: {artifact['path']}",
                    kind="binary_artifact",
                    source="mnemos-device-mapper",
                    metadata=artifact,
                )
                store.link(snapshot["id"], record["id"], relation="contains_artifact")
                artifact_ids.append(record["id"])
                details = artifact.get("binary_details") or {}
                dependencies = []
                if details.get("format") == "Mach-O":
                    for item in details.get("dependencies", []):
                        dependencies.append({
                            "name": item.get("name", ""),
                            "kind": item.get("kind", "load"),
                            "format": "Mach-O",
                        })
                if details.get("format") == "ELF":
                    for item in details.get("dependencies", []):
                        dependencies.append({
                            "name": item.get("name", ""),
                            "kind": item.get("kind", "needed"),
                            "format": "ELF",
                        })
                for library in details.get("imports", []):
                    dependencies.append({
                        "name": library.get("library", ""),
                        "kind": "import",
                        "format": "PE",
                        "symbols": library.get("symbols", []),
                    })
                for dependency in dependencies:
                    name = dependency["name"].strip()
                    if not name:
                        continue
                    key = (dependency["format"], name.casefold())
                    if key not in dependency_ids:
                        if key in existing_dependency_ids:
                            dependency_ids[key] = existing_dependency_ids[key]
                        else:
                            dep_record = store.add(
                                f"Runtime dependency: {name}",
                                kind="runtime_dependency",
                                tags=[dependency["format"].lower(), dependency["kind"]],
                                source="mnemos-static-binary-metadata",
                                metadata={
                                    "schema": "mnemos-dependency-evidence-v1",
                                    "name": name,
                                    "format": dependency["format"],
                                    "kind": dependency["kind"],
                                    "symbols": dependency.get("symbols", []),
                                    "evidence": {
                                        "artifact_sha256": artifact.get("sha256"),
                                        "artifact_path": artifact.get("path"),
                                        "parser_status": details.get("status"),
                                        "method": "static-file-metadata",
                                        "execution_performed": False,
                                        "network_used": False,
                                    },
                                },
                            )
                            dependency_ids[key] = dep_record["id"]
                            existing_dependency_ids[key] = dep_record["id"]
                            dependency_records_created += 1
                    store.link(record["id"], dependency_ids[key], relation="depends_on")
                    dependency_links += 1
            print(json.dumps({
                "snapshot_id": snapshot["id"],
                "artifact_records": len(artifact_ids),
                "dependency_records": len(dependency_ids),
                "dependency_records_created": dependency_records_created,
                "dependency_links": dependency_links,
                "report": report,
            }, ensure_ascii=False, indent=2))
        elif args.command == "doctor":
            report = store.diagnostics()
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
        elif args.command == "sync-status":
            print(json.dumps(store.sync_status(), ensure_ascii=False, indent=2))
        elif args.command == "outbox":
            print(json.dumps(store.pending_changes(limit=args.limit), ensure_ascii=False, indent=2))
        elif args.command == "validate-export":
            payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
            report = MemoryStore.validate_export(payload)
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
