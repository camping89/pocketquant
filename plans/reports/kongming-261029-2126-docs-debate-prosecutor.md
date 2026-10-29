# Docs debate: PROSECUTOR (delete) — 2026-10-29

Direction: the reader is an LLM agent that can grep and read code in seconds, plus a human owner who reviews what the agent writes. Every sentence that restates code is a liability. This report argues the deletion case as hard as the evidence allows. Every claim about a doc is checked against the file and the code it describes.

## TL;DR

Cut `docs/` from about 3,980 lines (docs + root README + CLAUDE.md) to under 500. Delete nine of the fifteen non-journal files outright, move the 27 journals out of `docs/`, and cut the three survivors (`system-architecture.md`, `code-standards.md`, `deployment.md`) to the parts that are not in the repo: decisions with a rejected alternative, venue quirks measured outside the repo, and procedures that touch the VPS or `pocketquant-config`. The evidence is not taste: the docs are wrong today on at least eight verifiable facts (ENABLE_JOBS, contract count, job second, paper-position boot drop, four ERD keys), and 137 of 722 commits (19%) touched one of the six core docs just to keep them in step.

## The evidence that drives the verdicts

Verified against code on 2026-10-29. Each row is a fact a doc states that the code contradicts.

| Doc says | Where | Code says | Where |
|---|---|---|---|
| `ENABLE_JOBS=false just be` is the fast dev mode; `remote-db.env` ships with `ENABLE_JOBS=false` | `README.md:39,47,60,66-68`; `docs/system-architecture.md:52`; `docs/deployment.md:218-221` | `ENABLE_JOBS` is retired; setting it raises `ValueError` at startup. Local env files set `APP_ROLES=api`. | `src/pocketquant/core/config.py:109-114`; `../pocketquant-config/local/all-local.env:34`, `remote-db.env:42` |
| 8 import-linter contracts | `README.md:102`; `docs/code-standards.md:295` | 6 contracts (CLAUDE.md:18 is right) | `pyproject.toml` (`[[tool.importlinter.contracts]]` x6) |
| `sync_1m` runs at second :02 | `docs/system-architecture.md:140`; `docs/project-overview-pdr.md:81` | `second=12`; there is also a `backtest_orphan_sweep` job at :40 that no doc lists | `src/pocketquant/engine/market_data/app_services/sync_jobs.py:735-781` |
| At boot `PositionAppService` deletes paper rows and logs `count` + `paper_dropped` | `docs/system-architecture.md:202` | "Every open row is kept"; logs `count` only. The paper drop happens in the strategy engine take-over. | `src/pocketquant/engine/execution/position_app_service.py:36-42`; `src/pocketquant/engine/strategy/strategy_app_service.py:193-199` |
| "One process, one worker" is the decision; "only one of them runs the scheduler" | `docs/system-architecture.md:7`; `docs/project-overview-pdr.md:110` | Lease-holding roles: `APP_ROLES` picks api/worker/trader; a second copy stands by | `src/pocketquant/app/roles.py:1-5`; `config.py:61-64`; `lease_repository.py` exists |
| Subscriptions `_id` = deterministic hash; `job_history._id` = ObjectId; `tracked_symbols._id` = natural key; `broker_order_id -> OKX` | `docs/visuals/collection-erd.mmd:43,46,62,95` | All uuid7; no OKX anywhere in `src/`; `trades`, `safeguards`, `leases` collections missing from the ERD | `subscription_repository.py:19`; `job_history_repository.py:36`; `tracked_symbol_repository.py:9`; `repositories/` listing |
| The key-level window is computed by `BarBuilderDomainService` | `docs/swing-pivot-key-level.md:14` | A `deque(maxlen=key_level_lookback_bars)` inside the strategy | `engulfing_strategy_service.py:69` |
| `template_id` is a deprecated id to watch for | `docs/code-standards.md:166` | Zero hits in `src/` and `web/src` | grep |
| Package map | `docs/codebase-summary.md:13-43` | Missing `app/roles.py`, `app/common/`, `web/src/constants`, `web/src/types`, `lease_repository.py` | `ls` |

