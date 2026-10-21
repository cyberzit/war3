import struct
import tempfile
import unittest
from pathlib import Path
import zlib

from recovery_lab.save_checkpoint import inspect_save


def fixture(flushed=False):
    slots = bytes([2, 100, 2, 0, 0, 1, 4, 1, 100,
                   3, 100, 2, 0, 1, 7, 8, 1, 100])
    raw = b'Maps\\Download\\Lab.w3x\0\0Match\0\0stats\0' + bytes(10)
    raw += b'\x02' + slots + struct.pack('<IBBI', 123, 0, 2, 456)
    if flushed:
        compressor = zlib.compressobj()
        packed = compressor.compress(raw) + compressor.flush(zlib.Z_SYNC_FLUSH)
    else:
        packed = zlib.compress(raw)
    block = struct.pack('<HHI', len(packed), len(raw), 0) + packed
    header = b'Warcraft III recorded game\x1a\0'
    header += struct.pack('<5I4sIHHII', 68, 68 + len(block), 1, len(raw), 1,
                          b'PX3W', 26, 6059, 0, 0, 0)
    return header + block


class CheckpointTests(unittest.TestCase):
    def inspect(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.w3z'
            path.write_bytes(data)
            return inspect_save(path)

    def test_stream_and_warcraft_sync_flush(self):
        for flushed in (False, True):
            with self.subTest(flushed=flushed):
                result = self.inspect(fixture(flushed))
                self.assertEqual([s['pid'] for s in result['slots']], [2, 3])
                self.assertEqual(result['magic'], 456)
                self.assertFalse(result['engine_state_or_rejoin_verified'])

    def test_truncated_save_rejected(self):
        data = fixture(True)
        for length in (0, 40, len(data) - 1, len(data) - 4):
            with self.subTest(length=length), self.assertRaises(ValueError):
                self.inspect(data[:length])

    def test_replay_rejected(self):
        data = bytearray(fixture())
        struct.pack_into('<H', data, 58, 0x8000)
        with self.assertRaises(ValueError):
            self.inspect(data)

    def test_broken_compressed_block_rejected(self):
        data = bytearray(fixture())
        data[76] = 0
        with self.assertRaises((ValueError, zlib.error)):
            self.inspect(data)

    def test_expansion_size_mismatch_rejected(self):
        data = bytearray(fixture())
        struct.pack_into('<H', data, 70, 1)
        with self.assertRaises(ValueError):
            self.inspect(data)


if __name__ == '__main__':
    unittest.main()
