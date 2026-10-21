import asyncio
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import app as api
from backend.w3gs_room import Framer, LOD_MAP_SIZE_INT, W3GSRoomManager, packet


def make_synthetic_w3z(seed: int = 0x12345678, magic: int = 0xCAFEBABE) -> bytes:
    prefix = bytearray()
    prefix.extend(b"Maps\\Download\\LoD_Sync_25.w3x\x00")
    prefix.extend(b"\x00")
    prefix.extend(b"MongolRanger Match\x00")
    prefix.extend(b"\x00\x00")
    prefix.extend(b"\x00" * 10)
    prefix.append(10)
    # Slot 0: PID 1 (HostPlayer), Team 0
    prefix.extend(bytes([1, 100, 2, 0, 0, 1, 4, 1, 100]))
    for c in range(2, 6):
        prefix.extend(bytes([0, 255, 0, 0, 0, c, 4, 1, 100]))
    # Slot 5: PID 2 (OtherPlayer), Team 1
    prefix.extend(bytes([2, 100, 2, 0, 1, 7, 8, 1, 100]))
    for c in range(8, 12):
        prefix.extend(bytes([0, 255, 0, 0, 1, c, 8, 1, 100]))
    prefix.extend(struct.pack("<IBBI", seed, 0, 10, magic))
    raw_block = bytes(prefix)
    comp = zlib.compressobj()
    compressed_block = comp.compress(raw_block) + comp.flush(zlib.Z_SYNC_FLUSH)
    block_hdr = struct.pack("<HHI", len(compressed_block), len(raw_block), 0)
    total_len = 68 + 8 + len(compressed_block)
    hdr = bytearray(b"Warcraft III recorded game\x1a\0")
    hdr.extend(struct.pack("<5I", 68, total_len, 1, len(raw_block), 1))
    hdr.extend(struct.pack("<4sIHHI", b"PX3W", 26, 6059, 0, 1000))
    hdr.extend(b"\x00\x00\x00\x00")
    return bytes(hdr) + block_hdr + compressed_block


def build_reqjoin(counter: int, key: int, name: str) -> bytes:
    encoded = name.encode("ascii")
    return packet(
        0x1E,
        struct.pack("<IIBHI", counter, key, 0, 6112, 0)
        + encoded
        + b"\0"
        + struct.pack("<IH", 0, 6112)
        + b"\x7f\0\0\x01",
    )


def build_outgoing(body: bytes) -> bytes:
    return packet(0x26, struct.pack("<I", zlib.crc32(body)) + body)


class LobbyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path_patch = patch.object(api, "DB_PATH", Path(self.temp.name) / "test.sqlite3")
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        api.rate_events.clear()
        self.client = self.enterContext(TestClient(api.app))

    def account(self, name):
        data = {"username": name, "password": "test-only-password-2026", "email": f"{name.lower()}@example.com"}
        self.assertEqual(self.client.post("/api/auth/register", json=data).status_code, 201)
        response = self.client.post("/api/auth/login", json=data)
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.json()["token"]}

    def room(self, headers, capacity=2):
        response = self.client.post("/api/rooms", headers=headers,
                                    json={"name": "Test", "map_name": "DotA LoD 6.85m", "capacity": capacity})
        self.assertEqual(response.status_code, 201)
        return response.json()["room_id"]

    def test_auth_and_persistence(self):
        headers = self.account("Host")
        with api.database() as db:
            row = db.execute("SELECT * FROM users").fetchone()
            self.assertNotEqual(row["password_hash"], "test-only-password-2026")
            self.assertNotEqual(db.execute("SELECT token_hash FROM sessions").fetchone()[0], headers["Authorization"][7:])
        api.initialize()
        self.assertEqual(self.client.get("/api/rooms", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/rooms", headers=headers).status_code, 401)

    def test_wrong_password_and_case_duplicate(self):
        self.account("Host")
        self.assertEqual(self.client.post("/api/auth/login", json={"username": "Host", "password": "wrong-password"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/register", json={"username": "host", "password": "long-password", "email": "host2@example.com"}).status_code, 409)

    def test_room_capacity_ownership_chat_and_close(self):
        host, friend, other = [self.account(n) for n in ("Host", "Friend", "Other")]
        rid = self.room(host)
        base = "/api/rooms/" + rid
        self.assertEqual(self.client.post(base + "/join", headers=friend).status_code, 200)
        self.assertEqual(self.client.post(base + "/join", headers=other).status_code, 409)
        self.assertEqual(self.client.post(base + "/heartbeat", headers=friend).status_code, 403)
        self.assertEqual(self.client.post(base + "/heartbeat", headers=host).status_code, 200)
        self.assertEqual(self.client.post(base + "/messages", headers=other, json={"text": "forbidden"}).status_code, 403)
        self.assertEqual(self.client.post(base + "/messages", headers=friend, json={"text": "hello"}).status_code, 201)
        result = self.client.get(base + "/messages", headers=host).json()["messages"]
        self.assertEqual(result[-1]["username"], "Friend")
        self.assertEqual(result[-1]["text"], "hello")
        self.client.post(base + "/leave", headers=host)
        self.assertEqual(self.client.get("/api/rooms", headers=friend).json()["rooms"], [])

    def test_expired_rooms_release_members(self):
        host = self.account("Host")
        rid = self.room(host)
        with api.database() as db:
            db.execute("UPDATE rooms SET updated=0")
        self.assertEqual(self.client.get("/api/rooms", headers=host).json()["rooms"], [])
        self.assertNotEqual(self.room(host), rid)

    def test_bounds_and_unauthenticated_access(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/api/rooms").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/register", content=b"x"*9000).status_code, 413)
        self.assertEqual(self.client.post("/api/auth/register", json={"username": "abc", "password": "short"}).status_code, 422)

    def test_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.client.post("/api/auth/login", json={}).status_code, 422)
        self.assertEqual(self.client.post("/api/auth/login", json={}).status_code, 429)

    def test_checkpoint_upload_and_download_api(self):
        host, friend = [self.account(n) for n in ("Bataa", "Dorj")]
        rid = self.room(host, capacity=10)
        self.assertEqual(self.client.post(f"/api/rooms/{rid}/join", headers=friend).status_code, 200)
        w3z_bytes = make_synthetic_w3z()
        up = self.client.put(
            f"/api/rooms/{rid}/checkpoint",
            headers={**friend, "Content-Length": str(len(w3z_bytes))},
            content=w3z_bytes,
        )
        self.assertEqual(up.status_code, 200)
        self.assertTrue(up.json()["filename"].startswith("mr_"))
        dl = self.client.get(f"/api/rooms/{rid}/checkpoint", headers=host)
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl.content, w3z_bytes)
        state = self.client.get(f"/api/rooms/{rid}/state", headers=host).json()
        self.assertEqual(state["checkpoint"]["filename"], up.json()["filename"])

    def test_w3gs_live_game_and_host_crash_rejoin(self):
        async def scenario():
            mgr = W3GSRoomManager()
            port = await mgr.start_tcp_server("127.0.0.1", 0)
            try:
                room = mgr.create_room("r1", "MongolRanger Test", "Bataa")
                self.assertEqual(room.hcl, "")
                # 1. Connect Bataa (Host) and Dorj (Client)
                r1, w1 = await asyncio.open_connection("127.0.0.1", port)
                r2, w2 = await asyncio.open_connection("127.0.0.1", port)
                w1.write(build_reqjoin(room.host_counter, room.entry_key, "Bataa"))
                w2.write(build_reqjoin(room.host_counter, room.entry_key, "Dorj"))
                await w1.drain()
                await w2.drain()
                await asyncio.sleep(0.05)

                # Send MAPSIZE ready + GAMELOADED_SELF
                mapsize_pkt = packet(0x42, struct.pack("<IBI", 1, 1, LOD_MAP_SIZE_INT))
                w1.write(mapsize_pkt)
                w2.write(mapsize_pkt)
                await w1.drain()
                await w2.drain()
                await asyncio.sleep(0.05)

                await room.start_game(force=True)
                self.assertEqual(room.phase, "STARTING")

                w1.write(packet(0x23))
                w2.write(packet(0x23))
                await w1.drain()
                await w2.drain()
                await asyncio.sleep(0.05)
                self.assertEqual(room.phase, "CONTINUING")

                # 2. Simulate Host PC (Bataa) crashing!
                w1.close()
                await asyncio.sleep(0.1)
                self.assertEqual(room.phase, "FROZEN")
                self.assertEqual(room.absent, "Bataa")

                # Survivor (Dorj) emits save-complete 0x0701000000 and acks frames
                w2.write(build_outgoing(b"\x07\x01\x00\x00\x00"))
                w2.write(packet(0x27, b"\x00\xaa\xbb\xcc\xdd"))
                w2.write(packet(0x27, b"\x00\xaa\xbb\xcc\xdd"))
                await w2.drain()
                await asyncio.sleep(0.25)

                # Survivor uploads checkpoint
                room.receive_checkpoint_bytes(make_synthetic_w3z())
                await asyncio.sleep(0.1)
                self.assertEqual(room.phase, "WAITING")

                # 3. Bataa (Host) rejoins using rejoin_counter!
                r1_new, w1_new = await asyncio.open_connection("127.0.0.1", port)
                f1 = Framer()
                w1_new.write(build_reqjoin(room.rejoin_counter, room.entry_key, "Bataa"))
                await w1_new.drain()
                await asyncio.sleep(0.05)
                self.assertEqual(room.phase, "LOADING")

                w1_new.write(mapsize_pkt)
                w1_new.write(packet(0x23))
                await w1_new.drain()

                # Read packets on Bataa and reply with 0x27 keepalive for each 0x0C step
                for _ in range(15):
                    await asyncio.sleep(0.05)
                    try:
                        chunk = await asyncio.wait_for(r1_new.read(8192), timeout=0.05)
                        for p in f1.feed(chunk):
                            if p[1] == 0x0C:
                                w1_new.write(packet(0x27, b"\x00\xaa\xbb\xcc\xdd"))
                                await w1_new.drain()
                    except asyncio.TimeoutError:
                        pass
                    w2.write(packet(0x27, b"\x00\xaa\xbb\xcc\xdd"))
                    await w2.drain()
                    if room.phase == "CONTINUING":
                        break

                self.assertEqual(room.phase, "CONTINUING")
                w1_new.close()
                w2.close()
            finally:
                await mgr.stop_tcp_server()

        asyncio.run(scenario())

    def test_admin_panel_and_map_auto_converter_catalog(self):
        from backend.map_catalog import MPQReader, mpq_encrypt, mpq_hash

        # Build a minimal valid .w3x MPQ archive containing war3map.j without -cam
        jass_code = (
            b"globals\nendglobals\n"
            b"function main takes nothing returns nothing\n"
            b"call DoNothing()\n"
            b"endfunction\n"
        )
        key = mpq_hash("war3map.j", "TABLE")
        comp = b"\x02" + zlib.compress(jass_code, 9)
        pos_enc = mpq_encrypt(struct.pack("<2I", 8, 8 + len(comp)), (key - 1) & 0xFFFFFFFF)
        sec_enc = mpq_encrypt(comp, key)
        file_block = pos_enc + sec_enc

        file_offset = 32
        ht_offset = file_offset + len(file_block)
        bt_offset = ht_offset + 16 * 4
        archive_size = bt_offset + 16 * 1

        mpq_hdr = struct.pack("<4s2I2H4I", b"MPQ\x1a", 32, archive_size, 0, 3, ht_offset, bt_offset, 4, 1)
        ha = mpq_hash("war3map.j", "HASH_A")
        hb = mpq_hash("war3map.j", "HASH_B")
        ht_plain = struct.pack("<2I2HI", ha, hb, 0, 0, 0) + struct.pack("<2I2HI", 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFFFFFFFF) * 3
        ht_enc = mpq_encrypt(ht_plain, mpq_hash("(hash table)", "TABLE"))
        bt_plain = struct.pack("<4I", file_offset, len(file_block), len(jass_code), 0x80010200)
        bt_enc = mpq_encrypt(bt_plain, mpq_hash("(block table)", "TABLE"))

        hm3w = bytearray(512)
        hm3w[:4] = b"HM3W"
        hm3w[8:27] = b"DotA v6.74c LoD\x00\x00\x00\x00"
        w3x_bytes = bytes(hm3w) + mpq_hdr + file_block + ht_enc + bt_enc

        # 1. Verify /admin page loads
        adm_page = self.client.get("/admin")
        self.assertEqual(adm_page.status_code, 200)
        self.assertIn("MongolRanger Admin", adm_page.text)

        # 2. Login as admin
        login_res = self.client.post("/api/admin/login", json={"username": "admin", "password": api.ADMIN_DEFAULT_PASS})
        self.assertEqual(login_res.status_code, 200)
        adm_headers = {"Authorization": "Bearer " + login_res.json()["token"]}

        # 3. Upload 6.74c map with -cam & reconnect auto-patching enabled
        up_res = self.client.post(
            "/api/admin/maps?filename=DotA_v6.74c_LoD.w3x&title=DotA+6.74c+LoD&enable_cam=1&enable_reconnect=1&is_default=1",
            headers={**adm_headers, "Content-Length": str(len(w3x_bytes))},
            content=w3x_bytes,
        )
        self.assertEqual(up_res.status_code, 201)
        map_info = up_res.json()["map"]
        self.assertTrue(map_info["has_cam"])
        self.assertTrue(map_info["has_reconnect"])
        self.assertTrue(map_info["download_available"])

        # 4. Fast HTTPS download returns the patched map with Aegis_InitCam injected
        dl_res = self.client.get(map_info["download_url"])
        self.assertEqual(dl_res.status_code, 200)
        patched_mpq = dl_res.content[dl_res.content.find(b"MPQ\x1a") :]
        reader = MPQReader(patched_mpq)
        extracted_jass = reader.read_file("war3map.j")
        self.assertIn(b"Aegis_InitCam", extracted_jass)
        self.assertIn(b"CAMERA_FIELD_TARGET_DISTANCE", extracted_jass)

        # 5. Creating a room with DotA_v6.74c_LoD.w3x uses its exact W3GS metadata
        user_hdr = self.account("ZevPlayer")
        room_res = self.client.post(
            "/api/rooms",
            headers=user_hdr,
            json={"name": "74c Room", "map_name": "DotA_v6.74c_LoD.w3x", "capacity": 10},
        )
        self.assertEqual(room_res.status_code, 201)
        rid = room_res.json()["room_id"]
        wroom = api.w3gs_manager.get_room(rid)
        self.assertEqual(wroom.map_path, "Maps\\Download\\DotA_v6.74c_LoD.w3x")
        self.assertEqual(wroom.map_crc.hex(), map_info["crc_hex"])
        self.assertEqual(wroom.map_sha1.hex(), map_info["sha1_hex"])

    def test_public_website_and_admin_downloads_manager(self):
        # 1. Public website loads with modern 2026 MongolRanger X UI
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("MongolRanger", home.text)
        self.assertIn("downloadsGrid", home.text)

        # 2. Public overview returns pre-seeded ready downloads (client_win, client_mac, game_full on R2)
        pub = self.client.get("/api/public/overview")
        self.assertEqual(pub.status_code, 200)
        dls = {d["slot"]: d for d in pub.json()["downloads"]}
        self.assertIn("client_win", dls)
        self.assertIn("client_mac", dls)
        self.assertIn("game_full", dls)
        self.assertTrue(dls["client_win"]["ready"])
        self.assertTrue(dls["client_mac"]["ready"])
        self.assertTrue(dls["game_full"]["ready"])
        self.assertTrue(dls["game_full"]["is_r2"])

        # 2b. Default game_full redirects to signed Cloudflare R2 URL
        r2_redir = self.client.get("/api/downloads/game_full/file", follow_redirects=False)
        self.assertEqual(r2_redir.status_code, 302)
        self.assertIn("r2.cloudflarestorage.com/kora/mongolranger/downloads/", r2_redir.headers["location"])
        self.assertIn("X-Amz-Signature=", r2_redir.headers["location"])

        # 3. Downloading client_win returns valid Windows client package (ZIP or PE)
        win_dl = self.client.get("/api/downloads/client_win/file")
        self.assertEqual(win_dl.status_code, 200)
        self.assertTrue(win_dl.content.startswith((b"PK\x03\x04", b"MZ")))

        # 4. Admin uploads a custom file to client_win and tests R2 presign + complete + external link
        login_res = self.client.post("/api/admin/login", json={"username": "admin", "password": api.ADMIN_DEFAULT_PASS})
        adm_headers = {"Authorization": "Bearer " + login_res.json()["token"]}

        presign_res = self.client.post(
            "/api/admin/downloads/game_full/r2-presign",
            headers=adm_headers,
            json={"filename": "War3-1.26a-Full.zip", "content_type": "application/zip"},
        )
        self.assertEqual(presign_res.status_code, 200)
        self.assertIn("r2.cloudflarestorage.com/kora/mongolranger/downloads/War3-1.26a-Full.zip", presign_res.json()["upload_url"])

        comp_res = self.client.post(
            "/api/admin/downloads/game_full/r2-complete",
            headers=adm_headers,
            json={
                "r2_key": presign_res.json()["r2_key"],
                "filename": "War3-1.26a-Full.zip",
                "size_bytes": 1288490188,
                "version": "1.26a R2",
            },
        )
        self.assertEqual(comp_res.status_code, 200)
        self.assertTrue(comp_res.json()["download"]["is_r2"])
        self.assertIn("1.20 GB (Cloudflare R2)", comp_res.json()["download"]["size_label"])

        custom_zip = b"PK\x03\x04" + b"MONGOLRANGER_CUSTOM_PACKAGE_TEST_DATA"
        up_dl = self.client.post(
            "/api/admin/downloads/client_win/upload?filename=MongolRanger-v2.6.zip&version=v2.6",
            headers={**adm_headers, "Content-Length": str(len(custom_zip))},
            content=custom_zip,
        )
        self.assertEqual(up_dl.status_code, 200)
        self.assertEqual(up_dl.json()["download"]["version"], "v2.6")
        self.assertEqual(self.client.get("/api/downloads/client_win/file").content, custom_zip)

        link_res = self.client.post(
            "/api/admin/downloads/game_full/link",
            headers=adm_headers,
            json={
                "external_url": "https://cdn.example.com/Warcraft-III-1.26a-Full.zip",
                "version": "1.26a Full",
                "size_label": "1.24 GB",
                "button_text": "Warcraft III 1.26a Шууд Татах",
            },
        )
        self.assertEqual(link_res.status_code, 200)
        game_dl_meta = link_res.json()["download"]
        self.assertTrue(game_dl_meta["is_external"])
        self.assertEqual(game_dl_meta["download_url"], "https://cdn.example.com/Warcraft-III-1.26a-Full.zip")

        redir = self.client.get("/api/downloads/game_full/file", follow_redirects=False)
        self.assertEqual(redir.status_code, 302)
        self.assertEqual(redir.headers["location"], "https://cdn.example.com/Warcraft-III-1.26a-Full.zip")

    def test_room_code_and_anti_maphack_protection(self):
        host_hdr = self.account("HostZev")
        joiner_hdr = self.account("JoinerBat")

        # 1. Create room initially with a code ("7788")
        cr = self.client.post(
            "/api/rooms",
            headers=host_hdr,
            json={"name": "VIP Clan War", "map_name": "LoD_Sync_25.w3x", "capacity": 10, "room_code": "7788"},
        )
        self.assertEqual(cr.status_code, 201)
        rid = cr.json()["room_id"]
        self.assertEqual(cr.json()["is_locked"], 1)
        self.assertEqual(cr.json()["room_code"], "7788")

        # 2. Rooms list shows is_locked=1 without leaking room_code
        rlist = self.client.get("/api/rooms", headers=joiner_hdr).json()["rooms"]
        room_item = next(r for r in rlist if r["id"] == rid)
        self.assertEqual(room_item["is_locked"], 1)
        self.assertNotIn("room_code", room_item)

        # 3. Joining without code or with wrong code is rejected with 403
        bad_join = self.client.post(f"/api/rooms/{rid}/join", headers=joiner_hdr, json={"room_code": "0000"})
        self.assertEqual(bad_join.status_code, 403)

        # 4. Joining with correct code succeeds
        ok_join = self.client.post(f"/api/rooms/{rid}/join", headers=joiner_hdr, json={"room_code": "7788"})
        self.assertEqual(ok_join.status_code, 200)

        # 5. Non-host cannot change room code (403), Host can change or remove room code
        non_owner_code = self.client.post(f"/api/rooms/{rid}/code", headers=joiner_hdr, json={"room_code": "9999"})
        self.assertEqual(non_owner_code.status_code, 403)

        owner_code = self.client.post(f"/api/rooms/{rid}/code", headers=host_hdr, json={"room_code": "9999"})
        self.assertEqual(owner_code.status_code, 200)
        self.assertEqual(owner_code.json()["room_code"], "9999")
        self.assertEqual(owner_code.json()["is_locked"], 1)

        # 6. Anti-MapHack violation reported via heartbeat kicks the cheater immediately (403)
        ac_res = self.client.post(
            f"/api/rooms/{rid}/heartbeat",
            headers=joiner_hdr,
            json={"ac_status": "violation", "violation": "MapHack програм илэрлээ (w3mh)"},
        )
        self.assertEqual(ac_res.status_code, 403)
        wroom = api.w3gs_manager.get_room(rid)
        self.assertIn("JoinerBat", getattr(wroom, "kicked_cheaters", set()))

        # 7. Server-side W3GS opcode filter blocks injected single-player cheat opcodes (0x2F RemoveFogOfWar)
        self.assertEqual(wroom.extract_and_strip_hero_nt("JoinerBat", b"\x2f\x00\x00\x00\x00"), b"")

        # 8. Steam-style Auto-Updater endpoint returns live SHA256 and version
        ver_res = self.client.get("/api/client/version")
        self.assertEqual(ver_res.status_code, 200)
        ver_json = ver_res.json()
        self.assertTrue(ver_json["ok"])
        self.assertEqual(len(ver_json["sha256"]), 64)
        self.assertEqual(ver_json["download_url"], "/api/client/exe")

    def test_lobby_phase_never_triggers_rejoin_or_premature_countdown(self):
        host_hdr = self.account("HostTest")
        client_hdr = self.account("ClientTest")
        rid = self.room(host_hdr, capacity=10)
        self.assertEqual(self.client.post(f"/api/rooms/{rid}/join", headers=client_hdr).status_code, 200)

        # Clicking START GAME in MongolRanger before Host is in War3 LAN lobby must ONLY set launch_signal
        # and keep phase == "LOBBY" (never prematurely enter STARTING or lock buttons)
        launch_res = self.client.post(f"/api/rooms/{rid}/launch", headers=host_hdr)
        self.assertEqual(launch_res.status_code, 200)
        self.assertEqual(launch_res.json()["phase"], "LOBBY")
        self.assertGreater(launch_res.json()["launch_signal"], 0)

        # Even if a player connects and leaves the War3 LAN lobby while phase == "LOBBY",
        # disconnected_players / my_disconnected must remain 0 so Rejoin never activates on an unstarted match
        wroom = api.w3gs_manager.get_room(rid)
        wroom.disconnected_players.add("ClientTest")
        st = self.client.get(f"/api/rooms/{rid}/state", headers=client_hdr).json()
        self.assertEqual(st["phase"], "LOBBY")
        self.assertEqual(st["my_disconnected"], 0)

    def test_host_slot1_and_unified_commands(self):
        import asyncio as _asyncio
        import time as _time
        from backend.w3gs_room import RoomPeer

        host_hdr = self.account("HostOwner")
        joiner_hdr = self.account("FirstJoiner")
        rid = self.room(host_hdr, capacity=10)
        self.assertEqual(self.client.post(f"/api/rooms/{rid}/join", headers=joiner_hdr).status_code, 200)

        wroom = api.w3gs_manager.get_room(rid)
        self.assertEqual(wroom.owner_name, "HostOwner")

        class _DummyWriter:
            def write(self, data):
                pass
            async def drain(self):
                pass
            def close(self):
                pass

        # 1. Non-host entering W3GS first gets Slot 2 (sid=1), Host always gets Slot 1 (sid=0)
        sid_joiner = wroom._allocate_sid(player_name="FirstJoiner")
        self.assertEqual(sid_joiner, 1)
        wroom.slots[sid_joiner]["status"] = 2
        wroom.slots[sid_joiner]["pid"] = 2
        wroom.peers["FirstJoiner"] = RoomPeer(name="FirstJoiner", pid=2, sid=sid_joiner, writer=_DummyWriter())

        sid_host = wroom._allocate_sid(player_name="HostOwner")
        self.assertEqual(sid_host, 0)
        wroom.slots[sid_host]["status"] = 2
        wroom.slots[sid_host]["pid"] = 1
        wroom.peers["HostOwner"] = RoomPeer(name="HostOwner", pid=1, sid=sid_host, writer=_DummyWriter())

        # 2. Only Host can execute -swap and -start
        res_swap_nonhost = self.client.post(
            f"/api/rooms/{rid}/chat", headers=joiner_hdr, json={"message": "-swap 2 6"}
        )
        self.assertEqual(res_swap_nonhost.status_code, 201)
        self.assertEqual(wroom.peers["FirstJoiner"].sid, 1)  # Unchanged!

        res_swap_host = self.client.post(
            f"/api/rooms/{rid}/chat", headers=host_hdr, json={"message": "-swap 2 6"}
        )
        self.assertEqual(res_swap_host.status_code, 201)
        self.assertEqual(wroom.peers["FirstJoiner"].sid, 5)  # Moved to Slot 6 (sid=5, Scourge)

        # Non-host typing -start in room chat is rejected
        res_start_nonhost = self.client.post(
            f"/api/rooms/{rid}/chat", headers=joiner_hdr, json={"message": "-start"}
        )
        self.assertEqual(res_start_nonhost.status_code, 201)
        self.assertEqual(wroom.phase, "LOBBY")

        # 3. Setup active match for -rmk and -gg rules across 1v1, 2v2, 3v3, 4v4, 5v5
        wroom.phase = "CONTINUING"
        wroom.match_started_at = _time.time() - 120.0  # 2 minutes into match

        # -gg before 15 minutes on ranked 5v5 (or default uninitialized room) must be rejected
        ok_gg_early, msg_gg_early = _asyncio.run(wroom.vote_forfeit("FirstJoiner"))
        self.assertFalse(ok_gg_early)
        self.assertIn("15 минут", msg_gg_early)

        # In 1v1 / 2v2 / 3v3 / 4v4 (initial_player_count < 10), -gg works after 5 minutes (no 5-15m dead zone)
        wroom.initial_player_count = 2
        wroom._cmd_dedup.clear()
        wroom.match_started_at = _time.time() - 360.0  # 6 minutes into 1v1 match
        ok_rmk_late, msg_rmk_late = _asyncio.run(wroom.vote_remake("FirstJoiner"))
        self.assertFalse(ok_rmk_late)
        self.assertIn("5 минут", msg_rmk_late)

        ok_gg_1v1, msg_gg_1v1 = _asyncio.run(wroom.vote_forfeit("FirstJoiner"))
        self.assertTrue(ok_gg_1v1)
        self.assertIn("бууж өглөө", msg_gg_1v1)

        # Test 2v2 -rmk: 2 votes from any players (including 2 on the same team) immediately passes
        wroom.phase = "CONTINUING"
        wroom.initial_player_count = 4
        wroom.match_started_at = _time.time() - 60.0
        wroom.rmk_votes.clear()
        wroom._cmd_dedup.clear()
        wroom.peers = {
            "P1": RoomPeer(name="P1", pid=1, sid=0, writer=_DummyWriter()),
            "P2": RoomPeer(name="P2", pid=2, sid=1, writer=_DummyWriter()),
            "P3": RoomPeer(name="P3", pid=3, sid=5, writer=_DummyWriter()),
            "P4": RoomPeer(name="P4", pid=4, sid=6, writer=_DummyWriter()),
        }
        ok_v1, msg_v1 = _asyncio.run(wroom.vote_remake("P1"))
        self.assertTrue(ok_v1)
        self.assertIn("1/2", msg_v1)
        ok_v2, msg_v2 = _asyncio.run(wroom.vote_remake("P2"))
        self.assertTrue(ok_v2)
        self.assertEqual(wroom.phase, "LOBBY")
        self.assertIn("2/2", msg_v2)

        # Test 3v3 -rmk: 3 votes across both teams (e.g. 2 Sentinel + 1 Scourge) passes
        wroom.phase = "CONTINUING"
        wroom.initial_player_count = 6
        wroom.match_started_at = _time.time() - 60.0
        wroom.rmk_votes.clear()
        wroom._cmd_dedup.clear()
        wroom.peers = {
            "S1": RoomPeer(name="S1", pid=1, sid=0, writer=_DummyWriter()),
            "S2": RoomPeer(name="S2", pid=2, sid=1, writer=_DummyWriter()),
            "S3": RoomPeer(name="S3", pid=3, sid=2, writer=_DummyWriter()),
            "K1": RoomPeer(name="K1", pid=4, sid=5, writer=_DummyWriter()),
            "K2": RoomPeer(name="K2", pid=5, sid=6, writer=_DummyWriter()),
            "K3": RoomPeer(name="K3", pid=6, sid=7, writer=_DummyWriter()),
        }
        _asyncio.run(wroom.vote_remake("S1"))
        _asyncio.run(wroom.vote_remake("S2"))
        self.assertEqual(wroom.phase, "CONTINUING")
        ok_3v3, msg_3v3 = _asyncio.run(wroom.vote_remake("K1"))
        self.assertTrue(ok_3v3)
        self.assertEqual(wroom.phase, "LOBBY")
        self.assertIn("3/3", msg_3v3)

        # Ranked 5v5 -gg after 15 minutes succeeds and records wins/losses
        wroom.phase = "CONTINUING"
        wroom.match_scored = False
        wroom.initial_player_count = 10
        wroom.initial_team_counts = {0: 5, 1: 5}
        wroom.ff_votes.clear()
        wroom._cmd_dedup.clear()
        wroom.peers = {
            "HostOwner": RoomPeer(name="HostOwner", pid=1, sid=0, writer=_DummyWriter()),
            "FirstJoiner": RoomPeer(name="FirstJoiner", pid=2, sid=5, writer=_DummyWriter()),
        }
        wroom.ensure_player_stat("HostOwner")
        wroom.ensure_player_stat("FirstJoiner")
        wroom.match_started_at = _time.time() - 960.0  # 16 minutes into match
        ok_gg_ok, msg_gg_ok = _asyncio.run(wroom.vote_forfeit("FirstJoiner"))
        self.assertTrue(ok_gg_ok)
        self.assertIn("бууж өглөө", msg_gg_ok)

        host_info = self.client.get("/api/users/info?q=HostOwner", headers=host_hdr).json()
        join_info = self.client.get("/api/users/info?q=FirstJoiner", headers=joiner_hdr).json()
        self.assertEqual(host_info["wins"], 1)
        self.assertEqual(join_info["losses"], 1)

        # 4. Verify W3GS chat packets are always pure ASCII Latin so Warcraft III 1.26a FRIZQT__.TTF never renders blank glyphs
        from backend.w3gs_room import send_w3gs_chat_from_host, to_wc3_latin
        self.assertEqual(
            to_wc3_latin("|cFFFFCC00-start|r : host hiisen hun ene commandig bichij togloomiig ehluulne"),
            "|cFFFFCC00-start|r : host hiisen hun ene commandig bichij togloomiig ehluulne",
        )
        cyr_test = send_w3gs_chat_from_host(11, [1], 16, b"", "⏳ «HostOwner» тоглоомыг эхлүүллээ!")
        self.assertTrue(cyr_test[8:-1].decode("utf-8").isascii())
        self.assertIn("togloomiig ehluullee!", cyr_test[8:-1].decode("utf-8"))

        # 5. Verify inventory slot item updates (I112, I73) later in the match never pair a new item
        #    with a stale old item from >1.5s earlier or leave identity/stale mappings in tag_map
        wroom.peers["HostOwner"] = RoomPeer(name="HostOwner", pid=1, sid=0, writer=_DummyWriter())
        wroom.peers["FirstJoiner"] = RoomPeer(name="FirstJoiner", pid=2, sid=5, writer=_DummyWriter())

        def _drx_nt_packet(mkey: str, hi: int, lo: int) -> bytes:
            payload = (
                b"\x6bdr.x\x00"
                + mkey.encode("ascii") + b"\x00"
                + b"1\x00" + int(hi).to_bytes(4, "little")
                + b"\x6bdr.x\x00"
                + mkey.encode("ascii") + b"\x00"
                + b"2\x00" + int(lo).to_bytes(4, "little")
            )
            return payload

        old_hi, old_lo = 0x00009602, 0x00036B07
        new_hi, new_lo = 0x00046744, 0x00077218
        old_tag = old_hi.to_bytes(4, "little") + old_lo.to_bytes(4, "little")
        new_tag = new_hi.to_bytes(4, "little") + new_lo.to_bytes(4, "little")

        # Initial post-rejoin emission at t0: both clients emit the same item in slot I112
        wroom.extract_and_strip_hero_nt("HostOwner", _drx_nt_packet("I112", old_hi, old_lo))
        wroom.extract_and_strip_hero_nt("FirstJoiner", _drx_nt_packet("I112", old_hi, old_lo))
        self.assertEqual(wroom.tag_map.get(("HostOwner", "FirstJoiner"), {}), {})
        self.assertEqual(wroom.tag_map.get(("FirstJoiner", "HostOwner"), {}), {})

        # Simulate 60 seconds passing before slot I112 gets a newly purchased/moved item
        wroom.latest_tag_ts[("HostOwner", "I112")] -= 60.0
        wroom.latest_tag_ts[("FirstJoiner", "I112")] -= 60.0

        # HostOwner's packet for the new item arrives 20ms before FirstJoiner's packet
        wroom.extract_and_strip_hero_nt("HostOwner", _drx_nt_packet("I112", new_hi, new_lo))
        # Must NOT pair new_tag on HostOwner with 60s-old old_tag on FirstJoiner!
        self.assertNotIn(new_tag, wroom.tag_map.get(("HostOwner", "FirstJoiner"), {}))
        self.assertNotIn(old_tag, wroom.tag_map.get(("FirstJoiner", "HostOwner"), {}))

        # FirstJoiner's packet arrives 20ms later with the same new_tag
        wroom.extract_and_strip_hero_nt("FirstJoiner", _drx_nt_packet("I112", new_hi, new_lo))
        self.assertEqual(wroom.tag_map.get(("HostOwner", "FirstJoiner"), {}), {})
        self.assertEqual(wroom.tag_map.get(("FirstJoiner", "HostOwner"), {}), {})

        # 6. Verify special characters in username (Map3ak!!!!!), email registration,
        #    concise Mongolian validation error messages, and password reset via email
        short_pw_res = self.client.post("/api/auth/register", json={"username": "Map3ak!!!!!", "password": "123"})
        self.assertEqual(short_pw_res.status_code, 422)
        self.assertIsInstance(short_pw_res.json()["detail"], str)
        self.assertIn("6 тэмдэгт", short_pw_res.json()["detail"])

        reg_special = self.client.post(
            "/api/auth/register",
            json={"username": "Map3ak!!!!!", "password": "pass1234", "email": "map3ak@gmail.com"},
        )
        self.assertEqual(reg_special.status_code, 201)
        self.assertEqual(reg_special.json()["username"], "Map3ak!!!!!")

        # Wrong email cannot reset password
        bad_reset = self.client.post(
            "/api/auth/reset-password",
            json={"username": "Map3ak!!!!!", "email": "wrong@gmail.com", "new_password": "newpass123"},
        )
        self.assertEqual(bad_reset.status_code, 403)
        self.assertIn("таарахгүй", bad_reset.json()["detail"])

        # Correct email resets password and allows immediate login
        ok_reset = self.client.post(
            "/api/auth/reset-password",
            json={"username": "Map3ak!!!!!", "email": "map3ak@gmail.com", "new_password": "newpass123"},
        )
        self.assertEqual(ok_reset.status_code, 200)
        login_new = self.client.post(
            "/api/auth/login",
            json={"username": "Map3ak!!!!!", "password": "newpass123"},
        )
        self.assertEqual(login_new.status_code, 200)
        self.assertEqual(login_new.json()["username"], "Map3ak!!!!!")

        # 1-Click PowerShell installer endpoint
        inst_res = self.client.get("/install")
        self.assertEqual(inst_res.status_code, 200)
        self.assertIn("MongolRanger.exe", inst_res.text)


if __name__ == "__main__":
    unittest.main()




