"""Dota 2 / CS2 Style Seamless Reconnect Service for Warcraft III LoD 6.85m.

Features:
1. Host server records and buffers all match actions.
2. When a player disconnects or crashes:
   - Game freezes on the pause/lag screen.
   - A countdown timer (3 minutes) begins.
3. When the player re-opens Warcraft III and joins the room:
   - The proxy fast-forwards all recorded match history at high speed.
   - Checksums synchronize.
   - The pause screen disappears and the match seamlessly resumes!
4. If the player fails to return within 3 minutes:
   - The player is dropped and the match continues for remaining players.
"""
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

from recovery_lab.host import create_room, launch, prepare, transfer_owner
from recovery_lab.protocol import join_game
from recovery_lab.proxy import LabProxy


def verify_patches():
    # 1. Check 4GB Patch on war3.exe
    exe = GAME / "war3.exe"
    if exe.is_file() and pefile:
        pe = pefile.PE(str(exe))
        is_laa = bool(pe.FILE_HEADER.Characteristics & 0x0020)
        pe.close()
        if not is_laa:
            print("[Patch] war3.exe 4GB Patch is missing. Applying...")
            data = bytearray(exe.read_bytes())
            pe = pefile.PE(data=data)
            off = pe.FILE_HEADER.get_field_absolute_offset("Characteristics")
            pe.close()
            val = struct.unpack_from("<H", data, off)[0] | 0x0020
            struct.pack_into("<H", data, off, val)
            exe.write_bytes(data)
            print("[Patch] war3.exe 4GB Patch applied.")
        else:
            print("[Patch] war3.exe 4GB Patch (LAA): OK")

    # 2. Check game.dll historical command bypass
    dll = GAME / "game.dll"
    if dll.is_file():
        data = dll.read_bytes()
        off = 0x67e704
        if data[off:off+2] == bytes([0x90, 0xe9]):
            print("[Patch] game.dll Reconnect Action Validation: OK (Patched)")
        else:
            print("[Patch] game.dll needs reconnect patch. Applying...")
            b = bytearray(data)
            b[off] = 0x90
            b[off+1] = 0xe9
            dll.write_bytes(b)
            print("[Patch] game.dll Reconnect Action Validation patched.")


async def assign_owner_task(proxy: LabProxy, player: str):
    while proxy.identity is None and not proxy.ended:
        await asyncio.sleep(0.25)
    if not proxy.ended:
        joined_name = proxy.identity[2].decode("ascii", errors="ignore")
        adv_path = Path("runtime/advertisement.bin")
        if adv_path.is_file():
            await asyncio.to_thread(transfer_owner, adv_path.read_bytes(), joined_name)
            proxy.event("owner_assigned", player=joined_name)
            print(f"[Host] Room ownership assigned to: {joined_name}")



async def run_server(advertisement: bytes, player: str):
    proxy = LabProxy(advertisement)
    # Ensure fast replay parameters
    proxy.first_action_delay = 0.2
    proxy.replay_interval = 0.001
    proxy.replay_window = 32

    owner_task = asyncio.create_task(assign_owner_task(proxy, player))
    try:
        await proxy.run()
    finally:
        owner_task.cancel()
        await asyncio.gather(owner_task, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description="Warcraft III Dota 2 / CS2 Style Reconnect Service")
    parser.add_argument("--player", default="ZEV", help="Your player name in Warcraft III LAN")
    parser.add_argument("--wait-time", type=int, default=10, help="Wait time in minutes (default: 10 minutes)")
    args = parser.parse_args()

    print("==================================================================")
    print("      Warcraft III DotA LoD — Dota 2 / CS2 Style Reconnect        ")
    print("==================================================================")

    # 1. Verify patches
    verify_patches()

    # 2. Prepare GHost++ runtime with Probe 7 map and flexible wait time
    map_file = GAME / "Maps" / "Download" / MAP_NAME
    runtime = prepare(GAME, str(map_file.relative_to(GAME)), wait_time=args.wait_time)

    for dll in ("msvcp100.dll", "msvcr100.dll"):
        dest = runtime / dll
        src = ROOT / "runtime" / "vc2010" / "extracted" / dll
        if not dest.is_file() and src.is_file():
            shutil.copy2(src, dest)

    # 3. Launch GHost++
    process = launch(runtime)
    print("[Host] GHost++ engine started.")

    try:
        time.sleep(1.5)
        if process.poll() is not None:
            raise RuntimeError(f"GHost++ failed to start; see {runtime / 'console.log'}")

        advertisement = create_room("Dota2 Reconnect Lab")
        Path("runtime/advertisement.bin").write_bytes(advertisement)

        print("------------------------------------------------------------------")
        print("  SERVER IS READY! (DOTA 2 / CS2 STYLE)")
        print(f"  Player Name: {args.player}")
        print(f"  Reconnect Wait Time: {args.wait_time} minutes ({args.wait_time * 60} seconds)")
        print("  1. Warcraft III-aa neegeed Local Area Network ruu orno.")
        print("  2. \"[LAB] Dota2 Reconnect Lab\" oroo ruu orno.")
        print("  3. Lobby-d orood chatand: !start force gej bicheed ekhluulne.")
        print("  4. Togloltiin dunduur:")
        print("     - Internet tasrakh, Router untrakh, esvel Fatal Error-oor PC untarval:")
        print(f"       -> Togloom gatsaj (Lag Screen / Pause), {args.wait_time} minut huleene.")
        print("       -> War3-aa dahin neegeed LAN-aas oroo ruugaa dahin orno.")
        print("       -> Server 2-3 secondod buh bichlegiig guitsej unpauslene!")
        print("     - Huleehgui shuud togloomiig urgeljluuleh bol chatand: !drop")
        print(f"     - {args.wait_time} minutad orj irehgui bol toglogch avtomaataar drop hiigdene.")
        print("  Serveriig untraakh bol: Ctrl + C darna uu.")
        print("------------------------------------------------------------------")

        asyncio.run(run_server(advertisement, args.player))

    except KeyboardInterrupt:
        print("\n[Host] Stopping server...")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        print("[Host] Server stopped cleanly.")


if __name__ == "__main__":
    main()
