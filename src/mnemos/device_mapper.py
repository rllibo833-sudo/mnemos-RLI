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
import struct
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



ELF_MACHINES = {
    3: "x86", 8: "MIPS", 20: "PowerPC", 40: "ARM",
    62: "x86_64", 183: "AArch64", 243: "RISC-V",
}
PE_MACHINES = {
    0x014C: "x86", 0x8664: "x86_64", 0x01C0: "ARM",
    0x01C4: "ARMv7", 0xAA64: "AArch64", 0x0200: "IA64",
}
MACHO_CPUS = {
    7: "x86", 0x01000007: "x86_64", 12: "ARM",
    0x0100000C: "AArch64", 18: "PowerPC",
}


def inspect_binary(path: str | Path, fmt: str | None = None) -> dict[str, Any]:
    """Read fixed-format headers only; no disassembly, dynamic loading, or execution."""
    target = Path(path)
    try:
        with target.open("rb") as stream:
            header = stream.read(64)
            if fmt == "PE/DOS" and header.startswith(b"MZ"):
                if len(header) < 64:
                    return {"status": "truncated_header"}
                pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
                stream.seek(pe_offset)
                pe = stream.read(26)
                if len(pe) < 26 or pe[:4] != b"PE\0\0":
                    return {"status": "invalid_pe_header"}
                machine, sections = struct.unpack_from("<HH", pe, 4)
                optional_magic = struct.unpack_from("<H", pe, 24)[0]
                return {
                    "status": "parsed", "format": "PE",
                    "architecture": PE_MACHINES.get(machine, f"machine-0x{machine:04x}"),
                    "machine_code": machine, "section_count": sections,
                    "optional_header": {0x10B: "PE32", 0x20B: "PE32+"}.get(optional_magic, "unknown"),
                }
            if fmt == "ELF" and header.startswith(b"\x7fELF"):
                if len(header) < 52 or header[4] not in (1, 2) or header[5] not in (1, 2):
                    return {"status": "invalid_elf_header"}
                bits = 32 if header[4] == 1 else 64
                endian = "<" if header[5] == 1 else ">"
                e_type, machine = struct.unpack_from(endian + "HH", header, 16)
                if bits == 32:
                    entry = struct.unpack_from(endian + "I", header, 24)[0]
                    section_offset = struct.unpack_from(endian + "I", header, 32)[0]
                    section_entry_size, section_count = struct.unpack_from(endian + "HH", header, 46)
                else:
                    if len(header) < 64:
                        return {"status": "truncated_header"}
                    entry = struct.unpack_from(endian + "Q", header, 24)[0]
                    section_offset = struct.unpack_from(endian + "Q", header, 40)[0]
                    section_entry_size, section_count = struct.unpack_from(endian + "HH", header, 58)
                return {
                    "status": "parsed", "format": "ELF", "bits": bits,
                    "endianness": "little" if endian == "<" else "big",
                    "architecture": ELF_MACHINES.get(machine, f"machine-{machine}"),
                    "machine_code": machine,
                    "object_type": {1: "relocatable", 2: "executable", 3: "shared", 4: "core"}.get(e_type, f"type-{e_type}"),
                    "entry_point": hex(entry), "section_table_offset": section_offset,
                    "section_entry_size": section_entry_size, "section_count": section_count,
                }
            macho = {
                b"\xfe\xed\xfa\xce": (">", 32),
                b"\xce\xfa\xed\xfe": ("<", 32),
                b"\xfe\xed\xfa\xcf": (">", 64),
                b"\xcf\xfa\xed\xfe": ("<", 64),
            }
            if fmt == "Mach-O" and header[:4] in macho and len(header) >= 28:
                endian, bits = macho[header[:4]]
                cpu, subtype, filetype, commands, command_bytes, flags = struct.unpack_from(endian + "IIIIII", header, 4)
                return {
                    "status": "parsed", "format": "Mach-O", "bits": bits,
                    "endianness": "little" if endian == "<" else "big",
                    "architecture": MACHO_CPUS.get(cpu, f"cpu-{cpu}"),
                    "cpu_type": cpu, "cpu_subtype": subtype, "file_type": filetype,
                    "load_command_count": commands, "load_command_bytes": command_bytes,
                    "flags": flags,
                }
            if fmt == "WebAssembly" and header.startswith(b"\x00asm"):
                version = struct.unpack_from("<I", header, 4)[0] if len(header) >= 8 else None
                return {"status": "parsed", "format": "WebAssembly", "version": version}
            if fmt in ("ZIP/APK/JAR", "Mach-O/Fat-or-Java-class", "Mach-O/Fat"):
                return {"status": "container_signature_only", "format": fmt}
    except OSError:
        return {"status": "unreadable"}
    return {"status": "unsupported_or_unknown"}


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
            "binary_details": inspect_binary(path, fmt),
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
