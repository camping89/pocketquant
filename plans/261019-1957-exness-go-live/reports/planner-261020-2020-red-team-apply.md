# Red-team findings applied to the Exness go-live plan

Date: 2026-10-20. Plan: `plans/261019-1957-exness-go-live/`. Plan files only; no code, no commit, no push. `ak plan validate` prints `[OK]`.

## What changed
- **Pause survives a restart (user decision 20:20).** Phase 05 adds `SafeguardsRepository` (one document, `core.infra.persistence.repositories`), loads the flag in an async `get_safeguards` provider and writes it on pause and resume. Load order is verified: `bootstrap_live_instances` (`app/main.py:68`) resolves reconcile, whose provider takes `Safeguards` after Task 5.7. Tests: three apps built with `make_test_app` on one database (pause stays paused, resume stays resumed). Phase 10 now pauses before deploy C and proves the pause survived it.
- **Edge hardening ships in deploy A.** Phase 07 adds the `edge`/`backend` networks, 127.0.0.1 binds for Mongo, Redis and Portainer, Mongo pinned to the newest 7.0 patch (7.0.45 on 2026-10-20), `cloudflared` pinned by digest (a release at least 7 days old), nginx `real_ip` from `CF-Connecting-IP`, uvicorn `--forwarded-allow-ips`, and a limiter exemption for `/api/v1/admin/safeguards*`. Phase 08 probes the three ports. Phase 09 probes `:80` and the three ports, confirms exactly two tunnel routes, and checks Pause after a 300-GET burst.
- **Phase 02:** a pooled venue broker is reused even with no holder (one condition); the whole dead test function is deleted; `from_mongo` refuses brokers other than `paper`/`exness`.
- **Phase 11:** the proof now reads `reason=entries_paused` log lines and requires zero `exness.order_submitted`/`exness.order_rejected` for the subscription's orders. It is voided on a StartedAt change, and counts are written at every `NOT_YET`. The phase adds an intent line before create and adopts an existing subscription on a re-run. The round trip is the first trade after `resumed_at`. "Re-baseline" became "accept without AC6, or stop". Scripts run at rate fraction 0.2 with the history clamp. Re-runs use `--from 11 --to 11`.
- **Phase 12:** the entry gate exits while a Phase 11 run is open, and 12.6 never resumes then. Live ids come from GET. The phase checks for below-minimum lines and `exness.order_rejected`. Unexpected bars and the DST check are record only. The `realized_today` loop and the E2 column are gone.
- **Mechanical, all phases:** every push uses the `camping89` token URL, then `git fetch origin`. Every `gh` call carries `GH_TOKEN`. There is a 15 s wait before each run-id lookup. Every Verify is one command, and every report path is fully qualified. Entry gates use `git status --porcelain` and `git show origin/develop:`. Log checks use `--since`. Each ops phase deletes the SSH key copy.
- **Deleted:** old Task 8.8, the 8.7 SSE check and old Task 10.7. Phases 08 and 10 were renumbered.
- **Hygiene:** `ADMIN_TOKEN` is rotated in the deploy-B config commit and again in the Phase 09 rollback. The "Restart while live" runbook goes into `docs/deployment.md` (Phase 09 Task 9.6), and every rollback references it.
- `plan.md` gained `## Red Team Review` (17 accepted rows, 2 rejected, 4 found while applying) and `### Whole-Plan Consistency Sweep`.

## Found while applying (not in the reviews)
- A push to a token URL does not move `origin/*`. The old "no `ahead`" Verify would have failed after every push. Fixed with `git fetch origin`; config pushes are now checked with `git ls-remote`.
- Loopback binds break the documented direct DataGrip, RedisInsight and Portainer access and `remote-db.env`. The docs now point at the SSH tunnel.
- `exness.order_submitted` and `exness.order_rejected` log `order_id`, not the subscription id. `below_min_lot` logs no id at all. The proof therefore maps order ids through Mongo, and `below_min_lot` is counted unscoped.

## Size
Phase 11 has 312 lines and is still one file; every other phase has at most 226. Total code effort is about 3d (05 grew to 0.75d, 07 to 2.5h).

## Unresolved questions
- `pocketquant-config/local/remote-db.env` still names the VPS IP and stops working after deploy A. Should it be edited to use localhost behind the SSH tunnel, or left alone?
- Several suggestions were neither accepted nor rejected, so they are left out: guard fail-closed outside production, `just be --host 127.0.0.1`, nginx `limit_conn`, a Cloudflare rate rule, Cloudflare 2FA, and a "signals vs orders" column. Confirm they stay out.
- How the runner treats a worker that ends `Status: BLOCKED` is still inferred. The Phase 12 gate now covers the dangerous case.
- Phase 07 also rewrites two Vietnamese comment lines in `compose.prod.yml` (CLAUDE.md English rule) because the file is already being edited. Drop that step if you do not want it.

## Validation answers applied (2026-10-20 20:50, with 21:32 overriding answer 1)
- **Data ports:** Mongo, Redis and Portainer bind 127.0.0.1 in deploy A. The 20:50 answer kept Mongo and Redis open, and 21:32 reversed it. Red-team finding 2 stays accepted. Phase 07 Task 7.6 adds a `just tunnel` recipe that forwards Mongo to local 27017, Redis to 6379 and Portainer to its own port. The recipe reads the host, key and ports from `pocketquant-config` at run time and uses its own key copy. Phase 08 Task 8.3 (an [ASK]) moves both `local/remote-db*.env` files to localhost in the same config commit. Task 8.7 proves the tunnel with a Mongo ping and a Redis ping, then confirms that no tunnel is left running. The docs now say "run `just tunnel` first".
- **Local backend rule:** a local backend may run against prod only with `ENABLE_JOBS=false`. Verified: `enable_jobs` (`core/config.py:64`) gates the reconcile loop (`main_extensions.py:256-258`), the scheduler, background jobs and the live collector. `bootstrap_live_instances` still loads subscriptions but starts none.
- **Hardening:** `just be` binds 127.0.0.1 (07). nginx caps SSE streams with `limit_conn` (07). A new Phase 09 Task 9.3 [USER] covers Cloudflare 2FA and one rate-limit rule, so the old tasks 9.3-9.13 became 9.4-9.14. Phase 12 has a record-only `signals / orders` column. Guard fail-closed is rejected (R3).
- **Removed:** the Vietnamese-comment step.
- **Found while applying:** with jobs off, `bootstrap_live_instances` still loads every subscription (N5). A local Pause or Resume writes the stored prod flag (N6). `sed -i` in Git Bash converts CRLF to LF, which is harmless because the index stores LF.
- **Effort:** 07 is now 3h, 08 is 2.5h + CI, and 09 needs 20 min of user time. The code total is still about 3d. `ak plan validate` prints `[OK]`.
