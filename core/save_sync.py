"""Silent Save-Sync Microservice for Warcraft III Multiplayer Snapshots.

Host:
- Serves latest .w3z savegame via HTTP on port 6205.
- Broadcasts save availability via UDP on port 6206.

Client:
- Discovers or connects to host.
- Downloads latest .w3z file into Save/Multiplayer/ folder in <0.3s.
- Zero manual file transfers or chat uploads needed.
"""
import asyncio
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socket
import threading
import time
import urllib.request

GAME = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III")
SAVE_DIR = GAME / "Save" / "Multiplayer"
SYNC_PORT_HTTP = 6205
SYNC_PORT_UDP = 6206


def get_latest_save(save_dir: Path = SAVE_DIR) -> Path | None:
    if not save_dir.is_dir():
        return None
    files = [f for f in save_dir.glob("*.w3z") if f.is_file() and f.stat().st_size > 0]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


class SaveRequestHandler(BaseHTTPRequestHandler):
    save_dir = SAVE_DIR
    room_name = None
    room_adv_b64 = None

    def log_message(self, format, *args):
        pass  # Silent logging

    def do_GET(self):
        latest = get_latest_save(self.save_dir)
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "status": "online",
                "room_name": SaveRequestHandler.room_name,
                "room_adv": SaveRequestHandler.room_adv_b64,
                "latest_name": latest.name if latest else None,
                "latest_size": latest.stat().st_size if latest else 0,
                "latest_mtime": latest.stat().st_mtime if latest else 0,
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if self.path in ("/download/latest", "/") and latest and latest.is_file():
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{latest.name}"')
            self.send_header("Content-Length", str(latest.stat().st_size))
            self.end_headers()
            with latest.open("rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
            return

        if self.path.startswith("/download/"):
            target_name = self.path[len("/download/"):]
            target_file = self.save_dir / target_name
            if target_file.is_file() and target_file.suffix.lower() == ".w3z":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(target_file.stat().st_size))
                self.end_headers()
                with target_file.open("rb") as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
                return

        self.send_response(404)
        self.end_headers()


class SaveSyncHost:
    def __init__(self, host: str = "0.0.0.0", port: int = SYNC_PORT_HTTP, save_dir: Path = SAVE_DIR):
        self.host = host
        self.port = port
        self.save_dir = save_dir
        self.httpd = None
        self.thread = None
        self.running = False
        self.udp_thread = None

    def start(self):
        if self.running:
            return
        SaveRequestHandler.save_dir = self.save_dir
        self.httpd = HTTPServer((self.host, self.port), SaveRequestHandler)
        self.running = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.udp_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.udp_thread.start()
        print(f"[SyncServer] Silent save server listening on {self.host}:{self.port}")

    def _broadcast_loop(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while self.running:
                latest = get_latest_save(self.save_dir)
                if latest:
                    msg = json.dumps({
                        "type": "SAVE_ANNOUNCE",
                        "name": latest.name,
                        "size": latest.stat().st_size,
                        "port": self.port
                    }).encode("utf-8")
                    for target in ("255.255.255.255", "127.0.0.1"):
                        try:
                            s.sendto(msg, (target, SYNC_PORT_UDP))
                        except Exception:
                            pass
                time.sleep(3.0)

    def set_room_info(self, room_name: str, room_adv: bytes | None):
        SaveRequestHandler.room_name = room_name
        SaveRequestHandler.room_adv_b64 = base64.b64encode(room_adv).decode("ascii") if room_adv else None

    def stop(self):
        self.running = False
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        print("[SyncServer] Silent save server stopped.")


def get_host_status(host_ip: str = "127.0.0.1", port: int = SYNC_PORT_HTTP) -> dict | None:
    status_url = f"http://{host_ip}:{port}/status"
    try:
        with urllib.request.urlopen(status_url, timeout=3.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[SyncClient] Could not get host status at {status_url}: {e}")
        return None


def sync_save_from_host(host_ip: str = "127.0.0.1", port: int = SYNC_PORT_HTTP, dest_dir: Path = SAVE_DIR) -> Path | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    status_url = f"http://{host_ip}:{port}/status"
    try:
        with urllib.request.urlopen(status_url, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest_name = data.get("latest_name")
            if not latest_name:
                print("[SyncClient] Host reports no save file available yet.")
                return None
    except Exception as e:
        print(f"[SyncClient] Could not contact host at {status_url}: {e}")
        return None

    target_file = dest_dir / latest_name
    download_url = f"http://{host_ip}:{port}/download/latest"
    start_time = time.monotonic()
    try:
        with urllib.request.urlopen(download_url, timeout=10.0) as resp, target_file.open("wb") as out:
            while chunk := resp.read(65536):
                out.write(chunk)
        duration = time.monotonic() - start_time
        print(f"[SyncClient] SUCCESS: Silently downloaded '{latest_name}' ({target_file.stat().st_size} bytes) in {duration:.2f}s")
        return target_file
    except Exception as e:
        print(f"[SyncClient] Failed to download save: {e}")
        return None


class ClientTunnel:
    """Local TCP tunnel and room reflector for friend client across VPN/Internet.
    
    1. Proxies local port 6200 -> Host IP:6200.
    2. Rebroadcasts host's room advertisement to local 127.0.0.1:6112.
    3. Allows Warcraft III LAN browser to instantly see and join remote host.
    """
    def __init__(self, host_ip: str = "127.0.0.1", remote_port: int = 6200, local_port: int = 6200):
        self.host_ip = host_ip
        self.remote_port = remote_port
        self.local_port = local_port
        self.server_sock = None
        self.running = False
        self.broadcast_thread = None
        self.adv_bytes = None

    def start_proxy(self):
        if self.running:
            return
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", self.local_port))
        self.server_sock.listen(10)
        self.running = True

        def accept_loop():
            while self.running:
                try:
                    client, _ = self.server_sock.accept()
                    remote = socket.create_connection((self.host_ip, self.remote_port), timeout=5)
                    threading.Thread(target=self._pipe, args=(client, remote), daemon=True).start()
                    threading.Thread(target=self._pipe, args=(remote, client), daemon=True).start()
                except Exception:
                    break

        threading.Thread(target=accept_loop, daemon=True).start()

    def _pipe(self, src, dst):
        try:
            while self.running:
                data = src.recv(4096)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try: src.close()
            except Exception: pass
            try: dst.close()
            except Exception: pass

    def start_local_broadcast(self, adv: bytes):
        self.adv_bytes = adv
        if self.broadcast_thread and self.broadcast_thread.is_alive():
            return

        def bcast_loop():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                while self.running and self.adv_bytes:
                    try:
                        s.sendto(self.adv_bytes, ("127.0.0.1", 6112))
                    except Exception:
                        pass
                    time.sleep(2.0)

        self.broadcast_thread = threading.Thread(target=bcast_loop, daemon=True)
        self.broadcast_thread.start()

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "client":
        host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        sync_save_from_host(host)
    else:
        server = SaveSyncHost()
        server.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
