import struct
import unittest
from native.build_handler_cache_restore import build, HOOK
from tests.test_sync_trace_probe import SyncTraceTests
from unicorn.x86_const import *


class HandlerCacheRestoreTests(unittest.TestCase):
    machine = SyncTraceTests.machine
    registers = SyncTraceTests.registers

    @classmethod
    def setUpClass(cls):
        from native.build_sync_trace_probe import ROOT
        cls.binary, _ = build((ROOT/'runtime/package-v1/Game/Game.dll').read_bytes())

    def fixture(self, matches=1, invalid=False):
        u, base = self.machine(self.binary)
        put = lambda a,v: u.mem_write(a,struct.pack('<I',v))
        put(base+0xAB778C,0x1000000)
        put(0x100001c,3);put(0x100000c,0x1001000)
        for index in range(3):
            obj=0x1002000+index*0x100
            wrapped=0x1003000+index*0x100
            put(0x1001000+index*8,0xfffffffe)
            put(0x1001004+index*8,obj)
            for offset,value in [(0xc,0x2b61676c),(0x10,0x68646c72),
                                 (0x14,index),(0x18,100+index),(0x54,wrapped)]:
                put(obj+offset,value)
            for offset,value in [(0,base+0x942a2c),(4,1),(0xc,index),(0x10,999 if invalid else 100+index),
                                 (0x24,8 if index<matches else 9)]:
                put(wrapped+offset,value)
        u.reg_write(UC_X86_REG_EBX,8)
        u.reg_write(UC_X86_REG_EDI,0x1004000)
        return u,base

    def test_exact_restored_handler_reuses_identity_and_acquires_cache_reference(self):
        u,b=self.fixture()
        before=bytes(u.mem_read(0x1001000,24))
        # Execute the real smart-pointer setter, not a mocked return.
        u.emu_start(b+HOOK,b+0x430aeb,count=1000)
        self.assertEqual(u.reg_read(UC_X86_REG_ESI),0x1003000)
        self.assertEqual(int.from_bytes(u.mem_read(0x1004018,4),'little'),0x1003000)
        self.assertEqual(int.from_bytes(u.mem_read(0x1003004,4),'little'),2)
        self.assertEqual(bytes(u.mem_read(0x1001000,24)),before)
        self.assertEqual(u.reg_read(UC_X86_REG_ESP),0x2008000)

    def test_absent_ambiguous_and_stale_identity_use_native_allocation(self):
        for matches,invalid in [(0,False),(2,False),(1,True)]:
            u,b=self.fixture(matches,invalid)
            before=self.registers(u)
            u.emu_start(b+HOOK,b+HOOK+6,count=1000)
            expected=before[:]
            expected[2]=0x2008000-4+0x58
            expected[7]-=4
            self.assertEqual(self.registers(u),expected)
            self.assertEqual(int.from_bytes(u.mem_read(0x1004018,4),'little'),0)
