# Docs purge review (adversarial) — 2026-10-29

Scope: the uncommitted working tree on `develop` (`git diff HEAD`), the new `docs/governance/documentation-rules.md`, and every path the new text cites. Every claim below was checked against the file named; outside-repo claims were checked over SSH to the VPS where marked.

## TL;DR

The purge is sound: no removed line lost a fact that no file holds, except two venue quirks (Exness and Binance WebSocket subscribe semantics) that now exist only in git history. Three sentences in the new text are wrong or misleading against current code, one copied count survives in `CLAUDE.md`, `scripts/rubric/README.md` still copies the grade map, one code comment points at a doc deleted long ago, and the governance rule has three gaps (scope, commands, requirements vs "code wins") that will let docs re-grow or delete a requirement. Fix list below, ranked.

## Ranked fixes

### 1. Wrong: `docs/code-standards.md`, Async section, bullet 1

Text: "`await container.get(X)` can run provider I/O. It can also resolve and start the APP-scoped `JobScheduler`, so persisted jobs may dispatch there."

Evidence: `src/pocketquant/app/di/infrastructure.py:97-104` yields an unstarted `JobScheduler` with the comment "The worker role starts the scheduler after it takes the worker lease." `scheduler.start()` is called only in `src/pocketquant/app/roles.py` (`start_worker.on_acquired`). `container.get` no longer starts it.

Change: replace the bullet with "`await container.get(X)` can run provider I/O: Dishka async factories await inside `get`." In the next bullet keep the `set_sync_container` example but drop the implied reason; write "`lifespan()` in `app/main.py` sets `set_sync_container(container)` before its first `await`, so a persisted job that fires right after the worker's `scheduler.start()` finds the container set."

Related code comment (same stale reason): `src/pocketquant/app/main.py:57-62` says the scheduler "may resolve+start inside any subsequent `await container.get(...)` chain". Update it with the same wording.

### 2. Misleading: `docs/system-architecture.md`, Decisions, bullet 1

Text: "Rejected: one process that holds every role as in-process singletons, where a restart stops trading until the new process is up."

Evidence: prod runs one process with every role: `deploy/compose.prod.yml:75` `APP_ROLES: "api,worker,trader"`; confirmed live over SSH (`docker exec pocketquant-app` shows `APP_ROLES=api,worker,trader`). There is no second copy in the prod stack, so a restart still stops trading until the new process is up. The rejected alternative is "no lease", not "one process".

Change: "Rejected: roles bound to the process with no lease, where only a restart can move a role. Prod runs one process with all three roles (`deploy/compose.prod.yml`); the warm standby is a capability, not a deployed copy."

### 3. Wrong in letter: `docs/system-architecture.md`, Decisions, bullet 3

Text: "The api process never calls the engine."

Evidence: `src/pocketquant/app/routes/market_data.py:219` and `src/pocketquant/app/routes/market_data_quotes.py:43` inject `BarAppService` (`engine.market_data`) and call it.

Change: "The api process never calls `StrategyAppService`. It reads engine state only through Mongo and Redis."

### 4. Over-cut: two venue facts now live nowhere

HEAD `docs/system-architecture.md:175-176` held: Binance "Unsubscribe is local; the stream changes on the next reconnect." Exness "A `subscribe` frame was observed to add instruments to earlier ones, so a reconnect re-sends all of them and `unsubscribe()` is local only."

Evidence of no owner: `grep -rni "re-send\|Unsubscribe is local" src` returns nothing. `src/pocketquant/core/infra/exness/exness_quote_adapter.py:105` (`_resubscribe_all`) and `src/pocketquant/core/infra/binance/binance_websocket_adapter.py:90` (`unsubscribe`, docstring "Remove a subscription.") carry no comment on the venue behaviour. These are rule-4 facts (outside this repo) and rule-3 sites (one function each).

Change (comments, not doc lines):
- `exness_quote_adapter.py` above `_resubscribe_all`: `# Observed: a subscribe frame adds to the instruments already on the socket, and a reconnect starts empty, so every instrument is re-sent. unsubscribe() is local only.`
- `binance_websocket_adapter.py` in the `unsubscribe` docstring: `Local only: the stream drops the symbol on the next reconnect.`

### 5. Under-cut: `CLAUDE.md:18` copies a count

Text: "(import-linter enforced, 6 contracts)". `pyproject.toml` owns the count (`grep -c tool.importlinter.contracts` = 6 today; the auditor found it written as 8 in two other docs this week). Rule 1 of the new governance forbids the copy.

Change: "(import-linter enforced, `[tool.importlinter]` in `pyproject.toml`)".

Same file, line 35: "Run / test / canonical routes / remote-DB dev modes → `README.md`". The README no longer lists routes beyond the smoke test. Drop "canonical routes".

### 6. Under-cut: `scripts/rubric/README.md` still copies owned values

