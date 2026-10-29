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
import time
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

import json
import tempfile

CACHE_PATH = Path.home() / ".cache" / "mnemos" / "hash_cache.json"
_CACHE_FIELDS = ("dev", "ino", "size", "mtime_ns", "ctime_ns")
_CACHE_LIMIT = 20000


def _cache_entry_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if any(not isinstance(value.get(field), int) or isinstance(value.get(field), bool)
           or value[field] < 0 for field in _CACHE_FIELDS):
        return False
    digest = value.get("sha256")
    return (isinstance(digest, str) and len(digest) == 64
            and all(char in "0123456789abcdef" for char in digest))


def _load_hash_cache() -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: value for key, value in raw.items()
        if isinstance(key, str) and key and _cache_entry_valid(value)
    }


def _save_hash_cache(cache: dict[str, dict[str, Any]]) -> None:
    temporary_name = None
    try:
        CACHE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        valid = {key: value for key, value in cache.items()
                 if isinstance(key, str) and key and _cache_entry_valid(value)}
        if len(valid) > _CACHE_LIMIT:
            valid = dict(sorted(
                valid.items(), key=lambda item: item[1].get("at", 0)
                if isinstance(item[1].get("at", 0), (int, float)) else 0
            )[-15000:])
        fd, temporary_name = tempfile.mkstemp(prefix="hash_cache.", suffix=".tmp",
                                               dir=str(CACHE_PATH.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.chmod(temporary_name, 0o600)
            json.dump(valid, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, CACHE_PATH)
        temporary_name = None
    except (OSError, TypeError, ValueError):
        pass
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


_HASH_CACHE: dict[str, dict[str, Any]] | None = None


def _get_cache() -> dict[str, dict[str, Any]]:
    global _HASH_CACHE
    if _HASH_CACHE is None:
        _HASH_CACHE = _load_hash_cache()
    return _HASH_CACHE


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000)))

def _normalize_os_type():
    system = platform.system() or sys.platform
    low = system.lower()
    if "TERMUX_VERSION" in os.environ or "com.termux" in os.environ.get("PREFIX", "").lower():
        normalized, family = "android-termux", "android"
    elif low.startswith("darwin"):
        normalized, family = "macos", "unix"
    elif low.startswith("win"):
        normalized, family = "windows", "windows"
    elif low.startswith("linux"):
        normalized, family = "linux", "unix"
    elif "freebsd" in low:
        normalized, family = "freebsd", "unix"
    else:
        normalized, family = low, "unknown"
    return {"raw": system, "normalized": normalized, "family": family}

def _detect_sandbox_id():
    import os
    env=os.environ; sb="host"; det={}
    if os.path.exists("/.dockerenv") or Path("/run/.containerenv").exists(): sb="docker"
    if env.get("FLATPAK_ID"): sb="flatpak"; det["flatpak_id"]=env["FLATPAK_ID"]
    if "com.termux" in env.get("PREFIX","").lower() or "TERMUX_VERSION" in env: sb="android-termux" if sb=="host" else sb
    return {"sandbox_id":sb,"details":det,"is_sandboxed":sb!="host"}

SAMPLE_HASH_WINDOW_BYTES = 64 * 1024
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



