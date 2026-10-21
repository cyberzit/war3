"""Explicit experimental listener relocation through an owned child handle.

This does not open the checksum gate or reduce allocator serial counters.
All threads are briefly suspended during preimage validation and writes.
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import importlib
import json
from pathlib import Path
import struct
import lab_allocator_graph

LAB = Path(__file__).resolve().parents[1] / 'runtime/two-client-lab'


def apply_requested(handle, base, read, target):
    pid=target['process_id']
    request=LAB/f'restore-listeners-{pid}.request'
    if not request.exists():
        return
    importlib.reload(lab_allocator_graph)
    command=json.loads(request.read_text())
    request.unlink()
    audit={'target_pid':pid,'applied':False,'moves':[]}
    suspended=False
    applied=[]
    ntdll=c.WinDLL('ntdll')
    ntdll.NtSuspendProcess.argtypes=[w.HANDLE]
    ntdll.NtSuspendProcess.restype=c.c_long
    ntdll.NtResumeProcess.argtypes=[w.HANDLE]
    ntdll.NtResumeProcess.restype=c.c_long
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.WriteProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
    kernel.WriteProcessMemory.restype=w.BOOL
    def write(address,data):
        count=c.c_size_t()
        buffer=c.create_string_buffer(data)
        if not kernel.WriteProcessMemory(handle,address,buffer,len(data),c.byref(count)) or count.value!=len(data):
            raise c.WinError(c.get_last_error())
    try:
        if command['target_pid']!=pid:
            raise ValueError('Wrong target process')
        name=command['donor_file']
        if Path(name).name!=name or not name.startswith('listener-donor-') or not name.endswith('.json'):
            raise ValueError('Expected named local listener donor')
        payload=(LAB/name).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=command['donor_sha256']:
            raise ValueError('Donor changed')
        donor=json.loads(payload)
        if donor['process_id']==pid:
            raise ValueError('Expected distinct donor')
        status=json.loads((LAB/'bridge-status.json').read_text())
        if status['phase']!='MISMATCH' or not all(p['connected'] for p in status['peers'].values()):
            raise ValueError('Both clients must be connected at a frozen mismatch')
        for state in (donor,target):
            managers=state['sync_manager_candidates']
            if len(managers)!=1 or managers[0]['fields']['0x1c70']!=command['current_clock_ms']:
                raise ValueError('Different frozen clocks')
        graph,moves=lab_allocator_graph.relocate_listeners(donor,target)
        old=target['sync_allocator_graph']
        writes=[]
        for index,(before,after) in enumerate(zip(old['entries'],graph['entries'])):
            if before!=after:
                writes.append((old['table_address']+index*8,struct.pack('<II',*before),struct.pack('<II',*after)))
        if old['head']!=graph['head']:
            writes.append((old['address']+0x40,struct.pack('<I',old['head']),struct.pack('<I',graph['head'])))
        for move in moves:
            writes.append((move['pointer']+0x14,struct.pack('<II',move['old'],move['before_serial']),
                           struct.pack('<II',move['destination'],move['serial'])))
        audit.update(moves=moves,donor_sha256=command['donor_sha256'],
                     writes=[{'address':hex(a),'before':b.hex(),'after':v.hex()} for a,b,v in writes])
        (LAB/f'restore-listeners-{pid}.audit.json').write_text(json.dumps(audit,indent=2))
        if ntdll.NtSuspendProcess(handle)!=0:
            raise ValueError('Could not suspend exact owned target')
        suspended=True
        current=lab_allocator_graph.snapshot(old['address'],read)
        if current!=old:
            raise ValueError('Allocator changed before transaction')
        manager=int(target['sync_manager_candidates'][0]['address'],16)
        if int.from_bytes(read(manager+0x1c70,4),'little')!=command['current_clock_ms']:
            raise ValueError('Clock advanced before transaction')
        for address,before,after in writes:
            if read(address,len(before))!=before:
                raise ValueError('Transaction preimage changed')
        for address,before,after in writes:
            applied.append((address,before))
            write(address,after)
            if read(address,len(after))!=after:
                raise ValueError('Transaction readback failed')
        if lab_allocator_graph.snapshot(old['address'],read)!=graph:
            raise ValueError('Restored free graph failed validation')
        audit['applied']=True
    except Exception as exc:
        audit['error']=str(exc)
        if suspended:
            try:
                for address,before in reversed(applied):
                    write(address,before)
                    if read(address,len(before))!=before:
                        raise ValueError('Rollback readback failed')
                audit['rolled_back']=bool(applied)
            except Exception as rollback:
                audit['rollback_error']=str(rollback)
    finally:
        if suspended:
            audit['resume_status']=ntdll.NtResumeProcess(handle)
        (LAB/f'restore-listeners-{pid}.audit.json').write_text(json.dumps(audit,indent=2))
    target['listener_restore']=audit
