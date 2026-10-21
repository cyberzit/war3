"""Two-Computer Wi-Fi/LAN Crash-Reconnect Live Test Runner.

- Host (Computer 1, 192.168.1.121): Plays as 'ZEV' (Sentinel Slot 1).
- Client (Computer 2 on Wi-Fi): Plays as 'ZEVB' (Scourge Slot 6).
- Serves HTTP Save & Map Sync + AutoSync.cmd on http://192.168.1.121:6205
- Broadcasts single clean LAN room to 127.0.0.1:6113 and 192.168.1.255:6112.
- Aligns 25ms save boundary clock, synchronizes RNG & hero selection, and runs at 1.0x native speed.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from recovery_lab.checkpoint_bridge import (
    AlignmentGate,
    Bridge,
    CheckpointGate,
    LoaderDiscovery,
    Peer,
    REPLAY,
    action_groups,
    admin,
    checkpoint_map_config,
    incoming,
    lag,
    outgoing,
    restore_lobby_seed,
)
from recovery_lab.checkpoint_store import stage_checkpoint
from recovery_lab.protocol import Framer, chat, checksum, game_info, join_identity, packet, redirect_game
from recovery_lab.save_checkpoint import inspect_save

LAB = ROOT / "runtime/two-client-lab"
MAIN_WAR3 = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III")
MAIN_SAVE_DIR = MAIN_WAR3 / "Save/Multiplayer"
LAB_SAVE_DIR = LAB / "A/Save/Multiplayer"
LAB_B_SAVE_DIR = LAB / "B/Save/Multiplayer"
AUTOSYNC_CMD = ROOT / "WAR3_HUULAH_FILES/AutoSync.cmd"
SYNC_MAP_PATH = ROOT / "WAR3_HUULAH_FILES/Maps/Download/LoD_Sync_25.w3x"


def set_nodelay(writer: asyncio.StreamWriter):
    sock = writer.get_extra_info("socket")
    if sock is not None:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass


def get_latest_mr_checkpoint() -> Path | None:
    candidates = []
    for d in (MAIN_SAVE_DIR, LAB_SAVE_DIR, LAB_B_SAVE_DIR):
        if d.is_dir():
            candidates.extend(f for f in d.glob("mr_*.w3z") if f.is_file() and f.stat().st_size > 0)
    if not candidates:
        return None
    candidates.sort(key=lambda f: f.stat().st_mtime_ns, reverse=True)
    return candidates[0]


class LanSaveHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _handle_upload(self):
        client_ip = self.client_address[0]
        if not self.path.startswith("/upload/"):
            self.send_response(404)
            self.end_headers()
            return
        name = Path(self.path[len("/upload/"):]).name
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length) if length > 0 else b""
        if client_ip not in ("127.0.0.1", "192.168.1.121") and name.endswith(".w3z") and len(data) > 0:
            LAB_B_SAVE_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = LAB_B_SAVE_DIR / (name + ".tmp")
            dst_path = LAB_B_SAVE_DIR / name
            tmp_path.write_bytes(data)
            tmp_path.replace(dst_path)
            print(f"[HTTP] {client_ip} uploaded checkpoint {name} ({len(data)} bytes)", flush=True)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_PUT(self):
        self._handle_upload()

    def do_POST(self):
        self._handle_upload()

    def do_GET(self):
        client_ip = self.client_address[0]
        if self.path == "/latest_name":
            latest = get_latest_mr_checkpoint()
            body = ((latest.name + "\r\n") if latest else "").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/AutoSync.cmd" and AUTOSYNC_CMD.is_file():
            data = AUTOSYNC_CMD.read_bytes()
            print(f"[HTTP] {client_ip} downloaded AutoSync.cmd ({len(data)} bytes)", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="AutoSync.cmd"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == "/Game.dll":
            dll_path = ROOT / "WAR3_HUULAH_FILES/Game.dll"
            if dll_path.is_file():
                data = dll_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", 'attachment; filename="Game.dll"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

        if ("LoD_Sync_" in self.path) and SYNC_MAP_PATH.is_file():
            size = SYNC_MAP_PATH.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="LoD_Sync_18.w3x"')
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with SYNC_MAP_PATH.open("rb") as fh:
                while chunk := fh.read(65536):
                    self.wfile.write(chunk)
            return

        if self.path.startswith("/download/"):
            name = Path(self.path[len("/download/"):]).name
            for d in (MAIN_SAVE_DIR, LAB_SAVE_DIR, LAB_B_SAVE_DIR):
                candidate = d / name
                if candidate.is_file() and candidate.suffix.lower() == ".w3z":
                    size = candidate.stat().st_size
                    print(f"[HTTP] {client_ip} downloaded checkpoint {name} ({size} bytes)", flush=True)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                    self.send_header("Content-Length", str(size))
                    self.end_headers()
                    with candidate.open("rb") as fh:
                        while chunk := fh.read(65536):
                            self.wfile.write(chunk)
                    return

        if self.path in ("/", "/index.html"):
            latest = get_latest_mr_checkpoint()
            latest_link = f'<p><a href="/download/{latest.name}">Latest Save: {latest.name}</a></p>' if latest else "<p>No checkpoint yet.</p>"
            html = f"""<!doctype html><html><head><meta charset="utf-8"><title>MongolRanger LAN Sync</title></head>
            <body style="font-family:sans-serif;background:#0f172a;color:#f8fafc;padding:24px;">
            <h2>MongolRanger 2-PC Crash Reconnect Sync</h2>
            <p><a href="/AutoSync.cmd" style="color:#38bdf8;font-size:18px;font-weight:bold;">1. AutoSync.cmd татах (Warcraft III хавтас дотор тавиад ажиллуулна)</a></p>
            {latest_link}
            </body></html>""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        self.send_response(404)
        self.end_headers()


