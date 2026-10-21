from pathlib import Path
import json
import tempfile
import unittest

from recovery_lab.native_workspace import prepare


class NativeWorkspaceTests(unittest.TestCase):
    def test_staging_preserves_sources_and_refuses_modified_working_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "game"
            source.mkdir()
            for name in ("war3.exe", "game.dll", "Storm.dll"):
                (source / name).write_bytes(name.encode())
            manifest = prepare(source, root / "native")
            records = json.loads(manifest.read_text())["files"]
            for record in records:
                self.assertEqual(Path(record["backup"]).read_bytes(), record["name"].encode())
            work = Path(records[1]["working"])
            work.write_bytes(b"experimental change")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                prepare(source, root / "native")
            self.assertEqual(work.read_bytes(), b"experimental change")
            self.assertEqual((source / "game.dll").read_bytes(), b"game.dll")
