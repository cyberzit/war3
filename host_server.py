"""Dedicated Warcraft III LoD Host Service with Reconnect and AutoSave Recovery."""
import argparse
import asyncio
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
GAME = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III")
MAP_NAME = "LoD State Probe 7.w3x"

sys.path.insert(0, str(ROOT / "runtime/tooldeps"))
try:
    import pefile
except ImportError:
    pefile = None

from recovery_lab.protocol import Framer, chat, game_info, join_game, packet


def check_and_apply_laa(game_path: Path):
    exe = game_path / "war3.exe"
    if not exe.is_file() or pefile is None:
        return
    data = bytearray(exe.read_bytes())
    pe = pefile.PE(data=data)
    is_laa = bool(pe.FILE_HEADER.Characteristics & 0x0020)
    offset = pe.FILE_HEADER.get_field_absolute_offset("Characteristics")
    pe.close()
    if not is_laa:
        print("[4GB Patch] war3.exe lacks Large Address Aware (LAA). Patching...")
        backup = exe.with_name("war3.exe.backup")
        if not backup.exists():
            shutil.copy2(exe, backup)
            print(f"[4GB Patch] Backup created at: {backup}")
        val = struct.unpack_from("<H", data, offset)[0] | 0x0020
        struct.pack_into("<H", data, offset, val)
        exe.write_bytes(data)
        print("[4GB Patch] war3.exe is now patched to 4GB RAM support!")
    else:
        print("[4GB Patch] war3.exe already has 4GB Patch (LAA) active.")


def prepare_host(game: Path = GAME, map_file: Path | None = None) -> Path:
    if map_file is None:
        map_file = game / "Maps" / "Download" / MAP_NAME
    if not map_file.is_file():
        raise FileNotFoundError(f"Map not found: {map_file}")
    if not (game / "war3.exe").is_file():
        raise FileNotFoundError(f"Warcraft III not found in: {game}")

    upstream = ROOT / "engines" / "ghostplusplus"
    runtime = ROOT / "runtime" / "host"
    runtime.mkdir(parents=True, exist_ok=True)

    for name in ("ghost.exe", "BNCSutil.dll", "libmysql.dll", "zlib1.dll", "language.cfg"):
        shutil.copy2(upstream / name, runtime / name)
    shutil.copy2(upstream / "StormLib" / "storm.dll", runtime / "Storm.dll")

    # Ensure required VC++ 2010 runtime DLLs exist
    vc_src = ROOT / "runtime" / "vc2010" / "extracted"
    for dll in ("msvcp100.dll", "msvcr100.dll"):
        dest = runtime / dll
        if not dest.is_file() and (vc_src / dll).is_file():
            shutil.copy2(vc_src / dll, dest)

    for directory in ("mapcfgs", "replays", "savegames"):
        (runtime / directory).mkdir(exist_ok=True)

    map_path = map_file.relative_to(game.resolve())
    (runtime / "mapcfgs" / "lod.cfg").write_text(
        f"map_path = {map_path}\n"
        f"map_localpath = {map_file.name}\n"
        "map_type =\nmap_speed = 3\nmap_visibility = 4\n"
        "map_observers = 1\nmap_flags = 3\n", encoding="utf-8"
    )

    save_dir = (game / "Save" / "Multiplayer").resolve()
    save_dir.mkdir(parents=True, exist_ok=True)

    (runtime / "ghost.cfg").write_text(
        f"bot_war3path = {game}\n"
        f"bot_mappath = {map_file.parent}\n"
        "bot_tft = 1\n"
        "bot_bindaddress = 0.0.0.0\n"
        "udp_broadcasttarget = 127.0.0.1\n"
        "bot_hostport = 6200\n"
        "bot_reconnect = 1\n"
        "bot_reconnectwaittime = 3\n"
        "bot_autosave = 1\n"
        f"bot_savegamepath = {save_dir}\n"
        "bot_mapcfgpath = mapcfgs\n"
        "bot_defaultmap = lod\n"
        "bot_language = language.cfg\n"
        "bot_log = ghost.log\n"
        "bot_savereplays = 1\n"
        "bot_replaypath = replays\n"
        "bot_maxgames = 1\n"
        "bot_spoofchecks = 0\n"
        "bot_requirespoofchecks = 0\n"
        "bot_autokickping = 0\n"
        "bot_checkmultipleipusage = 0\n"
        "bot_latency = 100\n"
        "bot_synclimit = 50\n"
        "bot_lobbytimelimit = 0\n"
        "bot_votekickallowed = 0\n"
        "admingame_create = 1\n"
        "admingame_port = 6201\n"
        "admingame_password = admin\n"
        "admingame_map = lod\n"
        "lan_war3version = 26\n"
        "replay_war3version = 26\n"
        "replay_buildnumber = 6401\n"
        "db_type = sqlite3\n"
        "db_sqlite3_file = lab.dbs\n"
        "bnet_server =\n", encoding="utf-8"
    )
    return runtime


