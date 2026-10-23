"""Offline device inventory and conservative binary triage.

Only explicitly supplied paths are traversed. Candidate binaries are identified by
magic bytes and metadata; this module never executes inspected files or uses network.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Any

TOOL_NAMES = (
    "python", "python3", "git", "clang", "gcc", "cc", "make", "cmake",
    "ninja", "rustc", "cargo", "go", "node", "npm", "java", "javac",
    "adb", "termux-info", "file", "readelf", "objdump", "otool", "dumpbin",
)
SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules", ".cache"}
MAX_HASH_BYTES = 256 * 1024 * 1024
MAGIC = (
    (b"\x7fELF", "ELF"),
    (b"MZ", "PE/DOS"),
    (b"\x00asm", "WebAssembly"),
    (b"PK\x03\x04", "ZIP/APK/JAR"),
    (b"\xfe\xed\xfa\xce", "Mach-O"),
    (b"\xce\xfa\xed\xfe", "Mach-O"),
    (b"\xfe\xed\xfa\xcf", "Mach-O"),
    (b"\xcf\xfa\xed\xfe", "Mach-O"),
    (b"\xca\xfe\xba\xbe", "Mach-O/Fat-or-Java-class"),
)


def classify_binary(header: bytes) -> str | None:
    """Return a format label from file magic without loading or executing a file."""
    for magic, label in MAGIC:
        if header.startswith(magic):
            return label
    # Mach-O fat/universal variants.
    if len(header) >= 4 and header[:4] in (b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"):
        return "Mach-O/Fat"
    return None


def _sha256(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_HASH_BYTES:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _artifact(path: Path) -> dict[str, Any] | None:
    try:
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            return None
        with path.open("rb") as stream:
            header = stream.read(4096)
        fmt = classify_binary(header)
        if fmt is None and not (info.st_mode & 0o111):
            return None
        digest = _sha256(path)
        return {
            "path": str(path),
            "name": path.name,
            "format": fmt or "executable-unknown",
            "size_bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "mode": stat.S_IMODE(info.st_mode),
            "sha256": digest,
            "hash_skipped_reason": (
                "file exceeds 256 MiB limit or could not be read"
                if digest is None else None
            ),
        }
    except OSError:
        return None


def discover_artifacts(paths: Iterable[str | Path] = (), *, max_files: int = 2000) -> list[dict[str, Any]]:
    """Inspect only user-selected files/directories; bound work and do not follow symlinks."""
    if max_files < 1:
        raise ValueError("max_files must be positive")
    found: list[dict[str, Any]] = []
    examined = 0
    for supplied in paths:
        if examined >= max_files:
            break
        root = Path(supplied).expanduser().resolve()
        if not root.exists():
            raise ValueError(f"scan path does not exist: {supplied}")
        candidates: Iterable[Path]
        if root.is_file():
            candidates = (root,)
        elif root.is_dir():
            def walk() -> Iterable[Path]:
                nonlocal examined
                for current, dirs, files in os.walk(root, followlinks=False):
                    dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(current) / d).is_symlink())
                    depth = len(Path(current).relative_to(root).parts)
                    if depth >= 12:
                        dirs[:] = []
                    for name in sorted(files):
                        if examined >= max_files:
                            return
                        examined += 1
                        yield Path(current) / name
            candidates = walk()
        else:
            continue
        for candidate in candidates:
            if examined >= max_files and root.is_dir():
                break
            if root.is_file():
                examined += 1
            item = _artifact(candidate)
            if item is not None:
                found.append(item)
            if examined >= max_files:
                break
    # Stable ordering makes snapshots easy to compare and review.
    found.sort(key=lambda item: item["path"])
    return found


def collect_device_map(paths: Iterable[str | Path] = (), *, max_files: int = 2000) -> dict[str, Any]:
    """Collect an offline OS/runtime/tool inventory and optional binary metadata."""
    paths = tuple(paths)
    uname = platform.uname()
    tools = {name: shutil.which(name) for name in TOOL_NAMES}
    prefix = os.environ.get("PREFIX", "")
    return {
        "schema": "mnemos-device-map-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": {
            "os": platform.system() or sys.platform,
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "uname": {
                "system": uname.system, "node": uname.node, "release": uname.release,
                "version": uname.version, "machine": uname.machine, "processor": uname.processor,
            },
            "python": {
                "version": platform.python_version(),
                "implementation": platform.python_implementation(),
                "executable": sys.executable,
                "prefix": sys.prefix,
                "exec_prefix": sys.exec_prefix,
            },
            "environment_class": (
                "android-termux" if "com.termux" in prefix.lower() or "TERMUX_VERSION" in os.environ
                else "unknown"
            ),
            "available_tools": tools,
        },
        "scan": {
            "scope": [str(Path(path).expanduser()) for path in paths],
            "max_files": max_files,
            "network_used": False,
            "executed_scanned_files": False,
        },
        "artifacts": discover_artifacts(paths, max_files=max_files),
    }
