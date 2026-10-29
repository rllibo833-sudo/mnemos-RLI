"""Command-line interface for the Mnemos local memory engine."""

import argparse
import contextlib
import hashlib
import io
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

from .device_mapper import collect_device_map
from .observation import Observation
from .analysis import analyze_graph
from .daemon import run_daemon
from .evolution import evolve_graph
from .graph import render_graph
from .live_graph import _evidence, serve_live_graph
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
    ctime = artifact.get("ctime_ns")
    file_type = artifact.get("file_type")
    ownership = (artifact.get("uid"), artifact.get("gid"))
    signature, status = artifact.get("signature_status", "unknown"), details.get("status", "unknown")
    digest = artifact.get("sha256")
    if isinstance(digest, str) and len(digest) == 64:
        return ("full", path, digest, size, mtime, ctime, mode, file_type, ownership, signature, status)
    sample = artifact.get("sample_sha256")
    if isinstance(sample, str) and len(sample) == 64:
        return ("sample", path, sample, size, mtime, ctime, mode, file_type, ownership, signature, status)
    if mtime is not None and size is not None:
        return ("weak", path, mtime, ctime, size, mode, file_type, ownership, signature, status)
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
        "source_device_id": metadata.get("device_id"),
        "source_host_env": metadata.get("host_env"),
        "source_scope": roots,
        "source_fingerprint": metadata.get("fingerprint"),
        "source_scan": {
            "complete": scan.get("complete") is True,
            "max_files": scan.get("max_files"),
            "examined_files": scan.get("examined_files"),
            "limit_reached": bool(scan.get("limit_reached")),
            "depth_limit_reached": bool(scan.get("depth_limit_reached")),
        },
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
    source_scan = payload.get("source_scan")
    if source_scan is not None:
        if not isinstance(source_scan, dict) or source_scan.get("complete") is not True:
            raise ValueError("manifest source_scan must describe a complete source snapshot.")
        for field in ("max_files", "examined_files"):
            value = source_scan.get(field)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"manifest source_scan {field} must be a non-negative integer.")
    source_scope = payload.get("source_scope")
    if source_scope is not None and (
        not isinstance(source_scope, list)
        or not source_scope
        or any(not isinstance(item, str) or not item.strip() for item in source_scope)
    ):
        raise ValueError("manifest source_scope must be a non-empty list of paths.")
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
        "source_device_id": manifest.get("source_device_id"),
        "source_host_env": manifest.get("source_host_env"),
        "source_scope": manifest.get("source_scope"),
        "source_fingerprint": manifest.get("source_fingerprint"),
        "source_scan": manifest.get("source_scan"),
        "checked_scope": roots,
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



