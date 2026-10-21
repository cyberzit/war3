import json
from pathlib import Path
import tempfile
import unittest

from recovery_lab.bundle import GAME_FILES, stage
from recovery_lab.native_workspace import digest


class BundleTests(unittest.TestCase):
    def test_allowlist_preserves_bytes_and_excludes_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "source"
            for name in GAME_FILES:
                path = game / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            (game / "private.log").write_text("not part of package")
            client = root / "client.exe"
            client.write_bytes(b"test client")
            destination = root / "package"
            records = stage(game, client, destination)
            self.assertEqual(len(records), 11)
            self.assertFalse((destination / "Game/private.log").exists())
            for record in records:
                self.assertEqual(digest(destination / record["path"]), record["sha256"])
            self.assertFalse(json.loads((destination / "manifest.json").read_text())["release_ready"])
            with self.assertRaises(FileExistsError):
                stage(game, client, destination)

    def test_missing_input_does_not_create_partial_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                stage(root, root / "missing.exe", root / "payload")
            self.assertFalse((root / "payload").exists())
