import unittest
from recovery_lab.checkpoint_bridge import CheckpointGate, incoming, outgoing, lag
from recovery_lab.actions import action_groups
import struct
import zlib
import asyncio
from unittest.mock import AsyncMock
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from recovery_lab.checkpoint_bridge import Bridge, Peer
from recovery_lab.checkpoint_bridge import checkpoint_map_config, restore_lobby_seed
from recovery_lab.protocol import packet


class LoaderHandshakeTests(unittest.IsolatedAsyncioTestCase):
    def clock_bridge(self):
        bridge = object.__new__(Bridge)
        bridge.phase = 'MISMATCH'
        bridge.absent = 'B'
        bridge.peers = {name: Peer(name, object(), object(), pid=pid)
                        for name, pid in [('A', 2), ('B', 3)]}
        bridge.event = lambda *args, **kwargs: None
        bridge.send = AsyncMock()
        return bridge

    async def test_clock_alignment_needs_real_ack_before_common_comparison(self):
        bridge = self.clock_bridge()
        task = asyncio.create_task(bridge.align_replacement_clock(225))
        await asyncio.sleep(0)
        self.assertEqual(bridge.phase, 'VERIFYING')
        self.assertEqual(bridge.send.call_count, 2)
        self.assertTrue(all(call.args[0].name == 'B' for call in bridge.send.call_args_list))
        self.assertEqual(bridge.send.call_args_list[1].args[1], incoming(milliseconds=225))
        with self.assertRaises(ValueError):
            bridge.alignment_gate.accept('A', b'old!')
        self.assertFalse(task.done())
        self.assertIsNone(bridge.gate.accept('B', b'ack!'))
        await task
        self.assertEqual(bridge.phase, 'VERIFYING')
        self.assertEqual(bridge.gate.values, {})
        self.assertEqual([(call.args[0].name, call.args[1]) for call in bridge.send.call_args_list[-2:]],
                         [('A', incoming(milliseconds=100)), ('B', incoming(milliseconds=100))])

    async def test_clock_diagnostic_rejects_invalid_gaps_or_unfrozen_match(self):
        for gap in [True, 0, -25, 1, 24, 1001, 1025, 25.0, '25']:
            bridge = self.clock_bridge()
            with self.assertRaises(ValueError):
                await bridge.align_replacement_clock(gap)
            bridge.send.assert_not_awaited()
        bridge = self.clock_bridge()
        bridge.phase = 'CONTINUING'
        with self.assertRaises(ValueError):
            await bridge.align_replacement_clock(25)
        bridge.send.assert_not_awaited()

    async def test_alignment_timeout_never_sends_common_tick(self):
        bridge = self.clock_bridge()
        with patch('recovery_lab.checkpoint_bridge.time.monotonic', side_effect=[0, 6]):
            with self.assertRaises(TimeoutError):
                await bridge.align_replacement_clock(25)
        self.assertTrue(all(call.args[0].name == 'B' for call in bridge.send.call_args_list))
        self.assertNotEqual(bridge.phase, 'CONTINUING')

    async def test_frozen_comparison_requires_two_new_actual_checks(self):
        bridge = self.clock_bridge()
        await bridge.compare_frozen_tick()
        self.assertEqual(bridge.phase, 'VERIFYING')
        self.assertEqual(bridge.gate.values, {})
        self.assertEqual([(c.args[0].name,c.args[1]) for c in bridge.send.call_args_list[-2:]],
                         [('A',incoming(milliseconds=100)),('B',incoming(milliseconds=100))])
        self.assertIsNone(bridge.gate.accept('A',b'abcd'))
        self.assertFalse(bridge.gate.accept('B',b'dcba'))

    async def test_frozen_comparison_rejects_disconnected_or_live_client(self):
        for disconnected in (False,True):
            bridge=self.clock_bridge()
            if disconnected:
                bridge.peers['B'].local=None
            else:
                bridge.phase='CONTINUING'
            with self.assertRaises(ValueError):
                await bridge.compare_frozen_tick()
            bridge.send.assert_not_awaited()

    async def test_own_loaded_ack_is_forwarded_before_first_simulation_tick(self):
        bridge = object.__new__(Bridge)
        bridge.phase = 'LOADING'
        bridge.send = AsyncMock()
        bridge.event = lambda *args, **kwargs: None
        peer = Peer('B', object(), object(), pid=3, loaded=True)
        reader = asyncio.StreamReader()
        reader.feed_data(packet(8, b'\x02') + packet(8, b'\x03') + incoming(milliseconds=100))
        reader.feed_eof()
        await bridge.host_packets(peer, reader, True)
        self.assertEqual(peer.loaded_pids, {2, 3})
        self.assertEqual([c.args[1] for c in bridge.send.call_args_list],
                         [packet(8, b'\x02'), packet(8, b'\x03')])


class BridgeTests(unittest.TestCase):
    def test_loader_seed_preserves_slots_pid_and_other_lobby_fields(self):
        for kind in (4, 9):
            slots = bytes(range(18))
            body = bytes([2]) + slots + struct.pack('<I', 123) + bytes([3, 2])
            original = packet(kind, struct.pack('<H', len(body)) + body + (bytes(range(17)) if kind == 4 else b''))
            restored = restore_lobby_seed(original, 0x12345678)
            self.assertEqual(restored[:25], original[:25])
            self.assertEqual(restored[29:], original[29:])
            self.assertEqual(restored[25:29], bytes.fromhex('78563412'))
            for broken in (original[:-1], original+b'x', original[:6]+b'\x0d'+original[7:]):
                with self.assertRaises(ValueError):
                    restore_lobby_seed(broken, 7)

    def test_loader_uses_checkpoint_map_and_rejects_missing_or_ambiguous_config(self):
        with TemporaryDirectory() as temporary, patch('recovery_lab.checkpoint_bridge.inspect_save',
                return_value={'map_path': 'Maps\\Download\\LoD Rebind Probe.w3x'}):
            root = Path(temporary)
            (root / 'lod.cfg').write_text('map_path = Maps\\Download\\Other.w3x\n')
            with self.assertRaises(ValueError):
                checkpoint_map_config(Path('fixture.w3z'), root)
            match = 'map_path = maps/download/lod rebind probe.w3x\n'
            (root / 'rebind.cfg').write_text(match)
            self.assertEqual(checkpoint_map_config(Path('fixture.w3z'), root), 'rebind')
            (root / 'duplicate.cfg').write_text(match)
            with self.assertRaises(ValueError):
                checkpoint_map_config(Path('fixture.w3z'), root)

    def test_mismatch_never_opens_gate(self):
        gate = CheckpointGate(('A','B'))
        self.assertIsNone(gate.accept('A',b'1234'))
        self.assertIs(gate.accept('B',b'5678'),False)

    def test_two_real_matching_acknowledgments_required(self):
        gate = CheckpointGate(('A','B'))
        self.assertIsNone(gate.accept('B',b'1234'))
        self.assertIs(gate.accept('A',b'1234'),True)
        with self.assertRaises(ValueError):
            gate.accept('A',b'1234')

    def test_save_action_and_empty_boundary_roundtrip(self):
        body=b'\x06bridge_fixture\0'
        self.assertEqual(action_groups(incoming([(3,body)],100)),[(3,body)])
        self.assertEqual(incoming(),bytes.fromhex('f70c06000000'))
        self.assertEqual(struct.unpack_from('<I',outgoing(body),4)[0],zlib.crc32(body))
        self.assertEqual(lag(3,True),bytes.fromhex('f7100a00010300000000'))
