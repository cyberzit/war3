"""Binary patch boundaries; live behaviour is separately tested in two clients."""
import struct
import unittest
from native import build_view_restore_probe as probe


class ViewRestoreProbeTests(unittest.TestCase):
    def test_refresh_only_skips_ownership_loop_and_preserves_native_tail(self):
        source = (probe.ROOT / 'runtime/package-v1/Game/game.dll').read_bytes()
        ordinary, _ = probe.build(source)
        result, _ = probe.build(source, refresh_only=True)
        pe = probe.pefile.PE(data=result)
        offset = pe.get_offset_from_rva(0x2FCBF3)
        self.assertTrue(all(a == b or offset <= i < offset+5
                            for i, (a, b) in enumerate(zip(ordinary, result))))
        self.assertEqual(0x2FCBF8 + struct.unpack('<i', pe.get_data(0x2FCBF4, 4))[0], 0x2FCCC6)

    def test_unknown_binary_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.build(b'unknown')

    def test_patch_is_confined_and_preserves_relocations_and_sync_checks(self):
        source = (probe.ROOT / 'runtime/package-v1/Game/game.dll').read_bytes()
        result, meta = probe.build(source)
        before = probe.pefile.PE(data=source)
        after = probe.pefile.PE(data=result)
        self.assertEqual(len(source), len(result))
        hook = before.get_offset_from_rva(probe.HOOK)
        cave = before.get_offset_from_rva(meta['stub_rva'])
        size = before.sections[0].get_file_offset() + 8
        allowed = set(range(hook, hook + 5)) | set(range(cave, cave + meta['stub_size'])) | set(range(size, size + 4))
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result))))
        self.assertEqual(after.get_data(probe.HOOK, 1), b'\xe9')
        self.assertEqual(probe.RETURN + struct.unpack('<i', after.get_data(probe.HOOK + 1, 4))[0], meta['stub_rva'])
        self.assertEqual(after.get_data(0x67E704, 6), before.get_data(0x67E704, 6))
        self.assertEqual(before.sections[-1].get_data(), after.sections[-1].get_data())
        code = bytes.fromhex(meta['stub_hex'])
        self.assertEqual(meta['stub_rva'] + 5 + struct.unpack('<i', code[1:5])[0], 0x7E1059)
        self.assertEqual(meta['stub_rva'] + len(code) + struct.unpack('<i', code[-4:])[0], probe.RETURN)
