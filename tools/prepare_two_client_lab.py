"""Prepare isolated 1.26a test copies; never modify the installed game.

Changes the single-instance event and LAN discovery UDP port in each copy.
Checkpoint reattachment is a separate experiment, not provided by this patch.
"""
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III')
EXPECTED = '6d21bd9a0f9fbc8446f455c9e89ac994fed68174426fe608fcb9baefd4dec53c'
EVENT = b'Warcraft III Game Application'


def prepare():
    # Installed DLL currently contains a historical echo-check bypass. Use the
    # verified original to avoid hiding synchronization failures in this lab.
    original = (SOURCE / 'game.dll.backup').read_bytes()
    if hashlib.sha256(original).hexdigest() != EXPECTED or original.count(EVENT) != 1:
        raise RuntimeError('Unsupported game.dll: inspect before patching')
    reports = []
    for label in ('A', 'B'):
        destination = ROOT / 'runtime' / 'two-client-lab' / label
        destination.mkdir(parents=True, exist_ok=True)
        names = ['war3.exe', 'Storm.dll', 'ijl15.dll', 'Mss32.dll',
                 'war3.mpq', 'War3x.mpq', 'War3Patch.mpq', 'War3xlocal.mpq']
        for name in names:
            target = destination / name
            if not target.exists():
                shutil.copy2(SOURCE / name, target)
        replacement = ('MongolRanger Lab Instance ' + label).encode().ljust(len(EVENT), b' ')
        assert len(replacement) == len(EVENT)
        patched = bytearray(original.replace(EVENT, replacement))
        # Verified call site: push maximum UDP port; mov edx, minimum UDP port;
        # call 6e2b10 -> UDP socket/bind range in 6e2050. Each discovery receiver
        # needs its own port; the lab broadcaster must target both.
        assert patched[0x6639fc:0x663a06] == bytes.fromhex('68e0170000bae0170000')
        discovery_port = 6112 if label == 'A' else 6113
        struct.pack_into('<I', patched, 0x6639fd, discovery_port)
        struct.pack_into('<I', patched, 0x663a02, discovery_port)
        (destination / 'game.dll').write_bytes(patched)
        maps = destination / 'Maps' / 'Download'
        maps.mkdir(parents=True, exist_ok=True)
        for name in ('DotA LoD 6.85m Aegis.w3x', 'DotA LoD 6.85m.w3x'):
            if (SOURCE / 'Maps' / 'Download' / name).is_file():
                shutil.copy2(SOURCE / 'Maps' / 'Download' / name, maps / name)
        (destination / 'Save' / 'Multiplayer').mkdir(parents=True, exist_ok=True)
        reports.append({'instance': label, 'directory': str(destination),
                        'discovery_port': discovery_port,
                        'game_sha256': hashlib.sha256(patched).hexdigest(),
                        'event_file_offset': original.index(EVENT)})
    output = ROOT / 'runtime' / 'two-client-lab' / 'manifest.json'
    output.write_text(json.dumps({'source_sha256': EXPECTED, 'copies': reports}, indent=2))
    print(output)


if __name__ == '__main__':
    prepare()