The purge edited this file (added three caveat bullets) and left copies in place:
- "Scoring" section: "Grade: A ≥ 3.5, B ≥ 2.5, C ≥ 1.5, D ≥ 0.5, F < 0.5" and "Each metric → 0–4 via industry threshold bands" copy `scripts/rubric/scoring.py`.
- "Notes": "Crypto-1m caveat" repeats the new bullet at the top of the same file and `scoring.py:16-17`. Three copies of one caveat.
- "axis → overall: min ... a weighted average would hide the F" is a rejected alternative; `scoring.py:5-7` ("Two aggregation levels, deliberately different") already holds it at the one site.

Change: delete the grade line, the "0–4" line and the Notes caveat; keep the min-aggregation sentence only if the `scoring.py` docstring does not state the "weighted average hides an F" reason (it states "deliberately different" without the reason; add the reason to the docstring and delete the README line).

### 7. Links: a code comment points at a deleted doc

`src/pocketquant/engine/market_data/sync_internals/provider_fetch.py:24`: "See docs/learning/retry-tuning-aggressive-vs-conservative.md for the decision". `docs/learning/` does not exist (deleted in `c613ed3b`). The same comment (line 22) says "+2s cron offset", but `sync_jobs.py:737` runs `sync_1m` at `second=12`.

Change: drop the doc reference; state the decision inline: "Retry is aggressive (0/3/8 s, 15 s budget) because the cron offset in `sync_jobs.py` already avoids the bar-close race; retry only covers residual provider hiccups." Remove the "+2s" number.

Low: three references cite heading titles that do not exist as written. `deploy/vps/one-time/00-server-setup.sh:152` and `deploy/vps/one-time/README.md:7` say "VPS Migration (new VPS)"; the heading is "VPS Migration". `scripts/backfill/binance_bars.py:32` says "2-Year Bar Re-Sync"; the heading is "Two-year bar re-sync". The links resolve; only the quoted titles are off.

All relative links and anchors in `README.md`, `CLAUDE.md`, `docs/**`, and `scripts/rubric/README.md` resolve (scripted check, 0 failures). `web/src/lib/indicators/engulfing.ts:65` and `scripts/rubric/scoring.py` point at docs that exist.

### 8. Governance rule: scope is undefined

`documentation-rules.md` never says which files the Line Test covers. The purge applied it to `docs/**` and `README.md`, partly to `scripts/rubric/README.md` (see 6), and not to `CLAUDE.md` (see 5). `deploy/vps/one-time/README.md` and `scripts/README.md` were not touched.

Change: add under the opening paragraph: "Scope: `CLAUDE.md`, `README.md`, and every `*.md` under `docs/`, `scripts/`, `deploy/` and `web/`. Code comments follow the comment policy in `code-standards.md`. `plans/` is exempt: it is a record."

### 9. Governance rule: rule 1 deletes runnable commands

Rule 1 says "Never copy the value" for paths, routes, ports and env vars. The README smoke test (`curl -X POST :41921/api/v1/market-data/sync ...`), the `just` block and every SSH command in `deployment.md` copy routes, ports and paths. A strict reader deletes them; the "Where Content Goes" table says the README holds them.

Change: add to rule 1: "A command or URL the reader runs is quoted whole. It is not a copy."

### 10. Governance rule: requirements vs rule 2 and rule 5 (needs the user)

Rule 2 ("Enforced: delete") and rule 4 ("A requirement ... keep") collide on `docs/project-overview-pdr.md`. Examples now in the PDR that a check enforces: "A bar is stored once" (unique index in `bar_repository.ensure_indexes`), "Mongo and Redis require auth in prod" (`deploy/vps/10-deploy.sh:38` refuses an empty `REDIS_PASSWORD`), "A new subscription starts stopped" (test in `tests/engine_test/test_strategy_service.py`). Rule 5 ("The code wins") also deletes a requirement line whenever code drifts from it, which is the one case where the doc should win.

Options:
- A. PDR is the requirement list: amend rule 4 to "A requirement: a sentence a test could fail. `project-overview-pdr.md` is the one list; a requirement stays there even when a test enforces it." Amend rule 5: "The code wins, except for a line in `project-overview-pdr.md`: there the code is the bug."
- B. PDR holds only vision and goals; move each requirement to a test name and delete the Functional/Non-Functional sections.

Recommend A: the PDR is 49 lines and is the only place a human can read what must stay true. Evidence that would flip to B: the owner never reads the PDR when reviewing.

### 11. Governance rule: small wording fixes

- "Where Facts Live: Routes: the OpenAPI page at `http://localhost:41921/api/v1/docs`" needs a running app. Add "or `app/routes/`".
- "Docs and code never link to them [plans]" is over-broad: `scripts/audit_bar_quality.py:5,60` writes its default output under `plans/reports/`. Change to "Docs and code never cite them as authority."
- Rule 4 "A fact outside this repo ... Say how it was verified." Good; the new `deployment.md` does this. Consider "how and when", since ufw rules and backup formats change without a commit here. The user's AS-IS rule may reject a date; leave as is if so.

