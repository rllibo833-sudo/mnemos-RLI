"""Command-line interface for the Mnemos local memory engine."""

import argparse
import contextlib
import hashlib
import io
import json
import re
import sqlite3
import sys
import time
from pathlib import Path, PurePosixPath

from .device_mapper import collect_device_map
from .analysis import analyze_graph
from .daemon import run_daemon
from .evolution import evolve_graph
from .graph import render_graph
from .live_graph import serve_live_graph
from .store import MemoryStore


_RELEASE_MANIFEST_SCHEMA = "mnemos-release-manifest-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _artifact_record_identity(path: str, artifact: dict) -> tuple | None:
    """Deduplicate identical observed states, not merely identical file contents."""
    details = artifact.get("binary_details")
    details = details if isinstance(details, dict) else {}
    if not path or details.get("status") == "file_changed_during_inspection":
        return None
    size, mtime, mode = artifact.get("size_bytes"), artifact.get("mtime_ns"), artifact.get("mode")
    signature, status = artifact.get("signature_status", "unknown"), details.get("status", "unknown")
    digest = artifact.get("sha256")
    if isinstance(digest, str) and len(digest) == 64:
        return ("full", path, digest, size, mtime, mode, signature, status)
    sample = artifact.get("sample_sha256")
    if isinstance(sample, str) and len(sample) == 64:
        return ("sample", path, sample, size, mtime, mode, signature, status)
    if mtime is not None and size is not None:
        return ("weak", path, mtime, size, mode, signature, status)
    return None


def _release_snapshot_artifacts(store: MemoryStore, snapshot: dict) -> list[dict]:
    """Return binary artifacts explicitly linked to one device snapshot."""
    by_id = {item["id"]: item for item in store.list_all()}
    artifact_ids = {
        link["target_id"] for link in store.links()
        if link.get("source_id") == snapshot["id"]
        and link.get("relation") == "contains_artifact"
    }
    return [
        by_id[item_id] for item_id in sorted(artifact_ids)
        if item_id in by_id and by_id[item_id].get("kind") == "binary_artifact"
    ]


def _release_roots(snapshot: dict) -> list[str]:
    metadata = snapshot.get("metadata") or {}
    raw = metadata.get("scope_path")
    if not isinstance(raw, list):
        raw = (metadata.get("scan") or {}).get("scope", [])
    roots = sorted({
        str(Path(item).expanduser().resolve())
        for item in raw if isinstance(item, str) and item.strip()
    })
    if len(roots) != 1:
        raise ValueError(
            "release manifests require a snapshot with exactly one explicit scan root; "
            "run map-device with one --path."
        )
    return roots


def _release_relative_path(artifact_path: str, root: str) -> str:
    artifact = Path(artifact_path).expanduser().resolve()
    scope = Path(root).expanduser().resolve()
    if artifact == scope:
        relative = artifact.name
    else:
        try:
            relative = artifact.relative_to(scope).as_posix()
        except ValueError as exc:
            raise ValueError(f"artifact path is outside the snapshot scan root: {artifact}") from exc
    normalized = PurePosixPath(relative)
    if normalized.is_absolute() or not normalized.parts or any(part in ("", ".", "..") for part in normalized.parts):
        raise ValueError(f"unsafe or invalid artifact-relative path: {relative}")
    return normalized.as_posix()


def _find_release_snapshot(store: MemoryStore, snapshot_id: str) -> dict:
    for item in store.list_all(kind="device_snapshot"):
        if item.get("id") == snapshot_id:
            return item
    raise ValueError(f"device snapshot not found: {snapshot_id}")


