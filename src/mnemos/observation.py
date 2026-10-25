"""Persisted scan coverage and conservative asset timeline reconstruction."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import time
import uuid


@dataclass
class Observation:
    """One scan episode; completeness is distinct from whether findings were found."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    scan_type: str = "filesystem_scan"
    paths: list[str] = field(default_factory=list)
    max_files: int = 0
    files_attempted: int = 0
    files_scanned: int = 0
    files_failed: int = 0
    dirs_failed: list[str] = field(default_factory=list)
    hit_max_files_limit: bool = False
    truncated_due_to: str | None = None
    event_monitor_active: bool = False
    event_monitor_type: str | None = None
    event_monitor_errors: list[str] = field(default_factory=lambda: ["No OS event backend is configured; periodic scans only."])
    coverage_complete: bool = False
    confidence_level: str = "unknown"

    @classmethod
    def from_scan(cls, report: dict[str, Any], *, paths: list[str], max_files: int) -> "Observation":
        scan = report.get("scan") if isinstance(report.get("scan"), dict) else {}
        errors = scan.get("traversal_errors") if isinstance(scan.get("traversal_errors"), list) else []
        dirs_failed = sorted({
            str(item.get("path") or "<unknown-path>")
            for item in errors if isinstance(item, dict)
        })
        hit_limit = bool(scan.get("limit_reached"))
        files_attempted = max(0, int(scan.get("examined_files") or 0))
        file_errors = scan.get("file_errors") if isinstance(scan.get("file_errors"), list) else []
        files_failed = len(file_errors)
        files_scanned = max(0, files_attempted - files_failed)
        complete = (
            scan.get("complete") is True and files_failed == 0 and not dirs_failed
            and not hit_limit and not scan.get("depth_limit_reached")
            and not scan.get("skipped_symlink_roots")
        )
        confidence = "high" if complete else ("medium" if files_scanned and not hit_limit else "low")
        return cls(
            timestamp=time.time(), paths=list(paths), max_files=int(max_files),
            files_attempted=files_attempted, files_scanned=files_scanned,
            files_failed=files_failed, dirs_failed=dirs_failed,
            hit_max_files_limit=hit_limit,
            truncated_due_to="max_files" if hit_limit else
                "permission_denied" if dirs_failed or files_failed else None,
            coverage_complete=complete, confidence_level=confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def trace_execution_path(store, asset_id: str, time_range: tuple[float, float] | None = None) -> dict[str, Any]:
    """Reconstruct an asset timeline from persisted observation, finding, risk, and alert records."""
    start_ts, end_ts = time_range or (0.0, time.time())
    memories = store.list_all()
    matches = []
    for item in memories:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if item.get("id") == asset_id or meta.get("path") == asset_id:
            matches.append(item)
    asset = matches[0] if matches else None
    asset_path = str(((asset or {}).get("metadata") or {}).get("path") or asset_id)
    observations = list(reversed(store.observations(limit=10000)))
    timeline: list[dict[str, Any]] = []
    relevant = []
    candidate = Path(asset_path).expanduser()
    for observation in observations:
        ts = float(observation.get("timestamp") or 0)
        if not start_ts <= ts <= end_ts:
            continue
        in_scope = False
        for root in observation.get("paths", []) if isinstance(observation.get("paths"), list) else []:
            try:
                resolved_root = Path(root).expanduser().resolve()
                resolved_asset = candidate.resolve()
                if resolved_asset == resolved_root or resolved_root in resolved_asset.parents:
                    in_scope = True
                    break
            except (OSError, RuntimeError):
                continue
        if not in_scope:
            continue
        relevant.append(observation)
        timeline.append({
            "timestamp": ts, "event": "observation", "observation_id": observation.get("id"),
            "scope": observation.get("paths", []),
            "coverage_complete": bool(observation.get("coverage_complete")),
            "confidence": observation.get("confidence_level", "unknown"),
            "files_attempted": observation.get("files_attempted", 0),
            "files_scanned": observation.get("files_scanned", 0),
            "files_failed": observation.get("files_failed", 0),
            "dirs_failed": observation.get("dirs_failed", []),
            "reason": observation.get("truncated_due_to"),
        })
    for event in (store.device_events(limit=10000) if hasattr(store, "device_events") else []):
        ts = float(event.get("timestamp") or 0)
        if not start_ts <= ts <= end_ts:
            continue
        if str(event.get("path") or "") != asset_path:
            continue
        timeline.append({
            "timestamp": ts, "event": "filesystem_event", "event_id": event.get("id"),
            "event_type": event.get("event_type"), "path": event.get("path"),
            "source": event.get("source"), "evidence": "OS filesystem event; content integrity is not implied.",
        })
    findings = store.integrity_findings(asset_id=asset_path, limit=10000)
    if asset and asset.get("id") != asset_path:
        findings += store.integrity_findings(asset_id=str(asset.get("id")), limit=10000)
    risks = {item.get("finding_id"): item for item in store.risk_assessments(limit=10000)}
    alerts = {item.get("finding_id"): item for item in store.alerts(limit=10000)} if hasattr(store, "alerts") else {}
    for finding in findings:
        ts = float(finding.get("timestamp") or 0)
        if not start_ts <= ts <= end_ts:
            continue
        timeline.append({
            "timestamp": ts, "event": "integrity_finding", "finding_id": finding.get("id"),
            "finding_type": finding.get("finding_type"), "confidence": finding.get("confidence"),
            "reason": finding.get("reason"), "hash_before": finding.get("hash_before"),
            "hash_after": finding.get("hash_after"), "observation_a_id": finding.get("observation_a_id"),
            "observation_b_id": finding.get("observation_b_id"),
        })
        risk = risks.get(finding.get("id"))
        if risk:
            risk_ts = float(risk.get("timestamp") or ts)
            if start_ts <= risk_ts <= end_ts:
                timeline.append({
                    "timestamp": risk_ts, "event": "risk_assessment", "finding_id": finding.get("id"),
                    "risk_level": risk.get("risk_level"), "confidence": risk.get("confidence"),
                    "reasoning": risk.get("reasoning"), "unobserved_scope": risk.get("unobserved_scope"),
                })
        alert = alerts.get(finding.get("id"))
        if alert:
            alert_ts = float(alert.get("timestamp") or ts)
            if start_ts <= alert_ts <= end_ts:
                timeline.append({
                    "timestamp": alert_ts, "event": "alert_generated", "alert_id": alert.get("id"),
                    "finding_id": finding.get("id"), "severity": alert.get("severity"),
                    "reason": alert.get("reason"),
                })
    unobserved_gaps = []
    runtime = store.monitoring_runtime() if hasattr(store, "monitoring_runtime") else None
    interval = float((runtime or {}).get("interval_seconds") or 0)
    for index, observation in enumerate(relevant):
        if observation.get("event_monitor_active"):
            continue
        ts = float(observation.get("timestamp") or 0)
        next_ts = float(relevant[index + 1].get("timestamp") or end_ts) if index + 1 < len(relevant) else min(end_ts, ts + interval if interval else end_ts)
        if next_ts < ts:
            next_ts = ts
        reason = "; ".join(observation.get("event_monitor_errors") or [])
        if not reason:
            reason = "No event monitor was active; changes between polling scans may be missed."
        unobserved_gaps.append({"period": [ts, min(end_ts, next_ts)], "reason": reason})
    timeline.sort(key=lambda item: (item["timestamp"], item["event"], str(item.get("finding_id") or "")))
    return {
        "asset": {"id": (asset or {}).get("id"), "path": asset_path, "found_in_store": asset is not None},
        "timeline": timeline, "unobserved_gaps": unobserved_gaps,
        "limitations": [
            "Timeline entries are read from persisted evidence; absent entries are not inferred as events.",
            "OS event monitoring is platform-dependent; unavailable backends are recorded and polling remains the fallback.",
            "A missing timeline entry does not establish that an asset was unchanged or safe.",
            "Only binary artifacts are currently represented as integrity assets by the device mapper.",
        ],
        "read_only": True,
    }

@dataclass
class RiskAssessment:
    """Persistable, evidence-based risk determination."""
    finding_id: str
    risk_level: str
    confidence: str
    reasoning: str
    unobserved_scope: str | None = None
    depends_on_findings: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_risk(
    finding: dict[str, Any],
    observation_a: dict[str, Any] | None,
    observation_b: dict[str, Any] | None,
    dependency_map: dict[str, list[str]] | None = None,
) -> RiskAssessment:
    """Assess only persisted findings and explicitly supplied observation evidence."""
    confidence = str(finding.get("confidence") or "unknown")
    kind = str(finding.get("finding_type") or "unobserved")
    asset_id = str(finding.get("asset_id") or "")
    deps = sorted(set((dependency_map or {}).get(asset_id, [])))
    gaps = []
    for label, obs in (("baseline", observation_a), ("current", observation_b)):
        if not obs:
            gaps.append(f"{label} observation is missing")
        elif not obs.get("coverage_complete"):
            gaps.append(
                f"{label} coverage incomplete ({obs.get('truncated_due_to') or 'scan errors or limits'})"
            )
        if obs and not obs.get("event_monitor_active"):
            gaps.append(f"{label} event monitoring unavailable; changes between polls may be missed")
    if confidence == "unknown" or kind == "unobserved":
        level, confidence = "unknown", "unknown"
        reason = "Observation evidence is incomplete or the relevant scope was not observed."
    elif confidence == "low":
        level = "info"
        reason = "Low-confidence integrity evidence; it does not justify a high-risk conclusion."
    elif kind in {"inaccessible", "inaccessible_then", "inaccessible_now"}:
        level = "unknown"
        reason = "The asset's containing scope was inaccessible; absence or integrity cannot be determined."
    elif kind == "hash_mismatch":
        if deps and confidence == "high":
            level = "critical" if any(x.lower() in {"critical", "system", "init", "security"} for x in deps) else "high"
            reason = "A high-confidence hash mismatch affects an asset with recorded downstream dependencies."
        elif confidence == "high":
            level, reason = "medium", "A high-confidence hash mismatch is recorded; no critical dependency evidence was found."
        else:
            level, reason = "info", "Hash mismatch has insufficient coverage confidence."
    elif kind == "missing":
        level = "medium" if confidence == "high" else "unknown"
        reason = "Asset absence is supported only when both observations have complete, matching scope."
    elif kind == "new":
        level = "info"
        reason = "A new binary artifact was observed; novelty alone is not evidence of compromise."
    else:
        level, reason = "info", "Recorded finding does not meet a higher-risk rule."
    if gaps:
        reason += " Coverage limitations: " + "; ".join(gaps) + "."
    scope = "; ".join(gaps) if gaps else None
    return RiskAssessment(
        finding_id=str(finding.get("id") or finding.get("finding_id") or ""),
        risk_level=level, confidence=confidence, reasoning=reason,
        unobserved_scope=scope, depends_on_findings=deps,
    )


class _InotifyBackend:
    """Small Linux inotify backend; no third-party dependency and no file execution."""
    _MASK = 0x00000FFF | 0x00004000 | 0x00008000 | 0x00000100 | 0x00000200

    def __init__(self, paths: list[str], on_error):
        import ctypes
        import os
        import select
        import struct
        import threading
        self._ctypes, self._os, self._select, self._struct = ctypes, os, select, struct
        self._threading = threading
        self.fd = os.inotify_init1(os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)) if hasattr(os, "inotify_init1") else -1
        if self.fd < 0:
            libc = ctypes.CDLL(None, use_errno=True)
            self.fd = libc.inotify_init1(os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        self.errors: list[str] = []
        self.event_count = 0
        self.events: list[dict[str, Any]] = []
        self._event_lock = threading.Lock()
        self._stop = threading.Event()
        self._watches: dict[int, str] = {}
        self._on_error = on_error
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self._libc.inotify_add_watch.restype = ctypes.c_int
        for root in paths:
            self._watch_tree(root)
        if not self._watches:
            self.close()
            raise OSError("No eligible directories could be watched by inotify")
        self._thread = threading.Thread(target=self._run, name="mnemos-inotify", daemon=True)
        self._thread.start()

    def _add_watch(self, path: str) -> None:
        try:
            wd = self._libc.inotify_add_watch(self.fd, self._os.fsencode(path), self._MASK)
            if wd < 0:
                err = self._ctypes.get_errno()
                self.errors.append(f"{path}: {self._os.strerror(err)}")
                return
            self._watches[wd] = path
        except OSError as exc:
            self.errors.append(f"{path}: {exc}")

    def _watch_tree(self, root: str) -> None:
        import os
        if not os.path.exists(root):
            self.errors.append(f"{root}: path does not exist")
            return
        if os.path.isfile(root):
            self._add_watch(os.path.dirname(root) or ".")
            return
        for current, dirs, _files in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if not os.path.islink(os.path.join(current, name))]
            self._add_watch(current)

    def _run(self) -> None:
        import os
        import struct
        while not self._stop.is_set():
            try:
                ready, _, _ = self._select.select([self.fd], [], [], 0.5)
                if not ready:
                    continue
                data = os.read(self.fd, 256 * 1024)
                offset = 0
                while offset + 16 <= len(data):
                    wd, mask, _cookie, name_len = struct.unpack_from("iIII", data, offset)
                    offset += 16
                    name_raw = data[offset:offset + name_len].split(b"\0", 1)[0]
                    offset += name_len
                    self.event_count += 1
                    base = self._watches.get(wd)
                    name = os.fsdecode(name_raw) if name_raw else ""
                    event_path = os.path.join(base, name) if base and name else base
                    event_type = (
                        "created" if mask & 0x00000100 else
                        "deleted" if mask & 0x00000200 else
                        "moved_from" if mask & 0x00000040 else
                        "moved_to" if mask & 0x00000080 else
                        "modified" if mask & (0x00000002 | 0x00000008) else
                        "metadata_changed" if mask & 0x00000004 else
                        "watch_lost" if mask & (0x00004000 | 0x00008000) else "filesystem_event"
                    )
                    if event_path:
                        with self._event_lock:
                            self.events.append({"timestamp": time.time(), "path": event_path,
                                                "event_type": event_type, "source": "inotify"})
                            if len(self.events) > 2000:
                                del self.events[:len(self.events) - 2000]
                    if base and mask & 0x00000100 and name_raw:
                        child = os.path.join(base, name)
                        if os.path.isdir(child) and not os.path.islink(child):
                            self._watch_tree(child)
                    if mask & (0x00004000 | 0x00008000):
                        self.errors.append(f"inotify watch lost for {base or wd}")
            except BlockingIOError:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self.errors.append(f"inotify read failed: {exc}")
                return

    def drain_events(self) -> list[dict[str, Any]]:
        with self._event_lock:
            pending, self.events = self.events, []
        return pending

    def close(self) -> None:
        self._stop.set()
        try:
            self._os.close(self.fd)
        except OSError:
            pass
        thread = getattr(self, "_thread", None)
        if thread and thread.is_alive():
            thread.join(timeout=1.0)


