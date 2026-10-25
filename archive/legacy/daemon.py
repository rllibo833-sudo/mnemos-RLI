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
