"""Replay the pre-crash transcript to isolate bootstrap errors, without a live host.

This is a diagnostic test, never an online reconnect success.
"""
import argparse
import asyncio
import json
import struct
from datetime import datetime, timezone
from pathlib import Path

from .protocol import checksum, join_identity
from .proxy import LabProxy


class OfflineReplay(LabProxy):
    def __init__(self, advertisement: bytes, source: Path, journal: Path | None = None):
        rows = [json.loads(line) for line in source.read_text().splitlines()]
        journal = journal or Path("runtime") / datetime.now(timezone.utc).strftime("offline-%Y%m%dT%H%M%S%fZ.jsonl")
        if journal.resolve() == source.resolve():
            raise ValueError("Diagnostic journal must not overwrite its source transcript")
        super().__init__(advertisement, journal=journal)
        for row in rows:
            if row.get("event") == "local_disconnected":
                break
            if "packet" not in row:
                continue
            p = bytes.fromhex(row["packet"])
            if row.get("direction") == "client":
                if p[1] == 0x1E:
                    self.identity = join_identity(p)
                elif p[1] == 0x27:
                    self.gate.history.append(checksum(p))
            elif row.get("direction") == "host" and p[1] != 1:
                self.transcript.append(p)
                if p[1] == 0x04:
                    self.local_pid = p[6 + struct.unpack_from("<H", p, 4)[0]]
                if p[1] == 0x0B:
                    self.started = True
        self.event("offline_diagnostic", packets=len(self.transcript), checksums=len(self.gate.history))

    async def send_remote(self, data: bytes):
        if data[1] == 0x27:
            self.event("offline_history_matched", checkpoints=self.gate.cursor)
        # There is deliberately no live host to forward to.


def main():
    parser = argparse.ArgumentParser(description="Offline bootstrap diagnostic, not online reconnect")
    parser.add_argument("--source", type=Path, default=Path("runtime/session.jsonl"))
    parser.add_argument("--advertisement", type=Path, default=Path("runtime/advertisement.bin"))
    parser.add_argument("--require-local-echo", action="store_true",
                        help="Diagnostic: wait until historical own commands exist in the fresh client")
    parser.add_argument("--journal", type=Path, help="Output journal (default: unique timestamped file)")
    parser.add_argument("--interval", type=float, default=0.02, help="Seconds between replay packets")
    parser.add_argument("--window", type=int, default=4, help="Maximum unacknowledged simulation updates")
    args = parser.parse_args()
    if args.interval < 0:
        parser.error("--interval must be nonnegative")
    if not 1 <= args.window <= 128:
        parser.error("--window must be between 1 and 128")
    proxy = OfflineReplay(args.advertisement.read_bytes(), args.source, args.journal)
    proxy.require_replay_echo = args.require_local_echo
    proxy.replay_interval = args.interval
    proxy.replay_window = args.window
    asyncio.run(proxy.run())


if __name__ == "__main__":
    main()
