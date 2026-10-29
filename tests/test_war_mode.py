import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mnemos.device_mapper import collect_device_map
from mnemos import evidence_ledger


class WarModeTests(unittest.TestCase):
    def test_war_mode_hashes_text_and_binary_files_without_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            text_file = root / "settings.ini"
            text_file.write_text("mode=secure\n", encoding="utf-8")
            binary_file = root / "sample.elf"
            binary_file.write_bytes(b"\x7fELF" + b"payload")
            report = collect_device_map([root], war_mode=True)
            artifacts = {Path(item["path"]).name: item for item in report["artifacts"]}
            self.assertEqual(set(artifacts), {"settings.ini", "sample.elf"})
            self.assertEqual(len(artifacts["settings.ini"]["sha256"]), 64)
            self.assertEqual(artifacts["settings.ini"]["artifact_class"], "file")
            self.assertEqual(artifacts["sample.elf"]["artifact_class"], "binary")
            self.assertEqual(report["scan"]["hash_mode"], "full_rehash_no_cache")
            self.assertFalse(report["scan"]["hash_cache_used"])
            self.assertTrue(report["scan"]["complete"])

    def test_signed_ledger_detects_tampered_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(evidence_ledger, "LEDGER_PATH", root / "ledger.jsonl"), patch.object(
                evidence_ledger, "KEY_PATH", root / "keys" / "signing.pem"
            ):
                first = evidence_ledger.append_observation(
                    {"coverage_complete": True, "files_scanned": 2},
                    snapshot_id="snapshot-1", war_mode=True,
                )
                self.assertEqual(first["sequence"], 1)
                self.assertTrue(evidence_ledger.verify_ledger()["ok"])
                path = root / "ledger.jsonl"
                entry = json.loads(path.read_text(encoding="utf-8"))
                entry["observation"]["files_scanned"] = 999
                path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
                report = evidence_ledger.verify_ledger()
                self.assertFalse(report["ok"])
                self.assertTrue(any("hash mismatch" in error or "signature invalid" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