def _build_release_manifest(store: MemoryStore, snapshot_id: str, release_id: str) -> dict:
    release_id = release_id.strip()
    if not release_id:
        raise ValueError("release ID must not be empty.")
    snapshot = _find_release_snapshot(store, snapshot_id)
    metadata = snapshot.get("metadata") or {}
    scan = metadata.get("scan") or {}
    if scan.get("complete") is not True:
        raise ValueError("cannot create a release manifest from an incomplete device snapshot.")
    roots = _release_roots(snapshot)
    artifacts = _release_snapshot_artifacts(store, snapshot)
    if not artifacts:
        raise ValueError("snapshot contains no mapped binary artifacts.")
    entries = []
    seen_paths = set()
    for artifact in artifacts:
        item = artifact.get("metadata") or {}
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path:
            raise ValueError(f"artifact {artifact.get('id')} has no recorded path.")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError(
                f"artifact {path} has no full SHA-256; sampled fingerprints are not accepted in a release manifest."
            )
        relative = _release_relative_path(path, roots[0])
        if relative in seen_paths:
            raise ValueError(f"duplicate artifact-relative path in snapshot: {relative}")
        seen_paths.add(relative)
        entries.append({
            "path": relative,
            "sha256": digest,
            "size_bytes": item.get("size_bytes"),
            "format": item.get("format"),
        })
    entries.sort(key=lambda item: item["path"])
    return {
        "schema": _RELEASE_MANIFEST_SCHEMA,
        "release_id": release_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_snapshot_id": snapshot_id,
        "artifact_count": len(entries),
        "artifacts": entries,
    }


