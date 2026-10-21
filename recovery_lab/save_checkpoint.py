"""Read-only 1.26 save inspection, based on GHost++ packed/savegame format.

Checks block completeness and extracts lobby identity. This does not validate
engine state, hero contents or ability to reconnect to a running match.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib


def inspect_save(path: Path) -> dict:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Save exceeds lab size limit')
    data = path.read_bytes()
    signature = b'Warcraft III recorded game\x1a\0'
    if not data.startswith(signature) or len(data) < 68:
        raise ValueError('Invalid packed save header')
    header, compressed, version, expanded, blocks = struct.unpack_from('<5I', data, 28)
    if header != 68 or version != 1 or compressed != len(data):
        raise ValueError('Incomplete or unsupported save header')
    if not 0 < blocks <= 8192 or not 0 < expanded <= 256 * 1024 * 1024:
        raise ValueError('Invalid expanded size or block count')
    identifier, war_version, build, flags, duration = struct.unpack_from('<4sIHHI', data, 48)
    if flags != 0 or war_version != 26 or identifier != b'PX3W':
        raise ValueError('Expected Warcraft III TFT version 26 save, not a replay')
    cursor, total, prefix = header, 0, b''
    for index in range(blocks):
        if cursor + 8 > len(data):
            raise ValueError('Truncated block header')
        packed_size, unpacked_size = struct.unpack_from('<HH', data, cursor)
        cursor += 8
        payload = data[cursor:cursor + packed_size]
        if len(payload) != packed_size:
            raise ValueError('Truncated block')
        decoder = zlib.decompressobj()
        chunk = decoder.decompress(payload, unpacked_size + 1)
        # Warcraft saves use sync-flushed zlib blocks, unlike replay streams
        # that may have a stream-end marker. Require exact expansion and a
        # complete end/flush boundary, not an arbitrary truncated prefix.
        complete = decoder.eof or payload.endswith(b'\x00\x00\xff\xff')
        if len(chunk) != unpacked_size or not complete or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Invalid compressed block')
        if index == 0:
            prefix = chunk
        total += len(chunk)
        if total > 256 * 1024 * 1024:
            raise ValueError('Expanded save exceeds lab limit')
        cursor += packed_size
    if cursor != len(data) or total < expanded:
        raise ValueError('Save data length mismatch')
    pos = 0
    def string():
        nonlocal pos
        end = prefix.index(0, pos)
        value = prefix[pos:end].decode('utf-8', errors='replace')
        pos = end + 1
        return value
    map_path = string()
    string()
    match_name = string()
    string()
    string()
    pos += 10
    count = prefix[pos]
    pos += 1
    if not 1 <= count <= 12 or pos + count * 9 + 10 > len(prefix):
        raise ValueError('Invalid slot layout')
    slots = []
    fields = ('pid', 'download', 'status', 'computer', 'team', 'colour', 'race', 'difficulty', 'handicap')
    for _ in range(count):
        slots.append(dict(zip(fields, prefix[pos:pos + 9])))
        pos += 9
    seed, game_type, player_slots, magic = struct.unpack_from('<IBBI', prefix, pos)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'blocks': blocks, 'expanded_bytes': expanded,
            'map_path': map_path, 'match_name': match_name, 'slots': slots,
            'random_seed': seed, 'magic': magic, 'header_duration': duration,
            'build': build, 'block_completeness_verified': True,
            'engine_state_or_rejoin_verified': False}


if __name__ == '__main__':
    print(json.dumps(inspect_save(Path(sys.argv[1])), indent=2))
