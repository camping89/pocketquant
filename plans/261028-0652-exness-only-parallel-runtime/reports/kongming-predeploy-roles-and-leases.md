# Pre-deploy review: roles and leases (Deploy A, D-4)

Reviewed `d10c1c3d..HEAD` on 2026-10-29. Verdict: **GO** (two non-code notes for the rollback text and one low-severity follow-up; nothing blocks D-4).

## Q1 — correctness

1. **Takeover > 25 s (restart loop) — not a real prod risk.** Fact: `take_over()` (`strategy_app_service.py:155-199`) does two Mongo loads, an in-memory paper restore and `broker.connect()`; with `EXNESS_LIVE_TRADING=false` the factory refuses an Exness broker (`broker_factory.py:77-80`), and `PaperBrokerAdapter.connect` only subscribes to the bus (`paper_broker_adapter.py:141-146`). Inference (high): sub-second on the VPS. Fact: if it ever did time out the loop is deterministic (`roles.py:89-96` releases, `on_lost` SIGTERMs, `restart: unless-stopped` restarts) and Task 7.8's `lease.takeover_failed=0` detects it. No mitigation needed before deploy.
2. **Lifespan ordering — sound.** Fact: `trading_until=None` is set before bars can flow (`roles.py:170`, quote feed starts at `main.py:79` after standby), so no order leaves without the lease; `_process_signal` fences at the send (`strategy_app_service.py:570-586`). Fact: the finally block runs `stop_worker` and `hand_over` together (`main.py:98-102`), the close timer keeps advancing `last_closed_boundary` even with no ticks (`bar_app_service.py:270-271`), so the drain normally ends ~0.75 s after the next minute boundary. Fact: deadlines count from `finally` start (`main.py:94`), i.e. up to 10 s after SIGTERM, not "from shutdown start" as the comment at `roles.py:47-48` says. Inference (high): worst case (drain timeout and slow stop) still releases the lease by ~175 s; only post-release cleanup could be SIGKILLed. Harmless.
3. **Lost lease, never retaken — no.** Fact: a lost or crashed holder leaves a doc that expires in <=30 s (`lease_repository.py:32`); a waiter polls every 0.5 s (`roles.py:83-85`); SIGTERM (`roles.py:131,224`) goes to uvicorn 0.40's `signal.signal` handler and uvicorn re-raises it on exit, so the container exits and restarts. Verified against uvicorn 0.40.0 `server.py` (fetched).
4. **One role dead with a healthy container — low-severity, follow-up.** Fact: `on_lost` is awaited outside any try (`roles.py:95,115`); if `engine.stop()` raised (e.g. a strategy `on_stop`), `os.kill` would never run and the trader would sit in state `lost` with HTTP 200. Inference (medium-low): base `on_stop` is trivial (`strategy_service_interface.py:53-54`) and paper `disconnect` cannot raise, so this needs a double fault. Harden later with `try/finally` around the `os.kill`. Not a D-4 blocker.
5. **Rollback compatibility — fine, but the phase text is wrong.** Fact: the Phase 06 image has `enable_jobs: bool = True` and `extra="ignore"` (`git show 3905ff6b:src/pocketquant/core/config.py:37,57`), so it runs under the new compose (`APP_ROLES` ignored, `--timeout-graceful-shutdown 10` accepted) with no `ENABLE_JOBS`. Fact: the new image refuses to start when `ENABLE_JOBS` is in the process env (`config.py:110-116`). **Do not revert the `pocketquant-config` commit for a rollback**; the phase's "After D-4" line claims the old image needs `ENABLE_JOBS=true`, which it does not, and putting it back would turn the next deploy of the new image into a restart loop. Inference (high): on rollback the old image logs one APScheduler "Unable to restore job" for `backtest_orphan_sweep` and drops it; `11-verify.sh:177` counts that as WARN, not FAIL.

## Q2 — Verify commands and rollback path

- Fact: prod `LOG_FORMAT=console` (config repo); `ConsoleRenderer` pads the event, so `trader\.takeover( |$)` matches after ANSI stripping. Fact: `register_sync_jobs` uses `replace_existing=True` (`scheduler.py:214`), so the pre-existing job docs do not break the worker's `on_acquired`. Fact: `11-verify.sh` never exits non-zero on a FAIL, so CI cannot fail there.
- Inference (medium): `lease_renewed_age_s < 11` is tight; renew is every 10 s plus loop lag. A 10.x reading is normal; >=11 would mean lag, re-run once before treating it as a defect.
- The `docker logs --since 15m` window note in the corrections stands.

## Assumptions

- Prod has only paper subscriptions (live trading off) — high; an Exness broker would add a WS connect inside the 25 s budget.
- VPS Mongo/Redis are local to the compose network — high.

Status: DONE
Summary: GO. No restart-loop, lost-lease, shutdown-hang or order-fence defect found; fix the rollback instruction (never re-add ENABLE_JOBS) and schedule the on_lost try/finally hardening.
