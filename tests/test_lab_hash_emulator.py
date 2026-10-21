import struct
import unittest
from tools.lab_hash_emulator import digest_components


class HashEmulatorTests(unittest.TestCase):
    def run_code(self, code):
        base, obj = 0x1000000, 0x2000000
        pages = {base: bytearray(4096), obj: bytearray(4096)}
        pages[base][0x100:0x100+len(code)] = code
        pages[obj][:4] = struct.pack('<I', 7)
        original = {k: bytes(v) for k,v in pages.items()}

        def read(address,size):
            page = address & ~4095
            if page not in pages:
                raise ValueError('Unmapped fixture page')
            return bytes(pages[page][address-page:address-page+size])

        result = digest_components(base, 0, [{'slot':0,'object':hex(obj),'method_rva':'0x100'}],read)
        self.assertEqual(original,{k:bytes(v)for k,v in pages.items()})
        return result['components'][0]

    def test_emulated_writes_never_change_source_process_memory(self):
        # mov dword ptr [ecx],42; mov eax,[ecx]; ret
        self.assertEqual(self.run_code(bytes.fromhex('c7012a0000008b01c3'))['digest'],42)

    def test_missing_memory_produces_error_not_invented_digest(self):
        # mov eax,[0x3000000]; ret
        result=self.run_code(bytes.fromhex('a100000003c3'))
        self.assertNotIn('digest',result)
        self.assertIn('error',result)

    def test_external_execution_is_rejected(self):
        # mov eax,0x2000000; jmp eax (fixture data is deliberately not code)
        result=self.run_code(bytes.fromhex('b800000002ffe0'))
        self.assertNotIn('digest',result)
        self.assertIn('External execution rejected',result['error'])

    def test_loop_stops_at_instruction_budget(self):
        result=self.run_code(bytes.fromhex('ebfe'))
        self.assertNotIn('digest',result)
        self.assertIn('budget exhausted',result['error'])
