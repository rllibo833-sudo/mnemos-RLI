import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from mnemos.analysis import analyze_graph
from mnemos.cli import main
from mnemos.store import MemoryStore


def snapshot(store, scope, complete=True, fingerprint=None):
    item = store.add(
        "test snapshot", kind="device_snapshot", source="test",
        metadata={"fingerprint": fingerprint or ("f" * 64),
                  "scan": {"scope": [scope], "complete": complete}, "artifacts": []},
    )
    created_at = "2026-01-01T00:00:00+00:00" if fingerprint == "1" * 64 else (
        "2026-02-01T00:00:00+00:00" if fingerprint == "2" * 64 else item["created_at"]
    )
    with store._connect() as db:
        db.execute("UPDATE memories SET created_at = ? WHERE id = ?", (created_at, item["id"]))
    return store.get(item["id"])


def artifact(store, path, digest, deps=(), *, status="parsed", observed=1, sample=None):
    details = {"status": status, "format": "ELF", "analysis_limits": [],
               "dependencies": [{"name": name, "kind": "needed"} for name in deps]}
    return store.add(
        f"artifact {path}", kind="binary_artifact", source="test",
        metadata={"path": path, "sha256": digest, "sample_sha256": sample,
                  "size_bytes": 128, "mtime_ns": observed, "observed_at_ns": observed,
                  "binary_details": details},
    )


def add_to_snapshot(store, snap, item):
    store.link(snap["id"], item["id"], relation="contains_artifact")


