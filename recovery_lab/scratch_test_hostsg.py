import sys
sys.path.insert(0, ".")
import socket
import time
import threading
from pathlib import Path
from core.recovery_manager import AegisEngine, execute_admin_commands
from recovery_lab.protocol import game_info

received = []

def listener():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.99', 6112))
    s.settimeout(6.0)
    t0 = time.time()
    while time.time() - t0 < 6.0:
        try:
            d, a = s.recvfrom(2048)
            received.append(d)
        except Exception:
            pass
    s.close()

th = threading.Thread(target=listener, daemon=True)
th.start()

engine = AegisEngine()
save_file = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III\Save\Multiplayer\test.w3z")
save_name = save_file.stem
replay_name = "GHost++ 2026-10-15 13-05 ariuka (00m59s)"
room_name = "[Restore] ariuka"
owner_name = "ZEV"

engine.stop()
engine.prepare_runtime(Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III\Maps\Download\DotA LoD 6.85m Aegis.w3x"), owner_name=owner_name)
engine.start_host_process()

print("Sending commands...")
execute_admin_commands([
    f"!enforcesg {replay_name}",
    f"!loadsg {save_name}",
    f"!hostsg {room_name}",
    f"!owner {owner_name}"
], admin_name="AegisRestore")

time.sleep(4.0)
engine.stop()
th.join()

print(f"Total packets received on 127.0.0.99:6112: {len(received)}")
for idx, p in enumerate(received):
    try:
        info = game_info(p)
        print(f"Packet {idx}: port={info['port']} name='{info['name']}'")
    except Exception as e:
        print(f"Packet {idx} error: {e}, len={len(p)}")
