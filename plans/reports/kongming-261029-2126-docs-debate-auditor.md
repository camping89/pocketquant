# Docs debate — AUDITOR position (drift and trace cost, measurable)

Date: 2026-10-29. Branch: develop. Scope: every file under `docs/`, root `README.md`, `CLAUDE.md`. `docs/README.md` is already decided (delete).

## TL;DR

Replace "obvious" with three mechanical tests: **owner** (does one machine-owned file already hold the fact?), **trace** (can an agent establish it in at most two tool calls?), **drift** (is the line already wrong?). Applied to this repo the tests find 27 stale claims in the core docs and a 31 % dead-path rate in `docs/journals/`. One retired flag (`ENABLE_JOBS`) is still documented in seven places across three docs; one count (import-linter contracts) is written as 8 in two docs and 6 in a third. Delete the journals, the visuals and `docs/README.md`; cut every copied number, path table and route list down to a pointer; keep decisions, negative knowledge, cross-file checklists and outside-repo operations. The re-growth guard: a doc line that names a number, path, symbol or route must cite the owning file, and the author must show the grep that failed to find the fact in code first.

## Why "obvious" and "easy to trace" are not usable as written

Both words describe the reader, not the fact. A reviewer cannot apply them. Evidence from this repo that the current, judgement-based rule does not hold the line:

