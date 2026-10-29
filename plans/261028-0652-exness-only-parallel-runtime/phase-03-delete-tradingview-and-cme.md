---
phase: 3
title: "Delete TradingView and the CME calendar (prod data first, then code)"
status: pending
priority: P1
effort: "1d + deploy D-2"
dependencies: [2]
---

# Phase 03 — Delete TradingView and the CME calendar

## Goal

Remove TradingView and the CME calendar completely (D1, D4). Prod data goes first, through the running app, because the old code still routes the symbols: stop subscription `01a178ef-5027-73ba-a98e-b7d6de8e2cc9`, then cascade-delete `ES1!:TRADINGVIEW`, `NQ1!:TRADINGVIEW` and `YM1!:TRADINGVIEW` through the API, recording counts before and after. There is no Mongo backup before this delete (D32, explicit owner decision for this one delete). Then delete the code, dependencies, import contracts, tests, web strings and doc lines, and deploy D-2. From this phase on `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`

## Context

- Stop route: `POST /api/v1/subscriptions/{sub_id}/stop` (`src/pocketquant/app/routes/strategy.py:96-102`, router prefix `:74-76`, API prefix `/api/v1` at `src/pocketquant/core/config.py:51`).
- Cascade route: `DELETE /api/v1/market-data/tracked-symbols/{symbol}` (`src/pocketquant/app/routes/market_data.py:296-310`, mounted under `/market-data` at `src/pocketquant/app/main_extensions.py:401`). `TrackedSymbolService.remove` (`src/pocketquant/engine/market_data/tracked_symbols_service.py:128-157`) deletes `tracked_symbols`, stops and removes each subscription, deletes every symbol-keyed collection (symbols, bars, sync_status, backtests, live rows), `job_history` details and cache keys, and returns `{"symbol", "status": "removed", "deleted": {...}}`.
- Field names: `symbol` in `tracked_symbols` (`tracked_symbol_repository.py:27`), `symbols` (`symbol_repository.py:30`), `bars` (`bar_repository.py:90`), `subscriptions` (`subscription_repository.py:55`); subscription `_id` is the string id and `actual_state` is set at `subscription_repository.py:74`; `asset_class`/`calendar_id` on `symbols` (`src/pocketquant/core/domain/symbol/entities.py:100-101`). Task 3.1 still reads one document first.
- No secret goes on a command line (plan.md Conventions). Admin calls run inside `pocketquant-app`, where `ADMIN_TOKEN` comes from the prod `.env` through `env_file` (`deploy/compose.prod.yml:69-70`); the shell builtin `printf` writes the header to stdin and `curl -H @-` reads it, so the token never appears in a process argument list. The route checks the `X-Admin-Token` header (`src/pocketquant/app/middleware/admin_auth_middleware.py:26-51`). Mongo reads are a Python snippet piped to `python -` inside `pocketquant-app`: it connects with `pymongo.MongoClient(str(s.mongodb_url))[s.mongodb_database]` from `get_settings()` (`src/pocketquant/core/config.py:53-54,145-146`), so no password is typed or passed. The image puts the app venv first on `PATH` (`deploy/Dockerfile:47`) and installs `curl` (`:35`). <!-- Red team 2026-10-28: #13 -->
- TradingView code: `src/pocketquant/core/infra/tradingview/` (`__init__.py` plus 5 modules); DI `src/pocketquant/app/di/adapters.py:5,43-45,76-80,94,100-104,114,120-124`; health `main_extensions.py:66,275-278,286-299`; settings `core/config.py:2,10-14,66-107`; `core/domain/shared/enums.py:1,58,62-106` (`INDEX_FUTURE`, `TradingViewPlan`, `TradingViewCapabilities`, `capabilities_for`); routing `core/domain/market_data/provider_routing_domain_service.py:3-4,23,46`; quote TTL `engine/market_data/app_services/quote_app_service.py:32-34,71`. Prod `.env` has no `TRADINGVIEW_*` key and `Settings` uses `extra="ignore"` (`core/config.py:44`).
- CME calendar: `core/infra/calendars/cme_globex_calendar_adapter.py`; factory `trading_calendar_factory.py:15,29`; package docstring `calendars/__init__.py:1-6`; `CALENDAR_CME_GLOBEX_EQUITY` at `core/domain/symbol/value_objects.py:21` and `:82`, re-exported at `core/domain/symbol/__init__.py:3,11`. `AssetClass.INDEX_FUTURE` is used only by TradingView paths and `scripts/seed_index_futures.py:71`.
- `pyproject.toml:13` (`pandas-market-calendars`), `:27-30` (`tvdatafeed` git pin, the only `@ git+` dependency), `:54-56` (`allow-direct-references`, exists only for it), `:141-176` (the two contracts for the deleted libraries).
- 32 test files match TradingView/CME today (`git grep -l -i -E "tradingview|cme_globex|pandas_market_calendars|seed_index_futures|tvdatafeed" -- tests | wc -l`, re-checked 2026-10-28). `tests/app_test/unit/test_data_provider_registration.py` enforces that `DATA_PROVIDER_DEFAULTS` and both routers list the same providers; it must stay green unchanged. <!-- Red team 2026-10-28: #10 -->
- Web strings: 9 files under `web/src` name `ES1!:TRADINGVIEW` only in examples or one fixture (`web/src/lib/datetime.test.ts:21`). Web scripts: `lint`, `test`, `build` (`web/package.json:6-12`).
- `CLAUDE.md:14` says "8 contracts". D28: `docs/journals/**` and `plans/**` are dated records, never edited.
- Searches use `git grep` (plan.md Conventions; `rg` is not installed in the local Git Bash). `git grep` exits 1 when nothing matches, so `...; echo "rc=$?"` printing only `rc=1` means no hit. <!-- Red team 2026-10-28: #10 -->
- Machine measurements use the same inline commands as Phase 02 (no script file, no VPS copy; Phase 08 installs `/opt/pocketquant/bin/` later). Every command runs from `D:/w/_me/algotrading/pocketquant` with the key at `.cache/ssh/vps_key`. <!-- Red team 2026-10-28: #2, #11 -->
  - **Snapshot command.** Replace `<label>` and `<file>`. Line 1 has the `snapshot.sh` fields `label= ts= mem_used_mb= mem_available_mb= swap_used_mb= load1= psi_some_avg10= oom= boot_id=`; the next lines are one `docker stats` row per container.

    ```bash
    HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'echo "label=<label> ts=$(date -u +%FT%TZ) $(free -m | awk "/^Mem:/{printf \"mem_used_mb=%s mem_available_mb=%s \", \$3, \$7} /^Swap:/{printf \"swap_used_mb=%s\", \$3}") load1=$(cut -d" " -f1 /proc/loadavg) psi_some_avg10=$(awk "/^some/{sub(\"avg10=\",\"\",\$2); print \$2}" /proc/pressure/memory 2>/dev/null || echo absent) oom=$(awk "/^oom_kill /{print \$2}" /proc/vmstat) boot_id=$(cat /proc/sys/kernel/random/boot_id)"; docker stats --no-stream --format "{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}"' > <file>
    ```
  - **OOM check command** (the plan.md OOM rule against the Phase 02 `oom_baseline=` line). It prints `OOM_OK`, or `OOM_STOP <reason>` when the boot id differs, the `oom_kill` counter is higher, or `pocketquant-app` has `State.OOMKilled=true`:

    ```bash
    B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); N=$(ssh -i .cache/ssh/vps_key "$HOST" 'echo "$(cat /proc/sys/kernel/random/boot_id) $(awk "/^oom_kill /{print \$2}" /proc/vmstat) $(docker inspect -f "{{.State.OOMKilled}}" pocketquant-app)"'); set -- $B $N; if [ "$#" -ne 5 ]; then V="OOM_STOP unreadable"; elif [ "$3" != "$1" ]; then V="OOM_STOP boot_id_changed"; elif [ "$4" -gt "$2" ]; then V="OOM_STOP oom_kill=$4 baseline=$2"; elif [ "$5" != false ]; then V="OOM_STOP oomkilled=$5"; else V=OOM_OK; fi; echo "$V"
    ```
  - **Deploy window command** (plan.md Conventions: Mon-Fri 06:00-11:20 or 12:50-19:30 UTC). It prints `WINDOW_OK` or `NOT_IN_WINDOW d=<weekday> t=<minute>`:

    ```bash
    d=$(date -u +%u); t=$((10#$(date -u +%H)*60 + 10#$(date -u +%M))); if [ "$d" -le 5 ] && { { [ $t -ge 360 ] && [ $t -lt 680 ]; } || { [ $t -ge 770 ] && [ $t -lt 1170 ]; }; }; then echo WINDOW_OK; else echo "NOT_IN_WINDOW d=$d t=$t"; fi
    ```

