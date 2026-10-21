"""Pinned lab: reconnect restored CCode objects to the native lookup cache.

Only a unique, active, identity-consistent handler may be reused. The normal
native smart-pointer setter acquires the cache reference. No allocator edits,
checksum changes, or guessed cross-process pointers are used.
"""
import struct
from native.build_code_cache_restore import build as code_build
from native.build_sync_trace_probe import Code, pefile, ROOT

HOOK = 0x430a2f
HOOK_FILTER = 0x430b9f


def build(source, restored_codes=()):
    binary, metadata = code_build(source, restored_codes=restored_codes)
    output = bytearray(binary)
    pe = pefile.PE(data=binary)
    section = pe.sections[0]
    code = Code((section.VirtualAddress + section.Misc_VirtualSize + 15) & ~15)
    labels, jumps = {}, []
    def label(name): labels[name] = len(code.data)
    def jump(op, name):
        code.emit(op)
        jumps.append((len(code.data), name))
        code.u32(0)
    assert pe.get_data(HOOK, 6) == bytes.fromhex('6a008d4c2458')
    code.emit('9c60')
    code.module_base_ebp()
    code.emit('8b85'); code.u32(0xAB778C)  # native allocator
    code.emit('8b481c 81f900001000'); jump('0f87', 'fallback')
    code.emit('8b500c 31ff 31f6')  # table EDX, index EDI, match ESI
    label('loop')
    code.emit('3bf9'); jump('0f83', 'done')
    code.emit('833cfa fe'); jump('0f85', 'next')
    code.emit('8b44fa04 81780c6c67612b'); jump('0f85', 'next')
    code.emit('817810726c6468'); jump('0f85', 'next')
    code.emit('83782000'); jump('0f85', 'next')
    code.emit('397814'); jump('0f85', 'next')
    code.emit('50 8b4054 85c0'); jump('0f84', 'pop_next')
    code.emit('395824'); jump('0f85', 'pop_next')  # exact native code key
    code.emit('39780c'); jump('0f85', 'pop_next')
    code.emit('55 8b6c2404 8b6d18 396810 5d'); jump('0f85', 'pop_next')
    code.emit('85f6'); jump('0f85', 'ambiguous')
    code.emit('8bf0')
    label('pop_next'); code.emit('58')
    label('next'); code.emit('47'); jump('e9', 'loop')
    label('ambiguous'); code.emit('58'); jump('e9', 'fallback')
    label('done'); code.emit('85f6'); jump('0f84', 'fallback')
    code.emit('89742404 619d')  # restore regs except ESI=existing CCode
    code.emit('56 8d4f18'); code.branch(0xe8, 0x3b54d0)
    code.branch(0xe9, 0x430aeb)  # original borrowed-result epilogue
    label('fallback'); code.emit('619d 6a008d4c2458')
    code.branch(0xe9, HOOK+6)
    for offset, name in jumps:
        struct.pack_into('<i', code.data, offset, labels[name]-offset-4)
    offset = pe.get_offset_from_rva(code.rva)
    assert offset+len(code.data) <= section.PointerToRawData+section.SizeOfRawData
    assert not any(output[offset:offset+len(code.data)])
    output[offset:offset+len(code.data)] = code.data
    offset = pe.get_offset_from_rva(HOOK)
    output[offset:offset+6] = b'\xe9'+struct.pack('<i',code.rva-HOOK-5)+b'\x90'

    code2 = Code((code.rva + len(code.data) + 15) & ~15)
    labels2, jumps2 = {}, []
    def label2(name): labels2[name] = len(code2.data)
    def jump2(op, name):
        code2.emit(op)
        jumps2.append((len(code2.data), name))
        code2.u32(0)
    assert pe.get_data(HOOK_FILTER, 6) == bytes.fromhex('6a008d4c2458')
    code2.emit('9c60')
    code2.module_base_ebp()
    code2.emit('8b85'); code2.u32(0xAB778C)  # native allocator
    code2.emit('8b481c 81f900001000'); jump2('0f87', 'fallback')
    code2.emit('8b500c 31ff 31f6')  # table EDX, index EDI, match ESI
    label2('loop')
    code2.emit('3bf9'); jump2('0f83', 'done')
    code2.emit('833cfa fe'); jump2('0f85', 'next')
    code2.emit('8b44fa04 81780c6c67612b'); jump2('0f85', 'next')
    code2.emit('817810746c662b'); jump2('0f85', 'next')  # '+flt'
    code2.emit('83782000'); jump2('0f85', 'next')
    code2.emit('397814'); jump2('0f85', 'next')
    code2.emit('50 8b4054 85c0'); jump2('0f84', 'pop_next')
    code2.emit('55 8b6824 85ed 5d'); jump2('0f84', 'pop_next')
    code2.emit('55 8b6824 395d24 5d'); jump2('0f85', 'pop_next')
    code2.emit('39780c'); jump2('0f85', 'pop_next')
    code2.emit('55 8b6c2404 8b6d18 396810 5d'); jump2('0f85', 'pop_next')
    code2.emit('85f6'); jump2('0f85', 'ambiguous')
    code2.emit('8bf0')
    label2('pop_next'); code2.emit('58')
    label2('next'); code2.emit('47'); jump2('e9', 'loop')
    label2('ambiguous'); code2.emit('58'); jump2('e9', 'fallback')
    label2('done'); code2.emit('85f6'); jump2('0f84', 'fallback')
    code2.emit('89742404 619d')  # restore regs except ESI=existing CFilterFunc
    code2.emit('56 8d4f18'); code2.branch(0xe8, 0x3b6040)
    code2.branch(0xe9, 0x430c5d)  # original borrowed-result epilogue
    label2('fallback'); code2.emit('619d 6a008d4c2458')
    code2.branch(0xe9, HOOK_FILTER+6)
    for offset, name in jumps2:
        struct.pack_into('<i', code2.data, offset, labels2[name]-offset-4)
    offset2 = pe.get_offset_from_rva(code2.rva)
    assert offset2+len(code2.data) <= section.PointerToRawData+section.SizeOfRawData
    assert not any(output[offset2:offset2+len(code2.data)])
    output[offset2:offset2+len(code2.data)] = code2.data
    offset2 = pe.get_offset_from_rva(HOOK_FILTER)
    output[offset2:offset2+6] = b'\xe9'+struct.pack('<i',code2.rva-HOOK_FILTER-5)+b'\x90'

    struct.pack_into('<I', output, section.get_file_offset()+8,
                     code2.rva+len(code2.data)-section.VirtualAddress)
    return bytes(output), {**metadata, 'handler_cache_stub': code.rva, 'filter_cache_stub': code2.rva}