Churn: `git log` counts 93 commits on `system-architecture.md`, 64 on `code-standards.md`, 56 on `README.md`, 45 on `project-overview-pdr.md`, 44 on `codebase-summary.md`, 32 on `deployment.md`. 137 distinct commits out of 722 touched at least one of them. That is the maintenance tax of restating code, and the table above shows the tax was not even enough.

Duplication (the same fact in three places): the route rule (`CLAUDE.md:17`, `code-standards.md:86-89`, `system-architecture.md:30`); composite-symbol routing (`code-standards.md:134-144`, `system-architecture.md:116-121`, `provider_routing_domain_service.py`); `set_sync_container` before first await (`system-architecture.md:47`, `code-standards.md:185-201`, and the comment in `app/main.py` that both cite); the rubric aggregation rule (`backtest-rubric/methodology.md:16-26`, `scripts/rubric/README.md:39-45`, `scripts/rubric/scoring.py:1-11`); local-against-prod (`README.md:45-70` and `deployment.md:207-223`, both wrong on ENABLE_JOBS).

## Methodology: the "write a doc or not" test

Default: no doc. A sentence earns its place only by surviving all six tests, applied line by line by the reviewer.

1. **Trace test.** Can an agent get this fact from one grep or one file open (a name, a path, a signature, a route, an env var, a schema, a list, a default, a schedule)? Then delete it. If a pointer helps, write the path only, never the content.
2. **Drift test.** Does the sentence hold a number, a name, a list or an order that the code also holds? Then delete it. Two copies always diverge; the table above is the proof. The code copy wins by definition (`docs/README.md:3` already says so).
3. **Enforcement test.** Is the rule enforced by a test, a linter, a validator or CI? Then delete the prose and keep the check. Import-linter, `test_domain_purity.py`, `test_data_provider_registration.py`, `config.py:109-114` and `cicd.yml:28` already enforce most of what `code-standards.md` and `system-architecture.md` explain.
4. **Residue test.** What survives must be one of exactly three kinds: (a) a decision with a rejected alternative that no test pins (why margin accounting, why no provider fallback); (b) an external fact not derivable from the repo (a venue quirk measured in a spike, a Cloudflare route, the `pocketquant-config` layout); (c) a procedure that touches something outside the repo (deploy, rollback, re-sync, break-glass).
5. **Placement test.** Put the residue at the point of decision: a module docstring or a comment on the line that makes the choice. A doc file is allowed only when the residue spans three or more modules, or it is an ops procedure. History (what happened, what was tried, who decided) goes to `plans/` or the commit message, never to `docs/`.
6. **Budget test.** `docs/` holds at most: `governance/`, one decisions doc, one standards doc, one ops doc. Root `README.md` holds run and smoke-test commands. `CLAUDE.md` holds the rules that change decisions and the pointers. A new file under `docs/` needs the owner's explicit sign-off in the same change.

What to do instead of writing a doc:

- A fact about code: nothing, or a path pointer.
- A "why": a two-line comment at the decision site (the comment policy in `code-standards.md:245-252` already allows exactly this).
- A behavior that must not change: a test that pins it (`code-standards.md:273` already says so).
- A procedure inside the repo: the script's `--help` and module docstring (`scripts/README.md` already does this).
- A plan, a roadmap, a session record: `plans/` (it already has `plans/journals/`).

## Per-file verdicts

### Root and index files

**`CLAUDE.md` (37 lines) — KEEP, cut 2 lines.** This is the only file read every session; rules live here or nowhere. Cut: line 17's route rule is also at `code-standards.md:86-89` and `system-architecture.md:30`; keep this copy, delete the other two. Line 36 is a sentence-long index; after the cuts below it becomes three paths. Line 18 ("6 contracts") is the only correct count in the repo.

**`README.md` (116 lines) — CUT to about 60.** Keep lines 1-5, 23-37, 81-94, 96-108 (trimmed), License. Delete: 9-21 (tree and contracts repeat `CLAUDE.md:3,18,19`); 39 (crashes the app, `config.py:109-114`); 40-43 (routing and TZ are in `provider_routing_domain_service.py` and `assert_utc_runtime`); 45-70 (duplicates `deployment.md:207-223` and is wrong on ENABLE_JOBS; replace with one line: "env profiles and their modes: `../pocketquant-config/local/*.env`, see each file's header", `remote-db-local-redis.env:3` already carries one); 102 ("8 contracts" is wrong); 112 (links a file being deleted).