## Entry gate

1. `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
2. `uv run lint-imports | tail -1` prints `Contracts: 8 kept, 0 broken.` On a resume after this phase's own code commit, it prints `Contracts: 6 kept, 0 broken.` instead; that also passes (plan.md Conventions, Resume). <!-- Red team 2026-10-28: resume -->
3. Phase 02 is deployed: `mkdir -p .cache/ssh && tr -d '\r' < ../pocketquant-config/vps/default/id_rsa > .cache/ssh/vps_key && chmod 600 .cache/ssh/vps_key && HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r') && ssh -i .cache/ssh/vps_key "$HOST" 'docker exec pocketquant-app curl -s http://localhost:41921/health' | grep -c '"event_loop_lag_max_s"'` prints `1`.
4. The Phase 02 OOM baseline exists exactly once: `grep -cE '^oom_baseline=[0-9a-f-]{36} [0-9]+$' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md` prints `1`. <!-- Red team 2026-10-28: #2 -->

On any miss: run `rm -f .cache/ssh/vps_key`, edit nothing, spawn no `kongming`, leave the phase pending, and end with exactly:

```text
Status: BLOCKED
NOT_YET: <which gate line missed and what it printed>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261028-0652-exness-only-parallel-runtime --from 03 after <UTC time>
```

## Files to create/modify