def _inspect_elf_dynamic(stream: Any, header: bytes, bits: int, endian: str, file_size: int) -> dict[str, Any]:
    """Extract bounded DT_NEEDED/RPATH/RUNPATH entries from ELF program headers."""
    result: dict[str, Any] = {"dependencies": [], "rpaths": [], "runpaths": [], "dynamic_status": "unavailable"}
    phoff = struct.unpack_from(endian + ("I" if bits == 32 else "Q"), header, 28 if bits == 32 else 32)[0]
    phentsize, phnum = struct.unpack_from(endian + "HH", header, 42 if bits == 32 else 54)
    expected = 32 if bits == 32 else 56
    if phnum == 0:
        result["dynamic_status"] = "no_program_headers"
        return result
    if phnum > 4096 or phentsize < expected or phentsize > 4096 or phoff > file_size or phnum * phentsize > file_size - phoff:
        result["dynamic_status"] = "invalid_or_excessive_program_headers"
        return result
    loads: list[tuple[int, int, int]] = []
    dynamic: tuple[int, int] | None = None
    stream.seek(phoff)
    for _ in range(phnum):
        raw = stream.read(phentsize)
        if len(raw) != phentsize:
            result["dynamic_status"] = "truncated_program_headers"
            return result
        if bits == 32:
            p_type, p_offset, p_vaddr, _paddr, p_filesz, _memsz, _flags, _align = struct.unpack_from(endian + "IIIIIIII", raw)
        else:
            p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz, _memsz, _align = struct.unpack_from(endian + "IIQQQQQQ", raw)
        if p_type in (1, 2) and p_filesz > _memsz:
            result["dynamic_status"] = "invalid_program_segment_size"
            return result
        if p_offset > file_size or p_filesz > file_size - p_offset:
            continue
        if p_type == 1:
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == 2:
            dynamic = (p_offset, p_filesz)
    if dynamic is None:
        result["dynamic_status"] = "no_dynamic_segment"
        return result

    def va_to_offset(address: int, size: int = 1) -> int | None:
        for vaddr, offset, span in loads:
            delta = address - vaddr
            if 0 <= delta <= span and size <= span - delta:
                return offset + delta
        return None

    dyn_offset, dyn_size = dynamic
    entry_size = 8 if bits == 32 else 16
    if dyn_size > 1024 * 1024:
        dyn_size = 1024 * 1024
        result["dynamic_status"] = "dynamic_segment_capped"
    stream.seek(dyn_offset)
    tags: dict[int, list[int]] = {}
    terminated = False
    for _ in range(min(dyn_size // entry_size, 4096)):
        raw = stream.read(entry_size)
        if len(raw) != entry_size:
            break
        if bits == 32:
            tag, value = struct.unpack(endian + "iI", raw)
        else:
            tag, value = struct.unpack(endian + "qQ", raw)
        if tag == 0:
            terminated = True
            break
        if tag in (1, 5, 10, 15, 29):
            tags.setdefault(tag, []).append(value)
    if not terminated:
        result["dynamic_status"] = "missing_dynamic_terminator"
        return result
    strtab_va = next(iter(tags.get(5, [])), None)
    strtab_size = next(iter(tags.get(10, [])), 0)
    if strtab_size > 8 * 1024 * 1024:
        result["dynamic_status"] = "string_table_size_exceeds_limit"
        return result
    strtab_offset = va_to_offset(strtab_va, strtab_size) if strtab_va is not None and strtab_size else None
    strings = b""
    if strtab_offset is None:
        result["dynamic_status"] = "invalid_string_table"
        return result
    stream.seek(strtab_offset)
    strings = stream.read(strtab_size)
    if len(strings) != strtab_size:
        result["dynamic_status"] = "truncated_string_table"
        return result

    def dyn_string(offset: int) -> str:
        if offset < 0 or offset >= len(strings):
            return ""
        end = strings.find(bytes((0,)), offset, min(len(strings), offset + 4096))
        if end < 0:
            return ""
        return strings[offset:end].decode("utf-8", errors="replace")

    for offset in tags.get(1, [])[:256]:
        name = dyn_string(offset)
        if name:
            result["dependencies"].append({"name": name, "kind": "needed"})
    for tag, key in ((15, "rpaths"), (29, "runpaths")):
        for offset in tags.get(tag, [])[:32]:
            value = dyn_string(offset)
            if value:
                result[key].extend(part for part in value.split(":") if part)
    if result["dynamic_status"] == "unavailable":
        result["dynamic_status"] = "parsed"
    return result


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
    dynamic = _inspect_elf_dynamic(stream, header, bits, endian, file_size)
    base.update(dynamic)
    if section_count == 0:
        return base
    if section_entry_size < expected_header_size or section_entry_size > 4096 or section_count > 4096:
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
    if string_index and string_index >= len(raw_sections):
        base["analysis_limits"].append("invalid_section_name_table_index")
    elif string_index < len(raw_sections):
        section = raw_sections[string_index]
        if section["size"] <= 8 * 1024 * 1024:
            names = read_region(section["offset"], section["size"])
        else:
            base["analysis_limits"].append("section_name_table_exceeds_limit")

    def string_at(table: bytes, offset: int) -> str:
        if offset < 0 or offset >= len(table):
            return ""
        end = table.find(bytes((0,)), offset, min(len(table), offset + 4096))
        if end < 0:
            return ""
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
        if section["type_code"] not in (2, 11):
            continue
        if section["link"] >= len(raw_sections):
            base["analysis_limits"].append(f"symbols_skipped_invalid_string_table_{section['index']}")
            continue
        if section["size"] > 16 * 1024 * 1024:
            base["analysis_limits"].append(f"symbols_skipped_large_section_{section['index']}")
            continue
        symbol_strings_section = raw_sections[section["link"]]
        if symbol_strings_section["size"] > 8 * 1024 * 1024:
            base["analysis_limits"].append(f"symbols_skipped_large_string_table_{section['index']}")
            continue
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



def _inspect_pe(stream: Any, dos_header: bytes) -> dict[str, Any]:
    """Parse bounded PE sections, imports, and exports without loading the image."""
    file_size = os.fstat(stream.fileno()).st_size
    if len(dos_header) < 64:
        return {"status": "truncated_dos_header", "format": "PE"}
    pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
    if pe_offset > file_size or 24 > file_size - pe_offset:
        return {"status": "invalid_pe_offset", "format": "PE"}
    stream.seek(pe_offset)
    signature_and_coff = stream.read(24)
    if len(signature_and_coff) != 24 or signature_and_coff[:4] != bytes((80, 69, 0, 0)):
        return {"status": "invalid_pe_header", "format": "PE"}
    machine, section_count, timestamp, symbol_pointer, symbol_count, optional_size, characteristics = struct.unpack_from("<HHIIIHH", signature_and_coff, 4)
    result: dict[str, Any] = {
        "status": "parsed", "format": "PE",
        "architecture": PE_MACHINES.get(machine, f"machine-0x{machine:04x}"),
        "machine_code": machine, "section_count": section_count,
        "timestamp": timestamp, "characteristics": characteristics,
        "sections": [], "imports": [], "exports": [], "analysis_limits": [],
    }
    if section_count > 4096 or optional_size > 4096 or optional_size < 2:
        result["analysis_limits"].append("invalid_or_excessive_pe_tables")
        return result
    optional = stream.read(optional_size)
    if len(optional) != optional_size:
        result["analysis_limits"].append("truncated_optional_header")
        return result
    magic = struct.unpack_from("<H", optional, 0)[0]
    if magic == 0x10B:
        bits, directory_offset, count_offset, image_base_offset = 32, 96, 92, 28
        image_base_format = "<I"
    elif magic == 0x20B:
        bits, directory_offset, count_offset, image_base_offset = 64, 112, 108, 24
        image_base_format = "<Q"
    else:
        result["analysis_limits"].append("unsupported_optional_header")
        return result
    if len(optional) < directory_offset:
        result["analysis_limits"].append("truncated_optional_header")
        return result
    result.update({
        "bits": bits, "optional_header": "PE32" if bits == 32 else "PE32+",
        "entry_point": hex(struct.unpack_from("<I", optional, 16)[0]),
        "image_base": hex(struct.unpack_from(image_base_format, optional, image_base_offset)[0]),
        "subsystem": struct.unpack_from("<H", optional, 68)[0] if len(optional) >= 70 else None,
    })
    directory_count = struct.unpack_from("<I", optional, count_offset)[0] if len(optional) >= count_offset + 4 else 0
    directory_count = min(directory_count, (len(optional) - directory_offset) // 8, 16)
    directories = [struct.unpack_from("<II", optional, directory_offset + i * 8) for i in range(directory_count)]
    section_table_offset = pe_offset + 24 + optional_size
    table_size = section_count * 40
    if section_table_offset > file_size or table_size > file_size - section_table_offset:
        result["analysis_limits"].append("section_table_out_of_bounds")
        return result
    stream.seek(section_table_offset)
    sections = []
    for index in range(section_count):
        raw = stream.read(40)
        if len(raw) != 40:
            result["analysis_limits"].append("truncated_section_table")
            return result
        name = raw[:8].split(bytes((0,)), 1)[0].decode("ascii", errors="replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", raw, 8)
        if raw_offset > file_size or raw_size > file_size - raw_offset:
            result["analysis_limits"].append(f"section_{index}_out_of_bounds")
            raw_size = 0
        section = {
            "name": name or f"section_{index}", "virtual_address": virtual_address,
            "virtual_size": virtual_size, "file_offset": raw_offset, "size_bytes": raw_size,
            "characteristics": struct.unpack_from("<I", raw, 36)[0],
        }
        sections.append(section)
        result["sections"].append(section.copy())

    def rva_offset(rva: int, size: int = 1) -> int | None:
        if rva == 0:
            return None
        for section in sections:
            span = max(section["virtual_size"], section["size_bytes"])
            delta = rva - section["virtual_address"]
            if 0 <= delta < span and delta <= section["size_bytes"] and size <= section["size_bytes"] - delta:
                offset = section["file_offset"] + delta
                if offset <= file_size and size <= file_size - offset:
                    return offset
        # Headers can contain RVAs directly.
        if rva < section_table_offset and size <= section_table_offset - rva and rva <= file_size and size <= file_size - rva:
            return rva
        return None

    def rva_available(rva: int) -> int:
        """Return bytes remaining in the single mapped file-backed region for an RVA."""
        if rva == 0:
            return 0
        for section in sections:
            delta = rva - section["virtual_address"]
            if 0 <= delta < section["size_bytes"]:
                if section["file_offset"] > file_size:
                    return 0
                return min(section["size_bytes"] - delta, file_size - section["file_offset"] - delta)
        if rva < section_table_offset and rva <= file_size:
            return min(section_table_offset - rva, file_size - rva)
        return 0

    def read_c_string(offset: int, limit: int = 512) -> str:
        if offset < 0 or offset >= file_size:
            return ""
        stream.seek(offset)
        raw = stream.read(min(limit, file_size - offset))
        raw = raw.split(bytes((0,)), 1)[0]
        return raw.decode("utf-8", errors="replace")

    # IMAGE_DIRECTORY_ENTRY_IMPORT = 1. Import descriptors are 20 bytes.
    if len(directories) > 1:
        import_rva, import_size = directories[1]
        import_offset = rva_offset(import_rva, 20) if import_rva else None
        if import_rva and import_offset is None:
            result["analysis_limits"].append("import_directory_rva_invalid")
        elif import_offset is not None:
            available_descriptors = rva_available(import_rva) // 20
            if import_size and import_size < 20:
                result["analysis_limits"].append("import_directory_size_too_small")
                available_descriptors = 0
            count = min(import_size // 20 if import_size else available_descriptors, available_descriptors, 256)
            stream.seek(import_offset)
            for _ in range(count):
                descriptor = stream.read(20)
                if len(descriptor) != 20:
                    result["analysis_limits"].append("truncated_import_directory")
                    break
                original_thunk, stamp, chain, name_rva, first_thunk = struct.unpack("<IIIII", descriptor)
                if not any((original_thunk, stamp, chain, name_rva, first_thunk)):
                    break
                name_offset = rva_offset(name_rva)
                dll = read_c_string(name_offset) if name_offset is not None else ""
                imported = []
                thunk_rva = original_thunk or first_thunk
                thunk_size = 8 if bits == 64 else 4
                thunk_offset = rva_offset(thunk_rva, thunk_size)
                if thunk_offset is not None:
                    thunk_count = min(1024, rva_available(thunk_rva) // thunk_size)
                    for index in range(thunk_count):
                        item_offset = thunk_offset + index * thunk_size
                        stream.seek(item_offset)
                        item_raw = stream.read(thunk_size)
                        if len(item_raw) != thunk_size:
                            break
                        thunk = int.from_bytes(item_raw, "little")
                        if thunk == 0:
                            break
                        ordinal_flag = 1 << (bits - 1)
                        if thunk & ordinal_flag:
                            imported.append({"ordinal": thunk & 0xFFFF})
                        else:
                            hint_name_offset = rva_offset(thunk, 2)
                            if hint_name_offset is not None:
                                name = read_c_string(hint_name_offset + 2)
                                if name:
                                    imported.append({"name": name})
                        if len(imported) >= 1024:
                            result["analysis_limits"].append("import_symbol_limit_reached")
                            break
                if dll:
                    result["imports"].append({"library": dll, "symbols": imported})
                if len(result["imports"]) >= 128:
                    result["analysis_limits"].append("import_library_limit_reached")
                    break

    # IMAGE_DIRECTORY_ENTRY_EXPORT = 0. Export arrays are bounded by file size and caps.
    if directories:
        export_rva, export_size = directories[0]
        export_offset = rva_offset(export_rva, 40) if export_rva else None
        if export_rva and export_offset is None:
            result["analysis_limits"].append("export_directory_rva_invalid")
        elif export_offset is not None:
            stream.seek(export_offset)
            raw = stream.read(40)
            if len(raw) == 40:
                (_, _, _, _, name_rva, ordinal_base, function_count, name_count,
                 functions_rva, names_rva, ordinals_rva) = struct.unpack("<IIHHIIIIIII", raw)
                result["export_library"] = read_c_string(rva_offset(name_rva)) if rva_offset(name_rva) is not None else ""
                function_count = min(function_count, 10000)
                name_count = min(name_count, function_count, 10000)
                functions_offset = rva_offset(functions_rva, function_count * 4) if function_count else None
                names_offset = rva_offset(names_rva, name_count * 4) if name_count else None
                ordinals_offset = rva_offset(ordinals_rva, name_count * 2) if name_count else None
                name_by_index = {}
                if names_offset is not None and ordinals_offset is not None:
                    stream.seek(names_offset)
                    name_rvas_raw = stream.read(name_count * 4)
                    stream.seek(ordinals_offset)
                    ordinal_raw = stream.read(name_count * 2)
                    for index in range(min(len(name_rvas_raw) // 4, len(ordinal_raw) // 2)):
                        name_rva = struct.unpack_from("<I", name_rvas_raw, index * 4)[0]
                        ordinal_index = struct.unpack_from("<H", ordinal_raw, index * 2)[0]
                        name_pos = rva_offset(name_rva)
                        if name_pos is not None and ordinal_index < function_count:
                            name_by_index[ordinal_index] = read_c_string(name_pos)
                if functions_offset is not None:
                    stream.seek(functions_offset)
                    function_raw = stream.read(function_count * 4)
                    for index in range(len(function_raw) // 4):
                        function_rva = struct.unpack_from("<I", function_raw, index * 4)[0]
                        if function_rva:
                            item = {"ordinal": ordinal_base + index, "rva": hex(function_rva)}
                            if name_by_index.get(index):
                                item["name"] = name_by_index[index]
                            # Export RVAs within the export directory are forwarder strings.
                            if export_rva <= function_rva < export_rva + export_size:
                                forwarder_offset = rva_offset(function_rva)
                                if forwarder_offset is not None:
                                    item["forwarder"] = read_c_string(forwarder_offset)
                            result["exports"].append(item)
                if function_count >= 10000 or name_count >= 10000:
                    result["analysis_limits"].append("export_symbol_limit_reached")
    return result

def inspect_binary(path: str | Path, fmt: str | None = None) -> dict[str, Any]:
    """Read fixed-format headers only; no disassembly, dynamic loading, or execution."""
    target = Path(path)
    try:
        with target.open("rb") as stream:
            header = stream.read(64)
            if fmt == "PE/DOS" and header.startswith(b"MZ"):
                return _inspect_pe(stream, header)
            if fmt == "ELF" and header.startswith(b"\x7fELF"):
                return _inspect_elf(stream, header)
            macho = {
                b"\xfe\xed\xfa\xce": (">", 32),
                b"\xce\xfa\xed\xfe": ("<", 32),
                b"\xfe\xed\xfa\xcf": (">", 64),
                b"\xcf\xfa\xed\xfe": ("<", 64),
            }
            if fmt == "Mach-O" and header[:4] in macho:
                endian, bits = macho[header[:4]]
                header_size = 32 if bits == 64 else 28
                if len(header) < header_size:
                    return {"status": "truncated_mach_o_header", "format": "Mach-O"}
                file_size = os.fstat(stream.fileno()).st_size
                cpu, subtype, filetype, commands, command_bytes, flags = struct.unpack_from(endian + "IIIIII", header, 4)
                result = {
                    "status": "parsed", "format": "Mach-O", "bits": bits,
                    "endianness": "little" if endian == "<" else "big",
                    "architecture": MACHO_CPUS.get(cpu, f"cpu-{cpu}"),
                    "cpu_type": cpu, "cpu_subtype": subtype, "file_type": filetype,
                    "load_command_count": commands, "load_command_bytes": command_bytes,
                    "flags": flags, "dependencies": [], "rpaths": [], "analysis_limits": [],
                }
                if header_size > file_size or commands > 4096 or command_bytes > 16 * 1024 * 1024 or command_bytes > file_size - header_size:
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
                    if command_size < 8 or command_size > 1024 * 1024 or command_size > command_bytes - consumed:
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
    except (struct.error, OverflowError, ValueError, IndexError):
        return {"status": "malformed_binary_metadata", "format": fmt or observed_format}
    return {"status": "unsupported_or_unknown"}


def _sha256(path: Path) -> str | None:
    """Hash a stable regular-file observation; refuse files changed mid-read."""
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_HASH_BYTES:
                return None
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
        identity = _stat_identity(before)
        if (_stat_identity(after) != identity or _stat_identity(current) != identity
                or not stat.S_ISREG(current.st_mode)):
            return None
        return digest.hexdigest()
    except OSError:
        return None


def _sample_sha256(path: Path, file_size: int) -> str | None:
    """Fingerprint bounded file regions; this is not a full-content hash."""
    if file_size < 0 or SAMPLE_HASH_WINDOW_BYTES < 1:
        return None
    window = min(SAMPLE_HASH_WINDOW_BYTES, file_size)
    offsets = sorted({
        0,
        max(0, (file_size - window) // 2),
        max(0, file_size - window),
    })
    digest = hashlib.sha256()
    digest.update(b"mnemos-sampled-content-v1\0")
    digest.update(str(file_size).encode("ascii") + b"\0")
    try:
        with path.open("rb") as stream:
            for offset in offsets:
                stream.seek(offset)
                chunk = stream.read(window)
                if len(chunk) != window:
                    return None
                digest.update(str(offset).encode("ascii") + b"\0")
                digest.update(len(chunk).to_bytes(8, "big"))
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _cached_sha256(path: Path, info: os.stat_result, *, full_rehash: bool = False) -> str | None:
    """Reuse a hash only when file identity, size, mtime, and ctime all match."""
    if not stat.S_ISREG(info.st_mode):
        return None
    if full_rehash:
        return _sha256(path)
    if info.st_size > MAX_HASH_BYTES:
        return None
    try:
        key = str(path.resolve())
        cache = _get_cache()
        identity = _stat_identity(info)
        current = path.stat(follow_symlinks=False)
        if _stat_identity(current) != identity or not stat.S_ISREG(current.st_mode):
            cache.pop(key, None)
            return None
        cached = cache.get(key)
        if _cache_entry_valid(cached) and tuple(cached[field] for field in _CACHE_FIELDS) == identity:
            return cached["sha256"]
        digest = _sha256(path)
        if digest:
            cache[key] = {
                "dev": identity[0], "ino": identity[1], "size": identity[2],
                "mtime_ns": identity[3], "ctime_ns": identity[4],
                "sha256": digest, "at": time.time(),
            }
            _save_hash_cache(cache)
        else:
            cache.pop(key, None)
        return digest
    except (OSError, TypeError, ValueError):
        return _sha256(path)


def _artifact(path: Path, scan_status: dict[str, Any] | None = None, *, include_all_files: bool = False, full_rehash: bool = False) -> dict[str, Any] | None:
    try:
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            return None
        with path.open("rb") as stream:
            header = stream.read(4096)
        fmt = classify_binary(header)
        if not fmt and not include_all_files:
            return None
        digest = _cached_sha256(path, info, full_rehash=full_rehash)
        sample_digest = _sample_sha256(path, info.st_size) if digest is None and not full_rehash else None
        details = inspect_binary(path, fmt) if fmt else {
            "status": "not_binary", "format": "unknown", "static_inspection": True,
        }
        after = path.stat(follow_symlinks=False)
        changed_during_inspection = (
            info.st_dev != after.st_dev
            or info.st_ino != after.st_ino
            or info.st_size != after.st_size
            or info.st_mtime_ns != after.st_mtime_ns
            or getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000))
               != getattr(after, "st_ctime_ns", int(after.st_ctime * 1_000_000_000))
        )
        if changed_during_inspection:
            digest = None
            sample_digest = None
            details = {"status": "file_changed_during_inspection", "format": fmt}
            if scan_status is not None:
                scan_status.setdefault("file_errors", []).append({
                    "path": str(path), "error": "FileChangedDuringInspection",
                })
        elif full_rehash and digest is None:
            if scan_status is not None:
                scan_status.setdefault("file_errors", []).append({
                    "path": str(path), "error": "FullHashUnavailable",
                })
        ctime_ns = getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000))
        file_type = (
            "regular_file" if stat.S_ISREG(info.st_mode) else
            "directory" if stat.S_ISDIR(info.st_mode) else
            "symlink" if stat.S_ISLNK(info.st_mode) else
            "socket" if stat.S_ISSOCK(info.st_mode) else
            "fifo" if stat.S_ISFIFO(info.st_mode) else
            "character_device" if stat.S_ISCHR(info.st_mode) else
            "block_device" if stat.S_ISBLK(info.st_mode) else "unknown"
        )
        portable_stat = {
            "schema": "mnemos-file-metadata-v1",
            "file_type": file_type,
            "size_bytes": info.st_size,
            "mode": stat.S_IMODE(info.st_mode),
            "mtime_ns": info.st_mtime_ns,
            "ctime_ns": ctime_ns,
            "ctime_semantics": "platform_defined" if os.name == "nt" else "metadata_change_time",
            "uid": getattr(info, "st_uid", None),
            "gid": getattr(info, "st_gid", None),
            "device_number": getattr(info, "st_dev", None),
            "inode_number": getattr(info, "st_ino", None),
            "link_count": getattr(info, "st_nlink", None),
        }
        return {
            "evidence": {
                "schema": "mnemos-binary-evidence-v1",
                "method": "static-file-metadata",
                "source_path": str(path),
                "sha256": digest,
                "signature_status": details.get("signature_status","unknown"),
                "sample_sha256": sample_digest,
                "sample_hash_method": "first-middle-last-bounded-regions" if sample_digest else None,
                "file_size_bytes": info.st_size,
                "observed_mtime_ns": info.st_mtime_ns,
                "file_metadata": portable_stat,
                "parser": "mnemos-device-mapper",
                "hash_mode": "full_rehash" if full_rehash else "cached_bounded",
                "artifact_class": "binary" if fmt else "file",
                "execution_performed": False,
                "network_used": False,
            },
            "path": str(path),
            "name": path.name,
            "format": fmt or "unknown",
            "artifact_class": "binary" if fmt else "file",
            "size_bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "ctime_ns": ctime_ns,
            "mode": stat.S_IMODE(info.st_mode),
            "file_type": file_type,
            "uid": portable_stat["uid"],
            "gid": portable_stat["gid"],
            "device_number": portable_stat["device_number"],
            "inode_number": portable_stat["inode_number"],
            "link_count": portable_stat["link_count"],
            "file_metadata": portable_stat,
            "sha256": digest,
                "signature_status": details.get("signature_status","unknown"),
            "sample_sha256": sample_digest,
            "sample_hash_method": "first-middle-last-bounded-regions" if sample_digest else None,
            "observed_at_ns": time.time_ns(),
            "hash_skipped_reason": (
                "file changed during inspection"
                if changed_during_inspection else
                "file exceeds 256 MiB limit or could not be read"
                if digest is None else None
            ),
            "binary_details": details,
        }
    except OSError as exc:
        if scan_status is not None:
            scan_status.setdefault("file_errors", []).append({
                "path": str(path), "error": type(exc).__name__,
            })
        return None


def discover_artifacts(
    paths: Iterable[str | Path] = (), *, max_files: int = 2000,
    scan_status: dict[str, Any] | None = None, include_all_files: bool = False,
    full_rehash: bool = False,
) -> list[dict[str, Any]]:
    """Inspect only user-selected files/directories; bound work and do not follow symlinks."""
    if max_files < 1:
        raise ValueError("max_files must be positive")
    found: list[dict[str, Any]] = []
    examined = 0
    status = scan_status if scan_status is not None else {}
    status.update({
        "examined_files": 0, "limit_reached": False,
        "depth_limit_reached": False, "skipped_symlink_roots": 0,
        "traversal_errors": [], "file_errors": [],
    })
    roots = tuple(paths)
    if not roots:
        status["scope_missing"] = True
        status["complete"] = False
        status["traversal_errors"] = [{"path": None, "error": "NoExplicitScanScope"}]
        return found
    status["scope_missing"] = False
    for root_index, supplied in enumerate(roots):
        if examined >= max_files:
            status["limit_reached"] = True
            break
        supplied_path = Path(supplied).expanduser()
        if supplied_path.is_symlink():
            status["skipped_symlink_roots"] += 1
            continue
        root = supplied_path.resolve()
        if not root.exists():
            raise ValueError(f"scan path does not exist: {supplied}")
        candidates: Iterable[Path]
        if root.is_file():
            candidates = (root,)
        elif root.is_dir():
            def walk() -> Iterable[Path]:
                nonlocal examined
                def record_walk_error(error: OSError) -> None:
                    status["traversal_errors"].append({
                        "path": str(error.filename) if error.filename else None,
                        "error": type(error).__name__,
                    })
                for current, dirs, files in os.walk(root, followlinks=False, onerror=record_walk_error):
                    dirs[:] = sorted(d for d in dirs if (include_all_files or d not in SKIP_DIRS) and not (Path(current) / d).is_symlink())
                    depth = len(Path(current).relative_to(root).parts)
                    if depth >= 12:
                        if dirs:
                            status["depth_limit_reached"] = True
                        dirs[:] = []
                    for name in sorted(files):
                        if examined >= max_files:
                            status["limit_reached"] = True
                            return
                        examined += 1
                        yield Path(current) / name
            candidates = walk()
        else:
            continue
        for candidate in candidates:
            if root.is_file():
                examined += 1
            item = _artifact(candidate, scan_status=status, include_all_files=include_all_files, full_rehash=full_rehash)
            if item is not None:
                found.append(item)
            if examined >= max_files:
                # Probe the iterator once: reaching the exact budget is not truncation
                # unless another file or another requested root remains.
                if root_index < len(roots) - 1:
                    status["limit_reached"] = True
                else:
                    try:
                        next(candidates)
                    except StopIteration:
                        pass
                break
    status["examined_files"] = examined
    status["complete"] = not (
        status["limit_reached"] or status["depth_limit_reached"]
        or status["skipped_symlink_roots"] or status["traversal_errors"]
        or status["file_errors"]
    )
    # Stable ordering makes snapshots easy to compare and review.
    found.sort(key=lambda item: item["path"])
    return found


def collect_device_map(paths: Iterable[str | Path] = (), *, max_files: int = 2000,
                       war_mode: bool = False, full_rehash: bool = False) -> dict[str, Any]:
    """Collect an offline inventory. War mode hashes every regular file in scope."""

    paths = tuple(paths)
    uname = platform.uname()
    tools = {name: shutil.which(name) for name in TOOL_NAMES}
    prefix = os.environ.get("PREFIX", "")
    scan_status: dict[str, Any] = {}
    artifacts = discover_artifacts(paths, max_files=max_files, scan_status=scan_status,
                                   include_all_files=war_mode, full_rehash=(full_rehash or war_mode))
    return {
        "schema": "mnemos-device-map-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": {
            "os_type": _normalize_os_type()["normalized"],
            "sandbox_id": _detect_sandbox_id()["sandbox_id"],
            "sandbox_details": _detect_sandbox_id()["details"],

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
            "environment_class": _normalize_os_type()["normalized"],
            "os_family": _normalize_os_type()["family"],
            "os_raw": _normalize_os_type()["raw"],
            "available_tools": tools,
        },
        "scan": {
            "scope": [str(Path(path).expanduser().resolve()) for path in paths],
            "scope_missing": scan_status.get("scope_missing", False),
            "max_files": max_files,
            "complete": scan_status["complete"],
            "examined_files": scan_status["examined_files"],
            "limit_reached": scan_status["limit_reached"],
            "depth_limit_reached": scan_status["depth_limit_reached"],
            "skipped_symlink_roots": scan_status["skipped_symlink_roots"],
            "traversal_errors": scan_status["traversal_errors"],
            "file_errors": scan_status["file_errors"],
            "network_used": False,
            "executed_scanned_files": False,
            "war_mode": bool(war_mode),
            "hash_mode": "full_rehash_no_cache" if (full_rehash or war_mode) else "cached_bounded",
            "hash_cache_used": not (full_rehash or war_mode),
        },
        "artifacts": artifacts,
    }
