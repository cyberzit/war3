"""Universal DotA LoD Map Converter & Patcher (Aegis Map Forge).

Transforms ANY DotA LoD map (.w3x) into a Reconnect-Ready & State-Restorable map:
1. Injects -cam and -zoom distance controls (e.g. -cam 1.6, -cam 2, -cam 2400).
2. Unblocks the engine Save Game menu (OOHCO patch).
3. Fixes CGameState allocator reference on load (OVGFO patch).
4. Injects LSAV to safely serialize forged virtual memory arrays without crashing.
5. Injects LRBT bootstrap to re-bind native memory arena and hooks on load.
6. Injects LSVN to patch the engine save counter for infinite repeatable saves.
"""
import argparse
import hashlib
import io
from pathlib import Path
import re
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runtime/tooldeps"))
import mpyq

GAME = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III")


def encrypt(archive, data, key):
    out = bytearray(data)
    seed = 0xEEEEEEEE
    for offset in range(0, len(data) // 4 * 4, 4):
        seed = (seed + archive.encryption_table[0x400 + (key & 255)]) & 0xFFFFFFFF
        value = struct.unpack_from("<I", data, offset)[0]
        struct.pack_into("<I", out, offset, value ^ ((key + seed) & 0xFFFFFFFF))
        key = (((~key << 21) + 0x11111111) | (key >> 11)) & 0xFFFFFFFF
        seed = (value + seed + (seed << 5) + 3) & 0xFFFFFFFF
    return bytes(out)


def decrypt(archive, data, key):
    return archive._decrypt(data, key) + data[len(data) // 4 * 4:]


def extract_script(mpq_bytes: bytes):
    offset = mpq_bytes.find(b"MPQ\x1a")
    if offset == -1:
        raise ValueError("Not a valid Warcraft III .w3x MPQ archive")
    mpq = mpq_bytes[offset:]
    archive = mpyq.MPQArchive(io.BytesIO(mpq), listfile=False)
    index = archive.get_hash_table_entry("war3map.j").block_table_index
    entry = archive.block_table[index]
    key = archive._hash("war3map.j", "TABLE")
    raw = mpq[entry.offset:entry.offset + entry.archived_size]
    
    if entry.flags & 0x00000200: # Encrypted
        start, end = struct.unpack("<2I", decrypt(archive, raw[:8], (key - 1) & 0xFFFFFFFF))
        compressed = decrypt(archive, raw[start:end], key)
    else:
        compressed = raw
        
    if compressed[0] == 2:
        script = zlib.decompress(compressed[1:])
    else:
        script = zlib.decompress(compressed)
        
    return offset, archive, index, script


CAM_FEATURE_JASS = b"""
function Aegis_CamAction takes nothing returns nothing
local string s = GetEventPlayerChatString()
local real val
local integer len = StringLength(s)
if SubString(s,0,5)=="-cam " then
set val = S2R(SubString(s,5,len))
if val >= 0.8 and val <= 3.5 then
call SetCameraField(CAMERA_FIELD_TARGET_DISTANCE, 1650.0 * val, 0.25)
elseif val > 1000.0 and val <= 4000.0 then
call SetCameraField(CAMERA_FIELD_TARGET_DISTANCE, val, 0.25)
endif
elseif SubString(s,0,6)=="-zoom " then
set val = S2R(SubString(s,6,len))
if val >= 0.8 and val <= 3.5 then
call SetCameraField(CAMERA_FIELD_TARGET_DISTANCE, 1650.0 * val, 0.25)
elseif val > 1000.0 and val <= 4000.0 then
call SetCameraField(CAMERA_FIELD_TARGET_DISTANCE, val, 0.25)
endif
endif
endfunction

function Aegis_InitCam takes nothing returns nothing
local trigger t = CreateTrigger()
local integer i = 0
loop
exitwhen i > 15
call TriggerRegisterPlayerChatEvent(t, Player(i), "-cam ", false)
call TriggerRegisterPlayerChatEvent(t, Player(i), "-zoom ", false)
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


def drop_function_by_name(script: bytes, name: bytes) -> bytes:
    if name not in script:
        return script
    matches = list(re.finditer(rb'[\r\n]function %s takes' % name, script))
    if not matches:
        return script
    start = matches[0].start() + 1
    end_match = re.compile(rb'endfunction[\r\n]').search(script, start)
    if not end_match:
        return script
    return script[:start] + script[end_match.end():]


def patch_jass_script(script: bytes, enable_cam: bool = True) -> bytes:
    changed = script

    # 1. Inject Camera Zoom Trigger if requested
    if enable_cam and b"Aegis_InitCam" not in changed:
        main_match = changed.find(b"function main takes nothing returns nothing")
        if main_match != -1:
            changed = changed[:main_match] + CAM_FEATURE_JASS + b"\n" + changed[main_match:]
            # Insert call right before endfunction of function main (after all locals and init code)
            main_body = changed.find(b"function main takes nothing returns nothing")
            end_main = changed.find(b"endfunction", main_body)
            if end_main != -1:
                changed = changed[:end_main] + b"call Aegis_InitCam()\n" + changed[end_main:]
                print("[Converter] Injected -cam / -zoom camera distance trigger cleanly at end of main.")

    # 2. Save Unblock: disable OOHCO
    if b'call ExecuteFunc("OOHCO")' in changed:
        changed = changed.replace(b'call ExecuteFunc("OOHCO")', b'// call ExecuteFunc("OOHCO")')
        print("[Converter] Unblocked native Save Game menu.")

    # 3. Live CGameState fix
    old_ovgfo = b'function OVGFO takes nothing returns integer\nreturn OBCC(CHH+12)\r'
    new_ovgfo = b'function OVGFO takes nothing returns integer\nreturn OBCC(OBCC(CBH+0xAB65F4)+28)-4\r'
    if old_ovgfo in changed:
        # Free space by dropping unused debug printers and tests
        for dead_func in (
            b'TestPrintAllTimers', b'TestPrintAllTimers2', b'OVGGO', b'TestRectEditor', b'TestBlockOrders',
            b'TestTerrainFilter', b'PrintJassNatives', b'TestReadWriteINI', b'TestIsReplay', b'TestDisableSaveGameButton'
        ):
            changed = drop_function_by_name(changed, dead_func)
        changed = changed.replace(old_ovgfo, new_ovgfo)
        print("[Converter] Fixed live CGameState allocator dereference.")

    # 4. Inject LSVN & LSAV after endglobals / before main
    main_match = changed.find(b"function main takes nothing returns nothing")
    if main_match != -1:
        if b"function LSVN takes nothing" not in changed:
            changed = changed[:main_match] + SAVE_REPEATABLE + b"\n" + changed[main_match:]
            main_match = changed.find(b"function main takes nothing returns nothing")
            print("[Converter] Injected LSVN infinite save counter patch.")
        if b"function LSAV takes nothing" not in changed:
            changed = changed[:main_match] + SAVE_EMPTY_ARRAYS + b"\n" + changed[main_match:]
            print("[Converter] Injected LSAV memory serializer.")
    else:
        endglobals_idx = changed.find(b"endglobals")
        ins = (endglobals_idx + len(b"endglobals")) if endglobals_idx != -1 else len(changed)
        if b"function LSVN takes nothing" not in changed:
            changed = changed[:ins] + b"\n" + SAVE_REPEATABLE + b"\n" + changed[ins:]
            ins += len(SAVE_REPEATABLE) + 2
        if b"function LSAV takes nothing" not in changed:
            changed = changed[:ins] + b"\n" + SAVE_EMPTY_ARRAYS + b"\n" + changed[ins:]

    # 6. Hook EVENT_GAME_SAVE and EVENT_GAME_LOADED if triggers exist
    if b"EVENT_GAME_SAVE" not in changed:
        hook_anchor = b'call TimerStart(CreateTimer(),0.1,true,function OVGVO)'
        if hook_anchor in changed:
            save_hook = b'\ncall LSVN()\nset t=CreateTrigger()\ncall TriggerRegisterGameEvent(t,EVENT_GAME_SAVE)\ncall TriggerAddAction(t,function LSAV)'
            changed = changed.replace(hook_anchor, hook_anchor + save_hook)
            print("[Converter] Hooked EVENT_GAME_SAVE for automatic state serialization.")

    return changed


def convert_map(input_path: Path, output_path: Path | None = None, enable_cam: bool = True) -> Path:
    if not input_path.is_file():
        raise FileNotFoundError(f"Map file not found: {input_path}")

    if output_path is None:
        stem = input_path.stem
        output_path = input_path.with_name(f"{stem} Aegis.w3x")

    print(f"==================================================================")
    print(f"      Aegis Universal LoD Map Converter                           ")
    print(f"==================================================================")
    print(f"Input Map : {input_path.name}")
    print(f"Output Map: {output_path.name}")

    source_bytes = input_path.read_bytes()
    offset, archive, index, original_script = extract_script(source_bytes)
    print(f"[Converter] Successfully extracted war3map.j ({len(original_script)} bytes)")

    patched_script = patch_jass_script(original_script, enable_cam=enable_cam)

    mpq = source_bytes[offset:]
    key = archive._hash("war3map.j", "TABLE")
    sector = b"\x02" + zlib.compress(patched_script, 9)
    raw = encrypt(archive, struct.pack("<2I", 8, 8 + len(sector)), (key - 1) & 0xFFFFFFFF)
    raw += encrypt(archive, sector, key)

    result = bytearray(mpq)
    entries = list(archive.block_table)
    original_entry = entries[index]

    if len(raw) > original_entry.archived_size:
        raise ValueError(
            f"Compressed sector size ({len(raw)} bytes) exceeds allocated block ({original_entry.archived_size} bytes). "
            f"Cannot safely write without corrupting adjacent tables!"
        )

    result[original_entry.offset:original_entry.offset + len(raw)] = raw
    if len(raw) < original_entry.archived_size:
        result[original_entry.offset + len(raw):original_entry.offset + original_entry.archived_size] = b"\x00" * (original_entry.archived_size - len(raw))

    entries[index] = original_entry._replace(archived_size=len(raw), size=len(patched_script))
    table = b"".join(struct.pack("<4I", *entry) for entry in entries)
    table_offset = archive.header["block_table_offset"]
    result[table_offset:table_offset + len(table)] = encrypt(archive, table, archive._hash("(block table)", "TABLE"))

    final_map_bytes = source_bytes[:offset] + bytes(result)
    output_path.write_bytes(final_map_bytes)

    print(f"[Converter] SUCCESS! Saved converted map to: {output_path}")
    print(f"[Converter] Output SHA256: {hashlib.sha256(final_map_bytes).hexdigest()[:16]}...")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Aegis Universal LoD Map Converter")
    parser.add_argument("map", nargs="?", default=str(GAME / "Maps" / "Download" / "DotA LoD 6.85m.w3x"), help="Path to .w3x map")
    parser.add_argument("--output", "-o", default=None, help="Output map path")
    parser.add_argument("--no-cam", action="store_true", help="Disable camera distance injection")
    args = parser.parse_args()

    input_map = Path(args.map)
    out_map = Path(args.output) if args.output else None
    convert_map(input_map, out_map, enable_cam=not args.no_cam)


if __name__ == "__main__":
    main()
