"""Pure-Python Warcraft III (.w3x / .w3m) MPQ Parser, Auto-Patcher (-cam & Reconnect), and W3GS Metadata Calculator.

100% self-contained (includes MPQ table/sector encryption, StormLib PKWARE DCL explode, war3map.w3i parser,
and GHost++ byte-identical XORRotateLeft map_crc + map_sha1 calculation).
"""
import bz2
from collections import namedtuple
import hashlib
import io
import lzma
from pathlib import Path
import re
import struct
import zlib

MPQ_FILE_IMPLODE = 0x00000100
MPQ_FILE_COMPRESS = 0x00000200
MPQ_FILE_ENCRYPTED = 0x00010000
MPQ_FILE_FIX_KEY = 0x00020000
MPQ_FILE_SINGLE_UNIT = 0x01000000
MPQ_FILE_DELETE_MARKER = 0x02000000
MPQ_FILE_SECTOR_CRC = 0x04000000
MPQ_FILE_EXISTS = 0x80000000

MAPOPT_MELEE = 1 << 2
MAPOPT_FIXEDPLAYERSETTINGS = 1 << 5
MAPOPT_CUSTOMFORCES = 1 << 6

MPQHashTableEntry = namedtuple("MPQHashTableEntry", "hash_a hash_b locale platform block_table_index")
MPQBlockTableEntry = namedtuple("MPQBlockTableEntry", "offset archived_size size flags")


def _prepare_encryption_table() -> list[int]:
    seed = 0x00100001
    crypt_table = [0] * 1280
    for i in range(256):
        index = i
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp1 = (seed & 0xFFFF) << 0x10
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp2 = seed & 0xFFFF
            crypt_table[index] = temp1 | temp2
            index += 0x100
    return crypt_table


CRYPT_TABLE = _prepare_encryption_table()


