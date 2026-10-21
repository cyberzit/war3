"""Evaluate checksum methods on copied memory in an isolated x86 emulator.

The only connection to Warcraft is the supplied bounded read callback. There
is no remote execution, process write, injected thread, or checksum bypass.
Outputs are diagnostics; they do not authorize resuming the real match.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/tooldeps'))
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_UNMAPPED, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EAX, UC_X86_REG_EIP


def digest_components(base, root, components, read):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    stack, sentinel = 0xF0000000, 0xF0010000
    uc.mem_map(stack, 0x11000)
    mapped = set()
    errors = []

    def memory_fault(machine, access, address, size, value, user):
        page = address & ~4095
        if not 0x10000 <= page < 0x80000000 or len(mapped) >= 8192:
            errors.append(f'Bounded emulation rejected address {address:#x}')
            return False
        try:
            data = b''.join(read(page+offset, 1024) for offset in range(0,4096,1024))
            machine.mem_map(page, 4096)
            machine.mem_write(page, data)
            mapped.add(page)
            return True
        except (OSError, ValueError, UcError) as exc:
            errors.append(str(exc))
            return False

    def instruction(machine, address, size, user):
        if not base <= address < base+0x86C700:
            errors.append(f'External execution rejected: {address:#x}')
            machine.emu_stop()
        elif address == base+0x4C34D0:
            # Read the inspected game thread's TLS array, without calling OS.
            index = machine.reg_read(UC_X86_REG_ECX)
            if index >= 32:
                errors.append('Unexpected engine TLS index')
                machine.emu_stop()
                return
            value = int.from_bytes(read(root+4*index,4),'little')
            esp = machine.reg_read(UC_X86_REG_ESP)
            target = int.from_bytes(machine.mem_read(esp,4),'little')
            machine.reg_write(UC_X86_REG_EAX,value)
            machine.reg_write(UC_X86_REG_ESP,esp+4)
            machine.reg_write(UC_X86_REG_EIP,target)

    uc.hook_add(UC_HOOK_MEM_UNMAPPED,memory_fault)
    uc.hook_add(UC_HOOK_CODE,instruction)
    output = []
    for component in components:
        errors.clear()
        esp = stack+0x8000
        uc.mem_write(esp,struct.pack('<I',sentinel))
        uc.reg_write(UC_X86_REG_ESP,esp)
        uc.reg_write(UC_X86_REG_ECX,int(component['object'],16))
        row = {'slot':component['slot']}
        try:
            uc.emu_start(base+int(component['method_rva'],16),sentinel,timeout=1_000_000,count=200_000)
            if errors or uc.reg_read(UC_X86_REG_EIP) != sentinel:
                raise ValueError('; '.join(errors) or 'Emulation budget exhausted')
            row['digest'] = uc.reg_read(UC_X86_REG_EAX)
            if 'readonly_digest' in component and row['digest'] != component['readonly_digest']:
                raise ValueError('Emulated digest differs from direct read calculation')
        except (UcError,ValueError,OSError) as exc:
            row.pop('digest',None)
            row['error'] = str(exc)
            row['details'] = list(errors)
        output.append(row)
    return {'components':output,'copied_pages':len(mapped)}
