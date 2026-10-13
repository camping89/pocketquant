"""Unit tests for exness_spike.py: signer, key loading, URL allowlist, redaction, clock."""

from __future__ import annotations

import base64
import email.utils
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.exness_spike import (
    ServerClock,
    allowed_access_point,
    body_hash,
    load_secret_key,
    redact,
    sign_headers,
    validate_base_url,
    ws_url,
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


def test_validate_base_url_accepts_https_on_confirmed_host() -> None:
    assert validate_base_url("https://api.example.test/", "api.example.test") == (
        "https://api.example.test"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test",
        "https://evil.test",
        "https://u:p@api.example.test",
        "https://api.example.test/?x=1",
    ],
)
def test_validate_base_url_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_base_url(url, "api.example.test")


def test_ws_url_switches_scheme_and_appends_path() -> None:
    assert ws_url("https://api.example.test", "/v1/x") == "wss://api.example.test/v1/x"


def test_allowed_access_point_accepts_exness_subdomain() -> None:
    assert allowed_access_point("ap-x.trading.exness.com") == "ap-x.trading.exness.com"


@pytest.mark.parametrize("url", ["https://ap-x.exness.com", "https://ap-x.exness.com/"])
def test_allowed_access_point_accepts_plain_https_url(url: str) -> None:
    assert allowed_access_point(url) == "ap-x.exness.com"


@pytest.mark.parametrize(
    "host",
    [
        "exness.com.evil.test",
        "evil.test",
        "http://ap-x.exness.com",
        "https://ap-x.exness.com.evil.test",
        "https://u:p@ap-x.exness.com",
        "https://ap-x.exness.com:8443",
        "https://ap-x.exness.com/v1",
    ],
)
def test_allowed_access_point_rejects_foreign_hosts(host: str) -> None:
    with pytest.raises(ValueError):
        allowed_access_point(host)


def test_redact_masks_identity_and_money_but_keeps_currency() -> None:
    result = redact(
        {
            "account_id": "9",
            "items": [{"deal": {"profit": {"amount": "-12.5", "currency": "USD"}, "deal_id": "7"}}],
        }
    )

    deal = result["items"][0]["deal"]
    assert result["account_id"] == "REDACTED"
    assert deal["profit"]["amount"] == "0.00"
    assert deal["profit"]["currency"] == "USD"
    assert deal["deal_id"] == "REDACTED"


def test_server_clock_tracks_offset_from_date_header() -> None:
    clock = ServerClock()

    clock.update_from_date_header(email.utils.formatdate(time.time() + 5, usegmt=True))

    assert 4000 <= clock.offset_ms <= 6000
