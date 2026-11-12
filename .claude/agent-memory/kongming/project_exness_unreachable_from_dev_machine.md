---
name: exness-unreachable-from-dev-machine
description: 2026-11-12 the dev machine's network resets TLS to api.exness.com; VPS reaches it; advised ssh -D SOCKS via VPS for local Exness scripts
metadata:
  type: project
---

On 2026-11-12 `curl https://api.exness.com/` from the dev machine (Asia/Bangkok network) returned `(35) Connection was reset`; the same curl from the VPS returned HTTP 404 (reachable). The cause on the local network is not verified.

**Why:** plan 261112-1445 task 1.5 (local `scripts/backfill/provider_bars.py`) failed with `TRANSPORT`. `ExnessClient` builds `httpx.AsyncClient(timeout=...)` with default `trust_env`, so `HTTPS_PROXY` is honoured; `socksio` is not in `uv.lock` (httpx 0.28.1).

**How to apply:** for any local script that calls Exness, advise `ssh -N -D 127.0.0.1:1080` to the VPS plus `HTTPS_PROXY=socks5://127.0.0.1:1080` on the python process only, with `uv run --with socksio`. GO was given for this on 11-12 (advice, outcome not seen). Re-test direct reachability first; the block may be temporary. Related: [[project_1m_fills_plan_red_team_adjudication]].
