"""Read-only, bounded inspection of the pinned engine's checksum components.

Uses the lab controller's retained process handle and query-only thread handles.
Never invokes game functions, changes TLS, or writes simulation/checksum state.
"""
import ctypes as c
from ctypes import wintypes as w


def inspect_components(handle, base, read, u32):
    kernel = c.WinDLL('kernel32', use_last_error=True)
    ntdll = c.WinDLL('ntdll')
    kernel.GetProcessId.argtypes = [w.HANDLE]
    kernel.GetProcessId.restype = w.DWORD
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenThread.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]

    class ThreadEntry(c.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('tid', w.DWORD),
                    ('pid', w.DWORD), ('priority', w.LONG), ('delta', w.LONG),
                    ('flags', w.DWORD)]

    class ThreadBasic(c.Structure):
        _fields_ = [('status', w.LONG), ('teb', c.c_void_p),
                    ('pid', c.c_void_p), ('tid', c.c_void_p),
                    ('affinity', c.c_size_t), ('priority', w.LONG),
                    ('base_priority', w.LONG)]

    kernel.Thread32First.argtypes = [w.HANDLE, c.POINTER(ThreadEntry)]
    kernel.Thread32Next.argtypes = [w.HANDLE, c.POINTER(ThreadEntry)]
    ntdll.NtQueryInformationThread.argtypes = [w.HANDLE, w.ULONG, c.c_void_p, w.ULONG, c.c_void_p]
    ntdll.NtQueryInformationThread.restype = w.LONG
    pid = kernel.GetProcessId(handle)
    index = u32(base + 0xAB7BF4)
    if index >= 64:
        raise ValueError('Expanded TLS is outside this bounded experiment')
    snapshot = kernel.CreateToolhelp32Snapshot(4, 0)
    if snapshot == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())
    result = {'tls_index': index, 'threads': []}
    entry = ThreadEntry(size=c.sizeof(ThreadEntry))
    try:
        found = kernel.Thread32First(snapshot, c.byref(entry))
        while found:
            if entry.pid == pid:
                thread = kernel.OpenThread(0x40, False, entry.tid)
                row = {'tid': entry.tid}
                result['threads'].append(row)
                if thread:
                    try:
                        info = ThreadBasic()
                        status = ntdll.NtQueryInformationThread(thread, 0, c.byref(info), c.sizeof(info), None)
                        if status != 0:
                            raise ValueError(f'Thread query status {status:#x}')
                        row['native_teb'] = hex(info.teb or 0)
                        # Candidate layouts are accepted only if the 32-bit
                        # TEB's self pointer and client PID/TID match exactly.
                        for teb in (info.teb or 0, (info.teb or 0) + 0x2000):
                            if not 0x10000 <= teb < 0x7ffff000:
                                continue
                            try:
                                if u32(teb+0x18) != teb or u32(teb+0x20) != pid or u32(teb+0x24) != entry.tid:
                                    continue
                                root = u32(teb + 0xE10 + 4*index)
                                row.update(teb32=hex(teb), root=hex(root))
                                if not root:
                                    break
                                manager = u32(root + 13*4)
                                row['manager'] = hex(manager)
                                if not manager:
                                    break
                                count, array = u32(manager+0xc), u32(manager+0x10)
                                if not 0 < count <= 128:
                                    raise ValueError('Unexpected component count')
                                row['components'] = []
                                for slot in range(count):
                                    obj = u32(array+slot*4)
                                    if obj:
                                        vtable = u32(obj)
                                        method = u32(vtable)
                                        if not base <= method < base+0x870000:
                                            raise ValueError('Unexpected checksum method')
                                        component = {'slot': slot, 'object': hex(obj),
                                            'vtable_rva': hex(vtable-base), 'method_rva': hex(method-base),
                                            'header': read(obj,64).hex()}
                                        if method-base == 0x280C80:
                                            data = read(obj+4, 45*8)
                                            component['streams'] = data.hex()
                                            component['readonly_digest'] = sum((b*0x7a2d)^b for b in data) & 0xffffffff
                                        elif method-base == 0x3834D0:
                                            component['readonly_digest'] = u32(obj+4) & 0xffffefff
                                        elif method-base == 0x5D60:
                                            component['cache_ready'] = bool(u32(obj+8)) or u32(obj+4) == 0
                                            if component['cache_ready']:
                                                component['readonly_digest'] = u32(obj+0xc)
                                        elif method-base == 0x256190:
                                            right, left = u32(obj+0xc), u32(obj+8)
                                            component['right_dirty'] = u32(right+0x198)
                                            component['right_digest'] = u32(right+0x19c)
                                            if left:
                                                component['left_dirty'] = u32(left+0x30)
                                                component['left_digest'] = u32(left+0x34)
                                            if not component['right_dirty'] and not component.get('left_dirty'):
                                                value = component['right_digest']
                                                if left:
                                                    value ^= component['left_digest']
                                                    value = ((value << 3) | (value >> 29)) & 0xffffffff
                                                component['readonly_digest'] = value
                                        elif method-base == 0x537E10:
                                            child = obj+0x2278
                                            component['child_method_rva'] = hex(u32(u32(child)+4)-base)
                                            component['child_header'] = read(child,64).hex()
                                            if component['child_method_rva'] == '0x536be0':
                                                component['readonly_digest'] = u32(child+4)
                                        row['components'].append(component)
                                break
                            except (OSError, ValueError) as exc:
                                row['layout_error'] = str(exc)
                    except (OSError, ValueError) as exc:
                        row['error'] = str(exc)
                    finally:
                        kernel.CloseHandle(thread)
                else:
                    row['error'] = f'OpenThread query denied: {c.get_last_error()}'
            found = kernel.Thread32Next(snapshot, c.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return result
