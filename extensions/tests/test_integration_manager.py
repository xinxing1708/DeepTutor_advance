"""Version-aware integration manager regression tests using only temporary targets."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration_manager import IntegrationError, run


def digest(data):
    return hashlib.sha256(data).hexdigest()


class IntegrationManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root, self.target = base / "extension", base / "package"
        self.root.mkdir()
        self.target.mkdir()
        self.version = "1.6.13"
        self.original, self.patched, self.added = b"upstream\n", b"extension\n", b"new module\n"
        self.manifest = {
            "foo.py": {"original": digest(self.original), "patched": digest(self.patched)},
            "new.py": {"original": None, "patched": digest(self.added)},
        }
        (self.root / f"integration-manifest-{self.version}.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )
        for directory, name, data in [
            ("upstream", "foo.py", self.original),
            ("patched", "foo.py", self.patched),
            ("patched", "new.py", self.added),
        ]:
            folder = self.root / f"{directory}-{self.version}"
            folder.mkdir(exist_ok=True)
            (folder / name).write_bytes(data)
        (self.target / "foo.py").write_bytes(self.original)

    def test_check_reports_original_and_missing_added_file_without_writing(self):
        result = run(self.root, self.target, self.version, "check")
        self.assertEqual(result, {"foo.py": "original", "new.py": "original"})
        self.assertEqual((self.target / "foo.py").read_bytes(), self.original)
        self.assertFalse((self.target / "new.py").exists())

    def test_apply_and_restore_handle_added_file(self):
        run(self.root, self.target, self.version, "apply")
        self.assertEqual((self.target / "foo.py").read_bytes(), self.patched)
        self.assertEqual((self.target / "new.py").read_bytes(), self.added)
        run(self.root, self.target, self.version, "restore")
        self.assertEqual((self.target / "foo.py").read_bytes(), self.original)
        self.assertFalse((self.target / "new.py").exists())

    def test_unknown_target_rejects_all_writes_before_apply(self):
        (self.target / "new.py").write_bytes(b"unrecognized")
        with self.assertRaisesRegex(IntegrationError, "Unrecognized changes"):
            run(self.root, self.target, self.version, "apply")
        self.assertEqual((self.target / "foo.py").read_bytes(), self.original)
        self.assertEqual((self.target / "new.py").read_bytes(), b"unrecognized")

    def test_status_is_read_only_even_for_unknown_file(self):
        (self.target / "foo.py").write_bytes(b"unexpected")
        result = run(self.root, self.target, self.version, "status")
        self.assertEqual(result["foo.py"], "unknown")
        self.assertEqual(result["new.py"], "original")
        self.assertEqual((self.target / "foo.py").read_bytes(), b"unexpected")

    def test_missing_version_snapshot_fails_closed(self):
        with self.assertRaisesRegex(IntegrationError, "No reviewed snapshot for DeepTutor 1.6.14"):
            run(self.root, self.target, "1.6.14", "apply")
        self.assertEqual((self.target / "foo.py").read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