class ScanOrchestrator:
    """Owns a real OS event backend when available and a polling fallback always."""
    def __init__(self, paths, max_files, interval=300, *, store=None, scan_callback=None):
        self.paths = [str(Path(p).expanduser().resolve()) for p in paths]
        self.max_files = int(max_files)
        self.interval = float(interval)
        if self.interval <= 0:
            raise ValueError("Polling interval must be greater than zero.")
        self.store = store
        self.scan_callback = scan_callback
        self.once = False
        self.event_monitor = None
        self.event_monitor_active = False
        self.event_monitor_type = None
        self.event_monitor_errors: list[str] = []
        self.last_observation = None
        self._stop = __import__("threading").Event()
        self._thread = None
        self._started_at = None

    def _attach_event_monitor(self):
        import sys
        if sys.platform.startswith("linux"):
            try:
                self.event_monitor = _InotifyBackend(self.paths, self.event_monitor_errors.append)
                self.event_monitor_active = True
                self.event_monitor_type = "inotify"
                self.event_monitor_errors.extend(self.event_monitor.errors)
            except (OSError, AttributeError, NotImplementedError) as exc:
                self.event_monitor_errors.append(f"inotify unavailable: {type(exc).__name__}: {exc}")
        elif sys.platform == "darwin":
            self.event_monitor_errors.append("FSEvents backend is not implemented in this build; polling remains active.")
        elif sys.platform == "win32":
            self.event_monitor_errors.append("ETW backend is not implemented in this build; polling remains active.")
        else:
            self.event_monitor_errors.append(f"No supported event backend for platform {sys.platform!r}; polling remains active.")

    def get_current_status(self) -> dict[str, Any]:
        now = time.time()
        dynamic_errors = self.event_monitor.errors if self.event_monitor else []
        return {
            "daemon_running": bool(self._thread and self._thread.is_alive()) or self._started_at is not None,
            "event_monitor_active": self.event_monitor_active,
            "event_monitor_type": self.event_monitor_type,
            "event_monitor_errors": list(dict.fromkeys(self.event_monitor_errors + dynamic_errors)),
            "polling_active": bool(self._thread and self._thread.is_alive()),
            "polling_interval": self.interval,
            "last_observation": self.last_observation,
            "last_scan_timestamp": (self.last_observation or {}).get("timestamp"),
            "uptime_seconds": max(0.0, now - self._started_at) if self._started_at else 0.0,
        }

    def start_monitoring(self):
        import threading
        if self._thread and self._thread.is_alive():
            return self.get_current_status()
        self._attach_event_monitor()
        self._started_at = time.time()
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, name="mnemos-polling", daemon=True)
        self._thread.start()
        return self.get_current_status()

    def _poll(self):
        while not self._stop.is_set():
            try:
                if self.scan_callback:
                    self.scan_callback()
                if self.store:
                    self.store.update_monitoring_runtime(
                        status="running", paths=self.paths, interval_seconds=self.interval,
                        event_monitor_active=self.event_monitor_active, event_monitor_type=self.event_monitor_type,
                        event_monitor_errors=list(dict.fromkeys(self.event_monitor_errors + (self.event_monitor.errors if self.event_monitor else []))),
                        pid=__import__("os").getpid(),
                    )
                    if self.event_monitor:
                        pending_events = self.event_monitor.drain_events()
                        if pending_events:
                            self.store.save_device_events(pending_events)
                    obs = self.store.latest_observation()
                    if obs:
                        obs["event_monitor_active"] = self.event_monitor_active
                        obs["event_monitor_type"] = self.event_monitor_type
                        obs["event_monitor_errors"] = list(dict.fromkeys(
                            self.event_monitor_errors + (self.event_monitor.errors if self.event_monitor else [])
                        ))
                        # Inotify sees changes, but the complete inventory remains a periodic scan.
                        obs["scan_type"] = "filesystem_scan"
                        self.store.save_observation(obs)
                        self.last_observation = self.store.latest_observation()
            except Exception as exc:
                self.event_monitor_errors.append(f"polling scan failed: {type(exc).__name__}: {exc}")
            if self.once:
                break
            if self._stop.wait(self.interval):
                break

    def stop_monitoring(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(2.0, min(self.interval + 1, 10.0)))
        if self.event_monitor:
            self.event_monitor.close()
            self.event_monitor = None
        self._started_at = None
        return self.get_current_status()