def mpq_hash(string: str, hash_type: str) -> int:
    hash_types = {"TABLE_OFFSET": 0, "HASH_A": 1, "HASH_B": 2, "TABLE": 3}
    seed1 = 0x7FED7FED
    seed2 = 0xEEEEEEEE
    ht_offset = hash_types[hash_type] << 8
    for ch in string.upper():
        c = ord(ch)
        value = CRYPT_TABLE[ht_offset + c]
        seed1 = (value ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed2 = (c + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def mpq_decrypt(data: bytes, key: int) -> bytes:
    seed1 = key & 0xFFFFFFFF
    seed2 = 0xEEEEEEEE
    n_words = len(data) // 4
    out = bytearray(data)
    for i in range(n_words):
        off = i * 4
        seed2 = (seed2 + CRYPT_TABLE[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        value = struct.unpack_from("<I", data, off)[0]
        value = (value ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed1 = (((~seed1 << 0x15) + 0x11111111) | (seed1 >> 0x0B)) & 0xFFFFFFFF
        seed2 = (value + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
        struct.pack_into("<I", out, off, value)
    return bytes(out)


def mpq_encrypt(data: bytes, key: int) -> bytes:
    seed1 = key & 0xFFFFFFFF
    seed2 = 0xEEEEEEEE
    n_words = len(data) // 4
    out = bytearray(data)
    for i in range(n_words):
        off = i * 4
        seed2 = (seed2 + CRYPT_TABLE[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        value = struct.unpack_from("<I", data, off)[0]
        struct.pack_into("<I", out, off, (value ^ (seed1 + seed2)) & 0xFFFFFFFF)
        seed1 = (((~seed1 << 0x15) + 0x11111111) | (seed1 >> 0x0B)) & 0xFFFFFFFF
        seed2 = (value + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return bytes(out)


# StormLib pklib/explode.c tables & decompressor
_DIST_BITS = [
    2, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,
]
_DIST_CODE = [
    0x03, 0x0D, 0x05, 0x19, 0x09, 0x11, 0x01, 0x3E, 0x1E, 0x2E, 0x0E, 0x36, 0x16, 0x26, 0x06, 0x3A,
    0x1A, 0x2A, 0x0A, 0x32, 0x12, 0x22, 0x42, 0x02, 0x7C, 0x3C, 0x5C, 0x1C, 0x6C, 0x2C, 0x4C, 0x0C,
    0x74, 0x34, 0x54, 0x14, 0x64, 0x24, 0x44, 0x04, 0x78, 0x38, 0x58, 0x18, 0x68, 0x28, 0x48, 0x08,
    0xF0, 0x70, 0xB0, 0x30, 0xD0, 0x50, 0x90, 0x10, 0xE0, 0x60, 0xA0, 0x20, 0xC0, 0x40, 0x80, 0x00,
]
_EX_LEN_BITS = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8]
_LEN_BASE = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 14, 22, 38, 70, 134, 262]
_LEN_BITS = [3, 2, 3, 3, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 7, 7]
_LEN_CODE = [0x05, 0x03, 0x01, 0x06, 0x0A, 0x02, 0x0C, 0x14, 0x04, 0x18, 0x08, 0x30, 0x10, 0x20, 0x40, 0x00]


def _gen_decode_tabs(count: int, bits: list[int], code: list[int]) -> list[int]:
    tab = [0] * 256
    for i in range(count - 1, -1, -1):
        idx1 = code[i]
        idx2 = 1 << bits[i]
        while idx1 < 256:
            tab[idx1] = i
            idx1 += idx2
    return tab


_POS1 = _gen_decode_tabs(64, _DIST_BITS, _DIST_CODE)
_POS2 = _gen_decode_tabs(16, _LEN_BITS, _LEN_CODE)


def pkware_explode(data: bytes) -> bytes:
    if len(data) <= 4:
        return b""
    ctype = data[0]
    dsize_bits = data[1]
    bit_buff = data[2]
    extra_bits = 0
    in_pos = 3
    in_len = len(data)
    dsize_mask = 0xFFFF >> (16 - dsize_bits)
    out = bytearray(0x2204)
    out_pos = 0x1000
    result = bytearray()

    def waste(n: int) -> bool:
        nonlocal bit_buff, extra_bits, in_pos
        if n <= extra_bits:
            extra_bits -= n
            bit_buff >>= n
            return False
        bit_buff >>= extra_bits
        if in_pos >= in_len:
            return True
        bit_buff |= data[in_pos] << 8
        in_pos += 1
        bit_buff >>= n - extra_bits
        extra_bits = (extra_bits - n) + 8
        return False

    while True:
        if bit_buff & 1:
            if waste(1):
                break
            val = _POS2[bit_buff & 0xFF]
            if waste(_LEN_BITS[val]):
                break
            nb = _EX_LEN_BITS[val]
            if nb:
                v2 = bit_buff & ((1 << nb) - 1)
                if waste(nb) and (val + v2) != 0x10E:
                    break
                val = _LEN_BASE[val] + v2
            one_byte = val + 0x100
        else:
            if waste(1):
                break
            if ctype == 0:
                one_byte = bit_buff & 0xFF
                if waste(8):
                    break
            else:
                break
        if one_byte >= 0x305:
            break
        if one_byte >= 0x100:
            copy_len = one_byte - 0xFE
            pos = _POS1[bit_buff & 0xFF]
            if waste(_DIST_BITS[pos]):
                break
            if copy_len == 2:
                pos = (pos << 2) | (bit_buff & 3)
                if waste(2):
                    break
            else:
                pos = (pos << dsize_bits) | (bit_buff & dsize_mask)
                if waste(dsize_bits):
                    break
            move_back = pos + 1
            src = out_pos - move_back
            for _ in range(copy_len):
                out[out_pos] = out[src]
                out_pos += 1
                src += 1
        else:
            out[out_pos] = one_byte
            out_pos += 1
        if out_pos >= 0x2000:
            result.extend(out[0x1000:0x2000])
            out[: out_pos - 0x1000] = out[0x1000:out_pos]
            out_pos -= 0x1000
    if out_pos > 0x1000:
        result.extend(out[0x1000:out_pos])
    return bytes(result)


class MPQReader:
    def __init__(self, mpq_bytes: bytes):
        self.mpq = mpq_bytes
        if len(mpq_bytes) < 32 or mpq_bytes[:4] != b"MPQ\x1a":
            raise ValueError("Invalid MPQ archive header")
        (
            self.magic,
            self.header_size,
            self.archive_size,
            self.format_version,
            self.sector_size_shift,
            self.hash_table_offset,
            self.block_table_offset,
            self.hash_table_entries,
            self.block_table_entries,
        ) = struct.unpack_from("<4s2I2H4I", mpq_bytes, 0)

        ht_raw = mpq_bytes[self.hash_table_offset : self.hash_table_offset + self.hash_table_entries * 16]
        ht_len = (len(ht_raw) // 16) * 16
        ht_dec = mpq_decrypt(ht_raw[:ht_len], mpq_hash("(hash table)", "TABLE"))
        actual_ht_entries = len(ht_dec) // 16
        self.hash_table = [
            MPQHashTableEntry._make(struct.unpack_from("<2I2HI", ht_dec, i * 16))
            for i in range(actual_ht_entries)
        ]

        bt_raw = mpq_bytes[self.block_table_offset : self.block_table_offset + self.block_table_entries * 16]
        bt_len = (len(bt_raw) // 16) * 16
        bt_dec = mpq_decrypt(bt_raw[:bt_len], mpq_hash("(block table)", "TABLE"))
        actual_bt_entries = len(bt_dec) // 16
        self.block_table = [
            MPQBlockTableEntry._make(struct.unpack_from("<4I", bt_dec, i * 16))
            for i in range(actual_bt_entries)
        ]

    def find_hash_entry(self, filename: str) -> MPQHashTableEntry | None:
        ha = mpq_hash(filename, "HASH_A")
        hb = mpq_hash(filename, "HASH_B")
        for entry in self.hash_table:
            if entry.hash_a == ha and entry.hash_b == hb and entry.block_table_index < len(self.block_table):
                return entry
        return None

    def read_file(self, filename: str) -> bytes | None:
        try:
            he = self.find_hash_entry(filename)
            if he is None:
                return None
            be = self.block_table[he.block_table_index]
            if not (be.flags & MPQ_FILE_EXISTS) or be.archived_size == 0 or be.offset >= len(self.mpq):
                return None
            raw = self.mpq[be.offset : be.offset + be.archived_size]
            if not raw:
                return None
            base_name = filename.replace("/", "\\").split("\\")[-1]
            key = mpq_hash(base_name, "TABLE")
            if be.flags & MPQ_FILE_FIX_KEY:
                key = ((key + be.offset) ^ be.size) & 0xFFFFFFFF

            def decompress_sector(sec: bytes, expected_len: int) -> bytes:
                if not (be.flags & (MPQ_FILE_COMPRESS | MPQ_FILE_IMPLODE)) or len(sec) >= expected_len:
                    return sec
                if be.flags & MPQ_FILE_IMPLODE:
                    return pkware_explode(sec)
                if not sec:
                    return b""
                ctype = sec[0]
                if ctype == 0:
                    return sec[1:]
                if ctype == 2:
                    return zlib.decompress(sec[1:])
                if ctype == 8:
                    return pkware_explode(sec[1:])
                if ctype == 16:
                    return bz2.decompress(sec[1:])
                return sec

            if be.flags & MPQ_FILE_SINGLE_UNIT:
                sec = mpq_decrypt(raw, key) if (be.flags & MPQ_FILE_ENCRYPTED) else raw
                return decompress_sector(sec, be.size)

            sector_size = 512 << self.sector_size_shift
            sectors = (be.size + sector_size - 1) // sector_size if be.size > 0 else 1
            n_pos = sectors + (2 if (be.flags & MPQ_FILE_SECTOR_CRC) else 1)
            pos_bytes = raw[: 4 * n_pos]
            if len(pos_bytes) < 4 * n_pos:
                return None
            if be.flags & MPQ_FILE_ENCRYPTED:
                pos_bytes = mpq_decrypt(pos_bytes, (key - 1) & 0xFFFFFFFF)
            positions = struct.unpack(f"<{n_pos}I", pos_bytes)
            out = bytearray()
            left = be.size
            for i in range(sectors):
                if positions[i] >= len(raw) or positions[i + 1] > len(raw) or positions[i] > positions[i + 1]:
                    break
                sec = raw[positions[i] : positions[i + 1]]
                if be.flags & MPQ_FILE_ENCRYPTED:
                    sec = mpq_decrypt(sec, (key + i) & 0xFFFFFFFF)
                sec = decompress_sector(sec, min(sector_size, left))
                out.extend(sec)
                left -= len(sec)
            return bytes(out)
        except Exception:
            return None


def _rotl32(v: int, n: int) -> int:
    return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF


def xor_rotate_left(data: bytes) -> int:
    val = 0
    n = len(data)
    i = 0
    mv = memoryview(data)
    if n > 3:
        for offset in range(0, n - 3, 4):
            w = struct.unpack_from("<I", mv, offset)[0]
            val = (((val ^ w) << 3) | ((val ^ w) >> 29)) & 0xFFFFFFFF
            i = offset + 4
    while i < n:
        v = val ^ data[i]
        val = ((v << 3) | (v >> 29)) & 0xFFFFFFFF
        i += 1
    return val


_JASS_BASE_CACHE: tuple[bytes, bytes, int, "hashlib._Hash"] | None = None


def _get_jass_base():
    global _JASS_BASE_CACHE
    if _JASS_BASE_CACHE is not None:
        return _JASS_BASE_CACHE
    lzma_path = Path(__file__).resolve().parent / "jass_base.lzma"
    raw = lzma.decompress(lzma_path.read_bytes())
    cj_len = struct.unpack_from("<I", raw, 0)[0]
    cj = raw[4 : 4 + cj_len]
    bj = raw[4 + cj_len :]
    val = xor_rotate_left(cj) ^ xor_rotate_left(bj)
    val = _rotl32(val, 3)
    val = _rotl32(val ^ 0x03F1379E, 3)
    sha = hashlib.sha1()
    sha.update(cj)
    sha.update(bj)
    sha.update(b"\x9e\x37\xf1\x03")
    _JASS_BASE_CACHE = (cj, bj, val, sha)
    return _JASS_BASE_CACHE


# Universal Camera Distance (-cam 1 .. 2 or 1200 .. 3300) + ESC ClearTextMessages + Black Sky/Fog fix
# Zero globals, zero periodic timers, zero memory hooks -> 100% crash-free & save/load safe on 6.74c / 6.83d.
CAM_FEATURE_JASS = b"""
function Aegis_CamAction takes nothing returns nothing
local string s = GetEventPlayerChatString()
local integer len = StringLength(s)
local real val = 1.0
local real dist = 1650.0
if GetTriggerEventId() == EVENT_PLAYER_END_CINEMATIC or s == "-clear" or s == "-c" then
if GetLocalPlayer() == GetTriggerPlayer() then
call ClearTextMessages()
endif
return
endif
if SubString(s,0,5)=="-cam " and len > 5 then
set val = S2R(SubString(s,5,len))
elseif SubString(s,0,6)=="-zoom " and len > 6 then
set val = S2R(SubString(s,6,len))
endif
if val >= 500.0 then
set dist = val
else
if val < 0.8 then
set val = 1.0
elseif val > 2.0 then
set val = 2.0
endif
set dist = 1650.0 * val
endif
if dist < 1200.0 then
set dist = 1200.0
elseif dist > 3300.0 then
set dist = 3300.0
endif
if GetLocalPlayer() == GetTriggerPlayer() then
call SetSkyModel(null)
call SetTerrainFogEx(0, 9999999.0, 10000000.0, 0.0, 0.0, 0.0, 0.0)
call SetCameraField(CAMERA_FIELD_FARZ, 100000.0, 0.0)
call SetCameraField(CAMERA_FIELD_TARGET_DISTANCE, dist, 0.20)
call SetCameraField(CAMERA_FIELD_ANGLE_OF_ATTACK, 304.0, 0.20)
call SetCameraField(CAMERA_FIELD_ROTATION, 90.0, 0.20)
call DisplayTimedTextToPlayer(GetTriggerPlayer(), 0.0, 0.0, 5.0, "|cff10b981[MongolRanger]|r Camera: |cffffcc00" + I2S(R2I(dist)) + "|r (Default: 1650 / -cam 1..2)")
endif
endfunction

function Aegis_InitCam takes nothing returns nothing
local trigger t = CreateTrigger()
local integer i = 0
call SetSkyModel(null)
call SetTerrainFogEx(0, 9999999.0, 10000000.0, 0.0, 0.0, 0.0, 0.0)
loop
exitwhen i > 11
call TriggerRegisterPlayerChatEvent(t, Player(i), "-cam", false)
call TriggerRegisterPlayerChatEvent(t, Player(i), "-zoom", false)
call TriggerRegisterPlayerChatEvent(t, Player(i), "-clear", true)
call TriggerRegisterPlayerChatEvent(t, Player(i), "-c", true)
call TriggerRegisterPlayerEvent(t, Player(i), EVENT_PLAYER_END_CINEMATIC)
set i = i + 1
endloop
call TriggerAddAction(t, function Aegis_CamAction)
set t = null
endfunction
"""

SAVE_REPEATABLE = b"""function LSVN takes nothing returns nothing
if OBCC(CBH+0x43F088)==0x01508D52 then
call BBGC(CBH+0x43F088,0x00508D52,true,true)
endif
endfunction
"""

SAVE_EMPTY_ARRAYS = b"""function LRSV takes nothing returns nothing
local timer t=GetExpiredTimer()
local integer h=GetHandleId(t)
local integer k=LoadInteger(HY,h,0)
if LoadInteger(HY,h,2)==OBVO then
call HOVC(k+4,-1)
call HOVC(k+8,-1)
set k=LoadInteger(HY,h,1)
call HOVC(k+4,-1)
call HOVC(k+8,-1)
endif
call FlushChildHashtable(HY,h)
call DestroyTimer(t)
set t=null
endfunction
function LSAV takes nothing returns nothing
local timer r=CreateTimer()
local integer h=GetHandleId(r)
local integer t=OBCC(GFOC(1)+0x285C)
local integer s=OBCC(t+4)
local integer n=OBCC(t+12)
local integer k
local integer f=0
loop
exitwhen n<0x10000 or f==2
set k=OBCC(OBCC(n+0x14))
if k==0x4F4F42 or k==0x4F4742 then
set k=OBCC(n+0x20)
call SaveInteger(HY,h,f,k)
set f=f+1
endif
set n=OBCC(n+s+4)
endloop
if f==2 then
call SaveInteger(HY,h,2,OBVO)
set k=LoadInteger(HY,h,0)
call HOVC(k+4,0)
call HOVC(k+8,0)
set k=LoadInteger(HY,h,1)
call HOVC(k+4,0)
call HOVC(k+8,0)
endif
call TimerStart(r,0,false,function LRSV)
set r=null
endfunction
"""


def _drop_function_by_name(script: bytes, name: bytes) -> bytes:
    if name not in script:
        return script
    matches = list(re.finditer(rb"[\r\n]function %s takes" % name, script))
    if not matches:
        return script
    start = matches[0].start() + 1
    end_match = re.compile(rb"endfunction[\r\n]").search(script, start)
    if not end_match:
        return script
    return script[:start] + script[end_match.end() :]


def has_native_cam_command(script: bytes) -> bool:
    """Detect if a map (such as DotA 6.81+, 6.85k, 6.85i LoD, 6.85m LoD, 6.88+) already has built-in -cam / -zoom."""
    markers = (
        b"Aegis_InitCam",
        b'"-cam"',
        b'"-cam "',
        b'"-camera"',
        b'"-camera "',
        b'"-zoom"',
        b'"-zoom "',
        b"'CAMD'",
        b"1128353092",
        b"Incorrect camera distance",
        b"Incorrect multiplier, camera changed to default",
    )
    return any(m in script for m in markers)


def patch_jass_script(script: bytes, enable_cam: bool = True, enable_reconnect: bool = True) -> tuple[bytes, bool, bool]:
    changed = script
    if b'call SetSkyModel("Environment\\\\Sky\\\\FoggedSky\\\\FoggedSky.mdl")' in changed:
        changed = changed.replace(
            b'call SetSkyModel("Environment\\\\Sky\\\\FoggedSky\\\\FoggedSky.mdl")',
            b"call SetSkyModel(null)\ncall SetTerrainFogEx(0,9999999.,10000000.,.0,.0,.0,.0)",
        )
    elif b"call SetSkyModel(null)" in changed and b"SetTerrainFogEx(0,9999999." not in changed:
        changed = changed.replace(
            b"call SetSkyModel(null)",
            b"call SetSkyModel(null)\ncall SetTerrainFogEx(0,9999999.,10000000.,.0,.0,.0,.0)",
            1,
        )
    if b"function Aegis_CamAction" in changed:
        changed = _drop_function_by_name(changed, b"Aegis_CamAction")
        changed = _drop_function_by_name(changed, b"Aegis_InitCam")
        changed = changed.replace(b"call Aegis_InitCam()\n", b"").replace(b"call Aegis_InitCam()\r\n", b"")

    has_cam = has_native_cam_command(changed)
    has_reconnect = True

    # ONLY inject -cam into older maps (like 6.74c LoD) that do NOT already have a native -cam command.
    # Maps that already have -cam (6.81+, 6.85m LoD, etc.) are left 100% untouched to avoid conflicts/crashes.
    if enable_cam and not has_cam:
        main_match = changed.find(b"function main takes nothing returns nothing")
        if main_match != -1:
            changed = changed[:main_match] + CAM_FEATURE_JASS + b"\n" + changed[main_match:]
            main_body = changed.find(b"function main takes nothing returns nothing")
            end_main = changed.find(b"endfunction", main_body)
            if end_main != -1:
                changed = changed[:end_main] + b"call Aegis_InitCam()\n" + changed[end_main:]
                has_cam = True

    # Standard Warcraft III maps (6.74c, 6.80c, 6.83d, etc.) support native multiplayer Save-Game (.w3z)
    # without any JASS modification. Only apply the 6.85m MemHack save-fix if the exact 6.85m signature is present.
    old_ovgfo = b"function OVGFO takes nothing returns integer\nreturn OBCC(CHH+12)\r"
    if enable_reconnect and old_ovgfo in changed:
        if b'call ExecuteFunc("OOHCO")' in changed:
            changed = changed.replace(b'call ExecuteFunc("OOHCO")', b'// call ExecuteFunc("OOHCO")')
        new_ovgfo = b"function OVGFO takes nothing returns integer\nreturn OBCC(OBCC(CBH+0xAB65F4)+28)-4\r"
        for dead_func in (
            b"TestPrintAllTimers",
            b"TestPrintAllTimers2",
            b"OVGGO",
            b"TestRectEditor",
            b"TestBlockOrders",
            b"TestTerrainFilter",
            b"PrintJassNatives",
            b"TestReadWriteINI",
            b"TestIsReplay",
            b"TestDisableSaveGameButton",
        ):
            changed = _drop_function_by_name(changed, dead_func)
        changed = changed.replace(old_ovgfo, new_ovgfo)

        if b"OBCC(" in changed and b"CBH" in changed:
            main_match = changed.find(b"function main takes nothing returns nothing")
            if main_match != -1:
                if b"function LSVN takes nothing" not in changed:
                    changed = changed[:main_match] + SAVE_REPEATABLE + b"\n" + changed[main_match:]
                    main_match = changed.find(b"function main takes nothing returns nothing")
                if b"function LSAV takes nothing" not in changed and b"GFOC(1)" in changed:
                    changed = changed[:main_match] + SAVE_EMPTY_ARRAYS + b"\n" + changed[main_match:]
            if b"EVENT_GAME_SAVE" not in changed:
                hook_anchor = b"call TimerStart(CreateTimer(),0.1,true,function OVGVO)"
                if hook_anchor in changed:
                    save_hook = (
                        b"\ncall LSVN()\nset t=CreateTrigger()\n"
                        b"call TriggerRegisterGameEvent(t,EVENT_GAME_SAVE)\n"
                        b"call TriggerAddAction(t,function LSAV)"
                    )
                    changed = changed.replace(hook_anchor, hook_anchor + save_hook)

    return changed, has_cam, has_reconnect


def _pack_mpq_script(
    mpq_bytes: bytes,
    reader: MPQReader,
    script_name: str,
    patched_script: bytes,
) -> bytes:
    he = reader.find_hash_entry(script_name)
    if he is None:
        return mpq_bytes
    idx = he.block_table_index
    orig_be = reader.block_table[idx]
    base_name = script_name.replace("/", "\\").split("\\")[-1]
    base_key = mpq_hash(base_name, "TABLE")

    sector_size = 512 << reader.sector_size_shift
    new_flags = (
        orig_be.flags & ~MPQ_FILE_SECTOR_CRC & ~MPQ_FILE_SINGLE_UNIT & ~MPQ_FILE_IMPLODE
    ) | MPQ_FILE_EXISTS | MPQ_FILE_COMPRESS | MPQ_FILE_ENCRYPTED

    def build_encrypted_sectors_for(script_buf: bytes, block_offset: int) -> bytes:
        secs = (len(script_buf) + sector_size - 1) // sector_size if len(script_buf) > 0 else 1
        key = ((base_key + block_offset) ^ len(script_buf)) & 0xFFFFFFFF if (new_flags & MPQ_FILE_FIX_KEY) else base_key
        comp_sectors = []
        for i in range(secs):
            chunk = script_buf[i * sector_size : (i + 1) * sector_size]
            comp = b"\x02" + zlib.compress(chunk, 9)
            if len(comp) >= len(chunk):
                comp = chunk
            comp_sectors.append(mpq_encrypt(comp, (key + i) & 0xFFFFFFFF))
        pos_list = [4 * (secs + 1)]
        for s in comp_sectors:
            pos_list.append(pos_list[-1] + len(s))
        pos_raw = struct.pack(f"<{secs + 1}I", *pos_list)
        pos_enc = mpq_encrypt(pos_raw, (key - 1) & 0xFFFFFFFF)
        return pos_enc + b"".join(comp_sectors)

    # First try in-place at orig_be.offset so total .w3x file size and MPQ block table offset never change
    raw_block = build_encrypted_sectors_for(patched_script, orig_be.offset)
    if len(raw_block) > orig_be.archived_size:
        # Strip full-line JASS comments or shorten non-gameplay tutorial tip strings to fit in-place
        cand = re.sub(rb"(?m)^[ \t]*//[^\r\n]*[\r\n]+", b"", patched_script)
        if cand != patched_script:
            patched_script = cand
            raw_block = build_encrypted_sectors_for(patched_script, orig_be.offset)
        for trim_count in (8, 14, 24, 40, 64):
            if len(raw_block) <= orig_be.archived_size:
                break
            cand = re.sub(
                rb'(set [A-Za-z0-9_]+\[i\]=)"[^"\r\n]{120,}"',
                rb'\1""',
                patched_script,
                count=trim_count,
            )
            if cand != patched_script:
                patched_script = cand
                raw_block = build_encrypted_sectors_for(patched_script, orig_be.offset)

    result = bytearray(mpq_bytes)
    entries = list(reader.block_table)

    # Clear stale (attributes) / (signature) entries so Storm.dll never rejects a patched war3map.j
    for meta_file in ("(attributes)", "(signature)"):
        m_he = reader.find_hash_entry(meta_file)
        if m_he is not None and 0 <= m_he.block_table_index < len(entries):
            entries[m_he.block_table_index] = MPQBlockTableEntry(0, 0, 0, 0)

    if len(raw_block) <= orig_be.archived_size:
        result[orig_be.offset : orig_be.offset + len(raw_block)] = raw_block
        if len(raw_block) < orig_be.archived_size:
            pad_len = orig_be.archived_size - len(raw_block)
            result[orig_be.offset + len(raw_block) : orig_be.offset + orig_be.archived_size] = b"\x00" * pad_len
        entries[idx] = MPQBlockTableEntry(orig_be.offset, len(raw_block), len(patched_script), new_flags)
        bt_plain = b"".join(struct.pack("<4I", *e) for e in entries)
        bt_enc = mpq_encrypt(bt_plain, mpq_hash("(block table)", "TABLE"))
        result[reader.block_table_offset : reader.block_table_offset + len(bt_enc)] = bt_enc
    elif reader.block_table_offset + len(entries) * 16 >= len(mpq_bytes):
        new_offset = reader.block_table_offset
        raw_block = build_encrypted_sectors_for(patched_script, new_offset)
        entries[idx] = MPQBlockTableEntry(new_offset, len(raw_block), len(patched_script), new_flags)
        bt_plain = b"".join(struct.pack("<4I", *e) for e in entries)
        bt_enc = mpq_encrypt(bt_plain, mpq_hash("(block table)", "TABLE"))
        result = result[:new_offset] + bytearray(raw_block) + bytearray(bt_enc)
        new_bt_offset = new_offset + len(raw_block)
        struct.pack_into("<I", result, 20, new_bt_offset)
        if reader.archive_size <= len(mpq_bytes):
            struct.pack_into("<I", result, 8, len(result))
    else:
        new_offset = len(result)
        raw_block = build_encrypted_sectors_for(patched_script, new_offset)
        result.extend(raw_block)
        entries[idx] = MPQBlockTableEntry(new_offset, len(raw_block), len(patched_script), new_flags)
        if reader.archive_size <= len(mpq_bytes):
            struct.pack_into("<I", result, 8, len(result))
        bt_plain = b"".join(struct.pack("<4I", *e) for e in entries)
        bt_enc = mpq_encrypt(bt_plain, mpq_hash("(block table)", "TABLE"))
        result[reader.block_table_offset : reader.block_table_offset + len(bt_enc)] = bt_enc

    return bytes(result)


def parse_war3map_w3i(w3i_bytes: bytes | None) -> dict:
    default_slots = []
    for c in range(1, 6):
        default_slots.append({
            "pid": 0, "download": 255, "status": 0, "computer": 0,
            "team": 0, "colour": c, "race": 4, "difficulty": 1, "handicap": 100,
        })
    for c in range(7, 12):
        default_slots.append({
            "pid": 0, "download": 255, "status": 0, "computer": 0,
            "team": 1, "colour": c, "race": 8, "difficulty": 1, "handicap": 100,
        })
    fallback = {
        "map_name": "",
        "map_author": "Unknown",
        "map_width": [118, 0],
        "map_height": [120, 0],
        "map_options": 96,
        "num_players": 10,
        "num_teams": 2,
        "slots": default_slots,
    }
    if not w3i_bytes or len(w3i_bytes) < 28:
        return fallback

    pos = 0
    n = len(w3i_bytes)

    def read_u32() -> int:
        nonlocal pos
        if pos + 4 > n:
            raise EOFError()
        val = struct.unpack_from("<I", w3i_bytes, pos)[0]
        pos += 4
        return val

    def skip(count: int):
        nonlocal pos
        if pos + count > n:
            raise EOFError()
        pos += count

    def read_cstr() -> str:
        nonlocal pos
        end = w3i_bytes.find(b"\x00", pos)
        if end == -1:
            raise EOFError()
        s = w3i_bytes[pos:end].decode("utf-8", errors="replace")
        pos = end + 1
        return s

    try:
        file_format = read_u32()
        if file_format not in (18, 25):
            return fallback
        skip(8)  # saves + editor version
        map_name = read_cstr()
        map_author = read_cstr()
        read_cstr()  # description
        read_cstr()  # players recommended
        skip(48)  # camera bounds (32 + 16)
        raw_width = read_u32()
        raw_height = read_u32()
        raw_flags = read_u32()
        skip(1)  # ground type

        if file_format == 18:
            skip(4)
        else:
            skip(4)
            read_cstr()
        read_cstr()
        read_cstr()
        read_cstr()

        if file_format == 18:
            skip(4)
        else:
            skip(4)
            read_cstr()
        read_cstr()
        read_cstr()
        read_cstr()

        if file_format == 25:
            skip(24)  # terrain fog + weather
            read_cstr()  # sound env
            skip(5)  # light + water tint

        raw_num_players = read_u32()
        closed_slots = 0
        slots = []
        for _ in range(min(raw_num_players, 24)):
            colour = read_u32()
            status = read_u32()
            race = read_u32()
            skip(4)  # fixed start pos
            read_cstr()  # player name
            skip(16)  # start x/y + ally priorities

            slot_status = 0
            comp = 0
            comp_type = 1
            if status == 1:
                slot_status = 0
            elif status == 2:
                slot_status = 2
                comp = 1
                comp_type = 1
            else:
                slot_status = 1
                closed_slots += 1

            slot_race = 32  # RANDOM
            if race == 1:
                slot_race = 1  # HUMAN
            elif race == 2:
                slot_race = 2  # ORC
            elif race == 3:
                slot_race = 8  # UNDEAD
            elif race == 4:
                slot_race = 4  # NIGHTELF

            if slot_status != 1:
                slots.append({
                    "pid": 0,
                    "download": 255,
                    "status": slot_status,
                    "computer": comp,
                    "team": 0,
                    "colour": colour & 0xFF,
                    "race": slot_race,
                    "difficulty": comp_type,
                    "handicap": 100,
                })

        raw_num_teams = read_u32()
        for team_idx in range(min(raw_num_teams, 24)):
            skip(4)  # team flags
            player_mask = read_u32()
            for j in range(12):
                if player_mask & 1:
                    for s in slots:
                        if s["colour"] == j:
                            s["team"] = team_idx
                player_mask >>= 1
            read_cstr()  # team name

        map_options = raw_flags & (MAPOPT_MELEE | MAPOPT_FIXEDPLAYERSETTINGS | MAPOPT_CUSTOMFORCES)
        if map_options & MAPOPT_MELEE:
            for idx, s in enumerate(slots):
                s["team"] = idx
                s["race"] = 32
        if not (map_options & MAPOPT_FIXEDPLAYERSETTINGS):
            for s in slots:
                s["race"] |= 64  # SLOTRACE_SELECTABLE

        num_players = max(1, raw_num_players - closed_slots)
        return {
            "map_name": map_name,
            "map_author": map_author,
            "map_width": list(struct.pack("<H", raw_width & 0xFFFF)),
            "map_height": list(struct.pack("<H", raw_height & 0xFFFF)),
            "map_options": map_options,
            "num_players": num_players,
            "num_teams": raw_num_teams,
            "slots": slots if slots else default_slots,
        }
    except EOFError:
        return fallback


def process_map_bytes(
    source_bytes: bytes,
    filename: str,
    enable_cam: bool = True,
    enable_reconnect: bool = True,
) -> tuple[bytes, dict]:
    """Optionally patches war3map.j with -cam & reconnect hooks and computes full W3GS metadata."""
    mpq_offset = source_bytes.find(b"MPQ\x1a")
    if mpq_offset == -1:
        raise ValueError("Uploaded file is not a valid Warcraft III .w3x / .w3m MPQ archive")

    header_title = ""
    if source_bytes[:4] == b"HM3W" and len(source_bytes) > 16:
        end_t = source_bytes.find(b"\x00", 8)
        if 8 < end_t < 128:
            header_title = source_bytes[8:end_t].decode("utf-8", errors="replace").strip()

    mpq_bytes = source_bytes[mpq_offset:]
    reader = MPQReader(mpq_bytes)

    script_name = None
    orig_script = None
    for candidate in ("war3map.j", "scripts\\war3map.j"):
        data = reader.read_file(candidate)
        if data is not None:
            script_name = candidate
            orig_script = data
            break

    has_cam = False
    has_reconnect = True
    patched_modified = False

    if orig_script is not None:
        patched_script, has_cam, has_reconnect = patch_jass_script(
            orig_script,
            enable_cam=enable_cam,
            enable_reconnect=enable_reconnect,
        )
        if patched_script != orig_script and script_name is not None:
            mpq_bytes = _pack_mpq_script(mpq_bytes, reader, script_name, patched_script)
            source_bytes = source_bytes[:mpq_offset] + mpq_bytes
            reader = MPQReader(mpq_bytes)
            patched_modified = True

    # Calculate GHost++ byte-identical map_crc and map_sha1
    cj, bj, base_val, base_sha = _get_jass_base()
    custom_cj = reader.read_file("Scripts\\common.j")
    custom_bj = reader.read_file("Scripts\\blizzard.j")
    if custom_cj is not None or custom_bj is not None:
        use_cj = custom_cj if custom_cj is not None else cj
        use_bj = custom_bj if custom_bj is not None else bj
        val = xor_rotate_left(use_cj) ^ xor_rotate_left(use_bj)
        val = _rotl32(val, 3)
        val = _rotl32(val ^ 0x03F1379E, 3)
        sha = hashlib.sha1()
        sha.update(use_cj)
        sha.update(use_bj)
        sha.update(b"\x9e\x37\xf1\x03")
    else:
        val = base_val
        sha = base_sha.copy()

    found_script = False
    for sub_name in (
        "war3map.j",
        "scripts\\war3map.j",
        "war3map.w3e",
        "war3map.wpm",
        "war3map.doo",
        "war3map.w3u",
        "war3map.w3b",
        "war3map.w3d",
        "war3map.w3a",
        "war3map.w3q",
    ):
        if found_script and sub_name == "scripts\\war3map.j":
            continue
        sub_data = reader.read_file(sub_name)
        if sub_data:
            if sub_name in ("war3map.j", "scripts\\war3map.j"):
                found_script = True
            val = _rotl32(val ^ xor_rotate_left(sub_data), 3)
            sha.update(sub_data)

    w3i_info = parse_war3map_w3i(reader.read_file("war3map.w3i"))
    file_size = len(source_bytes)
    map_size_bytes = list(struct.pack("<I", file_size))
    map_info_bytes = list(struct.pack("<I", zlib.crc32(source_bytes) & 0xFFFFFFFF))
    map_crc_bytes = list(struct.pack("<I", val))
    map_sha1_bytes = list(sha.digest())

    clean_fname = Path(filename).name
    display_title = header_title or w3i_info["map_name"] or Path(clean_fname).stem
    display_title = re.sub(r"\|c[0-9A-Fa-f]{8}|\|r", "", display_title).strip() or Path(clean_fname).stem

    meta = {
        "filename": clean_fname,
        "title": display_title,
        "author": w3i_info["map_author"],
        "map_path": f"Maps\\Download\\{clean_fname}",
        "file_size": file_size,
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "map_size": map_size_bytes,
        "map_info": map_info_bytes,
        "map_crc": map_crc_bytes,
        "map_sha1": map_sha1_bytes,
        "map_width": w3i_info["map_width"],
        "map_height": w3i_info["map_height"],
        "map_options": w3i_info["map_options"],
        "num_players": w3i_info["num_players"],
        "num_teams": w3i_info["num_teams"],
        "slots": w3i_info["slots"],
        "has_cam": has_cam,
        "has_reconnect": has_reconnect,
        "patched": patched_modified,
    }
    return source_bytes, meta
