"""Loopback two-player checkpoint-to-live-session experiment.

The survivor keeps its original Warcraft connection and world. A separate
GHost lobby bootstraps only the replacement from the survivor's checkpoint.
Actual simulation checksums must agree before this coordinator sends live
orders. No historical match replay, fabricated checksums or sync bypass.
This is an instrumented lab, not an authenticated/public game service.
"""
import asyncio
import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import importlib
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time
import zlib

from .actions import action_groups
from .checkpoint_store import stage_checkpoint
from .save_checkpoint import inspect_save
from .protocol import Framer, chat, checksum, game_info, join_game, join_identity, packet, redirect_game

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'runtime/two-client-lab'
REPLAY = 'GHost++ 2026-10-16 11-51 View Refresh Probe (04m26s)'


def incoming(groups=(), milliseconds=0):
    body = b''.join(struct.pack('<BH', pid, len(data)) + data for pid, data in groups)
    payload = struct.pack('<H', milliseconds)
    if body:
        payload += struct.pack('<H', zlib.crc32(body) & 65535) + body
    return packet(0x0c, payload)


def outgoing(body):
    return packet(0x26, struct.pack('<I', zlib.crc32(body)) + body)


def lag(pid, start):
    return packet(0x10 if start else 0x11, (b'\x01' if start else b'') + bytes([pid]) + bytes(4))


def restore_lobby_seed(data, seed):
    """Keep the checkpoint's match seed across the separate loader lobby."""
    if len(data) < 13 or data[0] != 0xf7 or data[1] not in (4, 9):
        raise ValueError('Expected complete slot-info packet')
    size = struct.unpack_from('<H', data, 4)[0]
    slots = data[6]
    if not 1 <= slots <= 12 or size != 7 + slots*9:
        raise ValueError('Invalid slot-info layout')
    expected = 6 + size + (17 if data[1] == 4 else 0)
    if len(data) != expected or struct.unpack_from('<H', data, 2)[0] != expected:
        raise ValueError('Truncated or trailing slot-info bytes')
    output = bytearray(data)
    struct.pack_into('<I', output, 7+slots*9, seed)
    return bytes(output)


def checkpoint_map_config(checkpoint, directory):
    expected = inspect_save(checkpoint)['map_path'].replace('/', '\\').lower()
    matches=[]
    for config in directory.glob('*.cfg'):
        for line in config.read_text().splitlines():
            key, separator, value = line.partition('=')
            if separator and key.strip() == 'map_path' and value.strip().replace('/', '\\').lower() == expected:
                matches.append(config.stem)
    if len(matches) != 1:
        raise ValueError('Checkpoint requires exactly one matching lab map configuration')
    return matches[0]


class CheckpointGate:
    """One explicitly aligned comparison round. Never substitutes old checks."""
    def __init__(self, names):
        self.names = frozenset(names)
        self.values = {}

    def accept(self, name, value):
        if name not in self.names or name in self.values:
            raise ValueError('Unexpected or duplicate checkpoint acknowledgment')
        self.values[name] = value
        if self.values.keys() == self.names:
            return len(set(self.values.values())) == 1
        return None


class AlignmentGate(CheckpointGate):
    """Record the replacement's real clock-step ack without opening play."""
    def accept(self, name, value):
        super().accept(name, value)
        return None


@dataclass
class Peer:
    name: str
    local: object
    remote: object
    pid: int = 0
    frames: int = 0
    checks: int = 0
    pending: deque = field(default_factory=deque)
    loaded: bool = False


class LoaderDiscovery(asyncio.DatagramProtocol):
    def __init__(self, bridge):
        self.bridge = bridge

    def datagram_received(self, data, address):
        self.bridge.datagram_received(data, address)


