"""Exercise the deployed API through verified TLS; no game/client settings touched."""
import json
import secrets
import ssl
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://37.27.115.231:8050"
CONTEXT = ssl.create_default_context(cafile=str(Path(__file__).with_name("server-ca.crt")))


def call(path, data=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
    try:
        response = urllib.request.urlopen(req, context=CONTEXT, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = json.load(response)
        assert response.status == expected, (path, response.status, body)
        return body


def main():
    suffix = secrets.token_hex(5)
    names = ["check_host_" + suffix, "check_peer_" + suffix]
    result_path = Path(__file__).parents[1] / "deploy" / "smoke-result.json"
    result = {"test_users": names, "status": "started"}
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tokens = []
    for name in names:
        credentials = {"username": name, "password": secrets.token_urlsafe(24)}
        call("/api/auth/register", credentials, expected=201)
        tokens.append(call("/api/auth/login", credentials)["token"])
    host, peer = tokens
    rid = call("/api/rooms", {"name": "Deployment verification", "map_name": "DotA LoD 6.85m", "capacity": 2}, host, 201)["room_id"]
    base = "/api/rooms/" + rid
    call(base + "/messages", {"text": "must reject non-member"}, peer, 403)
    call(base + "/join", {}, peer)
    call(base + "/heartbeat", {}, peer, 403)
    call(base + "/heartbeat", {}, host)
    call(base + "/messages", {"text": "isolated server test"}, peer, 201)
    messages = call(base + "/messages", token=host)["messages"]
    assert messages[-1]["username"] == names[1]
    assert messages[-1]["text"] == "isolated server test"
    assert any(r["id"] == rid and r["players"] == 2 for r in call("/api/rooms", token=peer)["rooms"])
    call(base + "/leave", {}, host)
    for token in tokens:
        call("/api/auth/logout", {}, token)
        call("/api/rooms", token=token, expected=401)
    latency = []
    for _ in range(10):
        start = time.perf_counter()
        call("/healthz")
        latency.append((time.perf_counter() - start) * 1000)
    result.update(status="passed", health_roundtrip_ms_median=round(statistics.median(latency), 1),
                  health_roundtrip_ms_max=round(max(latency), 1))
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