def check_service_registration() -> dict[str, Any]:
    """Read-only audit of user-level startup service registration."""
    import os
    import platform as platform_module
    import subprocess
    system = platform_module.system().lower()
    results: dict[str, Any] = {
        "platform": system, "service_registered": False, "service_enabled": False, "failures": [],
        "checks": [],
    }
    candidates = []
    if system == "linux":
        candidates = [
            (Path.home() / ".config/systemd/user/mnemos.service", ["systemctl", "--user", "is-enabled", "mnemos.service"]),
            (Path("/etc/systemd/system/mnemos.service"), ["systemctl", "is-enabled", "mnemos.service"]),
        ]
    elif system == "darwin":
        candidates = [(Path.home() / "Library/LaunchAgents/com.mnemos.daemon.plist",
                       ["launchctl", "list", "com.mnemos.daemon"])]
    elif system == "windows":
        candidates = [(Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/Tasks/Mnemos",
                       ["schtasks", "/Query", "/TN", "Mnemos"])]
    else:
        results["failures"].append(f"Unsupported service platform: {system}")
    for path, command in candidates:
        exists = path.exists()
        check = {"path": str(path), "registered": exists, "enabled": False, "command": command}
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
            check["command_exit_code"] = proc.returncode
            check["command_output"] = (proc.stdout or proc.stderr).strip()[:500]
            check["enabled"] = proc.returncode == 0 and (
                system != "linux" or "disabled" not in proc.stdout.lower()
            )
        except (OSError, subprocess.SubprocessError) as exc:
            results["failures"].append(f"{' '.join(command)}: {exc}")
        results["checks"].append(check)
        results["service_registered"] = results["service_registered"] or exists
        results["service_enabled"] = results["service_enabled"] or check["enabled"]
    return results


