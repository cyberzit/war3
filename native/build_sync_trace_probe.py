"""Pinned lab telemetry at actual checksum boundaries; never changes checks.

Copies component digests, RNG state and allocator metadata into a private
diagnostic ring. Original instructions/registers/flags are preserved. No file
I/O, timer, game handle allocation or simulation mutation is introduced.
"""
import hashlib
import struct
from pathlib import Path
from native.build_view_restore_probe import build as view_build, pefile, ROOT, EXPECTED

COMPONENT_HOOK = 0x5E49
FINAL_HOOK = 0x5458F9
DATA_RVA = 0xBB5000
RECORD_SIZE = 0x300
RECORD_COUNT = 32
RECORDS_OFFSET = 0x200
ALLOCATION_HOOK = 0x480687
ALLOCATIONS_OFFSET = 0x7000


class Code:
    def __init__(self, rva):
        self.rva, self.data = rva, bytearray()

    def emit(self, value):
        self.data.extend(bytes.fromhex(value))

    def u32(self, value):
        self.data.extend(struct.pack('<I', value))

    def branch(self, opcode, target):
        self.data.extend(bytes([opcode])+struct.pack('<i',target-(self.rva+len(self.data)+5)))

    def module_base_ebp(self):
        self.branch(0xe8,self.rva+len(self.data)+5)
        offset=self.rva+len(self.data)
        self.emit('5d 81ed'); self.u32(offset)


