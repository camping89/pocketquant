"""Exness Trader API request signing: Ed25519 over a canonical JSON payload.

The signed payload carries the method, the path with its query (never the host)
and a hash of the exact body bytes, so a request must be sent exactly as signed.
"""

from __future__ import annotations

import base64
import email.utils
import hashlib
import json
import re
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def load_secret_key(material: str) -> Ed25519PrivateKey:
    text = material.strip()
    if "BEGIN" in text:
        raise ValueError(
            "EXNESS_SECRET_KEY must be the 128-hex secret from Key Management, not PEM"
        )
    if not re.fullmatch(r"[0-9a-fA-F]{128}", text):
        raise ValueError("unsupported Ed25519 key format")
    raw = bytes.fromhex(text)
    key = Ed25519PrivateKey.from_private_bytes(raw[:32])
    if key.public_key().public_bytes_raw() != raw[32:]:
        raise ValueError("unsupported Ed25519 key format")
    return key


def body_hash(body: bytes) -> str:
    return _b64url_nopad(hashlib.sha256(body).digest())


def sign_headers(
    *,
    api_key: str,
    private_key: Ed25519PrivateKey,
    method: str,
    path_with_query: str,
    body: bytes,
    idempotency_key: str,
    timestamp_ms: int,
) -> dict[str, str]:
    payload = {
        "api_key": api_key,
        "idempotency_key": idempotency_key,
        "timestamp": timestamp_ms,
        "sign_version": 1,
        "method": method.upper(),
        "path": path_with_query,
        "body_hash": body_hash(body),
    }
    data_bytes = json.dumps(payload, separators=(",", ":")).encode()
    return {
        "EXN-API-KEY": api_key,
        "EXN-IDEMPOTENCY-KEY": idempotency_key,
        "EXN-TIMESTAMP": str(timestamp_ms),
        "EXN-SIGN-VERSION": "1",
        "EXN-DATA": _b64url_nopad(data_bytes),
        "EXN-SIGN": _b64url_nopad(private_key.sign(data_bytes)),
    }


@dataclass
class ServerClock:
    offset_ms: int = 0

    def update_from_date_header(self, value: str) -> None:
        server_ms = int(email.utils.parsedate_to_datetime(value).timestamp() * 1000)
        self.offset_ms = server_ms - int(time.time() * 1000)

    def now_ms(self) -> int:
        return int(time.time() * 1000) + self.offset_ms