def start_http_sync_server(port: int = 6205):
    MAIN_SAVE_DIR.mkdir(parents=True, exist_ok=True)
    LAB_SAVE_DIR.mkdir(parents=True, exist_ok=True)
    LAB_B_SAVE_DIR.mkdir(parents=True, exist_ok=True)
    for d in (MAIN_SAVE_DIR, LAB_SAVE_DIR, LAB_B_SAVE_DIR):
        for old_f in list(d.glob("mr_*.w3z")) + list(d.glob("bridge_*.w3z")) + list(d.glob("bridge_*.up")):
            try:
                old_f.unlink()
            except OSError:
                pass
    server = ThreadingHTTPServer(("0.0.0.0", port), LanSaveHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def ensure_host_running():
    src_map = SYNC_MAP_PATH
    for sub in ("A", "B"):
        for map_name in ("LoD Reuse Callbacks Probe.w3x", "LoD_Sync_13.w3x", "LoD_Sync_14.w3x", "LoD_Sync_15.w3x", "LoD_Sync_16.w3x", "LoD_Sync_17.w3x", "LoD_Sync_18.w3x", "LoD_Sync_19.w3x", "LoD_Sync_20.w3x", "LoD_Sync_21.w3x", "LoD_Sync_22.w3x", "LoD_Sync_23.w3x", "LoD_Sync_24.w3x", "LoD_Sync_25.w3x"):
            dst_map = LAB / sub / "Maps/Download" / map_name
            dst_map.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_map, dst_map)

    host_dir = LAB / "host"
    cfg_path = host_dir / "ghost.cfg"
    cfg_text = cfg_path.read_text("utf-8")
    if "udp_broadcasttarget = 127.0.0.1" in cfg_text:
        cfg_text = cfg_text.replace("udp_broadcasttarget = 127.0.0.1", "udp_broadcasttarget = 127.0.0.2")
        cfg_path.write_text(cfg_text, "utf-8")

    subprocess.run(["taskkill", "/F", "/IM", "ghost.exe"], capture_output=True)
    time.sleep(0.5)
    log_file = (host_dir / "console.log").open("ab")
    proc = subprocess.Popen(
        [str(host_dir / "ghost.exe"), "ghost.cfg"],
        cwd=host_dir,
        stdout=log_file,
        stderr=log_file,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(1.5)
    return proc


from core.war3_navigator import (
    VK_DOWN,
    VK_J,
    VK_L,
    VK_RETURN,
    ensure_desktop_access,
    find_war3_window,
    get_war3_geometry,
    launch_process_on_default_desktop,
    send_alt_combo,
    send_dual_key,
)

GLOBAL_WAR3_PID = 0


def ensure_local_war3_running():
    global GLOBAL_WAR3_PID
    ensure_desktop_access()
    subprocess.run(
        ["reg", "add", r"HKCU\Software\Blizzard Entertainment\Warcraft III\String", "/v", "userlocal", "/t", "REG_SZ", "/d", "ZEV", "/f"],
        capture_output=True,
    )
    hwnd = find_war3_window()
    if hwnd:
        return hwnd
    lab_dir = LAB / "A"
    # Ensure unique instance mutex in LAB/A/game.dll so any zombie process never blocks startup
    dll_path = lab_dir / "game.dll"
    old_dll = lab_dir / "game.dll.old"
    try:
        data = bytearray( (ROOT / "runtime/native/game-view-probe.dll").read_bytes() )
        idx = data.find(b"Warcraft III Game Application")
        tag = f"W{int(time.time()) % 999:03d}".encode("ascii")
        if idx != -1:
            data[idx:idx + 4] = tag
        struct.pack_into("<H", data, 0x6639FD, 6113)
        struct.pack_into("<H", data, 0x663A02, 6113)
        try:
            old_dll.unlink(missing_ok=True)
        except OSError:
            pass
        if dll_path.exists():
            try:
                dll_path.rename(old_dll)
            except OSError:
                pass
        dll_path.write_bytes(data)
    except Exception:
        pass

    GLOBAL_WAR3_PID = launch_process_on_default_desktop(str(lab_dir / "war3.exe"), "-window", str(lab_dir))
    for _ in range(20):
        time.sleep(0.5)
        hwnd = find_war3_window()
        if hwnd:
            break
    return hwnd


def kill_local_war3():
    """Close the Host PC's frozen Warcraft so it can rejoin the reload lobby fresh."""
    subprocess.run(["taskkill", "/F", "/IM", "war3.exe"], capture_output=True)
    for _ in range(20):
        time.sleep(0.5)
        if not find_war3_window():
            break
    time.sleep(1.0)


async def auto_drive_local_war3(bridge):
    """Automatically navigate Host PC's Warcraft III into LAN -> MongolRanger LoD AR or Rejoin Checkpoint as ZEV."""
    def is_zev_connected():
        p = bridge.peers.get("ZEV")
        return p is not None and p.local is not None

    def worker():
        import ctypes
        from core.war3_navigator import smooth_glide_mouse
        ensure_desktop_access()
        ensure_local_war3_running()
        u = ctypes.windll.user32
        time.sleep(4.5)
        if is_zev_connected():
            return
        hwnd = find_war3_window()
        if not hwnd:
            return

        def activate():
            u.keybd_event(0x12, 0x38, 0, 0)
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
            u.keybd_event(0x12, 0x38, 2, 0)
            time.sleep(0.2)

        def click_at(rx, ry, dbl=False):
            ox, oy, w, h = get_war3_geometry(hwnd)
            sx, sy = ox + int(w * rx), oy + int(h * ry)
            smooth_glide_mouse(sx, sy, duration=0.2, steps=15)
            u.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.06)
            u.mouse_event(0x0004, 0, 0, 0, 0)
            if dbl:
                time.sleep(0.08)
                u.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.06)
                u.mouse_event(0x0004, 0, 0, 0, 0)

        activate()
        send_dual_key(hwnd, 0x1C, VK_RETURN)
        time.sleep(0.6)
        click_at(0.72, 0.39)
        time.sleep(0.15)
        send_dual_key(hwnd, 0x26, VK_L)
        time.sleep(2.5)

        for _ in range(1, 8):
            if is_zev_connected():
                return
            activate()
            click_at(0.25, 0.35, dbl=True)
            time.sleep(0.4)
            if is_zev_connected():
                return
            click_at(0.25, 0.45, dbl=True)
            time.sleep(0.4)
            if is_zev_connected():
                return
            send_dual_key(hwnd, 0x50, VK_DOWN, extended=True)
            time.sleep(0.15)
            send_alt_combo(hwnd, 0x24, VK_J)
            time.sleep(0.4)
            if is_zev_connected():
                return
            send_dual_key(hwnd, 0x1C, VK_RETURN)
            time.sleep(1.2)

    await asyncio.to_thread(worker)
    if is_zev_connected():
        bridge.event("local_war3_auto_joined")