- `CLAUDE.md:18` says "6 contracts". `README.md:102` and `docs/code-standards.md:295` say 8. `pyproject.toml` has six `[[tool.importlinter.contracts]]` blocks (lines 78-125). The same fact, three docs, two values.
- `ENABLE_JOBS` is retired: `src/pocketquant/core/config.py:111-114` raises `ValueError("ENABLE_JOBS is retired; set APP_ROLES ...")`. It is still documented as the live switch at `README.md:39`, `:47`, `:68`, `docs/system-architecture.md:52`, `docs/deployment.md:218`, `:219`, `:221`. A reader who follows the docs gets a crash on boot.
- `sync_1m` fires at `second=12` (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:737`). `docs/system-architecture.md:140` says ":02"; `docs/project-overview-pdr.md:81` says "second 2".

Every one of these is a number copied from a file that was later edited. That is the cost of duplication, measured.

## Methodology: write a doc line or not

Apply the three tests in order to **each line** (not each file). The first test that fires decides.

### Test 1 — Owner test (is there already a machine-owned source?)

A fact is *machine-owned* when a file that the program, a test, CI or a tool reads holds it: code, `config.py`, `pyproject.toml`, `justfile`, `.github/workflows/*.yml`, compose files, a test, a schema, a script docstring.

- Owned fact → the doc may hold **a pointer** (`path`, optionally `symbol`), never the value. "Rate limit: `RateLimitMiddleware` in `app/main_extensions.py`" passes; "200 tokens, 20 per second" fails.
- Reviewer check: for each number, path, symbol, route or env name in the line, run one `grep`. If it hits a non-doc file, the line is a copy.

### Test 2 — Trace test (how many tool calls to establish it from the repo?)

Count the tool calls an agent needs with no doc: one `Grep`/`Glob` on the name plus one `Read` of the hit.

- **≤ 2 calls, one file** → do not write it. Examples: a class's file (naming convention encodes it), a job's schedule, a constant's value, a middleware order, a route list (`/api/v1/openapi.json`).
- **≥ 3 files, or cross-layer, or cross-repo** → write it. Examples: "adding a data provider touches these nine places" (`docs/code-standards.md:146-156`), the startup order across `main.py` + `roles.py` + `main_extensions.py`, anything that depends on `pocketquant-config/`, the VPS, Cloudflare or Exness behaviour.
- **Negative knowledge** (what does not exist) → write it, briefly. A grep cannot prove absence: no scale-out, no routing fallback, MT5 not built, no concurrency cap on backtests.
- **Decision and rejected alternative** → write it, as a "why" at the owning site first (a code comment or test name), in a doc only when it spans files.

### Test 3 — Drift test (is it already wrong?)

Before touching a doc, run the mechanical checks below and fix or delete every red line. A doc that fails the drift test is evidence that the line should not have been written, not a reason to write it again.

Mechanical checks a reviewer can run today:

1. **Path existence**: extract every `*.py|ts|tsx|sh|yml|toml|json|md|mmd` token from the doc and test the path exists (the script used for this audit is reproduced below). Target: 0 missing per doc.
2. **Counts**: `grep -c '^\[\[tool.importlinter.contracts\]\]' pyproject.toml`; `grep -c 'job_id=' sync_jobs.py` vs the jobs table; `grep -o 'COLLECTION_[A-Z_]*' core/common/constants.py` vs the collections table; `ls app/di/*.py` vs "three providers".
3. **Names**: every backticked symbol in the doc must `grep` to one hit in `src/` or `web/src/` (`template_id` at `docs/code-standards.md:166` has zero hits).
4. **Retired flags**: every env var named in a doc must be a field of `Settings` in `config.py`.

### Where content moves instead of being deleted

| Content type | Move to |
|---|---|
| A "why" about one function, ordering or race | Comment at that site (comment policy already allows WHY, `docs/code-standards.md:245-251`) |
| A rule a test can pin | The test; its name is the doc (e.g. `test_data_provider_registration.py`) |
| A number or schedule | Nowhere; the constant is the doc. Give it a name if it has none. |
| A gotcha an agent gets wrong without being told | `CLAUDE.md` (its stated purpose, `CLAUDE.md:3`) |
| A cross-file checklist, negative knowledge, outside-repo operation | Stays in `docs/` |
| Session narrative, decision history | `git log`; nowhere else |

### Re-growth guard (the governance rule)

A pull request may add a line to `docs/` or `README.md` only when all of the following hold, and the reviewer can check each with one command:

1. The line passes the owner test: it cites its owner (`path`, optional `symbol`) and copies no value from it.
2. The line passes the trace test: it needs ≥ 3 files, is negative knowledge, is a decision, or concerns a system outside this repo. The author writes the failed grep (the name they searched that returned nothing in code) in the PR description.
3. The doc it lands in passes the drift test after the change (path check 0 missing; counts match).
4. If the same fact is already in another doc, the PR deletes one copy. One fact, one doc, at most one pointer elsewhere.

Default when unsure: write a WHY comment at the owning code site, not a doc line.

## Measured drift

### Path-existence sweep (285 path references across all in-scope docs)

| Group | Refs | Missing | Rate |
|---|---|---|---|
| Core docs + README + CLAUDE.md | 156 | 0 (the one `cicd.yml` hit is a false positive: it lives under `.github/`, which the sweep skipped) | 0 % |
| `docs/journals/` (29 files, 2,297 lines, 59 % of all doc lines) | 129 | 40 | 31 % |

The core docs name real files but copy wrong values; the journals name files that no longer exist. Both are drift, of different kinds.

### Stale claims (doc → code)

| # | Doc claim | Code (current truth) |
|---|---|---|
| 1 | `README.md:102` "8 import-linter contracts" | `pyproject.toml:78-125`: 6 contract blocks |
| 2 | `docs/code-standards.md:295` "Contracts: 8 kept" | same |
| 3 | `README.md:39` `ENABLE_JOBS=false just be` | `src/pocketquant/core/config.py:111-114` raises: flag retired, use `APP_ROLES` |
| 4 | `README.md:47` "remote-db.env ships with ENABLE_JOBS=false" | `config.py:114`; all three `../pocketquant-config/local/*.env` set `APP_ROLES=api`, none sets `ENABLE_JOBS` |
| 5 | `README.md:68` "set ENABLE_JOBS=true" | `config.py:114` |
| 6 | `README.md:47` "The live WS feed still runs" with jobs off | `src/pocketquant/app/main.py:77-79`: quote feed starts only when `"trader" in roles`; local envs are `api` only |
| 7 | `docs/system-architecture.md:52` "`ENABLE_JOBS=false` skips the background jobs ... The quote feed still runs" | `config.py:114`; `main.py:77-82` |
| 8 | `docs/system-architecture.md:3,7`, `README.md:19-21`, `docs/project-overview-pdr.md:109-110` "one process, one worker; in-process singletons" | `CLAUDE.md:19`, `src/pocketquant/app/roles.py:1-5`, `deploy/compose.prod.yml:75`: roles + Mongo leases; a second copy waits in standby |
| 9 | `docs/system-architecture.md:45-50` startup order (indexes → recovery sweeps → bootstrap → health → quote feed → start_jobs) | `main.py:63-82`: indexes → health checks → trader (standby + bootstrap, quote feed, lease) → worker; `roles.py:119-127` runs `recover_orphan_jobs` after the worker lease |
| 10 | `docs/system-architecture.md:49` "This runs even when jobs are off" (bootstrap_live_instances) | `roles.py:170-176` inside `start_trader_standby`, called only for the trader role (`main.py:77-78`) |
| 11 | `docs/system-architecture.md:140`, `docs/project-overview-pdr.md:81` sync_1m at ":02" / "second 2" | `sync_jobs.py:735-737` `second=12` |
| 12 | `docs/system-architecture.md:138-146` jobs table (6 jobs) | `sync_jobs.py:777-781` also registers `backtest_orphan_sweep`, every 5 min at :40 |
| 13 | `docs/system-architecture.md:217-228` collections table | `src/pocketquant/core/common/constants.py:22` `COLLECTION_LEASES = "leases"`; `lease_repository.py:24` — not listed |
| 14 | `docs/system-architecture.md:202` "deletes the open `positions` rows of paper subscriptions ... logs `loaded_open_positions` with `count` and `paper_dropped`" | `src/pocketquant/engine/execution/position_app_service.py:36-42`: every open row is kept, log has `count` only; `paper_dropped` is logged under `strategy_engine.took_over` (`strategy_app_service.py:192-199`) |
| 15 | `docs/deployment.md:218`, `:219`, `:221` `ENABLE_JOBS` ×3 | `config.py:114` |
| 16 | `docs/swing-pivot-key-level.md:14` key level "computed by `BarBuilderDomainService`" | `engulfing_strategy_service.py:69-91`: deques held by the strategy; `grep key_level core/domain` hits only the two strategy files |
| 17 | `docs/swing-pivot-key-level.md:23` "(see brainstorm-report)" | no such file under `docs/` |
| 18 | `docs/visuals/collection-erd.mmd:41` SUBSCRIPTIONS `_id` "deterministic hash(strategy_code\|symbol\|interval)" | `src/pocketquant/core/domain/subscription/entities.py:54` `"_id": str(self.id)` (UUID); contradicts `CLAUDE.md:20` |
| 19 | `docs/visuals/collection-erd.mmd:38` TRACKED_SYMBOLS "composite = natural _id" | `tracked_symbol_repository.py:9` "uuid7 `_id`, unique index on `symbol`" |
| 20 | `docs/visuals/collection-erd.mmd` relation SUBSCRIPTIONS → BACKTEST_RUNS "subscription_id (cached result)"; no `trades`, `job_history`, `safeguards`, `leases` | `docs/system-architecture.md:81` "independent of subscriptions"; `constants.py` collection names |
| 21 | `docs/code-standards.md:166` `template_id` "deprecated old name" | 0 occurrences in `src/` and `web/src/` — dead row |
| 22 | `docs/codebase-summary.md:25` `core/common/` holds "event bus, middleware, tracing, logging, health, exceptions, UUIDv7" | actual dirs: `constants`, `exceptions`, `health`, `logging`, `messaging`, `rate_limit`, `time`, `tracing`, `uuid.py` — no `middleware` dir; three dirs unlisted |
| 23 | `docs/codebase-summary.md:68` "Startup order → `app/main.py` (`lifespan`)" | role start order is in `app/roles.py` |
| 24 | `docs/system-architecture.md:147` "At boot, `enqueue_missed_catchups`" | `roles.py:119-127`: after the worker lease, not at boot of an api-only process |
| 25 | `docs/system-architecture.md:54` shutdown "drains backtests, stops reconcile loop and quote feed, then close" | `main.py:92-113`: `stop_worker` + `hand_over` gather first, then drain, reconcile, feed, close |
| 26 | `docs/backtest-rubric/methodology.md:104` "at n=6 runs" | a DB snapshot, not a code fact; unverifiable in an AS-IS doc |
| 27 | `docs/journals/*`: 40 of 129 path references dead, e.g. `2026-07-05-r2-engine-restructure.md` cites 5 files that do not exist | path sweep |

Verified-correct samples (so the audit is not one-sided): rate limiter 200/20 (`main_extensions.py:292`), middleware order (`:284-293`, Starlette last-added-outermost), `RECONCILE_INTERVAL_SECONDS` default 5 (`config.py:98`), data-lag thresholds 3 min / 10 syncs / 30 min / 5 min (`data_lag_service.py:39-52`), Binance backoff 1-60 s (`binance_websocket_adapter.py:31-32`), Exness backoff 1-30 s, breaker 10/300 s, subprotocol (`exness_stream.py:27-31`), catch-up gaps 25 h / 12.5 h (`sync_jobs.py:95-98`), `TTL_QUOTE_LATEST = 60`, SSE polls 1.0 / 0.5 s (`routes/market_data.py:60`, `market_data_quotes.py:23`), 5 CI jobs, 6 prod containers, nginx `limit_conn sse 10` (`web/nginx.conf:27`), rubric bands and weights identical to `scripts/rubric/scoring.py:31-77`, `ix_subscriptions_dedup_triple`, all four scale-out symbols, `exit 3` in `provider_bars.py:78`. Every one of these correct lines is still a copy that will go the way of the 27 above at the next edit.

## Per-file verdicts

Legend: DELETE = remove the file; CUT = remove the listed ranges; KEEP = leave as is (fix listed stale lines).

| File | Verdict | Reason |
|---|---|---|
| `CLAUDE.md` | KEEP | Gotcha list by design (`:3`); all sampled claims verified (`:18` six contracts, `:19` roles/leases, `:20` UUIDv7). Add the governance pointer only. |
| `README.md` | CUT | Owner of run/test commands (`CLAUDE.md:37` points here). Fix `:19-21` (roles, not single process), `:39/:47/:68` (`APP_ROLES`), `:47` (feed needs trader role), `:102` (6), `:112` (link to `docs/README.md` breaks on delete). Keep `:45-70` as the single owner of remote-DB modes and delete the copy in `deployment.md:207-223`. |
| `docs/README.md` | DELETE | Decided. Move `:27` ("journals age; not authority") and `:30-34` ("Checking Facts": OpenAPI, `config.py`, `pyproject.toml`) into the governance rule — they are the owner-test in prose. |
| `docs/governance/README.md` | KEEP | Index for the new rule. |
| `docs/system-architecture.md` | CUT | Keep: Decisions `5-13`, control plane `56-77`, backtest `79-112` (paper accounting "why" `106-112` is the best doc text in the repo), routing `116-121`, Exness paragraphs `130-132`, brokers `187-211` (fix `:202`), persistence `213-232` (add `leases`), limitations `238-241`, MT5 `243-245` (negative knowledge, 3 lines). Cut: layers table `15-25` (copy of `codebase-summary`/README), request flow numbers `29` (copy of `main_extensions.py:284-293`), DI table `33-41` (copy of `app/di/__init__.py` docstring and of `code-standards.md:104-108`), startup/shutdown `43-54` (stale; rewrite as 5 lines pointing at `roles.py`), jobs table `136-154` (copy of `sync_jobs.py:735-781`, stale twice; keep only the three non-greppable facts: 100-min lookback heals, cascade runs after a failed fetch, one failing symbol never stops the others), data-lag table `160-166` (copy of `data_lag_service.py:39-52`; keep the sentence "lag is counted in trading minutes"), streaming constants `174-178` and `182-183` (copies), deployment shape `234-236` (copy of `deployment.md:58-68`). Expected size: 245 → ~140 lines. |
| `docs/codebase-summary.md` | CUT | 0 dead paths today, but 41 path copies with no owner but `ls`. Keep Stack `5-9` (dependency names are in `pyproject.toml`/`package.json`; keep the one-line pointer), Tests `90-95`. Cut package map `11-43` (= `tree -L 3`; fix `:25` if kept) and Key Services `75-88` (class name = file name by convention, `code-standards.md:44-67`). Reduce Find-It-Fast `45-73` to the rows whose location the name does not predict: symbol-removal cascade, provider routing, strategy registry, domain purity test, startup order (→ `roles.py`), code metric script. |
| `docs/code-standards.md` | CUT | Keep: principles `5-11` (but `:10-11` is the fourth copy of the layering rule — drop to a pointer to `CLAUDE.md:18`), helper rule `13-17`, size `19-22`, naming table + exemptions `44-83`, routes `84-92`, domain/repos `110-117`, composite symbol + adding-a-provider `134-156` (cross-layer, nine files: the strongest KEEP in the repo), strategy IDs `158-168` minus the `template_id` row `:166`, comment policy `233-251`, testing `270-276`, ratchet policy `300-302`. Cut: file-naming example block `28-42` (duplicates the table), route example `94-102`, DI `104-108` (copy), UUID example block `119-132` (`grep generate_id` shows it), async table `174-183` and checklist `226-231` (textbook asyncio, zero repo content), pattern 2-4, 6 `203-208`, `222-224` (textbook), the set_sync_container example `187-201` (already a comment at `main.py:57-62`), comment examples `254-268`, quality-gate command table `286-299` (copy of `README.md:96-104`, stale "8 kept"), config/secrets `304-308` (copy of `CLAUDE.md:12` and `deployment.md:117`). Expected: 308 → ~170 lines. |
| `docs/deployment.md` | CUT | Mostly outside-repo operations (VPS, Cloudflare, config repo, runbooks) — passes the trace test. Fix `:218-221`. Cut `207-223` (copy of `README.md:45-70`, both stale). Env table `93-116`: keep rows whose "Purpose" states a consequence not in `config.py` comments (ADMIN_TOKEN 503, REDIS_PASSWORD refusal, daily-loss-cap unset rejects); replace the rest with "full set: `config.py::Settings`". Add `remote-db-local-redis.env` to `80-92` or drop that table (it is `ls ../pocketquant-config/`). |
| `docs/project-overview-pdr.md` | CUT | Keep Vision/Goals `5-14` and the NF intent lines (not derivable). Cut every route bullet (`:24`, `:30`, `:39-40`, `:52`, `:58`, `:64`, `:69-70`): the doc itself names the owner at `:3` ("the live route list is the OpenAPI page"). Fix `:81` (second 12 — or drop the number), `:109-110` (leases). |
| `docs/engine-scale-out-limitation.md` | CUT (merge) | All four symbols verified; this is negative knowledge, which passes the trace test. But `16-25` (mermaid) restates the table and `27-37` is a speculative plan. Fold `3-12` into `system-architecture.md` "Limitations" as five lines; delete the file. |
| `docs/swing-pivot-key-level.md` | CUT | `:14` stale, `:23` dangling. `5-10` is a textbook primer; `25-60` copies the formula from `engulfing_strategy_service.py:8-11` plus ASCII worked examples. Keep three facts no grep yields: the proxy decision (`12-23`, fixed), chart markers ≠ strategy entries (`62-69`), FE `STRONG_THRESHOLD` vs BE `max_rejection_wick_pct` are two unlinked 0.30 constants (`71-73`) — that one deserves a parity test more than a doc line. 73 → ~20 lines. |
| `docs/backtest-rubric/methodology.md` | CUT | Bands `33-51` and weights `55-70` are a verbatim copy of `scripts/rubric/scoring.py:31-77` (verified identical). Formulas `85-101` are likely a copy of `empirical_metrics.py` (not line-verified; label). Keep the decisions: min-aggregation `15-26`, crypto caveat `11-13`, returns basis `74-83`, raw-kurtosis note `103-106`, bootstrap scope `108-115`, versioning `130-134`. Drop `:104` "n=6 runs". Check `scripts/rubric/README.md` for a third copy (out of scope here). |
| `docs/todo/deflated-sharpe-pbo-cscv-roadmap.md` | CUT | A roadmap record, not AS-IS; acceptable under `todo/`. But `26-78` derive PSR/DSR/PBO from the cited papers — model knowledge; the Sources list `96-100` suffices. Keep `1-24` (why deferred, prerequisite), `80-94` (direction, build order). |
| `docs/visuals/collection-erd.mmd` | DELETE | Stale primary keys (#18, #19) that contradict `CLAUDE.md:20`; four collections missing; a wrong relation (#20). Owner is the repositories' `ensure_indexes` and `constants.py`. |
| `docs/visuals/collection-erd.png` | DELETE | Render of the above. |
| `docs/journals/` (29 files) | DELETE | `CLAUDE.md:23` says docs hold no history; `docs/README.md:27` already denies them authority; `CLAUDE.md` never points agents at them, so they have zero agent read value; 31 % of their path references are dead; they are 59 % of doc lines. `git log` keeps them. Before deleting, skim the five 2026-10-19/20 Exness journals for a decision that has no owner yet (candidate: `2026-10-20-exness-go-live-plan-debate.md`); if found, move it as a WHY comment or a `system-architecture.md` Decisions bullet. |

## Script used for the path sweep

```python
import re, os, glob
files = sorted(glob.glob("docs/**/*.md", recursive=True)) + ["README.md", "CLAUDE.md"]
pat = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w-]+\.(?:py|ts|tsx|sh|yml|yaml|toml|json|md|mmd|bru|http))(?![\w/])")
base = {}
def walk(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".") and d not in ("node_modules", "__pycache__", "dist")]
        for f in fn: base.setdefault(f, []).append(os.path.join(dp, f).replace("\\", "/"))