**`docs/README.md` (34 lines) — DELETE** (decided by the user). Nothing else links to it except `README.md:112`; grep found no other reference.

**`docs/governance/README.md` (10 lines) — KEEP.** It is the index the new rule lands in and `CLAUDE.md:7` points at it.

### Core docs

**`docs/codebase-summary.md` (95 lines) — DELETE.** Lines 13-43 are `ls` output, already stale (missing `app/roles.py`, `app/common/`, `lease_repository.py`, `web/src/constants`, `web/src/types`). Lines 45-73 are a grep table; the naming convention (`code-standards.md:71`: "the class + file name self-encodes layer/role") exists precisely so that grep by name works. Lines 75-88 equal `grep "class .*AppService" src`. Lines 5-9 are `pyproject.toml` and `web/package.json`. Lines 90-95 repeat `code-standards.md:270-276`. 44 commits spent keeping a directory listing current.

**`docs/system-architecture.md` (245 lines) — CUT to about 60 (rename to `decisions.md` if the owner wants the name to match).** Delete, with the code location that makes each traceable:
- 15-25 Layers table: `CLAUDE.md:3` plus import-linter.
- 27-31 Request flow: `main_extensions.py:279-293` (middleware order and the 200/20 numbers are on line 292).
- 33-41 DI: three files in `app/di/`.
- 43-54 Startup: `app/main.py` `lifespan()`; line 52 is wrong (ENABLE_JOBS); the `set_sync_container` why is already at `code-standards.md:185-201` and in the `main.py` comment both cite.
- 134-154 Background jobs: `sync_jobs.py:728-798`; line 140 is wrong (:12 not :02); the table misses `backtest_orphan_sweep`; the job-history rules 149-154 are the `_tracked` docstring.
- 156-168 Data lag: constants with docstrings at `data_lag_service.py:39-52`.
- 170-185 Streaming numbers: `exness_stream.py:1-7` docstring states backoff 1-30 s and the 10-failure/300 s breaker; `binance_websocket_adapter.py:98`; the SSE routes are the OpenAPI page.
- 187-194 Broker table; 204-211 Exness broker: `exness_client.py:1-8` docstring, `broker_factory.py`, and the env table in `deployment.md`.
- 196-202 Paper lifecycle: line 202 is wrong (see evidence table).
- 213-232 Persistence and symbol removal: `repositories/` listing (ERD-level detail, missing `leases`); `TrackedSymbolService.remove` is a 30-line method that reads faster than its prose.
- 234-236 Deployment shape: `deployment.md`.
- 243-245 MT5: no code exists; speculation about unrequested work (`CLAUDE.md:27`).

Keep, as the decisions doc: 5-13 (rewrite line 7 to the lease model); 97-112 paper-broker accounting with its why (line 106 is a real decision with a rejected alternative, pinned nowhere in prose except a journal; better still, move it to the `paper_broker_adapter.py` module docstring, which today says nothing about margin vs spot); 119 "no fallback, because another provider's bars are a different instrument" (move to `provider_routing_domain_service.py` docstring); 175 the Exness `subscribe`-adds quirk (half of it is already the comment at `exness_stream.py:27`); 238-241 Limitations.

