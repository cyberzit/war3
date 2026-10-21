"""Explicit, one-shot lab transfer of real RNG state at a frozen boundary.

This is a diagnostic, not a production checkpoint implementation. It never
writes checksum values, clocks, allocator fields or object identities.
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path

LAB = Path(__file__).resolve().parents[1] / 'runtime/two-client-lab'


def digest(data):
    return sum((b * 0x7a2d) ^ b for b in data) & 0xffffffff


def transfer_plan(donor, target, command):
    if donor['process_id'] == target['process_id'] or command['target_pid'] != target['process_id']:
        raise ValueError('Expected distinct exact owned processes')
    a = donor['sync_trace']['records'][-1]
    b = target['sync_trace']['records'][-1]
    if b['sequence'] != command['target_sequence']:
        raise ValueError('Target advanced since the requested boundary')
    if a['clock_ms'] != b['clock_ms'] or b['clock_ms'] != command['clock_ms']:
        raise ValueError('Donor and target are at different simulation times')
    # Native checks are computed before the frame advances simulation time.
    # Validate the current frozen clocks as well as the recorded check clocks.
    for snapshot in (donor, target):
        managers = snapshot['sync_manager_candidates']
        if len(managers) != 1 or managers[0]['fields']['0x1c70'] != command['current_clock_ms']:
            raise ValueError('Current donor/target clocks differ or are ambiguous')
    if a['local_player'] == b['local_player']:
        raise ValueError('Expected different participants')
    before, after = bytes.fromhex(b['random_streams']), bytes.fromhex(a['random_streams'])
    if len(before) != 360 or len(after) != 360:
        raise ValueError('Invalid RNG state size')
    if digest(before) != b['components'][3] or digest(after) != a['components'][3]:
        raise ValueError('RNG bytes do not match the recorded native component')
    return before, after


def auxiliary_plan(donor, target):
    # This is the real eight-byte generator state consumed by 11390 and
    # initialized by 4ab660, not a stored checksum to be substituted.
    try:
        from .lab_checksum_report import snapshot_report
    except ImportError:
        from lab_checksum_report import snapshot_report
    for snapshot in (donor, target):
        if not snapshot_report(snapshot)['matches_native']:
            raise ValueError('Auxiliary state does not reconstruct the actual native check')
        recorded = snapshot['sync_trace']['records'][-1].get('auxiliary_state')
        if recorded is not None and recorded != snapshot['sync_auxiliary_state']:
            raise ValueError('Auxiliary generator advanced after the native check')
    return (bytes.fromhex(target['sync_auxiliary_state']),
            bytes.fromhex(donor['sync_auxiliary_state']))


def apply_requested(handle, base, read, target):
    pid = target['process_id']
    request = LAB / f'restore-rng-{pid}.request'
    if not request.exists():
        return
    # Consume once, even if validation fails; never silently retry a write.
    raw = request.read_bytes()
    request.unlink()
    audit = {'target_pid': pid, 'applied': False}
    try:
        command = json.loads(raw)
        name = command['donor_file']
        if Path(name).name != name or not name.startswith('trace-donor-') or not name.endswith('.json'):
            raise ValueError('Expected a named lab donor snapshot')
        payload = (LAB / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != command['donor_sha256']:
            raise ValueError('Donor snapshot changed')
        donor = json.loads(payload)
        status = json.loads((LAB / 'bridge-status.json').read_text())
        if status['phase'] != 'MISMATCH':
            raise ValueError('Bridge must be frozen at a failed comparison')
        before, after = transfer_plan(donor, target, command)
        auxiliary = auxiliary_plan(donor, target) if command.get('restore_auxiliary') is True else None
        candidates = {int(comp['object'], 16) for thread in target['sync_components']['threads']
                      for comp in thread.get('components', [])
                      if comp['slot'] == 3 and comp['method_rva'] == '0x280c80'}
        if len(candidates) != 1:
            raise ValueError('RNG component is ambiguous')
        address = candidates.pop() + 4
        if read(address, 360) != before:
            raise ValueError('Target RNG changed since the trace')
        auxiliary_address = int.from_bytes(read(base + 0xAB73D8, 4), 'little') if auxiliary else None
        if auxiliary and read(auxiliary_address, 8) != auxiliary[0]:
            raise ValueError('Auxiliary generator changed since snapshot')
        # Trace sequence and native clock must still match immediately before writing.
        from lab_sync_trace import trace_snapshot
        latest = trace_snapshot(base, read)['records'][-1]
        if latest != target['sync_trace']['records'][-1]:
            raise ValueError('Target trace changed during validation')
        managers = target['sync_manager_candidates']
        if len(managers) != 1 or int.from_bytes(read(int(managers[0]['address'],16)+0x1c70,4),'little') != command['current_clock_ms']:
            raise ValueError('Current target clock is ambiguous or changed')
        audit.update(address=hex(address), before=before.hex(), after=after.hex(),
                     donor_sha256=command['donor_sha256'], clock_ms=command['clock_ms'])
        if auxiliary:
            audit['auxiliary'] = {'address': hex(auxiliary_address),
                                  'before': auxiliary[0].hex(), 'after': auxiliary[1].hex(),
                                  'applied': False}
        (LAB / f'restore-rng-{pid}.audit.json').write_text(json.dumps(audit, indent=2))
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.WriteProcessMemory.argtypes = [w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
        kernel.WriteProcessMemory.restype = w.BOOL
        count = c.c_size_t()
        data = c.create_string_buffer(after)
        if not kernel.WriteProcessMemory(handle,address,data,360,c.byref(count)) or count.value != 360:
            raise c.WinError(c.get_last_error())
        if read(address,360) != after:
            raise ValueError('RNG readback did not match')
        audit['streams_applied'] = True
        if auxiliary:
            data = c.create_string_buffer(auxiliary[1])
            if not kernel.WriteProcessMemory(handle, auxiliary_address, data, 8, c.byref(count)) or count.value != 8:
                raise c.WinError(c.get_last_error())
            if read(auxiliary_address, 8) != auxiliary[1]:
                raise ValueError('Auxiliary generator readback did not match')
            audit['auxiliary']['applied'] = True
        audit['applied'] = True
    except Exception as exc:
        audit['error'] = str(exc)
    (LAB / f'restore-rng-{pid}.audit.json').write_text(json.dumps(audit, indent=2))
    target['rng_transfer'] = audit
