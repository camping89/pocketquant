# Cutover rehearsal on Docker Desktop

Date: 2026-10-30 (Asia/Bangkok). Runs at 2026-10-29 23:19-23:27 UTC on Windows 11, Docker Desktop.

Rehearsal: PASS

## Setup

- Images: `pqlocal/pocketquant:new` and `:old` are the same backend build plus the rehearsal `sitecustomize.py` layer. Paper brokers report one order in flight for 45 s after the first `inflight_count` read. `pqlocal/pocketquant-web:old` is built from `origin/master` (proxies `app`); `:new` is built from `develop` (proxies `api`).
- Compose project `pqrehearsal`, containers renamed `pqr-*`, paths `./logs` and `./bin`, lock disabled.
- Deviation from the plan: host ports changed to `MONGO_PORT=47017`, `REDIS_PORT=47379`, `PORTAINER_PORT=49000`. Port 57379 is inside a Windows excluded TCP port range, so Docker could not bind it.
- One paper subscription (`hitnrun2`, `BTCUSDT:BINANCE`, 1m) was seeded; it reached `actual_state=running` in the old `pqr-app`.

## OOM abort run

`oom-check.sh` printed `OOM_STOP rehearsal`. The deploy started the three role services, hit the OOM check before the cutover, removed them and exited 1. Afterwards 0 role containers ran and `pqr-app` reported `"lease":"held"`.

```text
ERROR: OOM stop before the cutover; removing the new services, the old app keeps trading
 Container pqrehearsal-api-1 Stopping 
 Container pqrehearsal-trader-1 Stopping 
 Container pqrehearsal-worker-1 Stopping 
 Container pqrehearsal-trader-1 Stopped 
 Container pqrehearsal-api-1 Stopped 
 Container pqrehearsal-worker-1 Stopped 
Going to remove pqrehearsal-api-1, pqrehearsal-worker-1, pqrehearsal-trader-1
 Container pqrehearsal-trader-1 Removing 
 Container pqrehearsal-worker-1 Removing 
 Container pqrehearsal-api-1 Removing 
 Container pqrehearsal-api-1 Removed 
 Container pqrehearsal-worker-1 Removed 
 Container pqrehearsal-trader-1 Removed 
deploy-exit=1
```

## Cutover run

The deploy printed `One-time cutover` and exited 0. Probe: 1 non-200 of 140 requests (`23:20:59 000`). The cutover probe is recorded only. The cause of the single `000` was not traced; it falls inside the cutover window in which `web` is recreated.

```text
 Container pqr-redis Healthy 
 Container pqr-mongodb Healthy 
 Container pqrehearsal-api-1 Waiting 
 Container pqr-redis Healthy 
 Container pqrehearsal-api-1 Healthy 
 Container pqr-web Waiting 
 Container pqr-web Healthy 
 Container pqr-cloudflared Starting 
 Container pqr-cloudflared Started 
=== Cleaning old images and logs ===
Total reclaimed space: 0B
=== Done ===
pocketquant-redis         Up 7 days (healthy)
pocketquant-mongodb       Up 7 days (healthy)
deploy-exit=0
```

The two `pocketquant-*` status lines are the local dev containers on this machine, matched by the script's final `grep pocketquant`. They are not part of the rehearsal.

Old app drain: `trader.drain_retry` at 23:22:30 (boundary 23:22:00), then `trader.lease_released` with `inflight=0` at 23:23:00.

`11-verify.sh` after the cutover: `grep -cE "containers: PASS|lease: PASS|Leases: PASS"` printed `6`. The leases line read `worker=01a502bdacac:1 trader=5475aa9b87ad:1 unexpired=2 owners_match=yes`. The API and Web probes printed `HTTP 200000` and failed, and `cloudflared` was unhealthy. Both are local-only:
- Git Bash rewrites the `/dev/null` argument passed to `docker exec`, so curl prints `200` and then exits 23. The script's `|| echo 000` then appends `000`. With `MSYS_NO_PATHCONV=1`, the same call prints `200` and exits 0.
- `cloudflared` has no real token, which the plan expects.

## Same-tag roll

The deploy printed `Rolling api, worker, trader` and exited 0. Probe: 0 non-200 of 127 requests.

```text
 Container pqr-mongodb Healthy 
 Container pqrehearsal-api-2 Waiting 
 Container pqr-mongodb Healthy 
 Container pqr-redis Healthy 
 Container pqrehearsal-api-2 Healthy 
 Container pqr-web Waiting 
 Container pqr-web Healthy 
 Container pqr-cloudflared Starting 
 Container pqr-cloudflared Started 
=== Cleaning old images and logs ===
Total reclaimed space: 0B
=== Done ===
pocketquant-redis         Up 7 days (healthy)
pocketquant-mongodb       Up 7 days (healthy)
deploy-exit=0
```

Rolled-out trader drain: `trader.drain_retry` at 23:26:30 (boundary 23:26:00), then `trader.lease_released` with `inflight=0` at 23:27:00. The new trader logged `trader.takeover` (`handover_gap_ms=30`) and `trader.takeover_complete` at 23:27:00.

## Verify

```text
1   app drain_retry
1   app lease_released inflight=0
1   trader drain_retry
1   trader lease_released inflight=0
0   drain_timeout in all saved logs
2   takeover + takeover_complete in the new trader
0   non-200 on the roll probe
1   "OOM stop before the cutover" in the abort run
```

Expected `1, 1, 1, 1, 0, 2, 0, 1`; every value matches.
