"""Load-only experiment: restart B from a real autosave in a separate lobby.

This is explicitly not live rejoin. It isolates whether this map's save can be
loaded by a fresh Warcraft process before attempting a live-session bridge.
Run only after the baseline match has ended. Never restarts the healthy client.
"""
from pathlib import Path
import argparse
import json
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.recovery_manager import execute_admin_commands
from recovery_lab.protocol import game_info
from recovery_lab.save_checkpoint import inspect_save
from tools.probe_checkpoint_perspective import first_block, perspective_offset
import struct

lab = ROOT / 'runtime' / 'two-client-lab'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--checkpoint', required=True, help='Short filename present independently in BOTH lab clients')
parser.add_argument('--replay', required=True, help='Exact completed replay filename in the isolated host/replays directory')
args = parser.parse_args()
if Path(args.checkpoint).name != args.checkpoint or not args.checkpoint.endswith('.w3z') or len(args.checkpoint) > 31:
    raise ValueError('Expected a short checkpoint filename, not a path')
if Path(args.replay).name != args.replay or not args.replay.endswith('.w3g'):
    raise ValueError('Expected an exact replay filename, not a path')
save = lab / 'A' / 'Save' / 'Multiplayer' / args.checkpoint
report = inspect_save(save)
destination = lab / 'B' / 'Save' / 'Multiplayer' / args.checkpoint
if not destination.is_file():
    raise RuntimeError('B has no own checkpoint. Copying A to B breaks local visibility; cross-player recovery is not implemented.')
b_report = inspect_save(destination)
for key in ('map_path', 'match_name', 'slots', 'random_seed', 'magic'):
    if report[key] != b_report[key]:
        raise RuntimeError(f'Checkpoint pair disagrees on {key}')
# Pinned lab layout only. These are local-perspective fields, NOT sufficient
# to convert another player's save or prove that two files have the same tick.
for path, expected in ((save, (0, 1)), (destination, (5, 7))):
    _, raw = first_block(path.read_bytes())
    if struct.unpack_from('<II', raw, perspective_offset(raw)) != expected:
        raise RuntimeError('Wrong local save perspective for the pinned lab player')
replay = lab / 'host' / 'replays' / args.replay
if not replay.is_file():
    raise FileNotFoundError(replay)
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
    receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    receiver.bind(('127.0.0.1', 6112))
    receiver.settimeout(1)
    execute_admin_commands([f'!enforcesg {replay.stem}', f'!loadsg {save.stem}', '!hostsg Checkpoint Load Probe'], admin_name='ZEV')
    # CreateProcess child handle is retained for precise forced-exit tests;
    # no process-name matching or killing unrelated Warcraft instances.
    child = subprocess.Popen([str(lab / 'B' / 'war3.exe'), '-window'], cwd=lab / 'B')
    (lab / 'load-probe-process.json').write_text(json.dumps({'pid': child.pid}))
    print('Load-only probe client PID', child.pid, flush=True)
    stop = lab / f'kill-probe-{child.pid}.request'
    deadline = time.monotonic() + 900
    while child.poll() is None and time.monotonic() < deadline:
        if stop.exists():
            child.kill()
            child.wait(timeout=10)
            print('Owned test process terminated', flush=True)
            break
        try:
            data, _ = receiver.recvfrom(65535)
            if game_info(data)['port'] == 6200:
                receiver.sendto(data, ('127.0.0.1', 6113))
                # The specific bind above otherwise intercepts A's discovery.
                receiver.sendto(data, ('127.0.0.2', 6112))
        except (socket.timeout, ConnectionResetError):
            pass
    print('Probe controller finished; child exit:', child.poll(), flush=True)