async def admin(port, commands):
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    writer.write(join_game(1, 0, 'ZEV'))
    framer = Framer()
    try:
        while chunk := await asyncio.wait_for(reader.read(65535), 6):
            for p in framer.feed(chunk):
                if p[1] == 1:
                    writer.write(packet(0x46, p[4:]))
                if p[1] == 4:
                    pid = p[6 + struct.unpack_from('<H', p, 4)[0]]
                    for cmd in ['!password admin', *commands]:
                        writer.write(chat(pid, cmd))
                        await writer.drain()
                        await asyncio.sleep(.25)
                    writer.write(packet(0x21, struct.pack('<I', 13)))
                    await writer.drain()
                    return
        raise ConnectionError('Admin lobby closed before accepting commands')
    finally:
        writer.close()


class Bridge(asyncio.DatagramProtocol):
    def __init__(self, checkpoint='nativehost', replay=REPLAY, fresh_map=None):
        if Path(checkpoint).name != checkpoint or not checkpoint or len(checkpoint) > 27:
            raise ValueError('Expected short lab checkpoint stem')
        if Path(replay).name != replay or not replay:
            raise ValueError('Expected exact lab replay stem')
        self.checkpoint = checkpoint
        self.replay = replay
        if fresh_map and (Path(fresh_map).name != fresh_map or not (LAB/'host/mapcfgs'/(fresh_map+'.cfg')).is_file()):
            raise ValueError('Expected existing isolated lab map configuration')
        self.fresh_map = fresh_map
        self.phase = 'LOBBY'
        self.peers = {}
        self.ads = {}
        self.gate = None
        self.tasks = set()
        self.helper = None
        self.helper_peer = None
        self.deadline = 0
        self.absent = None
        self.save_name = 'bridge_' + str(int(time.time()))
        self.save_action = b'\x06' + self.save_name.encode() + b'.w3z\0'
        self.log = (LAB / (self.save_name + '.jsonl')).open('x')
        self.started = False
        self.boundary_tail = []

    def event(self, event, **values):
        row = {'time': time.time(), 'phase': self.phase, 'event': event, **values}
        if event in ('lab_code_reloaded','replacement_boundary_sent','task_failed'):
            row['peers']={n:{'pid':p.pid,'frames':p.frames,'checks':p.checks,'connected':p.local is not None} for n,p in self.peers.items()}
        self.log.write(json.dumps(row) + '\n')
        self.log.flush()
        print(json.dumps(row), flush=True)
        (LAB / 'bridge-status.json').write_text(json.dumps(row, indent=2))
        if event == 'lab_code_reloaded' and not getattr(self, 'lag_maintenance_started', False):
            self.lag_maintenance_started = True
            self.spawn(self.maintain_wait())
        if event == 'lab_code_reloaded' and self.phase == 'FAILED' and self.absent and self.peers[self.absent].local is None:
            self.repairing_discovery = True
            self.spawn(self.repair_discovery())
        alignment=LAB/'bridge-alignment.json'
        comparison=LAB/'bridge-comparison.request'
        if event == 'lab_code_reloaded' and self.phase == 'MISMATCH' and comparison.exists() and not alignment.exists():
            comparison.unlink()
            self.spawn(self.compare_frozen_tick())
        if event == 'lab_code_reloaded' and self.phase == 'MISMATCH' and alignment.exists():
            command=json.loads(alignment.read_text())
            ms=command.get('advance_replacement_ms')
            if set(command)=={'advance_replacement_ms'} and type(ms) is int and 0 < ms <= 1000 and ms % 25 == 0:
                alignment.unlink()
                self.spawn(self.align_replacement_clock(ms))

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        def finished(task):
            self.tasks.discard(task)
            if not task.cancelled() and task.exception():
                self.phase = 'FAILED'
                self.event('task_failed', detail=repr(task.exception()))
        task.add_done_callback(finished)
        return task

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):
        if address[0] not in ('127.0.0.1','127.0.0.3'):
            self.event('nonloopback_ad_ignored',address=address)
            return
        try:
            info = game_info(data)
        except ValueError as exc:
            if data[:2] == b'\xf7\x30':
                self.event('invalid_ad',detail=str(exc),packet=data.hex())
            return
        if info['port'] not in (6200, 6300):
            return
        self.ads[info['port']] = data

    async def advertise(self):
        while True:
            port = 6300 if self.phase in ('WAITING', 'LOADING') else 6200
            if port in self.ads and self.phase in ('LOBBY', 'WAITING', 'LOADING'):
                ad = redirect_game(self.ads[port], 6210)
                self.transport.sendto(ad, ('127.0.0.2', 6112))
                self.transport.sendto(ad, ('127.0.0.1', 6113))
            await asyncio.sleep(1)

    async def send(self, peer, p):
        if peer.local is not None:
            try:
                peer.local.write(p)
                await peer.local.drain()
            except (ConnectionError, OSError):
                peer.local = None

    async def accept(self, reader, writer):
        peer = None
        replacement = False
        framer = Framer()
        try:
            while chunk := await reader.read(65535):
                for p in framer.feed(chunk):
                    if peer is None:
                        counter, key, raw_name = join_identity(p)
                        name = raw_name.decode('ascii')
                        replacement = self.phase == 'WAITING' and name == self.absent
                        port = 6300 if replacement else 6200
                        info = game_info(self.ads[port])
                        if (counter, key) != (info['counter'], info['key']):
                            raise ValueError('Wrong lobby identity')
                        if name not in ('ZEV', 'ZEVB') or (not replacement and self.phase != 'LOBBY'):
                            raise ValueError('Only the pinned lab participants may join')
                        if name in self.peers and not replacement:
                            raise ValueError('Participant already connected')
                        remote_reader, remote = await asyncio.open_connection('127.0.0.1', port)
                        old = self.peers.get(name)
                        peer = Peer(name, writer, remote, pid=old.pid if old else 0)
                        self.peers[name] = peer
                        if replacement:
                            self.phase = 'LOADING'
                        self.spawn(self.host_packets(peer, remote_reader, replacement))
                        remote.write(p)
                        await remote.drain()
                        self.event('replacement_join' if replacement else 'initial_join', name=name)
                        if replacement:
                            self.spawn(self.start_loader())
                        continue
                    if p[1] == 0x46:
                        continue
                    if p[1] == 0x23:
                        peer.loaded = True
                        self.event('client_loaded', name=peer.name, replacement=replacement)
                        if replacement:
                            peer.remote.write(p)
                            await peer.remote.drain()
                            self.spawn(self.verify())
                            continue
                    if p[1] == 0x27:
                        peer.checks += 1
                        if self.phase in ('VERIFYING', 'CONTINUING'):
                            result = self.gate.accept(peer.name, checksum(p))
                            self.event('state_check', name=peer.name, value=checksum(p).hex(), result=result)
                            if result is False:
                                self.phase = 'MISMATCH'
                                for target in self.peers.values():
                                    other = next(v for v in self.peers.values() if v is not target)
                                    await self.send(target, lag(other.pid, True))
                                self.event('state_mismatch', values={k: v.hex() for k,v in self.gate.values.items()})
                            elif result is True:
                                self.phase = 'CONTINUING'
                                self.spawn(self.next_tick())
                            continue
                    if p[1] == 0x26 and self.phase not in ('LOBBY', 'LIVE', 'SAVING'):
                        if len(p) < 8 or zlib.crc32(p[8:]) != struct.unpack_from('<I', p, 4)[0]:
                            raise ValueError('Bad player command CRC')
                        if sum(map(len, peer.pending)) + len(p[8:]) > 65535:
                            raise ValueError('Paused player command queue exceeded bound')
                        peer.pending.append(p[8:])
                        self.event('paused_command', name=peer.name, body=p[8:].hex())
                        continue
                    if p[1] == 0x29:
                        self.event('drop_request_ignored', name=peer.name)
                        continue
                    if self.phase in ('LOBBY', 'LIVE', 'SAVING') or (replacement and not peer.loaded):
                        peer.remote.write(p)
                        await peer.remote.drain()
            self.event('client_eof', name=peer.name if peer else None)
        except (ConnectionError, OSError, ValueError) as exc:
            self.event('client_error', detail=str(exc), name=peer.name if peer else None)
        finally:
            if peer and self.peers.get(peer.name) is peer:
                peer.local = None
                if self.phase == 'LIVE':
                    self.absent = peer.name
                    self.phase = 'SAVING'
                    peer.remote.write(outgoing(self.save_action))
                    await peer.remote.drain()
                    self.event('checkpoint_requested', name=self.save_name, absent=self.absent)
                elif self.phase not in ('SAVING', 'FROZEN', 'WAITING'):
                    self.phase = 'FAILED'
                    self.event('client_left_during_recovery', name=peer.name)
            writer.close()

    async def host_packets(self, peer, reader, replacement):
        framer = Framer()
        try:
            while chunk := await reader.read(65535):
                for p in framer.feed(chunk):
                    if p[1] == 1:
                        peer.remote.write(packet(0x46, p[4:]))
                        await peer.remote.drain()
                        # The game also needs host heartbeats while waiting/loading.
                        await self.send(peer, p)
                        continue
                    if p[1] == 4:
                        pid = p[6 + struct.unpack_from('<H', p, 4)[0]]
                        if replacement and pid != peer.pid:
                            raise ValueError('Replacement loader changed original player PID')
                        peer.pid = pid
                    if replacement and p[1] in (4, 9):
                        if not hasattr(self, 'loader_seed'):
                            raise ValueError('Loader checkpoint seed is missing')
                        p = restore_lobby_seed(p, self.loader_seed)
                    if p[1] == 0x0b and not replacement:
                        self.started = True
                        self.phase = 'LIVE'
                    if replacement:
                        if p[1] == 0x08:
                            await self.send(peer,p)
                            if not hasattr(peer,'loaded_pids'):
                                peer.loaded_pids=set()
                            peer.loaded_pids.add(p[4])
                            self.event('loader_participant_ready',pid=p[4])
                        elif not peer.loaded and p[1] not in (0x0c, 0x48, 0x10, 0x11):
                            await self.send(peer, p)
                        continue
                    if self.phase not in ('LOBBY', 'LIVE', 'SAVING'):
                        continue
                    if p[1] == 0x0c:
                        peer.frames += 1
                    await self.send(peer, p)
                    if self.phase == 'SAVING' and peer.local is not None and p[1] in (0x0c, 0x48):
                        if any(pid == self.peers[self.absent].pid and self.save_action in body
                               for pid, body in action_groups(p)):
                            self.phase = 'FROZEN'
                            self.deadline = time.monotonic() + 180
                            self.event('survivor_frozen', name=peer.name, frames=peer.frames, checks=peer.checks)
                            self.spawn(self.prepare_loader(peer))
        except (ConnectionError, OSError):
            pass
        self.event('upstream_closed', name=peer.name, replacement=replacement)

    async def prepare_loader(self, survivor):
        source = LAB / ('A' if survivor.name == 'ZEV' else 'B') / 'Save/Multiplayer' / (self.save_name + '.w3z')
        end = time.monotonic() + 30
        previous = None
        while time.monotonic() < end:
            if source.exists():
                stat = (source.stat().st_size, source.stat().st_mtime_ns)
                if stat == previous and stat[0] > 0 and survivor.frames == survivor.checks:
                    target = await asyncio.to_thread(stage_checkpoint, source, LAB / 'B/Save/Multiplayer')
                    await asyncio.to_thread(stage_checkpoint, source, LAB / 'A/Save/Multiplayer')
                    break
                previous = stat
            await asyncio.sleep(.5)
        else:
            raise TimeoutError(f'Checkpoint/ack not complete: frames={survivor.frames}, checks={survivor.checks}')
        # The requesting process died and cannot emit its save-finished action.
        # Only acknowledge that operation after complete checkpoint validation.
        groups = [(self.peers[self.absent].pid, b'\x07\x01\0\0\0')]
        while survivor.pending:
            groups.append((survivor.pid, survivor.pending.popleft()))
        # Keep only the short post-save boundary, never a match transcript.
        tail = incoming(groups, 100)
        self.boundary_tail.append(tail)
        survivor.frames += 1
        await self.send(survivor, tail)
        await self.send(survivor, lag(self.peers[self.absent].pid, True))
        await self.setup_loader(target)

    async def repair_discovery(self):
        if self.helper and self.helper.poll() is None:
            self.helper.terminate()
            await asyncio.to_thread(self.helper.wait, 5)
        self.phase = 'FROZEN'
        self.helper_peer = None
        self.ads.pop(6300,None)
        source = LAB/'A/Save/Multiplayer'/(self.save_name+'.w3z')
        target = await asyncio.to_thread(stage_checkpoint,source,LAB/'B/Save/Multiplayer')
        await self.setup_loader(target)

    async def setup_loader(self,target):
        self.loader_seed = inspect_save(target)['random_seed']
        self.event('loader_checkpoint_seed', value=self.loader_seed)
        if not getattr(self,'loader_transport',None):
            self.loader_transport,_=await asyncio.get_running_loop().create_datagram_endpoint(lambda:LoaderDiscovery(self),local_addr=('127.0.0.3',6112))
        helper = LAB / 'loader-host'
        helper.mkdir(exist_ok=True)
        base = LAB / 'host'
        for name in ('ghost.exe','BNCSutil.dll','libmysql.dll','zlib1.dll','Storm.dll','msvcp100.dll','msvcr100.dll','language.cfg'):
            shutil.copy2(base / name, helper / name)
        for name in ('mapcfgs', 'replays'):
            shutil.copytree(base / name, helper / name, dirs_exist_ok=True)
        config = (base / 'ghost.cfg').read_text().replace('bot_hostport = 6200','bot_hostport = 6300').replace('admingame_port = 6201','admingame_port = 6301').replace('bot_reconnect = 1','bot_reconnect = 0')
        config=config.replace('udp_broadcasttarget = 127.0.0.1','udp_broadcasttarget = 127.0.0.3')
        (helper / 'ghost.cfg').write_text(config)
        with (helper / 'console.log').open('ab') as output:
            self.helper = subprocess.Popen([str(base / 'ghost.exe'),'ghost.cfg'], cwd=helper, stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
        await asyncio.sleep(1)
        map_config = await asyncio.to_thread(checkpoint_map_config,target,helper/'mapcfgs')
        await admin(6301, ['!load '+map_config, '!enforcesg '+self.replay, '!loadsg '+target.stem, '!hostsg Rejoin Checkpoint'])
        for _ in range(80):
            if 6300 in self.ads:
                break
            await asyncio.sleep(.5)
        if 6300 not in self.ads:
            raise TimeoutError('Loader lobby advertisement not received')
        self.phase = 'WAITING'
        self.deadline = time.monotonic()+600
        self.spawn(self.fake_survivor(next(n for n in self.peers if n != self.absent)))
        self.event('checkpoint_ready', file=target.name, survivor_process_unchanged=True)

    async def fake_survivor(self, name):
        info = game_info(self.ads[6300])
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1',6300)
            self.helper_peer = writer
            writer.write(join_game(info['counter'],info['key'],name))
            framer = Framer()
            while chunk := await reader.read(65535):
                for p in framer.feed(chunk):
                    if p[1] == 1:
                        writer.write(packet(0x46,p[4:]))
                    elif p[1] == 4:
                        self.helper_pid = p[6+struct.unpack_from('<H',p,4)[0]]
                    elif p[1] == 0x3d:
                        end = p.index(0,8)
                        writer.write(packet(0x42, bytes(4)+b'\x01'+p[end+1:end+5]))
                    elif p[1] == 0x0b:
                        writer.write(packet(0x23))
                    await writer.drain()
        except (ConnectionError, OSError):
            pass

    async def start_loader(self):
        await asyncio.sleep(2)
        self.helper_peer.write(chat(self.helper_pid, '!start force'))
        await self.helper_peer.drain()

    async def verify(self):
        await asyncio.sleep(.5)
        if self.phase != 'LOADING':
            return
        replacement = self.peers[self.absent]
        expected = {p.pid for p in self.peers.values()}
        if not expected.issubset(getattr(replacement,'loaded_pids',set())):
            raise ValueError('Loader has not confirmed all participant identities ready')
        for tail in self.boundary_tail:
            # Save-finished is transport bookkeeping for the process that
            # actually saved. A newly loaded process has no matching own action
            # to echo; never feed it an invented local command.
            groups = action_groups(tail)
            for pid,body in groups:
                if pid == replacement.pid and body != b'\x07\x01\0\0\0':
                    raise ValueError('Unexpected replacement own boundary command')
            if any(body != b'\x07\x01\0\0\0' for pid,body in groups):
                raise ValueError('Unexpected gameplay action at save boundary')
            self.event('replacement_boundary_sent', original=tail.hex(), milliseconds=100)
            await self.send(replacement, incoming(milliseconds=100))
        # Drain the explicit boundary acknowledgments before comparing a new
        # common tick. A resumed client must acknowledge its own simulation.
        end = time.monotonic() + 10
        while replacement.checks < len(self.boundary_tail) or any(p.checks < p.frames for p in self.peers.values() if p is not replacement):
            if time.monotonic() > end:
                raise TimeoutError('Boundary simulation acknowledgment missing')
            await asyncio.sleep(.05)
        self.phase = 'VERIFYING'
        self.gate = CheckpointGate(self.peers)
        survivor = next(p for n,p in self.peers.items() if n != self.absent)
        await self.send(survivor, lag(self.peers[self.absent].pid, False))
        self.event('first_post_checkpoint_comparison_started',milliseconds=100)
        for peer in self.peers.values():
            await self.send(peer, incoming(milliseconds=100))

    async def next_tick(self):
        await asyncio.sleep(.1)
        if self.phase != 'CONTINUING':
            return
        groups=[]
        for peer in self.peers.values():
            while peer.pending:
                groups.append((peer.pid,peer.pending.popleft()))
        if sum(3+len(b) for _,b in groups) > 1400:
            raise ValueError('Lab action batch exceeds single-packet bound')
        self.gate = CheckpointGate(self.peers)
        p = incoming(groups,100)
        for peer in self.peers.values():
            await self.send(peer,p)

    async def compare_frozen_tick(self):
        """Recheck both real clients after an explicit frozen-state experiment."""
        if self.phase != 'MISMATCH' or len(self.peers) != 2 or any(p.local is None for p in self.peers.values()):
            raise ValueError('Expected two connected frozen diagnostic participants')
        self.gate = CheckpointGate(self.peers)
        self.phase = 'VERIFYING'
        for peer in self.peers.values():
            other = next(p for p in self.peers.values() if p is not peer)
            await self.send(peer, lag(other.pid, False))
        self.event('frozen_state_common_comparison', milliseconds=100)
        for peer in self.peers.values():
            await self.send(peer, incoming(milliseconds=100))

    async def align_replacement_clock(self, milliseconds=25):
        """Bounded diagnostic for a gap measured by native clock snapshots.

        Advance the returning simulation normally; never write its clock or
        checksum. No player orders are released until a new common check passes.
        """
        if type(milliseconds) is not int or not 0 < milliseconds <= 1000 or milliseconds % 25:
            raise ValueError('Expected bounded measured clock gap in 25ms steps')
        if self.phase != 'MISMATCH':
            raise ValueError('Clock diagnostic requires a frozen mismatch')
        replacement=self.peers[self.absent]
        survivor=next(p for n,p in self.peers.items() if n != self.absent)
        if replacement.local is None or survivor.local is None:
            raise ValueError('Both diagnostic participants must be connected')
        self.phase='VERIFYING'
        self.alignment_gate=AlignmentGate((replacement.name,))
        self.gate=self.alignment_gate
        await self.send(replacement,lag(survivor.pid,False))
        await self.send(replacement,incoming(milliseconds=milliseconds))
        self.event('clock_alignment_probe',milliseconds=milliseconds)
        end=time.monotonic()+5
        while replacement.name not in self.alignment_gate.values:
            if time.monotonic()>end:
                raise TimeoutError('Clock alignment acknowledgment missing')
            await asyncio.sleep(.05)
        self.gate=CheckpointGate(self.peers)
        self.phase='VERIFYING'
        await self.send(survivor,lag(replacement.pid,False))
        self.event('aligned_clock_common_comparison')
        for peer in self.peers.values():
            await self.send(peer,incoming(milliseconds=100))

    async def controls(self):
        path=LAB/'bridge-control.json'
        while True:
            if path.exists():
                command=json.loads(path.read_text())
                path.unlink()
                if command == {'action':'add_time'} and self.phase in ('FROZEN','WAITING','LOADING'):
                    self.deadline=max(time.monotonic(),self.deadline)+120
                    self.event('wait_extended',seconds_left=round(self.deadline-time.monotonic()))
                elif command == {'action':'reload_lab_code'}:
                    module=importlib.import_module('recovery_lab.checkpoint_bridge')
                    self.__class__=importlib.reload(module).Bridge
                    self.event('lab_code_reloaded')
                elif command == {'action':'retry_loader'} and self.phase == 'FAILED':
                    self.phase='FROZEN'
                    self.spawn(self.prepare_loader(next(p for n,p in self.peers.items() if n != self.absent)))
                elif command == {'action':'attach_loader'} and self.phase == 'FAILED' and 6300 in self.ads:
                    self.phase='WAITING'
                    self.deadline=time.monotonic()+600
                    self.spawn(self.fake_survivor(next(n for n in self.peers if n != self.absent)))
                    self.event('loader_attached')
            if self.deadline and time.monotonic()>self.deadline and self.phase in ('WAITING','LOADING'):
                self.phase='EXPIRED'
                self.event('wait_expired_checkpoint_preserved')
            await asyncio.sleep(.5)

    async def heartbeats(self):
        while True:
            for peer in list(self.peers.values()):
                if peer.local is not None:
                    await self.send(peer,packet(1,struct.pack('<I',int(time.monotonic()*1000)&0xffffffff)))
            await asyncio.sleep(3)

    async def maintain_wait(self):
        while True:
            await asyncio.sleep(25)
            if self.absent and self.phase in ('WAITING','LOADING','FROZEN','EXPIRED','MISMATCH','FAILED'):
                for peer in list(self.peers.values()):
                    if peer.local is not None and peer.loaded:
                        other = next(p for n,p in self.peers.items() if n != peer.name)
                        await self.send(peer,lag(other.pid,False))
                        await self.send(peer,incoming())
                        await self.send(peer,lag(other.pid,True))
                self.event('wait_connection_refreshed',peers={n:{'frames':p.frames,'checks':p.checks,'connected':p.local is not None} for n,p in self.peers.items()})

    async def run(self):
        loop=asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda:self,local_addr=('127.0.0.1',6112))
        server=await asyncio.start_server(self.accept,'127.0.0.1',6210)
        self.spawn(self.advertise())
        self.spawn(self.controls())
        self.spawn(self.heartbeats())
        self.lag_maintenance_started = True
        self.spawn(self.maintain_wait())
        if self.fresh_map:
            await admin(6201,['!load '+self.fresh_map,'!priv Camera AR Live'])
        else:
            map_config = await asyncio.to_thread(checkpoint_map_config,LAB/'A/Save/Multiplayer'/(self.checkpoint+'.w3z'),LAB/'host/mapcfgs')
            await admin(6201,['!load '+map_config,'!enforcesg '+self.replay,'!loadsg '+self.checkpoint,'!hostsg Bridge Initial'])
        self.event('bridge_ready',port=6210)
        try:
            async with server:
                await server.serve_forever()
        finally:
            for task in list(self.tasks):
                task.cancel()
            await asyncio.gather(*self.tasks,return_exceptions=True)
            self.transport.close()
            if getattr(self,'loader_transport',None):
                self.loader_transport.close()
            if self.helper and self.helper.poll() is None:
                self.helper.terminate()
            self.log.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',default='nativehost')
    parser.add_argument('--replay',default=REPLAY)
    parser.add_argument('--fresh-map',help='Start fresh lab match; replay must describe the same player/PID seats')
    args=parser.parse_args()
    asyncio.run(Bridge(args.checkpoint,args.replay,args.fresh_map).run())
