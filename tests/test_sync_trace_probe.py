import struct
import unittest
from native.build_sync_trace_probe import build, ROOT, pefile, DATA_RVA, COMPONENT_HOOK, FINAL_HOOK, ALLOCATION_HOOK
from tools.lab_sync_trace import trace_snapshot, allocation_snapshot
from tools.lab_hash_emulator import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import *


class SyncTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/'runtime/package-v1/Game/Game.dll').read_bytes()
        cls.result,cls.meta=build(cls.source)

    def machine(self,binary):
        pe=pefile.PE(data=binary)
        base=pe.OPTIONAL_HEADER.ImageBase
        u=Uc(UC_ARCH_X86,UC_MODE_32)
        u.mem_map(base,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
        u.mem_write(base,pe.get_memory_mapped_image())
        u.mem_map(0x1000000,0x10000)
        u.mem_map(0x2000000,0x10000)
        for i,r in enumerate([UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_EDI,UC_X86_REG_EBP]):
            u.reg_write(r,0x123400+i)
        u.reg_write(UC_X86_REG_ESI,0x1006000)
        u.reg_write(UC_X86_REG_ESP,0x2008000)
        u.reg_write(UC_X86_REG_EFLAGS,0x602)
        return u,base

    def registers(self,u):
        return [u.reg_read(r)for r in [UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,
            UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EFLAGS]]

    def test_component_hook_preserves_native_result_and_flags(self):
        expected=None
        for binary in [self.source,self.result]:
            u,b=self.machine(binary)
            u.reg_write(UC_X86_REG_ESI,6)
            u.emu_start(b+COMPONENT_HOOK,b+COMPONENT_HOOK+5,count=100)
            state=self.registers(u)
            if expected is None:expected=state
            else:
                self.assertEqual(state,expected)
                self.assertEqual(int.from_bytes(u.mem_read(b+DATA_RVA+0x10+6*4,4),'little'),0x123400)

    def test_final_hook_captures_complete_state_without_changing_native_registers(self):
        expected=None
        for binary in [self.source,self.result]:
            u,b=self.machine(binary)
            def put(address,value):u.mem_write(address,struct.pack('<I',value))
            put(b+0xAB778C,0x1004000); put(b+0xAB65F4,0x1005000)
            put(b+0xAB73D8,0x1007000)
            u.mem_write(0x1007000,bytes(range(8)))
            put(0x2008000+8,0xabcdef01); put(0x2008000+0x18,0x456789ab)
            for offset,value in [(0x1c,100),(0x40,90),(0x50,101)]:put(0x1004000+offset,value)
            put(0x1005000+0x28,7)
            for offset,value in [(0x1c70,56725),(0x1c68,600),(0x2f8,0)]:put(0x1006000+offset,value)
            put(0x1001000+0x10,0x1002000);put(0x1002000+12,0x1003000)
            random=bytes(i%256 for i in range(360));u.mem_write(0x1003004,random)
            # Emulator-only replacement for TLS getter. Real game code remains original.
            u.mem_write(b+0x4c34d0,b'\xb8'+struct.pack('<I',0x1001000)+b'\xc3')
            if binary is self.result:
                u.mem_write(b+DATA_RVA+0x10,struct.pack('<64I',*range(64)))
            u.emu_start(b+FINAL_HOOK,b+FINAL_HOOK+6,count=1000)
            state=self.registers(u)
            if expected is None:expected=state
            else:
                self.assertEqual(state,expected)
                report=trace_snapshot(b,lambda a,n:bytes(u.mem_read(a,n)))
                row=report['records'][0]
                self.assertEqual((row['sequence'],row['checksum'],row['clock_ms'],row['frame_count']),(1,0x123403,56725,600))
                self.assertEqual(row['components'],list(range(64)))
                self.assertEqual(row['random_streams'],random.hex())
                self.assertEqual(row['component_aggregate'],0xabcdef01)
                self.assertEqual(row['auxiliary_digest'],0x456789ab)
                self.assertEqual(row['auxiliary_state'],bytes(range(8)).hex())
                self.assertEqual((row['handle_count'],row['handle_free'],row['handle_serial'],row['local_player']),(100,90,101,7))

    def test_unknown_image_rejected(self):
        with self.assertRaises(ValueError):build(b'unknown')

    def test_allocation_trace_preserves_result_and_bounds_stack_read(self):
        traced,_=build(self.source,allocations=True)
        for count,kind in ((3,0x68646c72),(48,0x68646c72),(48,0x2b6d6269)):
            expected=None
            for binary in (self.source,traced):
                u,b=self.machine(binary)
                u.mem_map(0,0x1000)
                u.mem_write(4,struct.pack('<I',0x2008000+count*4))
                values=[b+0x480666,b+0x480680,0x123456]+[0x345678]*45
                u.mem_write(0x2008000,struct.pack('<48I',*values))
                u.reg_write(UC_X86_REG_EAX,0x1008000)
                u.reg_write(UC_X86_REG_ECX,kind)
                u.emu_start(b+ALLOCATION_HOOK,b+ALLOCATION_HOOK+5,count=1000)
                state=self.registers(u)
                self.assertEqual(int.from_bytes(u.mem_read(0x1008010,4),'little'),kind)
                if expected is None:expected=state
                else:
                    self.assertEqual(state,expected)
                    report=allocation_snapshot(b,lambda a,n:bytes(u.mem_read(a,n)))
                    if kind==0x2b6d6269:
                        self.assertEqual(report,{'sequence':0,'records':[]})
                        continue
                    row=report['records'][0]
                    self.assertEqual((row['object'],row['kind']),('0x1008000','0x68646c72'))
                    self.assertEqual(len(row['stack']),count)
                    self.assertEqual(row['module_stack_candidates'],['0x480666','0x480680'])
