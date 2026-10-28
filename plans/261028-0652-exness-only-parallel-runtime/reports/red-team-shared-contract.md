# Shared contract for applying the red-team findings (2026-10-28)

Every phase writer applies these names and shapes exactly, so the phases agree with each other. Source of the findings: `reports/red-team-adjudication.md`. Owner decisions D33 and D34 are in `plan.md`.

## Log events (all INFO unless stated)
- `lease.acquired name= owner=`, `lease.lost name=` (ERROR), `lease.takeover_failed name=` (ERROR, exc_info), `lease.released name=`.
- `trader.standby`, `trader.takeover handover_gap_ms=` (logged right after `lease.acquired`, before any takeover I/O; value = acquire time − `released_at` of the previous lease doc, empty when the previous holder lost the lease), `trader.takeover_complete takeover_ms=` (after the reconcile task starts).
- `trader.drain_retry boundary=`, `trader.drain_timeout inflight=` (ERROR), `trader.lease_released inflight= boundary= offset_s=`.
- `strategy.signal_discarded reason=lease|drain` at INFO (standby discards before any lease stay DEBUG `reason=standby`).
- `strategy.entry_skipped reason=stale|gap|lease|inflight` (WARNING).

## Drain and lease rules
- The drain deadline is measured from the start of lifespan shutdown; hard deadline shutdown-start + 150 s; trader `stop_grace_period: 180s`.
- Release only when `last_closed_boundary >= B` (every bar of boundary B published and the publish returned) and `inflight_count() == 0`.
- `inflight_count` counts Exness `_inflight` + `_pending_ack`, running signal tasks, and running bar handlers (inline paper processing). `_needs_snapshot` is not counted; it re-triggers a snapshot instead.
- Lease renewal keeps running until after `engine.stop()` and the release. `engine.stop()` gathers signal tasks bounded by the remaining grace.
- `hold_lease` sets state `held` only after `on_acquired` returns; an exception there logs `lease.takeover_failed`, releases, runs the on-lost path and sends SIGTERM. `/health` reports `lease` and `lease_renewed_age_s` from the lease document.
- `submit_order` receives the `trading_until` deadline and re-checks it after `_open_lock` and after the pacer wait, right before the send; no resend after the deadline; on lease loss, signal tasks that have not reached the send are cancelled.
- `app_roles` default is `"api"`; startup fails when `ENABLE_JOBS` is set in the environment. Compose sets `APP_ROLES` per service and `EXNESS_LIVE_TRADING: "false"` in the `api` and `worker` `environment:` blocks.
- Lease checks verify each lease `owner` hostname equals the hostname of its compose container (`docker inspect -f '{{.Config.Hostname}}'`).
- Worker stop: `scheduler.pause()`, await tracked running job tasks bounded below the grace, then shutdown and release.
- Only the trader lease holder writes or deletes `bar:current`; the stored seed carries `gap` and `coverage_start`.
- The process-local bar dedup cache (`_BAR_VALUE_CACHE`) is deleted; the `find_one` comparison stays.

## VPS helpers (installed once in Phase 08 at `/opt/pocketquant/bin/`)
- `snapshot.sh <label>`: prints `label= ts= mem_used_mb= mem_available_mb= swap_used_mb= load1= psi_some_avg10= oom= boot_id=` on one line.
- `sample.sh start|stop <file>`: `docker stats --no-stream` every 2 s while a roll runs.
- `probe.sh start|stop <file>`: host-side `docker exec pocketquant-web curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost/api/v1/market-data/symbols` every 0.5 s.
- `leases.sh`: prints `worker=<owner> trader=<owner> unexpired=<n> owners_match=<yes|no>`.
- `oom-check.sh <boot_id> <count>`: prints `OOM_OK` or `OOM_STOP <reason>`; also checks `State.OOMKilled` of backend containers.
- Before Phase 08, phases run the same snapshot and OOM commands inline (no scripts on the VPS).

## Deploy script
- `flock -n /opt/pocketquant/deploy.lock` around the deploy; `roll()` refuses unless exactly one running copy; `cancel-in-progress: false` for `master` in `cicd.yml`.
- `roll api`: `docker network disconnect pocketquant-prod_backend "$old"`, wait 6 s, then `docker stop`; nginx `proxy_connect_timeout 1s`.
- The old container's log is saved after `docker stop` and before `docker rm`; a failed health wait writes the tail to `/opt/pocketquant/logs/failed-<svc>-<ts>.log` and prints only the path; `find /opt/pocketquant/logs -name '*.log.gz' -mtime +30 -delete`.
- The cutover re-runs `oom-check.sh` before `docker stop pocketquant-app` and aborts with `dc rm -sf api worker trader` on `OOM_STOP`.

## Probe containers (Phase 07)
- `docker rm -f pq-probe-trader pq-probe-worker 2>/dev/null || true` first; `docker run -d --rm --stop-timeout 180 --label pq-probe=1 ... sh -c 'exec timeout -s TERM 600 <uvicorn command>'`; detached, with a completion poll; Verify and the Phase 08 entry gate require `docker ps -aq --filter label=pq-probe=1 | wc -l` = `0`.

## Logging config
- Console exception formatter without locals (`structlog.dev.plain_traceback` or `RichTracebackFormatter(show_locals=False)`) at `src/pocketquant/core/common/logging/setup.py:71`.
