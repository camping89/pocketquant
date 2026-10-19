---
phase: 4
title: "Ship with live off; set ADMIN_TOKEN and the loss cap (B7)"
status: pending
priority: P1
effort: 2h + CI
dependencies: [1, 2, 3]
---

# Phase 04: Ship with live off; set `ADMIN_TOKEN` and the loss cap (B7)

## Context
- Prod config is `pocketquant-config/vps/default/.env`, which the deploy writes onto the VPS on each run (`docs/deployment.md:72-76`). A config change takes effect only after a redeploy: push `master`, or run `gh workflow run cicd.yml --ref master` (`docs/deployment.md:33`).
- A release is `git push origin develop:master`, a fast-forward only (`docs/deployment.md:10`).
- Prod today has `ENVIRONMENT=production` and `DEFAULT_BROKER=paper`, and has none of `ADMIN_TOKEN`, `EXNESS_DAILY_LOSS_CAP`, `EXNESS_MAX_LOTS` or `EXNESS_LIVE_TRADING` (keys counted, values not read). The loss-cap gate is `exness_broker_adapter.py:239-240`.
- Entry conditions: Phases 01–03 are on `develop`, E1 is merged to `develop`, E2 is closed, and D1, D2 and D5 are answered.

## Files
- No repo file. Outside the repo: `pocketquant-config/vps/default/.env` (gated).

## Steps
1. Gate on `develop` at the commit to release: `just test` (only the 4 known `tzset` failures), `uv run lint-imports`, `uv run python scripts/code_metrics.py --ratchet`, `npm --prefix web test`, `npm --prefix web run build`.
2. **[Stop-and-ask]** Generate a token with `uv run python -c "import secrets;print(secrets.token_urlsafe(32))"`. Add `ADMIN_TOKEN=<token>` and `EXNESS_DAILY_LOSS_CAP=<D2>` to `pocketquant-config/vps/default/.env`. Confirm that `EXNESS_LIVE_TRADING` and `EXNESS_MAX_LOTS` are absent. Commit and push `pocketquant-config`. Never print the token in logs, plan files or chat; the user reads it from `pocketquant-config`.
3. **[Stop-and-ask]** `git push origin develop:master`. Take the run whose `headSha` equals `git rev-parse develop`, then `gh run watch <id> --exit-status`.
4. Verify prod (`KEY`, `HOST` as in `docs/deployment.md:49`):
   - `docker exec pocketquant-app python -c "from pocketquant.core.config import get_settings as g;s=g();print(s.exness_live_trading, s.exness_daily_loss_cap is not None, s.exness_max_lots, s.admin_token is not None)"` prints `False True None True`;
   - `docker exec pocketquant-app curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:41921/api/v1/subscriptions/x/stop` prints `401`;
   - `GET /api/v1/subscriptions/` returns 200 without the token, and every item has `"broker": "paper"`;
   - `POST /api/v1/market-data/integrity/check` with the token and `{"symbol":"XAUUSD:EXNESS","interval":"1m","days_back":1}` returns 200;
   - in the SPA, the user stops and starts one paper subscription and is asked for the token once.

## Validation
- `gh run view <id> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.
- Every value in step 4 matches.

## Risk
- Deploying before step 2 makes prod mutations return 503 (L/L). Step 2 comes first.
- The deploy restarts the app, and with it the paper validation subscriptions (L/L). E2 is already closed when this phase runs.

## Rollback
- Code: `git revert <sha>` on `develop`, then `git push origin develop:master` (gated).
- Config: remove the two keys and redeploy (gated). Removing `ADMIN_TOKEN` while the Phase 01 code is live makes mutations return 503; revert the code first or keep the key.
