---
title: Exness venue and lean sync refactor plan
date: 2026-10-10
summary: Planned Exness data/quotes/broker (broker off) behind existing ports after a SyncPolicy refactor; red team found live-money and auth gaps.
---

# Exness venue and lean sync refactor plan

## What happened
- I created the plan `plans/261009-0858-exness-venue-lean-sync-refactor/`. It has 9 phases, 91 tasks and about 7 weeks of work. I generated it with `ak:plan --ultra --advice`: five independent planners on Opus, then a Fable verifier. The winner scored 91 against 90 for the runner-up, so the margin is low.
- Four red-team lenses produced 36 findings. After deduplication, 15 were accepted plus about 13 medium fixes. The rankings and findings are in `reports/` inside the plan directory.

## Discoveries in the current code
- The subscription create, start, stop and delete routes have no auth. `verify_admin_token` is a no-op when `ADMIN_TOKEN` is unset, and prod does not set it. Anyone can mutate paper subscriptions today.
- No live fill path exists. `OrderAppService.on_order_update` has no subscriber, and every subscription trades on `paper`.
- `OrderAggregate.fill` requires the fill quantity to equal the order quantity. A broker min-lot clamp would therefore break every live fill unless the quantity is normalized before the order is created.
- Today `:OKX` symbols are silently fetched from Binance. `integrity_jobs` assumes 24/7 markets, so FX and metals session breaks would raise alarms every day.
- The metric thresholds the user first confirmed (≤30% tiny, ≤20 delegations) cannot be reached honestly. The honest projection is about 40–44% tiny and about 45–58 delegations.

## Decisions
- The Exness broker is built and tested but kept off with `EXNESS_LIVE_TRADING=false`. Going live is a separate later plan, and it requires auth on mutation routes, a broker-selection mechanism, a risk cap and a live round trip.
- Market data is routed strictly by symbol suffix through `SyncPolicy`, with no separate router module. `:OKX` data symbols migrate to `:BINANCE`, but only after a `mongodump` backup and user approval.
- The metric gate is a ratchet: the CI ceiling is frozen after the lean refactor and may only go down.
- There is no automatic retry on HTTP 429, for any call.
- The daily loss cap counts close, swap, admin fee, dividend and commission deals. Async fills are wired for Exness only, so OKX is unchanged. `hitnrun2` resets its open direction on any order that never fills.

## Next steps
- The user confirms U1 (the portal domain) and U2 (a single-line seed key pushed to `pocketquant-config` master).
- Set `ADMIN_TOKEN` in prod now, independently of this plan.
- Run `/ak:cook plans/261009-0858-exness-venue-lean-sync-refactor/plan.md --advice`.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