def discover_admin(port: int = 6201, timeout: float = 10) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 6112))
        sock.settimeout(timeout)
        deadline = time.monotonic() + timeout
        while True:
            sock.settimeout(max(0.01, deadline - time.monotonic()))
            data, _ = sock.recvfrom(65535)
            try:
                if game_info(data)["port"] == port:
                    return data
            except ValueError:
                continue


def create_lan_room(room_name: str = "[LoD] Reconnect & Save Room") -> bytes:
    advertisement = discover_admin(6201)
    info = game_info(advertisement)
    framer = Framer()
    with socket.create_connection(("127.0.0.1", 6201), timeout=5) as sock:
        sock.sendall(join_game(info["counter"], info["key"], "HostAdmin"))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            for data in framer.feed(sock.recv(65535)):
                if data[1] == 1:
                    sock.sendall(packet(0x46, data[4:]))
                if data[1] == 4:
                    slot_size = struct.unpack_from("<H", data, 4)[0]
                    pid = data[6 + slot_size]
                    sock.sendall(chat(pid, "!password admin"))
                    sock.sendall(chat(pid, "!map lod"))
                    sock.sendall(chat(pid, f"!pubby HostAdmin {room_name}"))
                    time.sleep(1.0)
                    # Discover the newly created room advertisement on port 6200
                    return discover_admin(6200, timeout=10)


def broadcast_loop(adv: bytes, stop_flag: list):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not stop_flag[0]:
            try:
                s.sendto(adv, ("255.255.255.255", 6112))
            except Exception:
                pass
            time.sleep(2.5)


def main():
    parser = argparse.ArgumentParser(description="Warcraft III LoD Host Server")
    parser.add_argument("--room", default="[LoD] Reconnect & Save Room", help="Room name displayed in LAN")
    args = parser.parse_args()

    print("==================================================================")
    print("      Warcraft III DotA LoD Host Service (Reconnect & AutoSave)   ")
    print("==================================================================")

    # 1. Check & Apply 4GB Patch
    check_and_apply_laa(GAME)

    # 2. Prepare GHost++ runtime
    runtime = prepare_host(GAME)
    print(f"[Host] Configured with map: {MAP_NAME}")
    print("[Host] Reconnect protection: ENABLED (3 minutes timeout)")
    print("[Host] AutoSave protection: ENABLED (Saves on disconnect)")
    print(f"[Host] SaveGames folder: {GAME / 'Save' / 'Multiplayer'}")

    # 3. Launch GHost++
    console_log = (runtime / "console.log").open("ab")
    process = subprocess.Popen(
        [str(runtime / "ghost.exe"), "ghost.cfg"],
        cwd=runtime,
        stdout=console_log,
        stderr=console_log
    )
    print("[Host] GHost++ engine started.")

    stop_broadcast = [False]
    try:
        time.sleep(1.5)
        if process.poll() is not None:
            raise RuntimeError(f"GHost++ failed to start. See: {runtime / 'console.log'}")

        print(f"[Host] Creating LAN room: \"{args.room}\"...")
        adv = create_lan_room(args.room)

        import threading
        if adv:
            t = threading.Thread(target=broadcast_loop, args=(adv, stop_broadcast), daemon=True)
            t.start()

        print("------------------------------------------------------------------")
        print(f"  SUCCESS! Room created: \"{args.room}\"")
        print("  - Warcraft III-aa neegeed Local Area Network ruu orj oroogoo songono uu.")
        print("  - Naizuud tani Radmin VPN esvel neg suljeenees LAN-aas harna.")
        print("  - Lobby-d orsny daraa togloomoo ekhluulekhdee: !start")
        print("  - Togloltyn dunduur khadgalakhdaa: F10 -> Save Game (Kheden ch udaa bolno)")
        print("  - Serveriig untraakh bol: Ctrl + C darna uu.")
        print("------------------------------------------------------------------")

        while process.poll() is None:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[Host] Stopping GHost++ server...")
    finally:
        stop_broadcast[0] = True
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        console_log.close()
        print("[Host] Server stopped cleanly.")


if __name__ == "__main__":
    main()
