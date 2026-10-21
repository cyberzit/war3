import json
from pathlib import Path
import struct
import tempfile
import unittest

from recovery_lab.offline import OfflineReplay
from recovery_lab.protocol import packet


class OfflineEvidenceTests(unittest.TestCase):
    def test_existing_journal_is_never_overwritten(self):
        from recovery_lab.proxy import LabProxy
        advertisement = packet(0x30, b"PX3W" + struct.pack("<III", 26, 2, 6439)
                               + b"LoD\0\0stat-string\0" + struct.pack("<IIIIIH", 10, 1, 1, 9, 1, 6200))
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "evidence.jsonl"
            journal.write_text("preserve this evidence\n")
            with self.assertRaises(FileExistsError):
                LabProxy(advertisement, journal=journal)
            self.assertEqual(journal.read_text(), "preserve this evidence\n")

    def test_source_cannot_be_used_as_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            original = '{"event":"local_disconnected"}\n'
            source.write_text(original)
            with self.assertRaisesRegex(ValueError, "overwrite"):
                OfflineReplay(b"", source, source)
            self.assertEqual(source.read_text(), original)

    def test_history_stops_at_first_disconnect(self):
        advertisement = packet(0x30, b"PX3W" + struct.pack("<III", 26, 2, 6439)
                               + b"LoD\0\0stat-string\0" + struct.pack("<IIIIIH", 10, 1, 1, 9, 1, 6200))
        first = packet(0x27, b"\0abcd")
        later = packet(0x27, b"\0wxyz")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            rows = [{"direction": "client", "packet": first.hex()},
                    {"event": "local_disconnected"},
                    {"direction": "client", "packet": later.hex()}]
            source.write_text("\n".join(map(json.dumps, rows)))
            proxy = OfflineReplay(advertisement, source, Path(directory) / "output.jsonl")
            try:
                self.assertEqual(proxy.gate.history, [b"abcd"])
            finally:
                proxy.journal.close()
