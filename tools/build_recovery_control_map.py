"""Minimal two-hero control fixture in the pinned lab map's existing archive.

No LoD bootstrap, native memory access, periodic triggers, or load callbacks.
Used only to distinguish engine checkpoint normalization from LoD callbacks.
The original map and its archive members other than war3map.j are untouched.
"""
from pathlib import Path
import sys
import hashlib
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native import build_state_probe_map as probe

SCRIPT = b'''globals
endglobals
function main takes nothing returns nothing
local unit a
local unit b
call SetMapFlag(MAP_FOG_HIDE_TERRAIN,false)
call SetMapFlag(MAP_FOG_MAP_EXPLORED,true)
call SetFloatGameState(GAME_STATE_TIME_OF_DAY,12.)
call SetPlayerState(Player(1),PLAYER_STATE_RESOURCE_GOLD,5000)
call SetPlayerState(Player(7),PLAYER_STATE_RESOURCE_GOLD,5000)
set a=CreateUnit(Player(1),'Hpal',-1000.,0.,0.)
set b=CreateUnit(Player(7),'Hamg',1000.,0.,180.)
if GetLocalPlayer()==Player(1) then
call PanCameraToTimed(-1000.,0.,0.)
call SelectUnit(a,true)
elseif GetLocalPlayer()==Player(7) then
call PanCameraToTimed(1000.,0.,0.)
call SelectUnit(b,true)
endif
set a=null
set b=null
endfunction
'''


def control_script(original):
    # Keep the original slot/colour/race contract used by war3map.w3i and GHost.
    setup = b'\n'.join(re.search(rb'function '+name+rb' takes.*?endfunction', original, re.S).group(0)
                       for name in (b'InitCustomTeams', b'config'))
    return SCRIPT + setup + b'\n'


if __name__ == '__main__':
    source = probe.SOURCE.read_bytes()
    result = probe.build(source, [control_script])
    target = probe.ROOT / 'runtime/native/Checkpoint Engine Control.w3x'
    target.write_bytes(result)
    (target.parent/'control.j').write_bytes(probe.read_script(result[512:])[2])
    print(target, hashlib.sha256(result).hexdigest())