def build(source, view=True, allocations=False):
    if hashlib.sha256(source).hexdigest() != EXPECTED:
        raise ValueError('Unsupported game.dll for sync telemetry')
    output = bytearray(view_build(source)[0] if view else source)
    pe=pefile.PE(data=bytes(output))
    text=pe.sections[0]
    cave=(text.VirtualAddress+text.Misc_VirtualSize+15)&~15
    assert pe.OPTIONAL_HEADER.SizeOfImage == DATA_RVA
    assert pe.get_data(COMPONENT_HOOK,5)==bytes.fromhex('33c3c1c003')
    assert pe.get_data(FINAL_HOOK,6)==bytes.fromhex('8996641c0000')

    component=Code(cave)
    component.emit('9c60')
    component.module_base_ebp()
    # ESI is the native component slot (0..19 in observed builds).
    component.emit('83fe40 7307 8984b5'); component.u32(DATA_RVA+0x10)
    component.emit('619d 33c3 c1c003')
    component.branch(0xe9,COMPONENT_HOOK+5)

    end=Code((cave+len(component.data)+15)&~15)
    end.emit('8996641c0000 9c60') # Original checksum store, unchanged EDX.
    end.module_base_ebp()
    end.emit('8bbd'); end.u32(DATA_RVA+4) # EDI=current sequence
    end.emit('47 57 8bcf 49 83e11f 69c900030000 8d9c0d'); end.u32(DATA_RVA+RECORDS_OFFSET)
    # EBX=unpublished ring entry. ESI is original sync manager.
    end.emit('895304 8b86701c0000 894308 8b86681c0000 89430c 8b86f8020000 894310')
    # At FINAL_HOOK the native pop edi already shifted ESP. The aggregate
    # component input is entry ESP+8; auxiliary digest is entry ESP+18.
    # pushfd/pushad plus saved sequence above add 28 hex bytes.
    end.emit('8b442430 894324 8b442440 894328')
    end.emit('8b85'); end.u32(0xAB73D8)
    end.emit('8b4804 894b30 8b00 89432c')
    end.emit('8bbd'); end.u32(0xAB778C)
    end.emit('8b471c 894314 8b4740 894318 8b4750 89431c')
    end.emit('8b85'); end.u32(0xAB65F4)
    end.emit('0fb74028 894320')
    # Snapshot all component values from this invocation.
    end.emit('8db5'); end.u32(DATA_RVA+0x10)
    end.emit('8d7b40 b940000000 fc f3a5')
    # Read the same TLS registry as the original checksum routine.
    end.emit('b90d000000'); end.branch(0xe8,0x4C34D0)
    end.emit('8b4010 8b700c 83c604 8dbb40010000 b95a000000 f3a5')
    # Publish only after copying a complete record.
    end.emit('58 8903 8985'); end.u32(DATA_RVA+4)
    end.emit('619d'); end.branch(0xe9,FINAL_HOOK+6)
    hooks = [(COMPONENT_HOOK,component,5),(FINAL_HOOK,end,6)]
    last = end
    if allocations:
        assert pe.get_data(ALLOCATION_HOOK,5)==bytes.fromhex('8948105e59')
        alloc=Code((end.rva+len(end.data)+15)&~15)
        alloc.emit('9c60')
        jumps=[]
        for kind in (0x68646c72,0x2b747267,0x2b746163,0x2b666c74):
            alloc.emit('81f9');alloc.u32(kind)
            alloc.emit('0f84');jumps.append(len(alloc.data));alloc.u32(0)
        alloc.emit('e9');skip=len(alloc.data);alloc.u32(0)
        for jump in jumps:
            struct.pack_into('<i',alloc.data,jump,len(alloc.data)-jump-4)
        alloc.module_base_ebp()
        alloc.emit('8bbd');alloc.u32(DATA_RVA+8)
        alloc.emit('47 57 8bcf 49 81e1ff000000 c1e108 8d9c0d');alloc.u32(DATA_RVA+ALLOCATIONS_OFFSET)
        # EAX is the new script-agent wrapper; saved ECX is its type tag.
        alloc.emit('894304 8b54241c 895308 8d742428')
        # Clamp the read-only stack sample to this thread's StackBase.
        alloc.emit('648b0d04000000 2bce c1e902 83f930 7605 b930000000 894b0c')
        alloc.emit('8d7b20 fc f3a5 58 8903 8985');alloc.u32(DATA_RVA+8)
        struct.pack_into('<i',alloc.data,skip,len(alloc.data)-skip-4)
        alloc.emit('619d 8948105e59')
        alloc.branch(0xe9,ALLOCATION_HOOK+5)
        hooks.append((ALLOCATION_HOOK,alloc,5))
        last=alloc
    for hook, code, size in hooks:
        offset=pe.get_offset_from_rva(code.rva)
        assert offset+len(code.data)<=text.PointerToRawData+text.SizeOfRawData
        assert not any(output[offset:offset+len(code.data)])
        output[offset:offset+len(code.data)]=code.data
        offset=pe.get_offset_from_rva(hook)
        output[offset:offset+size]=b'\xe9'+struct.pack('<i',code.rva-hook-5)+b'\x90'*(size-5)
    struct.pack_into('<I',output,text.get_file_offset()+8,last.rva+len(last.data)-text.VirtualAddress)

    alignment=pe.OPTIONAL_HEADER.FileAlignment
    raw_offset=(len(output)+alignment-1)&~(alignment-1)
    raw_size=0x17000 if allocations else 0x7000
    section_offset=pe.sections[-1].get_file_offset()+40
    assert section_offset+40 <= pe.OPTIONAL_HEADER.SizeOfHeaders
    assert not any(output[section_offset:section_offset+40])
    section=struct.pack('<8sIIIIIIHHI',b'.mrtrace',raw_size,DATA_RVA,raw_size,raw_offset,0,0,0,0,0xC0000040)
    output[section_offset:section_offset+40]=section
    struct.pack_into('<H',output,pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'),len(pe.sections)+1)
    struct.pack_into('<I',output,pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),DATA_RVA+raw_size)
    output.extend(bytes(raw_offset-len(output))+b'MRT2'+bytes(raw_size-4))
    return bytes(output),{'component_stub':component.rva,'final_stub':end.rva,'data_rva':DATA_RVA,
        'allocation_stub':last.rva if allocations else None,
        'component_bytes':component.data.hex(),'final_bytes':end.data.hex()}


if __name__=='__main__':
    binary,meta=build((ROOT/'runtime/package-v1/Game/Game.dll').read_bytes())
    target=ROOT/'runtime/native/game-sync-trace.dll'
    target.write_bytes(binary)
    print(meta)
    print(hashlib.sha256(binary).hexdigest())
