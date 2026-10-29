import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from mnemos.cli import _load_release_manifest, _verify_release_manifest_disk


class ReleaseDiskVerificationTests(unittest.TestCase):
    def _manifest_file(self, root: Path, digest: str) -> Path:
        manifest = {
            "schema": "mnemos-release-manifest-v1",
            "release_id": "test-release",
            "artifact_count": 1,
            "artifacts": [{"path": "bin/tool.dat", "sha256": digest}],
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_disk_verification_hashes_actual_bytes_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "root"
            (root / "bin").mkdir(parents=True)
            target = root / "bin" / "tool.dat"
            target.write_bytes(b"known-good")
            manifest_path = self._manifest_file(base, hashlib.sha256(b"known-good").hexdigest())
            manifest = _load_release_manifest(str(manifest_path))
            self.assertEqual(_verify_release_manifest_disk(manifest, str(root))["status"], "match")
            target.write_bytes(b"tampered")
            report = _verify_release_manifest_disk(manifest, str(root))
            self.assertEqual(report["status"], "different")
            self.assertEqual(report["counts"]["different"], 1)

    def test_disk_verification_reports_missing_and_unexpected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "root"
            root.mkdir()
            (root / "extra.txt").write_text("extra", encoding="utf-8")
            manifest_path = self._manifest_file(base, hashlib.sha256(b"expected").hexdigest())
            report = _verify_release_manifest_disk(_load_release_manifest(str(manifest_path)), str(root))
            self.assertEqual(report["status"], "different")
            self.assertEqual(report["counts"]["missing"], 1)
            self.assertEqual(report["counts"]["unexpected"], 1)

    def test_disk_verification_rejects_symlink_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "root"
            root.mkdir()
            outside = base / "outside.dat"
            outside.write_bytes(b"secret")
            (root / "tool.dat").symlink_to(outside)
            manifest = {"release_id": "test", "artifacts": [{"path": "tool.dat", "sha256": hashlib.sha256(b"secret").hexdigest()}]}
            report = _verify_release_manifest_disk(manifest, str(root))
            self.assertEqual(report["status"], "different")
            self.assertEqual(report["artifacts"][0]["status"], "unsafe_symlink")

    def test_manifest_rejects_windows_backslash_path(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            path = self._manifest_file(base, "a" * 64)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["artifacts"][0]["path"] = r"..\\outside.dat"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "safe relative path"):
                _load_release_manifest(str(path))


if __name__ == "__main__":
    unittest.main()