- Delete: `src/pocketquant/core/infra/tradingview/` (whole dir), `src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py`, `scripts/seed_index_futures.py`, `tests/core_test/infra/tradingview/` (4 files), `tests/app_test/unit/test_tradingview_credentialed.py`, `tests/core_test/infra/calendars/test_cme_globex_calendar.py`.
- Modify (src): `app/di/adapters.py`, `app/main_extensions.py`, `core/config.py`, `core/domain/shared/enums.py`, `core/domain/market_data/provider_routing_domain_service.py`, `core/domain/market_data/data_provider_port.py`, `core/domain/market_data/realtime_quote_provider_port.py`, `core/domain/market_data/trading_calendar_port.py`, `core/domain/symbol/value_objects.py`, `core/domain/symbol/__init__.py`, `core/domain/trading/performance_calculator_domain_service.py`, `core/infra/calendars/__init__.py`, `core/infra/calendars/trading_calendar_factory.py`, `core/infra/market_data/provider_health_check.py`, `engine/market_data/app_services/quote_app_service.py`, `engine/market_data/app_services/bar_app_service.py`, `engine/market_data/app_services/integrity_jobs.py`, `engine/market_data/data_lag_service.py`, `engine/market_data/tracked_symbols_backfill.py`, `engine/backtest/backtest_report_app_service.py` (all under `src/pocketquant/`).
- Modify (other): `scripts/README.md`, `scripts/backfill/binance_bars.py`, `pyproject.toml`, `uv.lock`, the 26 remaining test files listed in Task 3.6, 9 `web/src` files listed in Task 3.7, `docs/system-architecture.md`, `docs/deployment.md`, `docs/codebase-summary.md`, `docs/project-overview-pdr.md`, `docs/code-standards.md`, `README.md`, `CLAUDE.md`.
- Create: `plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md`; scratch `.cache/tv-counts.py`, `.cache/tv-delete.json`, `.cache/snap-d2-*.txt`. No snapshot script file. <!-- Red team 2026-10-28: #11, #13 -->
- Outside the repo, after D-2: delete `C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/pocketquant-es-paper-subscription-kept.md` and its line in that folder's `MEMORY.md`.

## Tasks

### Task 3.1 — Read field names and record counts before the delete

**Goal:** confirm the field names and record what will be deleted.

**Target files and symbols:** `.cache/tv-counts.py`; `plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md`.

**Steps:**
1. Read one document of each collection. Each printed document must carry a `symbol` key (and `asset_class`, `calendar_id` for `symbols`); if any key is missing, that is a failed Verify of this task. The snippet reads the connection from `get_settings()` inside the app container, so no password is on a command line: <!-- Red team 2026-10-28: #13 -->

```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' <<'EOF'
from pymongo import MongoClient
from pocketquant.core.config import get_settings
s = get_settings()
db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
print([
    db.tracked_symbols.find_one({}, {"_id": 0, "symbol": 1}),
    db.subscriptions.find_one({}, {"symbol": 1, "actual_state": 1}),
    db.symbols.find_one({}, {"_id": 0, "symbol": 1, "asset_class": 1, "calendar_id": 1}),
])
EOF
```
2. Write the count snippet (git-ignored scratch; it runs inside the app container through `python -`): <!-- Red team 2026-10-28: #13 -->

