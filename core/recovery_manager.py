"""Unified Match & Recovery Manager for Aegis Warcraft III Gaming Platform.

Combines all previously fragmented scripts into a single programmatic engine:
- Environment integrity checks (4GB patch, paths, maps).
- GHost++ host process lifecycle management.
- Normal match hosting with DotA LoD support.
- 1-Click Instant Crash Recovery (!loadsg and !hostsg with latest .w3z).
- Silent Save-Sync server automation.
- Warcraft III client launcher.
"""
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
GAME = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III")
MAPS_DIR = GAME / "Maps" / "Download"
SAVE_DIR = GAME / "Save" / "Multiplayer"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime/tooldeps"))
try:
    import pefile
except ImportError:
    pefile = None

from recovery_lab.protocol import Framer, chat, game_info, join_game, packet
from core.save_sync import SaveSyncHost, get_latest_save, sync_save_from_host


def apply_4gb_patch(game_path: Path = GAME) -> bool:
    exe = game_path / "war3.exe"
    if not exe.is_file() or pefile is None:
        return False
    data = bytearray(exe.read_bytes())
    pe = pefile.PE(data=data)
    is_laa = bool(pe.FILE_HEADER.Characteristics & 0x0020)
    offset = pe.FILE_HEADER.get_field_absolute_offset("Characteristics")
    pe.close()
    if not is_laa:
        backup = exe.with_name("war3.exe.backup")
        if not backup.exists():
            shutil.copy2(exe, backup)
        val = struct.unpack_from("<H", data, offset)[0] | 0x0020
        struct.pack_into("<H", data, offset, val)
        exe.write_bytes(data)
        print("[Aegis] war3.exe 4GB Patch applied successfully.")
        return True
    return False


def set_war3_player_name(player_name: str):
    """Sets local player nickname in registry so War3 joins LAN with this identity."""
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Blizzard Entertainment\Warcraft III\String") as key:
            winreg.SetValueEx(key, "userlocal", 0, winreg.REG_SZ, player_name)
    except Exception:
        pass


def ensure_war3_compatibility(game_path: Path = GAME):
    """Ensures Windows 7 compatibility layer for smooth DirectX 1024x768 execution."""
    exe_path = str(game_path / "war3.exe")
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            try:
                val, _ = winreg.QueryValueEx(key, exe_path)
            except FileNotFoundError:
                val = ""
            if "WIN7RTM" not in val:
                winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, "~ WIN7RTM")
                print("[Aegis] Set WIN7RTM compatibility layer for DirectX 1024x768.")
    except Exception as e:
        print(f"[Aegis] Compatibility layer warning: {e}")


def execute_admin_commands(commands: list[str], admin_name: str = "AegisHost", timeout: float = 6.0):
    """Directly connects to GHost++ admin port 6201, logs in, and executes bot commands."""
    framer = Framer()
    with socket.create_connection(("127.0.0.1", 6201), timeout=timeout) as sock:
        sock.sendall(join_game(1, 0, admin_name))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for data in framer.feed(sock.recv(65535)):
                if data[1] == 1:
                    sock.sendall(packet(0x46, data[4:]))
                if data[1] == 4:
                    slot_size = struct.unpack_from("<H", data, 4)[0]
                    pid = data[6 + slot_size]
                    sock.sendall(chat(pid, "!password admin"))
                    time.sleep(0.15)
                    for cmd in commands:
                        sock.sendall(chat(pid, cmd))
                        time.sleep(0.2)
                    time.sleep(0.5)
                    sock.sendall(packet(0x21, struct.pack("<I", 13)))
                    return


