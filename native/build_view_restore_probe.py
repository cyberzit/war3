"""Pinned lab-only native saved-game perspective rebind experiment.

The load-session epilogue has already mapped the local network participant to
CGameWar3+28, but copied saves retain local rendering caches. Invoke the native
UI player-view switch on the game thread after that mapping. Network checks are
preserved. The default native switch cycles unit ownership while rebuilding
views; its simulation-side effects are still under investigation. This is not
a production reconnect patch. The refresh-only variant skips that loop.
"""
from pathlib import Path
import hashlib
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/tooldeps'))
import pefile

EXPECTED = '6d21bd9a0f9fbc8446f455c9e89ac994fed68174426fe608fcb9baefd4dec53c'
HOOK = 0x5C1232
RETURN = HOOK + 5


def build(source, refresh_only=False):
    if hashlib.sha256(source).hexdigest() != EXPECTED:
        raise ValueError('Unsupported original game.dll')
    pe = pefile.PE(data=source)
    section = pe.sections[0]
    cave = (section.VirtualAddress + section.Misc_VirtualSize + 15) & ~15
    old = pe.get_data(HOOK, 5)
    assert old == b'\xe8' + struct.pack('<i', 0x7E1059 - RETURN)
    code = bytearray()

    def relative(opcode, target):
        code.extend(bytes([opcode]) + struct.pack('<i', target - (cave + len(code) + 5)))

    relative(0xE8, 0x7E1059)  # Original stack-cookie check, original ECX/ESP.
    code.extend(b'\x9c\x60')  # Preserve flags and every register.
    relative(0xE8, cave + len(code) + 5)
    base_return = cave + len(code)
    code.extend(b'\x5f\x81\xef' + struct.pack('<I', base_return))  # EDI = module base.
    code.extend(b'\x8b\xb7' + struct.pack('<I', 0xAB65F4))
    code.extend(b'\x85\xf6')
    exits = []
    def exit_if(op):
        code.extend(bytes([op, 0]))
        exits.append(len(code) - 1)
    exit_if(0x74)
    code.extend(b'\x8b\x8f' + struct.pack('<I', 0xAB4F80))
    code.extend(b'\x85\xc9')
    exit_if(0x74)
    code.extend(b'\x0f\xb7\x56\x28\x83\xfa\x0c')
    exit_if(0x73)  # This experiment supports active player colours 0..11.
    code.extend(b'\x51\xbB\x01\x00\x00\x00\x89\xd1\xd3\xe3\x66\x89\x5e\x2c\x59')
    code.extend(b'\x52\x8d\x87' + struct.pack('<I', 0x2FCB50) + b'\xff\xd0')
    exit_position = len(code)
    code.extend(b'\x61\x9d')
    relative(0xE9, RETURN)
    for offset in exits:
        distance = exit_position - offset - 1
        assert 0 <= distance < 128
        code[offset] = distance
    cave_offset = pe.get_offset_from_rva(cave)
    assert cave_offset + len(code) <= section.PointerToRawData + section.SizeOfRawData
    assert not any(source[cave_offset:cave_offset + len(code)])
    output = bytearray(source)
    output[cave_offset:cave_offset + len(code)] = code
    hook_offset = pe.get_offset_from_rva(HOOK)
    output[hook_offset:hook_offset + 5] = b'\xe9' + struct.pack('<i', cave - RETURN)
    if refresh_only:
        # The debug player switch cycles ownership of every unit twice before
        # refreshing UI/fog. That mutates the live agent graph on only the loaded
        # participant. Experiment: retain its UI/fog tail but skip that loop.
        # EBX=0 and ESI=CGameWar3 are established before this branch; the tail
        # initializes EBP/EDI itself. No checksum or allocator state is changed.
        skip, tail = 0x2FCBF3, 0x2FCCC6
        assert pe.get_data(skip, 5) == bytes.fromhex('33ff578bce')
        offset = pe.get_offset_from_rva(skip)
        output[offset:offset + 5] = b'\xe9' + struct.pack('<i', tail-skip-5)
    struct.pack_into('<I', output, section.get_file_offset() + 8, cave + len(code) - section.VirtualAddress)
    return bytes(output), {'hook_rva': HOOK, 'stub_rva': cave, 'stub_size': len(code), 'stub_hex': code.hex()}


if __name__ == '__main__':
    source = (ROOT / 'runtime/package-v1/Game/game.dll').read_bytes()
    output, metadata = build(source)
    target = ROOT / 'runtime/native/game-view-probe.dll'
    target.write_bytes(output)
    print(metadata)
    print('Experimental output:', target, hashlib.sha256(output).hexdigest())
