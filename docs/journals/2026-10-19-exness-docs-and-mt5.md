# Exness Provider, Broker Switch and MT5 in the Docs

**Date**: 2026-10-19
**Severity**: Low
**Component**: `docs/` (system-architecture, deployment, code-standards, codebase-summary, project-overview-pdr, and their `docs/vi` mirrors), `README.md`, `scripts/README.md`
**Status**: Resolved on develop (`995b4ba`, docs-only, CI skipped)

---

## What Happened

The docs now describe Exness as the third suffix-routed data and quote provider (`XAUUSD:EXNESS`). They cover its session calendars, the 429 rule, the Exness broker that is built but switched off behind `EXNESS_LIVE_TRADING`, the backtest `spread`, the eight `EXNESS_*` env keys, the seed and deep-backfill runbook, and a checklist of the places a new data provider touches. MT5 is documented as a future provider that is not built. Each English edit has a matching edit in its `docs/vi` mirror.

---

## Decisions Recorded

- The docs describe the code where the plan's wording differs from it. The ticks `subscribe` frame has no `add` mode. The plan's claim that M1 history reaches back one year has no source. The loss cap subtracts the commission of every deal except `balance`. The plan's task wording is unchanged and these differences are listed in the phase file for the user.
- `docs/system-architecture.md` is 876 lines, above the 800-line docs budget, and it was already 841 before this phase. It was not split, because splitting is a separate docs task.

---

## Lessons

- Every Exness claim in the docs was checked against source before it was written. That check found the three differences above, which would otherwise have gone into the docs as fact.
- A push from this machine to `camping89/pocketquant` needs the `camping89` token. The active `vunguyen-ai` account gets a 403.
