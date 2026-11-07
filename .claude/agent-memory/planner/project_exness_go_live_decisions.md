---
name: project-exness-go-live-decisions
description: PocketQuant Exness go-live (2026-10-20): arm paused, one strategy per Phase 11 re-run, E2 gates nothing; entry pause is STORED across restarts (20:20 decision)
metadata:
  type: project
---

User decisions 2026-10-20 for `plans/261019-1957-exness-go-live/`: deploy as soon as code is done (each master push still stop-and-ask); arming = entries paused, then flag on (deploy C), every subscription paper; going live is a re-runnable phase (`--from 11 --to 11`) for ONE user-chosen strategy (delete paper sub, create exness sub paused, zero-money proof from `reason=entries_paused` log lines, gated Resume, first natural trade); five trading-day observation rows; the E2 paper check (2026-11-02) is optional.

20:20 changes: the `entries_paused` flag is persisted (one doc via a repository in core) and loaded before reconcile starts strategies — replaces "pause in memory, resets on restart". Unexpected-bar counts and the DST check are record-only. ADMIN_TOKEN rotates in deploy B. Mongo/Redis/Portainer bind 127.0.0.1. Every planned restart while live follows the "Restart while live" runbook.

20:50/21:32 validation answers: data ports stay loopback but local debugging against prod must keep working, so the plan adds `just tunnel` (local 27017/6379, since local compose already uses 52017/53679) and moves `pocketquant-config/local/remote-db*.env` to localhost. A local backend against prod is allowed with `ENABLE_JOBS=false` (no "no local backend" rule). The user REJECTED admin-guard fail-closed outside production (it would block local debugging). Added: `just be` on 127.0.0.1, nginx SSE `limit_conn`, Cloudflare rate rule + 2FA, Phase 12 signals/orders column.

2026-10-21 00:21 answers: "trust in your hand" is NOT a standing approval — every real-money [ASK] stays, but each question leads with `Recommended: <reply>` so the user answers in one word. First live run is single-order (pause again once the first position opens; SL/TP from the strategy, no manual order route). Deep backfill is decided (1m, three :EXNESS symbols, to the probed M1 edge). Agent may `gh workflow run` but never test-dispatch (every cicd run deploys). No Cloudflare API token unless the dashboard rejects both expressions.

2026-10-21 00:43 answers: NO Cloudflare API token at all (reverses 00:21; Free-plan limits apply via API too; both expressions rejected → stop for counsel). Unwatched single-order risk ACCEPTED (bound: one position per subscription + 25 USD cap, ~50-100 USD worst day); no in-app pause-after-fill; first-entry watch 4 h. After a clean Phase 11 round trip the default is `keep on`, so Phase 12 observes real trading.

**Why:** the user wants live ASAP and rejected calendar gates; risk is bounded by 0.01 lot, 25 USD daily cap and a pause that cannot be lost to a crash.

**How to apply:** in later Exness plans do not gate live steps on E2 rows or weekend windows; keep per-step [ASK] gates and zero-money proofs; never reintroduce an in-memory-only pause; never propose hardening that blocks local debugging against the remote DB. Pushes to camping89 repos go through a token URL and need `git fetch origin` afterwards (URL pushes do not move origin/*). See [[feedback-single-plan-runner-order]].
