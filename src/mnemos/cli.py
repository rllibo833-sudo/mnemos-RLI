"""Command-line interface for the Mnemos local memory engine."""

import argparse
import contextlib
import hashlib
import io
import json
import sqlite3
import sys
import time
from pathlib import Path

from .device_mapper import collect_device_map
from .analysis import analyze_graph
from .daemon import run_daemon
from .evolution import evolve_graph
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
    graph.add_argument("--format", choices=("html", "json"), default="html",
                       help="Output an interactive HTML graph or graph JSON.")
    graph.add_argument("--live", action="store_true", help="Serve a local graph viewer that refreshes as the graph grows.")
    graph.add_argument("--port", type=int, default=8765, help="Loopback port for --live (default: 8765).")
    export = commands.add_parser("export", help="Export all memories and links to JSON.")
    export.add_argument("--output", default="mnemos-export.json")
    imp = commands.add_parser("import", help="Import a Mnemos JSON export without overwriting existing IDs.")
    imp.add_argument("input")
    mapping = commands.add_parser("map-device", help="Inventory this device offline; scan only explicitly supplied paths.")
    mapping.add_argument("--path", action="append", default=[], help="File or directory to inspect for binary artifacts; repeatable.")
    mapping.add_argument("--max-files", type=int, default=2000, help="Maximum files inspected across selected directories.")
    evolution = commands.add_parser("evolve", help="Reconcile artifact history and validate binary graph invariants.")
    analyze = commands.add_parser("analyze", help="Aggregate graph evidence into deterministic, traceable conclusions.")
    analyze.add_argument("--path", action="append", default=[], help="Restrict analysis to snapshots with this exact scan scope; repeatable.")
    analyze.add_argument("--critical-threshold", type=int, default=20, help="Flag dependencies used by more than this many active artifact versions.")
    analyze.add_argument("--churn-threshold", type=int, default=3, help="Flag paths with more than this many supersessions in the observation window.")
    analyze.add_argument("--window-days", type=int, default=30, help="Observation window for churn analysis (default: 30 days).")
    daemon = commands.add_parser("daemon", help="Continuously refresh an offline device map for explicitly selected paths.")
    daemon.add_argument("--path", action="append", default=[], help="File or directory to scan; repeatable.")
    daemon.add_argument("--max-files", type=int, default=2000, help="Maximum files inspected per scan.")
    daemon.add_argument("--interval", type=float, default=300, help="Seconds between full scans (default: 300).")
    daemon.add_argument("--once", action="store_true", help="Run one scan and exit.")
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
        elif args.command == "evolve":
            report = evolve_graph(store)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
        elif args.command == "analyze":
            result, created = analyze_graph(
                store, paths=args.path or None,
                critical_threshold=args.critical_threshold,
                churn_threshold=args.churn_threshold,
                window_days=args.window_days,
            )
            metadata = result.get("metadata") or {}
            print(json.dumps({
                "analysis_id": result["id"], "created": created,
                "input_fingerprint": metadata.get("input_fingerprint"),
                "source_snapshot_ids": metadata.get("source_snapshot_ids", []),
                "scope_status": metadata.get("scope_status", "unknown_scope_incomplete"),
                "counts": metadata.get("counts", {}),
                "unknown_scopes": metadata.get("unknown_scopes", []),
                "findings": metadata.get("findings", []),
                "dependency_states": metadata.get("dependency_states", []),
            }, ensure_ascii=False, indent=2))
        elif args.command == "daemon":
            if not args.path:
                raise ValueError("daemon requires at least one explicit --path.")
            scan_args = ["--db", str(store.path), "map-device"]
            for path in args.path:
                scan_args.extend(["--path", path])
            scan_args.extend(["--max-files", str(args.max_files)])
            def scan() -> int:
                with contextlib.redirect_stdout(io.StringIO()):
                    return main(scan_args)
            try:
                return run_daemon(scan, interval_seconds=args.interval, once=args.once,
                                  emit=lambda message: print(message, file=sys.stderr))
            except KeyboardInterrupt:
                return 130
        elif args.command == "map-device":
            report = collect_device_map(args.path, max_files=args.max_files)
            # Explicit host and scope identity keeps imported graph history isolated.
            report["device_id"] = store.device_id()
            system = str((report.get("device") or {}).get("os") or sys.platform).casefold()
            environment = str((report.get("device") or {}).get("environment_class") or "")
            report["host_env"] = (
                "linux-termux" if "termux" in environment or "android" in system
                else "macos" if system == "darwin"
                else "windows" if system == "windows"
                else "linux" if system == "linux"
                else system
            )
            report["scope_path"] = sorted({
                str(Path(path).expanduser().resolve()) for path in args.path
            })
            report["observation_ts_ns"] = time.time_ns()
            fingerprint_payload = dict(report)
            fingerprint_payload.pop("captured_at", None)
            fingerprint_payload.pop("observation_ts_ns", None)
            # Observation timestamps order artifact history but must not make an
            # unchanged device snapshot look different on every scan.
            fingerprint_payload["artifacts"] = [
                {key: value for key, value in artifact.items() if key != "observed_at_ns"}
                for artifact in report.get("artifacts", [])
            ]
            fingerprint = hashlib.sha256(
                json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            report["fingerprint"] = fingerprint
            snapshots = store.list_all(kind="device_snapshot")
            scope_identity = (report["device_id"], report["host_env"], report["scope_path"])
            scoped_snapshots = [
                item for item in snapshots
                if (
                    (item.get("metadata") or {}).get("device_id", report["device_id"]),
                    (item.get("metadata") or {}).get("host_env", report["host_env"]),
                    (item.get("metadata") or {}).get("scope_path",
                        sorted(str(Path(path).expanduser().resolve()) for path in
                               ((item.get("metadata") or {}).get("scan") or {}).get("scope", []))),
                ) == scope_identity
            ]
            latest_snapshot = max(
                scoped_snapshots,
                key=lambda item: (
                    int((item.get("metadata") or {}).get("observation_ts_ns") or 0),
                    item.get("created_at", ""), item["id"],
                ),
                default=None,
            )
            if latest_snapshot and (latest_snapshot.get("metadata") or {}).get("fingerprint") == fingerprint:
                snapshot = latest_snapshot
            else:
                snapshot = store.add(
                    f"Device map: {report['device']['os']} {report['device']['os_release']} ({report['device']['architecture']})",
                    kind="device_snapshot",
                    source="mnemos-device-mapper",
                    metadata=report,
                )
            artifact_ids = []
            existing_artifact_ids = {}
            latest_artifact_by_path = {}
            for existing in store.list_all(kind="binary_artifact"):
                metadata = existing.get("metadata") or {}
                existing_path = str(metadata.get("path", "")).strip()
                existing_sha = metadata.get("sha256")
                if existing_path and existing_sha:
                    existing_artifact_ids[(existing_path, existing_sha)] = existing["id"]
                elif (
                    existing_path and metadata.get("sample_sha256")
                    and (metadata.get("binary_details") or {}).get("status") != "file_changed_during_inspection"
                ):
                    existing_artifact_ids[(
                        existing_path, None, "sample", metadata.get("sample_sha256"), metadata.get("size_bytes")
                    )] = existing["id"]
                elif (
                    existing_path
                    and metadata.get("mtime_ns") is not None
                    and metadata.get("size_bytes") is not None
                    and (metadata.get("binary_details") or {}).get("status") != "file_changed_during_inspection"
                ):
                    existing_artifact_ids[(
                        existing_path, None, metadata.get("mtime_ns"), metadata.get("size_bytes")
                    )] = existing["id"]
                if existing_path:
                    previous = latest_artifact_by_path.get(existing_path)
                    current_rank = (str(existing.get("created_at", "")), int(metadata.get("observed_at_ns") or 0), int(metadata.get("mtime_ns") or 0))
                    previous_metadata = (previous or {}).get("metadata") or {}
                    previous_rank = (str((previous or {}).get("created_at", "")), int(previous_metadata.get("observed_at_ns") or 0), int(previous_metadata.get("mtime_ns") or 0))
                    if previous is None or current_rank > previous_rank:
                        latest_artifact_by_path[existing_path] = existing
            artifact_records_created = 0
            for artifact in report["artifacts"]:
                artifact_path = str(artifact.get("path", ""))
                artifact_sha = artifact.get("sha256")
                if artifact_sha:
                    identity = (artifact_path, artifact_sha)
                elif artifact_path and artifact.get("sample_sha256") and (
                    artifact.get("binary_details") or {}
                ).get("status") != "file_changed_during_inspection":
                    identity = (
                        artifact_path, None, "sample", artifact.get("sample_sha256"), artifact.get("size_bytes")
                    )
                elif (
                    artifact_path
                    and artifact.get("mtime_ns") is not None
                    and artifact.get("size_bytes") is not None
                    and (artifact.get("binary_details") or {}).get("status") != "file_changed_during_inspection"
                ):
                    identity = (
                        artifact_path, None, artifact.get("mtime_ns"), artifact.get("size_bytes")
                    )
                else:
                    identity = None
                artifact_id = existing_artifact_ids.get(identity) if identity else None
                if artifact_id is None:
                    record = store.add(
                        f"Binary artifact: {artifact_path}",
                        kind="binary_artifact",
                        source="mnemos-device-mapper",
                        metadata=artifact,
                    )
                    artifact_id = record["id"]
                    artifact_records_created += 1
                    previous = latest_artifact_by_path.get(artifact_path)
                    if previous and previous.get("id") != artifact_id:
                        store.link(previous["id"], artifact_id, relation="superseded_by")
                    if identity:
                        existing_artifact_ids[identity] = artifact_id
                    latest_artifact_by_path[artifact_path] = record
                store.link(snapshot["id"], artifact_id, relation="contains_artifact")
                artifact_ids.append(artifact_id)
            evolution_report = evolve_graph(store)
            artifact_id_set = set(artifact_ids)
            scan_dependency_links = [
                link for link in store.links()
                if link["source_id"] in artifact_id_set and link["relation"] == "depends_on"
            ]
            dependency_record_ids = {link["target_id"] for link in scan_dependency_links}
            print(json.dumps({
                "snapshot_id": snapshot["id"],
                "graph_evolution": evolution_report,
                "artifact_records": len(artifact_ids),
                "artifact_records_created": artifact_records_created,
                "dependency_records": len(dependency_record_ids),
                "dependency_records_created": evolution_report["dependency_nodes_created"],
                "dependency_links": len(scan_dependency_links),
                "report": report,
            }, ensure_ascii=False, indent=2))
            if not evolution_report["ok"]:
                return 1
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
            if args.live:
                if args.format != "html":
                    raise ValueError("--live requires --format html.")
                from .live_graph import serve_live_graph
                return serve_live_graph(store, args.output, args.port)
            memories, links = store.list_all(), store.links()
            if args.format == "json":
                path = Path(args.output)
                path.parent.mkdir(parents=True, exist_ok=True)
                from .graph import graph_payload
                path.write_text(json.dumps(graph_payload(memories, links), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                path = render_graph(memories, links, args.output)
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
    except (ValueError, KeyError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"mnemos: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