def capture_match_adv(timeout: float = 10.0) -> bytes:
    """Captures the isolated match room advertisement on 127.0.0.99:6112 (filtering out Admin Game)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.99", 6112))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sock.settimeout(max(0.01, deadline - time.monotonic()))
            try:
                data, _ = sock.recvfrom(65535)
                info = game_info(data)
                if info["port"] == 6200 and "Admin" not in info["name"]:
                    return data
            except (socket.timeout, ValueError):
                continue
    raise TimeoutError("Timed out waiting for match room advertisement on port 6200")


def discover_admin(port: int = 6201, timeout: float = 10) -> bytes:
    if port == 6200:
        return capture_match_adv(timeout=timeout)
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


class AegisEngine:
    def __init__(self, game_dir: Path = GAME):
        self.game_dir = game_dir
        self.runtime_dir = ROOT / "runtime" / "host"
        self.process = None
        self.sync_server = None
        self.broadcast_thread = None
        self.trap_sock = None
        self.trap_thread = None
        self.trap_running = False
        self.captured_adv = None
        self.adv_ready = threading.Event()
        self.is_running = False
        self.active_room = None
        self.active_mode = None  # "normal" or "recovered"
        ensure_war3_compatibility(self.game_dir)

    def start_isolation_trap(self):
        """Binds 127.0.0.99:6112 exclusively to absorb GHost Admin Game and duplicate broadcasts."""
        self.stop_isolation_trap()
        self.trap_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.trap_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self.trap_sock.bind(("127.0.0.99", 6112))
        self.trap_running = True
        self.captured_adv = None
        self.adv_ready.clear()

        def trap_loop():
            while self.trap_running and self.trap_sock:
                try:
                    self.trap_sock.settimeout(0.5)
                    data, _ = self.trap_sock.recvfrom(65535)
                    try:
                        info = game_info(data)
                        if info["port"] == 6200 and "Admin" not in info["name"]:
                            self.captured_adv = data
                            self.adv_ready.set()
                    except ValueError:
                        pass
                except (socket.timeout, OSError):
                    pass

        self.trap_thread = threading.Thread(target=trap_loop, daemon=True)
        self.trap_thread.start()

    def stop_isolation_trap(self):
        self.trap_running = False
        if getattr(self, "trap_sock", None):
            try:
                self.trap_sock.close()
            except Exception:
                pass
            self.trap_sock = None
        self.trap_thread = None

    def prepare_runtime(self, map_file: Path, wait_time: int = 10, owner_name: str = "ZEV") -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        upstream = ROOT / "engines" / "ghostplusplus"
        for name in ("ghost.exe", "BNCSutil.dll", "libmysql.dll", "zlib1.dll", "language.cfg"):
            dest = self.runtime_dir / name
            src = upstream / name
            if src.is_file() and (not dest.is_file() or src.stat().st_mtime > dest.stat().st_mtime):
                shutil.copy2(src, dest)
        shutil.copy2(upstream / "StormLib" / "storm.dll", self.runtime_dir / "Storm.dll")

        # Setup MOTD banner with custom site branding
        motd_file = self.runtime_dir / "motd.txt"
        if not motd_file.is_file():
            motd_file.write_text(
                "==========================================\n"
                " Aegis Gaming Platform - DotA LoD Match\n"
                " Website: https://aegis-gaming.mn\n"
                " Auto-Reconnect & Crash Recovery Enabled\n"
                " Commands: !fakeplayer | !swap | !start force\n"
                "==========================================\n",
                encoding="utf-8"
            )

        # Automatically grant owner root admin permissions in SQLite database
        db_file = self.runtime_dir / "lab.dbs"
        if db_file.is_file():
            try:
                import sqlite3
                con = sqlite3.connect(db_file)
                cur = con.cursor()
                cur.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, name TEXT NOT NULL, server TEXT NOT NULL)")
                cur.execute("INSERT OR REPLACE INTO admins (name, server) VALUES (?, '')", (owner_name,))
                cur.execute("INSERT OR REPLACE INTO admins (name, server) VALUES (?, '')", (owner_name.lower(),))
                con.commit()
                con.close()
            except Exception:
                pass

        vc_src = ROOT / "runtime" / "vc2010" / "extracted"
        for dll in ("msvcp100.dll", "msvcr100.dll"):
            dest = self.runtime_dir / dll
            if not dest.is_file() and (vc_src / dll).is_file():
                shutil.copy2(vc_src / dll, dest)

        for directory in ("mapcfgs", "replays", "savegames"):
            (self.runtime_dir / directory).mkdir(exist_ok=True)

        map_path = map_file.relative_to(self.game_dir.resolve())
        (self.runtime_dir / "mapcfgs" / "lod.cfg").write_text(
            f"map_path = {map_path}\n"
            f"map_localpath = {map_file.name}\n"
            "map_type =\nmap_speed = 3\nmap_visibility = 4\n"
            "map_observers = 1\nmap_flags = 3\n", encoding="utf-8"
        )

        save_dir = (self.game_dir / "Save" / "Multiplayer").resolve()
        save_dir.mkdir(parents=True, exist_ok=True)

        (self.runtime_dir / "ghost.cfg").write_text(
            f"bot_war3path = {self.game_dir}\n"
            f"bot_mappath = {map_file.parent}\n"
            "bot_tft = 1\n"
            "bot_bindaddress = 0.0.0.0\n"
            "udp_broadcasttarget = 127.0.0.99\n"
            "bot_hostport = 6200\n"
            "bot_reconnect = 1\n"
            f"bot_reconnectwaittime = {wait_time}\n"
            "bot_autosave = 1\n"
            f"bot_savegamepath = {save_dir}\n"
            "bot_mapcfgpath = mapcfgs\n"
            "bot_defaultmap = lod\n"
            "bot_language = language.cfg\n"
            "bot_motdfile = motd.txt\n"
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
        return self.runtime_dir

    def start_host_process(self):
        if self.process and self.process.poll() is None:
            return
        console_log = (self.runtime_dir / "console.log").open("ab")
        self.process = subprocess.Popen(
            [str(self.runtime_dir / "ghost.exe"), "ghost.cfg"],
            cwd=self.runtime_dir,
            stdout=console_log,
            stderr=console_log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        time.sleep(1.2)
        if self.process.poll() is not None:
            raise RuntimeError(f"GHost++ failed to start. See {self.runtime_dir / 'console.log'}")

    def host_normal_room(self, map_file: Path | None = None, room_name: str = "[Aegis] DotA LoD Match", owner_name: str = "ZEV"):
        self.stop()
        if map_file is None:
            # Prefer Aegis map, fallback to Probe 7 or DotA LoD 6.85m
            for candidate in ("DotA LoD 6.85m Aegis.w3x", "LoD State Probe 7.w3x", "DotA LoD 6.85m.w3x"):
                p = MAPS_DIR / candidate
                if p.is_file():
                    map_file = p
                    break
        if not map_file or not map_file.is_file():
            raise FileNotFoundError("No suitable LoD map found")

        apply_4gb_patch(self.game_dir)
        self.prepare_runtime(map_file, owner_name=owner_name)
        self.start_isolation_trap()
        self.start_host_process()

        # Instruct GHost to host match room via admin interface with player as owner
        execute_admin_commands([
            "!map lod",
            f"!pubby {owner_name} {room_name}",
            f"!owner {owner_name}"
        ], admin_name="AegisHost")

        # Capture newly created room advertisement on port 6200 and broadcast to LAN
        if not self.adv_ready.wait(timeout=10):
            raise TimeoutError("Timed out waiting for match room advertisement on port 6200")
        room_adv = self.captured_adv
        self.start_broadcast_loop(room_adv)

        # Start silent sync server
        self.sync_server = SaveSyncHost(save_dir=SAVE_DIR)
        self.sync_server.set_room_info(room_name, room_adv)
        self.sync_server.start()

        self.is_running = True
        self.active_room = room_name
        self.active_mode = "normal"
        print(f"[Aegis] Normal match room created and broadcasting: {room_name}")

    def host_recovered_match(self, save_file: Path | None = None, room_name: str | None = None, owner_name: str = "ZEV"):
        self.stop()
        if save_file is None:
            save_file = get_latest_save(SAVE_DIR)
        if not save_file or not save_file.is_file():
            raise FileNotFoundError(f"No save file found in {SAVE_DIR} to restore!")

        save_name_no_ext = save_file.stem
        if room_name is None:
            room_name = f"[Restore] {save_name_no_ext[:20]}"

        # Default map for runtime setup
        default_map = MAPS_DIR / "DotA LoD 6.85m Aegis.w3x"
        if not default_map.is_file():
            default_map = MAPS_DIR / "LoD State Probe 7.w3x"
        self.prepare_runtime(default_map, owner_name=owner_name)
        self.start_isolation_trap()
        self.start_host_process()

        # Ensure save file is in the multiplayer save path configured for GHost
        save_dir = (self.game_dir / "Save" / "Multiplayer").resolve()
        save_dir.mkdir(parents=True, exist_ok=True)
        target_save = save_dir / save_file.name
        if save_file.resolve() != target_save.resolve():
            shutil.copy2(save_file, target_save)

        # Locate replay for enforcing player slot layout
        replays_dir = self.runtime_dir / "replays"
        replays_dir.mkdir(parents=True, exist_ok=True)
        replays = list(replays_dir.glob("*.w3g"))
        if not replays:
            # Fallback to warcraft LastReplay.w3g
            wc_replay = self.game_dir / "replay" / "LastReplay.w3g"
            if wc_replay.is_file():
                dest = replays_dir / "LastReplay.w3g"
                shutil.copy2(wc_replay, dest)
                replays = [dest]

        if not replays:
            raise RuntimeError("No replay found to enforce player layout for savegame restoration!")

        save_mtime = save_file.stat().st_mtime
        replays.sort(key=lambda f: abs(f.stat().st_mtime - save_mtime))
        replay_name = replays[0].stem

        # GHost++ requires:
        # 1. !enforcesg <replay> to extract PID-to-player mappings
        # 2. !loadsg <savegame> to parse the .w3z savegame state and slots
        # 3. !hostsg <room_name> (the only GHost command that sets saveGame=true and MAPGAMETYPE_SAVEDGAME)
        # 4. !owner <owner_name> to grant lobby host privileges
        admin_cmds = [
            f"!enforcesg {replay_name}",
            f"!loadsg {save_name_no_ext}",
            f"!hostsg {room_name}",
            f"!owner {owner_name}"
        ]
        execute_admin_commands(admin_cmds, admin_name=owner_name)

        # Capture newly created restored room advertisement on port 6200 and broadcast to LAN
        if not self.adv_ready.wait(timeout=10):
            raise TimeoutError("Timed out waiting for match room advertisement on port 6200")
        room_adv = self.captured_adv
        self.start_broadcast_loop(room_adv)

        # Start silent sync server so other players can fetch the save
        self.sync_server = SaveSyncHost(save_dir=SAVE_DIR)
        self.sync_server.set_room_info(room_name, room_adv)
        self.sync_server.start()

        self.is_running = True
        self.active_room = room_name
        self.active_mode = "recovered"
        print(f"[Aegis] RESTORED match room created from save: {save_file.name}")
        print(f"[Aegis] Room Name: {room_name}")

        # Start background watcher to auto-trigger match start as soon as reconnecting player joins
        self._start_auto_start_watcher(owner_name)

    def _start_auto_start_watcher(self, expected_player: str):
        stop_flag = [False]
        self.auto_start_stop_flag = stop_flag

        def watcher():
            log_file = self.runtime_dir / "ghost.log"
            if not log_file.is_file():
                return
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                t0 = time.time()
                while not stop_flag[0] and (time.time() - t0 < 90):
                    line = f.readline()
                    if not line:
                        time.sleep(0.3)
                        continue
                    if "player [" in line and "joined the game" in line and (expected_player.lower() in line.lower()):
                        print(f"[Aegis] Reconnecting player '{expected_player}' recognized in lobby! Triggering auto-start...")
                        # Give Warcraft 3 1.8 seconds to complete lobby handshake
                        time.sleep(1.8)
                        if stop_flag[0]:
                            return
                        from core.war3_navigator import auto_send_lobby_start
                        auto_send_lobby_start()
                        print("[Aegis] Auto-start command sent to lobby!")
                        return

        th = threading.Thread(target=watcher, daemon=True)
        th.start()
        return th

    def start_broadcast_loop(self, adv: bytes):
        self.stop_broadcast()
        self.broadcast_stop_flag = [False]
        self.broadcast_thread = threading.Thread(
            target=self._broadcast_worker,
            args=(adv, self.broadcast_stop_flag),
            daemon=True
        )
        self.broadcast_thread.start()

    def _broadcast_worker(self, adv: bytes, stop_flag: list):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while not stop_flag[0]:
                try:
                    s.sendto(adv, ("127.0.0.1", 6112))
                except Exception:
                    pass
                try:
                    s.sendto(adv, ("255.255.255.255", 6112))
                except Exception:
                    pass
                time.sleep(1.5)

    def stop_broadcast(self):
        if hasattr(self, "broadcast_stop_flag") and self.broadcast_stop_flag:
            self.broadcast_stop_flag[0] = True
        self.broadcast_thread = None

    def launch_war3(self, auto_join: bool = True, player_name: str | None = None):
        war3_exe = self.game_dir / "war3.exe"
        if not war3_exe.is_file():
            raise FileNotFoundError(f"war3.exe not found in {self.game_dir}")
        if player_name:
            set_war3_player_name(player_name)
        subprocess.Popen([str(war3_exe)], cwd=self.game_dir)
        print(f"[Aegis] Warcraft III launched in native fullscreen (Player: {player_name or 'Default'}).")
        if auto_join:
            try:
                from core.war3_navigator import launch_auto_join_thread
                launch_auto_join_thread(delay=1.0)
            except Exception as e:
                print(f"[Aegis] Auto-join warning: {e}")

    def stop(self):
        if hasattr(self, "auto_start_stop_flag") and self.auto_start_stop_flag:
            self.auto_start_stop_flag[0] = True
        self.stop_broadcast()
        self.stop_isolation_trap()
        if self.sync_server:
            self.sync_server.stop()
            self.sync_server = None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except Exception:
                self.process.kill()
            self.process = None
        try:
            subprocess.run(["taskkill", "/f", "/im", "ghost.exe"], capture_output=True)
        except Exception:
            pass
        self.is_running = False
        self.active_room = None
        self.active_mode = None
        print("[Aegis] Engine stopped.")


if __name__ == "__main__":
    engine = AegisEngine()
    print("Testing Aegis Engine host initialization...")
    engine.host_normal_room()
    time.sleep(2)
    engine.stop()
    print("Aegis Engine test completed cleanly.")
