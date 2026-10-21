import struct
import unittest

from recovery_lab.protocol import Framer, checksum, game_info, join_game, join_identity, packet, redirect_game
from recovery_lab.sync import SyncGate, SyncMismatch


class ProtocolTests(unittest.TestCase):
    def test_fragmented_and_combined_tcp_reads(self):
        first = packet(1, b"1234")
        second = packet(0x23)
        parser = Framer()
        self.assertEqual(parser.feed(first[:3]), [])
        self.assertEqual(parser.feed(first[3:] + second[:2]), [first])
        self.assertEqual(parser.feed(second[2:]), [second])

    def test_bad_frame_is_rejected(self):
        for bad in (b"\xf7\x01\x03\x00", b"\xf8\x01\x04\x00"):
            with self.assertRaises(ValueError):
                Framer().feed(bad)

    def test_join_round_trip_and_identity(self):
        p = join_game(12, 345, "LabAdmin")
        self.assertEqual(join_identity(p), (12, 345, b"LabAdmin"))
        with self.assertRaises(ValueError):
            join_game(1, 1, "a\0b")

    def test_real_client_join_padding_is_accepted(self):
        wire = bytes.fromhex("f71e2900020000002719000000e017010000005a4556000100020018427f0000010000000000000000")
        self.assertEqual(join_identity(wire), (2, 6439, b"ZEV"))

    def test_real_client_checksum_layout(self):
        wire = bytes.fromhex("f72709000416d32971")
        self.assertEqual(checksum(wire), bytes.fromhex("16d32971"))

    def test_game_redirect_preserves_key_and_stat_string(self):
        p = packet(0x30, b"PX3W" + struct.pack("<III", 26, 2, 6439)
                   + b"LoD\0\0stat-string\0" + struct.pack("<IIIIIH", 10, 1, 1, 9, 1, 6200))
        q = redirect_game(p, 6210)
        self.assertEqual(game_info(q), dict(name="[LAB] LoD", counter=2, key=6439, port=6210))
        self.assertIn(b"stat-string\0", q)


class SyncTests(unittest.TestCase):
    @staticmethod
    def check(value):
        return packet(0x27, b"\x00" + struct.pack("<I", value))

    def test_restart_suppresses_duplicates_then_forwards_new_checkpoint(self):
        gate = SyncGate()
        self.assertTrue(gate.accept(self.check(1)))
        self.assertTrue(gate.accept(self.check(2)))
        gate.restart()
        self.assertFalse(gate.accept(self.check(1)))
        self.assertFalse(gate.accept(self.check(2)))
        self.assertTrue(gate.accept(self.check(3)))
        self.assertFalse(gate.replaying)
        self.assertEqual(len(gate.history), 3)

    def test_mismatch_does_not_accept_state_or_advance_cursor(self):
        gate = SyncGate()
        gate.accept(self.check(1))
        gate.restart()
        with self.assertRaises(SyncMismatch):
            gate.accept(self.check(9))
        self.assertEqual(gate.cursor, 0)
        self.assertTrue(gate.replaying)

    def test_missing_history_and_invalid_checksum_are_rejected(self):
        with self.assertRaises(ValueError):
            SyncGate().restart()
        with self.assertRaises(ValueError):
            checksum(packet(0x27, b"\0"))


if __name__ == "__main__":
    unittest.main()
