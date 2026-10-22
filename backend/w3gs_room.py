"""Pure-Python W3GS Room Host & Live Crash-Reconnect Coordinator for MongolRanger.

Runs inside the isolated MongolRanger backend with zero external binaries (no ghost.exe/Wine).
Implements:
- W3GS Lobby protocol (0x1E REQJOIN, 0x04 SLOTINFOJOIN, 0x06 PLAYERINFO, 0x3D MAPCHECK,
  0x09 SLOTINFO, 0x28 CHAT_TO_HOST, 0x42 MAPSIZE, HCL handicap encoding, 0x0A/0x0B COUNTDOWN)
- Lockstep Game Tick loop (0x0C INCOMING_ACTION, 0x26 OUTGOING_ACTION, 0x27 KEEPALIVE)
- Passive Hero & Item NetTag learning (0x6B dr.x gamecache sync) & bi-directional NetTag translation
- Live Crash Reconnect for ANY player (including Room Host):
  - Triggers 25ms-boundary save (0x06 bridge_<ts>.w3z) + 0x0701 completion + 0x10 START_LAG
  - Validates & stages mr_<sha256[:20]>.w3z checkpoint
  - Serves Saved-Game W3GS Loader handshake directly to the rejoining player
  - Aligns 25ms remainder + boundary tail, clears lag screen (0x11 STOP_LAG), and resumes lockstep play
"""
import asyncio
from collections import deque
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import random
import socket
import struct
import tempfile
import time
import zlib

# Default metadata for Maps\Download\LoD_Sync_25.w3x (verified by GHost++)
LOD_MAP_PATH = "Maps\\Download\\LoD_Sync_25.w3x"
LOD_MAP_SIZE = bytes([135, 243, 125, 0])  # 8,254,343 bytes
LOD_MAP_SIZE_INT = struct.unpack("<I", LOD_MAP_SIZE)[0]
LOD_MAP_INFO = bytes([15, 205, 125, 6])
LOD_MAP_CRC = bytes([227, 24, 106, 236])
LOD_MAP_SHA1 = bytes([155, 147, 48, 211, 62, 146, 116, 195, 113, 24, 21, 161, 211, 51, 158, 80, 114, 229, 125, 22])
LOD_MAP_WIDTH = bytes([118, 0])
LOD_MAP_HEIGHT = bytes([120, 0])
LOD_MAP_GAMEFLAGS = struct.pack("<I", 0x00064802)  # Fast speed, default vis, teams together + fixed teams
LOD_MAP_GAMETYPE_FRESH = struct.pack("<I", 1)  # MAPGAMETYPE_UNKNOWN0
LOD_MAP_GAMETYPE_SAVED = struct.pack("<I", 1 << 9)  # MAPGAMETYPE_SAVEDGAME (512)
LOD_LAYOUT_STYLE = 3
LOD_NUM_PLAYERS = 10

VIRTUAL_HOST_NAME = "|cFF00FF88MR"


def default_lod_slots() -> list[dict]:
    slots = []
    # Slots 0..4: Team 0 (Sentinel), colours 1..5, Night Elf (4)
    for c in range(1, 6):
        slots.append({
            "pid": 0, "download": 255, "status": 0, "computer": 0,
            "team": 0, "colour": c, "race": 4, "difficulty": 1, "handicap": 100,
        })
    # Slots 5..9: Team 1 (Scourge), colours 7..11, Undead (8)
    for c in range(7, 12):
        slots.append({
            "pid": 0, "download": 255, "status": 0, "computer": 0,
            "team": 1, "colour": c, "race": 8, "difficulty": 1, "handicap": 100,
        })
    return slots


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


def encode_stat_string(data: bytes) -> bytes:
    mask = 1
    result = bytearray()
    for i, b in enumerate(data):
        if (b % 2) == 0:
            result.append(b + 1)
        else:
            result.append(b)
            mask |= 1 << ((i % 7) + 1)
        if i % 7 == 6 or i == len(data) - 1:
            pos = len(result) - 1 - (i % 7)
            result.insert(pos, mask)
            mask = 1
    return bytes(result)


def build_w3gs_gameinfo(
    game_name: str,
    host_port: int,
    host_counter: int,
    entry_key: int,
    up_time: int = 1,
    save_filename: str | None = None,
    save_magic: int | None = None,
    map_path: str = LOD_MAP_PATH,
    map_width: bytes = LOD_MAP_WIDTH,
    map_height: bytes = LOD_MAP_HEIGHT,
    map_crc: bytes = LOD_MAP_CRC,
    map_sha1: bytes = LOD_MAP_SHA1,
) -> bytes:
    fixed_counter = host_counter & 0x0FFFFFFF
    if save_filename and save_magic is not None:
        game_type = LOD_MAP_GAMETYPE_SAVED
        width = b"\x00\x00"
        height = b"\x00\x00"
        use_map_path = "Save\\Multiplayer\\" + save_filename
        use_map_crc = struct.pack("<I", save_magic)
    else:
        game_type = LOD_MAP_GAMETYPE_FRESH
        width = map_width
        height = map_height
        use_map_path = map_path
        use_map_crc = map_crc

    stat_raw = bytearray()
    stat_raw.extend(LOD_MAP_GAMEFLAGS)
    stat_raw.append(0)
    stat_raw.extend(width)
    stat_raw.extend(height)
    stat_raw.extend(use_map_crc)
    stat_raw.extend(use_map_path.encode("utf-8") + b"\x00")
    stat_raw.extend(b"Varlock\x00")
    stat_raw.append(0)
    stat_raw.extend(map_sha1)
    stat_encoded = encode_stat_string(bytes(stat_raw))

    payload = bytearray()
    payload.extend(b"PX3W")
    payload.extend(struct.pack("<III", 26, fixed_counter, entry_key))
    payload.extend(game_name.encode("utf-8")[:31] + b"\x00")
    payload.append(0)  # empty password
    payload.extend(stat_encoded)
    payload.append(0)
    payload.extend(struct.pack("<IIIII", 12, game_type[0] | (game_type[1] << 8) | (game_type[2] << 16) | (game_type[3] << 24), 1, 12, max(1, up_time)))
    payload.extend(struct.pack("<H", host_port))
    return packet(0x30, bytes(payload))


def build_w3gs_decreate(host_counter: int) -> bytes:
    return packet(0x33, struct.pack("<I", host_counter & 0x0FFFFFFF))


def pack_slots(slots: list[dict]) -> bytes:
    out = bytearray([len(slots)])
    for s in slots:
        out.extend(bytes([
            s["pid"] & 0xFF,
            s["download"] & 0xFF,
            s["status"] & 0xFF,
            s["computer"] & 0xFF,
            s["team"] & 0xFF,
            s["colour"] & 0xFF,
            s["race"] & 0xFF,
            s["difficulty"] & 0xFF,
            s["handicap"] & 0xFF,
        ]))
    return bytes(out)


def build_slot_info_block(slots: list[dict], random_seed: int, layout_style: int = LOD_LAYOUT_STYLE, num_players: int = LOD_NUM_PLAYERS) -> bytes:
    raw = pack_slots(slots) + struct.pack("<IBB", random_seed & 0xFFFFFFFF, layout_style & 0xFF, num_players & 0xFF)
    return struct.pack("<H", len(raw)) + raw


def send_w3gs_slotinfojoin(pid: int, port: int, external_ip: bytes, slots: list[dict], random_seed: int) -> bytes:
    block = build_slot_info_block(slots, random_seed)
    sockaddr = bytearray([2, 0])
    sockaddr.extend(struct.pack(">H", port & 0xFFFF))
    sockaddr.extend((external_ip + b"\x00\x00\x00\x00")[:4])
    sockaddr.extend(b"\x00" * 8)
    return packet(0x04, block + bytes([pid & 0xFF]) + bytes(sockaddr))


def send_w3gs_slotinfo(slots: list[dict], random_seed: int) -> bytes:
    return packet(0x09, build_slot_info_block(slots, random_seed))


def send_w3gs_rejectjoin(reason: int = 9) -> bytes:
    return packet(0x05, struct.pack("<I", reason))


def send_w3gs_playerinfo(pid: int, name: str, external_ip: bytes = b"\x00\x00\x00\x00", internal_ip: bytes = b"\x00\x00\x00\x00") -> bytes:
    payload = bytearray()
    payload.extend(struct.pack("<IB", 2, pid & 0xFF))
    payload.extend(name.encode("utf-8")[:15] + b"\x00")
    payload.extend(b"\x01\x00")
    payload.extend(b"\x02\x00\x00\x00" + (external_ip + b"\x00\x00\x00\x00")[:4] + b"\x00" * 8)
    payload.extend(b"\x02\x00\x00\x00" + (internal_ip + b"\x00\x00\x00\x00")[:4] + b"\x00" * 8)
    return packet(0x06, bytes(payload))


def send_w3gs_playerleave_others(pid: int, left_code: int = 7) -> bytes:
    return packet(0x07, struct.pack("<BI", pid & 0xFF, left_code))


def send_w3gs_gameloaded_others(pid: int) -> bytes:
    return packet(0x08, bytes([pid & 0xFF]))


def send_w3gs_countdown_start() -> bytes:
    return packet(0x0A)


def send_w3gs_countdown_end() -> bytes:
    return packet(0x0B)


def send_w3gs_mapcheck(
    map_path: str = LOD_MAP_PATH,
    map_size: bytes = LOD_MAP_SIZE,
    map_info: bytes = LOD_MAP_INFO,
    map_crc: bytes = LOD_MAP_CRC,
    map_sha1: bytes = LOD_MAP_SHA1,
) -> bytes:
    payload = bytearray([1, 0, 0, 0])
    payload.extend(map_path.encode("utf-8") + b"\x00")
    payload.extend(map_size)
    payload.extend(map_info)
    payload.extend(map_crc)
    payload.extend(map_sha1)
    return packet(0x3D, bytes(payload))


def send_w3gs_ping_from_host() -> bytes:
    return packet(0x01, struct.pack("<I", int(time.monotonic() * 1000) & 0xFFFFFFFF))


_CYR_TO_LATIN_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "ye", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "ө": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ү": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "sh", "ъ": "", "ы": "ii", "ь": "i", "э": "e", "ю": "yu", "я": "ya",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "Ye", "Ё": "Yo",
    "Ж": "J", "З": "Z", "И": "I", "Й": "I", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "Ө": "O", "П": "P", "Р": "R", "С": "S", "Т": "T",
    "У": "U", "Ү": "U", "Ф": "F", "Х": "H", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh",
    "Щ": "Sh", "Ъ": "", "Ы": "Ii", "Ь": "I", "Э": "E", "Ю": "Yu", "Я": "Ya",
    "«": '"', "»": '"', "—": "-", "–": "-", "•": "|", "№": "#",
}


def to_wc3_latin(text: str) -> str:
    """Transliterates Cyrillic & non-ASCII symbols to ASCII Latin for Warcraft III 1.26a's FRIZQT__.TTF font."""
    if not text or text.isascii():
        return text
    out = []
    prev_space = False
    for ch in text:
        if ch in _CYR_TO_LATIN_MAP:
            mapped = _CYR_TO_LATIN_MAP[ch]
            if mapped:
                out.append(mapped)
                prev_space = False
        elif 32 <= ord(ch) <= 126:
            if ch == " ":
                if not prev_space:
                    out.append(" ")
                prev_space = True
            else:
                out.append(ch)
                prev_space = False
    return "".join(out).strip()


def send_w3gs_chat_from_host(from_pid: int, to_pids: list[int], flag: int, extra_flags: bytes, message: str) -> bytes:
    if not to_pids:
        return b""
    payload = bytearray([len(to_pids)])
    payload.extend(bytes(p & 0xFF for p in to_pids))
    payload.append(from_pid & 0xFF)
    payload.append(flag & 0xFF)
    payload.extend(extra_flags)
    # Standard Warcraft III 1.26a FRIZQT__.TTF only renders Latin ASCII glyphs (Cyrillic renders as blank space)
    wc3_msg = to_wc3_latin(message)
    safe_utf8 = wc3_msg.encode("utf-8")[:220].decode("utf-8", errors="ignore").encode("utf-8")
    payload.extend(safe_utf8 + b"\x00")
    return packet(0x0F, bytes(payload))


def incoming(groups=(), milliseconds: int = 100) -> bytes:
    body = b"".join(struct.pack("<BH", pid, len(data)) + data for pid, data in groups)
    payload = struct.pack("<H", milliseconds)
    if body:
        payload += struct.pack("<H", zlib.crc32(body) & 65535) + body
    return packet(0x0C, payload)


def lag(pid: int, start: bool, lag_ms: int = 0) -> bytes:
    # Game.dll is patched (12 sites, 0xAFC8 -> 0x2BF20) so the native lag window is 180000 ms.
    ms_clamped = max(0, min(180000, int(lag_ms)))
    return packet(0x10 if start else 0x11, (b"\x01" if start else b"") + bytes([pid & 0xFF]) + struct.pack("<I", ms_clamped))


def encode_hcl_handicaps(slots: list[dict], hcl: str) -> bool:
    if not hcl:
        return False
    occupied = [s for s in slots if s["status"] == 2]
    if len(hcl) > len(occupied):
        return False
    hcl_chars = "abcdefghijklmnopqrstuvwxyz0123456789 -=,."
    if any(ch not in hcl_chars for ch in hcl):
        return False
    encoding_map = []
    j = 0
    for _ in range(256):
        if j in (0, 50, 60, 70, 80, 90, 100):
            j += 1
        encoding_map.append(j & 0xFF)
        j += 1
    slot_idx = 0
    for ch in hcl:
        while slots[slot_idx]["status"] != 2:
            slot_idx += 1
        h_val = slots[slot_idx]["handicap"]
        if h_val not in (50, 60, 70, 80, 90, 100):
            h_val = 100
        h_index = (h_val - 50) // 10
        c_index = hcl_chars.index(ch)
        slots[slot_idx]["handicap"] = encoding_map[h_index + c_index * 6]
        slot_idx += 1
    return True


def inspect_save_bytes(data: bytes) -> dict:
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("Save exceeds size limit")
    signature = b"Warcraft III recorded game\x1a\0"
    if not data.startswith(signature) or len(data) < 68:
        raise ValueError("Invalid packed save header")
    header, compressed, version, expanded, blocks = struct.unpack_from("<5I", data, 28)
    if header != 68 or version != 1 or compressed != len(data):
        raise ValueError("Incomplete or unsupported save header")
    if not 0 < blocks <= 8192 or not 0 < expanded <= 256 * 1024 * 1024:
        raise ValueError("Invalid expanded size or block count")
    identifier, war_version, build, flags, duration = struct.unpack_from("<4sIHHI", data, 48)
    if flags != 0 or war_version != 26 or identifier != b"PX3W":
        raise ValueError("Expected Warcraft III TFT version 26 save")
    cursor, total, prefix = header, 0, b""
    for index in range(blocks):
        if cursor + 8 > len(data):
            raise ValueError("Truncated block header")
        packed_size, unpacked_size = struct.unpack_from("<HH", data, cursor)
        cursor += 8
        payload = data[cursor:cursor + packed_size]
        if len(payload) != packed_size:
            raise ValueError("Truncated block")
        decoder = zlib.decompressobj()
        chunk = decoder.decompress(payload, unpacked_size + 1)
        complete = decoder.eof or payload.endswith(b"\x00\x00\xff\xff")
        if len(chunk) != unpacked_size or not complete or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("Invalid compressed block")
        if index == 0:
            prefix = chunk
        total += len(chunk)
        if total > 256 * 1024 * 1024:
            raise ValueError("Expanded save exceeds limit")
        cursor += packed_size
    if cursor != len(data) or total < expanded:
        raise ValueError("Save data length mismatch")
    pos = 0

    def read_str():
        nonlocal pos
        end = prefix.index(0, pos)
        val = prefix[pos:end].decode("utf-8", errors="replace")
        pos = end + 1
        return val

    map_path = read_str()
    read_str()
    match_name = read_str()
    read_str()
    read_str()
    pos += 10
    count = prefix[pos]
    pos += 1
    if not 1 <= count <= 12 or pos + count * 9 + 10 > len(prefix):
        raise ValueError("Invalid slot layout")
    slots = []
    fields = ("pid", "download", "status", "computer", "team", "colour", "race", "difficulty", "handicap")
    for _ in range(count):
        slots.append(dict(zip(fields, prefix[pos:pos + 9])))
        pos += 9
    seed, game_type, player_slots, magic = struct.unpack_from("<IBBI", prefix, pos)
    sha256 = hashlib.sha256(data).hexdigest()
    return {
        "sha256": sha256,
        "filename": f"mr_{sha256[:20]}.w3z",
        "bytes": len(data),
        "blocks": blocks,
        "expanded_bytes": expanded,
        "map_path": map_path,
        "match_name": match_name,
        "slots": slots,
        "random_seed": seed,
        "magic": magic,
        "header_duration": duration,
        "build": build,
    }


