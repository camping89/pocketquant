---
title: Exness safeguards, stored entry pause and leverage sizing
date: 2026-10-21
summary: one Safeguards object holds the Exness caps and a stored entry pause; Exness subscriptions size with leverage
---

# Exness safeguards, stored entry pause and leverage sizing

## What happened
The Exness caps travelled in `default_broker_config`, no pause existed, and a 250 USD account sized below the minimum lot because the exposure cap ignored leverage.

## Change
- `Safeguards` (`core/infra/brokers/exness/exness_safeguards.py`) holds `live_trading`, `daily_loss_cap`, `max_lots`, `leverage`, `risk_per_trade` and `entries_paused`. `BrokerFactory` and `ExnessBrokerAdapter` read it; `default_broker_config` lost the Exness keys.
- The adapter's first presubmit check rejects every open with "entries paused" and logs `exness.order_rejected_presubmit reason=entries_paused` with `subscription_id`. Closes are never gated.
- `SafeguardsRepository` stores the pause in one `safeguards` document; `get_safeguards` loads it before reconcile bootstraps, so the pause survives a restart.
- `GET /api/v1/admin/safeguards` (public), `POST .../pause` and `.../resume` (token).
- `RiskConfig.leverage` scales the exposure cap. Reconcile gives `exness` subscriptions `RiskConfig(leverage=EXNESS_LEVERAGE, risk_per_trade=EXNESS_RISK_PER_TRADE)`; paper and backtests keep `RiskConfig()`.
- The code-metric ceilings rose to `max_tiny_share = 0.4862` and `max_delegations = 93` (user decision; the extra delegation is `save_entries_paused`).

## Risk left
`RiskCheckHandler._check_exposure` is not leverage-aware: while an Exness position is held, every new entry signal is rejected "Max exposure reached". This fails closed and matches the one-position bound; no phase changes it.

## Next steps
Phase 06 (SPA mode badge, pause control, real-money hints) or Phase 07 (Cloudflare Tunnel).

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