**`docs/code-standards.md` (308 lines) — CUT to about 110.** Delete:
- 5-11 Principles: `CLAUDE.md:24-30` plus import-linter; line 7 even admits "this file does not restate them" and then the rest of the file does.
- 13-22 Helper and size: `CLAUDE.md:25-29` and `scripts/code_metrics.py`.
- 28-67 File and class naming tables: `ls src/pocketquant -R` shows the convention; every row is an existing file name. One `*Helper` exists (`symbol_lookup_helper.py:25`), so the "only when justified" row is a listing, not a rule.
- 69-82 Exemptions: same.
- 84-102 Routes: `CLAUDE.md:17` plus any file in `app/routes/`; the exception map 90 is `core/common/exceptions.py`.
- 104-108 DI: duplicate of system-architecture 33-41 and `app/di/`.
- 110-132 Domain and repositories: `CLAUDE.md:16,20` plus `entities.py`; the code block 119-132 is an anti-pattern gallery for a rule a one-line grep (`_id`) checks.
- 134-144 Composite symbol: third copy; `provider_routing_domain_service.py` and `symbol/entities.py`.
- 158-168 Strategy IDs: row 166 names an identifier that no longer exists; the dedup-index sentence 168 is the `subscription_repository.py:19-30` docstring.
- 174-183 await table: Python semantics, not project knowledge; 224-231 checklist: generic.
- 270-276 Testing: keep two lines (pin before refactor; no DB mocks for query/index tests); the tz rule is `cicd.yml:28` and `justfile:70`.
- 278-284 Performance: generic.
- 286-302 Quality gate: the command table duplicates `README.md:98-104`; line 295 says 8 contracts (6).
- 304-308 Config and secrets: `CLAUDE.md:11-12` and `deployment.md:107-108`.

Keep: 146-156 "Adding a data provider" (nine touch points across layers, only three enforced by `test_data_provider_registration.py`); 170-172 and rules 1-6 at 185-222 (the one "why" section with a race that no test pins, but trim the duplicated `set_sync_container` example to a path); 233-268 comment policy (this is the policy the present exercise applies; it cannot be traced from code); 301 the ratchet policy sentence.

**`docs/deployment.md` (286 lines) — CUT to about 140.** This file has the most residue of kind (b) and (c) and is the one doc that earns its place. Delete: 17-27 (job names from `cicd.yml`); 29-31 (`cicd.yml:13-15,28`); 56-58 container list (`compose.prod.yml` services, six of them); 93-116 env table (every row's meaning is a `Settings` field with a docstring in `config.py`; the one deploy-side behavior, "empty REDIS_PASSWORD refuses", lives in `10-deploy.sh`); 119 port map (`compose.prod.yml`); 177-187 troubleshooting (generic docker; the boot-pattern list is `11-verify.sh:187`); 196-223 local-against-prod (duplicate of README 45-70, wrong on ENABLE_JOBS at 218-221; replace with the env-profile pointer); 225-231 firewall (`deploy/vps/one-time/00-server-setup.sh`). Keep: 5-11 branch model (a convention not in code; it could become a CI check, which would then let the prose go); 15; 35-54 verify; 60-70 URLs and edge (external); 72-92 credential routing and `pocketquant-config` layout (external repo); 121-129; 133-175 runbooks (break-glass, external); 233-241 migration; 243-282 data runbooks trimmed to order of operations and the backup step (flags are each script's `--help`).

**`docs/project-overview-pdr.md` (110 lines) — DELETE.** F1-F10 are route lists and feature restatements; line 3 itself says the route list is the OpenAPI page. Line 81 is wrong (:02). NF6 line 110 is superseded by the lease model. Lines 5-14 (vision, four goals) are the only residue; `README.md:3` already states what the system is, so fold the four goals into that paragraph. 45 commits on a requirements doc for a one-owner project.

### Topic docs

**`docs/engine-scale-out-limitation.md` (37 lines) — DELETE.** Lines 7-12 are four pointers to symbols that all exist and say the same thing in their signatures: `Signal.take_profit_price: float | None` (`strategy/value_objects.py:18`), `on_bar_completed -> Signal | None`, `_check_sl_tp` (`paper_broker_adapter.py:579`), `_fire_synthetic_exit` (:602), `position_key` (:344). The limitation is the type; one grep. Lines 27-37 plan unrequested work (`CLAUDE.md:27`: no possible callers). Last touched 2026-07-06. Residue, if the owner wants intent kept: one sentence in the `Signal` docstring.

**`docs/swing-pivot-key-level.md` (73 lines) — DELETE.** The TP formula at 29-32 is verbatim in the strategy module docstring (`engulfing_strategy_service.py:8-11`). Line 14 misattributes the window to `BarBuilderDomainService` (it is `engulfing_strategy_service.py:69`). Line 23 cites a "brainstorm-report" that is not in `docs/`. Line 73's chart caveat already exists as the comment at `engulfing.ts:63-65`, which points back to this doc; rewrite that comment to stand alone. Residue: "proxy, not pivot detection" and "a chart marker is not an entry (warmup, one-position cap)" become one sentence each in the strategy docstring and the `engulfing.ts` comment.

