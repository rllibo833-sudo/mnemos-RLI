import tempfile
import unittest
from pathlib import Path

from mnemos.device_mapper import classify_binary, collect_device_map, discover_artifacts
from mnemos.store import MemoryStore


class DeviceMapperTests(unittest.TestCase):
    def test_classifies_common_binary_signatures(self):
        self.assertEqual(classify_binary(b"\x7fELF\x02\x01"), "ELF")
        self.assertEqual(classify_binary(b"MZ\x90\x00"), "PE/DOS")
        self.assertEqual(classify_binary(b"\xcf\xfa\xed\xfe"), "Mach-O")
        self.assertIsNone(classify_binary(b"ordinary text"))

    def test_scans_only_explicit_scope_and_hashes_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "sample.elf"
            binary.write_bytes(b"\x7fELF" + b"sample")
            (root / "notes.txt").write_text("not a binary", encoding="utf-8")
            result = discover_artifacts([root])
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["format"], "ELF")
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
