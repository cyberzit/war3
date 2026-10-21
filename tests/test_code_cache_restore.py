import struct
import unittest
from native.build_code_cache_restore import build,HOOK
from tests.test_sync_trace_probe import SyncTraceTests
from unicorn.x86_const import *


class CodeCacheRestoreTests(SyncTraceTests):
    # Inherit the native preservation tests as well as the machine fixture.
    def test_restored_exact_callback_reuses_old_id_without_table_mutation(self):
        binary,_=build(self.source)
        u,base=self.machine(binary)
        vm,table,array=0x1000000,0x1004000,0x1005000
        put=lambda a,v:u.mem_write(a,struct.pack('<I',v))
        put(vm+0x2888,table);put(table+4,4);put(table+8,array)
        values=struct.pack('<4I',0,0x123450,0x234560,0x345670)
        u.mem_write(array,values)
        u.reg_write(UC_X86_REG_ESI,vm);u.reg_write(UC_X86_REG_EDI,0x234560)
        u.emu_start(base+HOOK,base+0x45ce7b,count=200)
        self.assertEqual(u.reg_read(UC_X86_REG_EAX),2)
        self.assertEqual(bytes(u.mem_read(array,16)),values)
        self.assertEqual(int.from_bytes(u.mem_read(table+4,4),'little'),4)

    def test_new_callback_and_oversize_table_keep_original_allocation_path(self):
        binary,_=build(self.source)
        for count in (3,65537):
            u,base=self.machine(binary)
            put=lambda a,v:u.mem_write(a,struct.pack('<I',v))
            put(0x1000000+0x2888,0x1004000);put(0x1000000+0x288c,0x1006000)
            put(0x1004004,count);put(0x1004008,0x1005000)
            u.reg_write(UC_X86_REG_ESI,0x1000000);u.reg_write(UC_X86_REG_EDI,0x234560)
            before=self.registers(u)
            u.emu_start(base+HOOK,base+HOOK+6,count=200)
            expected=before[:];expected[0]=0x1006000
            self.assertEqual(self.registers(u),expected)