**`docs/backtest-rubric/methodology.md` (134 lines) — DELETE; fold three sentences into `scripts/rubric/README.md`.** Bands 33-51 and weights 55-70 are the dicts at `scoring.py:33` and `:58`; formulas 85-101 are the function bodies in `empirical_metrics.py` and `robustness.py`; aggregation 16-26 is the `scoring.py:1-11` docstring and `scripts/rubric/README.md:39-45` (triple); the crypto-1m caveat is `scoring.py:15-17`; `scoring.py:12` points at this doc for "industry references" and the doc gives none, so the pointer is circular. Residue: returns-basis choices (74-83, half already at `empirical_metrics.py:9`) and the raw-vs-excess kurtosis trap (105-106), which belongs as a comment on the PSR line.

**`docs/todo/deflated-sharpe-pbo-cscv-roadmap.md` (100 lines) — DELETE from `docs/`; a five-line todo in `plans/` or an issue.** It is a plan, and `plans/` is where plans live. Lines 26-78 summarize two public papers whose links are at 96-100. The only project-specific content is 7-12 and 18-24 (no sweep harness; `/backtest/optimize` was removed). Last touched 2026-07-11, nothing references it.

**`docs/visuals/collection-erd.mmd` + `collection-erd.png` — DELETE.** Four wrong keys and one wrong venue (evidence table), three collections missing, zero references from any `.md` or code, a binary that cannot be diffed. Last touched 2026-09-24, before the lease and safeguards collections existed.

### Journals (`docs/journals/`, 27 files, 2,297 lines) — DELETE from `docs/` (move to `plans/journals/` if the owner wants them browsable)

The category argument: `CLAUDE.md:23` says docs hold no history; `docs/README.md:27` says journals are "not authority" and "age". A folder of not-authority history inside the authority tree fails tests 4 and 5 by its own description. `plans/journals/` already holds ten journals of the same kind, so two journal folders exist with two date formats (`2026-06-28-` and `260630-`). 13 of 27 follow a "Brutal Truth" narrative template. Git keeps every one of them.

The two facts plans cite from a journal are now in code: Exness session times (`2026-10-13-exness-api-spike.md:44-45`) are `exness_session_calendar_adapter.py:53-66`; transport quirks are `exness_stream.py:1-7,27` and `exness_client.py:3-8`. The one fact I could not find in code is the "10 active WS connections per account per node" limit (`:38`); that is a one-line comment at the connection site in `exness_stream.py`, not a 124-line journal.