class LanBridge(Bridge):
    def __init__(self, checkpoint="nativehost", replay=REPLAY, fresh_map="lodsync25"):
        super().__init__(checkpoint=checkpoint, replay=replay, fresh_map=fresh_map)
        self.bcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.bcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.last_advertised_counter = None
        self.last_tick_time = 0.0
        self.lag_active_since = 0.0
        self.hero_nt_parts = {}
        self.latest_tag = {}
        self.paired_tags = {}
        self.tag_map = {}
        self.pos_sync_count = 0

    def reset_nettag_maps(self):
        self.hero_nt_parts.clear()
        self.latest_tag.clear()
        self.paired_tags.clear()
        self.tag_map.clear()
        self.pos_sync_count = 0

    def extract_and_strip_hero_nt(self, peer_name: str, raw_body: bytes) -> bytes:
        prefix = b"\x6bdr.x\x00"
        if prefix not in raw_body:
            return raw_body
        pos = 0
        while pos < len(raw_body):
            idx = raw_body.find(prefix, pos)
            if idx == -1:
                break
            mkey_start = idx + len(prefix)
            mkey_end = raw_body.find(b"\x00", mkey_start)
            if mkey_end == -1:
                break
            key_start = mkey_end + 1
            key_end = raw_body.find(b"\x00", key_start)
            if key_end == -1 or key_end + 5 > len(raw_body):
                break
            mkey = raw_body[mkey_start:mkey_end].decode("ascii", errors="replace")
            key_str = raw_body[key_start:key_end].decode("ascii", errors="replace")
            val = struct.unpack_from("<I", raw_body, key_end + 1)[0]
            pos = key_end + 5
            if mkey.startswith("S") and key_str == "P" and val > 0:
                self.pos_sync_count += 1
                if self.pos_sync_count % 15 == 1:
                    sx = (val // 65536) - 16384
                    sy = (val % 65536) - 16384
                    self.event("hero_pos_sync", peer=peer_name, hero=mkey, x=sx, y=sy)
                continue
            if not (mkey.startswith("NT") or mkey.startswith("I")):
                continue
            parts = self.hero_nt_parts.setdefault((peer_name, mkey), {})
            parts[key_str] = val
            if "1" in parts and "2" in parts:
                tag_bytes = struct.pack("<II", parts.pop("1"), parts.pop("2"))
                self.latest_tag[(peer_name, mkey)] = tag_bytes
                for other_name in self.peers:
                    if other_name == peer_name:
                        continue
                    other_tag = self.latest_tag.get((other_name, mkey))
                    if other_tag:
                        self.tag_map.setdefault((peer_name, other_name), {})[tag_bytes] = other_tag
                        self.tag_map.setdefault((other_name, peer_name), {})[other_tag] = tag_bytes
                        pair_key = (mkey, tuple(sorted((peer_name, other_name))))
                        pair_val = (
                            self.latest_tag.get((pair_key[1][0], mkey)),
                            self.latest_tag.get((pair_key[1][1], mkey)),
                        )
                        if self.paired_tags.get(pair_key) != pair_val:
                            self.paired_tags[pair_key] = pair_val
                            self.event(
                                "hero_nettag_mapped",
                                slot=mkey,
                                peer_a=pair_key[1][0],
                                tag_a=pair_val[0].hex(),
                                peer_b=pair_key[1][1],
                                tag_b=pair_val[1].hex(),
                                same=(pair_val[0] == pair_val[1]),
                            )
        return raw_body

    def translate_nettags(self, sender_name: str, target_name: str, body: bytes) -> bytes:
        if sender_name == target_name or not body:
            return body
        mapping = self.tag_map.get((sender_name, target_name))
        if not mapping:
            return body
        out = body
        for src_tag, dst_tag in mapping.items():
            if src_tag != dst_tag and src_tag in out:
                out = out.replace(src_tag, dst_tag)
        return out

    def datagram_received(self, data, address):
        if address[0] not in ("127.0.0.1", "127.0.0.2", "127.0.0.3"):
            return
        try:
            info = game_info(data)
        except ValueError:
            return
        if info["port"] not in (6200, 6300):
            return
        self.ads[info["port"]] = data

    async def advertise(self):
        targets = [
            ("127.0.0.1", 6113),
            ("192.168.1.121", 6112),
            ("192.168.1.255", 6112),
            ("255.255.255.255", 6112),
        ]
        while True:
            port = 6300 if self.phase in ("WAITING", "LOADING") else 6200
            if port in self.ads and self.phase in ("LOBBY", "WAITING", "LOADING"):
                info = game_info(self.ads[port])
                cur_counter = info["counter"]
                if self.last_advertised_counter is not None and self.last_advertised_counter != cur_counter:
                    dec = packet(0x33, struct.pack("<I", self.last_advertised_counter))
                    for tgt in targets:
                        try:
                            self.bcast_sock.sendto(dec, tgt)
                        except OSError:
                            pass
                self.last_advertised_counter = cur_counter
                ad = redirect_game(self.ads[port], 6210)
                for tgt in targets:
                    try:
                        self.bcast_sock.sendto(ad, tgt)
                    except OSError:
                        pass
            elif self.last_advertised_counter is not None and self.phase not in ("LOBBY", "WAITING", "LOADING"):
                dec = packet(0x33, struct.pack("<I", self.last_advertised_counter))
                for tgt in targets:
                    try:
                        self.bcast_sock.sendto(dec, tgt)
                    except OSError:
                        pass
                self.last_advertised_counter = None
            await asyncio.sleep(1)

    async def auto_swap_zevb_to_scourge(self, start_game=True):
        await asyncio.sleep(0.5)
        if self.phase == "LOBBY":
            try:
                cmds = ["!swap 2 6"]
                if start_game and {"ZEV", "ZEVB"}.issubset(self.peers.keys()):
                    cmds.append("!start force")
                await admin(6201, cmds)
                self.event("auto_swapped_and_started", commands=cmds)
            except Exception as exc:
                self.event("auto_swap_warning", detail=str(exc))

    async def start_loader(self):
        for _ in range(80):
            await asyncio.sleep(0.25)
            rep = self.peers.get(self.absent)
            if rep and getattr(rep, "map_ready", False):
                break
        await asyncio.sleep(1.0)
        if self.helper_peer is not None and self.absent != "ZEV":
            self.helper_peer.write(chat(self.helper_pid, "!start force"))
            await self.helper_peer.drain()
        rep = self.peers.get(self.absent)
        if rep is not None and rep.remote is not None and rep.pid:
            try:
                rep.remote.write(chat(rep.pid, "!start force"))
                await rep.remote.drain()
            except Exception:
                pass
        try:
            await admin(6301, ["!start force"])
        except Exception:
            pass
        self.event("loader_start_requested")

    async def verify(self):
        self.lag_active_since = 0.0
        await asyncio.sleep(0.3)
        if self.phase != "LOADING":
            return
        replacement = self.peers[self.absent]
        expected = {p.pid for p in self.peers.values()}
        if not expected.issubset(getattr(replacement, "loaded_pids", set())):
            raise ValueError("Loader has not confirmed all participant identities ready")

        end = time.monotonic() + 10
        # Complete the 25ms remainder of the save turn first (matching survivor's exact step order)
        target_checks = replacement.checks + 1
        self.event("replacement_clock_align_sent", milliseconds=25)
        replacement.frames += 1
        await self.send(replacement, incoming(milliseconds=25))
        while replacement.checks < target_checks:
            if time.monotonic() > end:
                raise TimeoutError("Clock alignment acknowledgment missing")
            await asyncio.sleep(0.02)

        for tail in self.boundary_tail:
            self.event("replacement_boundary_sent", original=tail.hex(), milliseconds=100)
            replacement.frames += 1
            await self.send(replacement, incoming(milliseconds=100))

        target_checks += len(self.boundary_tail)
        while replacement.checks < target_checks or any(
            p.checks < p.frames for p in self.peers.values() if p is not replacement
        ):
            if time.monotonic() > end:
                raise TimeoutError("Boundary simulation acknowledgment missing")
            await asyncio.sleep(0.02)

        self.phase = "VERIFYING"
        self.gate = CheckpointGate(self.peers)
        survivor = next(p for n, p in self.peers.items() if n != self.absent)
        await self.send(survivor, lag(self.peers[self.absent].pid, False))
        self.event("first_post_checkpoint_comparison_started", milliseconds=100)
        self.last_tick_time = time.monotonic()
        for peer in self.peers.values():
            peer.frames = peer.checks + 1
            await self.send(peer, incoming(milliseconds=100))

    async def next_tick(self):
        # Account for Wi-Fi RTT already spent waiting for 0x27 acks so game speed stays 1.0x (10 ticks/sec)
        elapsed = time.monotonic() - self.last_tick_time
        wait_sec = 0.095 - elapsed
        if wait_sec > 0.002:
            await asyncio.sleep(wait_sec)
        if self.phase != "CONTINUING":
            return
        raw_groups = []
        for peer in self.peers.values():
            while peer.pending:
                raw_groups.append((peer.name, peer.pid, peer.pending.popleft()))
        if sum(3 + len(b) for _, _, b in raw_groups) > 1400:
            raise ValueError("Lab action batch exceeds single-packet bound")
        self.gate = CheckpointGate(self.peers)
        self.last_tick_time = time.monotonic()
        for target_name, target_peer in self.peers.items():
            translated_groups = []
            for sender_name, sender_pid, body in raw_groups:
                if sender_name != target_name:
                    body = self.translate_nettags(sender_name, target_name, body)
                if body:
                    translated_groups.append((sender_pid, body))
            target_peer.frames += 1
            await self.send(target_peer, incoming(translated_groups, 100))

    async def accept(self, reader, writer):
        set_nodelay(writer)
        peer = None
        replacement = False
        framer = Framer()
        peer_ip = writer.get_extra_info("peername")[0]
        try:
            while chunk := await reader.read(65535):
                for p in framer.feed(chunk):
                    if peer is None:
                        counter, key, raw_name = join_identity(p)
                        name = raw_name.decode("ascii", errors="replace")
                        replacement = self.phase == "WAITING" and name == self.absent
                        port = 6300 if replacement else 6200
                        info = game_info(self.ads[port])
                        if (counter, key) != (info["counter"], info["key"]):
                            raise ValueError("Wrong lobby identity")
                        if not name or (not replacement and self.phase != "LOBBY"):
                            raise ValueError(f"Unexpected join from {name!r} ({peer_ip}) in phase {self.phase}")
                        if name in self.peers and not replacement:
                            raise ValueError("Participant already connected")
                        remote_reader, remote = await asyncio.open_connection("127.0.0.1", port)
                        set_nodelay(remote)
                        old = self.peers.get(name)
                        peer = Peer(name, writer, remote, pid=old.pid if old else 0)
                        self.peers[name] = peer
                        if replacement:
                            self.phase = "LOADING"
                        peer.upstream_task = self.spawn(self.host_packets(peer, remote_reader, replacement))
                        remote.write(p)
                        await remote.drain()
                        self.event(
                            "replacement_join" if replacement else "initial_join",
                            name=name,
                            ip=peer_ip,
                        )
                        if replacement:
                            self.spawn(self.start_loader())
                        continue
                    if p[1] == 0x42 and len(p) >= 13:
                        map_bytes = struct.unpack_from("<I", p, 9)[0]
                        expected_bytes = SYNC_MAP_PATH.stat().st_size if SYNC_MAP_PATH.is_file() else 8000000
                        if p[8] == 1 and map_bytes >= expected_bytes:
                            if not getattr(peer, "map_ready", False):
                                peer.map_ready = True
                                self.event("client_map_ready", name=peer.name, replacement=replacement, bytes=map_bytes)
                                if not replacement and peer.name == "ZEVB":
                                    self.spawn(self.auto_swap_zevb_to_scourge(start_game=True))
                        elif not getattr(peer, "logged_dl", False) and not replacement and peer.name == "ZEVB":
                            peer.logged_dl = True
                            self.event("client_downloading_map", name=peer.name, bytes=map_bytes, expected=expected_bytes)
                    if p[1] == 0x46:
                        continue
                    if p[1] == 0x23:
                        peer.loaded = True
                        self.event("client_loaded", name=peer.name, replacement=replacement)
                        if replacement:
                            peer.remote.write(p)
                            await peer.remote.drain()
                            self.spawn(self.verify())
                            continue
                    if p[1] == 0x27:
                        peer.checks += 1
                        if self.phase in ("VERIFYING", "CONTINUING"):
                            result = self.gate.accept(peer.name, checksum(p))
                            self.event("state_check", name=peer.name, value=checksum(p).hex(), result=result)
                            if result is not None:
                                if result is False:
                                    self.event(
                                        "state_check_diff_continuing",
                                        values={k: v.hex() for k, v in self.gate.values.items()},
                                    )
                                self.phase = "CONTINUING"
                                self.spawn(self.next_tick())
                            continue
                    if p[1] == 0x26 and self.phase not in ("LOBBY", "LIVE", "SAVING"):
                        if len(p) < 8 or zlib.crc32(p[8:]) != struct.unpack_from("<I", p, 4)[0]:
                            raise ValueError("Bad player command CRC")
                        cleaned = self.extract_and_strip_hero_nt(peer.name, p[8:])
                        if cleaned:
                            if sum(map(len, peer.pending)) + len(cleaned) > 65535:
                                raise ValueError("Paused player command queue exceeded bound")
                            peer.pending.append(cleaned)
                        self.event("paused_command", name=peer.name, body=p[8:].hex())
                        continue
                    if p[1] == 0x29:
                        self.event("drop_request_ignored", name=peer.name)
                        continue
                    if self.phase in ("LOBBY", "LIVE", "SAVING") or (replacement and not peer.loaded):
                        peer.remote.write(p)
                        await peer.remote.drain()
            self.event("client_eof", name=peer.name if peer else None)
        except (ConnectionError, OSError, ValueError) as exc:
            self.event("client_error", detail=str(exc), name=peer.name if peer else None)
        finally:
            if peer and self.peers.get(peer.name) is peer:
                peer.local = None
                peer.loaded = False
                if self.phase == "LIVE":
                    self.absent = peer.name
                    self.phase = "SAVING"
                    self.reset_nettag_maps()
                    self.save_name = "bridge_" + str(int(time.time()))
                    self.save_action = b"\x06" + self.save_name.encode() + b".w3z\0"
                    self.boundary_tail.clear()
                    try:
                        peer.remote.write(outgoing(self.save_action))
                        await peer.remote.drain()
                        self.event("checkpoint_requested", name=self.save_name, absent=self.absent)
                    except (ConnectionError, OSError) as exc:
                        self.phase = "FAILED"
                        self.event("checkpoint_request_failed", detail=str(exc), absent=self.absent)
                elif self.phase in ("VERIFYING", "CONTINUING"):
                    survivor = next((p for n, p in self.peers.items() if n != peer.name and p.local is not None), None)
                    if survivor is not None:
                        self.absent = peer.name
                        self.phase = "FROZEN"
                        self.reset_nettag_maps()
                        self.save_name = "bridge_" + str(int(time.time()))
                        self.save_action = b"\x06" + self.save_name.encode() + b".w3z\0"
                        self.boundary_tail.clear()
                        survivor.frames = survivor.checks + 1
                        await self.send(survivor, incoming([(peer.pid, self.save_action)], 100))
                        self.deadline = time.monotonic() + 180
                        self.event(
                            "checkpoint_requested_continuing",
                            name=self.save_name,
                            absent=self.absent,
                            survivor=survivor.name,
                        )
                        self.spawn(self.prepare_loader(survivor))
                    else:
                        self.phase = "FAILED"
                        self.event("no_survivor_available", name=peer.name)
                elif self.phase == "LOBBY":
                    self.peers.pop(peer.name, None)
                    try:
                        peer.remote.close()
                    except Exception:
                        pass
                    self.event("client_left_lobby", name=peer.name)
                elif replacement and self.phase in ("WAITING", "LOADING"):
                    self.phase = "WAITING"
                    self.event("replacement_retry_ready", name=peer.name)
                elif self.phase not in ("SAVING", "FROZEN", "WAITING"):
                    self.phase = "FAILED"
                    self.event("client_left_during_recovery", name=peer.name)
            writer.close()

    async def prepare_loader(self, survivor):
        # 1. Wait for survivor to finish writing the .w3z file and emit 0701000000 into survivor.pending
        wait_end = time.monotonic() + 15.0
        while time.monotonic() < wait_end:
            if any(b"\x07\x01\0\0\0" in cmd for cmd in survivor.pending):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.1)

        # 2. Immediately send the post-save boundary (0x07) and lag(absent.pid, True)
        #    so the "Waiting for players..." dialog pops up immediately on survivor's screen
        #    and LRSV executes on survivor to upload bridge_*.w3z if survivor is on PC2!
        groups = [(self.peers[self.absent].pid, b"\x07\x01\0\0\0")]
        while survivor.pending:
            groups.append((survivor.pid, survivor.pending.popleft()))
        tail = incoming(groups, 100)
        self.boundary_tail.append(tail)
        survivor.frames += 1
        await self.send(survivor, tail)
        self.lag_active_since = time.monotonic()
        await self.send(survivor, lag(self.peers[self.absent].pid, True))
        self.event("survivor_waiting_dialog_shown", survivor=survivor.name, absent=self.absent)

        # 3. Wait for bridge_<timestamp>.w3z to be available locally or uploaded from PC2
        candidates = [
            MAIN_SAVE_DIR / (self.save_name + ".w3z"),
            LAB / "A/Save/Multiplayer" / (self.save_name + ".w3z"),
            LAB / "B/Save/Multiplayer" / (self.save_name + ".w3z"),
        ]
        end = time.monotonic() + 30.0
        previous = None
        source = None
        while time.monotonic() < end:
            for c in candidates:
                if c.exists():
                    source = c
                    break
            if source and source.exists():
                stat = (source.stat().st_size, source.stat().st_mtime_ns)
                if stat == previous and stat[0] > 0 and survivor.checks >= survivor.frames:
                    target = await asyncio.to_thread(stage_checkpoint, source, LAB / "B/Save/Multiplayer")
                    await asyncio.to_thread(stage_checkpoint, source, LAB / "A/Save/Multiplayer")
                    await asyncio.to_thread(stage_checkpoint, source, MAIN_SAVE_DIR)
                    break
                previous = stat
            await asyncio.sleep(0.25)
        else:
            raise TimeoutError(f"Checkpoint/ack not complete: frames={survivor.frames}, checks={survivor.checks}")

        await self.setup_loader(target)

    async def maintain_wait(self):
        while True:
            await asyncio.sleep(1.0)
            lag_since = getattr(self, "lag_active_since", 0.0)
            if (
                lag_since > 0.0
                and (time.monotonic() - lag_since) >= 25.0
                and self.absent
                and self.phase in ("FROZEN", "WAITING")
                and not getattr(self.peers.get(self.absent), "loaded", False)
            ):
                self.lag_active_since = time.monotonic()
                for peer in list(self.peers.values()):
                    if peer.local is not None and peer.loaded and peer.name != self.absent:
                        other = self.peers[self.absent]
                        await self.send(peer, lag(other.pid, False))
                        await self.send(peer, lag(other.pid, True))
                self.event(
                    "wait_connection_refreshed",
                    peers={
                        n: {"frames": p.frames, "checks": p.checks, "connected": p.local is not None}
                        for n, p in self.peers.items()
                    },
                )

    async def setup_loader(self, target):
        if self.helper and self.helper.poll() is None:
            self.helper.terminate()
            try:
                await asyncio.to_thread(self.helper.wait, 5)
            except Exception:
                pass
        self.helper_peer = None
        self.ads.pop(6300, None)
        self.loader_seed = inspect_save(target)["random_seed"]
        self.event("loader_checkpoint_seed", value=self.loader_seed)
        helper = LAB / "loader-host"
        helper.mkdir(exist_ok=True)
        base = LAB / "host"
        for name in ("ghost.exe", "BNCSutil.dll", "libmysql.dll", "zlib1.dll", "Storm.dll", "msvcp100.dll", "msvcr100.dll", "language.cfg"):
            try:
                shutil.copy2(base / name, helper / name)
            except OSError:
                pass
        for name in ("mapcfgs", "replays"):
            shutil.copytree(base / name, helper / name, dirs_exist_ok=True)
        config = (
            (base / "ghost.cfg").read_text()
            .replace("bot_hostport = 6200", "bot_hostport = 6300")
            .replace("admingame_port = 6201", "admingame_port = 6301")
            .replace("bot_reconnect = 1", "bot_reconnect = 0")
        )
        (helper / "ghost.cfg").write_text(config)
        with (helper / "console.log").open("ab") as output:
            self.helper = subprocess.Popen(
                [str(base / "ghost.exe"), "ghost.cfg"],
                cwd=helper,
                stdout=output,
                stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        await asyncio.sleep(1)
        map_config = await asyncio.to_thread(checkpoint_map_config, target, helper / "mapcfgs")
        await admin(6301, ["!load " + map_config, "!enforcesg " + self.replay, "!loadsg " + target.stem, "!hostsg Rejoin Checkpoint"])
        for _ in range(80):
            if 6300 in self.ads:
                break
            await asyncio.sleep(0.5)
        if 6300 not in self.ads:
            raise TimeoutError("Loader lobby advertisement not received")
        self.phase = "WAITING"
        self.deadline = time.monotonic() + 600
        for n in list(self.peers.keys()):
            if n != self.absent:
                self.spawn(self.fake_survivor(n))
        self.event("checkpoint_ready", file=target.name, survivor_process_unchanged=True)
        if self.absent == "ZEV":
            self.spawn(auto_drive_local_war3(self))

    async def run(self):
        loop = asyncio.get_running_loop()
        rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        rx_sock.bind(("127.0.0.2", 6112))
        rx_sock.setblocking(False)
        await loop.create_datagram_endpoint(lambda: self, sock=rx_sock)
        self.loader_transport = self.transport
        server = await asyncio.start_server(self.accept, "0.0.0.0", 6210)
        self.spawn(self.advertise())
        self.spawn(self.controls())
        self.spawn(self.heartbeats())
        self.lag_maintenance_started = True
        self.spawn(self.maintain_wait())
        await admin(6201, ["!load " + self.fresh_map, "!priv MongolRanger LoD AR"])
        self.event("lan_bridge_ready", host_ip="192.168.1.121", port=6210, sync_http="http://192.168.1.121:6205")
        self.spawn(auto_drive_local_war3(self))
        try:
            async with server:
                await server.serve_forever()
        finally:
            for task in list(self.tasks):
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.transport.close()
            self.bcast_sock.close()
            if getattr(self, "loader_transport", None):
                self.loader_transport.close()
            if self.helper and self.helper.poll() is None:
                self.helper.terminate()
            self.log.close()


if __name__ == "__main__":
    ensure_host_running()
    ensure_local_war3_running()
    start_http_sync_server(6205)
    asyncio.run(LanBridge().run())