def enable_service_registration() -> dict[str, Any]:
    """Install a per-user startup service; never silently elevates privileges."""
    import os
    import platform as platform_module
    import shlex
    import subprocess
    import sys
    exe = shlex.quote(sys.executable)
    args = " ".join(shlex.quote(item) for item in sys.argv)
    system = platform_module.system().lower()
    if system == "linux":
        target = Path.home() / ".config/systemd/user/mnemos.service"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "[Unit]\\nDescription=Mnemos-RLI offline integrity monitor\\nAfter=default.target\\n\\n"
            "[Service]\\nType=simple\\nExecStart=" + exe + " -m mnemos " + args + "\\n"
            "Restart=on-failure\\nRestartSec=5\\n\\n[Install]\\nWantedBy=default.target\\n",
            encoding="utf-8",
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=15)
        subprocess.run(["systemctl", "--user", "enable", "--now", "mnemos.service"], check=True, timeout=15)
        return {"service_registered": True, "service_enabled": True, "path": str(target)}
    if system == "darwin":
        target = Path.home() / "Library/LaunchAgents/com.mnemos.daemon.plist"
        target.parent.mkdir(parents=True, exist_ok=True)
        import plistlib
        target.write_bytes(plistlib.dumps({
            "Label": "com.mnemos.daemon", "ProgramArguments": [sys.executable, "-m", "mnemos", *sys.argv],
            "RunAtLoad": True, "KeepAlive": True,
        }))
        subprocess.run(["launchctl", "load", str(target)], check=True, timeout=15)
        return {"service_registered": True, "service_enabled": True, "path": str(target)}
    if system == "windows":
        command = f'"{sys.executable}" -m mnemos ' + " ".join(shlex.quote(item) for item in sys.argv)
        subprocess.run(["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", "Mnemos",
                        "/TR", command], check=True, timeout=15)
        return {"service_registered": True, "service_enabled": True, "command": command}
    raise OSError(f"Automatic startup registration is not supported on {system}.")