| File | Reason |
|---|---|
| `2026-06-28-backtest-fill-sharpe-grid-isolation-fix.md` | Fix narrative; the fix and its test are in git. |
| `2026-06-28-engulfing-full-candle-coverage-fix.md` | Fix narrative; edits a doc this report deletes. |
| `2026-06-28-engulfing-strategy-implementation.md` | Implementation log; the strategy file is the record. |
| `2026-06-28-paper-broker-futures-accounting.md` | The only "why" (margin vs spot) is already `system-architecture.md:106`; move it to the broker docstring, drop the 159-line story. |
| `2026-06-29-backtest-single-run-direct-task.md` | Refactor log. |
| `2026-06-29-web-claude-theme-and-ui-tweaks-complete.md` | UI tweak log. |
| `2026-06-30-backtest-research-workbench.md` | 22-line feature log. |
| `2026-07-05-r2-engine-restructure.md` | Refactor log (R-series). |
| `2026-07-05-r3-commission-abstraction-brainstorm.md` | Brainstorm; the decision is the code. |
| `2026-07-05-r3-commission-abstraction-implementation.md` | Implementation log. |
| `2026-07-05-r4-broker-trade-emission-remove-fifo.md` | Refactor log. |
| `2026-07-05-service-naming-convention-rename.md` | The convention is visible in file names. |
| `2026-07-06-r5-report-service-gut-equity.md` | Refactor log. |
| `2026-07-06-r6-position-calculator.md` | The circular-import workaround belongs as a comment at the `TYPE_CHECKING` site. |
| `2026-07-06-r7-config-defaults.md` | Defaults are in `config.py`. |
| `2026-07-06-r8-live-run-extraction.md` | Refactor log. |
| `2026-09-21-asset-class-trading-calendar.md` | Design log; calendars are `core/infra/calendars/`. |
| `2026-10-13-exness-api-spike.md` | External measurements; the two not yet in code go to comments at the retry site in `exness_client.py` and the connect site in `exness_stream.py`. If one journal must survive, this one. |
| `2026-10-19-exness-broker-off-by-default.md` | Ship record; "Open before go-live" (21-25) is plan material. |
| `2026-10-19-exness-docs-and-mt5.md` | MT5 speculation, duplicate of `system-architecture.md:243-245`. |
| `2026-10-19-exness-market-data-in-prod.md` | Ship record. |
| `2026-10-19-exness-spread-backtests.md` | Run record. |
| `2026-10-20-exness-go-live-plan-debate.md` | Plan record; belongs under `plans/261019-1957-exness-go-live/`. |
| `260630-backtest-workbench-master-detail-ux.md` | UI log; second date format. |
| `260702-backtest-trades-paging-server-analytics.md` | Feature log. |
| `260710-commission-3bps-recompute-double-persist-race.md` | Records an unfixed engine race (double subscribe) as prose; that is an issue or a comment at the subscribe site, not a doc. |
| `260711-backtest-rubric-scorecard-module.md` | Duplicate of `scripts/rubric/README.md`. |

## Where the "keep the why" position is weak

- Most of the "why" already sits at the decision site or in a test: `config.py:111` explains why ENABLE_JOBS is refused; `sync_jobs.py:13-14` explains why `data_lag_check` runs mid-minute; `exness_stream.py:27` records the subprotocol quirk; `subscription_repository.py:19-30` explains the dedup index; `engulfing_strategy_service.py:8-11` holds the TP rule. The docs restate these a second and third time.
- The "why" that docs claim to own was still wrong: `system-architecture.md:202` explains why paper rows are deleted at boot, and the code now keeps them. A why attached to a stale what is worse than nothing.
- The genuinely untraceable why is small: margin accounting (one paragraph), no provider fallback (one line), the branch model, the venue quirks. It fits in CLAUDE.md plus a 60-line decisions doc plus docstrings. It does not justify 1,500 lines of core docs.
- The human owner reads the code anyway (`CLAUDE.md:24`: "review and control AI-written code"). A doc that the owner must also verify against the code doubles the review surface.

## Strongest counter-argument against this position

An LLM agent pays the grep cost every session, while a 60-line decisions doc is read once and cached in context; and the human owner cannot grep at agent speed, so the cross-module narratives (startup order, signal flow, the three Exness gates) are the one place a reviewer sees the whole flow without opening eight files. Deleting them trades a visible, fixable drift problem for an invisible one: an agent that reconstructs the flow from code each time will reconstruct it slightly differently each time, and nobody will notice.

## Success metrics

- `docs/` + `README.md` + `CLAUDE.md` under 500 lines (from about 3,980).
- A grep audit finds zero numeric facts (schedules, limits, counts, defaults) in `docs/` that also exist in `src/`.
- Docs-touching commits fall from 19% of history to under 5% over the next 100 commits.
- `ENABLE_JOBS` appears nowhere in the repo except `config.py:109-114`.

## Assumptions

- The user's "obvious" means "traceable by an agent with grep", as the orchestrator framed it (high confidence; it is the stated direction).
- Journals were judged by category, six sampled files, and titles; I did not read all 27. If a journal holds an external fact not in code, the fix is a comment at the site, not keeping the file (medium confidence on the per-file reasons, high on the category verdict).
- The `.png` ERD matches the `.mmd`; I could not diff the binary (medium).
- `plans/` is the accepted home for plans and journals; `plans/journals/` already exists with ten files (high).
- Deleting a git-tracked file loses nothing; the owner accepts `git log -- <path>` as the archive (high; CLAUDE.md:23 says git keeps history).