def _load_release_manifest(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != _RELEASE_MANIFEST_SCHEMA:
        raise ValueError(f"manifest schema must be {_RELEASE_MANIFEST_SCHEMA}.")
    release_id = payload.get("release_id")
    artifacts = payload.get("artifacts")
    if not isinstance(release_id, str) or not release_id.strip():
        raise ValueError("manifest release_id must be a non-empty string.")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("manifest artifacts must be a non-empty list.")
    normalized = []
    seen = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise ValueError(f"manifest artifact at index {index} must be an object.")
        path_value, digest = item.get("path"), item.get("sha256")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError(f"manifest artifact at index {index} has no path.")
        relative = PurePosixPath(path_value)
        if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            raise ValueError(f"manifest artifact path is not a safe relative path: {path_value}")
        path_value = relative.as_posix()
        if path_value in seen:
            raise ValueError(f"duplicate path in release manifest: {path_value}")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError(f"manifest artifact {path_value} must contain a lowercase full SHA-256.")
        seen.add(path_value)
        normalized.append({**item, "path": path_value, "sha256": digest})
    if payload.get("artifact_count") not in (None, len(normalized)):
        raise ValueError("manifest artifact_count does not match its artifacts list.")
    return {**payload, "artifacts": sorted(normalized, key=lambda item: item["path"])}


def _verify_release_manifest(store: MemoryStore, manifest: dict, snapshot_id: str) -> dict:
    snapshot = _find_release_snapshot(store, snapshot_id)
    metadata = snapshot.get("metadata") or {}
    scan = metadata.get("scan") or {}
    complete = scan.get("complete") is True
    roots = _release_roots(snapshot)
    actual_by_path = {}
    for record in _release_snapshot_artifacts(store, snapshot):
        item = record.get("metadata") or {}
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        relative = _release_relative_path(path, roots[0])
        if relative in actual_by_path:
            raise ValueError(f"snapshot has duplicate artifact-relative path: {relative}")
        actual_by_path[relative] = item

    expected = {item["path"]: item for item in manifest["artifacts"]}
    results = []
    for path, wanted in sorted(expected.items()):
        observed = actual_by_path.get(path)
        if observed is None:
            status = "missing" if complete else "unknown"
            observed_sha = None
        else:
            observed_sha = observed.get("sha256")
            if not isinstance(observed_sha, str) or not _SHA256_RE.fullmatch(observed_sha):
                status = "unknown"
            elif observed_sha == wanted["sha256"]:
                status = "match"
            else:
                status = "different"
        results.append({
            "path": path, "status": status,
            "expected_sha256": wanted["sha256"], "observed_sha256": observed_sha,
        })

    unexpected = []
    for path, observed in sorted(actual_by_path.items()):
        if path not in expected:
            unexpected.append({
                "path": path, "status": "unexpected",
                "observed_sha256": observed.get("sha256"),
            })

    statuses = {item["status"] for item in results}
    overall = (
        "different" if statuses.intersection({"different", "missing"}) or unexpected
        else "unknown" if "unknown" in statuses or not complete
        else "match"
    )
    return {
        "schema": "mnemos-release-verification-v1",
        "release_id": manifest["release_id"],
        "manifest_source_snapshot_id": manifest.get("source_snapshot_id"),
        "checked_snapshot_id": snapshot_id,
        "scan_complete": complete,
        "status": overall,
        "counts": {
            "expected": len(expected),
            "match": sum(item["status"] == "match" for item in results),
            "different": sum(item["status"] == "different" for item in results),
            "missing": sum(item["status"] == "missing" for item in results),
            "unknown": sum(item["status"] == "unknown" for item in results),
            "unexpected": len(unexpected),
        },
        "artifacts": results,
        "unexpected_artifacts": unexpected,
        "limitations": [
            "Manifest hashes identify exact bytes but do not authenticate who created the manifest.",
            "A partial scan cannot prove that an expected artifact is absent.",
            "Only binary artifacts detected by the device mapper are compared; this is not a full filesystem or vulnerability audit.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mnemos", description="Offline system integrity evidence, artifact comparison, and reconstruction.")
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
    mapping = commands.add_parser("map-device", help="Inventory this device offline; scan only explicitly supplied paths.")
    mapping.add_argument("--path", action="append", default=[], help="File or directory to inspect for binary artifacts; repeatable.")
    mapping.add_argument("--max-files", type=int, default=2000, help="Maximum files inspected across selected directories.")
    manifest = commands.add_parser("release-manifest", help="Create an offline expected-artifact manifest from a complete snapshot.")
    manifest.add_argument("--snapshot-id", required=True, help="Source device snapshot ID returned by map-device.")
    manifest.add_argument("--release-id", required=True, help="Human-readable trusted release identifier.")
    manifest.add_argument("--output", default="mnemos-release-manifest.json", help="Manifest output path.")
    verify = commands.add_parser("verify-release", help="Compare a snapshot against an expected-artifact manifest.")
    verify.add_argument("--manifest", required=True, help="Path to a mnemos-release-manifest-v1 JSON file.")
    verify.add_argument("--snapshot-id", required=True, help="Snapshot ID returned by map-device to verify.")
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
    live = commands.add_parser("live-graph", help="Serve local integrity evidence at /mnem?mode=damaged.")
    live.add_argument("--port", type=int, default=8765)
    live.add_argument("--output", help="Optional path to save a static copy of the viewer.")
    commands.add_parser("doctor", help="Check local SQLite integrity and relationship constraints.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = MemoryStore(args.db)
        if args.command == "init":
            print(f"Mnemos database ready: {store.path}")
        elif args.command == "release-manifest":
            manifest = _build_release_manifest(store, args.snapshot_id, args.release_id)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({
                "manifest": str(output.resolve()),
                "release_id": manifest["release_id"],
                "artifact_count": manifest["artifact_count"],
                "source_snapshot_id": manifest["source_snapshot_id"],
            }, ensure_ascii=False, indent=2))
        elif args.command == "verify-release":
            manifest = _load_release_manifest(args.manifest)
            report = _verify_release_manifest(store, manifest, args.snapshot_id)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["status"] == "match" else 1
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
        elif args.command == "live-graph":
            return serve_live_graph(store, args.output, args.port)
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
            for existing in store.list_all(kind="binary_artifact"):
                metadata = existing.get("metadata") or {}
                identity = _artifact_record_identity(str(metadata.get("path", "")).strip(), metadata)
                if identity:
                    existing_artifact_ids[identity] = existing["id"]
            artifact_records_created = 0
            for artifact in report["artifacts"]:
                artifact_path = str(artifact.get("path", ""))
                identity = _artifact_record_identity(artifact_path, artifact)
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
                    if identity:
                        existing_artifact_ids[identity] = artifact_id
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
        return 0
    except (ValueError, KeyError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"mnemos: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
