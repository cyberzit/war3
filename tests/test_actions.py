import struct
import unittest
import zlib

from recovery_lab.actions import action_groups, OwnActionQueue
from recovery_lab.protocol import packet


class ActionTests(unittest.TestCase):
    def test_empty_tick_has_no_commands(self):
        self.assertEqual(action_groups(packet(0x0C, struct.pack("<H", 100))), [])

    def test_recorded_selection_decodes_and_checks_crc(self):
        data = bytes.fromhex("f70c150064004aca020a001b01ff570000af860000")
        self.assertEqual(action_groups(data), [(2, bytes.fromhex("1b01ff570000af860000"))])
        corrupt = bytearray(data)
        corrupt[-1] ^= 1
        with self.assertRaises(ValueError):
            action_groups(bytes(corrupt))

    def test_truncated_group_with_valid_crc_is_rejected(self):
        group = struct.pack("<BH", 2, 10) + b"short"
        data = packet(0x0C, struct.pack("<HH", 100, zlib.crc32(group) & 65535) + group)
        with self.assertRaises(ValueError):
            action_groups(data)

    def test_unproduced_historical_command_is_not_accepted(self):
        queue = OwnActionQueue()
        self.assertFalse(queue.can_echo(b"command"))
        with self.assertRaises(ValueError):
            queue.consume(b"command")

    def test_command_queue_preserves_split_and_combined_actions(self):
        queue = OwnActionQueue()
        queue.produced(packet(0x26, b"crc1" + b"one"))
        queue.produced(packet(0x26, b"crc2" + b"two"))
        self.assertTrue(queue.can_echo(b"onetwo"))
        queue.consume(b"one")
        self.assertEqual(queue.pending, b"two")
        queue.consume(b"two")
        self.assertEqual(queue.pending, b"")

    def test_different_replacement_command_is_rejected(self):
        queue = OwnActionQueue()
        queue.produced(packet(0x26, b"crc1" + b"wrong"))
        with self.assertRaises(ValueError):
            queue.can_echo(b"other")