def _terminal_graph(store: MemoryStore, refresh_seconds: float = 5.0) -> int:
    """Show a compact, read-only forensic dashboard in the current terminal."""
    if refresh_seconds <= 0:
        raise ValueError("--refresh must be greater than zero.")
    interactive = sys.stdout.isatty()
    width = max(48, min(shutil.get_terminal_size((80, 24)).columns, 110))

    def clip(value, limit):
        value = " ".join(str(value if value not in (None, "") else "—").split())
        return value if len(value) <= limit else value[:max(1, limit - 1)] + "…"

    def render(data):
        inventory = data.get("inventory") or {}
        graph_nodes = data.get("graph_nodes") or []
        graph_edges = data.get("graph_edges") or []
        snapshots = sorted(
            (node for node in graph_nodes if node.get("kind") == "device_snapshot"),
            key=lambda node: (node.get("observation_ts_ns") or 0, node.get("created_at") or ""),
        )
        findings = data.get("nodes") or []
        traces = data.get("traces") or []
        lines = [
            "MNEMOS-RLI | DIGITAL FORENSICS",
            "=" * min(width, 72),
            f"State: {data.get('status', 'UNKNOWN')}  |  Findings: {data.get('integrity_finding_count', 0)}"
            f"  |  Potential impacts: {data.get('dependency_impact_count', 0)}"
            f"  |  Unknown: {data.get('unknown_count', 0)}",
            f"Evidence: {inventory.get('snapshots', 0)} snapshots · "
            f"{inventory.get('binary_artifacts', 0)} artifacts · "
            f"{inventory.get('runtime_dependencies', 0)} dependencies",
            f"Relationships: {len(graph_edges)}  |  Compared artifacts: {data.get('compared_count', 0)}"
            f"  |  Scope: {clip(data.get('analysis_scope_status', 'unknown'), 28)}",
            "",
            "SNAPSHOT TIMELINE",
        ]
        if snapshots:
            for node in snapshots[-5:]:
                stamp = node.get("observed_at") or node.get("created_at") or "time unknown"
                scope = node.get("scope") or []
                scope_text = ", ".join(str(item) for item in scope) if isinstance(scope, list) else str(scope)
                flags = "complete" if node.get("scan_complete") else "incomplete/unscoped"
                lines.append(
                    f"  {clip(stamp, 19)}  {clip(node.get('id'), 12)}  [{flags}]"
                )
                if scope_text:
                    lines.append(f"    scope: {clip(scope_text, width - 10)}")
        else:
            lines.append("  No device snapshots recorded.")
        lines.extend(["", "INTEGRITY FINDINGS"])
        if findings:
            for item in findings[:8]:
                status = item.get("status") or item.get("report_status") or "UNKNOWN"
                path = item.get("path") or item.get("changed_path") or "(path unavailable)"
                reason = item.get("reason") or item.get("summary") or ""
                lines.append(f"  [{clip(status, 16)}] {clip(path, width - 22)}")
                if reason:
                    lines.append(f"    {clip(reason, width - 6)}")
        else:
            lines.append("  No comparison findings in the current view.")
        lines.extend(["", "DEPENDENCY IMPACT"])
        if traces:
            for trace in traces[:5]:
                lines.append(
                    f"  [POTENTIAL] {clip(trace.get('changed_path'), width - 14)}"
                )
                lines.append(
                    f"    dependency: {clip(trace.get('dependency_name'), width - 17)}"
                    f" | consumers: {len(trace.get('dependent_artifacts') or [])}"
                )
        else:
            lines.append("  No potential dependency-impact paths reported.")
        lines.extend(["", "KEY RELATIONSHIPS"])
        names = {
            node.get("id"): node.get("label") or node.get("path") or node.get("name") or node.get("id")
            for node in graph_nodes
        }
        useful_relations = {
            "observed_after", "contains_artifact", "depends_on",
            "current_observation", "baseline_observation", "integrity_status",
            "potential_impact",
        }
        shown = 0
        for edge in graph_edges:
            relation = edge.get("relation") or "relates_to"
            if relation not in useful_relations:
                continue
            source = names.get(edge.get("source_id"), edge.get("source_id"))
            target = names.get(edge.get("target_id"), edge.get("target_id"))
            marker = "~>" if edge.get("inferred") else "->"
            lines.append(
                f"  {clip(source, max(12, width // 3))} {marker} {clip(relation, 20)} "
                f"{marker} {clip(target, max(12, width // 3))}"
            )
            shown += 1
            if shown >= 10:
                break
        if not shown:
            lines.append("  No connected evidence relationships available yet.")
        lines.extend([
            "",
            clip(data.get("message") or "Read-only analysis; stored evidence is not modified.", width),
            f"Auto-refresh: {refresh_seconds:g}s  |  Ctrl+C to exit"
            if interactive else "Snapshot view (non-interactive terminal).",
        ])
        return "\n".join(clip(line, width) for line in lines)

    try:
        while True:
            data = _evidence(store, "damaged")
            if interactive:
                sys.stdout.write("\x1b[2J\x1b[H")
            print(render(data), flush=True)
            if not interactive:
                return 0
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        if interactive:
            print("\nMnemos dashboard stopped.")
        return 0
    except Exception as exc:
        print(f"Mnemos dashboard error: {exc}", file=sys.stderr)
        return 1


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
    mapping.add_argument("--war-mode", action="store_true", help="Hash every regular file in scope, bypass cache, and record war-mode coverage.")
    mapping.add_argument("--full-rehash", action="store_true", help="Recompute full hashes for recognized binaries without using the hash cache.")
    sign = commands.add_parser("sign-release", help="Sign a release manifest with cosign/Sigstore and emit a verification bundle.")
    sign.add_argument("--manifest", required=True, help="Manifest JSON to sign.")
    sign.add_argument("--bundle", required=True, help="Output Sigstore bundle path.")
    verify_sig = commands.add_parser("verify-release-signature", help="Verify a manifest Sigstore bundle against an expected signer identity.")
    verify_sig.add_argument("--manifest", required=True, help="Signed manifest JSON.")
    verify_sig.add_argument("--bundle", required=True, help="Sigstore bundle emitted by sign-release.")
    verify_sig.add_argument("--certificate-identity", required=True, help="Expected signer identity (email/workflow URI).")
    verify_sig.add_argument("--certificate-oidc-issuer", required=True, help="Expected OIDC issuer, e.g. https://github.com/login/oauth.")
    ledger_verify = commands.add_parser("verify-ledger", help="Verify the local append-only hash-chain and Ed25519 signatures.")
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
    forensic = commands.add_parser("forensics", help="Reconstruct a forensic case from stored offline evidence.")
    forensic.add_argument("--path", action="append", default=[], help="Restrict to snapshots with this exact scan scope; repeatable.")
    forensic.add_argument("--asset", help="Trace a specific asset path or evidence ID.")
    forensic.add_argument("--timeline", action="store_true", help="Include the asset observation-to-finding timeline.")
    forensic.add_argument("--format", choices=("json", "html"), default="json", help="Output forensic JSON or a self-contained HTML timeline.")
    forensic.add_argument("--output", help="Output file for HTML (default: ~/.mnemos/reports/mnemos-timeline.html).")
    daemon = commands.add_parser("daemon", help="Continuously refresh an offline device map for explicitly selected paths.")
    daemon.add_argument("--path", action="append", default=[], help="File or directory to scan; repeatable.")
    daemon.add_argument("--max-files", type=int, default=2000, help="Maximum files inspected per scan.")
    daemon.add_argument("--war-mode", action="store_true", help="Hash all regular files and bypass the hash cache on every daemon scan.")
    daemon.add_argument("--full-rehash", action="store_true", help="Recompute full hashes for recognized binaries on every daemon scan.")
    daemon.add_argument("--interval", type=float, default=300, help="Seconds between full scans (default: 300).")
    daemon.add_argument("--once", action="store_true", help="Run one scan and exit.")
    daemon.add_argument("--enable-service", action="store_true", help="Register this exact daemon command as a user-level service and enable it.")
    daemon.add_argument("--disable-service", action="store_true", help="Stop, disable, and remove the user-level startup service.")
    daemon.add_argument("--service-status", action="store_true", help="Audit startup service registration without changing it.")
    daemon.add_argument("--status-port", type=int, default=8080, help="Loopback monitoring API port (default: 8080).")
    daemon.add_argument("--no-status-server", action="store_true", help="Do not start the read-only monitoring API alongside the daemon.")
    live = commands.add_parser("live-graph", help="Show the live forensic evidence dashboard in the terminal.")
    live.add_argument("--refresh", type=float, default=5.0, help="Terminal refresh interval in seconds (default: 5).")
    live.add_argument("--web", action="store_true", help="Use the optional browser-based graph viewer.")
    live.add_argument("--port", type=int, default=8765, help="Loopback port for --web (default: 8765).")
    live.add_argument("--output", help="Optional path to save a static browser viewer when using --web.")
    commands.add_parser("doctor", help="Check local SQLite integrity and relationship constraints.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = MemoryStore(args.db)
        if args.command == "init":
            print(f"Mnemos database ready: {store.path}")
        elif args.command == "sign-release":
            try:
                result = subprocess.run(
                    ["cosign", "sign-blob", "--yes", "--bundle", args.bundle, args.manifest],
                    check=False, capture_output=True, text=True,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("cosign is required for Sigstore signing; install cosign and authenticate with a supported OIDC identity.") from exc
            if result.returncode:
                raise RuntimeError(f"cosign sign-blob failed: {result.stderr.strip()}")
            print(json.dumps({"status": "signed", "manifest": str(Path(args.manifest).resolve()),
                              "bundle": str(Path(args.bundle).resolve()), "tool": "cosign"}, indent=2))
        elif args.command == "verify-release-signature":
            try:
                result = subprocess.run(
                    ["cosign", "verify-blob", "--bundle", args.bundle,
                     "--certificate-identity", args.certificate_identity,
                     "--certificate-oidc-issuer", args.certificate_oidc_issuer, args.manifest],
                    check=False, capture_output=True, text=True,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("cosign is required for Sigstore verification.") from exc
            if result.returncode:
                print(json.dumps({"status": "invalid", "stderr": result.stderr.strip()}, indent=2))
                return 1
            print(json.dumps({"status": "verified", "manifest": str(Path(args.manifest).resolve()),
                              "bundle": str(Path(args.bundle).resolve()), "identity": args.certificate_identity,
                              "oidc_issuer": args.certificate_oidc_issuer}, indent=2))
        elif args.command == "verify-ledger":
            from .evidence_ledger import verify_ledger
            report = verify_ledger()
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
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
        elif args.command == "forensics":
            from .forensics import reconstruct_case
            report = reconstruct_case(store, paths=args.path or None)
            if args.asset and args.timeline:
                from .observation import trace_execution_path
                report["execution_trace"] = trace_execution_path(store, args.asset)
            if args.format == "html":
                import webbrowser
                from .forensics import render_timeline_html
                output = Path(args.output).expanduser() if args.output else (Path.home() / ".mnemos" / "reports" / "mnemos-timeline.html")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(render_timeline_html(report, asset=args.asset), encoding="utf-8")
                print(json.dumps({"format": "html", "output": str(output.resolve()), "events": sum(len(group.get("observations", [])) for group in report.get("timelines", [])) + len(report.get("integrity_findings", [])) + len((report.get("execution_trace") or {}).get("timeline", []))}, ensure_ascii=False, indent=2))
                try:
                    webbrowser.open(output.resolve().as_uri())
                except (OSError, RuntimeError):
                    pass
            else:
                print(json.dumps(report, ensure_ascii=False, indent=2))
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
            if not args.path and not (args.service_status or args.disable_service):
                raise ValueError("daemon requires at least one explicit --path, except for service management.")
            if args.max_files < 1 or args.interval <= 0:
                raise ValueError("--max-files and --interval must be positive.")
            from .observation import (
                ScanOrchestrator, check_service_registration,
                disable_service_registration, enable_service_registration,
            )
            if args.service_status:
                print(json.dumps(check_service_registration(), ensure_ascii=False, indent=2))
                return 0
            if args.disable_service:
                service = disable_service_registration()
                status = check_service_registration()
                print(json.dumps({"service": service, "status": status}, ensure_ascii=False, indent=2))
                return 0 if not status["service_enabled"] else 1
            if args.enable_service:
                # Register the daemon command without the one-shot install flags.
                original_argv = sys.argv[:]
                try:
                    sys.argv = ["--db", str(store.path), "daemon"]
                    for path in args.path:
                        sys.argv.extend(["--path", path])
                    sys.argv.extend(["--max-files", str(args.max_files), "--interval", str(args.interval)])
                    if args.war_mode:
                        sys.argv.append("--war-mode")
                    if args.full_rehash:
                        sys.argv.append("--full-rehash")
                    service = enable_service_registration()
                finally:
                    sys.argv = original_argv
                print(json.dumps({"service": service, "status": check_service_registration()}, indent=2))
                return 0
            scan_args = ["--db", str(store.path), "map-device"]
            for path in args.path:
                scan_args.extend(["--path", path])
            scan_args.extend(["--max-files", str(args.max_files)])
            if args.war_mode:
                scan_args.append("--war-mode")
            if args.full_rehash:
                scan_args.append("--full-rehash")
            def scan() -> int:
                with contextlib.redirect_stdout(io.StringIO()):
                    return main(scan_args)
            orchestrator = ScanOrchestrator(args.path, args.max_files, args.interval, store=store, scan_callback=scan)
            orchestrator.once = bool(args.once)
            status_server = None
            if not args.no_status_server:
                from .live_graph import start_live_graph_server
                try:
                    status_server, _status_thread = start_live_graph_server(store, port=args.status_port)
                    print(f"mnemos-daemon: monitoring API http://127.0.0.1:{args.status_port}/api/monitoring-status", file=sys.stderr)
                except OSError as exc:
                    print(f"mnemos-daemon: monitoring API unavailable: {exc}", file=sys.stderr)
            status = orchestrator.start_monitoring()
            store.update_monitoring_runtime(status="running", paths=orchestrator.paths,
                interval_seconds=args.interval, event_monitor_active=orchestrator.event_monitor_active,
                event_monitor_type=orchestrator.event_monitor_type, event_monitor_errors=orchestrator.event_monitor_errors,
                pid=__import__("os").getpid())
            print(json.dumps({"status": "running", **status}, ensure_ascii=False), file=sys.stderr)
            try:
                if args.once:
                    # The worker performs the initial scan immediately.
                    orchestrator._thread.join()
                else:
                    while orchestrator._thread and orchestrator._thread.is_alive():
                        orchestrator._thread.join(timeout=1.0)
                return 0
            except KeyboardInterrupt:
                return 130
            finally:
                orchestrator.stop_monitoring()
                if status_server is not None:
                    status_server.shutdown()
                    status_server.server_close()
                store.update_monitoring_runtime(status="stopped", paths=orchestrator.paths,
                    interval_seconds=args.interval, event_monitor_active=False,
                    event_monitor_type=None, event_monitor_errors=orchestrator.event_monitor_errors,
                    pid=None)
        elif args.command == "live-graph":
            if args.web:
                return serve_live_graph(store, args.output, args.port)
            return _terminal_graph(store, args.refresh)
        elif args.command == "map-device":
            if not args.path:
                raise ValueError(
                    "map-device requires at least one explicit --path; refusing to save an empty-scope snapshot. "
                    "Use --path /data/data/com.termux/files/usr/bin (or another directory you intend to inspect)."
                )
            if args.max_files < 1:
                raise ValueError("--max-files must be a positive integer.")
            report = collect_device_map(args.path, max_files=args.max_files, war_mode=args.war_mode, full_rehash=args.full_rehash)
            if report.get("scan", {}).get("scope_missing") or not report.get("scan", {}).get("scope"):
                raise ValueError("device map has no valid scan scope; no snapshot was saved.")
            # Bind each snapshot identity to this database and its observed host
            # fingerprint. A copied SQLite file must not silently merge histories
            # from differently named hosts into one device timeline.
            device_meta = report.get("device") or {}
            system = str(device_meta.get("os") or sys.platform).casefold()
            environment = str(device_meta.get("environment_class") or device_meta.get("os_type") or "")
            report["host_env"] = (
                "linux-termux" if "termux" in environment or "android" in system
                else "macos" if system == "darwin"
                else "windows" if system.startswith("win")
                else "linux" if system.startswith("linux")
                else str(device_meta.get("os_type") or system)
            )
            host_identity = {
                "hostname": str(device_meta.get("hostname") or ""),
                "os": system,
                "os_release": str(device_meta.get("os_release") or ""),
                "architecture": str(device_meta.get("architecture") or ""),
                "environment": environment,
            }
            host_fingerprint = hashlib.sha256(
                json.dumps(host_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16]
            report["device_id"] = f"{store.device_id()}@{host_fingerprint}"
            report["host_identity_method"] = "database-and-host-fingerprint-v1"
            report["scope_path"] = sorted({
                str(Path(path).expanduser().resolve()) for path in args.path
            })
            report["scan"]["scope"] = report["scope_path"]
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
            observation = Observation.from_scan(report, paths=report["scope_path"], max_files=args.max_files)
            store.save_observation(observation.to_dict(), snapshot_id=snapshot["id"])
            from .evidence_ledger import append_observation
            ledger_entry = append_observation(
                observation.to_dict(), snapshot_id=snapshot["id"], war_mode=bool(args.war_mode),
                snapshot_fingerprint=fingerprint, artifacts=report.get("artifacts", []),
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
            # Persist deterministic integrity findings and evidence-based risk assessments.
            from .integrity import compare_snapshot_histories
            from .observation import assess_risk
            all_records = store.list_all()
            by_id = {item.get("id"): item for item in all_records if isinstance(item.get("id"), str)}
            histories = compare_snapshot_histories(
                [item for item in all_records if item.get("kind") == "device_snapshot"], store.links(), by_id
            )
            for history in histories:
                for node in history.get("nodes", []):
                    if node.get("current_snapshot_id") != snapshot["id"]:
                        continue
                    status = str(node.get("status") or "UNKNOWN")
                    if status in {"UNCHANGED", "MATCH", "PRESENT", "BASELINE_ONLY"}:
                        continue
                    asset_path = str(node.get("path") or "")
                    if not asset_path:
                        continue
                    baseline_id = node.get("baseline_snapshot_id")
                    current_id = node.get("current_snapshot_id")
                    obs_a = store.observation_for_snapshot(baseline_id) if baseline_id else None
                    obs_b = store.observation_for_snapshot(current_id) if current_id else None
                    same_scope = bool(
                        obs_a and obs_b and sorted(obs_a.get("paths", [])) == sorted(obs_b.get("paths", []))
                    )
                    confidence = "high" if same_scope and obs_a.get("coverage_complete") and obs_b.get("coverage_complete") else (
                        "low" if obs_a or obs_b else "unknown"
                    )
                    kind_map = {
                        "HASH_MISMATCH": "hash_mismatch", "MISSING": "missing",
                        "NEW_FILE": "new", "UNKNOWN": "unobserved", "INCOMPLETE_SCAN": "unobserved",
                        "SAMPLED_MISMATCH": "sampled_mismatch", "SIZE_CHANGE": "metadata_change",
                        "PERM_CHANGE": "metadata_change", "OWNER_CHANGE": "metadata_change",
                        "FILE_TYPE_CHANGE": "metadata_change",
                    }
                    finding_id = hashlib.sha256(
                        f"{current_id}\0{asset_path}\0{status}".encode("utf-8")
                    ).hexdigest()
                    finding = {
                        "id": finding_id, "asset_id": asset_path, "finding_type": kind_map.get(status, "unobserved"),
                        "confidence": confidence, "reason": str(node.get("reason") or status),
                        "observation_a_id": (obs_a or {}).get("id"), "observation_b_id": (obs_b or {}).get("id"),
                        "snapshot_a_id": baseline_id, "snapshot_b_id": current_id,
                        "hash_before": node.get("expected_sha256"), "hash_after": node.get("observed_sha256"),
                        "timestamp": time.time(),
                    }
                    store.save_integrity_finding(finding)
                    artifact_id = node.get("artifact_id")
                    dependency_map = {}
                    if artifact_id:
                        dependency_map[asset_path] = [
                            str((by_id.get(link.get("target_id")) or {}).get("content") or
                                (((by_id.get(link.get("target_id")) or {}).get("metadata") or {}).get("name")) or
                                link.get("target_id"))
                            for link in store.links()
                            if link.get("source_id") == artifact_id and link.get("relation") == "depends_on"
                        ]
                    assessment = assess_risk(finding, obs_a, obs_b, dependency_map).to_dict()
                    store.save_risk_assessment(assessment)
                    if assessment["risk_level"] in {"critical", "high", "medium"}:
                        store.save_alert({
                            "finding_id": finding_id, "severity": "critical" if assessment["risk_level"] == "critical" else "warning",
                            "reason": assessment["reasoning"], "timestamp": time.time(),
                        })
            artifact_id_set = set(artifact_ids)
            scan_dependency_links = [
                link for link in store.links()
                if link["source_id"] in artifact_id_set and link["relation"] == "depends_on"
            ]
            dependency_record_ids = {link["target_id"] for link in scan_dependency_links}
            print(json.dumps({
                "snapshot_id": snapshot["id"],
                "evidence_ledger": ledger_entry,
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
            from .observation import check_service_registration
            # A background service is optional. Its absence must not make the
            # local database diagnostic fail for users who only want one-shot
            # scans or interactive CLI commands.
            report["service"] = check_service_registration()
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
