import tempfile
import unittest
from pathlib import Path

from mnemos.daemon import run_daemon
from mnemos.evolution import evolve_graph
from mnemos.store import MemoryStore


class GraphEvolutionTests(unittest.TestCase):
    def test_evolution_repairs_missing_history_edge_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            store = MemoryStore(Path(temp) / "memory.sqlite3")
            first = store.add("old binary", kind="binary_artifact", metadata={"path": "/opt/demo", "sha256": "a"})
            second = store.add("new binary", kind="binary_artifact", metadata={"path": "/opt/demo", "sha256": "b"})
            report = evolve_graph(store)
            self.assertTrue(report["ok"])
            self.assertEqual(report["supersession_edges_repaired"], 1)
            self.assertEqual(
                [link["relation"] for link in store.links(first["id"])],
                ["superseded_by"],
            )
            self.assertEqual(evolve_graph(store)["supersession_edges_repaired"], 0)
            self.assertEqual(next(link for link in store.links() if link["relation"] == "superseded_by")["target_id"], second["id"])

    def test_evolution_flags_dependency_edges_with_wrong_node_kinds(self):
        with tempfile.TemporaryDirectory() as temp:
            store = MemoryStore(Path(temp) / "memory.sqlite3")
            source = store.add("not a binary", kind="note")
            target = store.add("not a dependency", kind="note")
            store.link(source["id"], target["id"], relation="depends_on")
            report = evolve_graph(store)
            self.assertFalse(report["ok"])
            self.assertTrue(any(item["type"] == "invalid_dependency_edge" for item in report["violations"]))


class DaemonTests(unittest.TestCase):
    def test_once_runs_exactly_one_scan(self):
        calls = []
        logs = []
        result = run_daemon(lambda: calls.append("scan") or 0, once=True, emit=logs.append)
        self.assertEqual(result, 0)
        self.assertEqual(calls, ["scan"])
        self.assertEqual(len(logs), 1)

    def test_once_reports_scan_failure(self):
        logs = []
        result = run_daemon(lambda: 2, once=True, emit=logs.append)
        self.assertEqual(result, 1)
        self.assertIn("failed", logs[0])

    def test_invalid_interval_is_rejected(self):
        with self.assertRaises(ValueError):
            run_daemon(lambda: 0, interval_seconds=0, once=True)


if __name__ == "__main__":
    unittest.main()