def join_identity(data: bytes) -> tuple[int, int, str, bytes]:
    if len(data) < 31 or data[:2] != b"\xf7\x1e":
        raise ValueError("Expected join request (0x1E)")
    if struct.unpack_from("<H", data, 2)[0] != len(data):
        raise ValueError("Invalid join framing")
    end = data.index(0, 19)
    if len(data) < end + 11:
        raise ValueError("Invalid join request length")
    counter, key = struct.unpack_from("<II", data, 4)
    name = data[19:end].decode("utf-8", errors="replace")
    internal_ip = data[end + 7:end + 11]
    return counter, key, name, internal_ip


class CheckpointGate:
    def __init__(self, names):
        self.names = frozenset(names)
        self.values = {}

    def accept(self, name: str, value: bytes):
        if name not in self.names or name in self.values:
            return None
        self.values[name] = value
        if self.values.keys() == self.names:
            return len(set(self.values.values())) == 1
        return None


@dataclass
class RoomPeer:
    name: str
    writer: asyncio.StreamWriter | None
    pid: int
    sid: int
    internal_ip: bytes = b"\x7f\x00\x00\x01"
    frames: int = 0
    checks: int = 0
    pending: deque = field(default_factory=deque)
    loaded: bool = False
    map_ready: bool = False
    tunnel_reader: asyncio.StreamReader | None = None
    tunnel_writer: asyncio.StreamWriter | None = None
    join_slotinfojoin_pkt: bytes = b""
    loaded_other_pids: list[int] = field(default_factory=list)
    recorded_ticks: list[bytes] = field(default_factory=list)
    keepalives_sent: int = 0
    deliberate_quit: bool = False