### 12. Housekeeping

- `.claude/agent-memory/code-reviewer/MEMORY.md` is in the same working tree but is not part of the purge. Commit it separately.
- `docs/README.md`, `docs/visuals/`, `docs/journals/` and `docs/todo/` are already gone at HEAD (`4ba15de2`, `df01ef1c`); the current diff deletes only `methodology.md`, `codebase-summary.md` and `engine-scale-out-limitation.md`. The background note that journals were "moved" in this change is not what the tree shows; `plans/journals/` holds tracked files from earlier commits plus one untracked journal.

## Verified correct (so the review is not one-sided)

- README: every local profile sets `APP_ROLES=api` (`../pocketquant-config/local/{all-local,remote-db,remote-db-local-redis}.env`). The quote feed starts only under the trader role (`app/main.py:77-79`). The prod guard matches the VPS IP only (`tests/conftest.py:28,55`), so a tunnel URL passes it. `deploy/compose.local.yml` has only `mongodb` and `redis`, so "No local recipe serves the built UI" holds. `just test-tz` exists (`justfile`). `requires-python` is in `pyproject.toml:6`; `web/Dockerfile:4` pins the Node image.
- system-architecture: paper rows with neither SL nor TP are dropped at takeover (`engine/strategy/strategy_app_service.py:168-176`); the worker fails stale-heartbeat runs (`sync_jobs.py:655`); the cascade map is `TrackedSymbolService._symbol_data` (`tracked_symbols_service.py:101`); `:MT5` is pinned unregistered (`tests/core_test/infra/calendars/test_trading_calendar_factory_unseeded_default.py:50`); all four scale-out symbols exist; `ExnessBrokerAdapter` sends one `take_profit_price` (`exness_broker_adapter.py:285-286`); the risk check rejects EXIT/FLAT and an entry against an open position (`engine/execution/risk_check.py:21-37`); leases use `datetime.now(UTC)` (`lease_repository.py:28,44`).
- code-standards: "No test pins that upper-case" is true. `test_subscription_repository.py:50` upper-cases in the fixture; no test passes a lower-case symbol to `add_symbol`. HEAD's claim that the race test pins it was the wrong one.
- deployment (SSH-verified 2026-10-29): Vultr, Ubuntu 22.04; ufw active with 22/tcp and 52017/tcp only; SSH on 22; CI host file logs in as `root`; `/opt/pocketquant/backups` holds `.archive` files (gzip-ness not checked). `cicd.yml` has `paths-ignore` (lines 6-10), `concurrency` with `cancel-in-progress`, `cleanup-tags`, `verify-report`, `REMOTE_ROOT: /opt/pocketquant`, `deploy/.env` rsync. `00-server-setup.sh` defaults `SSH_PORT=49722`, creates `deploy`, sets `PermitRootLogin no`, prints `deploy@ip`.
- swing-pivot: the TP formula is in the `engulfing_strategy_service.py` module docstring; the key level is a deque held by the strategy (`:69-70`); `STRONG_THRESHOLD` appears only in `engulfing.ts`, so no test ties it to `max_rejection_wick_pct`.
- Facts cut from docs that a code site owns: APScheduler single-scheduler limit (`scheduling/scheduler.py:3-4`), 128-hex secret format (`exness_signer.py:28-30`), `ADMIN_TOKEN` 503 (`app/middleware` docstring), empty `REDIS_PASSWORD` refusal (`10-deploy.sh:35-39`), bid-price bars and spread (`paper_broker_adapter.py:108`), cover-a-short affordability (`:365-369`), SL-wins-over-TP and finest-interval exits (one hit each), 100-minute lookback and cascade-after-failed-fetch (`sync_jobs.py:347,371,728`), raw kurtosis, no-replacement bootstrap, MAE/MFE overstatement, latest-only scorecard, AST audit never runs the strategy (`scripts/rubric/*.py` docstrings), `STRICT_VALIDATION` reason (`app/di/__init__.py:8-9`).

## Assumptions

- The three local env files are the only local profiles (high; I listed `../pocketquant-config/local/`).
- Prod `MONGO_PORT` is 52017 (medium; inferred from the ufw rule and the listener list, not read from the prod `.env`). It does not change any finding.
- Backup archives are plain `mongodump --archive` (medium; names and the HEAD backup command agree; `file` was not run).
- The user wants `CLAUDE.md` under the same Line Test as `docs/` (medium; the rule's "Where Content Goes" table lists it as a home, so I treated it as in scope).

Status: DONE_WITH_CONCERNS
Summary: No lost knowledge except two WebSocket venue quirks; three wrong or misleading sentences in the new text (JobScheduler start, "one process" rejection, "never calls the engine"); one stale code comment to a deleted doc; the governance rule needs a scope line, a commands exception, and a user decision on how requirements in the PDR interact with "enforced: delete" and "code wins".
