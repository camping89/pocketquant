from __future__ import annotations

import base64
import email.utils
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pocketquant.core.infra.exness.exness_signer import (
    ServerClock,
    body_hash,
    load_secret_key,
    sign_headers,
)


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_body_hash_of_empty_body_matches_spec_example() -> None:
    assert body_hash(b"") == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"


def test_sign_headers_produces_verifiable_unpadded_signature() -> None:
    key = Ed25519PrivateKey.generate()
    path = "/v1/configuration/accounts/1/account"
    headers = sign_headers(
        api_key="k",
        private_key=key,
        method="get",
        path_with_query=path,
        body=b"",
        idempotency_key="",
        timestamp_ms=1773656070123,
    )

    assert "=" not in headers["EXN-DATA"]
    assert "=" not in headers["EXN-SIGN"]
    assert headers["EXN-IDEMPOTENCY-KEY"] == ""
    assert headers["EXN-TIMESTAMP"] == "1773656070123"
    assert headers["EXN-SIGN-VERSION"] == "1"
    data = _b64url_decode(headers["EXN-DATA"])
    assert json.loads(data) == {
        "api_key": "k",
        "idempotency_key": "",
        "timestamp": 1773656070123,
        "sign_version": 1,
        "method": "GET",
        "path": path,
        "body_hash": "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU",
    }
    key.public_key().verify(_b64url_decode(headers["EXN-SIGN"]), data)


def test_load_secret_key_accepts_seed_plus_matching_public_key() -> None:
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes_raw()
    pub = key.public_key().public_bytes_raw()

    loaded = load_secret_key(f"  {(seed + pub).hex()}\n")

    assert loaded.public_key().public_bytes_raw() == pub


def test_load_secret_key_rejects_mismatched_public_half() -> None:
    seed = Ed25519PrivateKey.generate().private_bytes_raw()

    with pytest.raises(ValueError):
        load_secret_key((seed + bytes(32)).hex())


def test_load_secret_key_rejects_pem_without_echoing_it() -> None:
    pem = (
        Ed25519PrivateKey.generate()
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )

    with pytest.raises(ValueError) as exc:
        load_secret_key(pem)

    assert "not PEM" in str(exc.value)
    assert "BEGIN" not in str(exc.value)


def test_load_secret_key_rejects_garbage_without_echoing_it() -> None:
    with pytest.raises(ValueError) as exc:
        load_secret_key("not-a-key-SECRET")

    assert "SECRET" not in str(exc.value)


def test_server_clock_tracks_offset_from_date_header() -> None:
    clock = ServerClock()

    clock.update_from_date_header(email.utils.formatdate(time.time() + 5, usegmt=True))

    assert 4000 <= clock.offset_ms <= 6000
