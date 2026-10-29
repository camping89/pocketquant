# Exness Go-Live Plan: Debate, Red Team and the Facts We Had Wrong

**Date**: 2026-10-20 21:48 (Asia/Bangkok)
**Severity**: High (the plan moves real money)
**Component**: `plans/261019-1957-exness-go-live/` (plan.md + 12 phase files)
**Status**: Planned, committed as `598a90a` on `develop`; no code changed yet

---

## What Happened

The Exness go-live plan was extended and debated. Three independent candidates were written: KISS, real-money safety and executability. `kongming` merged them in `reports/kongming-261020-1924-debate-synthesis.md`. Four red-team reviewers (security, failure modes, assumptions, scope) then raised 33 findings; 15 merged items were accepted and applied, three were rejected. The plan has 12 phases, and file order is run order.

## Decisions (user)

- Account: 250 USD, 0.01 lot, leverage 1000, risk 0.10, daily loss cap 25 USD realized per UTC day.
- Arm live as soon as possible with every subscription still on paper. Go live later with one strategy the user picks, starting paused. A zero-money proof comes before a gated Resume.
- The pause is stored and survives a restart. The first draft kept it in memory, so a crash during the proof wait would have traded without approval (red-team FM-1, Critical).
- Cloudflare Tunnel for the public edge.
- Mongo, Redis and Portainer bind to 127.0.0.1. Local debugging goes through a new `just tunnel` recipe.
- The 2026-11-02 paper check is optional, not a gate.

## The Brutal Truth

Several "known" facts were wrong, and the plan would have failed in prod on each one. The debate and red team earned their cost. The real kick in the teeth: the data ports were open to the internet the whole time, and we believed ufw covered them.

## Surprises Worth Remembering

- hitnrun2 warmup is 480 closed 1m bars, about 8 market hours, not minutes (`hitnrun2_strategy_service.py:93`). Earlier advice said minutes.
- The unique index on `(strategy_code, symbol, interval)` means a paper and an exness subscription for the same triple cannot coexist.
- With `EXNESS_LIVE_TRADING` on, the deep backfill refuses and exits 3 (`scripts/backfill/provider_bars.py:76-78`).
- Mongo, Redis and Portainer published public ports. Docker-published ports bypass ufw.
- A pooled broker was reused only while a subscription held it. Deleting the last exness subscription left its adapter connected, and the next one built a second adapter. Fix: reuse regardless of holders (Phase 02).
- `develop` pushes need the `camping89` token URL. The active gh account `vunguyen-ai` cannot push. A push to a URL does not move `origin/*`, so every push is followed by `git fetch origin`.
- Rejection reasons are not stored on orders (`to_mongo` has no reason field). The zero-money proof therefore reads the `reason=entries_paused` log line, not the `orders` collection.

## Lessons Learned

- Verify every carried-over number against source before it becomes a gate. "Minutes" vs 480 bars would have stalled a phase for a day.
- Check what Docker publishes, not what the firewall says.
- A proof that counts "any rejected order" proves nothing when the reason is not stored.

## Open (not verified)

- How the cook runner handles a `Status: BLOCKED` worker is inferred from `eve-cook-plan/SKILL.md`, not tested. The first `NOT_YET` exit will show it.
- The unit of `margin_percent` is unverified. Phase 11 records it raw.
- The Cloudflare rate-limit rule expression (200 requests / 10 s per IP on `/api/*`, safeguards exempt) has not been saved in the dashboard yet. If rejected, Phase 09 stops for counsel.

## Next Steps

- Run Phases 01-07 (code) on `develop`, then deploy A (live off) and the tunnel cutover. Owner: plan runner with user gates.
- Phase 11 asks the user which strategy goes live first.

---

**Status**: DONE
**Summary**: The go-live plan was debated, red-teamed (33 findings, 15 accepted) and committed as `598a90a` with 12 phases. Three items remain unverified: runner BLOCKED handling, `margin_percent` unit, and the Cloudflare rate rule.
