"""Restart-friendly polling loop for offline Mnemos device scans."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def run_daemon(
    scan: Callable[[], int],
    *,
    interval_seconds: float = 300,
    once: bool = False,
    stop_event: Any = None,
    emit: Callable[[str], None] = print,
) -> int:
    """Run complete scans repeatedly; a restart simply performs a fresh scan.

    Failures are reported and retried on the next interval. The caller owns
    scan scope and persistence, so this loop never needs network access or a
    separate queue that could drift away from the source files.
    """
    if interval_seconds <= 0:
        raise ValueError("Daemon interval must be greater than zero.")
    cycles = 0
    failures = 0
    while True:
        cycles += 1
        try:
            result = scan()
            if result == 0:
                emit(f"mnemos-daemon: scan {cycles} completed")
            else:
                failures += 1
                emit(f"mnemos-daemon: scan {cycles} failed with exit code {result}")
        except Exception as exc:  # Keep the daemon alive after an individual scan failure.
            failures += 1
            emit(f"mnemos-daemon: scan {cycles} failed: {type(exc).__name__}: {exc}")
            result = 1
        if once:
            return 0 if result == 0 else 1
        try:
            if stop_event is not None:
                if stop_event.wait(interval_seconds):
                    break
            else:
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            break
    emit(f"mnemos-daemon: stopped after {cycles} scans; failures={failures}")
    return 1 if failures else 0


class WatchdogEventBackend:
    """Bounded event adapter for watchdog's native or polling observers.

    The backend name describes the actual mechanism: FSEvents is reported only
    when the native macOS observer was successfully created. PollingObserver is
    explicitly labelled as a polling fallback and is not represented as FSEvents.
    """

    def __init__(self, paths: list[str], *, prefer_fsevents: bool = True, polling_timeout: float = 1.0):
        import threading
        from collections import deque
        from watchdog.events import FileSystemEventHandler

        self.errors: list[str] = []
        self._events = deque(maxlen=2000)
        self._lock = threading.Lock()
        self.event_monitor_type = None
        self._observer = None

        class Handler(FileSystemEventHandler):
            def on_any_event(inner_self, event):
                if getattr(event, "is_directory", False):
                    return
                src = getattr(event, "src_path", None)
                if not src:
                    return
                item = {
                    "timestamp": time.time(),
                    "path": str(src),
                    "event_type": str(getattr(event, "event_type", "filesystem_event")),
                    "source": self.event_monitor_type or "watchdog",
                }
                dest = getattr(event, "dest_path", None)
                if dest:
                    item["dest_path"] = str(dest)
                with self._lock:
                    self._events.append(item)

        handler = Handler()
        observer_errors = []
        if prefer_fsevents:
            try:
                from watchdog.observers.fsevents import FSEventsObserver
                observer = FSEventsObserver()
                for path in paths:
                    observer.schedule(handler, path, recursive=True)
                observer.start()
                self._observer = observer
                self.event_monitor_type = "fsevents"
            except Exception as exc:
                observer_errors.append(
                    f"native FSEvents unavailable: {type(exc).__name__}: {exc}"
                )
                if self._observer is not None:
                    try:
                        self._observer.stop()
                        self._observer.join(timeout=2)
                    except Exception:
                        pass
                    self._observer = None
        if self._observer is None:
            if __import__("os").name == "nt":
                # watchdog's default Observer selects ReadDirectoryChangesW on Windows.
                from watchdog.observers import Observer
                observer = Observer()
                self.event_monitor_type = "windows-read-directory-changes"
            else:
                from watchdog.observers.polling import PollingObserver
                observer = PollingObserver(timeout=max(0.1, float(polling_timeout)))
            scheduled = 0
            for path in paths:
                try:
                    observer.schedule(handler, path, recursive=True)
                    scheduled += 1
                except (OSError, ValueError) as exc:
                    observer_errors.append(f"cannot watch {path}: {type(exc).__name__}: {exc}")
            if not scheduled:
                raise OSError("No requested paths could be watched. " + "; ".join(observer_errors))
            observer.start()
            self._observer = observer
            self.event_monitor_type = "watchdog-polling"
            observer_errors.append(
                "Native FSEvents unavailable; watchdog PollingObserver is active and has higher latency."
                if prefer_fsevents else
                "watchdog PollingObserver explicitly selected; changes are detected on its polling cadence."
            )
        self.errors.extend(observer_errors)

    def drain_events(self) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    def close(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
