import tempfile
import unittest
from pathlib import Path

from recovery_lab.checkpoint_store import stage_checkpoint
from tests.test_save_checkpoint import fixture


class CheckpointStoreTests(unittest.TestCase):
    def test_identical_bytes_get_same_short_name_on_both_clients(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'GHost++ AutoSave Autosave Lab (ZEVB).w3z'
            source.write_bytes(fixture(True))
            a = stage_checkpoint(source, root / 'A')
            b = stage_checkpoint(source, root / 'B')
            self.assertEqual(a.name, b.name)
            self.assertLessEqual(len(a.name), 31)
            self.assertEqual(a.read_bytes(), source.read_bytes())
            self.assertEqual(stage_checkpoint(source, root / 'A'), a)

    def test_partial_save_never_published(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'partial.w3z'
            source.write_bytes(fixture(True)[:-3])
            with self.assertRaises(ValueError):
                stage_checkpoint(source, root / 'A')
            self.assertEqual(list((root / 'A').iterdir()), [])

    def test_existing_conflicting_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'source.w3z'
            source.write_bytes(fixture(True))
            target = stage_checkpoint(source, root / 'A')
            target.write_bytes(b'other data')
            with self.assertRaises(ValueError):
                stage_checkpoint(source, root / 'A')
            self.assertEqual(target.read_bytes(), b'other data')
