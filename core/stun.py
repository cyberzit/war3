"""RFC 5389 / RFC 3489 Lightweight STUN Client for NAT Traversal.

Discovers external public IP and mapped UDP port without external dependencies.
"""
import random
import socket
import struct
import time

STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun.syncthing.net", 3478),
]


def get_public_endpoint(timeout: float = 2.5, local_port: int = 0) -> tuple[str, int, int] | None:
    """Discovers (public_ip, public_port, local_port) via public STUN servers."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    if local_port != 0:
        try:
            sock.bind(("0.0.0.0", local_port))
        except Exception:
            pass

    msg_type = 0x0001
    msg_len = 0
    magic_cookie = 0x2112A442
    trans_id = random.randbytes(12)
    req = struct.pack(">HHI12s", msg_type, msg_len, magic_cookie, trans_id)

    for host, port in STUN_SERVERS:
        try:
            sock.sendto(req, (host, port))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                data, _ = sock.recvfrom(2048)
                if len(data) >= 20:
                    resp_type, resp_len, resp_cookie = struct.unpack_from(">HHI", data, 0)
                    if resp_type == 0x0101:  # Binding Success
                        offset = 20
                        actual_ip = None
                        actual_port = None
                        while offset < 20 + resp_len:
                            attr_type, attr_len = struct.unpack_from(">HH", data, offset)
                            val = data[offset + 4 : offset + 4 + attr_len]
                            if attr_type == 0x0020:  # XOR-MAPPED-ADDRESS
                                _, family, xor_port = struct.unpack_from(">BBH", val, 0)
                                actual_port = xor_port ^ (magic_cookie >> 16)
                                if family == 1:
                                    xor_ip = struct.unpack_from(">I", val, 4)[0]
                                    actual_ip = socket.inet_ntoa(struct.pack(">I", xor_ip ^ magic_cookie))
                                    sock_local = sock.getsockname()[1]
                                    sock.close()
                                    return actual_ip, actual_port, sock_local
                            elif attr_type == 0x0001:  # MAPPED-ADDRESS (fallback)
                                _, family, mapped_port = struct.unpack_from(">BBH", val, 0)
                                if family == 1:
                                    mapped_ip = socket.inet_ntoa(val[4:8])
                                    sock_local = sock.getsockname()[1]
                                    sock.close()
                                    return mapped_ip, mapped_port, sock_local
                            offset += 4 + attr_len
        except Exception:
            continue
    try:
        sock.close()
    except Exception:
        pass
    return None


if __name__ == "__main__":
    print("Discovering NAT endpoint via STUN...")
    res = get_public_endpoint()
    print("Result:", res)
