import struct
import tempfile
import unittest
from pathlib import Path

from mnemos.device_mapper import classify_binary, collect_device_map, discover_artifacts, inspect_binary
from mnemos.store import MemoryStore


class DeviceMapperTests(unittest.TestCase):
    def test_classifies_common_binary_signatures(self):
        self.assertEqual(classify_binary(b"\x7fELF\x02\x01"), "ELF")
        self.assertEqual(classify_binary(b"MZ\x90\x00"), "PE/DOS")
        self.assertEqual(classify_binary(b"\xcf\xfa\xed\xfe"), "Mach-O")
        self.assertIsNone(classify_binary(b"ordinary text"))

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
            shstr = b"\\0.shstrtab\\0.strtab\\0.symtab\\0.text\\0"
            strtab = b"\\0demo_function\\0"
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
            data[offset_text:offset_text + 16] = b"\\x90" * 16
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

    def test_scans_only_explicit_scope_and_hashes_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "sample.elf"
            binary.write_bytes(b"\x7fELF" + b"sample")
            (root / "notes.txt").write_text("not a binary", encoding="utf-8")
            result = discover_artifacts([root])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "ELF")
            self.assertEqual(result[0]["binary_details"]["status"], "invalid_elf_header")
            self.assertEqual(len(result[0]["sha256"]), 64)

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
