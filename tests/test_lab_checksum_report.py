import struct
import unittest
from native.build_view_restore_probe import ROOT, pefile
from tools.lab_hash_emulator import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP
from tools.lab_checksum_report import reconstruct


class ChecksumReportTests(unittest.TestCase):
    def test_matches_original_native_function_including_stack_pop(self):
        pe = pefile.PE(str(ROOT / 'runtime/package-v1/Game/Game.dll'))
        base = pe.OPTIONAL_HEADER.ImageBase
        for free in (29671, 0xffffffff):
            u = Uc(UC_ARCH_X86, UC_MODE_32)
            u.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
            u.mem_write(base, pe.get_memory_mapped_image())
            u.mem_map(0x1000000, 0x10000)
            def put(address, value):
                u.mem_write(address, struct.pack('<I', value))
            manager, handles, auxiliary, stack = 0x1000000, 0x1003000, 0x1004000, 0x1008000
            put(base + 0xab778c, handles)
            put(base + 0xab73d8, auxiliary)
            put(handles + 0x1c, 33640)
            put(handles + 0x40, free)
            put(handles + 0x50, 40839)
            put(manager + 0x1c70, 58925)
            raw = bytes.fromhex('5706d94b8454984c')
            u.mem_write(auxiliary, raw)
            put(stack, 0x100f000)
            u.reg_write(UC_X86_REG_ESP, stack)
            u.reg_write(UC_X86_REG_ECX, manager)
            # Replace the TLS lookup and component call only inside this emulator.
            # One present component returning 0x12345678 produces 0x91a2b3c0.
            u.mem_write(base + 0x4c34d0, b'\xb8\x00\x00\x00\x01\xc3')
            u.mem_write(base + 0x5e20, b'\xb8\xc0\xb3\xa2\x91\xc3')
            u.emu_start(base + 0x545840, 0x100f000, count=500)
            native = int.from_bytes(u.mem_read(manager + 0x1c64, 4), 'little')
            record = dict(full_agent_hash=0, components=[0x12345678] + [0]*63,
                          clock_ms=58925, handle_free=free, handle_count=33640,
                          handle_serial=40839)
            self.assertEqual(reconstruct(record, [0], raw), native)
            self.assertNotEqual(reconstruct(record, [0], bytes(8)), native)

    def test_rejects_unavailable_world_hash_and_bad_registry(self):
        with self.assertRaises(ValueError):
            reconstruct({'full_agent_hash': 1}, [], bytes(8))
        with self.assertRaises(ValueError):
            reconstruct({'full_agent_hash': 0}, [2, 2], bytes(8))
