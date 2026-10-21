"""Reuse a restored JASS code-table entry when its reverse cache misses.

Pinned 1.26a only. Loader45e0e8 restores the forward code table but does not
populate reverse cache2890. Factory45ce50 otherwise allocates a duplicate ID.
This hook performs an exact pointer lookup before the original allocation path.
It does not change synchronization checks or synthesize callback identities.
"""
import hashlib
import struct
from native.build_sync_trace_probe import build as trace_build, Code, pefile, ROOT

HOOK=0x45ce80


def build(source, allocations=True, restored_codes=()):
    binary,metadata=trace_build(source,allocations=allocations)
    output=bytearray(binary)
    pe=pefile.PE(data=binary)
    text=pe.sections[0]
    stub=Code((text.VirtualAddress+text.Misc_VirtualSize+15)&~15)
    assert pe.get_data(HOOK,6)==bytes.fromhex('8b868c280000')
    stub.emit('9c60 8b8688280000 8b5004 8b4008 b901000000')
    # Bound inspection. Preserve the original allocation behavior on bad/large
    # tables instead of traversing arbitrary memory.
    stub.emit('81fa00000100 0f87'); invalid=len(stub.data);stub.u32(0)
    loop=len(stub.data)
    stub.emit('3bca 0f83'); exhausted=len(stub.data);stub.u32(0)
    stub.emit('393c88 0f84'); found=len(stub.data);stub.u32(0)
    stub.emit('41');stub.branch(0xe9,stub.rva+loop)
    match=len(stub.data)
    # POPAD restores EAX from saved offset1c. Return through native epilogue.
    stub.emit('894c241c 619d');stub.branch(0xe9,0x45ce7b)
    recovery=len(stub.data)
    # Explicit checkpoint descriptors, lab only. Rebind missing unnamed JASS
    # code entries to bytecode created by this process's normal bootstrap.
    # Never reuse an occupied slot or infer identity from the new ID order.
    keys=set()
    for descriptor in restored_codes:
        key=descriptor['key']
        words=descriptor['words']
        ignored=descriptor.get('process_address_words',[])
        if type(key) is not int or not 1<=key<4096 or key in keys or len(words)!=8:
            raise ValueError('Invalid checkpoint code descriptor')
        if ignored not in ([],[1,5]) or any(type(w) is not int or not 0<=w<=0xffffffff for w in words):
            raise ValueError('Invalid bytecode pattern')
        keys.add(key)
        skip=[]
        def reject(op):
            stub.emit(op);skip.append(len(stub.data));stub.u32(0)
        stub.emit('81fa');stub.u32(key);reject('0f86')
        stub.emit('83b8');stub.u32(key*4);stub.emit('00');reject('0f85')
        for index,word in enumerate(words):
            if index not in ignored:
                stub.emit('817f');stub.emit(f'{index*4:02x}');stub.u32(word);reject('0f85')
        if ignored:
            # Both relocated operands must be the same bounded process address.
            stub.emit('8b4f04 3b4f14');reject('0f85')
            stub.emit('81f900000100');reject('0f82')
            stub.emit('81f900000080');reject('0f83')
        stub.emit('89b8');stub.u32(key*4)
        stub.emit('c744241c');stub.u32(key)
        stub.emit('619d');stub.branch(0xe9,0x45ce7b)
        for position in skip:
            struct.pack_into('<i',stub.data,position,len(stub.data)-position-4)
    fallback=len(stub.data)
    stub.emit('619d 8b868c280000');stub.branch(0xe9,HOOK+6)
    for position,target in ((invalid,fallback),(exhausted,recovery),(found,match)):
        struct.pack_into('<i',stub.data,position,target-position-4)
    offset=pe.get_offset_from_rva(stub.rva)
    assert offset+len(stub.data)<=text.PointerToRawData+text.SizeOfRawData
    assert not any(output[offset:offset+len(stub.data)])
    output[offset:offset+len(stub.data)]=stub.data
    offset=pe.get_offset_from_rva(HOOK)
    output[offset:offset+6]=b'\xe9'+struct.pack('<i',stub.rva-HOOK-5)+b'\x90'
    struct.pack_into('<I',output,text.get_file_offset()+8,stub.rva+len(stub.data)-text.VirtualAddress)
    return bytes(output),{**metadata,'code_cache_stub':stub.rva}


if __name__=='__main__':
    binary,metadata=build((ROOT/'runtime/package-v1/Game/Game.dll').read_bytes())
    target=ROOT/'runtime/native/game-code-cache-restore.dll'
    target.write_bytes(binary)
    print(metadata,hashlib.sha256(binary).hexdigest())
