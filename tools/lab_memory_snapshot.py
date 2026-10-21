"""Diagnostics through the controller's own child process handle.

Only the pinned lab game's module and a bounded set of engine/JASS fields are
read by default. An explicit per-PID repair request permits six local fog-cache bytes
and the two-byte view mask to be reconstructed from that player's existing
identity and alliance state. Lab only; field writes alone did not fix the UI.
An additional explicit restore-rng request transfers 360 real RNG bytes between
frozen owned clients after validating equal times and state digests. No checksum,
clock or allocator writes, OpenProcess, injection or remote threads.
"""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path


def snapshot(handle):
    kernel = c.WinDLL('kernel32', use_last_error=True)
    psapi = c.WinDLL('psapi', use_last_error=True)
    kernel.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    kernel.ReadProcessMemory.restype = w.BOOL
    psapi.EnumProcessModulesEx.argtypes = [w.HANDLE, c.POINTER(w.HMODULE), w.DWORD, c.POINTER(w.DWORD), w.DWORD]
    psapi.GetModuleBaseNameW.argtypes = [w.HANDLE, w.HMODULE, w.LPWSTR, w.DWORD]
    modules = (w.HMODULE * 1024)()
    needed = w.DWORD()
    if not psapi.EnumProcessModulesEx(handle, modules, c.sizeof(modules), c.byref(needed), 3):
        raise c.WinError(c.get_last_error())
    base = None
    for module in modules[:needed.value // c.sizeof(w.HMODULE)]:
        name = c.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(handle, module, name, len(name))
        if name.value.lower() == 'game.dll':
            base = module
    if base is None:
        return {'state': 'game.dll not loaded'}

    def read(address, size):
        if not 0x10000 <= address < 0x80000000 or not 0 < size <= 1024:
            raise ValueError(f'Invalid bounded read {address:#x}, size {size}')
        buf = c.create_string_buffer(size)
        count = c.c_size_t()
        if not kernel.ReadProcessMemory(handle, address, buf, size, c.byref(count)) or count.value != size:
            raise c.WinError(c.get_last_error())
        return buf.raw

    def u32(address):
        return int.from_bytes(read(address, 4), 'little')

    # Confirm known GetLocalPlayer entry before interpreting version-specific offsets.
    signature = read(base + 0x3BBB60, 6).hex()
    if read(base + 0x3BBB60, 3) != bytes.fromhex('568b35') or u32(base + 0x3BBB63) != base + 0xAB65F4:
        raise ValueError('Unsupported GetLocalPlayer entry')
    game = u32(base + 0xAB65F4)
    kernel.GetProcessId.argtypes = [w.HANDLE]
    kernel.GetProcessId.restype = w.DWORD
    result = {'base': hex(base), 'process_id': kernel.GetProcessId(handle), 'get_local_player_entry': signature, 'game': hex(game)}
    if not game:
        return result
    result['game_header'] = read(game, 96).hex()
    result['code_cache_hook'] = read(base + 0x45CE80, 6).hex()
    # Auxiliary eight-byte input hashed by 545840 via 280be0. This read is
    # current-state evidence only, not necessarily the earlier packet boundary.
    result['sync_auxiliary_state'] = read(u32(base + 0xAB73D8), 8).hex()
    result['local_player_word'] = int.from_bytes(read(game + 0x28, 2), 'little')
    result['replay_player_word'] = int.from_bytes(read(game + 0x2A, 2), 'little')
    result['game_view_mask'] = int.from_bytes(read(game + 0x2C, 2), 'little')
    fog = u32(game + 0x34)
    result['fog_address'] = hex(fog)
    result['fog_header'] = read(fog, 0x80).hex()
    result['fog_masks'] = [int.from_bytes(read(fog + offset, 2), 'little') for offset in (0x3C, 0x3E, 0x40)]
    player = u32(game + 0x58 + result['local_player_word'] * 4)
    result['player_address'] = hex(player)
    result['player_colour'] = read(player + 0x30, 1)[0]
    result['player_vision_allies'] = int.from_bytes(read(player + 0x2E0, 2), 'little')
    result['ui_address'] = hex(u32(base + 0xAB4F80))
    # Read-only synchronization inputs used by pinned routine 0x545840.
    handles = u32(base + 0xAB778C)
    result['sync_handle_table'] = {hex(off): u32(handles + off) for off in (0x1c, 0x40, 0x50)}
    result['sync_handle_table_address'] = hex(handles)
    allocator_request = Path(__file__).resolve().parents[1] / 'runtime/two-client-lab' / f'inspect-allocator-{result["process_id"]}.request'
    if allocator_request.exists():
        allocator_request.unlink()
        import lab_allocator_graph
        result['sync_allocator_graph'] = lab_allocator_graph.snapshot(handles, read)
    # Compare object identities/types without reading arbitrary object payloads.
    # An active entry is tagged -2 in the pinned engine's 0x543d40 walker.
    entries = u32(handles + 0x0c)
    count = u32(handles + 0x1c)
    if count > 100000:
        raise ValueError('Unexpected object table size')
    active = {}
    handlers = {}
    for first in range(0, count, 128):
        raw = read(entries + first * 8, min(128, count-first) * 8)
        for offset in range(0, len(raw), 8):
            if int.from_bytes(raw[offset:offset+4], 'little') == 0xfffffffe:
                obj = int.from_bytes(raw[offset+4:offset+8], 'little')
                active[str(first + offset//8)] = hex(u32(obj)-base)
                if active[str(first + offset//8)]=='0x9520d4' and u32(obj+0x10)==0x68646c72:
                    wrapped=u32(obj+0x54)
                    handlers[str(first+offset//8)]={'object':hex(obj),'serial':u32(obj+0x18),
                        'wrapped':hex(wrapped),'code_key':u32(wrapped+0x24)}
    result['sync_active_object_types'] = active
    result['sync_handler_records'] = handlers
    detail_request = Path(__file__).resolve().parents[1] / 'runtime/two-client-lab' / f'inspect-objects-{result["process_id"]}.request'
    if detail_request.exists():
        indices = json.loads(detail_request.read_text())
        detail_request.unlink()
        if not isinstance(indices,list) or len(indices)>256 or any(type(i) is not int or not 0<=i<count for i in indices):
            raise ValueError('Invalid bounded object-detail request')
        details={}
        for index in indices:
            raw=read(entries+index*8,8)
            tag, pointer=int.from_bytes(raw[:4],'little'),int.from_bytes(raw[4:],'little')
            row={'entry':raw.hex(),'tag':tag}
            if tag==0xfffffffe:
                row.update(address=hex(pointer),header=read(pointer,128).hex(),vtable_rva=hex(u32(pointer)-base))
                if row['vtable_rva']=='0x9520d4':
                    wrapped=u32(pointer+0x54)
                    if wrapped>=0x10000:
                        row.update(wrapped_address=hex(wrapped),wrapped_header=read(wrapped,96).hex())
                if row['vtable_rva']=='0x952b6c':
                    links = {}
                    for offset in (0x24, 0x28, 0x30, 0x34, 0x40):
                        linked = u32(pointer + offset)
                        if 0x10000 <= linked < 0x80000000:
                            links[hex(offset)] = {'address': hex(linked), 'header': read(linked, 128).hex()}
                    row['listener_links'] = links
            details[str(index)]=row
        result['sync_object_details']=details
    result['sync_world_address'] = hex(u32(base + 0xAB73D8))
    # Locate the pinned sync-manager instance by its vtable, read-only. Scan
    # committed writable private memory, with an explicit total byte bound.
    class MBI(c.Structure):
        _fields_=[('base',c.c_void_p),('allocation',c.c_void_p),('allocation_protect',w.DWORD),
                  ('partition',w.WORD),('size',c.c_size_t),('state',w.DWORD),('protect',w.DWORD),('kind',w.DWORD)]
    kernel.VirtualQueryEx.argtypes=[w.HANDLE,c.c_void_p,c.POINTER(MBI),c.c_size_t]
    kernel.VirtualQueryEx.restype=c.c_size_t
    needle=(base+0x9590D0).to_bytes(4,'little')
    address=0x10000
    scanned=0
    candidates=[]
    while address<0x80000000 and scanned<768*1024*1024:
        region=MBI()
        if not kernel.VirtualQueryEx(handle,address,c.byref(region),c.sizeof(region)):
            break
        end=int(region.base or address)+region.size
        if end<=address:
            break
        if region.state==0x1000 and region.kind==0x20000 and region.protect in (4,8,0x40,0x80):
            for start in range(address,end,1024*1024):
                size=min(1024*1024,end-start)
                buffer=c.create_string_buffer(size)
                count=c.c_size_t()
                if kernel.ReadProcessMemory(handle,start,buffer,size,c.byref(count)):
                    raw=buffer.raw[:count.value]
                    offset=raw.find(needle)
                    while offset>=0:
                        location=start+offset
                        try:
                            candidates.append({'address':hex(location),'fields':{hex(o):u32(location+o) for o in (4,0x2f8,0x610,0x1c64,0x1c68,0x1c70)}})
                        except (OSError,ValueError):
                            pass
                        offset=raw.find(needle,offset+4)
                scanned+=size
        address=end
    result['sync_manager_candidates']=candidates
    try:
        import lab_sync_trace
        import importlib
        importlib.reload(lab_sync_trace)
        result['sync_trace']=lab_sync_trace.trace_snapshot(base,read)
        result['allocation_trace']=lab_sync_trace.allocation_snapshot(base,read)
    except (OSError, ValueError) as exc:
        result['sync_trace_error']=str(exc)
    try:
        import lab_sync_components
        import importlib
        importlib.reload(lab_sync_components)
        result['sync_components'] = lab_sync_components.inspect_components(handle, base, read, u32)
        threads = [t for t in result['sync_components']['threads'] if t.get('components')]
        if threads:
            import lab_hash_emulator
            importlib.reload(lab_hash_emulator)
            first = threads[0]
            result['sync_emulated'] = lab_hash_emulator.digest_components(base, int(first['root'],16), first['components'], read)
    except (OSError, ValueError) as exc:
        result['sync_components_error'] = str(exc)
    result['diagnostic_scanned_bytes']=scanned
    result['sync_nearby_globals'] = {}
    for off in range(0xAB7740,0xAB77C0,4):
        pointer=u32(base+off)
        if 0x10000 <= pointer < 0x80000000:
            try:
                result['sync_nearby_globals'][hex(off)]={'address':hex(pointer),'header':read(pointer,32).hex()}
            except OSError:
                pass
    kernel.GetProcessId.argtypes = [w.HANDLE]
    kernel.GetProcessId.restype = w.DWORD
    marker = Path(__file__).resolve().parents[1] / 'runtime/two-client-lab' / f'repair-view-{kernel.GetProcessId(handle)}.request'
    if marker.is_file():
        request = json.loads(marker.read_text())
        if result['local_player_word'] != request['expected_player'] or result['fog_masks'] != request['expected_masks']:
            raise ValueError('Repair precondition changed')
        if read(fog + 0x24, 1)[0] & 1 or not 0 <= result['player_colour'] < 12:
            raise ValueError('Observer/full-vision mode is outside this experiment')
        if 'expected_game_mask' in request and result['game_view_mask'] != request['expected_game_mask']:
            raise ValueError('Game view mask precondition changed')
        allies = result['player_vision_allies']
        union = 0
        for index in range(16):
            if allies & (1 << index):
                ally = u32(game + 0x58 + index * 4)
                union |= int.from_bytes(read(ally + 0x2E0, 2), 'little')
        new_masks = [1 << result['player_colour'], allies, union]
        data = b''.join(v.to_bytes(2, 'little') for v in new_masks)
        kernel.WriteProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
        kernel.WriteProcessMemory.restype = w.BOOL
        count = c.c_size_t()
        if not kernel.WriteProcessMemory(handle, fog + 0x3C, data, len(data), c.byref(count)) or count.value != len(data):
            raise c.WinError(c.get_last_error())
        if read(fog + 0x3C, 6) != data:
            raise ValueError('Repair readback mismatch')
        result['repaired_masks'] = new_masks
        if 'expected_game_mask' in request:
            # Native initialization at 3b0859 uses 1 << CGameWar3.local_player.
            data = (1 << result['local_player_word']).to_bytes(2, 'little')
            if not kernel.WriteProcessMemory(handle, game + 0x2C, data, 2, c.byref(count)) or count.value != 2:
                raise c.WinError(c.get_last_error())
            if read(game + 0x2C, 2) != data:
                raise ValueError('Game view repair readback mismatch')
            result['repaired_game_mask'] = int.from_bytes(data, 'little')
        marker.replace(marker.with_suffix('.applied'))
    try:
        a = u32(base + 0xADA848)
        result['vm_chain_a'] = hex(a)
        b = u32(a + 0x14)
        result['vm_chain_b'] = hex(b)
        vm_list = u32(b + 0x90)
        result['vm_chain_list'] = hex(vm_list)
        vm = u32(vm_list + 4)
        result['vm_address'] = hex(vm)
        result['vm_list_header'] = read(vm_list,32).hex()
        result['vm_header'] = read(vm,32).hex()
        code_table = u32(vm + 0x2888)
        result['vm_code_table_header'] = read(code_table, 16).hex()
        code_array = u32(code_table + 8)
        codes = {}
        for code_key in sorted({h['code_key'] for h in handlers.values()}):
            if not 0 <= code_key < 4096:
                raise ValueError('Unexpected callback key bound')
            codes[str(code_key)] = read(code_array + 4*code_key, 4).hex()
        result['vm_code_entries'] = codes
        result['vm_code_pointer_headers'] = {}
        for key, value in codes.items():
            pointer = int.from_bytes(bytes.fromhex(value), 'little')
            if pointer >= 0x10000:
                try:
                    result['vm_code_pointer_headers'][key] = read(pointer, 32).hex()
                except (OSError, ValueError):
                    pass
        table = u32(vm + 0x285C)
        result['vm_table'] = hex(table)
        result['vm_table_header'] = read(table,32).hex()
        step, node = u32(table + 4), u32(table + 12)
        if step > 256 or step % 4:
            raise ValueError('Unexpected JASS table')
        selected = {}
        seen = set()
        wanted = {'CHHV', 'OVO', 'CHBV', 'CGOV', 'CBH', 'OBVO', 'GHC'}
        while node >= 0x10000 and node not in seen and len(seen) < 30000:
            seen.add(node)
            name = read(u32(node + 0x14), 64).split(b'\0', 1)[0].decode('ascii')
            if name in wanted:
                selected[name] = {'type': u32(node + 0x1C), 'value': u32(node + 0x20)}
            node = u32(node + step + 4)
        result['globals'] = selected
    except (OSError, ValueError, UnicodeError) as exc:
        result['globals_error'] = str(exc)
    import importlib
    import lab_rng_restore
    importlib.reload(lab_rng_restore).apply_requested(handle, base, read, result)
    import lab_listener_restore
    importlib.reload(lab_listener_restore).apply_requested(handle, base, read, result)
    return result
