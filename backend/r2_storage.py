"""Cloudflare R2 (S3-compatible) storage & AWS SigV4 Presigned URL helper for MongolRanger.

Uses isolated prefix `mongolranger/` inside the R2 bucket so existing Kora objects (`org/...`)
are 100% untouched. Zero external dependencies (pure Python stdlib hmac/hashlib/urllib).
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET


def _load_local_r2_secrets() -> dict[str, str]:
    for candidate in (
        Path(__file__).resolve().parent / ".r2_secrets.json",
        Path("/var/lib/mongolranger/r2_secrets.json"),
    ):
        try:
            if candidate.is_file():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


_LOCAL_SECRETS = _load_local_r2_secrets()

R2_ACCOUNT_ID = os.environ.get(
    "MONGOLRANGER_R2_ACCOUNT_ID",
    _LOCAL_SECRETS.get("MONGOLRANGER_R2_ACCOUNT_ID", ""),
).strip()
R2_BUCKET = os.environ.get(
    "MONGOLRANGER_R2_BUCKET",
    _LOCAL_SECRETS.get("MONGOLRANGER_R2_BUCKET", "kora"),
).strip()
R2_ACCESS_KEY_ID = os.environ.get(
    "MONGOLRANGER_R2_ACCESS_KEY_ID",
    _LOCAL_SECRETS.get("MONGOLRANGER_R2_ACCESS_KEY_ID", ""),
).strip()
R2_SECRET_ACCESS_KEY = os.environ.get(
    "MONGOLRANGER_R2_SECRET_ACCESS_KEY",
    _LOCAL_SECRETS.get("MONGOLRANGER_R2_SECRET_ACCESS_KEY", ""),
).strip()
R2_PREFIX = "mongolranger/"


def is_r2_configured() -> bool:
    return bool(R2_ACCOUNT_ID and R2_BUCKET and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signing_key(secret: str, date_stamp: str, region: str = "auto", service: str = "s3") -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def normalize_r2_key(key: str) -> str:
    clean = key.lstrip("/")
    if not clean.startswith(R2_PREFIX):
        clean = R2_PREFIX + clean
    return clean


def presign_r2_url(
    method: str,
    key: str,
    expires_sec: int = 21600,
    download_filename: str | None = None,
) -> str:
    """Generate an AWS Signature V4 presigned URL (GET or PUT) for Cloudflare R2."""
    r2_key = normalize_r2_key(key)
    host = f"{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"

    encoded_key = urllib.parse.quote(r2_key, safe="/-_.~")
    canonical_uri = f"/{R2_BUCKET}/{encoded_key}"

    query_params: dict[str, str] = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{R2_ACCESS_KEY_ID}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_sec),
        "X-Amz-SignedHeaders": "host",
    }
    if download_filename and method.upper() == "GET":
        safe_fn = download_filename.replace('"', "")
        query_params["response-content-disposition"] = f'attachment; filename="{safe_fn}"'

    sorted_items = sorted(query_params.items(), key=lambda kv: kv[0])
    canonical_querystring = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in sorted_items
    )

    canonical_headers = f"host:{host}\n"
    signed_headers = "host"
    payload_hash = "UNSIGNED-PAYLOAD"

    canonical_request = "\n".join([
        method.upper(),
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    signing_key = _get_signing_key(R2_SECRET_ACCESS_KEY, date_stamp)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return f"https://{host}{canonical_uri}?{canonical_querystring}&X-Amz-Signature={signature}"


def upload_bytes_to_r2(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to R2 under `mongolranger/` prefix using a presigned PUT URL."""
    r2_key = normalize_r2_key(key)
    put_url = presign_r2_url("PUT", r2_key, expires_sec=3600)
    req = urllib.request.Request(
        put_url,
        data=data,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
            "User-Agent": "MongolRanger-R2/1.0",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        if resp.status not in (200, 201, 204):
            raise RuntimeError(f"R2 PUT returned HTTP {resp.status}")
    return f"r2://{r2_key}"


def ensure_bucket_cors() -> bool:
    """Ensure mongolranger.com is in the R2 bucket CORS origins while preserving existing Kora origins."""
    cf_token = os.environ.get(
        "MONGOLRANGER_CF_API_TOKEN",
        _LOCAL_SECRETS.get("MONGOLRANGER_CF_API_TOKEN", ""),
    ).strip()
    if not cf_token or not R2_ACCOUNT_ID or not R2_BUCKET:
        return False
    import json

    url = f"https://api.cloudflare.com/client/v4/accounts/{R2_ACCOUNT_ID}/r2/buckets/{R2_BUCKET}/cors"
    headers = {
        "Authorization": f"Bearer {cf_token}",
        "Content-Type": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rules = (data.get("result") or {}).get("rules") or []
        if rules:
            origins = list(rules[0].get("allowed", {}).get("origins", []))
        else:
            origins = [
                "https://kora.mn",
                "https://www.kora.mn",
                "https://socialpaywall-cms.web.app",
                "http://localhost:3000",
            ]
        needed = ["https://mongolranger.com", "https://www.mongolranger.com", "http://localhost:8050"]
        changed = False
        for o in needed:
            if o not in origins:
                origins.append(o)
                changed = True
        if not changed and rules:
            return True
        payload = {
            "rules": [
                {
                    "allowed": {
                        "origins": origins,
                        "methods": ["GET", "PUT", "HEAD"],
                        "headers": ["*"],
                    },
                    "exposeHeaders": ["ETag"],
                    "maxAgeSeconds": 3600,
                }
            ]
        }
        put_req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="PUT",
        )
        with urllib.request.urlopen(put_req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception:
        return False

