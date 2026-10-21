"""Experimental local-perspective header patch for the pinned two-client save.

Paired engine-generated saves identified two integers after lobby metadata and
24 opaque bytes: local slot index and colour. This is not a general save editor
and does not implement live rejoin. Only patches the B lab checkpoint copy.
"""
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]


def perspective_offset(prefix):
    pos = 0
    for _ in range(5):
        pos = prefix.index(0, pos) + 1
    pos += 10
    slots = prefix[pos]
    if not 1 <= slots <= 12:
        raise ValueError('Invalid slot count')
    return pos + 1 + slots * 9 + 10 + 24


def first_block(data):
    packed, expanded = struct.unpack_from('<HH', data, 68)
    raw = zlib.decompressobj().decompress(data[76:76 + packed])
    if len(raw) != expanded:
        raise ValueError('Invalid block')
    return packed, raw


def patch():
    lab = ROOT / 'runtime/two-client-lab'
    # Confirm the candidate fields against same-tick paired engine saves.
    for label, identity in [('A', (0, 1)), ('B', (5, 7))]:
        _, raw = first_block((lab / label / 'Save/Multiplayer/pairchecku.w3z').read_bytes())
        if struct.unpack_from('<II', raw, perspective_offset(raw)) != identity:
            raise ValueError('Paired-save identity evidence does not match')
    source = lab / 'A/Save/Multiplayer/checkpoint.w3z'
    data = source.read_bytes()
    packed, raw = first_block(data)
    offset = perspective_offset(raw)
    if struct.unpack_from('<II', raw, offset) != (0, 1):
        raise ValueError('Unexpected checkpoint perspective')
    changed = bytearray(raw)
    struct.pack_into('<II', changed, offset, 5, 7)
    compressor = zlib.compressobj()
    payload = compressor.compress(changed) + compressor.flush(zlib.Z_SYNC_FLUSH)
    block = bytearray(struct.pack('<HHI', len(payload), len(changed), 0))
    a, b = zlib.crc32(block), zlib.crc32(payload)
    struct.pack_into('<I', block, 4, ((a ^ (a >> 16)) & 65535) | (((b ^ (b >> 16)) & 65535) << 16))
    result = bytearray(data[:68]) + block + payload + data[76 + packed:]
    struct.pack_into('<I', result, 32, len(result))
    struct.pack_into('<I', result, 64, 0)
    struct.pack_into('<I', result, 64, zlib.crc32(result[:68]))
    target = lab / 'B/Save/Multiplayer/perspective.w3z'
    target.write_bytes(result)
    (lab / 'A/Save/Multiplayer/perspective.w3z').write_bytes(data)
    print('Experimental B perspective:', offset, 'slot 5, colour 7; game state bytes unchanged')


if __name__ == '__main__':
    patch()
