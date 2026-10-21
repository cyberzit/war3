"""Small W3GS framing helpers for a local Warcraft III 1.26 research harness."""
import struct


def packet(kind: int, payload: bytes = b"") -> bytes:
    if not 0 <= kind <= 255 or len(payload) > 65531:
        raise ValueError("Invalid W3GS packet")
    return struct.pack("<BBH", 0xF7, kind, len(payload) + 4) + payload


class Framer:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= 4:
            header, _, length = struct.unpack_from("<BBH", self.buffer)
            if header != 0xF7 or length < 4:
                raise ValueError("Invalid W3GS stream framing")
            if len(self.buffer) < length:
                break
            result.append(bytes(self.buffer[:length]))
            del self.buffer[:length]
        return result


def search_game() -> bytes:
    return packet(0x2F, b"PX3W" + struct.pack("<II", 26, 0))


def game_info(data: bytes) -> dict:
    if len(data) < 54 or data[:2] != b"\xf7\x30":
        raise ValueError("Invalid game advertisement")
    if struct.unpack_from("<H", data, 2)[0] != len(data):
        raise ValueError("Invalid advertisement length")
    if data[4:8] != b"PX3W" or struct.unpack_from("<I", data, 8)[0] != 26:
        raise ValueError("Only TFT 1.26 advertisements are supported")
    name_end = data.index(0, 20)
    stat_end = data.index(0, name_end + 2)
    if len(data) != stat_end + 23:
        raise ValueError("Invalid advertisement tail")
    return {
        "name": data[20:name_end].decode("utf-8", errors="replace"),
        "counter": struct.unpack_from("<I", data, 12)[0],
        "key": struct.unpack_from("<I", data, 16)[0],
        "port": struct.unpack_from("<H", data, len(data) - 2)[0],
    }


def redirect_game(data: bytes, port: int) -> bytes:
    game_info(data)
    name_end = data.index(0, 20)
    redirected = (data[:20] + b"[LAB] " + data[20:name_end]
                  + data[name_end:-2] + struct.pack("<H", port))
    return packet(0x30, redirected[4:])


def join_game(counter: int, key: int, name: str) -> bytes:
    encoded = name.encode("ascii")
    if not encoded or len(encoded) > 15 or b"\0" in encoded:
        raise ValueError("Player name must be 1-15 ASCII characters")
    return packet(0x1E, struct.pack("<IIBHI", counter, key, 0, 6112, 0)
                  + encoded + b"\0" + struct.pack("<IH", 0, 6112)
                  + b"\x7f\0\0\x01")


def join_identity(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 31 or data[:2] != b"\xf7\x1e":
        raise ValueError("Expected join request")
    if struct.unpack_from("<H", data, 2)[0] != len(data):
        raise ValueError("Invalid join framing")
    end = data.index(0, 19)
    if len(data) < end + 11:
        raise ValueError("Invalid join request length")
    return (*struct.unpack_from("<II", data, 4), data[19:end])


def chat(pid: int, message: str) -> bytes:
    return packet(0x28, bytes([1, pid, pid, 16]) + message.encode("utf-8") + b"\0")


def checksum(data: bytes) -> bytes:
    if len(data) != 9 or data[:2] != b"\xf7\x27":
        raise ValueError("Invalid client synchronization checksum")
    return data[5:9]
