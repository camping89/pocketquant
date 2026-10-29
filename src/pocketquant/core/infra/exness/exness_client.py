"""Signed REST client for the Exness Trader API — the only path to Exness endpoints.

Every call except the access-point discovery goes to the per-account access
point, which is discovered once and again after a transport failure or a 421:
the base host answers account routes with a bare 404. Data calls are spaced by
the strictest published rate with headroom; order calls have their own lane. A
429 on a data call is retried a bounded number of times, a 429 on an order call
never is. Order calls are
refused while ``EXNESS_LIVE_TRADING`` is false, before any network use.

Headers, keys and signed bodies are never logged.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.parse
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time.simulation import get_current_time
from pocketquant.core.config import Settings
from pocketquant.core.infra.exness.exness_signer import (
    ServerClock,
    load_secret_key,
    sign_headers,
)

logger = get_logger(__name__)

EXNESS_API_HOST = "api.exness.com"

_ENDPOINTS: dict[str, tuple[str, str]] = {
    "getAccessPoint": ("GET", "/v1/trading/access-point"),
    "getLimits": ("GET", "/v1/configuration/accounts/{account_id}/limits"),
    "getAccountDetails": ("GET", "/v1/configuration/accounts/{account_id}/account"),
    "getAvailableInstrumentList": ("GET", "/v1/configuration/accounts/{account_id}/instruments"),
    "getInstrumentCondition": (
        "GET",
        "/v1/configuration/accounts/{account_id}/instruments/{instrument}/conditions",
    ),
    "getCandleHistory": ("GET", "/v1/market-data/accounts/{account_id}/candles"),
    "getTradingStateSnapshot": ("GET", "/v1/trading/accounts/{account_id}/snapshot"),
    "getDealsHistory": ("GET", "/v1/history/accounts/{account_id}/deals"),
    "getOperationStatus": (
        "GET",
        "/v1/trading/accounts/{account_id}/operations/{operation_id}",
    ),
    "openPosition": ("POST", "/v1/trading/accounts/{account_id}/positions"),
}
_ORDER_OPS = frozenset({"openPosition"})
_PRIORITY_OPS = _ORDER_OPS | {"getOperationStatus"}
_BOOTSTRAP_OPS = frozenset({"getAccessPoint", "getLimits"})
_RATE_LIMIT_RETRIES = 3
_TRANSPORT_ATTEMPTS = 3
# Spacing for the calls made before the published limits are known.
_BOOTSTRAP_INTERVAL_S = 1.0
_HTTP_TIMEOUT_S = 10.0
_CACHE_TTL_S = 3600.0
_REQUIRED_SETTINGS = (
    "exness_api_base_url",
    "exness_account_id",
    "exness_api_key",
    "exness_secret_key",
)


def validate_base_url(url: str, api_host: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != api_host
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("EXNESS_API_BASE_URL must be https on the confirmed host")
    return url.rstrip("/")


def allowed_access_point(value: str) -> str:
    host = value.strip().lower()
    if "://" in host:
        parts = urllib.parse.urlsplit(host)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.port is not None
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in ("", "/")
        ):
            raise ValueError("access point must be a plain https URL or host")
        host = parts.hostname
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.(exness\.com|exness-api\.com)", host):
        raise ValueError("access point host is not an Exness host")
    return host


def ws_url(base_url: str, path: str) -> str:
    parts = urllib.parse.urlsplit(base_url)
    return urllib.parse.urlunsplit(("wss", parts.netloc, parts.path.rstrip("/") + path, "", ""))


def min_request_interval(limits: dict[str, Any]) -> float:
    rest = limits["limits"]["rest"]
    rates = [rest["global_account_rate"]] + [m["rate_limit"] for m in rest["methods"]]
    # 20% headroom so a sliding window never sees two requests inside one slot.
    return max(r["window_seconds"] / r["limit"] for r in rates) * 1.2


def order_request_interval(limits: dict[str, Any], fraction: float) -> float:
    rest = limits["limits"]["rest"]
    own = max(
        m["rate_limit"]["window_seconds"] / m["rate_limit"]["limit"]
        for m in rest["methods"]
        if m["api_operation_id"] in ("openPosition", "getOperationStatus")
    )
    shared = rest["global_account_rate"]["window_seconds"] / rest["global_account_rate"]["limit"]
    # Only the trader sends order calls, so their own limits are not scaled by the
    # fraction; the account-wide limit is.
    return max(own * 1.2, shared * 1.2 / fraction)


def history_age_days(limits: dict[str, Any]) -> int:
    for method in limits["limits"]["rest"]["methods"]:
        if method["api_operation_id"] == "getDealsHistory":
            return int(method.get("limits", {}).get("history_age_days", 30))
    return 30


def max_candles(limits: dict[str, Any]) -> int:
    for method in limits["limits"]["rest"]["methods"]:
        if method["api_operation_id"] == "getCandleHistory":
            return int(method.get("limits", {}).get("max_candles_per_request", 1000))
    return 1000


class ExnessApiError(Exception):
    """An Exness call that did not succeed. ``status`` 0 means no HTTP answer."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class _RequestPacer:
    """Lets requests leave one at a time, at least ``min_interval_s`` apart, in arrival order."""

    def __init__(
        self,
        min_interval_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.min_interval_s = min_interval_s
        self._clock = clock
        self._sleep = sleep
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._next_at - self._clock()
            if delay > 0:
                await self._sleep(delay)
            self._next_at = self._clock() + self.min_interval_s


class ExnessClient:
    """Signed, paced REST access to one Exness account. Builds no request until used."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S)
        self._clock = ServerClock()
        self._base_url = ""
        self._account_id = ""
        self._api_key = ""
        self._private_key: Ed25519PrivateKey | None = None
        self._access_point: str | None = None
        self._access_point_lock = asyncio.Lock()
        self._bootstrap_pacer = _RequestPacer(_BOOTSTRAP_INTERVAL_S)
        self._data_pacer: _RequestPacer | None = None
        self._order_pacer: _RequestPacer | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self.is_configured = self._configure()

    def _configure(self) -> bool:
        s = self._settings
        setting = _REQUIRED_SETTINGS[0]
        try:
            for setting in _REQUIRED_SETTINGS:
                if not _text(getattr(s, setting)):
                    raise ValueError(setting)
            setting = "exness_api_base_url"
            self._base_url = validate_base_url(_text(s.exness_api_base_url), EXNESS_API_HOST)
            setting = "exness_secret_key"
            self._private_key = load_secret_key(_text(s.exness_secret_key))
        except ValueError:
            logger.warning("exness.not_configured", setting=setting)
            return False
        self._account_id = _text(s.exness_account_id)
        self._api_key = _text(s.exness_api_key)
        return True

    @property
    def account_id(self) -> str:
        return self._account_id

    async def access_point(self) -> str:
        """The account's access-point host, discovered again after a transport failure or 421."""
        if self._access_point is not None:
            return self._access_point
        async with self._access_point_lock:
            if self._access_point is None:
                body = await self.call("getAccessPoint", params={"account_id": self._account_id})
                self._access_point = allowed_access_point(str(body.get("access_point", "")))
        return self._access_point

    async def call(
        self,
        op: str,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        idempotency_key: str = "",
        deadline: datetime | None = None,
    ) -> dict[str, Any]:
        """Send operation ``op`` and return its JSON body; never send it at or after ``deadline``.

        Raises:
            ExnessApiError: not configured, live trading off for an order call,
                deadline passed, transport failure, exhausted 429 retries, or any non-2xx
                answer.
        """
        if not self.is_configured:
            raise ExnessApiError(0, "NOT_CONFIGURED", "exness settings missing or invalid")
        if op in _ORDER_OPS and not self._settings.exness_live_trading:
            raise ExnessApiError(0, "LIVE_TRADING_DISABLED", "EXNESS_LIVE_TRADING is false")
        method, template = _ENDPOINTS[op]
        if op == "getAccessPoint":
            base = self._base_url
        else:
            base = f"https://{await self.access_point()}"
        path = template.format(account_id=self._account_id, **(path_params or {}))
        target = f"{path}?{urllib.parse.urlencode(params)}" if params else path
        body = b"" if json_body is None else json.dumps(json_body, separators=(",", ":")).encode()
        try:
            response = await self._send_paced(
                op, method, base + target, body, idempotency_key, deadline
            )
        except ExnessApiError as e:
            if e.code == "TRANSPORT":
                self._access_point = None
                logger.warning("exness.access_point_reset", reason="transport", op=op)
            raise
        if response.is_success:
            return response.json() if response.content else {}
        if response.status_code == 421:
            self._access_point = None
            logger.warning("exness.access_point_reset", reason="421", op=op)
        raise _api_error(response)

    async def _send_paced(
        self,
        op: str,
        method: str,
        url: str,
        body: bytes,
        idempotency_key: str,
        deadline: datetime | None,
    ) -> httpx.Response:
        pacer = await self._pacer_for(op)
        attempt = 0
        while True:
            await pacer.wait()
            if deadline is not None and get_current_time() >= deadline:
                raise ExnessApiError(0, "ORDER_DEADLINE", f"{op} deadline passed before send")
            response = await self._send(method, url, body, idempotency_key, deadline)
            if response.status_code != 429:
                return response
            # The published limits are cluster-wide, so a 429 can arrive under them.
            if op in _ORDER_OPS or attempt == _RATE_LIMIT_RETRIES:
                logger.warning("exness.rate_limited", op=op)
                raise ExnessApiError(429, "REQUEST_RATE_LIMIT", f"{op} rate limited")
            retry_after = response.headers.get("retry-after", "")
            delay = int(retry_after) if retry_after.isdigit() else 2**attempt
            attempt += 1
            logger.warning("exness.rate_limited_retry", op=op, attempt=attempt)
            await asyncio.sleep(delay)

    async def _send(
        self, method: str, url: str, body: bytes, idempotency_key: str, deadline: datetime | None
    ) -> httpx.Response:
        """One signed request.

        Transport failures retried with the same idempotency key, never after the deadline.
        """
        headers = {"Content-Type": "application/json"} if body else {}
        for attempt in range(_TRANSPORT_ATTEMPTS):
            request = self._http.build_request(method, url, content=body or None, headers=headers)
            request.headers.update(
                self._sign(method, request.url.raw_path.decode(), body, idempotency_key)
            )
            try:
                response = await self._http.send(request)
            except httpx.TransportError as exc:
                if attempt == _TRANSPORT_ATTEMPTS - 1:
                    raise ExnessApiError(0, "TRANSPORT", type(exc).__name__) from exc
                await asyncio.sleep(2**attempt)
                if deadline is not None and get_current_time() >= deadline:
                    raise ExnessApiError(0, "TRANSPORT", type(exc).__name__) from exc
                continue
            if date := response.headers.get("date"):
                self._clock.update_from_date_header(date)
            return response
        raise AssertionError("unreachable")  # pragma: no cover

    def _sign(self, method: str, path: str, body: bytes, idempotency_key: str) -> dict[str, str]:
        assert self._private_key is not None
        return sign_headers(
            api_key=self._api_key,
            private_key=self._private_key,
            method=method,
            path_with_query=path,
            body=body,
            idempotency_key=idempotency_key,
            timestamp_ms=self._clock.now_ms(),
        )

    async def _pacer_for(self, op: str) -> _RequestPacer:
        if self._data_pacer is None or self._order_pacer is None:
            if op in _BOOTSTRAP_OPS:
                return self._bootstrap_pacer
            limits = await self.limits()
            fraction = self._settings.exness_rate_fraction
            if self._data_pacer is None or self._order_pacer is None:
                self._data_pacer = _RequestPacer(min_request_interval(limits) / fraction)
                self._order_pacer = _RequestPacer(order_request_interval(limits, fraction))
        return self._order_pacer if op in _PRIORITY_OPS else self._data_pacer

    async def _cached(self, key: str, fetch: Callable[[], Awaitable[Any]]) -> Any:
        hit = self._cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < _CACHE_TTL_S:
            return hit[1]
        value = await fetch()
        self._cache[key] = (time.monotonic(), value)
        return value

    async def limits(self) -> dict[str, Any]:
        return await self._cached("limits", lambda: self.call("getLimits"))

    async def instruments(self) -> list[str]:
        body = await self._cached("instruments", lambda: self.call("getAvailableInstrumentList"))
        return list(body.get("instruments", []))

    async def conditions(self, instrument: str) -> dict[str, Any]:
        return await self._cached(
            f"conditions:{instrument}",
            lambda: self.call("getInstrumentCondition", path_params={"instrument": instrument}),
        )

    async def deals_window_days(self) -> int:
        # The API rejects a window of exactly history_age_days.
        return history_age_days(await self.limits()) - 1

    def sign_ws_headers(self, path: str) -> dict[str, str]:
        """Handshake headers: a WS handshake is signed as a GET over the path."""
        return self._sign("GET", path, b"", "")

    async def ws_url(self, path: str) -> str:
        return ws_url(f"https://{await self.access_point()}", path)

    async def close(self) -> None:
        await self._http.aclose()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return str(value).strip()


def _api_error(response: httpx.Response) -> ExnessApiError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    status = response.status_code
    return ExnessApiError(
        status,
        code=str(body.get("error_message") or f"HTTP_{status}"),
        message=str(body.get("code", "")),
    )
