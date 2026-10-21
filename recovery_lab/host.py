"""Prepare a LAN-only GHost++ sandbox; the Warcraft installation stays untouched."""
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time

from .protocol import Framer, chat, game_info, join_game, packet, search_game

ROOT = Path(__file__).resolve().parent.parent
GAME = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III")


def prepare(game: Path = GAME, map_relative: str = r"Maps\Download\LoD State Probe 7.w3x", wait_time: int = 10) -> Path:
    map_file = (game / map_relative).resolve()
    map_path = map_file.relative_to(game.resolve())
    if map_file.suffix.lower() != '.w3x' or not map_file.is_file():
        raise ValueError("Expected an existing .w3x map within the game directory")
    upstream = ROOT / "engines" / "ghostplusplus"
    runtime = ROOT / "runtime" / "host"
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("ghost.exe", "BNCSutil.dll", "libmysql.dll", "zlib1.dll", "language.cfg"):
        shutil.copy2(upstream / name, runtime / name)
    shutil.copy2(upstream / "StormLib" / "storm.dll", runtime / "Storm.dll")
    for directory in ("mapcfgs", "replays", "savegames"):
        (runtime / directory).mkdir(exist_ok=True)
    if not map_file.is_file() or not (game / "war3.exe").is_file():
        raise FileNotFoundError("Warcraft III or LoD State Probe 7 is missing")
    (runtime / "mapcfgs" / "lod.cfg").write_text(
        f"map_path = {map_path}\n"
        f"map_localpath = {map_file.name}\n"
        "map_type =\nmap_speed = 3\nmap_visibility = 4\n"
        "map_observers = 1\nmap_flags = 3\n", encoding="utf-8")
    save_path = (game / "Save" / "Multiplayer").resolve()
    save_path.mkdir(parents=True, exist_ok=True)
    (runtime / "ghost.cfg").write_text(
        f"bot_war3path = {game}\n"
        f"bot_mappath = {map_file.parent}\n"
        "bot_tft = 1\nbot_bindaddress = 0.0.0.0\n"
        "udp_broadcasttarget = 127.0.0.1\n"
        "bot_hostport = 6200\nbot_reconnect = 1\n"
        f"bot_reconnectwaittime = {wait_time}\n"
        "bot_autosave = 1\n"
        f"bot_savegamepath = {save_path}\n"
        "bot_mapcfgpath = mapcfgs\nbot_defaultmap = lod\n"
        "bot_language = language.cfg\nbot_log = ghost.log\n"
        "bot_savereplays = 1\nbot_replaypath = replays\n"
        "bot_maxgames = 1\n"
        "bot_spoofchecks = 0\nbot_requirespoofchecks = 0\n"
        "bot_autokickping = 0\nbot_checkmultipleipusage = 0\n"
        "bot_latency = 100\nbot_synclimit = 50\n"
        "bot_lobbytimelimit = 0\nbot_votekickallowed = 0\n"
        "admingame_create = 1\nadmingame_port = 6201\n"
        "admingame_password = local-research-only\nadmingame_map = lod\n"
        "lan_war3version = 26\nreplay_war3version = 26\n"
        "replay_buildnumber = 6401\n"
        "db_type = sqlite3\ndb_sqlite3_file = lab.dbs\n"
        "bnet_server =\n", encoding="utf-8")
    return runtime


def launch(runtime: Path) -> subprocess.Popen:
    out = (runtime / "console.log").open("ab")
    try:
        return subprocess.Popen([str(runtime / "ghost.exe"), "ghost.cfg"],
                                cwd=runtime, stdout=out, stderr=out,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        out.close()


def discover(port: int, timeout: float = 12) -> bytes:
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


def create_room(name: str = "LoD Recovery Lab") -> bytes:
    advertisement = discover(6201)
    info = game_info(advertisement)
    framer = Framer()
    with socket.create_connection(("127.0.0.1", 6201), timeout=3) as sock:
        sock.sendall(join_game(info["counter"], info["key"], "LabAdmin"))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            for data in framer.feed(sock.recv(65535)):
                if data[1] == 1:
                    sock.sendall(packet(0x46, data[4:]))
                if data[1] == 4:
                    slot_size = struct.unpack_from("<H", data, 4)[0]
                    pid = data[6 + slot_size]
                    sock.sendall(chat(pid, "!password local-research-only"))
                    sock.sendall(chat(pid, "!priv " + name))
                    time.sleep(0.3)
                    sock.sendall(packet(0x21, struct.pack("<I", 13)))
                    return discover(6200)
        raise TimeoutError("Admin lobby did not accept the lab controller")


def transfer_owner(advertisement: bytes, owner: str):
    info = game_info(advertisement)
    framer = Framer()
    with socket.create_connection(("127.0.0.1", 6200), timeout=3) as sock:
        sock.sendall(join_game(info["counter"], info["key"], "LabAdmin"))
        while True:
            for data in framer.feed(sock.recv(65535)):
                if data[1] == 4:
                    size = struct.unpack_from("<H", data, 4)[0]
                    sock.sendall(chat(data[6 + size], "!fakeplayer"))
                    sock.sendall(chat(data[6 + size], "!owner " + owner))
                    time.sleep(0.3)
                    sock.sendall(packet(0x21, struct.pack("<I", 13)))
                    return
