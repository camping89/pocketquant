# Red team: Assumption Destroyer (Scope Auditor)

This review produced 10 findings: 1 Critical, 7 High and 2 Medium. The full reviewer text is in the controller transcript.

1. **Critical — Phase 07, T7.3/T7.4/T7.2.** The min-lot clamp produces a fill quantity that differs from the order quantity, so `order.fill` raises (`order/entities.py:147-149`). As a result no position ever opens, and D2 fails. This is the same issue as failure-mode finding 1.
2. **High — Phase 08, T8.6/T8.7.** On a retail account the position sizer can't reach the Exness minimum lot. `max_size = balance*0.10/price` (`position_sizer.py:58-59`, `value_objects.py:11`), so XAUUSD needs a balance of about $23k–40k. The rejection is logged only as `order_rejected` (`order_app_service.py:98-106`), which the T8.7 grep never matches.
   - Fix: add a feasibility check at T1.11, add an `exness.order_rejected_presubmit` log event, and widen the grep.
3. **High — Phase 03 T3.2, Phase 01 T1.11, Phase 08 T8.8.** The calendar models weekends only, so daily breaks and holidays show up as integrity alarms (`integrity_jobs.py:43-44,58-62`, `sync_jobs.py:302-305`). This is the same issue as failure-mode finding 7.
4. **High — Phase 01 T1.6/T1.11, Phase 06 T6.2, Phase 07 T7.4.** Exness instrument names can carry lowercase suffixes (`XAUUSDm`, `BTCUSDc`), but the repo uppercases every composite symbol (`symbol/entities.py:24,47`, `symbol_validation.py:22`, `tracked_symbols_service.py:34`, `quote_app_service.py:44`). A Standard account would stop the plan after Phase 01.
   - Fix: keep a case-preserving map from instrument code to Exness name, populated by the spike.
5. **High — Phase 03 T3.8, Phase 06 T6.16, Phase 07 T7.8.** The Verify steps write to Git Bash `/tmp`, which maps to `%TEMP%`. Windows Python then reads `/tmp`, which resolves to `D:\tmp`, so the step raises `FileNotFoundError` every time.
   - Fix: add an `--out` option with a repo-relative path, or use stdin.
6. **High — U2, Phase 01 T1.1/T1.6/T1.8.** Key delivery has several problems: the `_PATH` variant can't work, a PEM key breaks `source .env` under `set -euo pipefail`, and the key must be pushed to remote master. This is the same issue as security finding 3 and failure-mode finding 8.
7. **High — Phase 06 T6.4/T6.15, Phase 08 T8.4, Phase 03 T3.6.** Each process gets its own token bucket while the rate limit is per account. A 429 has no retry, and Exness throttling can starve Binance `sync_1m` (`scheduler.py:67-70`, `sync_jobs.py:164-175`).
   - Fix: budget per operation, retry on 429, run backfill at a reduced rate fraction, and give Exness its own job or a time cap.
8. **High — Phase 07 T7.4.** A fill missed while the events WebSocket is down, or across a restart, is lost permanently and can double exposure.
   - Fix: reconcile from the snapshot via operation status or deals, hold unmanaged positions, and check positions ≤1 per instrument.
9. **Medium — Phase 06 T6.10.** Ticks are subscribed one instrument per message, but the spec doesn't say whether a subscribe adds to or replaces the set (`ws_subscription_manager.py:20,74-80`).
   - Fix: have the spike test this, or always send the full instrument list.
10. **Medium — Phase 08 T8.1.** A symmetric half-spread on bid candles shifts the fill price but not the SL/TP trigger, so shorts still look better than they should (`paper_broker.py:436,678,715`).
    - Fix: model ask = bid + spread, including for short triggers.

Fact check: `config.py:98` should be `:30`, and `paper_broker.py:671` should be `:678`/`:715`. The other paths and symbols the reviewer sampled were verified.
