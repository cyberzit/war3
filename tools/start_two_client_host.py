"""Start a loopback-only, isolated two-client baseline host (no rejoin claims)."""
from pathlib import Path
import sys
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.recovery_manager import AegisEngine, execute_admin_commands

game = ROOT / 'runtime' / 'two-client-lab' / 'A'
engine = AegisEngine(game)
engine.runtime_dir = ROOT / 'runtime' / 'two-client-lab' / 'host'
engine.prepare_runtime(game / 'Maps' / 'Download' / 'DotA LoD 6.85m Aegis.w3x', owner_name='ZEV')
for name in ('msvcp100.dll', 'msvcr100.dll'):
    shutil.copy2(ROOT / 'runtime' / 'host' / name, engine.runtime_dir / name)
cfg = engine.runtime_dir / 'ghost.cfg'
cfg.write_text(cfg.read_text().replace('bot_bindaddress = 0.0.0.0', 'bot_bindaddress = 127.0.0.1')
               .replace('udp_broadcasttarget = 127.0.0.99', 'udp_broadcasttarget = 127.0.0.1'))
(engine.runtime_dir / 'motd.txt').write_text('Local autosave experiment. Crash rejoin is NOT implemented.\n')
engine.start_host_process()
execute_admin_commands(['!map lod', '!pubby ZEV Autosave Lab'])
(engine.runtime_dir / 'process.json').write_text(json.dumps({'pid': engine.process.pid}))
print('Local baseline host PID', engine.process.pid)
