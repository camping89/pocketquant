"""Read-only Exness Trader API spike: limits, instruments, sessions, candles, deals, ticks.

Signs GET requests and WebSocket handshakes with the Ed25519 key from the environment,
writes redacted JSON fixtures to ``--out`` and prints ``summary.json``. It never places,
modifies or closes an order.

Usage (inside the app container, where the env comes from ``deploy/.env``):
    python scripts/exness_spike.py --check-config --api-host HOST
    python scripts/exness_spike.py --api-host HOST --out DIR [--tick-seconds 600]

Env: EXNESS_API_BASE_URL, EXNESS_ACCOUNT_ID, EXNESS_API_KEY, EXNESS_SECRET_KEY.
Values are never printed.

Exit codes: 0 = success, 2 = HTTP 401/403, 3 = other HTTP error, 4 = missing or invalid settings.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import statistics
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidHandshake, InvalidStatus
from websockets.typing import Subprotocol

from pocketquant.core.domain.bar.services.bar_builder_domain_service import is_bar_aligned
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.risk.value_objects import RiskConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.shared.value_objects import INTERVAL_SECONDS
from pocketquant.core.infra.exness.exness_client import (
    allowed_access_point,
    history_age_days,
    max_candles,
    min_request_interval,
    validate_base_url,
    ws_url,
)
from pocketquant.core.infra.exness.exness_signer import (
    ServerClock,
    load_secret_key,
    sign_headers,
)

IDENTITY_KEYS = frozenset(
    {
        "account_id",
        "account_name",
        "login",
        "position_id",
        "order_id",
        "deal_id",
        "operation_id",
        "client_request_id",
    }
)
MONEY_KEYS = frozenset(
    {
        "balance",
        "equity",
        "used_margin",
        "free_margin",
        "margin_level",
        "credit",
        "amount",
        "commission",
        "swap",
    }
)
TIMEFRAMES = {
    "M1": Interval.MINUTE_1,
    "M5": Interval.MINUTE_5,
    "M15": Interval.MINUTE_15,
    "H1": Interval.HOUR_1,
    "H4": Interval.HOUR_4,
    "D1": Interval.DAY_1,
}
WS_SUBPROTOCOL = Subprotocol("exness-ws-protocol")
RATE_LIMIT_RETRIES = 3
ENV_KEYS = ("EXNESS_API_BASE_URL", "EXNESS_ACCOUNT_ID", "EXNESS_API_KEY", "EXNESS_SECRET_KEY")


class ApiError(Exception):
    def __init__(self, status: int, error_message: str) -> None:
        super().__init__(error_message)
        self.status = status
        self.error_message = error_message


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            scalar = not isinstance(value, dict | list)
            if key in IDENTITY_KEYS and scalar:
                out[key] = "REDACTED"
            elif key in MONEY_KEYS and scalar:
                out[key] = "0.00"
            else:
                out[key] = redact(value)
        return out
    if isinstance(obj, list):
        return [redact(item) for item in obj]
    return obj


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Exness Trader API spike.")
    parser.add_argument("--api-host", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--tick-seconds", type=int, default=600)
    parser.add_argument("--instruments", default="XAUUSD,EURUSD,BTCUSD")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args(argv)
    if not args.check_config and args.out is None:
        parser.error("--out is required unless --check-config")
    return args


@dataclass
class SpikeConfig:
    base_url: str
    account_id: str
    api_key: str
    private_key: Ed25519PrivateKey
    out: Path
    tick_seconds: int
    instruments: list[str]


def check_config(env: dict[str, str], api_host: str) -> dict[str, bool]:
    flags = {"base_url_valid": False, "secret_key_valid": False}
    with contextlib.suppress(ValueError):
        validate_base_url(env.get("EXNESS_API_BASE_URL", ""), api_host)
        flags["base_url_valid"] = True
    with contextlib.suppress(ValueError):
        load_secret_key(env.get("EXNESS_SECRET_KEY", ""))
        flags["secret_key_valid"] = True
    result = {
        "base_url_valid": flags["base_url_valid"],
        "account_id_set": bool(env.get("EXNESS_ACCOUNT_ID", "").strip()),
        "api_key_set": bool(env.get("EXNESS_API_KEY", "").strip()),
        "secret_key_valid": flags["secret_key_valid"],
    }
    result["configured"] = all(result.values())
    return result


def build_config(args: argparse.Namespace, env: dict[str, str]) -> SpikeConfig:
    missing = [k for k in ENV_KEYS if not env.get(k, "").strip()]
    if missing:
        raise ValueError(f"missing settings: {', '.join(missing)}")
    return SpikeConfig(
        base_url=validate_base_url(env["EXNESS_API_BASE_URL"].strip(), args.api_host),
        account_id=env["EXNESS_ACCOUNT_ID"].strip(),
        api_key=env["EXNESS_API_KEY"].strip(),
        private_key=load_secret_key(env["EXNESS_SECRET_KEY"]),
        out=args.out,
        tick_seconds=args.tick_seconds,
        instruments=[i.strip().upper() for i in args.instruments.split(",") if i.strip()],
    )


@dataclass
class Session:
    cfg: SpikeConfig
    client: httpx.AsyncClient
    clock: ServerClock = field(default_factory=ServerClock)
    min_interval_s: float = 0.0
    ap_base: str | None = None
    rate_limited_retries: int = 0
    _last_request_at: float = 0.0

    def signed(self, method: str, path_with_query: str) -> dict[str, str]:
        return sign_headers(
            api_key=self.cfg.api_key,
            private_key=self.cfg.private_key,
            method=method,
            path_with_query=path_with_query,
            body=b"",
            idempotency_key="",
            timestamp_ms=self.clock.now_ms(),
        )

    async def get(
        self, path: str, params: dict[str, Any] | None = None, base: str | None = None
    ) -> tuple[int, Any]:
        target = f"{path}?{urllib.parse.urlencode(params)}" if params else path
        url = (base or self.ap_base or self.cfg.base_url) + target
        attempt = 0
        while True:
            wait = self._last_request_at + self.min_interval_s - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            request = self.client.build_request("GET", url)
            request.headers.update(self.signed("GET", request.url.raw_path.decode()))
            response = await self.client.send(request)
            self._last_request_at = time.monotonic()
            if date := response.headers.get("date"):
                self.clock.update_from_date_header(date)
            if response.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
                break
            # The published limits are cluster-wide, so a 429 can arrive under them.
            self.rate_limited_retries += 1
            retry_after = response.headers.get("retry-after", "")
            await asyncio.sleep(int(retry_after) if retry_after.isdigit() else 2**attempt)
            attempt += 1
        return response.status_code, _json_or_none(response)

    async def get_ok(
        self, path: str, params: dict[str, Any] | None = None, base: str | None = None
    ) -> Any:
        status, body = await self.get(path, params, base)
        if status != 200:
            message = body.get("error_message") if isinstance(body, dict) else None
            raise ApiError(status, str(message or f"HTTP_{status}"))
        return body


def _json_or_none(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def write_json(cfg: SpikeConfig, name: str, obj: Any) -> None:
    text = json.dumps(redact(obj), indent=2, ensure_ascii=False)
    (cfg.out / name).write_text(text.replace(cfg.account_id, "0"), encoding="utf-8")


def iso_seconds(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).replace(microsecond=0).isoformat()


def resolve_names(instruments: list[str], codes: list[str]) -> dict[str, str | None]:
    names: dict[str, str | None] = {}
    for code in codes:
        names[code] = next(
            (n for n in instruments if n.upper() == code or n.upper().startswith(code)), None
        )
    return names


async def resolve_access_point(s: Session) -> str | None:
    status, body = await s.get("/v1/trading/access-point", {"account_id": s.cfg.account_id})
    write_json(s.cfg, "access_point.json", body)
    if status in (401, 403):
        message = body.get("error_message") if isinstance(body, dict) else None
        raise ApiError(status, str(message or f"HTTP_{status}"))
    if status == 200 and isinstance(body, dict) and body.get("access_point"):
        return "https://" + allowed_access_point(str(body["access_point"]))
    return None


def rate_limits(limits: dict[str, Any]) -> dict[str, Any]:
    rest = limits["limits"]["rest"]
    out: dict[str, Any] = {m["api_operation_id"]: m["rate_limit"] for m in rest["methods"]}
    out["global_account_rate"] = rest["global_account_rate"]
    out["websocket"] = limits["limits"]["websocket"]
    return out


def candle_stats(candles: list[dict[str, Any]], tf: str, fetched_at: datetime) -> dict[str, Any]:
    if not candles:
        return {
            "count": 0,
            "first_time": None,
            "last_time": None,
            "all_aligned": True,
            "last_in_progress": False,
        }
    interval = TIMEFRAMES[tf]
    times = [datetime.fromisoformat(c["time"]) for c in candles]
    # The spike probes whether Exness candles sit on the plain UTC-epoch grid,
    # which is exactly the 24/7 calendar's grid.
    calendar = Continuous24x7Calendar()
    return {
        "count": len(candles),
        "first_time": times[0].isoformat(),
        "last_time": times[-1].isoformat(),
        "all_aligned": all(is_bar_aligned(t, interval, calendar) for t in times),
        "last_in_progress": times[-1] + timedelta(seconds=INTERVAL_SECONDS[interval]) > fetched_at,
    }


def condition_summary(cond: dict[str, Any]) -> dict[str, Any]:
    keys = ("contract_size", "volume_min", "volume_step", "volume_max", "point_digits")
    out = {k: cond.get(k) for k in keys}
    out["trade_mode"] = cond.get("trade_mode")
    out["trade_sessions"] = cond.get("trade_sessions", [])
    return out


async def fetch_rest(s: Session, summary: dict[str, Any]) -> dict[str, Any]:
    cfg, acc = s.cfg, f"/v1/configuration/accounts/{s.cfg.account_id}"
    ap_base = await resolve_access_point(s)
    summary["access_point_resolved"] = ap_base is not None
    summary["rest_host"] = "access_point" if ap_base else "base"
    s.ap_base = ap_base
    limits = await s.get_ok(f"{acc}/limits")
    write_json(cfg, "limits.json", limits)
    s.min_interval_s = min_request_interval(limits)
    summary["max_candles_per_request"] = max_candles(limits)
    summary["history_age_days"] = history_age_days(limits)
    summary["rate_limits"] = rate_limits(limits)
    account = await s.get_ok(f"{acc}/account")
    write_json(cfg, "account.json", account)
    summary["account_currency"] = (account.get("settings") or {}).get("currency")
    instruments = await s.get_ok(f"{acc}/instruments")
    write_json(cfg, "instruments.json", instruments)
    names = resolve_names(list(instruments.get("instruments", [])), cfg.instruments)
    summary["instrument_names"] = names
    summary["conditions"] = {}
    for code, name in names.items():
        if name is None:
            continue
        cond = await s.get_ok(f"{acc}/instruments/{name}/conditions")
        write_json(cfg, f"conditions_{code}.json", cond)
        summary["conditions"][code] = condition_summary(cond)
    return {"ap_base": ap_base, "names": names}


async def fetch_candles(
    s: Session, summary: dict[str, Any], names: dict[str, str | None]
) -> dict[str, float]:
    path = f"/v1/market-data/accounts/{s.cfg.account_id}/candles"
    now_ms = s.clock.now_ms()
    fetched_at = datetime.fromisoformat(iso_seconds(now_ms))
    summary["fetched_at"] = fetched_at.isoformat()
    m1_count = -min(1000, summary["max_candles_per_request"])
    jobs = [(code, "M1", m1_count) for code, n in names.items() if n is not None]
    if names.get("XAUUSD"):
        jobs += [("XAUUSD", tf, -10) for tf in ("M5", "M15", "H1", "H4", "D1")]
    summary["candles"], last_close = {}, {}
    for code, tf, count in jobs:
        params = {
            "instrument": names[code],
            "timeframe": tf,
            "price_type": "bid",
            "from": fetched_at.isoformat(),
            "count": count,
        }
        body = await s.get_ok(path, params)
        write_json(s.cfg, f"candles_{code}_{tf}.json", body)
        candles = body.get("candles", [])
        summary["candles"][f"{code}_{tf}"] = candle_stats(candles, tf, fetched_at)
        if tf == "M1" and candles:
            last_close[code] = float(candles[-1]["close"])
    return last_close


async def fetch_account_state(s: Session, ap_base: str | None) -> float | None:
    snapshot = await s.get_ok(f"/v1/trading/accounts/{s.cfg.account_id}/snapshot", base=ap_base)
    write_json(s.cfg, "snapshot.json", snapshot)
    balance = (snapshot.get("account_state") or {}).get("balance")
    return float(balance) if balance is not None else None


async def fetch_deals(s: Session, summary: dict[str, Any]) -> None:
    path = f"/v1/history/accounts/{s.cfg.account_id}/deals"
    # The API rejects a window of exactly history_age_days, so stay one day inside it.
    days = max(1, summary["history_age_days"] - 1)
    since = iso_seconds(s.clock.now_ms() - days * 86_400_000)
    params: dict[str, Any] = {"from": since, "limit": 200}
    types: set[str] = set()
    for page in range(5):
        body = await s.get_ok(path, params)
        if page == 0:
            write_json(s.cfg, "deals.json", body)
        types.update(str(i["deal"].get("type")) for i in body.get("items", []) if i.get("deal"))
        if not body.get("has_more") or not body.get("next_cursor"):
            break
        params = {"cursor": body["next_cursor"], "limit": 200}
    summary["deal_types_seen"] = sorted(types)


def sizer_feasibility(
    summary: dict[str, Any], last_close: dict[str, float], balance: float | None
) -> None:
    exposure = RiskConfig().max_exposure_percent
    min_balance: dict[str, float | None] = {}
    reaches: dict[str, bool | None] = {}
    for code, cond in summary["conditions"].items():
        price = last_close.get(code)
        if price is None or cond["volume_min"] is None or cond["contract_size"] is None:
            min_balance[code], reaches[code] = None, None
            continue
        needed = float(cond["volume_min"]) * float(cond["contract_size"]) * price / exposure
        min_balance[code] = round(needed, 2)
        reaches[code] = None if balance is None else balance >= needed
    summary["sizer_min_balance"] = min_balance
    summary["sizer_reaches_min_lot"] = reaches


async def open_ws(s: Session, base: str, path: str) -> tuple[ClientConnection, str]:
    url = ws_url(base, path)
    try:
        ws = await connect(
            url, additional_headers=s.signed("GET", path), subprotocols=[WS_SUBPROTOCOL]
        )
        return ws, ws.subprotocol or "none"
    except InvalidHandshake:
        ws = await connect(url, additional_headers=s.signed("GET", path))
        return ws, "without_subprotocol"


async def open_ws_with_fallback(
    s: Session, ap_base: str | None, path: str
) -> tuple[ClientConnection, str, str]:
    try:
        ws, subprotocol = await open_ws(s, ap_base or s.cfg.base_url, path)
        return ws, subprotocol, "access_point" if ap_base else "base"
    except (InvalidHandshake, OSError) as exc:
        if ap_base is None:
            raise _ws_error(exc) from exc
    try:
        ws, subprotocol = await open_ws(s, s.cfg.base_url, path)
    except (InvalidHandshake, OSError) as exc:
        raise _ws_error(exc) from exc
    return ws, subprotocol, "base"


def _ws_error(exc: Exception) -> ApiError:
    if isinstance(exc, InvalidStatus):
        status = exc.response.status_code
        return ApiError(status, f"WS_HANDSHAKE_HTTP_{status}")
    return ApiError(0, "WS_HANDSHAKE_FAILED")


async def collect(ws: ClientConnection, seconds: float) -> list[Any]:
    frames: list[Any] = []
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            raw = await asyncio.wait_for(ws.recv(), remaining)
        except TimeoutError:
            break
        try:
            frames.append(json.loads(raw))
        except ValueError:
            frames.append({"raw": str(raw)[:200]})
    return frames


def tick_of(frame: Any) -> dict[str, Any] | None:
    if not isinstance(frame, dict):
        return None
    if "instrument" in frame and "bid" in frame and "ask" in frame:
        return frame
    for value in frame.values():
        if isinstance(value, dict) and (tick := tick_of(value)):
            return tick
    return None


def tick_stats(frames: list[Any], names: dict[str, str | None]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for code, name in names.items():
        ticks = [t for f in frames if (t := tick_of(f)) and t["instrument"] == name]
        if not ticks:
            stats[code] = {
                "count": 0,
                "median_spread": None,
                "max_gap_seconds": None,
                "first": None,
                "last": None,
            }
            continue
        times = [datetime.fromisoformat(t["timestamp"]) for t in ticks if t.get("timestamp")]
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)]
        stats[code] = {
            "count": len(ticks),
            "median_spread": statistics.median(float(t["ask"]) - float(t["bid"]) for t in ticks),
            "max_gap_seconds": max(gaps) if gaps else None,
            "first": ticks[0],
            "last": ticks[-1],
        }
    return stats


def _subscribe(request_id: str, event: str, instruments: list[str] | None = None) -> str:
    body: dict[str, Any] = {"event": event}
    if instruments is not None:
        body["instruments"] = instruments
    return json.dumps({"id": request_id, "subscribe": body})


async def run_ticks(
    s: Session, summary: dict[str, Any], ap_base: str | None, names: dict[str, str | None]
) -> None:
    path = f"/v1/server-events/accounts/{s.cfg.account_id}/ws/ticks"
    ws, subprotocol, host = await open_ws_with_fallback(s, ap_base, path)
    summary["ws_subprotocol"], summary["ws_host"] = subprotocol, host
    resolved = [n for n in names.values() if n is not None]
    async with ws:
        await ws.send(_subscribe("spike-ticks-1", "ticks", resolved[:1]))
        await collect(ws, 20)
        await ws.send(_subscribe("spike-ticks-2", "ticks", resolved[1:2]))
        probe = await collect(ws, 30)
        first_seen = any((t := tick_of(f)) and t["instrument"] == resolved[0] for f in probe)
        summary["ticks_subscribe_mode"] = "add" if first_seen else "replace"
        await ws.send(_subscribe("spike-ticks-all", "ticks", resolved))
        frames = await collect(ws, s.cfg.tick_seconds)
    write_json(s.cfg, "ticks_sample.json", frames[:50])
    summary["ticks"] = tick_stats(frames, names)
    summary["ticks_errors"] = [
        {k: f.get(k) for k in ("id", "code", "error_message")}
        for f in frames
        if isinstance(f, dict) and "error_message" in f
    ]


async def run_events(s: Session, ap_base: str | None) -> None:
    path = f"/v1/server-events/accounts/{s.cfg.account_id}/ws/events"
    ws, _, _ = await open_ws_with_fallback(s, ap_base, path)
    async with ws:
        await ws.send(_subscribe("spike-tx", "transactions"))
        frames = await collect(ws, 15)
    write_json(s.cfg, "events_snapshot.json", frames[0] if frames else None)


async def run(cfg: SpikeConfig) -> int:
    cfg.out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=15) as client:
        s = Session(cfg=cfg, client=client)
        rest = await fetch_rest(s, summary)
        ap_base, names = rest["ap_base"], rest["names"]
        last_close = await fetch_candles(s, summary, names)
        balance = await fetch_account_state(s, ap_base)
        await fetch_deals(s, summary)
        sizer_feasibility(summary, last_close, balance)
        await run_ticks(s, summary, ap_base, names)
        await run_events(s, ap_base)
        summary["rate_limited_retries"] = s.rate_limited_retries
    write_json(cfg, "summary.json", summary)
    print((cfg.out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    env = dict(os.environ)
    if args.check_config:
        flags = check_config(env, args.api_host)
        print(" ".join(f"{k}={v}" for k, v in flags.items()))
        return 0 if flags["configured"] else 4
    try:
        cfg = build_config(args, env)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    try:
        return asyncio.run(run(cfg))
    except ApiError as exc:
        print(exc.error_message, file=sys.stderr)
        return 2 if exc.status in (401, 403) else 3
    except httpx.HTTPError as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
