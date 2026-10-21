import asyncio
import struct
import tempfile
import unittest
from pathlib import Path

from recovery_lab.protocol import packet
from recovery_lab.proxy import LabProxy


class Writer:
    def __init__(self):
        self.packets = []

    def write(self, data):
        self.packets.append(data)

    async def drain(self):
        pass


class ReplayGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_player_load_notification_waits_for_local_map_load(self):
        advertisement = packet(0x30, b"PX3W" + struct.pack("<III", 26, 2, 6439)
                               + b"LoD\0\0stat-string\0" + struct.pack("<IIIIIH", 10, 1, 1, 9, 1, 6200))
        with tempfile.TemporaryDirectory() as directory:
            proxy = LabProxy(advertisement, journal=Path(directory) / "test.jsonl")
            proxy.first_action_delay = 0
            writer = Writer()
            lobby = packet(0x09)
            notification = packet(0x08, b"\x03")
            proxy.transcript = [lobby, notification, packet(0x0C, b"\x64\0")]
            task = asyncio.create_task(proxy.replay(writer))
            try:
                await asyncio.sleep(0.03)
                self.assertEqual(writer.packets, [lobby])
                proxy.loaded.set()
                await asyncio.wait_for(task, 1)
                self.assertEqual(writer.packets, proxy.transcript)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                proxy.journal.close()
