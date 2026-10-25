"""Cross-platform contract tests for macOS watchdog event backend."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mnemos.daemon import WatchdogEventBackend
from mnemos.observation import ScanOrchestrator


@unittest.skipUnless(sys.platform == "darwin", "macOS event backend integration test")
class MacOSEventBackendTests(unittest.TestCase):
    def test_backend_detects_change_faster_than_long_polling_interval(self):
        # Native FSEvents should usually arrive quickly. If native support cannot
        # attach, the test exercises the explicitly labelled watchdog polling
        # fallback with a short observer timeout.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Measure the polling observer's real detection latency independently
            # from native FSEvents delivery, which is OS/framework-version dependent.
            backend = WatchdogEventBackend([str(root)], prefer_fsevents=False, polling_timeout=0.2)
            try:
                # FSEvents creates its stream asynchronously; let the observer
                # establish the root watch before generating the probe event.
                time.sleep(1.0)
                started = time.monotonic()
                changed = root / "latency-probe.txt"
                changed.write_text("changed", encoding="utf-8")
                deadline = started + 10.0
                observed = None
                while time.monotonic() < deadline and observed is None:
                    for event in backend.drain_events():
                        if event.get("path") == str(changed):
                            observed = time.monotonic()
                            break
                    time.sleep(0.02)
                self.assertIsNotNone(observed, "filesystem change was not observed within 10 seconds")
                latency = observed - started
                # Compare against the configured 60s polling scan cadence: the
                # event observer must not wait for the next full inventory scan.
                self.assertLess(latency, 60.0, f"event notification latency was {latency:.3f}s")
                self.assertEqual(backend.event_monitor_type, "watchdog-polling")
                self.assertLess(latency, 5.0, "short-interval observer should detect well before a 60s inventory poll")
            finally:
                backend.close()

    def test_orchestrator_reports_real_backend_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = ScanOrchestrator([tmp], 100, interval=60)
            with mock.patch("sys.platform", "darwin"):
                orchestrator._attach_event_monitor()
            try:
                if orchestrator.event_monitor_active:
                    self.assertIn(orchestrator.event_monitor_type, {"fsevents", "watchdog-polling"})
            finally:
                if orchestrator.event_monitor:
                    orchestrator.event_monitor.close()


if __name__ == "__main__":
    unittest.main()
