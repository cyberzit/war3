"""Direct P2P UDP Hole-Punching Tunnel for Warcraft III 1.26a.

Connects players behind NAT/firewalls directly across the Internet
without third-party VPNs (Radmin/Hamachi).

Architecture:
1. Both Host & Client query public STUN servers to get their mapped public endpoints.
2. Both send UDP punch packets to each other's public endpoints to open firewall states.
3. Once punched, a direct bidirectional UDP stream is established with 0 relay latency.
4. Client exposes local port 6200 (TCP) and 6112 (UDP) on 127.0.0.1.
5. Warcraft III automatically sees the host in LAN and connects seamlessly!
"""
import socket
import struct
import threading
import time
from typing import Callable

PUNCH_MAGIC = b"AEGIS_PUNCH_V1"
DATA_MAGIC = b"AEGIS_DATA_V1"


class P2PHostTunnel:
    def __init__(self, ghost_port: int = 6200, local_udp_port: int = 0):
        self.ghost_port = ghost_port
        self.local_udp_port = local_udp_port
        self.udp_sock = None
        self.running = False
        self.client_endpoints: set[tuple[str, int]] = set()
        self.tcp_connections: dict[tuple[str, int], socket.socket] = {}
        self.lock = threading.Lock()

    def start(self) -> int:
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind(("0.0.0.0", self.local_udp_port))
        self.local_udp_port = self.udp_sock.getsockname()[1]
        self.running = True

        threading.Thread(target=self._udp_listen_loop, daemon=True).start()
        print(f"[P2PHost] Tunnel listening on local UDP port {self.local_udp_port}")
        return self.local_udp_port

    def punch_to_client(self, client_ip: str, client_port: int):
        """Sends initial punch packet to open outbound NAT table entry."""
        if not self.udp_sock:
            return
        target = (client_ip, client_port)
        self.client_endpoints.add(target)
        for _ in range(3):
            try:
                self.udp_sock.sendto(PUNCH_MAGIC, target)
            except Exception:
                pass
            time.sleep(0.05)

    def _udp_listen_loop(self):
        while self.running and self.udp_sock:
            try:
                data, addr = self.udp_sock.recvfrom(65535)
                if not data:
                    continue
                if data == PUNCH_MAGIC:
                    # Connection handshake established!
                    self.client_endpoints.add(addr)
                    self.udp_sock.sendto(b"AEGIS_PUNCH_ACK", addr)
                    continue

                if data.startswith(DATA_MAGIC):
                    # Multiplexed payload from client War3 -> pipe to GHost
                    payload = data[len(DATA_MAGIC):]
                    with self.lock:
                        if addr not in self.tcp_connections:
                            ghost_conn = socket.create_connection(("127.0.0.1", self.ghost_port), timeout=3)
                            self.tcp_connections[addr] = ghost_conn
                            threading.Thread(target=self._ghost_to_client, args=(ghost_conn, addr), daemon=True).start()
                        ghost_conn = self.tcp_connections[addr]

                    try:
                        ghost_conn.sendall(payload)
                    except Exception:
                        with self.lock:
                            self.tcp_connections.pop(addr, None)
            except Exception:
                break

    def _ghost_to_client(self, ghost_sock: socket.socket, client_addr: tuple[str, int]):
        """Pipes GHost's responses back through the P2P UDP tunnel to client."""
        try:
            while self.running:
                chunk = ghost_sock.recv(4096)
                if not chunk:
                    break
                packet = DATA_MAGIC + chunk
                self.udp_sock.sendto(packet, client_addr)
        except Exception:
            pass
        finally:
            with self.lock:
                self.tcp_connections.pop(client_addr, None)
            try:
                ghost_sock.close()
            except Exception:
                pass

    def stop(self):
        self.running = False
        with self.lock:
            for conn in self.tcp_connections.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self.tcp_connections.clear()
        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass
            self.udp_sock = None


class P2PClientTunnel:
    def __init__(self, host_public_ip: str, host_public_port: int, local_tcp_port: int = 6200):
        self.host_target = (host_public_ip, host_public_port)
        self.local_tcp_port = local_tcp_port
        self.udp_sock = None
        self.local_server = None
        self.running = False
        self.active_client_sock: socket.socket | None = None
        self.is_punched = False
        self.tcp_ready = threading.Event()

    def start(self, local_udp_port: int = 0) -> int:
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind(("0.0.0.0", local_udp_port))
        assigned_port = self.udp_sock.getsockname()[1]
        self.running = True

        threading.Thread(target=self._udp_listen_loop, daemon=True).start()
        threading.Thread(target=self._start_local_tcp_server, daemon=True).start()
        self.tcp_ready.wait(timeout=2.0)

        # Punch hole to host
        self.punch()
        return assigned_port

    def punch(self):
        """Sends hole-punching packets to the host's public endpoint."""
        for _ in range(5):
            if not self.running or not self.udp_sock:
                break
            try:
                self.udp_sock.sendto(PUNCH_MAGIC, self.host_target)
            except Exception:
                pass
            time.sleep(0.08)

    def _start_local_tcp_server(self):
        """Binds local port 6200 for War3 to connect into."""
        self.local_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.local_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.local_server.bind(("127.0.0.1", self.local_tcp_port))
        self.local_tcp_port = self.local_server.getsockname()[1]
        self.local_server.listen(5)
        self.tcp_ready.set()

        while self.running:
            try:
                client_sock, _ = self.local_server.accept()
                self.active_client_sock = client_sock
                threading.Thread(target=self._war3_to_host, args=(client_sock,), daemon=True).start()
            except Exception:
                break

    def _war3_to_host(self, client_sock: socket.socket):
        """Takes War3 TCP packets and sends them over P2P UDP to Host."""
        try:
            while self.running:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                packet = DATA_MAGIC + chunk
                self.udp_sock.sendto(packet, self.host_target)
        except Exception:
            pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _udp_listen_loop(self):
        """Receives responses from Host over P2P UDP and sends to local War3 TCP."""
        while self.running and self.udp_sock:
            try:
                data, addr = self.udp_sock.recvfrom(65535)
                if not data:
                    continue
                if data in (PUNCH_MAGIC, b"AEGIS_PUNCH_ACK"):
                    self.is_punched = True
                    continue
                if data.startswith(DATA_MAGIC) and self.active_client_sock:
                    payload = data[len(DATA_MAGIC):]
                    try:
                        self.active_client_sock.sendall(payload)
                    except Exception:
                        pass
            except Exception:
                break

    def broadcast_to_local_war3(self, adv: bytes):
        """Announces room on local 127.0.0.1:6112 so War3 LAN browser displays it."""
        def bcast_loop():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                while self.running:
                    try:
                        s.sendto(adv, ("127.0.0.1", 6112))
                    except Exception:
                        pass
                    time.sleep(1.8)

        threading.Thread(target=bcast_loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.local_server:
            try:
                self.local_server.close()
            except Exception:
                pass
            self.local_server = None
        if self.active_client_sock:
            try:
                self.active_client_sock.close()
            except Exception:
                pass
            self.active_client_sock = None
        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass
            self.udp_sock = None
