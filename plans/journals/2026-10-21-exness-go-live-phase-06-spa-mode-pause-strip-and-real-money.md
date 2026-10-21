---
title: "Exness go-live phase 06: SPA mode, pause strip and real-money hints"
date: 2026-10-21
summary: "Phase 06 shipped (e9d4e87) with two follow-up SPA fixes; UI check re-run by agent after an unverified 'UI ok'"
---

# Exness go-live phase 06: SPA mode, pause strip and real-money hints

## What happened
- Phase 06 of `plans/261019-1957-exness-go-live` shipped to `develop` as `e9d4e87`: PAPER/LIVE badge and one state pill per row, broker-aware Start/Stop dialogs (LIVE Start confirms), Delete in the card footer, an Exness strip with Pause (one click) and Resume (confirm), `moneyHint` table test, 8 dead files removed.
- The user's first "UI ok" was not backed by evidence: the server log showed no subscription existed and all 3 browser Pause POSTs returned 401. The user then delegated the check; the agent drove a headless browser and checked all six items against backend state.
- The check found two existing bugs, fixed after a three-option debate per bug:
  - `58d0bf5`: the config card read a row copy taken at click time, so Start/Stop stayed stale until re-select. The page now owns the `['subscriptions']` query and keeps only the selected id.
  - `906d6bb`: the app nav overflowed to 610 px at 375 px. It now wraps to two rows below 768 px; the strategies and backtest pages fill with flex instead of a hard-coded `41px` (the real nav height is 36 px).

## Local stack quirks (Windows)
- Redis port 53679 sits in a Windows reserved TCP range (53623-53722); `just up` fails until the throwaway `.env` uses another port.
- `just be` fails under the PowerShell recipe shell because of the `TZ=UTC` prefix; run uvicorn directly from bash.
- Binance WS is rejected from this machine, so tracked symbols never sync; UI checks need a subscription seeded in local Mongo.

## Next steps
- Fixed in `71ad8e7`: delete and create invalidated `['subscriptions', code]`, which missed the list key `['subscriptions']`.
- Phase 07 (Cloudflare tunnel): prove `just tunnel` before the 127.0.0.1 bind ships, and keep the forwarded-IP fix in the same deploy as the tunnel.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
