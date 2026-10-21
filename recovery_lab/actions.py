"""Validate action framing and track commands originated by a replacement client."""
import struct
import zlib


def action_groups(data: bytes) -> list[tuple[int, bytes]]:
    if data[:2] not in (b"\xf7\x0c", b"\xf7\x48") or len(data) < 6:
        raise ValueError("Expected incoming action packet")
    if struct.unpack_from("<H", data, 2)[0] != len(data):
        raise ValueError("Action packet length mismatch")
    if len(data) == 6:
        return []
    if len(data) < 11 or (zlib.crc32(data[8:]) & 65535) != struct.unpack_from("<H", data, 6)[0]:
        raise ValueError("Invalid action packet checksum")
    groups = []
    cursor = 8
    while cursor < len(data):
        if cursor + 3 > len(data):
            raise ValueError("Incomplete action group")
        pid, size = struct.unpack_from("<BH", data, cursor)
        cursor += 3
        if cursor + size > len(data):
            raise ValueError("Incomplete player actions")
        groups.append((pid, data[cursor:cursor + size]))
        cursor += size
    return groups


class OwnActionQueue:
    def __init__(self):
        self.pending = bytearray()

    def produced(self, data: bytes):
        if len(data) < 8 or data[:2] != b"\xf7\x26":
            raise ValueError("Expected outgoing action packet")
        self.pending.extend(data[8:])

    def can_echo(self, body: bytes) -> bool:
        if len(self.pending) < len(body):
            return False
        if self.pending[:len(body)] != body:
            raise ValueError("Replacement process generated different local commands")
        return True

    def consume(self, body: bytes):
        if not self.can_echo(body):
            raise ValueError("Historical local command was not produced by replacement process")
        del self.pending[:len(body)]
