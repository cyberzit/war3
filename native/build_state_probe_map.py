"""Build a research-only LoD map with its explicit save-menu blocker removed.

Uses mpyq for MPQ tables. Sector encryption follows StormLib SBaseCommon.cpp
and SFileReadFile.cpp. Only the pinned, single-sector script layout is accepted.
The original archive is never written. This does not make LoD save-compatible.
"""
import hashlib
import io
import re
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'runtime/tooldeps'))
import mpyq

SOURCE = Path(r'D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III\Maps\Download\DotA LoD 6.85m.w3x')
EXPECTED = 'fcda6794f58263fab73315725308ce3dda69c5bd15ce563c886e9510a110aef7'


def encrypt(archive, data, key):
    out = bytearray(data)
    seed = 0xEEEEEEEE
    for offset in range(0, len(data) // 4 * 4, 4):
        seed = (seed + archive.encryption_table[0x400 + (key & 255)]) & 0xFFFFFFFF
        value = struct.unpack_from('<I', data, offset)[0]
        struct.pack_into('<I', out, offset, value ^ ((key + seed) & 0xFFFFFFFF))
        key = (((~key << 21) + 0x11111111) | (key >> 11)) & 0xFFFFFFFF
        seed = (value + seed + (seed << 5) + 3) & 0xFFFFFFFF
    return bytes(out)


def decrypt(archive, data, key):
    return archive._decrypt(data, key) + data[len(data) // 4 * 4:]


def read_script(mpq):
    archive = mpyq.MPQArchive(io.BytesIO(mpq), listfile=False)
    index = archive.get_hash_table_entry('war3map.j').block_table_index
    entry = archive.block_table[index]
    assert entry.flags == 0x80010200, 'Unsupported script flags'
    assert entry.size < (512 << archive.header['sector_size_shift'])
    key = archive._hash('war3map.j', 'TABLE')
    raw = mpq[entry.offset:entry.offset + entry.archived_size]
    start, end = struct.unpack('<2I', decrypt(archive, raw[:8], (key - 1) & 0xFFFFFFFF))
    assert start == 8 and end == len(raw)
    compressed = decrypt(archive, raw[start:end], key)
    assert compressed[0] == 2, 'Expected zlib sector'
    script = zlib.decompress(compressed[1:])
    assert len(script) == entry.size
    return archive, index, script


SAVE_UNBLOCK = [(b'call ExecuteFunc("OOHCO")', b'')]  # Remove only this invocation.
# LoD's OVGFO takes the first InstanceGenerator<CGameState> slot (0xAB6EA4+0xC).
# After LoadGame that slot is the destroyed pre-load object; read the engine's
# live CGameWar3+0x1c instead. OVGVO adds 4 back and skips a null result.
LIVE_GAME_STATE = [(b'function OVGFO takes nothing returns integer\nreturn OBCC(CHH+12)\r',
                    b'function OVGFO takes nothing returns integer\nreturn OBCC(OBCC(CBH+0xAB65F4)+28)-4\r')]
# The longer OVGFO no longer fits the script's archived span. TestPrintAllTimers
# is a never-called debug printer (its name occurs only in definitions), so its
# body is dropped to make room; no live map behavior depends on it.
DEBUG_START = b'function TestPrintAllTimers takes nothing returns nothing\r'
DEBUG_END = b'function OVGGO takes nothing returns nothing'
def drop_function(name):
    """Remove one never-referenced function (its name occurs only in its definition)."""
    def mutate(script):
        assert len(re.findall(rb'\b%s\b' % name, script)) == 1, name
        start = re.search(rb'[\r\n]function %s takes' % name, script).start() + 1
        end = re.compile(rb'endfunction[\r\n]').search(script, start).end()
        assert 0 < end - start < 2048, name
        return script[:start] + script[end:]
    return mutate


# Process-local state a loaded game inherits from the saving process. These are
# reset on EVENT_GAME_LOADED so LoD's own bootstrap (BVBC: forged BOO/BGO memory
# arrays, game.dll addresses, new executable arena, HCOC native stubs, helper DLL)
# runs again in the new process, followed by main's code patches.
RESET_FALSE = (b'CHBV', b'CGOV', b'GHC')  # GHC: helper-DLL native hook active
RESET_TRUE = (b'VFF', b'FVF')  # first-use arena stub writers
RESET_ZERO = (b'BVH', b'BBH', b'BGH', b'OCG', b'HOG', b'FHF')  # native-table rebind caches
# Cached char* of JASS strings (OGH/OFH/OFO), engine map-grid pointer (HVCO), and A030 ability data pointer (GVO).
RESET_ZERO += (b'OGH', b'OFH', b'HVCO', b'OFO', b'GVO')


def reload_bootstrap(script):
    globals_part = script[:script.find(b'endglobals')]
    # Every global holding a GetProcAddress result (CFHC) is a process address.
    procs = sorted(set(n for n in re.findall(rb'set (\w+)=CFHC\(', script)
                       if re.search(rb'[\r\n]integer %s\b' % n, globals_part)))
    assert len(procs) == 51, len(procs)
    body = [b'set %s=false' % n for n in RESET_FALSE] + [b'set %s=true' % n for n in RESET_TRUE]
    body += [b'set %s=0' % n for n in RESET_ZERO + tuple(procs)]
    body += [b'call BVBC()', b'call OBBFO(true)', b'call OBBGO(true)', b'call OBHBO(0x100)',
             b'call OCOOO(true)', b'set i=BGOC(FGC,8,0x40)', b'call HOVC(FGC,0xFFFF681C)',
             b'call HOVC(FFC,0x6A570FFF)', b'call BGOC(FGC,8,i)', b'call OVGBO(true)']
    function = b'function LRBT takes nothing returns nothing\nlocal integer i\n' + b'\n'.join(body) + b'\nendfunction\n'
    anchor = b'function main takes nothing returns nothing'
    assert script.count(anchor) == 1
    script = script.replace(anchor, function + anchor)
    hook = b'call OVGBO(true)\ncall TimerStart(CreateTimer(),0.1,true,function OVGVO)'
    assert script.count(hook) == 1
    register = b'\nset t=CreateTrigger()\ncall TriggerRegisterGameEvent(t,EVENT_GAME_LOADED)\ncall TriggerAddAction(t,function LRBT)'
    return script.replace(hook, hook + register)


DEAD_DEBUG = [drop_function(n) for n in (b'TestRectEditor', b'TestBlockOrders', b'TestTerrainFilter', b'PrintJassNatives')]
PROBES = {2: SAVE_UNBLOCK, 3: SAVE_UNBLOCK + LIVE_GAME_STATE + ['drop-timer-debug'],
          4: SAVE_UNBLOCK + LIVE_GAME_STATE + ['drop-timer-debug'] + DEAD_DEBUG + [reload_bootstrap]}


# The engine's array serializer cannot write LoD's forged BOO/BGO memory arrays
# (header count 0xffffffff, data address 0). On EVENT_GAME_SAVE, LSAV walks the
# JASS global table (VM GFOC(1)+0x285c, the layout CloseTrace inspects) and sets
# both arrays' header fields (+4, +8) to 0 so they are saved empty; a zero-delay
# timer restores the forged 0xffffffff values once saving has finished. After a
# load, LRBT forges the arrays again, so the saved empty state is intended.
# GFOC reads through BOO itself, so the array addresses are found once and kept
# in HY under the timer; the restore only writes when OBVO (reallocated by LRBT
# in a new process) is unchanged, so a timer restored from a save does nothing.
SAVE_EMPTY_ARRAYS = b'''function LRSV takes nothing returns nothing
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
local timer r
local integer h
local integer t=OBCC(GFOC(1)+0x285C)
local integer s=OBCC(t+4)
local integer n=OBCC(t+12)
local integer k
local integer f=0
call LSVN()
set r=CreateTimer()
set h=GetHandleId(r)
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
'''


def save_empty_arrays(script):
    anchor = b'function LRBT takes nothing returns nothing'
    assert script.count(anchor) == 1
    script = script.replace(anchor, SAVE_EMPTY_ARRAYS + anchor)
    hook = b'call TriggerAddAction(t,function LRBT)'
    assert script.count(hook) == 1
    register = b'\nset t=CreateTrigger()\ncall TriggerRegisterGameEvent(t,EVENT_GAME_SAVE)\ncall TriggerAddAction(t,function LSAV)'
    return script.replace(hook, hook + register)


PROBES[5] = PROBES[4] + [save_empty_arrays]

# Hooks LoD installs 0.01 s into a game (FCVHG: game.dll patches, helper-DLL
# features, ability-data overrides, event hooks) and its first 0.3 s settings
# pass (HHCBO) are lost on load as well. LRBT reruns them after the bootstrap.
# FCVHG's one-time game-state work (quests, JASS id lists, the 15th-slot report)
# stays init-only, keyed on its timer event; LRBT runs on EVENT_GAME_LOADED.
INIT_ONLY = b'GetTriggerEventId()==EVENT_GAME_TIMER_EXPIRED'
RUNTIME_HOOKS = [
    (b'call FCFVG()\ncall FCFGG()\ncall CGOBO()\n',
     b'if ' + INIT_ONLY + b' then\ncall FCFVG()\ncall FCFGG()\ncall CGOBO()\nendif\n'),
    (b'if CHHV==15 then\ncall BFBC(GetLocalPlayer(),"15th")',
     b'if CHHV==15 and ' + INIT_ONLY + b' then\ncall BFBC(GetLocalPlayer(),"15th")'),
    # main's FGC/FFC patch is undone again by FCVHG's BGVC; OCOOO likewise.
    (b'call OCOOO(true)\nset i=BGOC(FGC,8,0x40)\ncall HOVC(FGC,0xFFFF681C)\ncall HOVC(FFC,0x6A570FFF)\ncall BGOC(FGC,8,i)\ncall OVGBO(true)',
     b'call OCOOO(true)\ncall OVGBO(true)\ncall FCVHG()\ncall HHGVO()\ncall HHCGO(true)\ncall HHCVO(1)\ncall HHCVO(2)\ncall HHCVO(3)\ncall HHCVO(4)'),
]
# Room for the hooks: TestPrintAllTimers2 is another never-called debug printer
# and OVGGO is only its timer callback.
PROBES[6] = PROBES[5] + RUNTIME_HOOKS + [drop_function(b'TestPrintAllTimers2'), drop_function(b'OVGGO')]


# game.dll's save-command handler (RVA 0x43f060) increments a per-player save
# counter (entry +0x3c, setter 0x53ef40), and the game menu (0x3500a0 via
# 0x53ef80) greys out Save Game once it is non-zero, so each player could save
# only once per match. LSVN changes the increment at 0x43f089 ("lea edx,[eax+1]")
# to "lea edx,[eax]". Every client runs the same patch, at init and after a load.
SAVE_REPEATABLE = b'''function LSVN takes nothing returns nothing
if OBCC(CBH+0x43F088)==0x01508D52 then
call BBGC(CBH+0x43F088,0x00508D52,true,true)
endif
if OBCC(CBH+0x4BC250)==0x8B909056 then
call BBGC(CBH+0x4BC250,0x8B2F7556,true,true)
endif
endfunction
'''



def save_repeatable(script):
    anchor = b'function LRSV takes nothing returns nothing'
    assert script.count(anchor) == 1
    script = script.replace(anchor, SAVE_REPEATABLE + anchor)
    for old, new in ((b'call TriggerAddAction(t,function LSAV)', b'call TriggerAddAction(t,function LSAV)\ncall LSVN()'),
                     (b'call OVGBO(true)\ncall FCVHG()', b'call OVGBO(true)\ncall LSVN()\ncall FCVHG()')):
        assert script.count(old) == 1, old
        script = script.replace(old, new)
    return script


PROBES[7] = PROBES[6] + [save_repeatable]


def refresh_loaded_view(script):
    """Probe 8: refresh the existing fog settings after the load completes.

    Hypothesis only: copied saves retain the saving client's view cache.
    Never disables fog or grants shared vision. No live-rejoin claim.
    """
    callback = b'''function LVPF takes nothing returns nothing
set CHHV=GetPlayerId(GetLocalPlayer())
set OVO=IsPlayerObserver(GetLocalPlayer())
call FogEnable(IsFogEnabled())
call FogMaskEnable(IsFogMaskEnabled())
call DisplayTimedTextToPlayer(GetLocalPlayer(),0,0,20,"View probe: player "+I2S(CHHV))
call DestroyTimer(GetExpiredTimer())
endfunction
'''
    anchor = b'function LRBT takes nothing returns nothing'
    assert script.count(anchor) == 1
    script = script.replace(anchor, callback + anchor)
    start = script.index(anchor)
    end = script.index(b'endfunction', start)
    return script[:end] + b'call TimerStart(CreateTimer(),0,false,function LVPF)\n' + script[end:]


PROBES[8] = PROBES[7] + [drop_function(b'TestReadWriteINI'), refresh_loaded_view]


def center_loaded_hero(script):
    """Restore only local camera; do not allocate handles or alter selection."""
    anchor = b'function LRBT takes nothing returns nothing'
    start = script.index(anchor)
    end = script.index(b'endfunction', start)
    camera = b'''set CHHV=GetPlayerId(GetLocalPlayer())
set OVO=IsPlayerObserver(GetLocalPlayer())
if not OVO and CGCH[CHHV]!=null then
if GetOwningPlayer(CGCH[CHHV])==GetLocalPlayer() then
call PanCameraToTimed(GetUnitX(CGCH[CHHV]),GetUnitY(CGCH[CHHV]),0)
endif
endif
'''
    return script[:end] + camera + script[end:]


# Native view rebind supersedes probe 8's ineffective fog-refresh timer.
PROBES[9] = PROBES[7] + [drop_function(b'TestReadWriteINI'), center_loaded_hero]


def reuse_loaded_hook_objects(script):
    """Probe 10: rebind saved hook objects, without repeating init allocations.

    FGCBO previously made another trigger on each load; HHGVO temporarily added
    two abilities just to discover module-relative code addresses. Preserve the
    trigger and the discovered RVAs in the save. This does not alter sync checks
    or assert that the complete load path is simulation-neutral.
    """
    script = script.replace(b'endglobals', b'trigger LRFT=null\ninteger LRVA=0\ninteger LRPA=0\nendglobals', 1)
    old = re.search(rb'function FGCBO takes.*?endfunction', script, re.S).group(0)
    assert b'local trigger t=CreateTrigger()' in old
    new = b'''function FGCBO takes nothing returns nothing
if LRFT==null then
set LRFT=CreateTrigger()
call TriggerAddAction(LRFT,function FGCFO)
endif
call OBVOO(GetHandleId(LRFT))
endfunction'''
    script = script.replace(old, new, 1)
    old = re.search(rb'function HHGVO takes.*?endfunction', script, re.S).group(0)
    new = old.replace(b'set GVOO=OBCC(OBCC(a)+0x30C)',
                      b'set GVOO=OBCC(OBCC(a)+0x30C)\nset LRVA=GVOO-CBH')
    new = new.replace(b'set a=OBCC(a)+0x30C', b'set a=OBCC(a)+0x30C\nset LRPA=a-CBH')
    assert new != old
    script = script.replace(old, new, 1)
    anchor = b'function LRBT takes nothing returns nothing'
    rebind = b'''function LRCH takes nothing returns nothing
local integer p
local integer old
if LRVA>0 and LRVA<0xB00000 and LRPA>0 and LRPA<0xB00000 then
set GVOO=CBH+LRVA
set p=CBH+LRPA
set old=BGOC(p,4,0x40)
call HOVC(p,GVOO)
call BGOC(p,4,old)
endif
endfunction
'''
    script = script.replace(anchor, rebind + anchor, 1)
    start = script.index(anchor)
    end = script.index(b'endfunction', start)
    body = script[start:end]
    assert body.count(b'call HHGVO()') == 1
    return script[:start] + body.replace(b'call HHGVO()', b'call LRCH()') + script[end:]


PROBES[10] = PROBES[9] + [drop_function(b'TestKeyPressed'), drop_function(b'TestPingsTest'),
                         drop_function(b'TestSendHttpGetRequest'), reuse_loaded_hook_objects]


def defer_loaded_camera(script):
    """Run local camera restoration on the existing post-load timer tick.

    EVENT_GAME_LOADED still exposes the saving player's local identity. The
    native participant remap happens afterward. Reuse OVGVO rather than adding
    another timer to the saved simulation's handle graph.
    """
    script = script.replace(b'endglobals', b'boolean LRCP=false\nendglobals', 1)
    start = script.index(b'function LRBT takes nothing returns nothing')
    end = script.index(b'endfunction', start)
    camera_start = script.index(b'set CHHV=GetPlayerId(GetLocalPlayer())', start, end)
    camera = script[camera_start:end]
    assert b'PanCameraToTimed' in camera
    script = script[:camera_start] + b'set LRCP=true\n' + script[end:]
    anchor = b'function OVGVO takes nothing returns nothing\nlocal integer OVGCO=OVGFO()+4'
    assert script.count(anchor) == 1
    return script.replace(anchor, anchor + b'\nif LRCP then\nset LRCP=false\n' + camera + b'endif\n', 1)


PROBES[11] = PROBES[10] + [defer_loaded_camera]


def reuse_loaded_ui_triggers(script):
    """Preserve the two helper callback triggers instead of allocating on load."""
    script = script.replace(b'endglobals', b'trigger LROT=null\ntrigger LRGT=null\nendglobals', 1)
    old = re.search(rb'function OBFCO takes.*?endfunction', script, re.S).group(0)
    assert old.count(b'CreateTrigger()') == 2
    new = b'''function OBFCO takes nothing returns nothing
if LROT==null then
set LROT=CreateTrigger()
call TriggerAddAction(LROT,function OBOVO)
set LRGT=CreateTrigger()
call TriggerAddAction(LRGT,function OBGBO)
endif
call OCHVO(GetHandleId(LROT))
call OBFGO(GetHandleId(LRGT))
endfunction'''
    return script.replace(old, new, 1)


PROBES[12] = PROBES[11] + [reuse_loaded_ui_triggers]


def sync_rng_and_selection_on_rejoin(script):
    """Probe 13: flush cached pre-save raw heap pointers and run 10-player authoritative hero/item/allocator sync."""
    script = script.replace(
        b'endglobals',
        b'integer LRSG=100003\ninteger LRSN=0\ninteger LRHS=0\ninteger LRAC=0\ninteger LRAS=0\ninteger LRLB=0\ninteger LIPC=0\ninteger array LNT\ninteger array LIT\ninteger array LRS\nendglobals',
        1,
    )
    bcoc_old = b'call OGVC("DLL_State",I2S(CHHV),CGVV)'
    assert script.count(bcoc_old) == 1
    script = script.replace(
        bcoc_old,
        b'if GetTriggerEventId()!=EVENT_GAME_LOADED then\ncall OGVC("DLL_State",I2S(CHHV),CGVV)\nendif',
        1,
    )
    lrbt_anchor = b'call BVBC()\n'
    assert script.count(lrbt_anchor) == 1
    lrbt_flush = (
        b'set GFO=0.\n'
        b'call FlushParentHashtable(FCO)\n'
    )
    script = script.replace(lrbt_anchor, lrbt_flush + lrbt_anchor, 1)

    lsav_anchor = b'call TimerStart(r,0,false,function LRSV)\n'
    assert script.count(lsav_anchor) == 1
    lsav_sync = (
        b'set LRSG=LRSG+104729\n'
        b'set LRSN=-5\n'
        b'if OBCC(CBH+0xAB778C)!=0 then\n'
        b'set LRAC=((OBCC(OBCC(CBH+0xAB778C)+0x1C)+256)/32)*32\n'
        b'set LRAS=OBCC(OBCC(CBH+0xAB778C)+0x50)-OBCC(OBCC(CBH+0xAB778C)+0x1C)\n'
        b'endif\n'
    )
    script = script.replace(lsav_anchor, lsav_anchor + lsav_sync, 1)

    lrsv_anchor = b'call DestroyTimer(t)\nset t=null\n'
    assert script.count(lrsv_anchor) == 1
    script = script.replace(lrsv_anchor, lrsv_anchor + b'call SetRandomSeed(LRSG)\n', 1)

    lrbt_end = b'call HHCVO(4)\n'
    assert script.count(lrbt_end) == 1
    script = script.replace(lrbt_end, lrbt_end + b'set LRSN=-5\n', 1)

    lrsy_fn = b'''function LRSB takes integer tc,integer ts returns nothing
local integer a=OBCC(CBH+0xAB778C)
local integer c
if a!=0 then
set c=OBCC(a+0x1C)
if tc>c then
call HOVC(OBVO+49000,-1)
call HOVC(OBVO+49004,0)
call FFOC(CBH+0x486780,a,0,OBVO+49000,tc-c)
endif
if ts>OBCC(a+0x50) then
call HOVC(a+0x50,ts)
endif
endif
endfunction
function LRSY takes nothing returns nothing
if LRSN!=0 then
set LRHS=LRHS+1
call SetRandomSeed(LRSG+LRHS*7919)
endif
endfunction
function LRST takes nothing returns nothing
local unit u
local item it
local integer i=1
local integer a
local integer s
set LRSN=LRSN+1
set a=OBCC(CBH+0xAB778C)
if a!=0 and LRAC>0 then
set s=OBCC(a+0x1C)
if s>LRLB then
set LRLB=((s+7)/32+1)*32
call LRSB(LRLB,LRLB+LRAS)
endif
endif
call LRSY()
set s=LRSN-(LRSN/6)*6
loop
exitwhen i>11
if i!=6 then
if LRSN==2 then
set LNT[i]=0
set LRS[i]=0
set LIT[i*6]=0
set LIT[i*6+1]=0
set LIT[i*6+2]=0
set LIT[i*6+3]=0
set LIT[i*6+4]=0
set LIT[i*6+5]=0
endif
set u=CGCH[i]
if u!=null then
set a=GOGC(u)
if a>0 then
if OBCC(a+12)!=LNT[i] or LRSN==3 or LRSN==12 then
set LNT[i]=OBCC(a+12)
set LRS[i]=LRSN+5
call OGVC("NT"+I2S(i),"1",LNT[i])
call OGVC("NT"+I2S(i),"2",OBCC(a+16))
endif
if (LRSN==LRS[i] or LRSN==LRS[i]+10) and CHHV==i then
call SelectUnit(u,false)
call SelectUnit(u,true)
endif
set it=UnitItemInSlot(u,s)
if it!=null then
set a=GOGC(it)
if a>0 then
if OBCC(a+12)!=LIT[i*6+s] or LRSN<16 then
set LIT[i*6+s]=OBCC(a+12)
call OGVC("I"+I2S(i)+I2S(s),"1",LIT[i*6+s])
call OGVC("I"+I2S(i)+I2S(s),"2",OBCC(a+16))
endif
endif
else
set LIT[i*6+s]=0
endif
endif
endif
endif
set i=i+1
endloop
set u=null
set it=null
endfunction
'''
    ovgvo_anchor = b'function OVGVO takes nothing returns nothing\nlocal integer OVGCO=OVGFO()+4'
    assert script.count(ovgvo_anchor) == 1
    sync_block = (
        b'\nif LRSN<0 then\n'
        b'set LRSN=LRSN+1\n'
        b'if LRSN==-4 then\n'
        b'call BBGC(CBH+0x4BC250,0x8B909056,true,true)\n'
        b'if LRAC>0 then\n'
        b'call LRSB(LRAC,LRAC+LRAS)\n'
        b'set LRLB=LRAC\n'
        b'endif\n'
        b'elseif LRSN==0 then\n'
        b'set LRSN=1\n'
        b'endif\n'
        b'elseif LRSN>0 then\n'
        b'call LRST()\n'
        b'endif'
    )
    script = script.replace(ovgvo_anchor, lrsy_fn + ovgvo_anchor + sync_block, 1)

    ffggg_old = b'function FFGGG takes nothing returns boolean\nif GetTriggerEventId()==EVENT_PLAYER_UNIT_PICKUP_ITEM then\r'
    assert script.count(ffggg_old) == 1
    ffggg_new = (
        ffggg_old
        + b'if LRSN>0 and GetTriggerUnit()==CGCH[GetPlayerId(GetOwningPlayer(GetTriggerUnit()))] then\n'
        + b'set LIPC=LIPC-(LIPC/99)*99+1\n'
        + b'call OGVC("IP"+I2S(GetPlayerId(GetOwningPlayer(GetTriggerUnit())))+"_"+I2S(LIPC),"1",OBCC(GOGC(GetManipulatedItem())+12))\n'
        + b'call OGVC("IP"+I2S(GetPlayerId(GetOwningPlayer(GetTriggerUnit())))+"_"+I2S(LIPC),"2",OBCC(GOGC(GetManipulatedItem())+16))\n'
        + b'endif\n'
    )
    script = script.replace(ffggg_old, ffggg_new, 1)

    fgvgo_old = b'function FGVGO takes nothing returns integer\nlocal integer HGFVO\rlocal integer i\rloop\n'
    assert script.count(fgvgo_old) == 1
    script = script.replace(fgvgo_old, fgvgo_old[:-5] + b'call LRSY()\rloop\n', 1)

    fbhbo_old = b'function FBHBO takes nothing returns integer\nlocal integer FBGOO=GetRandomInt(1,VO)\rlocal integer FBGHO=WO[FBGOO]\r'
    assert script.count(fbhbo_old) == 1
    script = script.replace(
        fbhbo_old,
        b'function FBHBO takes nothing returns integer\nlocal integer FBGOO\rlocal integer FBGHO\rcall LRSY()\rset FBGOO=GetRandomInt(1,VO)\r',
        1,
    )

    cvvvo_old = b'local integer FVHOO\rlocal integer i=0\rlocal integer te\n'
    assert script.count(cvvvo_old) == 1
    script = script.replace(cvvvo_old, cvvvo_old + b'call LRSY()\n', 1)

    hhfoh_old = b'function HHFOH takes nothing returns nothing\nlocal integer FVHOO\rlocal integer GVFVH\rlocal integer HFCBO\rlocal integer te\n'
    assert script.count(hhfoh_old) == 1
    script = script.replace(hhfoh_old, hhfoh_old + b'call LRSY()\n', 1)

    cvvgo_sel = b'call ClearSelectionForPlayer(p)\rcall SelectUnitAddForPlayer(u,p)\n'
    assert script.count(cvvgo_sel) == 1
    cvvgo_nt = (
        b'call OGVC("NT"+I2S(HOHOO),"1",OBCC(GOGC(u)+12))\n'
        b'call OGVC("NT"+I2S(HOHOO),"2",OBCC(GOGC(u)+16))\n'
    )
    script = script.replace(cvvgo_sel, cvvgo_nt + cvvgo_sel, 1)

    return script


PROBES[13] = PROBES[12] + [
    drop_function(b'SaveHeroesTick'),
    drop_function(b'InitKeyActionHook'),
    drop_function(b'CraniumBasherWrapper'),
    drop_function(b'InitGlobalConvertString'),
    drop_function(b'Rot_Suicide'),
    drop_function(b'TestSendPacket'),
    drop_function(b'TestLockedPing'),
    drop_function(b'TestRemoveGameAreaLimit'),
    drop_function(b'TestIfdamageHookCrash'),
    drop_function(b'TestEnableAllyCheckbox2'),
    drop_function(b'TestEnableAllyCheckbox'),
    drop_function(b'TestIsReplay'),
    drop_function(b'TestDisableSaveGameButton'),
    drop_function(b'TestGetFrameItem'),
    drop_function(b'TestGetFrame'),
    drop_function(b'OOGOO'),
    drop_function(b'OOFHO'),
    drop_function(b'OOFGO'),
    drop_function(b'OOVHO'),
    drop_function(b'OOVVO'),
    sync_rng_and_selection_on_rejoin,
]


# Diagnostic state dump (local file output only via Preload natives; zero handle allocation, zero group enumeration).
# Dumps deterministic hero coordinates, orders, HP, mana, nettag and RNG probe to <Warcraft III>\MRDump\<tag>.txt.
# Symmetrically triggered on BOTH survivor and replacement at post-rejoin OVGVO ticks.
STATE_DUMP = b'''function LRDP takes string tag,boolean rng returns nothing
local integer i=0
local unit u
local integer a
call PreloadGenClear()
call PreloadGenStart()
if rng then
call Preload("rng "+I2S(GetRandomInt(0,1000000000)))
endif
call Preload("tag "+tag+" lrsn "+I2S(LRSN)+" lrhs "+I2S(LRHS)+" lrsg "+I2S(LRSG)+" bvoc "+I2S(OBCC(OBCC(CBH+0xAB778C)+28))+" bvos "+I2S(OBCC(OBCC(CBH+0xAB778C)+80)))
loop
exitwhen i>11
call Preload("p "+I2S(i)+" g "+I2S(GetPlayerState(Player(i),PLAYER_STATE_RESOURCE_GOLD))+" l "+I2S(GetPlayerState(Player(i),PLAYER_STATE_RESOURCE_LUMBER)))
set u=CGCH[i]
if u!=null then
set a=GOGC(u)
if a>0 then
call Preload("h "+I2S(i)+" "+I2S(GetHandleId(u))+" "+I2S(GetUnitTypeId(u))+" "+I2S(R2I(GetUnitX(u)*10))+" "+I2S(R2I(GetUnitY(u)*10))+" "+I2S(R2I(GetWidgetLife(u)*10))+" "+I2S(R2I(GetUnitState(u,UNIT_STATE_MANA)*10))+" "+I2S(GetUnitCurrentOrder(u))+" nt "+I2S(OBCC(a+12)))
else
call Preload("h "+I2S(i)+" "+I2S(GetHandleId(u))+" "+I2S(GetUnitTypeId(u))+" "+I2S(R2I(GetUnitX(u)*10))+" "+I2S(R2I(GetUnitY(u)*10))+" "+I2S(R2I(GetWidgetLife(u)*10))+" "+I2S(R2I(GetUnitState(u,UNIT_STATE_MANA)*10))+" "+I2S(GetUnitCurrentOrder(u)))
endif
endif
set i=i+1
endloop
set u=null
call PreloadGenEnd("MRDump\\\\"+tag+".txt")
endfunction
'''


def state_dump_probe(script):
    anchor = b'function LRSY takes nothing returns nothing'
    assert script.count(anchor) == 1
    script = script.replace(anchor, STATE_DUMP + anchor, 1)
    # Post-rejoin ticks on every client, taken after LRSB quantization and before LRSY reseeds.
    old = b'call LRSY()\nset s=LRSN-(LRSN/6)*6\n'
    assert script.count(old) == 1
    script = script.replace(old, b'if LRSN==2 or LRSN==20 or LRSN==50 or LRSN==100 or LRSN==200 or LRSN==300 then\ncall LRDP("T"+I2S(LRSN),true)\nendif\ncall LRSY()\nset s=LRSN-(LRSN/6)*6\n', 1)
    return script



PROBES[13] = PROBES[13] + [
    state_dump_probe,
]



def drop_timer_debug(script):
    assert script.count(b'TestPrintAllTimers') == 2 and script.count(DEBUG_START) == 1
    start = script.find(DEBUG_START)
    end = script.find(DEBUG_END, start)
    assert 0 < end - start < 1024
    return script[:start] + script[end:]


def build(source, mutations=SAVE_UNBLOCK):
    assert hashlib.sha256(source).hexdigest() == EXPECTED, 'Unsupported map'
    offset = source.find(b'MPQ\x1a')
    assert offset == 512
    mpq = source[offset:]
    archive, index, script = read_script(mpq)
    changed = script
    for mutation in mutations:
        if mutation == 'drop-timer-debug':
            changed = drop_timer_debug(changed)
            continue
        if callable(mutation):
            changed = mutation(changed)
            continue
        old, new = mutation
        assert changed.count(old) == 1, old
        changed = changed.replace(old, new)
    key = archive._hash('war3map.j', 'TABLE')
    sector = b'\x02' + zlib.compress(changed, 9)
    raw = encrypt(archive, struct.pack('<2I', 8, 8 + len(sector)), (key - 1) & 0xFFFFFFFF)
    raw += encrypt(archive, sector, key)
    result = bytearray(mpq)
    entries = list(archive.block_table)
    original_entry = entries[index]
    # Keep the archive below Warcraft 1.26a's LAN map size ceiling. Do not
    # append a second script: the changed compressed sector fits its old span.
    assert len(raw) <= original_entry.archived_size
    result[original_entry.offset:original_entry.offset + len(raw)] = raw
    entries[index] = original_entry._replace(archived_size=len(raw), size=len(changed))
    table = b''.join(struct.pack('<4I', *entry) for entry in entries)
    table_offset = archive.header['block_table_offset']
    result[table_offset:table_offset + len(table)] = encrypt(archive, table, archive._hash('(block table)', 'TABLE'))
    check, _, decoded = read_script(bytes(result))
    assert decoded == changed
    assert check.hash_table == archive.hash_table
    assert all(before == after for i, (before, after) in enumerate(zip(archive.block_table, check.block_table)) if i != index)
    return source[:offset] + result


if __name__ == '__main__':
    version = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    destination = SOURCE.with_name(f'LoD State Probe {version}.w3x')
    result = build(SOURCE.read_bytes(), PROBES[version])
    with destination.open('xb') as output:
        output.write(result)
    print(destination)
    print('sha256', hashlib.sha256(result).hexdigest())
    print('Verified: script round-trip; other MPQ entries unchanged; source untouched.')
