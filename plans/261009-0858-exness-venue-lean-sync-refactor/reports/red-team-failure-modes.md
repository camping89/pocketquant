# Red team: Failure Mode Analyst (Flow Tracer)

This review produced 9 findings: 2 Critical, 6 High and 1 Medium. The full reviewer text is in the controller transcript.

1. **Critical. Phase 07 T7.3/T7.4/T7.5/T7.2.** The plan clamps a live order to the instrument's minimum lot. The fill then reports a smaller quantity than the order, and `OrderAggregate.fill` raises (`order/entities.py:140-149`, `order_app_service.py:180-185`).
   - The live position is open at Exness but the engine never records it.
   - A later SL/TP close opens a phantom SHORT (`position_app_service.py:43-56`).
   - The exception also kills the stream.
   - Fix: normalise the quantity before the order is created (broker `normalize_quantity` hook). Add an integration test running a clamped fill through adapter → OrderAppService → PositionAppService. Make `_notify` exception-safe.
2. **Critical. Phase 07 T7.7.** Live subscriptions can be created and started without authentication (`strategy.py:69-70,113,122`; `verify_admin_token` is used only in `tracked_symbols.py`). This duplicates security finding 1.
3. **High. Phase 07 T7.3/T7.4, Phase 08 T8.7.** Any Exness rejection leaves `hitnrun2._open_direction` set (`hitnrun2.py:94,102,110,115-125`), so the strategy goes silent until a restart.
   - Fix: send a rejection callback to the strategy, or reset the direction. Add a test. Make T8.7 grep for rejections.
4. **High. Phase 07 T7.4, Phase 06 T6.6.** Fills and closes missed during a WS outage, deploy or restart are never reconciled (`hitnrun2.py:65-70`, `strategy_app_service.py:144-145`, `deploy/vps/10-deploy.sh:50`).
   - Fix: reconcile against the snapshot in both directions, and register the close path in `_pending_ack`.
   - Block signals until the first snapshot arrives.
   - Gate every deploy on there being no open Exness position.
5. **High. Phase 06 T6.4/T6.14/T6.15, Phase 07 T7.6.** Sync jobs (including backfill and repair with `n_bars=5000`, `integrity_jobs.py:96-101`) and unauthenticated bulk sync share one token bucket with live orders. This duplicates security finding 5.
6. **High. Phase 08 T8.7/T8.8.** The week-long metrics count matches in `docker logs`. Logs are capped at 30 MB (`compose.prod.yml:56-60`) and the container is recreated on deploy, so a count of 0 proves nothing.
   - Fix: persist the counters in Mongo, or check how far back the logs reach. Forbid deploys during the observation week.
7. **High. Phase 03 T3.2, Phase 01 T1.11, Phase 08 T8.8.** The FX calendar only models weekends. The XAUUSD daily break therefore produces integrity issues every day (`integrity_jobs.py:41-44,57-58`) and repair loops.
   - Fix: build the calendar from the spike's `trade_sessions`. Add a stop condition to T1.11.
8. **High. U2, Phase 01 T1.1/T1.9.** The key must be pushed to `pocketquant-config` master, because CI checks out from GitHub (`get-vps-config/action.yml:42-43`). A PEM key would leak into the Actions logs (`action.yml:74-78`, `cicd.yml:190-198`). `_PATH` is unusable. This duplicates security finding 3.
9. **Medium. Phase 03 T3.10.** Verification calls `GET /api/v1/system/jobs`, which does not exist. Only `/{job_id}/runs` and `/{job_id}/stats` exist (`system_jobs.py:24,30,50`).
   - Fix: query `apscheduler_jobs` in Mongo, or `/{job_id}/runs`.

The reviewer confirmed these points against the code:
- `on_order_update` has no subscriber.
- An order can go from SUBMITTED to CANCELLED, but not from SUBMITTED to REJECTED.
- The fill-before-ACK handoff is correct for the open path.
- `sync_one` swallows provider errors.
- Jobs are registered with `replace_existing=True`.
- The OKX attributes the plan relies on exist.
