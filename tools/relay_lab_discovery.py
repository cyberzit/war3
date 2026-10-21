"""Forward only loopback lab advertisements to the two isolated clients."""
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recovery_lab.protocol import game_info

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 6112))
    sock.settimeout(1)
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        try:
            data, sender = sock.recvfrom(65535)
            if sender[0] != '127.0.0.1' or game_info(data)['port'] != 6200:
                continue
            sock.sendto(data, ('127.0.0.1', 6113))
            sock.sendto(data, ('127.0.0.2', 6112))
        except (socket.timeout, ConnectionResetError, ValueError):
            pass
