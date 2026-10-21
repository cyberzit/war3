"""Loopback-only reconstruction experiment. No internet reconnect or release claims.

Retains the host socket if the local game process disappears, reconstructs a fresh
client from its original server transcript, and checks old simulation checksums.
Never fakes simulation checksums to keep a server moving.
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import socket
import time

from .protocol import Framer, game_info, join_identity, packet, redirect_game
from .sync import SyncGate
from .actions import action_groups, OwnActionQueue


class LabProxy:
    def __init__(self, advertisement: bytes, port: int = 6210, journal: Path | None = None):
        self.advertisement = redirect_game(advertisement, port)
        self.info = game_info(advertisement)
        if self.info["port"] != 6200:
            raise ValueError("Only the dedicated lab host on port 6200 is allowed")
        self.port = port
        self.remote = None
        self.local = None
        self.identity = None
        self.transcript: list[bytes] = []
        self.gate = SyncGate()
        self.started = False
        self.ended = False
        self.reconstructing = False
        self.replay_cursor = 0
        self.ready_to_load = asyncio.Event()
        self.loaded = asyncio.Event()
        journal = journal or Path("runtime") / datetime.now(timezone.utc).strftime("session-%Y%m%dT%H%M%S%fZ.jsonl")
        self.journal = journal.open("x", encoding="utf-8")
        self.tasks: set[asyncio.Task] = set()
        self.server = None
        self.last_replay_kind = None
        self.first_action_delay = 0.2
        self.replay_interval = 0.001
        self.replay_window = 32
        self.replay_actions_sent = 0
        self.replay_checks_received = 0
        self.replay_ack = asyncio.Event()
        self.require_replay_echo = False
        self.own_actions = OwnActionQueue()
        self.own_action_ready = asyncio.Event()
        self.local_pid = None

    def event(self, name: str, **values):
        row = {"time": time.time(), "event": name, **values}
        self.journal.write(json.dumps(row) + "\n")
        self.journal.flush()
        print(name, values, flush=True)

    def record(self, direction: str, data: bytes):
        self.journal.write(json.dumps({"time": time.time(), "direction": direction,
                                       "packet": data.hex()}) + "\n")
        self.journal.flush()

    async def send_remote(self, data: bytes):
        if self.remote is None or self.ended:
            raise ConnectionError("Lab host session is unavailable")
        self.remote.write(data)
        await self.remote.drain()

    async def host_loop(self, reader):
        framer = Framer()
        try:
            while data := await reader.read(65535):
                for p in framer.feed(data):
                    self.record("host", p)
                    if p[1] == 1:
                        await self.send_remote(packet(0x46, p[4:]))
                        continue
                    self.transcript.append(p)
                    if p[1] == 0x0B:
                        self.started = True
                    if self.local is not None and not self.reconstructing:
                        self.local.write(p)
                        await self.local.drain()
            self.event("host_closed")
        except (ConnectionError, OSError, ValueError) as exc:
            self.event("host_error", detail=str(exc))
        finally:
            self.ended = True
            if self.local is not None:
                self.local.close()

    async def replay(self, writer):
        try:
            # Replay the lobby first. The real client must report its map ready
            # before receiving countdown, then report loaded before game actions.
            self.replay_cursor = 0
            self.replay_actions_sent = 0
            self.replay_checks_received = 0
            first_action = True
            while self.replay_cursor < len(self.transcript):
                p = self.transcript[self.replay_cursor]
                if p[1] == 0x0A:
                    await asyncio.wait_for(self.ready_to_load.wait(), 30)
                if p[1] in (0x08, 0x0C, 0x48):
                    await asyncio.wait_for(self.loaded.wait(), 45)
                if p[1] in (0x0C, 0x48) and first_action:
                    self.event("first_action_wait", cursor=self.replay_cursor)
                    await asyncio.sleep(self.first_action_delay)
                    first_action = False
                if p[1] == 0x0C:
                    # Bound simulation updates by acknowledgments from the new
                    # process, rather than assuming it can absorb a fixed burst.
                    while self.replay_actions_sent - self.replay_checks_received >= self.replay_window:
                        self.replay_ack.clear()
                        await asyncio.wait_for(self.replay_ack.wait(), 15)
                if self.require_replay_echo and p[1] in (0x0C, 0x48):
                    for pid, body in action_groups(p):
                        if pid != self.local_pid:
                            continue
                        while not self.own_actions.can_echo(body):
                            self.own_action_ready.clear()
                            self.event("awaiting_historical_local_command", cursor=self.replay_cursor,
                                       action=body.hex())
                            await asyncio.wait_for(self.own_action_ready.wait(), 45)
                        self.own_actions.consume(body)
                self.replay_cursor += 1
                if p[1] in (0x10, 0x11):
                    continue  # Historical lag-screen messages are not simulation.
                if p[1] in (0x3F, 0x43):
                    raise ValueError("Map download during reconstruction is unsupported")
                self.last_replay_kind = p[1]
                if p[1] not in (0x0C, 0x48):
                    self.record("replay", p)
                writer.write(p)
                if p[1] == 0x0C:
                    self.replay_actions_sent += 1
                await writer.drain()
                # Bound transcript bursts for diagnostics. Whether burst size
                # causes the observed legacy-client disconnect is unproven.
                await asyncio.sleep(self.replay_interval)
            # Switch modes without awaiting, so no newly received host packet is
            # lost between draining the transcript and forwarding the live stream.
            self.reconstructing = False
            self.event("transcript_delivered", packets=self.replay_cursor,
                       checkpoints=len(self.gate.history))
        except (ConnectionError, OSError, ValueError, TimeoutError) as exc:
            self.event("reconstruction_failed", detail=str(exc))
            writer.close()

    async def handle_local(self, reader, writer):
        self.event("local_accepted", peer=writer.get_extra_info("peername"),
                   busy=self.local is not None, ended=self.ended)
        if self.local is not None or self.ended:
            writer.close()
            await writer.wait_closed()
            return
        self.local = writer
        framer = Framer()
        connected = False
        replay_task = None
        try:
            while data := await reader.read(65535):
                for p in framer.feed(data):
                    self.record("client", p)
                    if not connected:
                        identity = join_identity(p)
                        if self.identity is None:
                            if identity[:2] != (self.info["counter"], self.info["key"]):
                                raise ValueError("Join does not match the lab room")
                            self.identity = identity
                            remote_reader, self.remote = await asyncio.open_connection("127.0.0.1", 6200)
                            task = asyncio.create_task(self.host_loop(remote_reader))
                            self.tasks.add(task)
                            task.add_done_callback(self.tasks.discard)
                            await self.send_remote(p)
                            self.event("initial_join")
                        else:
                            if identity != self.identity or not self.started:
                                raise ValueError("Reconstruction requires the same player and started game")
                            self.gate.restart()
                            self.own_actions = OwnActionQueue()
                            self.ready_to_load.clear()
                            self.loaded.clear()
                            self.reconstructing = True
                            replay_task = asyncio.create_task(self.replay(writer))
                            self.event("reconstruction_started")
                        connected = True
                        continue
                    if p[1] == 0x46:
                        continue  # Host pings are answered by the persistent proxy.
                    if self.gate.replaying or self.reconstructing:
                        if p[1] == 0x42:
                            self.ready_to_load.set()
                        elif p[1] == 0x23:
                            self.loaded.set()
                        elif p[1] == 0x26:
                            self.own_actions.produced(p)
                            self.own_action_ready.set()
                        elif p[1] == 0x27:
                            was_replaying = self.gate.replaying
                            forward = self.gate.accept(p)
                            self.replay_checks_received += 1
                            self.replay_ack.set()
                            if forward:
                                await self.send_remote(p)
                                if was_replaying:
                                    self.event("checksums_caught_up", matched=self.gate.cursor)
                            elif self.gate.cursor % 250 == 0:
                                self.event("reconstruction_progress", matched=self.gate.cursor,
                                           target=len(self.gate.history))
                        # Suppress lobby replies, old actions, leave/drop requests,
                        # and checksums already delivered by the original process.
                        continue
                    if p[1] == 0x27:
                        self.gate.accept(p)
                    if p[1] == 0x21:
                        self.ended = True
                        self.remote.write(p)
                        await self.remote.drain()
                        self.event("voluntary_leave")
                        return
                    await self.send_remote(p)
            self.event("local_eof", replay_cursor=self.replay_cursor,
                       last_replay_kind=self.last_replay_kind,
                       matched_checkpoints=self.gate.cursor)
        except (ConnectionError, OSError, ValueError) as exc:
            self.event("client_error", detail=str(exc))
        finally:
            if replay_task:
                replay_task.cancel()
                await asyncio.gather(replay_task, return_exceptions=True)
            self.local = None
            self.reconstructing = False
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self.event("local_disconnected", retained=not self.ended,
                       history_packets=len(self.transcript), checksums=len(self.gate.history))

    async def advertise(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            while not self.ended:
                sock.sendto(self.advertisement, ("127.0.0.1", 6112))
                await asyncio.sleep(1)

    async def controlled_disconnect(self, reader, writer):
        """Local test control: a drop followed by restart, not a real fatal crash."""
        try:
            command = await asyncio.wait_for(reader.readline(), 2)
            if command == b"disconnect-local-for-test\n" and self.local is not None:
                self.event("controlled_local_disconnect")
                self.local.close()
                writer.write(b"OK\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def run(self):
        self.server = await asyncio.start_server(self.handle_local, "127.0.0.1", self.port)
        self.event("lab_proxy_ready", port=self.port, room=self.info["name"])
        advertiser = asyncio.create_task(self.advertise())
        control = await asyncio.start_server(self.controlled_disconnect, "127.0.0.1", self.port + 1)
        try:
            async with self.server, control:
                await self.server.serve_forever()
        finally:
            advertiser.cancel()
            await asyncio.gather(advertiser, return_exceptions=True)
            for task in list(self.tasks):
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            if self.remote:
                self.remote.close()
            if self.local:
                self.local.close()
            self.journal.close()


def main():
    parser = argparse.ArgumentParser(description="Local crash reconstruction experiment; not a production client")
    parser.add_argument("--advertisement", type=Path, default=Path("runtime/advertisement.bin"))
    args = parser.parse_args()
    asyncio.run(LabProxy(args.advertisement.read_bytes()).run())


if __name__ == "__main__":
    main()
