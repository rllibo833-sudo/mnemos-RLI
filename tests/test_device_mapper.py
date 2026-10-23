import contextlib
import io
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mnemos.cli import main
from mnemos.device_mapper import classify_binary, collect_device_map, discover_artifacts, inspect_binary
from mnemos.store import MemoryStore


class DeviceMapperTests(unittest.TestCase):
    def test_classifies_common_binary_signatures(self):
        self.assertEqual(classify_binary(b"\x7fELF\x02\x01"), "ELF")
        self.assertEqual(classify_binary(b"MZ\x90\x00"), "PE/DOS")
        self.assertEqual(classify_binary(b"\xcf\xfa\xed\xfe"), "Mach-O")
        self.assertIsNone(classify_binary(b"ordinary text"))

    def test_extracts_pe_section_and_import_library(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "minimal.exe"
            data = bytearray(0x400)
            data[:2] = b"MZ"
            struct.pack_into("<I", data, 0x3C, 0x80)
            data[0x80:0x84] = bytes((80, 69, 0, 0))
            struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 240, 0x2022)
            optional = 0x98
            struct.pack_into("<H", data, optional, 0x20B)
            struct.pack_into("<I", data, optional + 16, 0x1010)
            struct.pack_into("<Q", data, optional + 24, 0x140000000)
            struct.pack_into("<I", data, optional + 108, 16)
            struct.pack_into("<II", data, optional + 112 + 8, 0x1000, 40)
            section = optional + 240
            data[section:section + 8] = b".rdata\0\0"
            struct.pack_into("<IIII", data, section + 8, 0x200, 0x1000, 0x200, 0x200)
            struct.pack_into("<I", data, section + 36, 0x40000040)
            struct.pack_into("<IIIII", data, 0x200, 0, 0, 0, 0x1040, 0)
            data[0x240:0x24D] = b"KERNEL32.dll\0"
            path.write_bytes(data)
            details = inspect_binary(path, "PE/DOS")
            self.assertEqual(details["status"], "parsed")
            self.assertEqual(details["architecture"], "x86_64")
            self.assertEqual(details["sections"][0]["name"], ".rdata")
            self.assertEqual(details["imports"][0]["library"], "KERNEL32.dll")

    def test_extracts_pe_export_name_and_ordinal(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "exports.exe"
            data = bytearray(0x400)
            data[:2] = b"MZ"
            struct.pack_into("<I", data, 0x3C, 0x80)
            data[0x80:0x84] = bytes((80, 69, 0, 0))
            struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 240, 0x2022)
            optional = 0x98
            struct.pack_into("<H", data, optional, 0x20B)
            struct.pack_into("<I", data, optional + 16, 0x1010)
            struct.pack_into("<Q", data, optional + 24, 0x140000000)
            struct.pack_into("<I", data, optional + 108, 16)
            struct.pack_into("<II", data, optional + 112, 0x1000, 40)
            section = optional + 240
            data[section:section + 8] = b".rdata\x00\x00"
            struct.pack_into("<IIII", data, section + 8, 0x200, 0x1000, 0x200, 0x200)
            struct.pack_into("<I", data, section + 36, 0x40000040)
            struct.pack_into("<IIHHIIIIIII", data, 0x200, 0, 0, 0, 0, 0x1050, 1, 1, 1, 0x1040, 0x1044, 0x1048)
            struct.pack_into("<I", data, 0x240, 0x1070)
            struct.pack_into("<I", data, 0x244, 0x1060)
            struct.pack_into("<H", data, 0x248, 0)
            data[0x250:0x25B] = b"sample.dll\x00"
            data[0x260:0x26E] = b"ExportedEntry\x00"
            path.write_bytes(data)
            details = inspect_binary(path, "PE/DOS")
            self.assertEqual(details["status"], "parsed")
            self.assertEqual(details["export_library"], "sample.dll")
            self.assertEqual(details["exports"][0]["name"], "ExportedEntry")
            self.assertEqual(details["exports"][0]["ordinal"], 1)
            self.assertEqual(details["exports"][0]["rva"], "0x1070")

    def test_extracts_elf_header_metadata_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "minimal.elf"
            header = bytearray(64)
            header[:4] = b"\x7fELF"
            header[4] = 2  # ELF64
            header[5] = 1  # little endian
            import struct
            struct.pack_into("<HHIQQQIHHHHHH", header, 16, 2, 62, 1, 0x400000, 64, 0, 0, 64, 56, 0, 64, 0, 0)
            path.write_bytes(header)
            details = inspect_binary(path, "ELF")
            self.assertEqual(details["status"], "parsed")
            self.assertEqual(details["architecture"], "x86_64")
            self.assertEqual(details["object_type"], "executable")
            self.assertEqual(details["entry_point"], "0x400000")
            self.assertEqual(details["section_count"], 0)


    def test_extracts_elf_sections_and_symbols(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "symbols.elf"
            header = bytearray(64)
            header[:4] = bytes((127, 69, 76, 70))
            header[4:6] = bytes((2, 1))
            shstr = bytes((0,)) + b".shstrtab" + bytes((0,)) + b".strtab" + bytes((0,)) + b".symtab" + bytes((0,)) + b".text" + bytes((0,))
            strtab = bytes((0,)) + b"demo_function" + bytes((0,))
            symtab = struct.pack("<IBBHQQ", 0, 0, 0, 0, 0, 0) + struct.pack("<IBBHQQ", 1, 0x12, 0, 4, 0x401000, 12)
            offset_shstr = 64
            offset_strtab = offset_shstr + len(shstr)
            offset_symtab = offset_strtab + len(strtab)
            offset_text = offset_symtab + len(symtab)
            offset_sections = (offset_text + 16 + 7) & ~7
            path.write_bytes(b"")
            # ELF64 header and four non-null section headers.
            struct.pack_into("<HHIQQQIHHHHHH", header, 16, 2, 62, 1, 0x401000, 0, offset_sections, 0, 64, 56, 0, 64, 5, 1)
            sections = [bytes(64)]
            sections.append(struct.pack("<IIQQQQIIQQ", 1, 3, 0, 0, offset_shstr, len(shstr), 0, 0, 1, 0))
            sections.append(struct.pack("<IIQQQQIIQQ", 11, 3, 0, 0, offset_strtab, len(strtab), 0, 0, 1, 0))
            sections.append(struct.pack("<IIQQQQIIQQ", 19, 2, 0, 0, offset_symtab, len(symtab), 2, 1, 8, 24))
            sections.append(struct.pack("<IIQQQQIIQQ", 27, 1, 6, 0x401000, offset_text, 16, 0, 0, 16, 0))
            data = bytearray(offset_sections + 5 * 64)
            data[:64] = header
            data[offset_shstr:offset_shstr + len(shstr)] = shstr
            data[offset_strtab:offset_strtab + len(strtab)] = strtab
            data[offset_symtab:offset_symtab + len(symtab)] = symtab
            data[offset_text:offset_text + 16] = bytes((0x90,)) * 16
            for index, section in enumerate(sections):
                start = offset_sections + index * 64
                data[start:start + 64] = section
            path.write_bytes(data)
            details = inspect_binary(path, "ELF")
            self.assertEqual(details["status"], "parsed")
            self.assertIn(".text", [section["name"] for section in details["sections"]])
            symbol = next(symbol for symbol in details["symbols"] if symbol["name"] == "demo_function")
            self.assertEqual(symbol["value"], "0x401000")
            self.assertEqual(symbol["size_bytes"], 12)

    def test_extracts_elf_dynamic_dependencies_and_runpath(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dynamic.elf"
            data = bytearray(0x300)
            data[:6] = b"\x7fELF\x02\x01"
            # ELF64 header with two program headers and no section table.
            struct.pack_into("<HHIQQQIHHHHHH", data, 16, 3, 62, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
            # PT_LOAD maps virtual address 0x400000 to file offset 0.
            struct.pack_into("<IIQQQQQQ", data, 64, 1, 4, 0, 0x400000, 0, len(data), len(data), 0x1000)
            # PT_DYNAMIC at file offset 0x100, virtual address 0x400100.
            struct.pack_into("<IIQQQQQQ", data, 120, 2, 4, 0x100, 0x400100, 0, 80, 80, 8)
            entries = [
                (1, 1), (5, 0x400180), (10, 32), (29, 12), (0, 0),
            ]
            for i, (tag, value) in enumerate(entries):
                struct.pack_into("<qQ", data, 0x100 + i * 16, tag, value)
            strings = b"\x00libdemo.so\x00$ORIGIN/lib\x00"
            data[0x180:0x180 + len(strings)] = strings
            path.write_bytes(data)
            details = inspect_binary(path, "ELF")
            self.assertEqual(details["status"], "parsed")
            self.assertEqual(details["dynamic_status"], "parsed")
            self.assertEqual(details["dependencies"], [{"name": "libdemo.so", "kind": "needed"}])
            self.assertEqual(details["runpaths"], ["$ORIGIN/lib"])

    def test_map_device_reuses_runtime_dependency_nodes_between_scans(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "dynamic.elf"
            data = bytearray(0x300)
            data[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<HHIQQQIHHHHHH", data, 16, 3, 62, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
            struct.pack_into("<IIQQQQQQ", data, 64, 1, 4, 0, 0x400000, 0, len(data), len(data), 0x1000)
            struct.pack_into("<IIQQQQQQ", data, 120, 2, 4, 0x100, 0x400100, 0, 80, 80, 8)
            entries = [(1, 1), (5, 0x400180), (10, 32), (0, 0)]
            for i, (tag, value) in enumerate(entries):
                struct.pack_into("<qQ", data, 0x100 + i * 16, tag, value)
            strings = b"\x00libshared.so\x00"
            data[0x180:0x180 + len(strings)] = strings
            path.write_bytes(data)
            database = root / "memory.sqlite3"
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--db", str(database), "map-device", "--path", str(path)]), 0)
            copy_path = root / "dynamic-copy.elf"
            copy_path.write_bytes(data)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--db", str(database), "map-device", "--path", str(root)]), 0)
            data[0x2F0] = 0xA5
            path.write_bytes(data)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--db", str(database), "map-device", "--path", str(root)]), 0)
            store = MemoryStore(database)
            memories = store.list(limit=10000)
            dependencies = [item for item in memories if item["kind"] == "runtime_dependency"]
            artifacts = [item for item in memories if item["kind"] == "binary_artifact"]
            self.assertEqual(len(dependencies), 1)
            self.assertEqual(len(artifacts), 3)
            self.assertEqual(len([item for item in memories if item["kind"] == "device_snapshot"]), 3)
            dependency_links = [link for link in store.links() if link["relation"] == "depends_on"]
            self.assertEqual(len(dependency_links), 3)
            superseded_links = [link for link in store.links() if link["relation"] == "superseded_by"]
            self.assertEqual(len(superseded_links), 1)
            self.assertEqual(dependencies[0]["metadata"]["name"], "libshared.so")
            evidence_sources = dependencies[0]["metadata"]["evidence_sources"]
            self.assertEqual(len(evidence_sources), 3)
            self.assertEqual(len({(item["artifact_path"], item["artifact_sha256"]) for item in evidence_sources}), 3)

    def test_malformed_binary_headers_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            elf = root / "truncated.elf"
            elf.write_bytes(b"\x7fELF\x02\x01")
            self.assertEqual(inspect_binary(elf, "ELF")["status"], "invalid_elf_header")

            pe = root / "bad-offset.exe"
            header = bytearray(64)
            header[:2] = b"MZ"
            struct.pack_into("<I", header, 0x3C, 0xFFFFFFF0)
            pe.write_bytes(header)
            self.assertEqual(inspect_binary(pe, "PE/DOS")["status"], "invalid_pe_offset")

            macho = root / "truncated.macho"
            macho.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 24)
            self.assertEqual(inspect_binary(macho, "Mach-O")["status"], "truncated_mach_o_header")

    def test_scans_only_explicit_scope_and_hashes_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "sample.elf"
            binary.write_bytes(b"\x7fELF" + b"sample")
            (root / "notes.txt").write_text("not a binary", encoding="utf-8")
            result = discover_artifacts([root])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "ELF")
            link = root / "linked.elf"
            try:
                link.symlink_to(binary)
            except OSError:
                pass
            else:
                self.assertEqual(discover_artifacts([link]), [])
            self.assertEqual(result[0]["binary_details"]["status"], "invalid_elf_header")
            self.assertEqual(len(result[0]["sha256"]), 64)

    def test_scan_budget_marks_directory_inventory_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("a.elf", "b.elf"):
                (root / name).write_bytes(b"\x7fELF" + name.encode("ascii"))
            report = collect_device_map([root], max_files=1)
            self.assertFalse(report["scan"]["complete"])
            self.assertTrue(report["scan"]["limit_reached"])
            self.assertEqual(report["scan"]["examined_files"], 1)

    def test_skipped_symlink_root_marks_inventory_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.elf"
            target.write_bytes(b"\x7fELFfixture")
            link = root / "linked.elf"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            report = collect_device_map([link])
            self.assertFalse(report["scan"]["complete"])
            self.assertEqual(report["scan"]["skipped_symlink_roots"], 1)

    def test_single_explicit_file_scan_is_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "single.elf"
            path.write_bytes(b"\x7fELFfixture")
            report = collect_device_map([path])
            self.assertTrue(report["scan"]["complete"])
            self.assertEqual(report["scan"]["examined_files"], 1)


    def test_sample_fingerprint_distinguishes_oversized_files_with_preserved_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "large.elf"
            original_bytes = bytearray(b"\\x7fELF" + b"A" * 251)
            path.write_bytes(original_bytes)
            original = path.stat()
            database = root / "memory.sqlite3"
            with patch("mnemos.device_mapper.MAX_HASH_BYTES", 64), patch(
                "mnemos.device_mapper.SAMPLE_HASH_WINDOW_BYTES", 64
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--db", str(database), "map-device", "--path", str(path)]), 0)
                first_observation = collect_device_map([path])["artifacts"][0]
                self.assertIsNone(first_observation["sha256"])
                self.assertIsNotNone(first_observation["sample_sha256"])
                self.assertEqual(first_observation["sample_hash_method"], "first-middle-last-bounded-regions")

                changed_bytes = bytearray(original_bytes)
                changed_bytes[8] = ord("B")
                path.write_bytes(changed_bytes)
                os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--db", str(database), "map-device", "--path", str(path)]), 0)

            store = MemoryStore(database)
            artifacts = [item for item in store.list(limit=10000) if item["kind"] == "binary_artifact"]
            self.assertEqual(len(artifacts), 2)
            self.assertEqual(len({item["metadata"]["sample_sha256"] for item in artifacts}), 2)

    def test_device_map_persists_offline_snapshot_and_artifact_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "sample.elf"
            binary.write_bytes(b"\x7fELF" + b"fixture")
            store = MemoryStore(root / "memory.sqlite3")
            report = collect_device_map([binary])
            snapshot = store.add(
                "Offline device map",
                kind="device_snapshot",
                source="mnemos-device-mapper",
                metadata=report,
            )
            self.assertEqual(report["schema"], "mnemos-device-map-v1")
            self.assertFalse(report["scan"]["network_used"])
            artifact = report["artifacts"][0]
            record = store.add(
                f"Binary artifact: {artifact['path']}",
                kind="binary_artifact",
                source="mnemos-device-mapper",
                metadata=artifact,
            )
            self.assertEqual(store.link(snapshot["id"], record["id"], relation="contains_artifact")["relation"],
                             "contains_artifact")
            self.assertEqual(store.get(snapshot["id"])["metadata"]["artifacts"][0]["format"], "ELF")


if __name__ == "__main__":
    unittest.main()
