import struct
import unittest
from native.build_code_cache_restore import build, HOOK
from tests.test_sync_trace_probe import SyncTraceTests
from unicorn.x86_const import *


class CheckpointCodeRebindTests(unittest.TestCase):
    machine=SyncTraceTests.machine

    @classmethod
    def setUpClass(cls):
        from native.build_sync_trace_probe import ROOT
        cls.pattern=[0x0c010900,0x1007000,0x11010000,0xfcc,0x0c010a00,0x1007000,0x11010000,0xfce]
        cls.binary,_=build((ROOT/'runtime/package-v1/Game/Game.dll').read_bytes(),
            restored_codes=[{'key':3,'words':cls.pattern,'process_address_words':[1,5]}])

    def test_missing_code_restored_only_with_exact_descriptor_and_valid_relocation(self):
        for mode in ('valid','occupied','mismatch','bad_pointer'):
            u,b=self.machine(self.binary)
            put=lambda a,v:u.mem_write(a,struct.pack('<I',v))
            put(0x1000000+0x2888,0x1004000);put(0x1000000+0x288c,0x1006000)
            put(0x1004004,4);put(0x1004008,0x1005000)
            if mode=='occupied':put(0x100500c,0x1007200)
            words=self.pattern[:];words[1]=words[5]=0x1007100
            if mode=='mismatch':words[3]^=1
            if mode=='bad_pointer':words[5]+=4
            u.mem_write(0x1007000,struct.pack('<8I',*words))
            u.reg_write(UC_X86_REG_ESI,0x1000000);u.reg_write(UC_X86_REG_EDI,0x1007000)
            u.emu_start(b+HOOK,b+(0x45ce7b if mode=='valid' else HOOK+6),count=1000)
            self.assertEqual(int.from_bytes(u.mem_read(0x100500c,4),'little'),
                0x1007000 if mode=='valid' else 0x1007200 if mode=='occupied' else 0)
            self.assertEqual(u.reg_read(UC_X86_REG_EAX),3 if mode=='valid' else 0x1006000)
