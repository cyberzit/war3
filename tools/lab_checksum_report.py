"""Offline reconstruction of the pinned 1.26a checksum; never changes a game.

The auxiliary bytes in older snapshots are read after the packet. A successful
reconstruction is useful corroboration, not a claim of a complete world hash.
"""
import json
from pathlib import Path


def rol3(value):
    return ((value << 3) | (value >> 29)) & 0xffffffff


def byte_digest(data):
    return sum((value * 0x7a2d) ^ value for value in data) & 0xffffffff


def reconstruct(record, slots, auxiliary):
    if record['full_agent_hash'] != 0:
        raise ValueError('Full world hash requires its own captured input')
    if len(auxiliary) != 8:
        raise ValueError('Expected eight auxiliary state bytes')
    if len(set(slots)) != len(slots) or any(not 0 <= i < 64 for i in slots):
        raise ValueError('Invalid component registry')
    value = 0
    for slot in sorted(slots, reverse=True):
        value = rol3(value ^ record['components'][slot])
    value = rol3(value ^ 0x17ab)
    value = rol3(value ^ record['clock_ms'])
    free = record['handle_free']
    if free == 0xffffffff:
        free = record['handle_count']
    value = rol3(value ^ free)
    # pop edi at 5458e7 changes ESP: the next input is serial, not free again.
    value = rol3(value ^ record['handle_serial'])
    return rol3(value ^ byte_digest(auxiliary))


def snapshot_report(snapshot):
    registries = {tuple(c['slot'] for c in thread['components'])
                  for thread in snapshot['sync_components']['threads']
                  if thread.get('components')}
    if len(registries) != 1:
        raise ValueError('Missing or ambiguous component registry')
    record = snapshot['sync_trace']['records'][-1]
    exact_auxiliary = record.get('auxiliary_state')
    auxiliary = bytes.fromhex(exact_auxiliary if exact_auxiliary is not None
                              else snapshot['sync_auxiliary_state'])
    if exact_auxiliary is not None and byte_digest(auxiliary) != record['auxiliary_digest']:
        raise ValueError('Captured auxiliary bytes disagree with the native digest')
    calculated = reconstruct(record, registries.pop(), auxiliary)
    return {'sequence': record['sequence'], 'clock_ms': record['clock_ms'],
            'native_checksum': record['checksum'], 'calculated_checksum': calculated,
            'matches_native': calculated == record['checksum'],
            'auxiliary_digest': byte_digest(auxiliary),
            'auxiliary_capture': 'native packet boundary' if exact_auxiliary is not None
                                 else 'current snapshot, after native packet'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshots', nargs='+', type=Path)
    args = parser.parse_args()
    for path in args.snapshots:
        print(json.dumps({'file': str(path), **snapshot_report(json.loads(path.read_text()))}))