class W3GSRoom:
    def __init__(
        self,
        room_id: str,
        name: str,
        owner_name: str,
        host_counter: int,
        entry_key: int,
        hcl: str = "",
        map_meta: dict | None = None,
    ):
        self.room_id = room_id
        self.name = name
        self.owner_name = owner_name
        self.host_counter = host_counter & 0x0FFFFFFF
        self.rejoin_counter = ((host_counter + 0x00100000) & 0x0FFFFFFF) or 2
        self.entry_key = entry_key & 0xFFFFFFFF
        self.hcl = hcl
        self.random_seed = random.randint(1, 0x7FFFFFFF)
        self.created_at = time.monotonic()
        self.updated_at = time.time()
        self.phase = "LOBBY"  # LOBBY -> STARTING -> CONTINUING -> FROZEN -> WAITING -> LOADING -> VERIFYING
        self.map_path = map_meta["map_path"] if map_meta and "map_path" in map_meta else LOD_MAP_PATH
        self.map_size = bytes(map_meta["map_size"]) if map_meta and "map_size" in map_meta else LOD_MAP_SIZE
        self.map_size_int = struct.unpack("<I", self.map_size)[0]
        self.map_info = bytes(map_meta["map_info"]) if map_meta and "map_info" in map_meta else LOD_MAP_INFO
        self.map_crc = bytes(map_meta["map_crc"]) if map_meta and "map_crc" in map_meta else LOD_MAP_CRC
        self.map_sha1 = bytes(map_meta["map_sha1"]) if map_meta and "map_sha1" in map_meta else LOD_MAP_SHA1
        self.map_width = bytes(map_meta["map_width"]) if map_meta and "map_width" in map_meta else LOD_MAP_WIDTH
        self.map_height = bytes(map_meta["map_height"]) if map_meta and "map_height" in map_meta else LOD_MAP_HEIGHT
        self.slots = [dict(s) for s in map_meta["slots"]] if map_meta and map_meta.get("slots") else default_lod_slots()
        self.default_slots = [dict(s) for s in self.slots]
        self.peers: dict[str, RoomPeer] = {}
        self.vhost_pid = 11
        self.absent: str | None = None
        self.save_name: str | None = None
        self.save_action: bytes = b""
        self.boundary_tail: list[bytes] = []
        self.checkpoint_bytes: bytes | None = None
        self.checkpoint_info: dict | None = None
        self.checkpoint_event = asyncio.Event()
        self.gate: CheckpointGate | None = None
        self.last_tick_time = 0.0
        self.lag_active_since = 0.0
        self.hero_nt_parts: dict = {}
        self.latest_tag: dict = {}
        self.latest_tag_ts: dict = {}
        self.paired_tags: dict = {}
        self.tag_map: dict = {}
        self.pos_sync_count = 0
        self.match_started_at: float = 0.0
        self.match_scored: bool = False
        self.winner_team: int | None = None
        self.initial_player_count: int = 0
        self.initial_team_counts: dict[int, int] = {0: 0, 1: 0}
        self.initial_players: set[str] = set()
        self.first_empty_team: int | None = None
        self.colour_to_name: dict[int, str] = {}
        self.player_stats: dict[str, dict] = {}
        self.kill_dedup: dict[tuple[int, int], float] = {}
        self.assist_dedup: dict[tuple[int, int], float] = {}
        self.kicked_players: set[str] = set()
        self.disconnected_players: set[str] = set()
        self.no_leavers: bool = False
        self.auto_fill_comp: bool = False
        self.wait_started_at: float = 0.0
        self.wait_duration_sec: float = 180.0
        self.addtime_count: int = 0
        self.addtime_max: int = 3
        self.host_drop_unlocked_sent: bool = False
        self.warned_20s_addtime: bool = False
        self.last_wait_announce: float = 0.0
        self.rmk_votes: set[str] = set()
        self.ff_votes: dict[int, set[str]] = {0: set(), 1: set()}
        self._cmd_dedup: dict[tuple[str, str], float] = {}
        self.remake_in_progress: bool = False
        self.on_match_complete_cb = None
        self.on_player_dropped_cb = None
        self.last_drop_reason = "drop"
        # Rejoin diagnostics: rolling record of the last ~30 s of lockstep traffic, flushed to a JSONL file
        # when a player drops, then streamed live until 3 minutes after the rejoin completes.
        self.turn_ring: deque = deque(maxlen=1500)
        self.debug_fh = None
        self.debug_until = 0.0
        self.on_chat_announce_cb = None
        self.on_room_remake_cb = None
        self.events: deque = deque(maxlen=200)
        self.tasks: set[asyncio.Task] = set()
        self._tick_task: asyncio.Task | None = None
        self._bg_started = False
        # Native Warcraft III "Create Game" Host Tunnel & Rejoin state
        self.host_raw_gameinfo: bytes = b""
        self.last_host_gameinfo_snapshot: bytes = b""
        self.host_raw_updated_at: float = 0.0
        self.host_war3_port: int = 6112
        self.orig_host_counter: int = 1
        self.orig_entry_key: int = 0
        self.host_ctrl_writer: asyncio.StreamWriter | None = None
        self.pending_tunnels: dict[str, asyncio.Future] = {}
        self._tunnel_seq: int = 0
        self.host_playerinfo_pkts: dict[int, bytes] = {}
        self.last_mapcheck_pkt: bytes = b""
        self.last_slotinfo_pkt: bytes = b""
        self.host_pid: int = 1

    async def reset_room_for_remake(self, reason_msg: str, score_winner_team: int | None = None):
        if self.remake_in_progress:
            return
        self.remake_in_progress = True
        try:
            elapsed_match = (time.time() - self.match_started_at) if self.match_started_at > 0 else 0.0
            has_kda = any(
                (st.get("kills", 0) > 0 or st.get("deaths", 0) > 0 or st.get("assists", 0) > 0)
                for st in self.player_stats.values()
            )
            if (score_winner_team is not None or (has_kda and elapsed_match >= 300.0)) and not self.match_scored:
                if score_winner_team is not None:
                    self.winner_team = score_winner_team
                now_end = time.time()
                for pname, st in self.player_stats.items():
                    if (
                        pname in self.peers
                        or self.initial_player_count < 10
                        or (now_end - float(st.get("quit_at", 0.0))) < 300.0
                    ):
                        st["abandoned"] = False
                if self.on_match_complete_cb is not None:
                    try:
                        self.on_match_complete_cb(self)
                    except Exception:
                        pass

            # Disconnect any remaining in-game W3GS sockets so Warcraft III returns players to the LAN screen cleanly
            old_peers = list(self.peers.values())
            for p in old_peers:
                if p.writer is not None:
                    for other in old_peers:
                        if other.pid != p.pid:
                            await self.send(p, send_w3gs_playerleave_others(other.pid, 8))
            await asyncio.sleep(0.25)
            for p in old_peers:
                if p.writer is not None:
                    try:
                        p.writer.close()
                    except Exception:
                        pass
                    p.writer = None
                if p.tunnel_writer is not None:
                    try:
                        p.tunnel_writer.close()
                    except Exception:
                        pass
                    p.tunnel_writer = None
                p.loaded = False

            # Reset room back to fresh LOBBY and bump host_counter so Warcraft III LAN refreshes the host immediately
            self.phase = "LOBBY"
            self.host_counter = ((self.host_counter + 1) & 0x0FFFFFFF) or 1
            self.rejoin_counter = ((self.host_counter + 1000) & 0x0FFFFFFF) or 2
            self.absent = None
            self.lag_active_since = 0.0
            self.wait_started_at = 0.0
            self.wait_duration_sec = 180.0
            self.addtime_count = 0
            self.host_drop_unlocked_sent = False
            self.warned_20s_addtime = False
            self.kicked_players.clear()
            self.disconnected_players.clear()
            self.rmk_votes.clear()
            self.ff_votes = {0: set(), 1: set()}
            self._cmd_dedup.clear()
            self.checkpoint_bytes = None
            self.checkpoint_info = None
            self.checkpoint_event.clear()
            self.boundary_tail.clear()
            self.reset_nettag_maps()
            self.winner_team = None
            self.match_scored = False
            self.match_started_at = 0.0
            self.initial_player_count = 0
            self.initial_team_counts = {0: 0, 1: 0}
            self.initial_players.clear()
            self.first_empty_team = None
            self.colour_to_name.clear()
            self.kill_dedup.clear()
            self.assist_dedup.clear()
            self.player_stats.clear()
            self.host_playerinfo_pkts.clear()
            self.last_mapcheck_pkt = b""
            self.last_slotinfo_pkt = b""
            self.host_raw_gameinfo = b""
            self.auto_fill_comp = False
            self.slots = [dict(s) for s in self.default_slots]
            self.peers.clear()
            self.event("room_reset_for_remake", reason=reason_msg, new_host_counter=self.host_counter)
            if self.on_room_remake_cb is not None:
                try:
                    self.on_room_remake_cb(self, reason_msg)
                except Exception:
                    pass
        finally:
            self.remake_in_progress = False

    async def vote_remake(self, sender_name: str, force_by_host: bool = False) -> tuple[bool, str]:
        if self.phase == "LOBBY":
            return False, "Өрөө аль хэдийн LOBBY (хүлээлгийн) төлөвт бэлэн байна. Warcraft III LAN дотроос шууд орно уу!"
        now_m = time.monotonic()
        dedup_key = (sender_name.lower(), "vote_remake")
        if now_m - self._cmd_dedup.get(dedup_key, 0.0) < 1.2 and sender_name in self.rmk_votes:
            return True, "🔄 Таны -rmk санал бүртгэгдсэн байна."
        self._cmd_dedup[dedup_key] = now_m

        elapsed = (time.time() - self.match_started_at) if self.match_started_at > 0 else 0.0
        if self.match_started_at > 0 and elapsed > 300.0:
            err_msg = f"⏳ -rmk (warda) командыг зөвхөн тоглолт эхлээд эхний 5 минутын дотор ашиглах боломжтой! (Одоо {int(elapsed // 60)} мин өнгөрсөн байна)"
            await self.send_all_chat(f"|cFFFF5555[MongolRanger]|r {err_msg}")
            if self.on_chat_announce_cb is not None:
                try:
                    self.on_chat_announce_cb(self.room_id, err_msg)
                except Exception:
                    pass
            return False, err_msg

        self.rmk_votes.add(sender_name)
        active_peers = [p for p in self.peers.values() if p.writer is not None]
        active_names = [p.name for p in active_peers]
        total_active = len(active_names)

        peer = self.peers.get(sender_name)
        my_team = int(self.slots[peer.sid].get("team", 0)) if (peer and 0 <= peer.sid < len(self.slots)) else 0
        team_name = "Sentinel" if my_team == 0 else "Scourge"

        team0_active = [p.name for p in active_peers if 0 <= p.sid < len(self.slots) and self.slots[p.sid].get("team") == 0]
        team1_active = [p.name for p in active_peers if 0 <= p.sid < len(self.slots) and self.slots[p.sid].get("team") == 1]
        my_team_active = team0_active if my_team == 0 else team1_active

        team_votes = len([n for n in my_team_active if n in self.rmk_votes])
        total_votes = len([n for n in active_names if n in self.rmk_votes]) or len(self.rmk_votes)

        if total_active <= 1:
            needed = 1
            current_votes = max(1, total_votes)
            passed = True
        elif total_active <= 4:
            # 1v1 (2 players) and 2v2 (3-4 players): 2 votes needed
            needed = 2
            current_votes = total_votes
            passed = current_votes >= 2
        else:
            # 3v3, 4v4, 5v5 (5-10 players): 3 votes across the match (or entire short-handed team of 2+)
            needed = 3
            current_votes = total_votes
            passed = (current_votes >= 3) or (len(my_team_active) >= 2 and team_votes >= len(my_team_active))

        if passed:
            msg = f"🔄 Тоглогчид тохиролцож тоглолтыг дахин эхлүүлэхээр (-rmk / warda {current_votes}/{needed}) шийдлээ!"
            await self.reset_room_for_remake(msg, score_winner_team=None)
            return True, msg + " Warcraft III (F10 -> E -> Q) гаргаад LAN дотроо өрөө рүүгээ шууд буцаж орно уу!"

        wait_msg = (
            f"🔄 «{sender_name}» ({team_name}) тоглолтыг дахин эхлүүлэх (-rmk / warda) санал өглөө ({current_votes}/{needed}). "
            f"Зөвшөөрөх бол чат дээр -rmk гэж бичнэ үү! (Эхний 5 минутын дотор хүчинтэй)"
        )
        await self.send_all_chat(f"|cFFFFCC00[MongolRanger]|r {wait_msg}")
        if self.on_chat_announce_cb is not None:
            try:
                self.on_chat_announce_cb(self.room_id, wait_msg)
            except Exception:
                pass
        return True, wait_msg

    async def vote_forfeit(self, sender_name: str) -> tuple[bool, str]:
        if self.phase == "LOBBY":
            return False, "Тоглолт эхлээгүй байна."
        now_m = time.monotonic()
        dedup_key = (sender_name.lower(), "vote_forfeit")
        if now_m - self._cmd_dedup.get(dedup_key, 0.0) < 1.2:
            return True, "🏳️ Таны -gg санал бүртгэгдсэн байна."
        self._cmd_dedup[dedup_key] = now_m

        elapsed = (time.time() - self.match_started_at) if self.match_started_at > 0 else 0.0
        # Ranked 5v5 (or default uninitialized test room) requires 15 mins (900s); live 1v1/2v2/3v3/4v4 (1..9 players) allows -gg after 5 mins (300s)
        min_gg_sec = 300.0 if (0 < self.initial_player_count < 10) else 900.0
        min_gg_label = 5 if min_gg_sec == 300.0 else 15
        if self.match_started_at <= 0 or elapsed < min_gg_sec:
            rem_sec = max(1, int(min_gg_sec - elapsed))
            rem_min = max(1, (rem_sec + 59) // 60)
            err_msg = f"⏳ -gg (-ff) бууж өгөх команд тоглолт эхлээд {min_gg_label} минутаас хойш ажиллана! (Одоо {int(elapsed // 60)} мин • Үлдсэн: {rem_min} мин)"
            await self.send_all_chat(f"|cFFFF5555[MongolRanger]|r {err_msg}")
            if self.on_chat_announce_cb is not None:
                try:
                    self.on_chat_announce_cb(self.room_id, err_msg)
                except Exception:
                    pass
            return False, err_msg

        peer = self.peers.get(sender_name)
        my_team = 0
        if peer and 0 <= peer.sid < len(self.slots):
            my_team = int(self.slots[peer.sid].get("team", 0))
        self.ff_votes.setdefault(my_team, set()).add(sender_name)

        team_peers = [
            p.name for p in self.peers.values()
            if p.writer is not None and 0 <= p.sid < len(self.slots) and int(self.slots[p.sid].get("team", 0)) == my_team
        ]
        if len(team_peers) >= 4:
            needed = 3
        elif len(team_peers) >= 2:
            needed = 2
        else:
            needed = 1
        cur_ff = len(self.ff_votes[my_team])
        team_name = "Sentinel" if my_team == 0 else "Scourge"
        win_team = 1 - my_team
        win_name = "Scourge" if my_team == 0 else "Sentinel"

        if cur_ff >= needed:
            msg = f"🏳️ {team_name} баг бууж өглөө (-gg {cur_ff}/{needed}) — 🏆 {win_name} баг яллаа! (ELO оноо тооцогдлоо)"
            await self.reset_room_for_remake(msg, score_winner_team=win_team)
            return True, msg + " Өрөө LAN дээр дахин бэлэн боллоо!"

        wait_msg = f"🏳️ «{sender_name}» ({team_name}) бууж өгөх (-gg {cur_ff}/{needed}) санал өглөө. Багийн бусад гишүүд -gg бичиж баталгаажуулна уу."
        await self.send_all_chat(f"|cFFFFCC00[MongolRanger]|r {wait_msg}")
        if self.on_chat_announce_cb is not None:
            try:
                self.on_chat_announce_cb(self.room_id, wait_msg)
            except Exception:
                pass
        return True, wait_msg

    def get_wait_remaining_sec(self) -> int:
        if not self.absent or self.phase not in ("FROZEN", "WAITING", "LOADING") or self.wait_started_at <= 0:
            return 0
        rem = (self.wait_started_at + self.wait_duration_sec) - time.time()
        return max(0, int(round(rem)))

    async def add_wait_time(self, sender_name: str) -> tuple[bool, str, int]:
        if not self.absent or self.phase not in ("FROZEN", "WAITING", "LOADING"):
            return False, "Одоогоор хүлээгдэж буй гарсан тоглогч байхгүй байна.", 0
        now_m = time.monotonic()
        dedup_key = (sender_name.lower(), "add_wait_time")
        if now_m - self._cmd_dedup.get(dedup_key, 0.0) < 1.2:
            rem = self.get_wait_remaining_sec()
            return True, f"⏳ Хүлээх хугацаа сунгагдсан байна (Нийт үлдсэн: {rem} сек).", rem
        self._cmd_dedup[dedup_key] = now_m
        if self.addtime_count >= self.addtime_max:
            rem = self.get_wait_remaining_sec()
            return False, f"Хугацаа сунгах эрх дууссан байна ({self.addtime_count}/{self.addtime_max} удаа ашигласан • Үлдсэн: {rem} сек).", rem
        if self.get_wait_remaining_sec() <= 0:
            self.wait_started_at = time.time()
            self.wait_duration_sec = 60.0
        else:
            self.wait_duration_sec += 60.0
        self.addtime_count += 1
        self.host_drop_unlocked_sent = False
        self.warned_20s_addtime = False
        rem = self.get_wait_remaining_sec()
        absent_peer = self.peers.get(self.absent)
        if absent_peer:
            for name, peer in list(self.peers.items()):
                if name != self.absent and peer.writer is not None and peer.loaded:
                    await self.send(peer, lag(absent_peer.pid, False))
                    await self.send(peer, lag(absent_peer.pid, True, self._lag_ms_for(name, rem)))
        msg = f"⏳ «{sender_name}» хүлээх хугацааг +1 минутаар (+60 сек) сунгалаа! ({self.addtime_count}/{self.addtime_max} эрх ашигласан • Нийт үлдсэн: {rem} сек)"
        await self.send_all_chat(f"|cFF00FF88[MongolRanger]|r {msg}")
        self.event("wait_time_extended", by=sender_name, used=self.addtime_count, remaining_sec=rem)
        return True, msg, rem

    async def drop_absent_player_by_host(self, actor_name: str, allow_self: bool = False) -> tuple[bool, str]:
        if not self.absent or self.phase not in ("FROZEN", "WAITING", "LOADING"):
            return False, "Одоогоор хүлээгдэж буй тоглогч байхгүй байна."
        if not allow_self and actor_name != self.owner_name:
            return False, f"Зөвхөн өрөөний Host ({self.owner_name}) хүлээж буй тоглогчийг Drop хийх эрхтэй!"
        if not allow_self and self.absent == actor_name:
            return False, "Host өөрөө өөрийгөө өрөөнөөс Drop/Kick хийх боломжгүй! ТОГЛОЛТОНД БУЦАЖ ОРОХ (REJOIN) товчийг дарж тоглолт руугаа орно уу."
        alive_other = [p for p in self.peers.values() if p.writer is not None and p.name != self.absent]
        rem = self.get_wait_remaining_sec()
        if rem > 0 and alive_other:
            return False, f"Хүлээх хугацаа дуусаагүй байна! ({rem} секунд үлдсэн байна)"
        dropped_name = self.absent
        if not alive_other:
            await self.reset_room_for_remake("🔄 Хүлээх горим цуцлагдаж өрөө LAN дээр дахин бэлэн боллоо!")
            return True, "🔄 Хүлээх горим цуцлагдаж өрөө Лобби төлөвт шилжлээ."
        absent_peer = self.peers.pop(dropped_name, None)
        self.disconnected_players.discard(dropped_name)
        self.kicked_players.add(dropped_name)
        st = self.ensure_player_stat(dropped_name)
        st["abandoned"] = True
        self.absent = None
        self.lag_active_since = 0.0
        self.wait_started_at = 0.0
        self.host_drop_unlocked_sent = False
        if absent_peer:
            if 0 <= absent_peer.sid < len(self.slots):
                self.slots[absent_peer.sid]["pid"] = 0
                self.slots[absent_peer.sid]["download"] = 255
                self.slots[absent_peer.sid]["status"] = 0
            for name, peer in list(self.peers.items()):
                if peer.writer is not None:
                    await self.send(peer, lag(absent_peer.pid, False))
                    await self.send(peer, send_w3gs_playerleave_others(absent_peer.pid, 7))
        alive_peers = [p for p in self.peers.values() if p.writer is not None]
        if alive_peers:
            await self.send_all_chat(f"|cFFFF5555[MongolRanger]|r Хүлээх хугацаа (3 мин) дууссан тул Host «{dropped_name}» тоглогчийг хаслаа (Drop). Тоглолт үргэлжилж байна!")
            self.phase = "CONTINUING"
            self.gate = CheckpointGate([n for n, p in self.peers.items() if p.writer is not None and p.loaded])
            self.last_tick_time = 0.0
            self.schedule_next_tick()
        else:
            self.phase = "LOBBY"
        self.event("absent_player_dropped_by_host", dropped=dropped_name, host=actor_name)
        if self.on_player_dropped_cb is not None:
            try:
                self.on_player_dropped_cb(self, dropped_name)
            except Exception:
                pass
        return True, f"👢 Хүлээх хугацаа дууссан тул Host «{dropped_name}» тоглогчийг тоглолтоос хаслаа (Drop)."

    def _lag_ms_for(self, name: str, rem: int) -> int:
        """Elapsed lag (ms) for W3GS_START_LAG so the patched 180 s Game.dll dialog shows the real remaining time.

        Only the Host may reach 0 s (which enables the native Drop Players button); everyone else stays at >= 1 s.
        """
        rem = max(0, min(180, int(rem)))
        elapsed = (180 - rem) * 1000
        if name != self.owner_name:
            elapsed = min(elapsed, 179000)
        return elapsed

    def _peer_by_colour(self, colour: int) -> RoomPeer | None:
        for peer in self.peers.values():
            if 0 <= peer.sid < len(self.slots) and self.slots[peer.sid].get("colour") == colour:
                return peer
        return None

    def _name_by_colour(self, colour: int) -> str | None:
        peer = self._peer_by_colour(colour)
        if peer is not None:
            return peer.name
        return self.colour_to_name.get(colour)

    def ensure_player_stat(self, name: str) -> dict:
        peer = self.peers.get(name)
        if peer and 0 <= peer.sid < len(self.slots):
            c_val = int(self.slots[peer.sid].get("colour", 1))
            self.colour_to_name[c_val] = name
        if name not in self.player_stats:
            team = 0
            colour = 1
            if peer and 0 <= peer.sid < len(self.slots):
                team = self.slots[peer.sid].get("team", 0)
                colour = self.slots[peer.sid].get("colour", 1)
            self.player_stats[name] = {
                "kills": 0,
                "deaths": 0,
                "assists": 0,
                "team": team,
                "colour": colour,
                "reconnected": 0,
                "abandoned": False,
            }
        return self.player_stats[name]

    def event(self, kind: str, **fields):
        self.updated_at = time.time()
        entry = {"t": round(time.time(), 3), "event": kind, "phase": self.phase, **fields}
        self.events.append(entry)
        self.dbg("event", **{k: v for k, v in entry.items() if k not in ("t", "phase")})

    def dbg(self, kind: str, **fields):
        rec = {"t": round(time.time(), 4), "k": kind, "ph": self.phase, **fields}
        self.turn_ring.append(rec)
        # Never perform synchronous disk I/O during CONTINUING lockstep play;
        # turn_ring keeps the rolling history in memory and flushes once if a drop occurs.
        fh = self.debug_fh
        if fh is not None and (self.phase != "CONTINUING" or kind in ("event", "act")):
            try:
                import json as _json
                fh.write(_json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            except Exception:
                pass

    def start_debug_capture(self, reason: str):
        try:
            import json as _json
            d = Path(os.environ.get("MONGOLRANGER_DEBUG_DIR", "/var/lib/mongolranger/debug"))
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                d = Path(tempfile.gettempdir()) / "mongolranger_debug"
                d.mkdir(parents=True, exist_ok=True)
            if self.debug_fh is not None:
                try:
                    self.debug_fh.close()
                except Exception:
                    pass
            path = d / f"w3gs_{self.room_id[:8]}_{int(time.time())}_{reason}.jsonl"
            fh = open(path, "w", encoding="utf-8", buffering=1)
            fh.write(_json.dumps({"k": "header", "room": self.room_id, "reason": reason,
                                  "peers": {n: {"pid": p.pid, "sid": p.sid, "frames": p.frames, "checks": p.checks}
                                            for n, p in self.peers.items()}}, default=str) + "\n")
            for rec in list(self.turn_ring):
                fh.write(_json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self.debug_fh = fh
            self.debug_until = time.time() + 600.0
        except Exception:
            self.debug_fh = None

    def stop_debug_capture_if_due(self):
        if self.debug_fh is not None and time.time() > self.debug_until:
            try:
                self.debug_fh.close()
            except Exception:
                pass
            self.debug_fh = None

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def ensure_background_tasks(self):
        if not self._bg_started:
            self._bg_started = True
            self.spawn(self._ping_and_wait_loop())

    def close(self):
        if self.debug_fh is not None:
            try:
                self.debug_fh.close()
            except Exception:
                pass
            self.debug_fh = None
        if self.host_ctrl_writer is not None:
            try:
                self.host_ctrl_writer.close()
            except Exception:
                pass
            self.host_ctrl_writer = None
        for fut in list(self.pending_tunnels.values()):
            if not fut.done():
                fut.cancel()
        self.pending_tunnels.clear()
        for t in list(self.tasks):
            t.cancel()
        for p in list(self.peers.values()):
            if p.writer is not None:
                try:
                    p.writer.close()
                except Exception:
                    pass
                p.writer = None
            if p.tunnel_writer is not None:
                try:
                    p.tunnel_writer.close()
                except Exception:
                    pass
                p.tunnel_writer = None

    def _patch_raw_gameinfo(self, raw: bytes, counter: int, local_port: int, custom_title: str | None = None) -> bytes:
        if len(raw) < 26 or raw[:2] != b"\xf7\x30":
            return b""
        try:
            name_end = raw.index(0, 20)
            title_bytes = (to_wc3_latin(custom_title or self.name) or "ZevArena").encode("utf-8")[:31]
            new_payload = (
                raw[4:12]
                + struct.pack("<II", counter & 0x0FFFFFFF, self.entry_key & 0xFFFFFFFF)
                + title_bytes + b"\x00"
                + raw[name_end + 1 : -2]
                + struct.pack("<H", local_port & 0xFFFF)
            )
            return packet(0x30, new_payload)
        except ValueError:
            pkt = bytearray(raw)
            pkt[12:20] = struct.pack("<II", counter & 0x0FFFFFFF, self.entry_key & 0xFFFFFFFF)
            pkt[-2:] = struct.pack("<H", local_port & 0xFFFF)
            return bytes(pkt)

    async def set_host_lan_ad_async(self, raw_gameinfo: bytes, host_port: int = 6112):
        if not raw_gameinfo or len(raw_gameinfo) < 26 or raw_gameinfo[:2] != b"\xf7\x30":
            self.host_raw_gameinfo = b""
            self.updated_at = time.time()
            return
        orig_counter, orig_key = struct.unpack_from("<II", raw_gameinfo, 12)
        if self.phase != "LOBBY":
            await self.reset_room_for_remake("🔄 Host Warcraft III дотор шинээр Create Game үүсгэлээ!", score_winner_team=self.winner_team)
        self.orig_host_counter = orig_counter
        self.orig_entry_key = orig_key
        ad_port = struct.unpack_from("<H", raw_gameinfo, len(raw_gameinfo) - 2)[0]
        self.host_war3_port = int(host_port or ad_port or 6112)
        self.host_raw_gameinfo = bytes(raw_gameinfo)
        self.last_host_gameinfo_snapshot = bytes(raw_gameinfo)
        self.host_raw_updated_at = time.time()
        self.updated_at = time.time()

    def get_lan_advertisement(self, local_port: int = 6210, viewer_name: str | None = None) -> bytes:
        up_time = max(1, int(time.monotonic() - self.created_at))
        if viewer_name is not None:
            # The Room Host clicks "Create Game" inside Warcraft III themselves -> never broadcast a LAN ad to the Host!
            if self.owner_name and viewer_name.lower() == self.owner_name.lower():
                return b""
            if self.phase in ("WAITING", "LOADING", "CONTINUING") and viewer_name in self.disconnected_players:
                if self.last_host_gameinfo_snapshot and len(self.last_host_gameinfo_snapshot) >= 26:
                    return self._patch_raw_gameinfo(
                        self.last_host_gameinfo_snapshot,
                        self.rejoin_counter,
                        local_port,
                        custom_title=f"REJOIN {self.name}",
                    )
                if self.checkpoint_info:
                    return build_w3gs_gameinfo(
                        game_name="Rejoin Checkpoint",
                        host_port=local_port,
                        host_counter=self.rejoin_counter,
                        entry_key=self.entry_key,
                        up_time=up_time,
                        save_filename=self.checkpoint_info["filename"],
                        save_magic=self.checkpoint_info["magic"],
                        map_path=self.map_path,
                        map_width=self.map_width,
                        map_height=self.map_height,
                        map_crc=self.map_crc,
                        map_sha1=self.map_sha1,
                    )
            if self.phase == "LOBBY":
                if self.host_raw_gameinfo and len(self.host_raw_gameinfo) >= 26 and (time.time() - self.host_raw_updated_at) <= 6.0:
                    return self._patch_raw_gameinfo(
                        self.host_raw_gameinfo,
                        self.host_counter,
                        local_port,
                        custom_title=self.name,
                    )
                return b""
            return b""
        if self.phase == "FROZEN":
            # Do not broadcast a stale pre-save lobby advertisement while waiting for the survivor's .w3z checkpoint upload
            return b""
        if self.phase in ("WAITING", "LOADING") and self.checkpoint_info:
            return build_w3gs_gameinfo(
                game_name="Rejoin Checkpoint",
                host_port=local_port,
                host_counter=self.rejoin_counter,
                entry_key=self.entry_key,
                up_time=up_time,
                save_filename=self.checkpoint_info["filename"],
                save_magic=self.checkpoint_info["magic"],
                map_path=self.map_path,
                map_width=self.map_width,
                map_height=self.map_height,
                map_crc=self.map_crc,
                map_sha1=self.map_sha1,
            )
        return build_w3gs_gameinfo(
            game_name=self.name,
            host_port=local_port,
            host_counter=self.host_counter,
            entry_key=self.entry_key,
            up_time=up_time,
            map_path=self.map_path,
            map_width=self.map_width,
            map_height=self.map_height,
            map_crc=self.map_crc,
            map_sha1=self.map_sha1,
        )

    def reset_nettag_maps(self):
        self.hero_nt_parts.clear()
        self.latest_tag.clear()
        self.latest_tag_ts.clear()
        self.paired_tags.clear()
        self.tag_map.clear()
        self.pos_sync_count = 0

    def extract_and_strip_hero_nt(self, peer_name: str, raw_body: bytes) -> bytes:
        if raw_body and 0x20 <= raw_body[0] <= 0x32:
            # Block injected Warcraft III cheat opcodes (0x2F RemoveFogOfWar / iseedeadpeople, 0x26 GodMode, 0x27 Gold, etc.)
            self.event("anti_cheat_opcode_blocked", player=peer_name, opcode=hex(raw_body[0]))
            return b""
        if self.phase != "FROZEN" and b"\x07\x01\0\0\0" in raw_body:
            # Strip any late save-completion ack from a slower survivor so it never leaks into CONTINUING turns
            raw_body = raw_body.replace(b"\x07\x01\0\0\0", b"")
            if not raw_body:
                return b""
        prefix = b"\x6bdr.x\x00"
        if prefix not in raw_body:
            return raw_body
        pos = 0
        now_m = time.monotonic()
        while pos < len(raw_body):
            idx = raw_body.find(prefix, pos)
            if idx == -1:
                break
            mkey_start = idx + len(prefix)
            mkey_end = raw_body.find(b"\x00", mkey_start)
            if mkey_end == -1:
                break
            key_start = mkey_end + 1
            key_end = raw_body.find(b"\x00", key_start)
            if key_end == -1 or key_end + 5 > len(raw_body):
                break
            mkey = raw_body[mkey_start:mkey_end].decode("ascii", errors="replace")
            key_str = raw_body[key_start:key_end].decode("ascii", errors="replace")
            val = struct.unpack_from("<I", raw_body, key_end + 1)[0]
            pos = key_end + 5

            # 1. Live DotA / LoD Kill, Death, Assist & Winner parsing from dr.x GameCache
            if mkey == "Data" and key_str.startswith("Hero") and key_str[4:].isdigit():
                victim_col = int(key_str[4:])
                killer_col = int(val)
                dedup_key = (killer_col, victim_col)
                if now_m - self.kill_dedup.get(dedup_key, 0.0) > 2.5:
                    self.kill_dedup[dedup_key] = now_m
                    victim_name = self._name_by_colour(victim_col)
                    if victim_name:
                        vst = self.ensure_player_stat(victim_name)
                        vst["deaths"] += 1
                    if 1 <= killer_col <= 11 and killer_col != victim_col:
                        killer_name = self._name_by_colour(killer_col)
                        if killer_name:
                            kst = self.ensure_player_stat(killer_name)
                            kst["kills"] += 1
                            self.event("dota_kill", killer=killer_name, victim=victim_name or str(victim_col), kills=kst["kills"])
                continue

            if mkey == "Data" and key_str.startswith("Assist") and key_str[6:].isdigit():
                assister_col = int(key_str[6:])
                victim_col = int(val)
                dedup_key = (assister_col, victim_col)
                if now_m - self.assist_dedup.get(dedup_key, 0.0) > 2.5:
                    self.assist_dedup[dedup_key] = now_m
                    assister_name = self._name_by_colour(assister_col)
                    if assister_name:
                        ast = self.ensure_player_stat(assister_name)
                        ast["assists"] += 1
                continue

            if mkey.isdigit() and 1 <= int(mkey) <= 11:
                p_col = int(mkey)
                t_name = self._name_by_colour(p_col)
                if t_name and 0 <= val <= 250:
                    pst = self.ensure_player_stat(t_name)
                    if key_str == "1":
                        pst["kills"] = max(pst["kills"], int(val))
                    elif key_str == "2":
                        pst["deaths"] = max(pst["deaths"], int(val))
                    elif key_str == "5":
                        pst["assists"] = max(pst["assists"], int(val))
                continue

            if mkey in ("Data", "Global") and key_str == "Winner" and val in (1, 2):
                if self.winner_team is None:
                    self.winner_team = 0 if val == 1 else 1
                    self.event("dota_winner", winner_team=self.winner_team)
                    now_win = time.time()
                    for pname, st in self.player_stats.items():
                        if (
                            pname in self.peers
                            or self.initial_player_count < 10
                            or (now_win - float(st.get("quit_at", 0.0))) < 300.0
                        ):
                            st["abandoned"] = False
                    if self.on_match_complete_cb is not None and not self.match_scored:
                        try:
                            self.on_match_complete_cb(self)
                        except Exception:
                            pass
                continue

            if mkey.startswith("S") and key_str == "P" and val > 0:
                self.pos_sync_count += 1
                continue
            if not (mkey.startswith("NT") or mkey.startswith("I")):
                continue
            parts = self.hero_nt_parts.setdefault((peer_name, mkey), {})
            parts[key_str] = val
            if "1" in parts and "2" in parts:
                tag_bytes = struct.pack("<II", parts.pop("1"), parts.pop("2"))
                prev_tag = self.latest_tag.get((peer_name, mkey))
                if prev_tag and prev_tag != tag_bytes:
                    for other_name in self.peers:
                        if other_name == peer_name:
                            continue
                        fwd_map = self.tag_map.get((peer_name, other_name))
                        if fwd_map:
                            fwd_map.pop(prev_tag, None)
                        rev_map = self.tag_map.get((other_name, peer_name))
                        if rev_map:
                            for rk, rv in list(rev_map.items()):
                                if rv == prev_tag:
                                    rev_map.pop(rk, None)
                self.latest_tag[(peer_name, mkey)] = tag_bytes
                self.latest_tag_ts[(peer_name, mkey)] = now_m
                for other_name in self.peers:
                    if other_name == peer_name:
                        continue
                    other_tag = self.latest_tag.get((other_name, mkey))
                    other_ts = self.latest_tag_ts.get((other_name, mkey), 0.0)
                    # Only pair NetTags emitted on the same simulation event (within 1.5s);
                    # never pair a newly moved/bought item in slot I{i}{s} with a stale item from minutes ago!
                    if other_tag and abs(now_m - other_ts) <= 1.5:
                        fwd_map = self.tag_map.setdefault((peer_name, other_name), {})
                        rev_map = self.tag_map.setdefault((other_name, peer_name), {})
                        if tag_bytes == other_tag:
                            fwd_map.pop(tag_bytes, None)
                            rev_map.pop(other_tag, None)
                        else:
                            fwd_map[tag_bytes] = other_tag
                            rev_map[other_tag] = tag_bytes
                        pair_key = (mkey, tuple(sorted((peer_name, other_name))))
                        pair_val = (
                            self.latest_tag.get((pair_key[1][0], mkey)),
                            self.latest_tag.get((pair_key[1][1], mkey)),
                        )
                        if self.paired_tags.get(pair_key) != pair_val:
                            self.paired_tags[pair_key] = pair_val
                            self.event(
                                "hero_nettag_mapped",
                                slot=mkey,
                                peer_a=pair_key[1][0],
                                tag_a=pair_val[0].hex(),
                                peer_b=pair_key[1][1],
                                tag_b=pair_val[1].hex(),
                                same=(pair_val[0] == pair_val[1]),
                            )
        return raw_body

    async def _confirm_quit_leaver(self, quit_name: str, hc: int):
        """Confirm leaver ONLY if remaining players continue playing for 5 full minutes (300s) after F10->E->Q."""
        for _ in range(60):
            await asyncio.sleep(5.0)
            if self.host_counter != hc or self.phase == "LOBBY" or self.match_scored or self.winner_team is not None:
                st = self.player_stats.get(quit_name)
                if st is not None:
                    st["abandoned"] = False
                return
            t0_chk = sum(
                1 for px in self.peers.values()
                if px.writer is not None and 0 <= px.sid < len(self.slots) and int(self.slots[px.sid].get("team", 0)) == 0
            )
            t1_chk = sum(
                1 for px in self.peers.values()
                if px.writer is not None and 0 <= px.sid < len(self.slots) and int(self.slots[px.sid].get("team", 0)) == 1
            )
            if t0_chk == 0 or t1_chk == 0:
                st = self.player_stats.get(quit_name)
                if st is not None:
                    st["abandoned"] = False
                return
        st = self.ensure_player_stat(quit_name)
        st["abandoned"] = True
        self.kicked_players.add(quit_name)
        self.event("player_quit_leaver", name=quit_name)
        self.last_drop_reason = "quit"
        if self.on_player_dropped_cb is not None:
            try:
                self.on_player_dropped_cb(self, quit_name)
            except Exception:
                pass
        self.last_drop_reason = "drop"

    async def kick_player(self, player_name: str, reason: str = "Host өрөөнөөс гаргалаа"):
        self.event("host_kick_player", player=player_name, reason=reason)
        self.kicked_players.add(player_name)
        await self.send_all_chat(f"|cFFFF8800[MongolRanger]|r {player_name} өрөөнөөс хасагдлаа ({reason}).")
        peer = self.peers.pop(player_name, None)
        if peer:
            if 0 <= peer.sid < len(self.slots):
                self.slots[peer.sid]["pid"] = 0
                self.slots[peer.sid]["download"] = 255
                self.slots[peer.sid]["status"] = 0
            if peer.writer is not None:
                try:
                    peer.writer.close()
                except Exception:
                    pass
                peer.writer = None
            await self.broadcast(send_w3gs_playerleave_others(peer.pid, 7), exclude_name=player_name)
            await self.send_all_slot_info()

    async def report_and_kick_cheater(self, player_name: str, reason: str):
        self.event("anti_maphack_kick", player=player_name, reason=reason)
        if not hasattr(self, "kicked_cheaters"):
            self.kicked_cheaters = set()
        self.kicked_cheaters.add(player_name)
        await self.send_all_chat(f"|cFFFF3333[Anti-MapHack]|r {player_name} MapHack/Cheat илэрсэн тул тоглоомоос хасагдлаа! ({reason})")
        peer = self.peers.get(player_name)
        if peer:
            if peer.writer is not None:
                try:
                    peer.writer.close()
                except Exception:
                    pass
                peer.writer = None
            await self.broadcast(send_w3gs_playerleave_others(peer.pid, 7), exclude_name=player_name)

    def translate_nettags(self, sender_name: str, target_name: str, body: bytes) -> bytes:
        if sender_name == target_name or not body:
            return body
        mapping = self.tag_map.get((sender_name, target_name))
        if not mapping:
            return body
        out = body
        for src_tag, dst_tag in mapping.items():
            if src_tag != dst_tag and src_tag in out:
                out = out.replace(src_tag, dst_tag)
        return out

    async def send(self, peer: RoomPeer, data: bytes):
        if peer.writer is not None and data:
            if len(data) > 1 and data[1] in (0x0C, 0x10, 0x11):
                self.dbg("out", to=peer.name, fr=peer.frames, ck=peer.checks, hex=data.hex()[:400])
            try:
                peer.writer.write(data)
                if len(data) < 2 or data[1] != 0x0C:
                    await peer.writer.drain()
            except (ConnectionError, OSError):
                peer.writer = None

    async def broadcast(self, data: bytes, exclude_name: str | None = None):
        for name, peer in list(self.peers.items()):
            if name != exclude_name:
                await self.send(peer, data)

    async def send_all_slot_info(self):
        if self.phase == "LOBBY":
            await self.broadcast(send_w3gs_slotinfo(self.slots, self.random_seed))

    async def send_all_chat(self, message: str):
        to_pids = [p.pid for p in self.peers.values() if p.writer is not None]
        if not to_pids:
            return
        from_pid = self.vhost_pid if self.phase == "LOBBY" else to_pids[0]
        flag = 16 if self.phase == "LOBBY" else 32
        extra = b"" if self.phase == "LOBBY" else b"\x00\x00\x00\x00"
        for line in message.split("\n"):
            line_s = line.strip()
            if not line_s:
                continue
            pkt = send_w3gs_chat_from_host(from_pid, to_pids, flag, extra, line_s)
            await self.broadcast(pkt)

    def _allocate_pid(self) -> int:
        used = {p.pid for p in self.peers.values()} | {self.vhost_pid}
        for candidate in range(1, 12):
            if candidate not in used:
                return candidate
        return 1

    def _is_human_slot(self, sid: int) -> bool:
        if not (0 <= sid < len(self.slots)):
            return False
        s = self.slots[sid]
        return s.get("status") == 2 and s.get("computer", 0) == 0 and s.get("pid", 0) > 0

    def _set_slot_computer(self, sid: int, difficulty: int = 1, locked: bool = False) -> bool:
        if not (0 <= sid < len(self.slots)) or self._is_human_slot(sid):
            return False
        s = self.slots[sid]
        s["pid"] = 0
        s["download"] = 100
        s["status"] = 2
        s["computer"] = 1
        s["difficulty"] = difficulty
        s["locked"] = locked
        return True

    def _set_slot_open(self, sid: int) -> bool:
        if not (0 <= sid < len(self.slots)) or self._is_human_slot(sid):
            return False
        s = self.slots[sid]
        s["pid"] = 0
        s["download"] = 255
        s["status"] = 0
        s["computer"] = 0
        s["difficulty"] = 1
        s["locked"] = False
        return True

    def _set_slot_closed(self, sid: int) -> bool:
        if not (0 <= sid < len(self.slots)) or self._is_human_slot(sid):
            return False
        s = self.slots[sid]
        s["pid"] = 0
        s["download"] = 255
        s["status"] = 1
        s["computer"] = 0
        s["difficulty"] = 1
        s["locked"] = True
        return True

    async def update_map_meta(self, map_meta: dict):
        if self.phase != "LOBBY" or not map_meta:
            return
        self.map_path = map_meta.get("map_path", self.map_path)
        if "map_size" in map_meta:
            self.map_size = bytes(map_meta["map_size"])
            self.map_size_int = struct.unpack("<I", self.map_size)[0]
        if "map_info" in map_meta:
            self.map_info = bytes(map_meta["map_info"])
        if "map_crc" in map_meta:
            self.map_crc = bytes(map_meta["map_crc"])
        if "map_sha1" in map_meta:
            self.map_sha1 = bytes(map_meta["map_sha1"])
        if "map_width" in map_meta:
            self.map_width = bytes(map_meta["map_width"])
        if "map_height" in map_meta:
            self.map_height = bytes(map_meta["map_height"])
        if map_meta.get("slots"):
            self.default_slots = [dict(s) for s in map_meta["slots"]]
        if not self.peers:
            self.slots = [dict(s) for s in self.default_slots]
            self.host_counter = ((self.host_counter + 1) & 0x0FFFFFFF) or 1
        else:
            for peer in list(self.peers.values()):
                if peer.writer is not None:
                    await self.send(peer, send_w3gs_mapcheck(self.map_path, self.map_size, self.map_info, self.map_crc, self.map_sha1))
            await self.send_all_slot_info()

    async def host_set_slot(self, actor_name: str, action: str, slot: int = 0, target_slot: int = 0) -> tuple[bool, str]:
        if self.phase != "LOBBY":
            return False, "Зөвхөн Лобби дотор суудал тохируулна."
        if not self._is_effective_host(actor_name):
            return False, "Зөвхөн Host суудал тохируулах эрхтэй."
        act = (action or "").strip().lower()
        sid = slot - 1
        if act == "start":
            started = await self.start_game(force=True)
            return started, "started" if started else "not_started"
        if act == "swap":
            tsid = target_slot - 1
            if 0 <= sid < len(self.slots) and 0 <= tsid < len(self.slots) and sid != tsid:
                await self.swap_slots(sid, tsid)
                return True, f"Slot {slot} <-> {target_slot}"
            return False, "Invalid swap slots"
        if act in ("1v1", "2v2", "3v3", "4v4"):
            await self.apply_team_size_preset(int(act[0]), difficulty=1)
            return True, act
        if act in ("5v5", "openall", "clear"):
            for i in range(len(self.slots)):
                self._set_slot_open(i)
            await self.send_all_slot_info()
            return True, "5v5"
        if not (0 <= sid < len(self.slots)):
            return False, "Invalid slot"
        # If a non-host human player is occupying this slot and the Host sets it to Closed or Computer, kick that player first
        if self._is_human_slot(sid) and act in ("closed", "close", "easy", "normal", "insane"):
            occ = next((p for p in self.peers.values() if p.sid == sid), None)
            if occ and not self._is_effective_host(occ.name):
                await self.kick_player(occ.name, "Host суудлыг хаалаа")
        if act == "open":
            self._set_slot_open(sid)
        elif act in ("closed", "close"):
            self._set_slot_closed(sid)
        elif act == "easy":
            self._set_slot_computer(sid, difficulty=0, locked=True)
        elif act == "normal":
            self._set_slot_computer(sid, difficulty=1, locked=True)
        elif act in ("insane", "hard"):
            self._set_slot_computer(sid, difficulty=2, locked=True)
        else:
            return False, "Unknown action"
        await self.send_all_slot_info()
        return True, act

    def _parse_slot_targets(self, args: list[str]) -> list[int]:
        out: list[int] = []
        for token in args:
            for sub in token.replace(",", " ").split():
                if "-" in sub:
                    bounds = sub.split("-", 1)
                    if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                        a, b = int(bounds[0]), int(bounds[1])
                        if a > b:
                            a, b = b, a
                        for n in range(max(1, a), min(len(self.slots), b) + 1):
                            if (n - 1) not in out:
                                out.append(n - 1)
                elif sub.isdigit():
                    n = int(sub)
                    if 1 <= n <= len(self.slots) and (n - 1) not in out:
                        out.append(n - 1)
        return out

    async def apply_team_size_preset(self, per_team: int, difficulty: int = 1):
        if self.phase != "LOBBY":
            return
        per_team = max(1, min(5, per_team))
        for team_id in (0, 1):
            team_sids = [i for i, s in enumerate(self.slots) if s.get("team") == team_id]
            human_sids = [i for i in team_sids if self._is_human_slot(i)]
            # If the top slot of this team is unoccupied while a human sits in a lower slot and no open slots are needed,
            # move the first human into the top slot so Computer AI never sits above human players in 1v1/2v2/3v3/4v4.
            if human_sids and len(human_sids) >= per_team and not self._is_human_slot(team_sids[0]):
                await self.swap_slots(team_sids[0], human_sids[0])
                human_sids = [i for i in team_sids if self._is_human_slot(i)]
            open_needed = max(0, per_team - len(human_sids))
            for i in team_sids:
                if i in human_sids:
                    continue
                if open_needed > 0:
                    self._set_slot_open(i)
                    open_needed -= 1
                else:
                    self._set_slot_computer(i, difficulty=difficulty, locked=True)
        await self.send_all_slot_info()

    def _allocate_sid(self, preferred_team: int | None = None, player_name: str | None = None, allow_replace_comp: bool = False) -> int:
        is_host = bool(player_name and self.owner_name and player_name.lower() == self.owner_name.lower())
        if is_host and preferred_team is None:
            # Host always sits in Slot 1 (sid = 0, Sentinel Blue)
            if len(self.slots) > 0 and not self._is_human_slot(0):
                return 0
        # Non-host players never auto-allocate into Slot 1 (sid = 0); reserve Slot 1 for Host
        start_idx = 0 if is_host else 1
        if preferred_team is not None:
            for idx in range(start_idx, len(self.slots)):
                s = self.slots[idx]
                if s["status"] == 0 and s["team"] == preferred_team:
                    return idx
            if is_host and len(self.slots) > 0 and self.slots[0]["status"] == 0 and self.slots[0]["team"] == preferred_team:
                return 0
            if allow_replace_comp:
                for idx in range(start_idx, len(self.slots)):
                    s = self.slots[idx]
                    if s.get("computer", 0) == 1 and s["team"] == preferred_team:
                        return idx
                return -1
        # Balance teams automatically on initial join: Sentinel (0) then Scourge (1) — count only human players!
        team_counts = {0: 0, 1: 0}
        for i, s in enumerate(self.slots):
            if self._is_human_slot(i) and s["team"] in team_counts:
                team_counts[s["team"]] += 1
        target_team = 0 if team_counts[0] <= team_counts[1] else 1
        for idx in range(start_idx, len(self.slots)):
            s = self.slots[idx]
            if s["status"] == 0 and s["team"] == target_team:
                return idx
        for idx in range(start_idx, len(self.slots)):
            s = self.slots[idx]
            if s["status"] == 0:
                return idx
        # Fallback: if Host filled all empty slots with unlocked Computer (-normal / -easy / -insane), allow joining human to take a Computer slot
        for idx in range(start_idx, len(self.slots)):
            s = self.slots[idx]
            if s.get("computer", 0) == 1 and not s.get("locked", False) and s["team"] == target_team:
                return idx
        for idx in range(start_idx, len(self.slots)):
            s = self.slots[idx]
            if s.get("computer", 0) == 1 and not s.get("locked", False):
                return idx
        if len(self.slots) > 0 and self.slots[0]["status"] == 0:
            return 0
        return -1

    async def swap_slots(self, sid1: int, sid2: int):
        if self.phase != "LOBBY":
            return
        if not (0 <= sid1 < len(self.slots) and 0 <= sid2 < len(self.slots)) or sid1 == sid2:
            return
        s1, s2 = self.slots[sid1], self.slots[sid2]
        # Fixed player settings: swap pid, download, status, computer, difficulty
        for k in ("pid", "download", "status", "computer", "difficulty"):
            if k in s1 and k in s2:
                s1[k], s2[k] = s2[k], s1[k]
        for p in self.peers.values():
            if p.sid == sid1:
                p.sid = sid2
            elif p.sid == sid2:
                p.sid = sid1
        await self.send_all_slot_info()

    async def start_game(self, force: bool = True):
        if self.phase != "LOBBY" or not self.peers:
            return False
        if not force:
            if any(not p.map_ready for p in self.peers.values()):
                await self.send_all_chat("Players are still downloading the map.")
                return False
        # Ensure Slot 1 (sid = 0, Sentinel Blue) is occupied by a human player before filling Computer AI
        # so DotA / LoD mode commands (-ap, -sd, -sds6...) always work in 1v1/2v2/3v3/4v4
        if len(self.slots) > 0 and not self._is_human_slot(0):
            sentinel_humans = [i for i, s in enumerate(self.slots) if s.get("team") == 0 and self._is_human_slot(i)]
            any_humans = [i for i in range(len(self.slots)) if self._is_human_slot(i)]
            target_human_sid = sentinel_humans[0] if sentinel_humans else (any_humans[0] if any_humans else -1)
            if target_human_sid > 0:
                await self.swap_slots(0, target_human_sid)
        # Auto-fill any unoccupied (Open/Closed) slots with Computer (Normal) so 1v1/2v2/3v3/4v4 starting gold is properly reduced (853 gold)
        if getattr(self, "auto_fill_comp", True):
            filled_any = False
            for sid in range(len(self.slots)):
                if self.slots[sid]["status"] != 2:
                    self._set_slot_computer(sid, difficulty=1, locked=True)
                    filled_any = True
            if filled_any:
                await self.send_all_chat("|cFF00FF88[MongolRanger]|r Hooson suudluudad Computer (Normal) oruulj garaani mongiig taaruullaa (853 gold)!")
        encode_hcl_handicaps(self.slots, self.hcl)
        await self.send_all_slot_info()
        await asyncio.sleep(0.15)
        self.phase = "STARTING"
        self.event("game_starting", players=list(self.peers.keys()), hcl=self.hcl)
        await self.broadcast(send_w3gs_countdown_start())
        await self.broadcast(send_w3gs_playerleave_others(self.vhost_pid, 7))
        await self.broadcast(send_w3gs_countdown_end())
        return True

    def receive_checkpoint_bytes(self, data: bytes) -> dict:
        info = inspect_save_bytes(data)
        if self.checkpoint_info is not None and self.checkpoint_bytes is not None:
            # In a 10-player (multi-survivor) match, all surviving clients try to upload their local bridge_*.w3z.
            # Lock in the first valid checkpoint per disconnect cycle so all players use the exact same .w3z file.
            self.event("checkpoint_duplicate_ignored", file=info["filename"], active_file=self.checkpoint_info["filename"])
            return self.checkpoint_info
        self.checkpoint_bytes = data
        self.checkpoint_info = info
        self.checkpoint_event.set()
        self.event("checkpoint_uploaded", file=info["filename"], bytes=info["bytes"], seed=info["random_seed"])
        return info

    async def _ping_and_wait_loop(self):
        last_ping = time.monotonic()
        while True:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            if now - last_ping >= 5.0:
                last_ping = now
                self.stop_debug_capture_if_due()
                await self.broadcast(send_w3gs_ping_from_host())
            if (
                self.absent
                and self.phase in ("FROZEN", "WAITING")
                and not getattr(self.peers.get(self.absent), "loaded", False)
            ):
                rem = self.get_wait_remaining_sec()
                absent_peer = self.peers.get(self.absent)
                alive_other = [p for n, p in self.peers.items() if n != self.absent and p.writer is not None]
                if rem <= 0 and not alive_other:
                    await self.reset_room_for_remake("⏰ Хүлээх 180 секунд дуусаж тоглолтод тоглогч үлдээгүй тул өрөө Лобби төлөвт шилжлээ.")
                    continue
                if rem <= 0 and not self.host_drop_unlocked_sent:
                    self.host_drop_unlocked_sent = True
                    if absent_peer:
                        for name, peer in list(self.peers.items()):
                            if name != self.absent and peer.writer is not None and peer.loaded:
                                await self.send(peer, lag(absent_peer.pid, False))
                                # Game.dll is patched to a 180000 ms lag window. Unlock the in-game Drop Players
                                # button ONLY for the Host (lag_ms=180000 -> 0s); non-hosts stay locked at 1s.
                                await self.send(peer, lag(absent_peer.pid, True, self._lag_ms_for(name, 0)))
                    exp_msg = f"⏰ «{self.absent}» тоглогчийг хүлээх 180 секунд (3 минут) дууслаа! Зөвхөн Host ({self.owner_name}) Drop товч дарж хасах эрхтэй."
                    await self.send_all_chat(f"|cFFFF5555[MongolRanger]|r {exp_msg}")
                    if self.on_chat_announce_cb is not None:
                        try:
                            self.on_chat_announce_cb(self.room_id, exp_msg)
                        except Exception:
                            pass
                    self.event("wait_timer_expired_host_drop_unlocked", absent=self.absent, host=self.owner_name)
                elif self.lag_active_since > 0.0 and (now - self.lag_active_since) >= 20.0:
                    self.lag_active_since = now
                    if absent_peer:
                        for name, peer in list(self.peers.items()):
                            if name != self.absent and peer.writer is not None and peer.loaded:
                                if name == self.owner_name and rem <= 0:
                                    # Host's Drop button already unlocked; do not re-lock it
                                    continue
                                await self.send(peer, lag(absent_peer.pid, False))
                                await self.send(peer, lag(absent_peer.pid, True, self._lag_ms_for(name, rem)))
                        self.event("wait_connection_refreshed", absent=self.absent, remaining_sec=rem)
                if 0 < rem <= 22 and not self.warned_20s_addtime:
                    self.warned_20s_addtime = True
                    warn_20 = f"⚠️ «{self.absent}» хүлээх хугацаа дуусахад {rem} секунд үлдлээ! ({self.addtime_count}/{self.addtime_max})"
                    if self.on_chat_announce_cb is not None:
                        try:
                            self.on_chat_announce_cb(self.room_id, warn_20)
                        except Exception:
                            pass

    async def handle_host_ctrl(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, framer: Framer):
        old_w = self.host_ctrl_writer
        self.host_ctrl_writer = writer
        if old_w is not None and old_w is not writer:
            try:
                old_w.close()
            except Exception:
                pass
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
        try:
            while True:
                packets = framer.feed(b"")
                for pkt in packets:
                    if len(pkt) < 4 or pkt[0] != 0xF7:
                        continue
                    ptype = pkt[1]
                    if ptype == 0x5D:  # HOST_LAN_AD update from Host's ZevArena client
                        if len(pkt) >= 32:
                            hport = struct.unpack_from("<H", pkt, 4)[0]
                            raw_ad = pkt[6:]
                            await self.set_host_lan_ad_async(raw_ad, hport)
                        else:
                            await self.set_host_lan_ad_async(b"", 6112)
                chunk = await asyncio.wait_for(reader.read(4096), timeout=25.0)
                if not chunk:
                    break
                framer.feed(chunk)
                for pkt in framer.feed(b""):
                    if len(pkt) < 4 or pkt[0] != 0xF7:
                        continue
                    ptype = pkt[1]
                    if ptype == 0x5D:
                        if len(pkt) >= 32:
                            hport = struct.unpack_from("<H", pkt, 4)[0]
                            raw_ad = pkt[6:]
                            await self.set_host_lan_ad_async(raw_ad, hport)
                        else:
                            await self.set_host_lan_ad_async(b"", 6112)
        except Exception:
            pass
        finally:
            if self.host_ctrl_writer is writer:
                self.host_ctrl_writer = None
                self.host_raw_gameinfo = b""
            try:
                writer.close()
            except Exception:
                pass

    def resolve_host_tunnel(self, tunnel_id: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, framer: Framer) -> bool:
        fut = self.pending_tunnels.pop(tunnel_id, None)
        if fut is not None and not fut.done():
            sock = writer.get_extra_info("socket")
            if sock is not None:
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
            fut.set_result((reader, writer, framer))
            return True
        return False

    async def open_host_tunnel(self, timeout: float = 5.0) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, Framer] | None:
        if self.host_ctrl_writer is None:
            return None
        self._tunnel_seq += 1
        tid = f"t{self._tunnel_seq}_{int(time.monotonic() * 1000) & 0xFFFF}"
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.pending_tunnels[tid] = fut
        try:
            cmd_pkt = packet(0x5B, f"{tid}:{self.host_war3_port}".encode("utf-8"))
            self.host_ctrl_writer.write(cmd_pkt)
            await self.host_ctrl_writer.drain()
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            self.pending_tunnels.pop(tid, None)
            return None

    def _parse_and_update_slot_block(self, block: bytes):
        if len(block) < 3:
            return
        count = block[2]
        if not (1 <= count <= 12) or len(block) < 3 + count * 9 + 6:
            return
        fields = ("pid", "download", "status", "computer", "team", "colour", "race", "difficulty", "handicap")
        pos = 3
        parsed_slots = []
        for _ in range(count):
            parsed_slots.append(dict(zip(fields, block[pos : pos + 9])))
            pos += 9
        self.slots = parsed_slots
        self.random_seed = struct.unpack_from("<I", block, pos)[0]
        for p in self.peers.values():
            if p.pid > 0:
                for idx, s in enumerate(self.slots):
                    if s.get("pid") == p.pid and s.get("status") == 2 and s.get("computer") == 0:
                        p.sid = idx
                        break

    async def _handle_native_rejoin(self, peer: RoomPeer, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, framer: Framer):
        peer.writer = writer
        peer.loaded = False
        self.disconnected_players.discard(peer.name)
        if self.absent == peer.name:
            self.absent = next(iter(self.disconnected_players), None)
        self.phase = "LOADING"
        st = self.ensure_player_stat(peer.name)
        st["reconnected"] = st.get("reconnected", 0) + 1
        if self.last_slotinfo_pkt and len(self.last_slotinfo_pkt) > 4 and len(peer.join_slotinfojoin_pkt) >= 21:
            sjoin_pkt = packet(0x04, self.last_slotinfo_pkt[4:] + peer.join_slotinfojoin_pkt[-17:])
        else:
            sjoin_pkt = peer.join_slotinfojoin_pkt
        if sjoin_pkt:
            await self.send(peer, sjoin_pkt)
        sent_pids = {peer.pid}
        for opid, pinfo_pkt in list(self.host_playerinfo_pkts.items()):
            if opid != peer.pid and opid not in sent_pids:
                sent_pids.add(opid)
                await self.send(peer, pinfo_pkt)
        for other_name, other_peer in list(self.peers.items()):
            if other_name != peer.name and other_peer.pid > 0 and other_peer.pid not in sent_pids:
                sent_pids.add(other_peer.pid)
                await self.send(peer, send_w3gs_playerinfo(other_peer.pid, other_peer.name))
        if self.last_mapcheck_pkt:
            await self.send(peer, self.last_mapcheck_pkt)
        if self.last_slotinfo_pkt:
            await self.send(peer, self.last_slotinfo_pkt)
        self.event("native_rejoin_handshake_sent", name=peer.name, pid=peer.pid, recorded_ticks=len(peer.recorded_ticks))

        rejoin_ticks_sent = 0
        rejoin_acks_recv = 0
        fast_forwarding = False
        try:
            while True:
                for p in framer.feed(b""):
                    if len(p) < 4 or p[0] != 0xF7:
                        continue
                    ptype = p[1]
                    if ptype == 0x3D and not fast_forwarding:  # MAPSIZE
                        await self.send(peer, send_w3gs_countdown_start())
                        await self.send(peer, send_w3gs_countdown_end())
                    elif ptype == 0x23 and not fast_forwarding:  # GAMELOADED_SELF
                        fast_forwarding = True
                        loaded_pids = list(dict.fromkeys(peer.loaded_other_pids))
                        if not loaded_pids:
                            loaded_pids = [s["pid"] for s in self.slots if s.get("status") == 2 and s.get("computer") == 0 and s.get("pid", 0) > 0 and s.get("pid") != peer.pid]
                        for opid in loaded_pids:
                            await self.send(peer, send_w3gs_gameloaded_others(opid))
                        while rejoin_ticks_sent < len(peer.recorded_ticks) and (rejoin_ticks_sent - rejoin_acks_recv) < 35:
                            await self.send(peer, peer.recorded_ticks[rejoin_ticks_sent])
                            rejoin_ticks_sent += 1
                        if rejoin_ticks_sent >= len(peer.recorded_ticks):
                            peer.loaded = True
                            if not self.disconnected_players:
                                self.phase = "CONTINUING"
                    elif ptype == 0x27:  # OUTGOING_KEEPALIVE
                        rejoin_acks_recv += 1
                        if rejoin_acks_recv > peer.keepalives_sent and peer.tunnel_writer is not None:
                            try:
                                peer.tunnel_writer.write(p)
                                await peer.tunnel_writer.drain()
                                peer.keepalives_sent += 1
                            except Exception:
                                pass
                        if fast_forwarding and not peer.loaded:
                            while rejoin_ticks_sent < len(peer.recorded_ticks) and (rejoin_ticks_sent - rejoin_acks_recv) < 35:
                                await self.send(peer, peer.recorded_ticks[rejoin_ticks_sent])
                                rejoin_ticks_sent += 1
                            if rejoin_ticks_sent >= len(peer.recorded_ticks) and rejoin_acks_recv >= len(peer.recorded_ticks):
                                peer.loaded = True
                                if not self.disconnected_players:
                                    self.phase = "CONTINUING"
                                self.event("native_rejoin_completed", name=peer.name, ticks=rejoin_ticks_sent)
                    elif ptype == 0x21:  # LEAVEGAME
                        peer.deliberate_quit = True
                        if peer.tunnel_writer is not None:
                            try:
                                peer.tunnel_writer.write(p)
                                await peer.tunnel_writer.drain()
                            except Exception:
                                pass
                        return
                    elif peer.loaded and peer.tunnel_writer is not None:
                        if ptype == 0x26 and len(p) >= 8:
                            self.extract_and_strip_hero_nt(peer.name, p[8:])
                        try:
                            peer.tunnel_writer.write(p)
                            await peer.tunnel_writer.drain()
                        except Exception:
                            return
                chunk = await asyncio.wait_for(reader.read(8192), timeout=45.0)
                if not chunk:
                    break
                framer.feed(chunk)
        except Exception:
            pass
        finally:
            if peer.writer is writer:
                peer.writer = None
                peer.loaded = False
                if peer.deliberate_quit or self.winner_team is not None or self.match_started_at <= 0.0:
                    if peer.tunnel_writer is not None:
                        try:
                            peer.tunnel_writer.close()
                        except Exception:
                            pass
                        peer.tunnel_writer = None
                    self.peers.pop(peer.name, None)
                    self.disconnected_players.discard(peer.name)
                else:
                    self.disconnected_players.add(peer.name)
                    self.absent = peer.name
                    self.wait_started_at = time.time()
                    self.phase = "WAITING"
            try:
                writer.close()
            except Exception:
                pass

    async def handle_native_host_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, first_packet: bytes, framer: Framer):
        counter, key, name, internal_ip = join_identity(first_packet)
        if not name or len(name) > 15 or name in self.kicked_players:
            writer.write(send_w3gs_rejectjoin(9))
            await writer.drain()
            writer.close()
            return
        if name in self.disconnected_players and name in self.peers and self.peers[name].tunnel_writer is not None:
            await self._handle_native_rejoin(self.peers[name], reader, writer, framer)
            return
        if self.phase != "LOBBY":
            writer.write(send_w3gs_rejectjoin(9))
            await writer.drain()
            writer.close()
            return
        tun = await self.open_host_tunnel(timeout=5.0)
        if tun is None:
            writer.write(send_w3gs_rejectjoin(9))
            await writer.drain()
            writer.close()
            return
        t_reader, t_writer, t_framer = tun
        patched_join = bytearray(first_packet)
        patched_join[4:12] = struct.pack("<II", self.orig_host_counter & 0xFFFFFFFF, self.orig_entry_key & 0xFFFFFFFF)
        peer = RoomPeer(
            name=name,
            writer=writer,
            pid=0,
            sid=-1,
            internal_ip=internal_ip,
            tunnel_reader=t_reader,
            tunnel_writer=t_writer,
        )
        old_p = self.peers.get(name)
        if old_p is not None and old_p.tunnel_writer is not None:
            try:
                old_p.tunnel_writer.close()
            except Exception:
                pass
        self.peers[name] = peer

        async def _tunnel_to_client():
            try:
                while True:
                    for pkt in t_framer.feed(b""):
                        if len(pkt) < 4 or pkt[0] != 0xF7:
                            continue
                        ptype = pkt[1]
                        if ptype == 0x04 and len(pkt) >= 21:  # SLOTINFOJOIN
                            peer.join_slotinfojoin_pkt = pkt
                            peer.pid = pkt[-17]
                            self._parse_and_update_slot_block(pkt[4:-17])
                        elif ptype == 0x06 and len(pkt) >= 10:  # PLAYERINFO
                            opid = pkt[8]
                            self.host_playerinfo_pkts[opid] = pkt
                        elif ptype == 0x3D:  # MAPCHECK
                            self.last_mapcheck_pkt = pkt
                        elif ptype == 0x09 and len(pkt) > 6:  # SLOTINFO
                            self.last_slotinfo_pkt = pkt
                            self._parse_and_update_slot_block(pkt[4:])
                        elif ptype == 0x0A:  # COUNTDOWN_START
                            self.host_raw_gameinfo = b""
                            if self.phase == "LOBBY":
                                self.phase = "STARTING"
                                joined_pids = {px.pid for px in self.peers.values() if px.pid > 0}
                                t0_cnt = 0
                                t1_cnt = 0
                                for idx, s in enumerate(self.slots):
                                    if s.get("status") == 2 and s.get("computer") == 0:
                                        tm = int(s.get("team", 0))
                                        if tm == 0:
                                            t0_cnt += 1
                                        elif tm == 1:
                                            t1_cnt += 1
                                        spid = int(s.get("pid", 0))
                                        if spid > 0 and spid not in joined_pids and self.owner_name:
                                            self.host_pid = spid
                                            hst = self.ensure_player_stat(self.owner_name)
                                            hst["team"] = tm
                                            hst["colour"] = int(s.get("colour", 1))
                                            self.colour_to_name[hst["colour"]] = self.owner_name
                                for px in self.peers.values():
                                    self.ensure_player_stat(px.name)
                                self.initial_team_counts = {0: t0_cnt, 1: t1_cnt}
                                self.initial_player_count = t0_cnt + t1_cnt
                                self.initial_players = set(self.player_stats.keys())
                        elif ptype == 0x0B:  # COUNTDOWN_END
                            if self.match_started_at <= 0.0:
                                self.match_started_at = time.time()
                        elif ptype == 0x08 and len(pkt) >= 5:  # GAMELOADED_OTHERS
                            opid = pkt[4]
                            if opid not in peer.loaded_other_pids:
                                peer.loaded_other_pids.append(opid)
                            if self.phase == "STARTING":
                                self.phase = "CONTINUING"
                        elif ptype in (0x0C, 0x48):  # INCOMING_ACTION / INCOMING_ACTION2
                            peer.recorded_ticks.append(pkt)
                            if len(pkt) > 8:
                                pos_a = 8
                                while pos_a + 3 <= len(pkt):
                                    apid = pkt[pos_a]
                                    alen = struct.unpack_from("<H", pkt, pos_a + 1)[0]
                                    pos_a += 3
                                    if pos_a + alen > len(pkt):
                                        break
                                    aname = self.owner_name if apid == self.host_pid else next((px.name for px in self.peers.values() if px.pid == apid), "")
                                    if aname:
                                        self.extract_and_strip_hero_nt(aname, pkt[pos_a : pos_a + alen])
                                    pos_a += alen
                        elif ptype == 0x07 and len(pkt) >= 9:  # PLAYERLEAVE_OTHERS
                            lpid = pkt[4]
                            lcode = struct.unpack_from("<I", pkt, 5)[0]
                            if self.phase == "LOBBY":
                                self.host_playerinfo_pkts.pop(lpid, None)
                            elif lcode in (8, 9) and self.winner_team is None:
                                lteam = 0
                                for s in self.slots:
                                    if s.get("pid") == lpid:
                                        lteam = int(s.get("team", 0))
                                        break
                                self.winner_team = lteam if lcode == 9 else (1 - lteam)
                        elif ptype == 0x01 and len(pkt) >= 8:  # PING_FROM_HOST
                            if peer.writer is None:
                                try:
                                    t_writer.write(packet(0x28, pkt[4:8]))
                                    await t_writer.drain()
                                except Exception:
                                    break
                        if peer.writer is not None and (peer.loaded or self.phase in ("LOBBY", "STARTING") or ptype not in (0x0C, 0x48)):
                            try:
                                peer.writer.write(pkt)
                                await peer.writer.drain()
                            except Exception:
                                pass
                    if peer.writer is None and self.wait_started_at > 0 and (time.time() - self.wait_started_at) > self.wait_duration_sec:
                        st = self.ensure_player_stat(peer.name)
                        st["abandoned"] = True
                        break
                    chunk = await asyncio.wait_for(t_reader.read(16384), timeout=30.0)
                    if not chunk:
                        break
                    t_framer.feed(chunk)
            except Exception:
                pass
            finally:
                peer.tunnel_writer = None
                peer.tunnel_reader = None
                try:
                    t_writer.close()
                except Exception:
                    pass
                if peer.writer is not None:
                    try:
                        peer.writer.close()
                    except Exception:
                        pass
                    peer.writer = None
                if self.peers.get(peer.name) is peer:
                    self.peers.pop(peer.name, None)
                self.disconnected_players.discard(peer.name)
                if not self.peers and self.phase != "LOBBY" and not self.remake_in_progress:
                    await self.reset_room_for_remake("🔄 Тоглолт дуусаж өрөө шинэ Create Game хүлээж байна!", score_winner_team=self.winner_team)

        tun_task = self.spawn(_tunnel_to_client())
        try:
            t_writer.write(bytes(patched_join))
            if framer.buffer:
                t_writer.write(bytes(framer.buffer))
                framer.buffer.clear()
            await t_writer.drain()
            while True:
                chunk = await asyncio.wait_for(reader.read(16384), timeout=45.0)
                if not chunk:
                    break
                for p in framer.feed(chunk):
                    if len(p) < 4 or p[0] != 0xF7:
                        continue
                    ptype = p[1]
                    if ptype == 0x3D:
                        peer.map_ready = True
                    elif ptype == 0x23:
                        peer.loaded = True
                        if self.phase == "STARTING":
                            self.phase = "CONTINUING"
                    elif ptype == 0x27:
                        peer.keepalives_sent += 1
                    elif ptype == 0x26 and len(p) >= 8:
                        self.extract_and_strip_hero_nt(peer.name, p[8:])
                    elif ptype == 0x2F and self.disconnected_players and self.get_wait_remaining_sec() > 0:
                        # Block premature Drop Players clicks during the 180s Reconnect Shield window
                        continue
                    elif ptype == 0x21:  # Deliberate F10 -> E -> Q Quit
                        if len(p) >= 8:
                            lreason = struct.unpack_from("<I", p, 4)[0]
                            pteam = int(self.slots[peer.sid].get("team", 0)) if (0 <= peer.sid < len(self.slots)) else 0
                            if lreason == 9 and self.winner_team is None:
                                self.winner_team = pteam
                            elif lreason == 8 and self.winner_team is None:
                                self.winner_team = 1 - pteam
                        peer.deliberate_quit = True
                        try:
                            t_writer.write(p)
                            await t_writer.drain()
                        except Exception:
                            pass
                        break
                    try:
                        t_writer.write(p)
                        await t_writer.drain()
                    except Exception:
                        break
                if peer.deliberate_quit:
                    break
        except Exception:
            pass
        finally:
            if peer.writer is writer:
                peer.writer = None
                peer.loaded = False
            if self.phase == "LOBBY" or peer.deliberate_quit or self.winner_team is not None or self.match_started_at <= 0.0:
                if self.match_started_at > 0.0 and peer.deliberate_quit and self.winner_team is None:
                    st = self.ensure_player_stat(peer.name)
                    st["quit_at"] = time.time()
                    self.spawn(self._confirm_quit_leaver(peer.name, self.host_counter))
                try:
                    t_writer.close()
                except Exception:
                    pass
                tun_task.cancel()
                if self.peers.get(peer.name) is peer:
                    self.peers.pop(peer.name, None)
                self.disconnected_players.discard(peer.name)
                if not self.peers and self.phase != "LOBBY" and not self.remake_in_progress:
                    await self.reset_room_for_remake("🔄 Бүх тоглогчид гарсан тул өрөө шинээр бэлэн боллоо!", score_winner_team=self.winner_team)
            else:
                # Crash / Fatal Error / Internet drop -> keep HOST_TUNNEL (t_writer / tun_task) alive for 180s Rejoin!
                self.disconnected_players.add(peer.name)
                self.absent = peer.name
                self.wait_started_at = time.time()
                self.wait_duration_sec = 180.0
                self.phase = "WAITING"
                self.event("native_client_disconnected_waiting_rejoin", name=peer.name, wait_sec=180)
            try:
                writer.close()
            except Exception:
                pass

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, first_packet: bytes, framer: Framer):
        self.ensure_background_tasks()
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                if hasattr(socket, "TCP_QUICKACK"):
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
            except OSError:
                pass
        if self.host_ctrl_writer is not None or self.last_host_gameinfo_snapshot:
            await self.handle_native_host_client(reader, writer, first_packet, framer)
            return
        peer: RoomPeer | None = None
        replacement = False
        deliberate_quit = False
        try:
            counter, key, name, internal_ip = join_identity(first_packet)
            if not name or len(name) > 15 or name in self.kicked_players or name in getattr(self, "kicked_cheaters", set()):
                writer.write(send_w3gs_rejectjoin(9))
                await writer.drain()
                writer.close()
                return
            replacement = self.phase in ("WAITING", "LOADING") and name == self.absent
            if replacement and self.checkpoint_info is None:
                # Solo test / no survivor checkpoint: allow clean rejoin to lobby
                self.phase = "LOBBY"
                self.absent = None
                self.wait_started_at = 0.0
                self.host_drop_unlocked_sent = False
                self.disconnected_players.discard(name)
                replacement = False
            if replacement:
                old_peer = self.peers[name]
                peer = RoomPeer(
                    name=name,
                    writer=writer,
                    pid=old_peer.pid,
                    sid=old_peer.sid,
                    internal_ip=internal_ip,
                    frames=0,
                    checks=0,
                    loaded=False,
                    map_ready=False,
                )
                self.peers[name] = peer
                self.disconnected_players.discard(name)
                self.phase = "LOADING"
                st = self.ensure_player_stat(name)
                st["reconnected"] = st.get("reconnected", 0) + 1
                save_slots = [dict(s) for s in self.checkpoint_info["slots"]]
                save_seed = self.checkpoint_info["random_seed"]
                await self.send(peer, send_w3gs_slotinfojoin(peer.pid, 6112, b"\x00\x00\x00\x00", save_slots, save_seed))
                await self.send(peer, send_w3gs_playerinfo(self.vhost_pid, VIRTUAL_HOST_NAME))
                for other_name, other_peer in self.peers.items():
                    if other_name != name:
                        await self.send(peer, send_w3gs_playerinfo(other_peer.pid, other_peer.name))
                await self.send(peer, send_w3gs_mapcheck(self.map_path, self.map_size, self.map_info, self.map_crc, self.map_sha1))
                await self.send(peer, send_w3gs_slotinfo(save_slots, save_seed))
                self.event("replacement_join", name=name, pid=peer.pid)
            else:
                if self.phase != "LOBBY":
                    writer.write(send_w3gs_rejectjoin(9))
                    await writer.drain()
                    writer.close()
                    return
                if name in self.peers:
                    old_p = self.peers.pop(name, None)
                    if old_p:
                        if 0 <= old_p.sid < len(self.slots):
                            self.slots[old_p.sid]["pid"] = 0
                            self.slots[old_p.sid]["download"] = 255
                            self.slots[old_p.sid]["status"] = 0
                        if old_p.writer is not None:
                            try:
                                old_p.writer.close()
                            except Exception:
                                pass
                            old_p.writer = None
                        await self.broadcast(send_w3gs_playerleave_others(old_p.pid, 7))
                is_host_join = bool(self.owner_name and name.lower() == self.owner_name.lower())
                if is_host_join and len(self.slots) > 0 and self.slots[0]["status"] != 0:
                    # Ensure Slot 1 (sid = 0) is always vacated for the Host
                    if not self._is_human_slot(0):
                        self._set_slot_open(0)
                    else:
                        free_sid = self._allocate_sid(player_name="__non_host__")
                        if free_sid > 0:
                            await self.swap_slots(0, free_sid)
                sid = self._allocate_sid(player_name=name)
                if sid < 0:
                    writer.write(send_w3gs_rejectjoin(9))
                    await writer.drain()
                    writer.close()
                    return
                pid = self._allocate_pid()
                peer = RoomPeer(name=name, writer=writer, pid=pid, sid=sid, internal_ip=internal_ip)
                self.peers[name] = peer
                self.disconnected_players.discard(name)
                self.slots[sid]["pid"] = pid
                self.slots[sid]["download"] = 255
                self.slots[sid]["status"] = 2
                self.slots[sid]["computer"] = 0
                self.slots[sid]["locked"] = False
                await self.send(peer, send_w3gs_slotinfojoin(pid, 6112, b"\x00\x00\x00\x00", self.slots, self.random_seed))
                await self.send(peer, send_w3gs_playerinfo(self.vhost_pid, VIRTUAL_HOST_NAME))
                for other_name, other_peer in list(self.peers.items()):
                    if other_name != name:
                        await self.send(other_peer, send_w3gs_playerinfo(pid, name))
                        await self.send(peer, send_w3gs_playerinfo(other_peer.pid, other_peer.name))
                await self.send(peer, send_w3gs_mapcheck(self.map_path, self.map_size, self.map_info, self.map_crc, self.map_sha1))
                await self.send_all_slot_info()
                self.event("initial_join", name=name, pid=pid, sid=sid, team=self.slots[sid]["team"])

            while True:
                packets = framer.feed(b"")
                if not packets:
                    chunk = await reader.read(65535)
                    if not chunk:
                        break
                    packets = framer.feed(chunk)
                for p in packets:
                    ptype = p[1]
                    if ptype == 0x46:  # PONG_TO_HOST
                        continue
                    elif ptype == 0x42 and len(p) >= 13:  # MAPSIZE
                        size_flag = p[8]
                        map_bytes = struct.unpack_from("<I", p, 9)[0]
                        if size_flag == 1 and map_bytes >= self.map_size_int:
                            peer.map_ready = True
                            if not replacement and 0 <= peer.sid < len(self.slots):
                                self.slots[peer.sid]["download"] = 100
                                await self.send_all_slot_info()
                            self.event("client_map_ready", name=peer.name, replacement=replacement)
                            if replacement:
                                await self.send(peer, send_w3gs_countdown_start())
                                await self.send(peer, send_w3gs_playerleave_others(self.vhost_pid, 7))
                                await self.send(peer, send_w3gs_countdown_end())
                                for other_name, other_peer in self.peers.items():
                                    if other_name != peer.name:
                                        await self.send(peer, send_w3gs_gameloaded_others(other_peer.pid))
                    elif ptype == 0x28:  # CHAT_TO_HOST
                        await self._handle_chat_packet(peer, p)
                    elif ptype == 0x29:  # DROPREQ (In-game "Drop Players" button clicked)
                        if self.absent and self.phase in ("FROZEN", "WAITING"):
                            absent_peer = self.peers.get(self.absent)
                            if peer.name != self.owner_name:
                                # Block non-host players from dropping the waiting player
                                if absent_peer and peer.writer is not None:
                                    await self.send(peer, lag(absent_peer.pid, False))
                                    await self.send(peer, lag(absent_peer.pid, True, self._lag_ms_for(peer.name, self.get_wait_remaining_sec())))
                            else:
                                rem = self.get_wait_remaining_sec()
                                if rem > 0:
                                    if absent_peer and peer.writer is not None:
                                        await self.send(peer, lag(absent_peer.pid, False))
                                        await self.send(peer, lag(absent_peer.pid, True, self._lag_ms_for(peer.name, rem)))
                                else:
                                    await self.drop_absent_player_by_host(peer.name)
                    elif ptype == 0x23:  # GAMELOADED_SELF
                        peer.loaded = True
                        self.event("client_loaded", name=peer.name, replacement=replacement)
                        if replacement:
                            await self.send(peer, send_w3gs_gameloaded_others(peer.pid))
                            self.spawn(self.verify())
                        else:
                            await self.broadcast(send_w3gs_gameloaded_others(peer.pid))
                            if self.phase == "STARTING" and all(px.loaded for px in self.peers.values()):
                                self.phase = "CONTINUING"
                                if self.match_started_at == 0.0:
                                    self.match_started_at = time.time()
                                    self.initial_player_count = len(self.peers)
                                    self.initial_players = set(self.peers.keys())
                                    self.first_empty_team = None
                                    t0 = sum(1 for px in self.peers.values() if 0 <= px.sid < len(self.slots) and int(self.slots[px.sid].get("team", 0)) == 0)
                                    t1 = sum(1 for px in self.peers.values() if 0 <= px.sid < len(self.slots) and int(self.slots[px.sid].get("team", 0)) == 1)
                                    self.initial_team_counts = {0: t0, 1: t1}
                                for pname in self.peers:
                                    self.ensure_player_stat(pname)
                                self.gate = None
                                self.last_tick_time = 0.0
                                self.event("all_players_loaded", players=list(self.peers.keys()))
                                self.schedule_next_tick()
                    elif ptype == 0x27:  # OUTGOING_KEEPALIVE
                        if len(p) >= 9:
                            peer.checks += 1
                            self.dbg("ack", p=peer.name, n=peer.checks, fr=peer.frames, chk=p[5:9].hex())
                            if self.phase == "VERIFYING" and self.gate is not None:
                                chk = p[5:9]
                                result = self.gate.accept(peer.name, chk)
                                if result is not None:
                                    if result is False:
                                        self.event(
                                            "state_check_diff_continuing",
                                            values={k: v.hex() for k, v in self.gate.values.items()},
                                        )
                                    self.phase = "CONTINUING"
                                    self.gate = None
                                    self.last_tick_time = 0.0
                                    self.schedule_next_tick()
                            elif self.phase == "CONTINUING":
                                self.schedule_next_tick()
                    elif ptype == 0x26:  # OUTGOING_ACTION
                        if len(p) >= 8 and zlib.crc32(p[8:]) == struct.unpack_from("<I", p, 4)[0]:
                            raw_act = p[8:]
                            self.dbg("act", p=peer.name, hex=raw_act.hex()[:300])
                            cleaned = self.extract_and_strip_hero_nt(peer.name, raw_act)
                            if self.phase == "FROZEN":
                                if b"\x07\x01\0\0\0" in raw_act:
                                    peer.pending.append(b"\x07\x01\0\0\0")
                            elif self.phase == "CONTINUING":
                                if cleaned and sum(map(len, peer.pending)) + len(cleaned) <= 65535:
                                    peer.pending.append(cleaned)
                    elif ptype == 0x21:  # LEAVEGAME (deliberate F10 -> Quit or Victory/Defeat exit)
                        if len(p) >= 8:
                            leave_reason = struct.unpack_from("<I", p, 4)[0]
                            peer_team = (
                                int(self.slots[peer.sid].get("team", 0))
                                if (0 <= peer.sid < len(self.slots))
                                else int(self.ensure_player_stat(peer.name).get("team", 0))
                            )
                            if leave_reason == 9 and self.winner_team is None:  # PLAYERLEAVE_WON
                                self.winner_team = peer_team
                            elif leave_reason == 8 and self.winner_team is None:  # PLAYERLEAVE_LOSTBUILDINGS
                                self.winner_team = 1 - peer_team
                        deliberate_quit = True
                        break
                if deliberate_quit:
                    break
        except (ConnectionError, OSError, ValueError) as exc:
            self.event("client_error", name=peer.name if peer else None, detail=str(exc))
        finally:
            if peer and self.peers.get(peer.name) is peer and not self.remake_in_progress:
                peer.writer = None
                peer.loaded = False
                is_cheater = peer.name in getattr(self, "kicked_cheaters", set()) or peer.name in self.kicked_players
                if is_cheater:
                    if 0 <= peer.sid < len(self.slots):
                        self.slots[peer.sid]["pid"] = 0
                        self.slots[peer.sid]["download"] = 255
                        self.slots[peer.sid]["status"] = 0
                    self.peers.pop(peer.name, None)
                    self.disconnected_players.discard(peer.name)
                    await self.broadcast(send_w3gs_playerleave_others(peer.pid, 7))
                elif self.phase == "LOBBY":
                    if 0 <= peer.sid < len(self.slots):
                        self.slots[peer.sid]["pid"] = 0
                        self.slots[peer.sid]["download"] = 255
                        self.slots[peer.sid]["status"] = 0
                    self.peers.pop(peer.name, None)
                    # Never mark a player as disconnected_players during LOBBY (match has NOT started!)
                    self.disconnected_players.discard(peer.name)
                    await self.broadcast(send_w3gs_playerleave_others(peer.pid, 7))
                    await self.send_all_slot_info()
                    self.event("client_left_lobby", name=peer.name)
                elif deliberate_quit or self.winner_team is not None or self.match_started_at <= 0.0:
                    # Deliberate Quit Mission (0x21 LEAVEGAME), or match already has a winner, or match never finished loading:
                    # NEVER activate Rejoin (FROZEN/WAITING)! Rejoin is strictly for unexpected crash/Fatal Error/PC off/internet drop.
                    if self.match_started_at > 0.0:
                        st = self.ensure_player_stat(peer.name)
                        st["quit_at"] = time.time()
                    self.peers.pop(peer.name, None)
                    self.disconnected_players.discard(peer.name)
                    if self.absent == peer.name:
                        self.absent = next(iter(self.disconnected_players), None)
                    t0_alive = sum(
                        1 for px in self.peers.values()
                        if px.writer is not None and 0 <= px.sid < len(self.slots) and int(self.slots[px.sid].get("team", 0)) == 0
                    )
                    t1_alive = sum(
                        1 for px in self.peers.values()
                        if px.writer is not None and 0 <= px.sid < len(self.slots) and int(self.slots[px.sid].get("team", 0)) == 1
                    )
                    if self.first_empty_team is None and (t0_alive == 0 or t1_alive == 0) and (t0_alive + t1_alive) > 0:
                        self.first_empty_team = 0 if t0_alive == 0 else 1
                    survivor = next((p for n, p in self.peers.items() if p.writer is not None), None)
                    if survivor is None:
                        if self.match_started_at <= 0.0:
                            reason = "⚠️ Тоглолт эхлэхээс өмнө цуцлагдсан тул өрөө LAN дээр дахин бэлэн боллоо!"
                        elif self.winner_team is not None:
                            reason = "🏆 Тоглолт дуусаж өрөө LAN дээр дахин бэлэн боллоо!"
                        else:
                            reason = "🔄 Бүх тоглогчид тоглолтоос гарсан (Quit) тул өрөө LAN дээр шинээр бэлэн боллоо!"
                        await self.reset_room_for_remake(reason, score_winner_team=self.winner_team)
                    else:
                        await self.broadcast(send_w3gs_playerleave_others(peer.pid, 7))
                        if (
                            deliberate_quit
                            and self.winner_team is None
                            and self.match_started_at > 0.0
                            and t0_alive > 0
                            and t1_alive > 0
                        ):
                            self.spawn(self._confirm_quit_leaver(peer.name, self.host_counter))
                        elif t0_alive == 0 or t1_alive == 0:
                            now_q = time.time()
                            for pst in self.player_stats.values():
                                if pst.get("abandoned") and (now_q - float(pst.get("quit_at", 0.0))) < 300.0:
                                    pst["abandoned"] = False
                        if self.phase in ("FROZEN", "WAITING") and not self.disconnected_players:
                            self.phase = "CONTINUING"
                            self.absent = None
                        self.schedule_next_tick()
                elif self.phase in ("STARTING", "VERIFYING", "CONTINUING", "FROZEN", "WAITING"):
                    survivor = next((p for n, p in self.peers.items() if n != peer.name and p.writer is not None), None)
                    if survivor is not None:
                        self.absent = peer.name
                        self.disconnected_players.add(peer.name)
                        self.wait_started_at = time.time()
                        self.wait_duration_sec = 180.0
                        self.addtime_count = 0
                        self.host_drop_unlocked_sent = False
                        self.warned_20s_addtime = False
                        self.last_wait_announce = time.monotonic()
                        self.phase = "FROZEN"
                        self.start_debug_capture("drop")
                        self.reset_nettag_maps()
                        self.checkpoint_event.clear()
                        self.checkpoint_bytes = None
                        self.checkpoint_info = None
                        self.save_name = f"bridge_{int(time.time())}"
                        self.save_action = b"\x06" + self.save_name.encode("ascii") + b".w3z\0"
                        self.boundary_tail.clear()
                        # Allow any lookahead turn already in flight on real clients to be acknowledged before save_action
                        for _ in range(20):
                            if not any(sp.checks > 0 and sp.checks < sp.frames for sp in self.peers.values() if sp.writer is not None):
                                break
                            await asyncio.sleep(0.01)
                        for s_peer in self.peers.values():
                            if s_peer.writer is not None:
                                s_peer.frames = max(s_peer.frames, s_peer.checks) + 1
                                await self.send(s_peer, incoming([(peer.pid, self.save_action)], 100))
                        self.event("checkpoint_requested", name=self.save_name, absent=self.absent, survivor=survivor.name, wait_sec=180)
                        if self.on_chat_announce_cb is not None:
                            try:
                                self.on_chat_announce_cb(
                                    self.room_id,
                                    f"⏳ «{peer.name}» тоглолтоос салсан тул 180 секунд (3 минут) хүлээх горим идэвхжлээ!",
                                )
                            except Exception:
                                pass
                        self.spawn(self.prepare_loader(survivor))
                    else:
                        # No survivor remains in the match -> never leave room in WAITING/Rejoin state, immediately reset to LOBBY!
                        reason = (
                            "🏆 Тоглолт дуусаж өрөө LAN дээр дахин бэлэн боллоо!"
                            if self.winner_team is not None
                            else "🔄 Бүх тоглогчид тоглолтоос гарсан тул өрөө LAN дээр шинээр бэлэн боллоо!"
                        )
                        await self.reset_room_for_remake(reason, score_winner_team=self.winner_team)
                elif replacement and self.phase in ("WAITING", "LOADING"):
                    self.phase = "WAITING"
                    self.event("replacement_retry_ready", name=peer.name)
            try:
                writer.close()
            except Exception:
                pass

    def _is_effective_host(self, actor_name: str) -> bool:
        if not actor_name:
            return False
        if self.owner_name and actor_name.lower() == self.owner_name.lower():
            return True
        # If the nominal room owner has not joined W3GS Lobby, allow Slot 1 (sid=0) or the first connected W3GS peer
        owner_in_w3gs = bool(
            self.owner_name
            and any(p.name.lower() == self.owner_name.lower() and p.writer is not None for p in self.peers.values())
        )
        if not owner_in_w3gs and self.peers:
            peer = self.peers.get(actor_name)
            if peer is not None and peer.sid == 0:
                return True
            active_peers = [p for p in self.peers.values() if p.writer is not None]
            if active_peers and active_peers[0].name.lower() == actor_name.lower():
                return True
        return False

    async def execute_lobby_slot_command(self, actor_name: str, msg: str) -> tuple[bool, str] | None:
        return None

    async def _execute_chat_command(self, peer: RoomPeer, msg: str) -> bool:
        if self.phase != "LOBBY" or not msg.startswith(("-", "!", "/")):
            return False
        parts = msg[1:].split()
        cmd = parts[0].lower() if parts else ""
        if cmd != "swap":
            return False
        now_m = time.monotonic()
        dedup_key = (peer.name.lower(), msg.strip().lower()[:32])
        if now_m - self._cmd_dedup.get(dedup_key, 0.0) < 0.8:
            return True
        self._cmd_dedup[dedup_key] = now_m
        if not self._is_effective_host(peer.name):
            return True
        if len(parts) >= 3:
            try:
                s1, s2 = int(parts[1]) - 1, int(parts[2]) - 1
                await self.swap_slots(s1, s2)
            except ValueError:
                pass
        return True

    async def _handle_chat_packet(self, peer: RoomPeer, p: bytes):
        if len(p) < 6:
            return
        count = p[4]
        idx = 5 + count
        if idx + 2 > len(p):
            return
        client_to_pids = set(p[5 : 5 + count])
        from_pid = p[idx]
        flag = p[idx + 1]
        idx += 2
        if flag == 0x11 and idx < len(p):  # CTH_TEAMCHANGE
            if self.phase == "LOBBY":
                team = p[idx]
                new_sid = self._allocate_sid(preferred_team=team, player_name=peer.name, allow_replace_comp=True)
                if new_sid >= 0:
                    await self.swap_slots(peer.sid, new_sid)
            return
        if flag == 0x14 and idx < len(p):  # CTH_HANDICAPCHANGE (Host's clickable 100%/90%/80%/70%/60%/50% dropdown in Lobby)
            if self.phase == "LOBBY" and self._is_effective_host(peer.name):
                h_val = p[idx]
                if 0 <= peer.sid < len(self.slots):
                    self.slots[peer.sid]["handicap"] = 100
                if h_val == 90:
                    await self.apply_team_size_preset(1, difficulty=1)
                elif h_val == 80:
                    await self.apply_team_size_preset(2, difficulty=1)
                elif h_val == 70:
                    await self.apply_team_size_preset(3, difficulty=1)
                elif h_val == 60:
                    await self.apply_team_size_preset(4, difficulty=1)
                elif h_val == 50:
                    for sid in range(len(self.slots)):
                        self._set_slot_computer(sid, difficulty=2, locked=True)
                    await self.send_all_slot_info()
                elif h_val == 100:
                    for sid in range(len(self.slots)):
                        self._set_slot_open(sid)
                    await self.send_all_slot_info()
            return
        if flag not in (0x10, 0x20):
            return
        extra = b""
        if flag == 0x20:
            if idx + 4 > len(p):
                return
            extra = p[idx:idx + 4]
            idx += 4
        end = p.find(0, idx)
        if end == -1:
            return
        msg = p[idx:end].decode("utf-8", errors="replace").strip()
        low_msg = msg.lower()
        if any(c in low_msg for c in ("iseedeadpeople", "whosyourdaddy", "greedisgood", "thereisnospoon", "keysersoze", "warpten")):
            self.event("cheat_chat_blocked", player=peer.name, msg=msg)
            await self.send_all_chat(f"|cFFFF3333[Anti-MapHack]|r {peer.name} хориотой cheat код бичих гэж оролдлоо!")
            return
        if self.phase == "LOBBY" and msg.startswith(("!", "-", "/")):
            if await self._execute_chat_command(peer, msg):
                return
        if self.phase == "LOBBY" or flag == 0x10:
            to_pids = [px.pid for px in self.peers.values() if px.writer is not None and px.pid != from_pid]
        else:
            if extra == b"\x01\x00\x00\x00":  # CHAT_RECIPIENT_ALLIES ([Allies]) -> strictly same-team allies only!
                my_team = int(self.slots[peer.sid].get("team", 0)) if (0 <= peer.sid < len(self.slots)) else 0
                to_pids = [
                    px.pid for px in self.peers.values()
                    if px.writer is not None
                    and px.pid != from_pid
                    and 0 <= px.sid < len(self.slots)
                    and int(self.slots[px.sid].get("team", 0)) == my_team
                ]
            elif extra == b"\x00\x00\x00\x00":  # CHAT_RECIPIENT_ALL ([All])
                to_pids = [px.pid for px in self.peers.values() if px.writer is not None and px.pid != from_pid]
            else:  # CHAT_RECIPIENT_OBSERVERS / REFEREES / PRIVATE -> strictly client-specified recipient PIDs
                to_pids = [
                    px.pid for px in self.peers.values()
                    if px.writer is not None and px.pid != from_pid and px.pid in client_to_pids
                ]
        if to_pids:
            pkt = send_w3gs_chat_from_host(from_pid, to_pids, flag, extra, msg)
            for px in self.peers.values():
                if px.pid in to_pids:
                    await self.send(px, pkt)

    async def prepare_loader(self, survivor: RoomPeer):
        ack = b"\x07\x01\0\0\0"
        wait_end = time.monotonic() + 15.0
        while time.monotonic() < wait_end:
            active_survivors = [
                p for n, p in self.peers.items()
                if n != self.absent and p.writer is not None and p.loaded
            ]
            if active_survivors and all(
                any(ack in cmd for cmd in p.pending) for p in active_survivors
            ):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.05)

        absent_peer = self.peers.get(self.absent)
        if not absent_peer:
            return
        # Drain the save-completion acks from all surviving peers while preserving any gameplay commands
        # queued in pending so they are delivered to everyone together once play resumes.
        for s_peer in self.peers.values():
            if s_peer.writer is None:
                continue
            kept = deque()
            while s_peer.pending:
                cmd = s_peer.pending.popleft()
                if ack in cmd:
                    rest = cmd.replace(ack, b"", 1)
                    if rest:
                        kept.append(rest)
                else:
                    kept.append(cmd)
            s_peer.pending = kept
        # Include a save-completion ack for every peer PID in the match so all surviving clients'
        # "Saving game..." modal closes deterministically in 2-player through 10-player matches.
        groups = [(p.pid, ack) for p in sorted(self.peers.values(), key=lambda x: x.pid)]
        tail = incoming(groups, 100)
        self.boundary_tail.append(tail)
        self.lag_active_since = time.monotonic()
        for s_peer in self.peers.values():
            if s_peer.writer is not None:
                s_peer.frames = max(s_peer.frames, s_peer.checks) + 1
                await self.send(s_peer, tail)
                await self.send(s_peer, lag(absent_peer.pid, True, 0))
        await self.send_all_chat(
            f"|cFFFFCC00[MongolRanger]|r «{self.absent}» гэнэт салсан тул 180 сек (3 мин) хүлээж байна."
        )
        self.event("survivor_waiting_dialog_shown", survivor=survivor.name, absent=self.absent, wait_sec=180)

        try:
            await asyncio.wait_for(self.checkpoint_event.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            self.phase = "WAITING"
            self.event("checkpoint_upload_timeout", absent=self.absent)
            return

        self.rejoin_counter = ((self.rejoin_counter + 1) & 0x0FFFFFFF) or 2
        self.phase = "WAITING"
        self.event("checkpoint_ready", file=self.checkpoint_info["filename"], rejoin_counter=self.rejoin_counter)

    async def verify(self):
        self.lag_active_since = 0.0
        await asyncio.sleep(0.2)
        if self.phase != "LOADING" or not self.absent:
            return
        replacement = self.peers[self.absent]
        end = time.monotonic() + 10.0

        # 1. Initial 25 ms post-load step for the replacement client
        self.event("replacement_post_load_frame_sent", milliseconds=25)
        target_checks = replacement.checks + 1
        replacement.frames += 1
        await self.send(replacement, incoming(milliseconds=25))
        while replacement.checks < target_checks:
            if time.monotonic() > end:
                raise TimeoutError("Post-load simulation acknowledgment missing")
            await asyncio.sleep(0.02)

        # 2. Boundary step (100 ms empty turn) to align replacement with survivor
        self.event("replacement_boundary_sent", milliseconds=100)
        target_checks = replacement.checks + 1
        replacement.frames += 1
        await self.send(replacement, incoming(milliseconds=100))
        while replacement.checks < target_checks or any(
            p.checks < p.frames for p in self.peers.values() if p is not replacement and p.writer is not None
        ):
            if time.monotonic() > end:
                raise TimeoutError("Boundary simulation acknowledgment missing")
            await asyncio.sleep(0.02)

        # 3. Stop lag dialog on all surviving players and resume lockstep ticks
        rejoined_name = self.absent
        self.phase = "VERIFYING"
        self.absent = None
        self.wait_started_at = 0.0
        self.host_drop_unlocked_sent = False
        self.disconnected_players.discard(rejoined_name)
        self.gate = CheckpointGate([n for n, p in self.peers.items() if p.writer is not None and p.loaded])
        for name, peer in self.peers.items():
            if name != rejoined_name and peer.writer is not None:
                await self.send(peer, lag(replacement.pid, False))
        await self.send_all_chat(f"|cFF00FF88[MongolRanger]|r «{rejoined_name}» тоглолтонд буцаж орлоо (Rejoin)! Тоглолт үргэлжилж байна.")
        if self.on_chat_announce_cb is not None:
            try:
                self.on_chat_announce_cb(self.room_id, f"✅ «{rejoined_name}» тоглолтонд амжилттай буцаж орж ирлээ (Rejoin)!")
            except Exception:
                pass
        self.event("first_post_checkpoint_comparison_started", milliseconds=100, rejoined=rejoined_name)
        self.debug_until = time.time() + 180.0
        self.last_tick_time = time.monotonic()
        for peer in self.peers.values():
            peer.pending.clear()
            if peer.writer is not None:
                peer.frames = peer.checks + 1
                await self.send(peer, incoming(milliseconds=100))

    def schedule_next_tick(self):
        if self._tick_task is None or self._tick_task.done():
            self._tick_task = self.spawn(self.next_tick())

    # GHost++-style lockstep: turns are sent on a fixed 100 ms wall-clock schedule, NOT gated on each client's
    # keepalive. Clients buffer several turns, so network jitter never starves war3.exe (no periodic stutter).
    # Only if a client falls more than SYNC_LIMIT turns behind do we stop sending until it catches up.
    TURN_MS = 100
    SYNC_LIMIT = 25  # 2500 ms max unacknowledged cushion (prevents TCP tail-loss 1.0s-2.0s RTO freezes & turn starvation)

    async def next_tick(self):
        next_deadline = time.monotonic()
        while self.phase == "CONTINUING":
            alive = [px for px in self.peers.values() if px.writer is not None and px.loaded]
            if not alive:
                return
            now = time.monotonic()
            if next_deadline - now > 0.001:
                await asyncio.sleep(next_deadline - now)
                continue
            if self.phase != "CONTINUING":
                return
            if max(px.frames - px.checks for px in alive) >= self.SYNC_LIMIT:
                # A client is far behind: hold turns briefly instead of piling up more.
                await asyncio.sleep(0.02)
                next_deadline = time.monotonic()
                continue
            raw_groups = []
            for peer in self.peers.values():
                while peer.pending:
                    raw_groups.append((peer.name, peer.pid, peer.pending.popleft()))
            self.last_tick_time = time.monotonic()
            for target_name, target_peer in list(self.peers.items()):
                if target_peer.writer is None:
                    continue
                translated_groups = []
                for sender_name, sender_pid, body in raw_groups:
                    if sender_name != target_name:
                        body = self.translate_nettags(sender_name, target_name, body)
                    if body:
                        translated_groups.append((sender_pid, body))
                target_peer.frames += 1
                await self.send(target_peer, incoming(translated_groups, self.TURN_MS))
            now_after = time.monotonic()
            next_deadline += self.TURN_MS / 1000.0
            # Never burst multiple turns in <1 ms if the event loop experienced jitter; pace catch-up smoothly (>=55 ms).
            if now_after - next_deadline > 0.5:
                next_deadline = now_after + 0.055
            elif next_deadline < now_after + 0.055:
                next_deadline = now_after + 0.055


class W3GSRoomManager:
    def __init__(self):
        self.rooms: dict[str, W3GSRoom] = {}
        self._counter_seq = 1
        self._server: asyncio.AbstractServer | None = None
        self.listen_port: int = 0

    def create_room(self, room_id: str, name: str, owner_name: str, hcl: str = "", map_meta: dict | None = None) -> W3GSRoom:
        self._counter_seq = (self._counter_seq + 1) & 0x000FFFFF or 1
        entry_key = random.randint(1, 0x7FFFFFFF)
        room = W3GSRoom(room_id, name, owner_name, self._counter_seq, entry_key, hcl=hcl, map_meta=map_meta)
        self.rooms[room_id] = room
        return room

    def get_room(self, room_id: str) -> W3GSRoom | None:
        return self.rooms.get(room_id)

    def remove_room(self, room_id: str):
        room = self.rooms.pop(room_id, None)
        if room is not None:
            room.close()

    def find_room_by_counter(self, counter: int, key: int) -> W3GSRoom | None:
        masked = counter & 0x0FFFFFFF
        for room in self.rooms.values():
            if room.entry_key == key and masked in (room.host_counter, room.rejoin_counter):
                return room
        # Fallback if single active room or matched counter
        for room in self.rooms.values():
            if masked in (room.host_counter, room.rejoin_counter):
                return room
        return None

    async def start_tcp_server(self, host: str = "0.0.0.0", port: int = 8051):
        self._server = await asyncio.start_server(self._accept, host, port)
        sockets = self._server.sockets
        if sockets:
            self.listen_port = sockets[0].getsockname()[1]
        return self.listen_port

    async def stop_tcp_server(self):
        for r in list(self.rooms.values()):
            r.close()
        self.rooms.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        framer = Framer()
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=10.0)
            if not chunk:
                writer.close()
                return
            packets = framer.feed(chunk)
            if not packets:
                writer.close()
                return
            first = packets[0]
            # Re-inject any remaining packets after the first into framer buffer
            if len(packets) > 1:
                rem = b"".join(packets[1:]) + bytes(framer.buffer)
                framer.buffer = bytearray(rem)
            if len(first) >= 4 and first[0] == 0xF7 and first[1] == 0x5A:
                info_str = first[4:].decode("utf-8", errors="replace")
                parts = info_str.split(":")
                if len(parts) >= 2 and parts[0] == "HOST_CTRL":
                    room = self.get_room(parts[1])
                    if room is not None:
                        await room.handle_host_ctrl(reader, writer, framer)
                try:
                    writer.close()
                except Exception:
                    pass
                return
            if len(first) >= 4 and first[0] == 0xF7 and first[1] == 0x5C:
                info_str = first[4:].decode("utf-8", errors="replace")
                parts = info_str.split(":", 1)
                if len(parts) == 2:
                    room = self.get_room(parts[0])
                    if room is not None and room.resolve_host_tunnel(parts[1], reader, writer, framer):
                        return
                try:
                    writer.close()
                except Exception:
                    pass
                return
            counter, key, _, _ = join_identity(first)
            room = self.find_room_by_counter(counter, key)
            if room is None:
                writer.write(send_w3gs_rejectjoin(9))
                await writer.drain()
                writer.close()
                return
            await room.handle_client(reader, writer, first, framer)
        except Exception:
            try:
                writer.close()
            except Exception:
                pass
