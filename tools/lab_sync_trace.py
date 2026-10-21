"""Read the diagnostic ring, accepting only stable published records."""
import struct

DATA_RVA=0xBB5000


def trace_snapshot(base,read):
    address=base+DATA_RVA
    magic=read(address,4)
    if magic not in (b'MRT1',b'MRT2'):
        return {'available':False}
    for _ in range(3):
        sequence=int.from_bytes(read(address+4,4),'little')
        rows=[]
        for number in range(max(1,sequence-31),sequence+1):
            raw=read(address+0x200+((number-1)&31)*0x300,0x300)
            fields=struct.unpack_from('<9I',raw)
            if fields[0]!=number:
                break
            rows.append({'sequence':fields[0],'checksum':fields[1],'clock_ms':fields[2],
                'frame_count':fields[3],'full_agent_hash':fields[4],
                'handle_count':fields[5],'handle_free':fields[6],'handle_serial':fields[7],
                'local_player':fields[8],'components':list(struct.unpack_from('<64I',raw,0x40)),
                'random_streams':raw[0x140:0x2a8].hex()})
            if magic==b'MRT2':
                rows[-1].update(component_aggregate=int.from_bytes(raw[0x24:0x28],'little'),
                    auxiliary_digest=int.from_bytes(raw[0x28:0x2c],'little'),
                    auxiliary_state=raw[0x2c:0x34].hex())
        if len(rows)==min(sequence,32) and int.from_bytes(read(address+4,4),'little')==sequence:
            return {'available':True,'sequence':sequence,'records':rows}
    raise ValueError('Sync trace changed while reading; retry at frozen boundary')


def allocation_snapshot(base,read):
    address=base+DATA_RVA
    sequence=int.from_bytes(read(address+8,4),'little')
    rows=[]
    for number in range(max(1,sequence-255),sequence+1):
        raw=read(address+0x7000+((number-1)&255)*0x100,0x100)
        seq,obj,kind,count=struct.unpack_from('<4I',raw)
        if seq!=number or count>48:
            raise ValueError('Allocation trace changed or invalid')
        stack=list(struct.unpack_from('<'+str(count)+'I',raw,0x20))
        rows.append({'sequence':seq,'object':hex(obj),'kind':hex(kind),
                     'stack':list(map(hex,stack)),
                     'module_stack_candidates':[hex(v-base)for v in stack if base<=v<base+0x870000]})
    if int.from_bytes(read(address+8,4),'little')!=sequence:
        raise ValueError('Allocation trace changed during read')
    return {'sequence':sequence,'records':rows}