def link_dependencies(store, item, names):
    for name in names:
        dep = next((record for record in store.list_all(kind="runtime_dependency")
                    if record["metadata"].get("name") == name), None)
        if dep is None:
            dep = store.add(
                f"Runtime dependency: {name}", kind="runtime_dependency",
                metadata={"schema": "mnemos-dependency-evidence-v1", "name": name,
                          "format": "ELF", "kind": "needed", "kinds": ["needed"],
                          "evidence_sources": []},
            )
        store.link(item["id"], dep["id"], relation="depends_on")


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.temp.name) / "memory.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_critical_dependency_uses_active_artifact_count_and_provenance(self):
        scope = "/prefix/bin"
        snap = snapshot(self.store, scope)
        for index in range(3):
            item = artifact(self.store, f"/prefix/bin/app{index}", f"{index + 1:064x}", ["libshared.so"])
            add_to_snapshot(self.store, snap, item)
            link_dependencies(self.store, item, ["libshared.so"])
        result, created = analyze_graph(self.store, paths=[scope], critical_threshold=2)
        self.assertTrue(created)
        finding = next(item for item in result["metadata"]["findings"] if item["rule_id"] == "critical_dependency")
        self.assertEqual(finding["evidence"]["artifact_count"], 3)
        self.assertEqual(finding["evidence"]["artifacts"][0]["snapshot_ids"], [snap["id"]])

    def test_missing_dependency_requires_same_complete_scope(self):
        scope = "/prefix/bin"
        previous = snapshot(self.store, scope, fingerprint="1" * 64)
        old = artifact(self.store, "/prefix/bin/old", "a" * 64, ["libgone.so"])
        add_to_snapshot(self.store, previous, old)
        link_dependencies(self.store, old, ["libgone.so"])
        current = snapshot(self.store, scope, fingerprint="2" * 64)
        new = artifact(self.store, "/prefix/bin/new", "b" * 64, [])
        add_to_snapshot(self.store, current, new)
        result, _ = analyze_graph(self.store, paths=[scope])
        missing = [item for item in result["metadata"]["findings"] if item["rule_id"] == "missing_dependency"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["evidence"]["status"], "proven_absent")
        self.assertEqual(missing[0]["evidence"]["previous_snapshot_id"], previous["id"])
        self.assertEqual(missing[0]["evidence"]["current_snapshot_id"], current["id"])

    def test_incomplete_scope_is_unknown_not_missing(self):
        scope = "/prefix/bin"
        previous = snapshot(self.store, scope, fingerprint="1" * 64)
        old = artifact(self.store, "/prefix/bin/old", "a" * 64, ["libgone.so"])
        add_to_snapshot(self.store, previous, old)
        link_dependencies(self.store, old, ["libgone.so"])
        snapshot(self.store, scope, complete=False, fingerprint="2" * 64)
        result, _ = analyze_graph(self.store, paths=[scope])
        self.assertFalse(any(item["rule_id"] == "missing_dependency" for item in result["metadata"]["findings"]))
        self.assertEqual(result["metadata"]["unknown_scopes"][0]["reason"], "scope_incomplete")

    def test_failed_current_parser_is_unknown_not_missing(self):
        scope = "/prefix/bin"
        previous = snapshot(self.store, scope, fingerprint="1" * 64)
        old = artifact(self.store, "/prefix/bin/old", "a" * 64, ["libgone.so"])
        add_to_snapshot(self.store, previous, old)
        link_dependencies(self.store, old, ["libgone.so"])
        current = snapshot(self.store, scope, fingerprint="2" * 64)
        invalid = artifact(self.store, "/prefix/bin/broken", "b" * 64, [], status="invalid_elf_header")
        add_to_snapshot(self.store, current, invalid)
        result, _ = analyze_graph(self.store, paths=[scope])
        self.assertFalse(any(item["rule_id"] == "missing_dependency" for item in result["metadata"]["findings"]))
        self.assertEqual(result["metadata"]["unknown_scopes"][0]["reason"], "failed_validation")
        self.assertTrue(any(item["rule_id"] == "failed_validation" for item in result["metadata"]["findings"]))

    def test_analysis_is_idempotent_and_enqueues_only_once(self):
        scope = "/prefix/bin"
        snapshot(self.store, scope)
        first, created1 = analyze_graph(self.store, paths=[scope])
        second, created2 = analyze_graph(self.store, paths=[scope])
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.list_all(kind="analysis_result")), 1)
        queued = [item for item in self.store.pending_changes()
                  if item["entity_type"] == "memory" and item["payload"].get("kind") == "analysis_result"]
        self.assertEqual(len(queued), 1)

    def test_sampled_only_identity_is_explicit(self):
        scope = "/prefix/bin"
        snap = snapshot(self.store, scope)
        item = artifact(self.store, "/prefix/bin/large", None, sample="sampled" * 8)
        add_to_snapshot(self.store, snap, item)
        result, _ = analyze_graph(self.store, paths=[scope])
        finding = next(item for item in result["metadata"]["findings"] if item["rule_id"] == "sampled_only_risk")
        self.assertEqual(finding["evidence"]["identity"]["kind"], "sampled_fingerprint")

    def test_analysis_normalizes_relative_and_dotdot_scope_paths(self):
        scope = Path(self.temp.name) / "prefix" / "bin"
        scope.mkdir(parents=True)
        snapshot(self.store, str(scope))
        alias = scope.parent / "unused" / ".." / scope.name
        result, created = analyze_graph(self.store, paths=[str(alias)])
        self.assertTrue(created)
        self.assertEqual(result["metadata"]["scope_status"], "known")
        self.assertEqual(result["metadata"]["source_snapshot_ids"], [
            item["id"] for item in self.store.list_all(kind="device_snapshot")
        ])

    def test_empty_graph_reports_unknown_scope(self):
        result, _ = analyze_graph(self.store)
        self.assertEqual(result["metadata"]["scope_status"], "unknown_scope_incomplete")
        self.assertEqual(result["metadata"]["unknown_scopes"][0]["reason"], "no_snapshot_for_scope")

    def test_cli_analyze_prints_traceable_result(self):
        scope = "/prefix/bin"
        snapshot(self.store, scope)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--db", str(self.store.path), "analyze", "--path", scope])
        self.assertEqual(code, 0)
        self.assertIn("source_snapshot_ids", output.getvalue())
        self.assertIn("unknown_scopes", output.getvalue())


if __name__ == "__main__":
    unittest.main()