```bash
cat > .cache/tv-counts.py <<'EOF'
from pymongo import MongoClient
from pocketquant.core.config import get_settings
s = get_settings()
db = MongoClient(str(s.mongodb_url))[s.mongodb_database]
tv = {"symbol": {"$regex": "TRADINGVIEW$"}}
print(" ".join(str(n) for n in [
    db.tracked_symbols.count_documents(tv),
    db.symbols.count_documents(tv),
    db.bars.count_documents(tv),
    db.subscriptions.count_documents(tv),
    db.subscriptions.count_documents({"_id": "01a178ef-5027-73ba-a98e-b7d6de8e2cc9"}),
    db.symbols.count_documents({"asset_class": "index_future"}),
    db.symbols.count_documents({"calendar_id": "CME_GLOBEX_EQUITY"}),
]))
EOF
```
3. Record: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); C=$(ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' < .cache/tv-counts.py); { printf '# TradingView removal counts\n\nNo backup was taken before this delete (D32).\nColumns: tracked_symbols symbols bars subscriptions_tv subscription_01a178ef symbols_index_future symbols_cme_calendar\n\n'; echo "before: $C"; } > plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md`. <!-- Red team 2026-10-28: #13 -->

**Success criteria:** step 1 showed the expected keys; the report has one `before:` line with seven integers.

**Verify:** `grep -cE "^before: [0-9]+( [0-9]+){6}$" plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md` prints `1`.

### Task 3.2 — Stop subscription `01a178ef` (prod)

**Goal:** the ES paper run stops before its symbol goes.

**Target files and symbols:** prod route `POST /api/v1/subscriptions/01a178ef-5027-73ba-a98e-b7d6de8e2cc9/stop`.

**Steps:**
1. Stop it; the answer contains `"status":"stopped"`. The token goes to `curl` on stdin (`-H @-`), never as an argument: <!-- Red team 2026-10-28: #13 -->

```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s' <<'EOF'
printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X POST -H @- http://localhost:41921/api/v1/subscriptions/01a178ef-5027-73ba-a98e-b7d6de8e2cc9/stop; echo
EOF
```
2. `sleep 15`.

**Success criteria:** the stored `actual_state` is `stopped`.

**Verify:** `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); echo 'from pymongo import MongoClient; from pocketquant.core.config import get_settings; s = get_settings(); print(MongoClient(str(s.mongodb_url))[s.mongodb_database].subscriptions.find_one({"_id": "01a178ef-5027-73ba-a98e-b7d6de8e2cc9"})["actual_state"])' | ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -'` prints `stopped`. <!-- Red team 2026-10-28: #13 -->

### Task 3.3 — Cascade-delete the three symbols through the API (prod)

**Goal:** all TradingView data is gone from Mongo and Redis (D4, no backup per D32).

**Target files and symbols:** prod route `DELETE /api/v1/market-data/tracked-symbols/{symbol}`; `.cache/tv-delete.json`; the counts report.

**Steps:**
1. Delete the three symbols, one answer per line (token on stdin through `-H @-`): <!-- Red team 2026-10-28: #13 -->

```bash
HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app sh -s' > .cache/tv-delete.json <<'EOF'
for s in ES1%21%3ATRADINGVIEW NQ1%21%3ATRADINGVIEW YM1%21%3ATRADINGVIEW; do
  printf 'X-Admin-Token: %s\n' "$ADMIN_TOKEN" | curl -s -X DELETE -H @- "http://localhost:41921/api/v1/market-data/tracked-symbols/$s"; echo
done
EOF
```
2. `grep -c '"status":"removed"' .cache/tv-delete.json` prints `3`.
3. Record: `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); C=$(ssh -i .cache/ssh/vps_key "$HOST" 'docker exec -i pocketquant-app python -' < .cache/tv-counts.py); { printf '\nDelete responses:\n\n```json\n'; cat .cache/tv-delete.json; printf '```\n\n'; echo "after: $C"; } >> plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md`. <!-- Red team 2026-10-28: #13 -->

**Success criteria:** three `removed` answers; every count is 0. A non-zero `symbols_index_future` or `symbols_cme_calendar` means a non-TradingView symbol still uses what Task 3.5 deletes: that is a failed Verify, not something to delete by hand.

**Verify:** `grep -c "^after: 0 0 0 0 0 0 0$" plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md` prints `1`.

### Task 3.4 — Delete the TradingView code

**Goal:** no TradingView module, setting, provider entry, health entry or script remains; Binance and Exness behaviour is unchanged.

**Target files and symbols:** see Context; paths below are under `src/pocketquant/` unless they start with `scripts/`.

**Steps:**
1. `git rm -r src/pocketquant/core/infra/tradingview scripts/seed_index_futures.py`.
2. `app/di/adapters.py`: in the module docstring (`:5`) drop the `ES1!:TRADINGVIEW -> "tradingview"` example; delete the three imports (`:43-45`), `get_tradingview_client` (`:76-80`), the `tradingview_client` parameters (`:94`, `:114`) and both `"tradingview"` router entries (`:100-104`, `:120-124`). Then delete every parameter of `get_data_provider` and `get_realtime_quote_provider` that is no longer used (`calendar_factory` in both; `settings` in the quote provider). Keep `settings` where `BinanceAdapter(settings=settings)` uses it.
3. `app/main_extensions.py`: delete the `TvDatafeedClient` import (`:66`) and `_tradingview_credentialed` (`:275-278`). In `register_health_checks` delete `settings` and `tradingview_client`, set `credentialed = {"exness"} if exness_client.is_configured else set()` in place of the three `credentialed` lines, and delete the `"tradingview"` map entry.
4. `core/config.py`: delete the enums import (`:10-14`), the TradingView block (`:66-107`, comments, fields and both properties) and `from dataclasses import replace` (`:2`) if nothing else uses it.
5. `core/domain/shared/enums.py`: delete `TradingViewPlan`, `TradingViewCapabilities`, `_CAPABILITIES_FOR` and `capabilities_for` (`:62-106`) and `from dataclasses import dataclass` (`:1`). `INDEX_FUTURE` goes in Task 3.5.
6. `core/domain/market_data/provider_routing_domain_service.py`: change the docstring example (`:3-4`) to `` ``XAUUSD:EXNESS`` by ``exness`` ``; delete the `CALENDAR_CME_GLOBEX_EQUITY` import (`:23`) and the `"tradingview"` entry (`:46`).
7. `engine/market_data/app_services/quote_app_service.py`: delete the comment and the `self._quote_ttl` line (`:32-34`) and pass `ttl=TTL_QUOTE_LATEST` at `:71`.
8. Docstrings: `core/domain/market_data/data_provider_port.py:4` and `realtime_quote_provider_port.py:4` list `(Binance, Exness)`; in `core/infra/market_data/provider_health_check.py:13-19` replace the paragraph with "``degraded`` means a provider was given credentials and holds no session. It never reads ``unhealthy``, so the container health check never restarts the app for it."; `engine/market_data/data_lag_service.py:3-10`: replace the TradingView/CME sentences with "A delayed feed is not a broken one: it keeps arriving, just behind the clock." and "Only trading minutes count, so a weekend, a holiday or a daily session break is the market being shut, not the feed falling behind."
9. `scripts/README.md`: delete the `seed_index_futures.py` bullet (`:12-16`). `scripts/backfill/binance_bars.py:4`: drop the TradingView comparison from the comment.
10. Added 2026-10-29 (pre-run review): `core/common/constants.py:38` `LIMIT_TVDATAFEED_MAX_BARS = 5000` becomes `LIMIT_SYNC_MAX_BARS = 5000` and its five uses in `engine/market_data/sync_dtos.py` (`:9,22,24,51,53`) follow. After step 7, `QuoteAppService.__init__` has no use for `settings`: delete the parameter and `self.settings`, and drop `settings=` at `app/di/services.py:94-96` (and the provider parameter if it becomes unused). Anchors in `app/main_extensions.py` moved after the previous phase: import `:67`, `_tradingview_credentialed` `:304-307`, health block `:315-328`.

**Success criteria:** no TradingView text in `src` or `scripts`.

**Verify:** `git grep -l -i -E "tradingview|tvdatafeed|seed_index_futures" -- src scripts ':!docs/journals' ':!plans'; echo "rc=$?"` prints only `rc=1`. <!-- Red team 2026-10-28: #10 -->

### Task 3.5 — Delete the CME calendar, the index-future class and the two contracts

**Goal:** no CME calendar, no `pandas-market-calendars`, no `tvdatafeed`, 6 import contracts.

**Target files and symbols:** `core/infra/calendars/`, `core/domain/symbol/value_objects.py`, `core/domain/symbol/__init__.py`, `pyproject.toml`, `uv.lock`, `CLAUDE.md:14`.

**Steps:**
1. `git rm src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py`.
2. `trading_calendar_factory.py`: delete the import (`:15`) and `CmeGlobexCalendarAdapter()` from the tuple (`:29`). `calendars/__init__.py`: docstring becomes `"""Exchange-calendar adapters behind ``ITradingCalendarPort``."""`.
3. `core/domain/shared/enums.py`: delete `INDEX_FUTURE = "index_future"` (`:58`). `core/domain/symbol/value_objects.py`: delete `CALENDAR_CME_GLOBEX_EQUITY` (`:21`) and the `INDEX_FUTURE` map entry (`:82`); reword the comment (`:16-19`) to "the schedule rules stay in code behind ITradingCalendarPort, because venue holidays and session changes are code, not data." `core/domain/symbol/__init__.py`: delete `CALENDAR_CME_GLOBEX_EQUITY` from the import (`:3`) and from `__all__` (`:11`).
4. Comments that use CME as the calendar example: reword each to the equivalent Exness example (`EXNESS_FX` weekday sessions, or `EXNESS_XAUUSD` with its daily break) and keep the sentence's point: `core/domain/market_data/trading_calendar_port.py:5,9`, `core/domain/trading/performance_calculator_domain_service.py:44`, `engine/market_data/app_services/bar_app_service.py:67`, `engine/market_data/app_services/integrity_jobs.py:102`, `engine/market_data/tracked_symbols_backfill.py:104`, `engine/backtest/backtest_report_app_service.py:363`. Leave `core/domain/trading/commission_model.py:17` (a fee convention, not a calendar).
5. `pyproject.toml`: delete `"pandas-market-calendars>=5.4.0",` (`:13`), `"pandas>=2.1.0",` (`:12`; added 2026-10-29: only the two deleted modules import it), the `tvdatafeed` comment and pin (`:27-30`), the `[tool.hatch.metadata]` table with `allow-direct-references` and its comment (`:53-56`), and both contracts (`:141-176`, `pandas_market_calendars confined ...` and `tvDatafeed confined ...`).
6. `uv lock && uv sync`.
7. `CLAUDE.md:14`: change `8 contracts` to `6 contracts`.

**Success criteria:** lock and sync succeed; 6 contracts kept.

**Verify:** `uv lock --check >/dev/null 2>&1 && echo "$(git grep -n -E 'CME' -- src scripts ':!docs/journals' ':!plans' | grep -vc 'commission_model.py') $(uv run lint-imports | tail -1)"` prints `0 Contracts: 6 kept, 0 broken.` <!-- Red team 2026-10-28: #10 -->

### Task 3.6 — Move the CME and TradingView fixtures in tests

**Goal:** the suite covers the same behaviour on Exness or Binance symbols; no assertion is weakened.

**Target files and symbols:** delete `tests/core_test/infra/tradingview/`, `tests/app_test/unit/test_tradingview_credentialed.py`, `tests/core_test/infra/calendars/test_cme_globex_calendar.py`. Rewrite: `tests/app_test/integration/test_futures_sync_end_to_end.py`, `tests/app_test/integration/test_market_data_routing_characterization.py`, `tests/app_test/market_data/test_bar_app_service_unit.py`, `tests/app_test/market_data/test_cascade_aggregator.py`, `tests/app_test/market_data/test_integrity_calendar.py`, `tests/app_test/unit/handlers/status/test_sync_status_calendar.py`, `tests/app_test/unit/handlers/sync/test_bar_filters.py`, `tests/app_test/unit/market_data/test_closed_market_skip_precedes_provider_loops.py`, `tests/app_test/unit/market_data/test_quote_app_service.py`, `tests/app_test/unit/market_data/test_sync_jobs_calendar_gate.py`, `tests/backtest_test/domain/test_performance_calculator_calendar_annualization.py`, `tests/backtest_test/engine/test_report_annualization_source.py`, `tests/backtest_test/test_backtest_dispatch_contract_spec.py`, `tests/core_test/infra/brokers/test_paper_broker_contract_spec.py`, `tests/core_test/infra/calendars/test_trading_calendar_factory_unseeded_default.py`, `tests/core_test/infra/market_data/test_provider_health_check.py`, `tests/core_test/infra/market_data/test_routing_data_provider_adapter.py`, `tests/core_test/infra/market_data/test_routing_realtime_quote_adapter.py`, `tests/core_test/infra/persistence/test_symbol_repository_touch.py`, `tests/core_test/unit/domain/bar/services/test_bar_builder.py`, `tests/core_test/unit/domain/market_data/test_provider_routing.py`, `tests/engine_test/market_data/test_backfill_calendar_stamp.py`, `tests/engine_test/market_data/test_backfill_daily_mode.py`, `tests/engine_test/market_data/test_data_lag_service.py`, `tests/engine_test/market_data/test_ws_subscription_reconcile_logging.py`, `tests/engine_test/test_contract_spec_wiring.py`.

**Steps:**
1. `git rm -r tests/core_test/infra/tradingview tests/app_test/unit/test_tradingview_credentialed.py tests/core_test/infra/calendars/test_cme_globex_calendar.py`.
2. For each rewrite file: where the CME calendar or a `:TRADINGVIEW` symbol is only an example of a session calendar or a second provider, switch to `CALENDAR_EXNESS_FX` / `CALENDAR_EXNESS_XAUUSD` (`core/domain/symbol/value_objects.py:24-25`) or `XAUUSD:EXNESS`, and recompute the expected instants from the Exness sessions (XAUUSD: Sun 22:01:30 to Fri 20:57:59 UTC, daily break Mon-Thu 20:58:00-22:00:29; EURUSD: Sun 21:05:00 to Fri 20:58:59, no break, `docs/journals/2026-10-13-exness-api-spike.md:44-45`). Where an index-future `ContractSpec` is the example, use the XAUUSD spec (contract size 100, volume step 0.01).
3. Delete a test case only when the behaviour it covers is deleted (CME holidays, CME early closes, TradingView plan capabilities, the TradingView quote TTL). In `test_quote_app_service.py`, the TTL case asserts `ttl == TTL_QUOTE_LATEST`.
4. Never loosen an assertion, widen a tolerance or add a skip to make a test pass.

**Success criteria:** no test names a removed symbol, calendar or class; the suite is green apart from the expected timezone red.

**Verify:** `git grep -l -i -E "tradingview|cme_globex|pandas_market_calendars|seed_index_futures|tvdatafeed|INDEX_FUTURE|index_future|CALENDAR_CME" -- tests ':!docs/journals' ':!plans'; echo "rc=$?"` prints only `rc=1`. <!-- Red team 2026-10-28: #10 -->

### Task 3.7 — Web strings and fixture

**Goal:** no TradingView example in the SPA.

**Target files and symbols:** `web/src/lib/symbol-format.ts:2`, `web/src/components/chart/trading-chart.tsx:38`, `web/src/components/backtest/backtest-form.tsx:72`, `web/src/components/ticker-widget/ticker-widget.tsx:7`, `web/src/components/data-lag-badge.tsx:6`, `web/src/components/controls/symbol-selector.tsx:6`, `web/src/types/quote.ts:3`, `web/src/types/market-data.ts:20`, `web/src/lib/datetime.test.ts:21`.

**Steps:**
1. Replace `ES1!:TRADINGVIEW` with `XAUUSD:EXNESS` in each of the nine lines (including the user-facing message in `backtest-form.tsx:72` and the `statusVariant` fixture symbol in `datetime.test.ts:21`). Change nothing else.
2. Run `cd web && npm run lint && npm test && npm run build`.

**Success criteria:** web lint, tests and build pass.

**Verify:** `(cd web && npm run lint >/dev/null 2>&1 && npm test >/dev/null 2>&1 && npm run build >/dev/null 2>&1) && echo web_ok; git grep -c -i -E "tradingview" -- web/src ':!docs/journals' ':!plans'; echo "rc=$?"` prints exactly `web_ok` and then `rc=1`. <!-- Red team 2026-10-28: #10 -->

### Task 3.8 — Docs, README and the TradingView gate

**Goal:** docs describe only Binance and Exness (AS-IS, one idea per sentence); the D28 gate prints nothing.

**Target files and symbols:** `README.md:3,11,40-48`; `docs/system-architecture.md:40,118,128,159`; `docs/deployment.md:104-106`; `docs/codebase-summary.md:21,24`; `docs/project-overview-pdr.md:7,20`; `docs/code-standards.md:136,139,152,248,299`.

**Steps:**
1. `README.md`: drop "TradingView (index futures)" from `:3` and `tradingview` from the tree line `:11`; in `:40-41` keep only the `BTCUSDT:BINANCE` → `binance` example and add `XAUUSD:EXNESS` → `exness`; delete the TradingView bullet `:42-48`.
2. `docs/system-architecture.md`: `:40` becomes "Exness client, the routed data and quote ports, `BrokerFactory`."; `:118` example uses `XAUUSD:EXNESS` → `exness` only after Binance; delete the TradingView provider row `:128`; `:159` becomes "A delayed feed is flagged, not treated as broken."
3. `docs/deployment.md`: delete the three `TRADINGVIEW_*` rows `:104-106`.
4. `docs/codebase-summary.md`: delete the `tradingview/` tree line `:21`; `:24` becomes `# trading calendars (Exness sessions)`.
5. `docs/project-overview-pdr.md`: `:7` reads "crypto and CFDs"; `:20` lists "Binance (crypto spot), Exness (CFDs)".
6. `docs/code-standards.md`: drop `ES1!:TRADINGVIEW` from `:136` and `TRADINGVIEW` from `:139`; at `:142` drop the `TRADINGVIEW_EXCHANGE_BY_CODE` clause (added 2026-10-29); `:152` points at `scripts/seed_exness_symbols.py`; drop `TradingView` from the list at `:248`; at `:299` drop the two clauses about `pandas_market_calendars` and `tvDatafeed`.
7. Run the D28 gate.

**Success criteria:** the gate prints nothing.

**Verify:** `git grep -n -i -E "tradingview|cme_globex|pandas_market_calendars|seed_index_futures" -- src tests web/src docs pyproject.toml ':!docs/journals' ':!plans'; echo "rc=$?"` prints only `rc=1`. <!-- Red team 2026-10-28: #10 -->

### Task 3.9 — Local gates and commit

**Goal:** one green commit on `develop`.

**Target files and symbols:** every file above.

**Steps:**
1. `docker ps`; if it fails, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background, wait 10 s and retry.
2. `uv run ruff check src tests` prints `All checks passed!`; `uv run ruff format --check` on the touched files reports nothing to reformat; `uv run pyright` reports no more than the 34 errors and `ruff format --check src tests` no more than the 12 files that were already red at HEAD before this phase (amended 2026-10-29: those are pre-existing in untouched files; CI runs neither tool).
3. `uv run python scripts/code_metrics.py --ratchet; echo "rc=$?"` prints `rc=0`. If a ceiling trips only because of this change, raise it in `pyproject.toml` `[tool.code-metrics]` in its own commit `chore(metrics): raise the code-metrics ceiling` and say so in the phase summary.
4. `just test` (fallback `uv run python -m pytest tests/ -q`): the only red is `4 failed, 4 errors` in `tests/core_test/unit/common/test_utc_runtime_guard.py` and `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`.
5. `git add -A src tests scripts web/src docs README.md CLAUDE.md pyproject.toml uv.lock && git commit -m "refactor: remove TradingView and the CME calendar"`.

**Success criteria:** no other red; 6 contracts; clean tree for the gate paths.

**Verify:** `test "$(uv run python -m pytest tests/ -q 2>&1 | grep -E '^(FAILED|ERROR)' | grep -vcE 'test_utc_runtime_guard|test_cron_trigger_timezone')" = 0 && test -z "$(git status --porcelain -- src web deploy tests scripts docs)" && uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`

### Task 3.10 — Push `develop` and wait for CI

**Goal:** CI is green on the pushed commit.

**Target files and symbols:** remote `develop`.

**Steps:**
1. `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin`; then `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
2. `sleep 15`, then (re-run on tool timeout) `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch develop --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --repo camping89/pocketquant --exit-status > /dev/null; echo "rc=$?"`.

**Success criteria:** the run concluded `success`.

**Verify:** `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch develop --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --repo camping89/pocketquant --json conclusion -q .conclusion` prints `success`.

### Task 3.11 — Deploy D-2 [ASK]

**Goal:** prod runs without TradingView; memory recorded before and after; the OOM rule holds. <!-- Red team 2026-10-28: #2 -->

**Target files and symbols:** remote `master`; VPS `pocketquant-app`; `.cache/snap-d2-before.txt`, `.cache/snap-d2-after.txt`; the Phase 02 `oom_baseline=` line in `plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md` (read only). <!-- Red team 2026-10-28: #2, #11 -->

**Steps:**
1. [ASK] the owner:
   > Recommended: có — deploy D-2 lên prod ngay. Lý do: dữ liệu TradingView đã xoá xong trên prod, code cũ vẫn chạy nhưng không còn symbol nào cần TradingView; bản mới gỡ hẳn TradingView, lịch CME và 2 import contract. Sự thật: CI `develop` xanh (run <RUN_ID>); số đếm sau khi xoá đều bằng 0; `EXNESS_LIVE_TRADING=false`; deploy khởi động lại `pocketquant-app` khoảng 1-2 phút. Cho phép push `develop:master` không?
   Only an explicit yes continues; a "no" or "wait" ends the phase with the `NOT_YET` block (run `rm -f .cache/ssh/vps_key` first). The prod data delete stays done either way.
2. Check the deploy window (plan.md Conventions) with the Context deploy window command. On `NOT_IN_WINDOW`, wait until the next window opens, re-checking every 10 min (use the runtime's background-command facility for a wait longer than the tool timeout), then continue. <!-- Red team 2026-10-28: #11 -->
3. Snapshot before: run the Context snapshot command with `<label>` = `d2-before` and `<file>` = `.cache/snap-d2-before.txt`. <!-- Red team 2026-10-28: #11 -->
4. Release: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/master)" && echo released` prints `released`.
5. `sleep 15`, then (re-run on tool timeout) `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch master --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run watch "$RUN_ID" --repo camping89/pocketquant --exit-status > /dev/null; echo "rc=$?"` prints `rc=0`.
6. Verdict: `RUN_ID=$(GH_TOKEN=$(gh auth token --user camping89) gh run list --repo camping89/pocketquant --branch master --commit "$(git rev-parse HEAD)" --limit 1 --json databaseId -q '.[0].databaseId'); GH_TOKEN=$(gh auth token --user camping89) gh run view "$RUN_ID" --repo camping89/pocketquant --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.
7. Snapshot after (at least 5 min after the run ended): run the Context snapshot command with `<label>` = `d2-after` and `<file>` = `.cache/snap-d2-after.txt`. <!-- Red team 2026-10-28: #11 -->

**Success criteria:** green deploy with a 0-failure verdict; both snapshots exist; the OOM check against the Phase 02 `oom_baseline=` prints `OOM_OK` (same boot id, `oom_kill` not higher, `pocketquant-app` not OOM-killed). An `OOM_STOP` is a failed Verify (D31). <!-- Red team 2026-10-28: #2 -->

**Verify:** `B=$(sed -n 's/^oom_baseline=//p' plans/261028-0652-exness-only-parallel-runtime/reports/machine-baseline.md); HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); N=$(ssh -i .cache/ssh/vps_key "$HOST" 'echo "$(cat /proc/sys/kernel/random/boot_id) $(awk "/^oom_kill /{print \$2}" /proc/vmstat) $(docker inspect -f "{{.State.OOMKilled}}" pocketquant-app)"'); set -- $B $N; if [ "$#" -ne 5 ]; then V="OOM_STOP unreadable"; elif [ "$3" != "$1" ]; then V="OOM_STOP boot_id_changed"; elif [ "$4" -gt "$2" ]; then V="OOM_STOP oom_kill=$4 baseline=$2"; elif [ "$5" != false ]; then V="OOM_STOP oomkilled=$5"; else V=OOM_OK; fi; echo "$V $(cat .cache/snap-d2-before.txt .cache/snap-d2-after.txt | grep -cE '^label=d2-(before|after) ts=.* oom=[0-9]+ boot_id=[0-9a-f-]+$')"` prints `OOM_OK 2`. <!-- Red team 2026-10-28: #2 -->

### Task 3.12 — Post-deploy checks, report, memory note

**Goal:** prod boots clean without TradingView; the record and the memory index are current.

**Target files and symbols:** VPS `pocketquant-app`; the counts report; `C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/`.

**Steps:**
1. `HOST=$(head -1 ../pocketquant-config/vps/default/host | tr -d '\r'); ssh -i .cache/ssh/vps_key "$HOST" 'docker logs --since 15m pocketquant-app 2>&1 | grep -cE "ModuleNotFoundError|ImportError"; docker exec pocketquant-app curl -s http://localhost:41921/health | grep -ci tradingview'` prints `0` then `0`.
2. Append the deploy measurements: `{ printf '\n## D-2 deploy\n\n### Before\n\n```text\n'; cat .cache/snap-d2-before.txt; printf '```\n\n### After\n\n```text\n'; cat .cache/snap-d2-after.txt; printf '```\n'; } >> plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md`.
3. Commit: `git add plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md && git commit -m "docs(plans): record the TradingView removal counts and deploy measurements"`.
4. Delete the memory note that said to delete itself after this phase: `rm -f C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/pocketquant-es-paper-subscription-kept.md && sed -i '/pocketquant-es-paper-subscription-kept\.md/d' C:/Users/evele/.claude/projects/D--w--me-algotrading/memory/MEMORY.md`.
5. `rm -f .cache/ssh/vps_key`.

**Success criteria:** step 1 printed `0` and `0`; report and commit exist; the memory note and its index line are gone; the key copy is gone.

**Verify:** `M=C:/Users/evele/.claude/projects/D--w--me-algotrading/memory; echo "$(grep -c 'es-paper-subscription-kept' $M/MEMORY.md) $(test -e $M/pocketquant-es-paper-subscription-kept.md && echo note_present || echo note_gone) $(grep -c '^## D-2 deploy' plans/261028-0652-exness-only-parallel-runtime/reports/tv-removal-counts.md) $(test -e .cache/ssh/vps_key && echo key_present || echo key_gone)"` prints `0 note_gone 1 key_gone`.

## Rollback

- Code: `git revert --no-edit <refactor sha>` (and the ratchet commit if any), run the Task 3.9 gates expecting `Contracts: 8 kept, 0 broken.`, push `develop`, [ASK], push `develop:master` inside the **Deploy window** of plan.md Conventions as in Task 3.11. The old code boots with no TradingView symbol tracked [inference: nothing in the old boot path requires one; check `docker logs` for errors after the rollback deploy].
- Data: not reversible. No backup exists by owner decision (D32); D4 accepted the loss.
- Memory note: restore only if the code revert is also meant to bring TradingView back, which needs a new owner decision.
- End with `rm -f .cache/ssh/vps_key`.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
