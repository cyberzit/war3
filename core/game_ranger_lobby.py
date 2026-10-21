"""GameRanger-Style All-In-One P2P Lobby & Matchmaking Service.

Handles:
1. Global room discovery via public MQTT signaling.
2. STUN NAT endpoint discovery.
3. Automated P2P tunnel setup.
4. Synchronized game launch across all room members.
5. 1-Click crash recovery synchronization.
"""
import base64
import json
from pathlib import Path
import random
import socket
import threading
import time
from typing import Callable

from core.stun import get_public_endpoint
from core.signaling import AegisSignaling, TOPIC_ROOMS
from core.p2p_tunnel import P2PHostTunnel, P2PClientTunnel
from core.save_sync import SaveSyncHost, sync_save_from_host

GAME = Path(r"D:\games\_Oceanofgames.com_Warcraft_III_Frozen_Throne\Warcraft III")


class OnlineLobbyService:
    def __init__(self, player_name: str = "Player"):
        self.player_name = player_name
        self.sig = AegisSignaling(client_id=f"aegis_{player_name}_{random.randint(1000, 9999)}")
        self.rooms: dict[str, dict] = {}
        self.active_room: dict | None = None
        self.is_host = False
        self.public_endpoint: tuple[str, int, int] | None = None
        self.p2p_host_tunnel: P2PHostTunnel | None = None
        self.p2p_client_tunnel: P2PClientTunnel | None = None
        self.running = False

        # Callbacks for GUI
        self.on_rooms_updated: Callable[[list[dict]], None] | None = None
        self.on_room_state_changed: Callable[[dict | None], None] | None = None
        self.on_game_start_signal: Callable[[dict], None] | None = None
        self.on_recovery_signal: Callable[[dict], None] | None = None

    def start(self, on_rooms_updated: Callable[[list[dict]], None] | None = None) -> bool:
        self.on_rooms_updated = on_rooms_updated
        # 1. Discover public NAT endpoint via STUN
        self.public_endpoint = get_public_endpoint()
        if not self.public_endpoint:
            self.public_endpoint = ("127.0.0.1", 6200, 6200)

        # 2. Connect to global signaling broker
        if not self.sig.connect():
            return False

        self.running = True
        self.sig.subscribe(TOPIC_ROOMS, self._on_room_broadcast)
        self.sig.subscribe(f"{TOPIC_ROOMS}/query", self._on_room_query)
        # Ask active hosts to re-announce their rooms
        self.sig.publish(f"{TOPIC_ROOMS}/query", {"action": "list_request"})
        return True

    def create_online_room(self, room_name: str, map_name: str) -> dict:
        room_id = f"room_{random.randint(1000, 9999)}"
        pub_ip, pub_port, local_port = self.public_endpoint or ("127.0.0.1", 6200, 6200)

        room_data = {
            "action": "announce",
            "room_id": room_id,
            "room_name": room_name,
            "host_name": self.player_name,
            "map_name": map_name,
            "ip": pub_ip,
            "port": pub_port,
            "players": [self.player_name],
            "max_players": 10,
            "status": "Waiting in Lobby",
            "created_at": time.time(),
        }

        self.active_room = room_data
        self.is_host = True
        self.rooms[room_id] = room_data

        # Subscribe to room-specific channel for handshakes and commands
        self.sig.subscribe(f"aegis/room/{room_id}/#", self._on_room_message)
        self.sig.publish(TOPIC_ROOMS, room_data)

        if self.on_room_state_changed:
            self.on_room_state_changed(self.active_room)
        return room_data

    def join_online_room(self, room_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room:
            return False

        self.active_room = room
        self.is_host = False

        # Subscribe to room events
        self.sig.subscribe(f"aegis/room/{room_id}/#", self._on_room_message)

        # Send join request to host
        join_msg = {
            "action": "player_join",
            "player_name": self.player_name,
            "endpoint": self.public_endpoint,
        }
        self.sig.publish(f"aegis/room/{room_id}/events", join_msg)

        if self.on_room_state_changed:
            self.on_room_state_changed(self.active_room)
        return True

    def leave_active_room(self):
        if not self.active_room:
            return
        room_id = self.active_room["room_id"]
        if self.is_host:
            self.sig.publish(TOPIC_ROOMS, {"action": "close", "room_id": room_id})
            self.rooms.pop(room_id, None)
        else:
            self.sig.publish(f"aegis/room/{room_id}/events", {
                "action": "player_leave",
                "player_name": self.player_name
            })
        self.active_room = None
        self.is_host = False
        if self.on_room_state_changed:
            self.on_room_state_changed(None)
        if self.on_rooms_updated:
            self.on_rooms_updated(list(self.rooms.values()))

    def broadcast_game_start(self, room_adv: bytes):
        if not self.active_room or not self.is_host:
            return
        room_id = self.active_room["room_id"]
        pub_ip, pub_port, _ = self.public_endpoint or ("127.0.0.1", 6200, 6200)

        msg = {
            "action": "start_game",
            "room_id": room_id,
            "room_adv": base64.b64encode(room_adv).decode("ascii"),
            "host_ip": pub_ip,
            "host_port": pub_port,
        }
        self.sig.publish(f"aegis/room/{room_id}/events", msg)
        self.active_room["status"] = "In Game"
        self.sig.publish(TOPIC_ROOMS, {"action": "update", "room_id": room_id, "status": "In Game"})
        if self.on_room_state_changed:
            self.on_room_state_changed(self.active_room)

    def broadcast_recovery_start(self, room_adv: bytes, save_name: str):
        if not self.active_room or not self.is_host:
            return
        room_id = self.active_room["room_id"]
        pub_ip, pub_port, _ = self.public_endpoint or ("127.0.0.1", 6200, 6200)

        msg = {
            "action": "recover_game",
            "room_id": room_id,
            "room_adv": base64.b64encode(room_adv).decode("ascii"),
            "host_ip": pub_ip,
            "host_port": pub_port,
            "save_name": save_name,
        }
        self.sig.publish(f"aegis/room/{room_id}/events", msg)
        self.active_room["status"] = "In Game"
        self.active_room["room_adv"] = base64.b64encode(room_adv).decode("ascii")
        self.sig.publish(TOPIC_ROOMS, {"action": "update", "room_id": room_id, "status": "In Game"})
        if self.on_room_state_changed:
            self.on_room_state_changed(self.active_room)

    def _on_room_broadcast(self, topic: str, data: dict):
        if not isinstance(data, dict):
            return
        action = data.get("action")
        room_id = data.get("room_id")
        if action == "announce":
            self.rooms[room_id] = data
        elif action == "update" and room_id in self.rooms:
            self.rooms[room_id].update(data)
        elif action == "close":
            self.rooms.pop(room_id, None)

        if self.on_rooms_updated:
            self.on_rooms_updated(list(self.rooms.values()))

    def _on_room_query(self, topic: str, data: dict):
        # If someone requests the room list and we are hosting an active room, re-announce it
        if data.get("action") == "list_request" and self.active_room and self.is_host:
            self.sig.publish(TOPIC_ROOMS, self.active_room)

    def _on_room_message(self, topic: str, data: dict):
        if not isinstance(data, dict):
            return
        action = data.get("action")

        if action == "player_join":
            pname = data.get("player_name")
            if self.active_room and pname and pname not in self.active_room.get("players", []):
                self.active_room.setdefault("players", []).append(pname)
                if self.is_host:
                    # Host announces player list update
                    self.sig.publish(TOPIC_ROOMS, {
                        "action": "update",
                        "room_id": self.active_room["room_id"],
                        "players": self.active_room["players"]
                    })
                if self.on_room_state_changed:
                    self.on_room_state_changed(self.active_room)

        elif action == "player_leave":
            pname = data.get("player_name")
            if self.active_room and pname in self.active_room.get("players", []):
                self.active_room["players"].remove(pname)
                if self.on_room_state_changed:
                    self.on_room_state_changed(self.active_room)

        elif action == "start_game":
            if self.active_room:
                self.active_room["status"] = "In Game"
                if data.get("room_adv"):
                    self.active_room["room_adv"] = data.get("room_adv")
                if data.get("host_ip"):
                    self.active_room["host_ip"] = data.get("host_ip")
                if self.on_room_state_changed:
                    self.on_room_state_changed(self.active_room)
            if not self.is_host and self.on_game_start_signal:
                self.on_game_start_signal(data)

        elif action == "recover_game":
            if self.active_room:
                self.active_room["status"] = "In Game"
                if data.get("room_adv"):
                    self.active_room["room_adv"] = data.get("room_adv")
                if data.get("host_ip"):
                    self.active_room["host_ip"] = data.get("host_ip")
                if self.on_room_state_changed:
                    self.on_room_state_changed(self.active_room)
            if not self.is_host and self.on_recovery_signal:
                self.on_recovery_signal(data)

    def stop(self):
        self.leave_active_room()
        self.sig.disconnect()
        self.running = False
