"""End-to-End Test Suite for Aegis Platform Components."""
import io
from pathlib import Path
import tempfile
import time
import unittest

from core.save_sync import SaveSyncHost, sync_save_from_host
from core.warkey import AegisWarKey
from tools.map_converter import patch_jass_script


class TestAegisSuite(unittest.TestCase):
    def test_warkey_mapping(self):
        warkey = AegisWarKey()
        self.assertEqual(warkey.mapping, {})
        self.assertFalse(warkey.chat_active)
        self.assertTrue(warkey.enabled)

    def test_map_converter_patches(self):
        sample_script = (
            b'function main takes nothing returns nothing\n'
            b'call ExecuteFunc("OOHCO")\n'
            b'call TimerStart(CreateTimer(),0.1,true,function OVGVO)\n'
            b'endfunction\n'
        )
        patched = patch_jass_script(sample_script, enable_cam=True)
        self.assertIn(b"Aegis_InitCam", patched)
        self.assertIn(b"-cam ", patched)
        self.assertIn(b"-zoom ", patched)
        self.assertIn(b"// call ExecuteFunc(\"OOHCO\")", patched)
        self.assertIn(b"LSVN", patched)
        self.assertIn(b"LSAV", patched)
        self.assertIn(b"EVENT_GAME_SAVE", patched)

    def test_save_sync_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_host, tempfile.TemporaryDirectory() as tmp_client:
            host_save_dir = Path(tmp_host)
            client_save_dir = Path(tmp_client)

            # Create a mock .w3z save
            mock_save = host_save_dir / "Test_AutoSave_Match.w3z"
            mock_save.write_bytes(b"MOCK_W3Z_SAVE_PAYLOAD_FOR_TESTING_12345")

            # Start save sync server on port 6215 (test port)
            server = SaveSyncHost(host="127.0.0.1", port=6215, save_dir=host_save_dir)
            server.start()
            try:
                time.sleep(0.3)
                synced = sync_save_from_host(host_ip="127.0.0.1", port=6215, dest_dir=client_save_dir)
                self.assertIsNotNone(synced)
                self.assertTrue(synced.is_file())
                self.assertEqual(synced.name, "Test_AutoSave_Match.w3z")
                self.assertEqual(synced.read_bytes(), b"MOCK_W3Z_SAVE_PAYLOAD_FOR_TESTING_12345")
            finally:
                server.stop()

    def test_jass_locals_precedence(self):
        script_with_locals = (
            b'function main takes nothing returns nothing\n'
            b'local integer i = 0\n'
            b'local string s = "test"\n'
            b'call SetCameraBounds(0,0,0,0,0,0,0,0)\n'
            b'endfunction\n'
        )
        patched = patch_jass_script(script_with_locals, enable_cam=True)
        idx_main = patched.find(b"function main takes nothing returns nothing")
        idx_local_s = patched.find(b'local string s = "test"')
        idx_call_cam = patched.find(b"call Aegis_InitCam()")
        idx_end_main = patched.find(b"endfunction", idx_main)

        # Ensure call Aegis_InitCam() is placed AFTER all local declarations
        self.assertGreater(idx_call_cam, idx_local_s)
        # Ensure call Aegis_InitCam() is inside function main before endfunction
        self.assertLess(idx_call_cam, idx_end_main)

    def test_ghost_cfg_isolated_broadcast(self):
        from core.recovery_manager import AegisEngine
        engine = AegisEngine()
        cfg_path = engine.runtime_dir / "ghost.cfg"
        # Check that ghost.cfg uses isolated 127.0.0.99 target
        if cfg_path.is_file():
            content = cfg_path.read_text(encoding="utf-8")
            self.assertIn("udp_broadcasttarget = 127.0.0.99", content)

    def test_p2p_tunnel_loopback(self):
        import socket
        import threading
        from core.p2p_tunnel import P2PHostTunnel, P2PClientTunnel

        # 1. Mock GHost TCP server
        ghost_echo = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ghost_echo.bind(("127.0.0.1", 0))
        ghost_echo.listen(1)
        ghost_port = ghost_echo.getsockname()[1]

        def echo_worker():
            try:
                conn, _ = ghost_echo.accept()
                data = conn.recv(1024)
                conn.sendall(b"ECHO:" + data)
                conn.close()
            except Exception:
                pass

        echo_th = threading.Thread(target=echo_worker, daemon=True)
        echo_th.start()

        # 2. Host tunnel listening on random UDP port
        host_tunnel = P2PHostTunnel(ghost_port=ghost_port, local_udp_port=0)
        host_udp_port = host_tunnel.start()

        # 3. Client tunnel connecting to host's UDP port, listening on dynamic TCP port
        client_tunnel = P2PClientTunnel(host_public_ip="127.0.0.1", host_public_port=host_udp_port, local_tcp_port=0)
        client_udp_port = client_tunnel.start(local_udp_port=0)

        # Notify host about client
        host_tunnel.punch_to_client("127.0.0.1", client_udp_port)
        time.sleep(0.1)

        try:
            # 4. Connect simulated War3 to client's local TCP port
            war3_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            war3_sock.settimeout(2.0)
            war3_sock.connect(("127.0.0.1", client_tunnel.local_tcp_port))

            # Send payload through client tunnel -> UDP -> host tunnel -> GHost
            war3_sock.sendall(b"WAR3_HELLO")
            response = war3_sock.recv(1024)
            self.assertEqual(response, b"ECHO:WAR3_HELLO")
            war3_sock.close()
        finally:
            client_tunnel.stop()
            host_tunnel.stop()
            ghost_echo.close()

    def test_signaling_packet_encoding(self):
        from core.signaling import _encode_str
        encoded = _encode_str("MQTT")
        self.assertEqual(encoded, b"\x00\x04MQTT")

    def test_stun_packet_structure(self):
        import struct
        msg_type = 0x0001
        msg_len = 0
        magic_cookie = 0x2112A442
        trans_id = b"0123456789ab"
        req = struct.pack(">HHI12s", msg_type, msg_len, magic_cookie, trans_id)
        self.assertEqual(len(req), 20)
        self.assertEqual(req[:4], b"\x00\x01\x00\x00")

    def test_isolation_trap_no_leak(self):
        import socket
        from core.recovery_manager import AegisEngine
        engine = AegisEngine()
        engine.start_isolation_trap()
        try:
            # Simulate War3 listening on 0.0.0.0:6112
            war3_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            war3_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            war3_sock.bind(("0.0.0.0", 6112))
            war3_sock.settimeout(0.3)

            # Sender sends to 127.0.0.99:6112
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.sendto(b"GHOST_ADMIN_SAMPLE", ("127.0.0.99", 6112))

            # War3 must receive nothing because trap absorbed it
            with self.assertRaises(socket.timeout):
                war3_sock.recvfrom(1024)

            send_sock.close()
            war3_sock.close()
        finally:
            engine.stop_isolation_trap()

    def test_war3_navigator_definitions(self):
        from core.war3_navigator import find_war3_window, press_scan, send_combo
        self.assertTrue(callable(find_war3_window))
        self.assertTrue(callable(press_scan))
        self.assertTrue(callable(send_combo))


if __name__ == "__main__":
    unittest.main()
