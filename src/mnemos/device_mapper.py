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



def _inspect_elf(stream: Any, header: bytes) -> dict[str, Any]:
    """Parse bounded ELF section and symbol metadata from file bytes only."""
    if len(header) < 52 or header[4] not in (1, 2) or header[5] not in (1, 2):
        return {"status": "invalid_elf_header"}
    bits = 32 if header[4] == 1 else 64
    endian = "<" if header[5] == 1 else ">"
    file_size = os.fstat(stream.fileno()).st_size
    e_type, machine = struct.unpack_from(endian + "HH", header, 16)
    if bits == 32:
        if len(header) < 52:
            return {"status": "truncated_header"}
        entry = struct.unpack_from(endian + "I", header, 24)[0]
        section_offset = struct.unpack_from(endian + "I", header, 32)[0]
        section_entry_size, section_count, string_index = struct.unpack_from(endian + "HHH", header, 46)
        expected_header_size = 40
        section_format = endian + "IIIIIIIIII"
    else:
        if len(header) < 64:
            return {"status": "truncated_header"}
        entry = struct.unpack_from(endian + "Q", header, 24)[0]
        section_offset = struct.unpack_from(endian + "Q", header, 40)[0]
        section_entry_size, section_count, string_index = struct.unpack_from(endian + "HHH", header, 58)
        expected_header_size = 64
        section_format = endian + "IIQQQQIIQQ"
    base = {
        "status": "parsed", "format": "ELF", "bits": bits,
        "endianness": "little" if endian == "<" else "big",
        "architecture": ELF_MACHINES.get(machine, f"machine-{machine}"),
        "machine_code": machine,
        "object_type": {1: "relocatable", 2: "executable", 3: "shared", 4: "core"}.get(e_type, f"type-{e_type}"),
        "entry_point": hex(entry), "section_table_offset": section_offset,
        "section_entry_size": section_entry_size, "section_count": section_count,
        "sections": [], "symbols": [], "analysis_limits": [],
    }
    if section_count == 0:
        return base
    if section_entry_size < expected_header_size or section_count > 4096:
        base["analysis_limits"].append("invalid_or_excessive_section_table")
        return base
    table_size = section_entry_size * section_count
    if section_offset > file_size or table_size > file_size - section_offset:
        base["analysis_limits"].append("section_table_out_of_bounds")
        return base

    stream.seek(section_offset)
    raw_sections = []
    for index in range(section_count):
        raw = stream.read(section_entry_size)
        if len(raw) != section_entry_size:
            base["analysis_limits"].append("truncated_section_table")
            return base
        fields = struct.unpack_from(section_format, raw)
        if bits == 32:
            name, section_type, flags, address, offset, size, link, info, alignment, entry_size = fields
        else:
            name, section_type, flags, address, offset, size, link, info, alignment, entry_size = fields
        if offset > file_size or (section_type != 8 and size > file_size - offset):
            # SHT_NOBITS sections occupy memory but no bytes in the file.
            base["analysis_limits"].append(f"section_{index}_out_of_bounds")
            size = 0
        raw_sections.append({
            "index": index, "name_offset": name, "type_code": section_type,
            "flags": flags, "address": address, "offset": offset, "size": size,
            "link": link, "info": info, "alignment": alignment, "entry_size": entry_size,
        })

    def read_region(offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset > file_size or size > file_size - offset:
            return b""
        stream.seek(offset)
        return stream.read(size)

    names = b""
    if string_index < len(raw_sections):
        section = raw_sections[string_index]
        if section["size"] <= 8 * 1024 * 1024:
            names = read_region(section["offset"], section["size"])

    def string_at(table: bytes, offset: int) -> str:
        if offset < 0 or offset >= len(table):
            return ""
        end = table.find(bytes((0,)), offset, min(len(table), offset + 4096))
        if end < 0:
            end = min(len(table), offset + 4096)
        return table[offset:end].decode("utf-8", errors="replace")

    for section in raw_sections:
        section_name = string_at(names, section["name_offset"])
        section["name"] = section_name or f"section_{section['index']}"
        base["sections"].append({
            "index": section["index"], "name": section["name"],
            "type_code": section["type_code"], "flags": section["flags"],
            "address": hex(section["address"]), "offset": section["offset"],
            "size_bytes": section["size"], "entry_size": section["entry_size"],
        })

    symbol_format = endian + ("IBBHQQ" if bits == 64 else "IIIBBH")
    symbol_size = struct.calcsize(symbol_format)
    for section in raw_sections:
        if section["type_code"] not in (2, 11) or section["link"] >= len(raw_sections):
            continue
        if section["size"] > 16 * 1024 * 1024:
            base["analysis_limits"].append(f"symbols_skipped_large_section_{section['index']}")
            continue
        symbol_strings_section = raw_sections[section["link"]]
        strings = read_region(symbol_strings_section["offset"], symbol_strings_section["size"])
        entry_size = section["entry_size"] or symbol_size
        if entry_size < symbol_size or entry_size == 0:
            base["analysis_limits"].append(f"symbols_skipped_invalid_entry_size_{section['index']}")
            continue
        count = min(section["size"] // entry_size, 10000 - len(base["symbols"]))
        raw = read_region(section["offset"], count * entry_size)
        for index in range(0, len(raw) - symbol_size + 1, entry_size):
            values = struct.unpack_from(symbol_format, raw, index)
            if bits == 64:
                name_offset, info, other, shndx, value, size = values
            else:
                name_offset, value, size, info, other, shndx = values
            name = string_at(strings, name_offset)
            if not name:
                continue
            base["symbols"].append({
                "name": name, "value": hex(value), "size_bytes": size,
                "binding_code": info >> 4, "type_code": info & 0x0F,
                "section_index": shndx, "source_section": section["name"],
            })
        if len(base["symbols"]) >= 10000:
            base["analysis_limits"].append("symbol_limit_10000_reached")
            break
    return base


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
                return _inspect_elf(stream, header)
            macho = {
                b"\xfe\xed\xfa\xce": (">", 32),
                b"\xce\xfa\xed\xfe": ("<", 32),
                b"\xfe\xed\xfa\xcf": (">", 64),
                b"\xcf\xfa\xed\xfe": ("<", 64),
            }
            if fmt == "Mach-O" and header[:4] in macho and len(header) >= 28:
                endian, bits = macho[header[:4]]
                file_size = os.fstat(stream.fileno()).st_size
                cpu, subtype, filetype, commands, command_bytes, flags = struct.unpack_from(endian + "IIIIII", header, 4)
                header_size = 32 if bits == 64 else 28
                result = {
                    "status": "parsed", "format": "Mach-O", "bits": bits,
                    "endianness": "little" if endian == "<" else "big",
                    "architecture": MACHO_CPUS.get(cpu, f"cpu-{cpu}"),
                    "cpu_type": cpu, "cpu_subtype": subtype, "file_type": filetype,
                    "load_command_count": commands, "load_command_bytes": command_bytes,
                    "flags": flags, "dependencies": [], "rpaths": [], "analysis_limits": [],
                }
                if header_size > file_size or commands > 4096 or command_bytes > file_size - header_size:
                    result["analysis_limits"].append("invalid_or_excessive_load_commands")
                    return result
                stream.seek(header_size)
                consumed = 0
                for command_index in range(commands):
                    if consumed + 8 > command_bytes:
                        result["analysis_limits"].append("truncated_load_command_header")
                        break
                    command_header = stream.read(8)
                    if len(command_header) != 8:
                        result["analysis_limits"].append("truncated_load_command_header")
                        break
                    command, command_size = struct.unpack(endian + "II", command_header)
                    if command_size < 8 or command_size > command_bytes - consumed:
                        result["analysis_limits"].append("invalid_load_command_size")
                        break
                    payload = stream.read(command_size - 8)
                    if len(payload) != command_size - 8:
                        result["analysis_limits"].append("truncated_load_command")
                        break
                    # Dylib commands store a string offset at byte 8; LC_RPATH does too.
                    dylib_commands = {
                        0x0000000C: "load", 0x0000000D: "id",
                        0x80000018: "weak_load", 0x8000001F: "reexport",
                        0x80000023: "upward_load",
                    }
                    if command in dylib_commands or command == 0x8000001C:
                        if command_size >= 12:
                            name_offset = struct.unpack_from(endian + "I", payload, 0)[0]
                            payload_string_offset = name_offset - 8
                            if 0 <= payload_string_offset < len(payload):
                                raw_name = payload[payload_string_offset:]
                                raw_name = raw_name.split(bytes((0,)), 1)[0][:4096]
                                name = raw_name.decode("utf-8", errors="replace")
                                if name:
                                    if command == 0x8000001C:
                                        if len(result["rpaths"]) < 256:
                                            result["rpaths"].append(name)
                                    elif len(result["dependencies"]) < 2048:
                                        result["dependencies"].append({
                                            "name": name, "kind": dylib_commands[command],
                                        })
                    consumed += command_size
                    stream.seek(header_size + consumed)
                if consumed != command_bytes and not result["analysis_limits"]:
                    result["analysis_limits"].append("load_command_size_mismatch")
                return result
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