walk("."); walk("../pocketquant-config")
def resolve(p):
    if p.startswith(("_", ".")): return True          # suffix patterns such as _adapter.py
    b = os.path.basename(p)
    if b not in base: return False
    return "/" not in p or any(x.endswith(p) for x in base[b])
for f in files:
    refs = sorted({m.group(1) for m in pat.finditer(open(f, encoding="utf-8", errors="ignore").read())})
    refs = [r for r in refs if not r.startswith(("http", "cfg.")) and "{" not in r and "<" not in r]
    print(f, len(refs), [r for r in refs if not resolve(r)])
```

Known gap: it skips dot-directories, so `.github/workflows/cicd.yml` reads as missing. Add `.github` to the walk if adopted.

## Strongest counter-argument against this position

The human owner does not grep; a pointer-only doc moves the reading cost onto them at every review, and the duplicated numbers exist precisely so a person can check AI-written code against one page. The 27 stale claims also show the opposite lesson: `CLAUDE.md:3` already says "code wins, fix the doc", drift was caught here in one afternoon, and the cost of a wrong ":02" is far lower than the cost of a reviewer who cannot see the job schedule without opening five files. Agents also err most on multi-file facts (startup order, role gating), which is exactly where this audit found the deepest drift — the answer could be "keep those sections and make them tested", not "cut them".

## Assumptions

- The three local env files in `../pocketquant-config/local/` are the ones `README.md` refers to; I read only the `APP_ROLES`/`ENABLE_JOBS` key names, no values (high confidence).
- `docs/backtest-rubric/methodology.md:85-101` formulas mirror `scripts/rubric/empirical_metrics.py`; I verified bands and weights line by line but not every formula (medium confidence; a one-file read settles it).
- Journals carry no decision that lacks another owner; I verified this by sampling path references, not by reading all 2,297 lines (medium confidence; the pre-delete skim in the verdict row covers the risk).
- The human owner reviews docs with the same tools as agents (Grep/Read in an editor). If the owner reads docs on a phone or printout, the codebase-summary and jobs-table cuts should be softer (low confidence; would flip those two verdicts to KEEP-with-fixes).

Status: DONE
Summary: Methodology (owner / trace / drift tests + re-growth guard), 27 verified stale claims with doc:line → code:line, a 31 % dead-path rate in journals, and a verdict for every in-scope file are in the report above.
