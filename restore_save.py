"""Host a Saved Game (AutoSave / Checkpoint) in Warcraft III LAN."""
import argparse
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
SAVE_DIR = GAME / "Save" / "Multiplayer"

from recovery_lab.protocol import Framer, chat, game_info, join_game, packet
from host_server import discover_admin, prepare_host


def list_savegames():
    if not SAVE_DIR.is_dir():
        return []
    files = sorted(SAVE_DIR.glob("*.w3z"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def host_saved_game(save_name_no_ext: str, room_name: str = "[LoD] Restored Match"):
    advertisement = discover_admin(6201)
    info = game_info(advertisement)
    framer = Framer()
    with socket.create_connection(("127.0.0.1", 6201), timeout=5) as sock:
        sock.sendall(join_game(info["counter"], info["key"], "SaveAdmin"))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            for data in framer.feed(sock.recv(65535)):
                if data[1] == 1:
                    sock.sendall(packet(0x46, data[4:]))
                if data[1] == 4:
                    slot_size = struct.unpack_from("<H", data, 4)[0]
                    pid = data[6 + slot_size]
                    sock.sendall(chat(pid, "!password admin"))
                    time.sleep(0.2)
                    sock.sendall(chat(pid, f"!loadsg {save_name_no_ext}"))
                    time.sleep(0.3)
                    sock.sendall(chat(pid, f"!pubby SaveAdmin {room_name}"))
                    time.sleep(0.5)
                    return


def main():
    print("==================================================================")
    print("        Warcraft III LoD Saved Game Recovery (HostSG)             ")
    print("==================================================================")

    saves = list_savegames()
    if not saves:
        print(f"Khavtas dotor .w3z save file oldsongui: {SAVE_DIR}")
        return

    print("Khamgiin suuliin khadgalsan togloomuud:")
    for idx, f in enumerate(saves[:10], 1):
        mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(f.stat().st_mtime))
        print(f" [{idx}] {f.stem}  ({mtime})")

    choice = input("\nAchaalakh Save-iin dugaaryg songono uu (1-10) [Default: 1]: ").strip()
    if not choice:
        choice = "1"

    try:
        selected_file = saves[int(choice) - 1]
    except (ValueError, IndexError):
        print("Buruu dugaar songoson tul tsutsallaa.")
        return

    save_name = selected_file.stem
    room_name = f"[Restore] {save_name[:18]}"
    print(f"\nSongoson Save: {save_name}")
    print(f"Uusgekh oroonii ner: {room_name}")

    # Start host if not already running
    runtime = ROOT / "runtime" / "host"
    runtime = prepare_host(GAME)

    console_log = (runtime / "console.log").open("ab")
    process = subprocess.Popen(
        [str(runtime / "ghost.exe"), "ghost.cfg"],
        cwd=runtime,
        stdout=console_log,
        stderr=console_log
    )

    try:
        time.sleep(1.5)
        print(f"[Host] Loading save game \"{save_name}\" and creating LAN room...")
        host_saved_game(save_name, room_name)
        print("------------------------------------------------------------------")
        print(f"  SUCCESS! Khadgalsan togloom amjilttai uuslee: \"{room_name}\"")
        print("  - Bukh toglogch Warcraft III-aa neegeed LAN tsesnees orno.")
        print("  - Ankh suuj baisan bairandaa (Slot) suukh yostoi.")
        print("  - Bugd orj irsnii daraa togloomoo ekhluulne.")
        print("  - Serveriig untraakh bol: Ctrl + C darna uu.")
        print("------------------------------------------------------------------")

        while process.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Host] Stopping server...")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        console_log.close()
        print("[Host] Server stopped.")


if __name__ == "__main__":
    main()
