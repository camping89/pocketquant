---
phase: 5
title: "Safeguards object, stored entry pause, leverage-aware sizing (B4, B11)"
status: completed
priority: P1
effort: 0.75d
dependencies: [1, 2]
---

# Phase 05: Safeguards object, stored entry pause, leverage-aware sizing (B4, B11)

## Context
- Source: `D:/w/_me/algotrading/plans/reports/advise-261020-1630-exness-go-live-safeguards.md` §2 item 3 and "User answers 2026-10-20 18:42", changed by the user decision of 2026-10-20 20:20: **the pause is remembered across a restart**. Paused entries stay paused after a restart; an unpaused running strategy restarts and continues as usual. This is the only phase that edits `exness_broker_adapter.py` and its tests.
- Today: `Settings` holds `exness_live_trading`, `exness_daily_loss_cap`, `exness_max_lots` (`core/config.py:121,127-128`). The flag reaches `BrokerFactory` via its constructor (`app/di/adapters.py:45-58`; `core/infra/brokers/broker_factory.py:28,87-88`). The caps travel in `default_broker_config` (`app/di/services.py:166-167`) to the adapter constructor (`broker_factory.py:92-98`; `exness_broker_adapter.py:95-107`). No pause exists.
- Entry gate in the adapter: `submit_order` sends to `_submit_open` only when the subscription holds no position; a close goes straight to `closePosition` (`exness_broker_adapter.py:197-212`). `_submit_open` calls `_presubmit_reason` first (`:214-217`), whose first check is "loss cap unset" (`:243-245`). `OrderAppService` saves a REJECTED order and logs `order_rejected` (`engine/execution/order_app_service.py:103-112`).
- `normalize_quantity` runs before `submit_order` (`engine/strategy/strategy_app_service.py:405-415`) and logs `exness.order_rejected_presubmit reason=below_min_lot` (`exness_broker_adapter.py:175-177`). So a paused rejection proves the size reached the lot grid; Phase 11 relies on this and on the `subscription_id` field of the paused log line (Task 5.4).
- Sizer: `size = min(balance × risk / |entry − sl|, balance × max_exposure / entry)` (`core/domain/risk/services/position_calculator_domain_service.py:43-45`). Balance = Exness `equity − used_margin` (`exness_broker_adapter.py:645-658`). `RiskConfig` caps `risk_per_trade` at 0.10 (`core/domain/risk/value_objects.py:17-18`). Reconcile builds every config with `RiskConfig()` (`engine/live/strategy_reconcile_app_service.py:167-173`).
- Arithmetic at 250 USD, leverage 1000, risk 0.10, exposure 0.10: cap leg `25 000 / price` units (about 6 oz gold, 22 300 EUR); risk leg `25 / |entry − sl|` passes for a gold stop ≤ 25 USD/oz and a EURUSD stop ≤ 0.025. `units_to_lots` caps at `max_lots`, or at `volume_min` when `max_lots` is None (`core/infra/exness/exness_mappers.py:77-96`).
- Store: repositories live only in `core/infra/persistence/repositories/` (CLAUDE.md). Precedent for an upsert keyed by a filter with a UUIDv7 `_id` on insert: `sync_status_repository.py:37-49`. Repositories are provided at `Scope.APP` in `app/di/infrastructure.py:74-87`; async providers exist (`app/di/services.py:123-129`). A route may inject a repository directly (`app/routes/system_jobs.py:30-47`).
- Load order: `lifespan` calls `bootstrap_live_instances` (`app/main.py:68`), which resolves `StrategyReconcileAppService` (`app/main_extensions.py:162-173`). After Task 5.6 its provider takes `Safeguards`, so the stored flag is loaded before any strategy loads or starts. `StrategyAppService` → `BrokerFactory` → `Safeguards` gives the same order.
- Lifetime: `Safeguards` is `Scope.APP`, one per process. `BrokerFactory` is built at `app/di/adapters.py:46` and in `tests/core_test/infra/brokers/exness/test_exness_broker_factory.py:16,20,28`. The adapter is built at `broker_factory.py:92`, `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py:132`, `tests/engine_test/test_exness_clamp_fill_position.py:46`. Reconcile is built at `app/di/services.py:172-185` and in `tests/engine_test/test_contract_spec_wiring.py:156`, `test_reconcile_restart_resume_integration.py:120,134,162`, `test_strategy_reconcile_service.py:120`.
- After Phase 01 the `api` router carries the guard: POST needs the token, GET is public. Integration tests build a fresh app with `make_test_app(settings)` (`tests/app_test/integration/app_factory.py:36`); two apps on the same test database stand in for a restart.

## Gates in this phase
- [ASK] only if `scripts/code_metrics.py --ratchet` fails: state the metric, its value and the ceiling; ask whether to raise the ceiling, leading with `Recommended: raise the ceiling` (KISS wins over padding). Otherwise none; the `develop` push is authorized.

## Entry gate
Run first. On a miss: edit nothing, spawn no `kongming`, leave the phase pending, and end with:
```
Status: BLOCKED
NOT_YET: <reason>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261019-1957-exness-go-live --from 05 after <UTC time>
```
- `docker ps` exits 0 (start Docker Desktop and retry once after 10 s).
- `git status --porcelain -- src web deploy tests scripts docs` prints nothing.
- After `git fetch origin`, each prints ≥ 1: `git show origin/develop:src/pocketquant/app/main_extensions.py | grep -c verify_admin_token` and `git show origin/develop:src/pocketquant/core/domain/subscription/entities.py | grep -c broker`.

## Tasks

### Task 5.1 — Two new settings
- Goal: leverage and Exness risk are configurable, defaulting to today's paper sizing.
- Target files and symbols: `src/pocketquant/core/config.py:125-128`.
- Steps: add `exness_leverage: float = Field(default=1.0, ge=1)` and `exness_risk_per_trade: float = Field(default=0.02, gt=0, le=0.10)`; update the comment above the caps to name both keys.
- Success criteria: unset keys change nothing.
- Verify: no verification needed (Task 5.9).

### Task 5.2 — `Safeguards` object
- Goal: one in-process object holds the caps and the pause.
- Target files and symbols: create `src/pocketquant/core/infra/brokers/exness/exness_safeguards.py` → `@dataclass class Safeguards`.
- Steps:
  1. Fields: `live_trading: bool`, `daily_loss_cap: float | None`, `max_lots: float | None`, `leverage: float`, `risk_per_trade: float`, `entries_paused: bool = False`.
  2. One method `set_entries_paused(paused: bool)` that sets the flag and logs WARNING `exness.safeguards.entries_paused` or `exness.safeguards.entries_resumed`.
  3. Docstring: one object per process; `entries_paused` is loaded from the store at startup and written on every pause and resume, so it survives a restart; the pause blocks opens only.
- Success criteria: a plain dataclass with one method.
- Verify: no verification needed (Task 5.9).

### Task 5.3 — Store for the pause flag
- Goal: the pause flag survives a restart, with the smallest store.
- Target files and symbols: `src/pocketquant/core/common/constants.py` (new `COLLECTION_SAFEGUARDS = "safeguards"`); create `src/pocketquant/core/infra/persistence/repositories/safeguards_repository.py` → `SafeguardsRepository(BaseRepository)`; `app/di/infrastructure.py` (one `provide` line after `:87`).
- Steps:
  1. `async def load_entries_paused(self) -> bool`: `doc = await self._collection().find_one({})`; return `bool(doc and doc.get("entries_paused"))`.
  2. `async def save_entries_paused(self, paused: bool) -> None`: `update_one({}, {"$set": {"entries_paused": paused, "updated_at": datetime.now(UTC)}, "$setOnInsert": {"_id": generate_id_str()}}, upsert=True)`. One document; the `_id` is UUIDv7.
  3. Module docstring: one document holds the entry pause of the Exness safeguards. No index (one document).
  4. `safeguards_repository = provide(SafeguardsRepository, scope=Scope.APP)`.
- Success criteria: two methods; nothing else is stored.
- Verify: no verification needed (Task 5.9).

### Task 5.4 — DI and factory
- Goal: the factory and adapter read `Safeguards`; `default_broker_config` loses the Exness keys; the stored pause is loaded at startup.
- Target files and symbols: `app/di/adapters.py` (new `get_safeguards` at `Scope.APP`; `get_broker_factory`); `core/infra/brokers/broker_factory.py` (constructor and exness branch); `app/di/services.py:166-167`.
- Steps:
  1. `async def get_safeguards(self, settings: Settings, repo: SafeguardsRepository) -> Safeguards`: seeded from the five Settings fields, with `entries_paused=await repo.load_entries_paused()`.
  2. `get_broker_factory` takes `safeguards: Safeguards` and passes it in place of `exness_live_trading=`.
  3. `BrokerFactory`: replace `exness_live_trading: bool = False` with `safeguards: Safeguards | None = None`; the exness branch refuses with the same message when `safeguards is None or not safeguards.live_trading`, and passes `safeguards` to the adapter.
  4. Delete the two `exness_*` keys from `default_broker_config`.
- Success criteria: one source of truth for the caps and the pause.
- Verify: `grep -rn "exness_daily_loss_cap\|exness_max_lots" src/pocketquant/app/di/services.py src/pocketquant/core/infra/brokers/broker_factory.py` prints nothing.

### Task 5.5 — Adapter reads `Safeguards` and checks the pause first
- Goal: while paused every open is rejected before any venue call; closes are never gated.
- Target files and symbols: `exness_broker_adapter.py` → `__init__` (`:95-107`), `_lots` (`:187-195`), `_presubmit_reason` (`:243-253`), `_loss_cap_reason` (`:255-264`), module docstring (`:1-12`).
- Steps:
  1. The constructor takes `safeguards: Safeguards` in place of `daily_loss_cap` and `max_lots`.
  2. `_lots` reads `safeguards.max_lots`; `_presubmit_reason` and `_loss_cap_reason` read `safeguards.daily_loss_cap`.
  3. First branch of `_presubmit_reason`: when `safeguards.entries_paused`, log WARNING `exness.order_rejected_presubmit` with `reason="entries_paused"`, `subscription_id=order.subscription_id`, `symbol=order.symbol`, and return `"entries paused"`.
  4. `submit_order` unchanged. Add one docstring sentence on the pause.
- Success criteria: the adapter has no cap fields of its own.
- Verify: `grep -n "daily_loss_cap: float\|max_lots: float" src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py` prints nothing.

### Task 5.6 — Leverage in the sizer
- Goal: the exposure cap scales with leverage; default 1.0 keeps today's result.
- Target files and symbols: `core/domain/risk/value_objects.py` → `RiskConfig`; `core/domain/risk/services/position_calculator_domain_service.py:44` and the comments at `:13-15`.
- Steps:
  1. `RiskConfig.leverage: float = 1.0`; `__post_init__` raises when `leverage < 1`.
  2. `cap = account_balance * max_exposure * leverage / entry_price`, with `leverage` from `risk_config` (1.0 when it is None).
  3. Rewrite the three non-English comments at `:13-15` in English (CLAUDE.md).
- Success criteria: one formula change.
- Verify: `grep -c "leverage" src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py` prints ≥ 1.

### Task 5.7 — Reconcile gives Exness subscriptions the Exness risk
- Goal: `exness` subscriptions size with leverage 1000 and risk 0.10; all others keep `RiskConfig()`.
- Target files and symbols: `engine/live/strategy_reconcile_app_service.py` → `__init__` (`:59-69`), `_ensure_instances` (`:167-173`); `app/di/services.py` → `get_reconcile_service` (`:172-185`).
- Steps:
  1. Constructor keyword `exness_risk: RiskConfig | None = None`.
  2. `get_reconcile_service` takes `safeguards: Safeguards` and passes `exness_risk=RiskConfig(leverage=safeguards.leverage, risk_per_trade=safeguards.risk_per_trade)`, built once. This dependency also loads the stored pause before `bootstrap` (Context, load order).
  3. In `_ensure_instances`, pass `risk=self._exness_risk` when `sub.broker == "exness"` and it is set; else `RiskConfig()`. Backtests never pass through reconcile.
- Success criteria: one keyword, built once.
- Verify: no verification needed (Task 5.9).

### Task 5.8 — Safeguards routes
- Goal: `GET /api/v1/admin/safeguards` (public), `POST .../pause` and `POST .../resume` (token), with the pause written to the store.
- Target files and symbols: create `src/pocketquant/app/routes/safeguards.py`; `app/main_extensions.py` (include after `system_jobs_router`, `:455`).
- Steps:
  1. `APIRouter(prefix="/admin/safeguards", route_class=DishkaRoute)`; three routes inject `FromDishka[Safeguards]` and return `dataclasses.asdict(safeguards)`: `GET ""`; `POST /pause`; `POST /resume`.
  2. Pause and resume also inject `FromDishka[SafeguardsRepository]`: first `safeguards.set_entries_paused(p)`, then `await repo.save_entries_paused(p)`. A store error propagates (500); the in-memory flag already holds.
  3. No per-route auth (Phase 01 rule).
- Success criteria: three routes; pause and resume write the store.
- Verify: no verification needed (Task 5.9).

### Task 5.9 — Tests
- Goal: sizing, pause, the stored flag, fail-closed config and routes are pinned.
- Target files and symbols: create `tests/core_test/unit/domain/risk/test_position_calculator_leverage.py`, `tests/app_test/integration/test_safeguards_api.py`; modify `tests/core_test/infra/brokers/exness/test_exness_broker_adapter.py`, `test_exness_broker_factory.py`, `tests/engine_test/test_exness_clamp_fill_position.py`, `tests/engine_test/test_subscription_broker_selection.py`, the four reconcile test sites listed in Context (only if their construction breaks), `tests/app_test/integration/test_admin_token_guard.py`.
- Steps — cases:
  1. Sizer: 250 USD with `RiskConfig(leverage=1000, risk_per_trade=0.10)`: XAUUSD 4180 with a 20 USD stop gives size ≥ 1; EURUSD 1.12 with a 0.0020 stop gives size ≥ 1000. Same inputs with `RiskConfig()` give less than one minimum lot. `leverage=1.0` reproduces an existing case. `RiskConfig(leverage=0.5)` raises.
  2. Adapter (`_Harness` builds a `Safeguards`): paused open → rejected "entries paused", no `openPosition`; paused close of a held position → sent; after `set_entries_paused(False)` an open is sent; `max_lots` from `Safeguards` clamps; `daily_loss_cap=None` still rejects "EXNESS_DAILY_LOSS_CAP not set" (keep the existing parametrized case at `:205` green); `max_lots=None` sends exactly `volume_min` lots.
  3. Factory and clamp tests construct with `Safeguards`; the refusal and build cases keep their meaning.
  4. Reconcile with `exness_risk=RiskConfig(leverage=1000, risk_per_trade=0.10)`: an `exness` subscription gets `risk.leverage == 1000` and `risk.risk_per_trade == 0.10`; a `paper` one gets `RiskConfig()`.
  5. Safeguards API: on an empty database GET returns the six fields with `entries_paused` false; POST pause then GET shows true; POST resume shows false; with a token set, POST without header → 401 and GET → 200.
  6. Restart (same file): app 1 POSTs pause; app 2 built with `make_test_app(settings)` on the same database GETs `entries_paused` true; app 2 POSTs resume; app 3 GETs `entries_paused` false.
  7. `test_admin_token_guard.py`: change the assertion from `== 17` to `== 19`.
- Success criteria: every case above exists.
- Verify: `uv run python -m pytest tests/core_test/infra/brokers tests/core_test/unit/domain/risk tests/engine_test tests/app_test/integration -q` exits 0.

### Task 5.10 — Docs
- Goal: env table and architecture describe the safeguards.
- Target files and symbols: `docs/deployment.md` env table; `docs/system-architecture.md` "Exness broker" section (`:185-191`).
- Steps:
  1. Add `EXNESS_LEVERAGE` ("Account leverage ratio, used only to size Exness entries; default 1") and `EXNESS_RISK_PER_TRADE` ("Share of balance risked per Exness entry, 0-0.10; default 0.02"). Reword `EXNESS_DAILY_LOSS_CAP` to "Daily realized-loss limit in account currency, per UTC day; unset rejects every Exness order".
  2. Add one bullet: "**Safeguards:** one in-process `Safeguards` object holds the env caps and `entries_paused`. `GET /api/v1/admin/safeguards` shows it; `POST .../pause` and `.../resume` flip the pause. The pause blocks opens only. It is stored in the `safeguards` collection and loaded before strategies start, so it survives a restart. Exness subscriptions size with `EXNESS_LEVERAGE` and `EXNESS_RISK_PER_TRADE`; paper and backtests keep the defaults."
- Success criteria: three env rows and one bullet.
- Verify: `grep -c "EXNESS_RISK_PER_TRADE" docs/deployment.md` prints ≥ 1 and `grep -c "so it survives a restart" docs/system-architecture.md` prints `1`.

### Task 5.11 — Full suite, gates, push
- Goal: green on `origin/develop`.
- Target files and symbols: whole repo.
- Steps: `just test 2>&1 | tail -n 15`; ruff and pyright on `src` and touched tests; `uv run lint-imports`; `uv run python scripts/code_metrics.py --ratchet` (a failure → the [ASK] above); commit; `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin` (never print the token).
- Success criteria: only the expected Windows red.
- Verify: the pytest summary shows exactly `4 failed` and `4 errors`, all in `test_utc_runtime_guard.py` or `test_cron_trigger_timezone.py`; ruff `All checks passed!`; pyright `0 errors`; lint-imports `Contracts: 8 kept, 0 broken.`; ratchet exits 0; `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.

## Risk
- Sizing leaks into paper or backtests (L/H). `leverage` defaults to 1.0 and only reconcile sets it for `exness`; the `leverage=1.0` test and existing suites pin it.
- A gold stop wider than 25 USD/oz is still rejected `below_min_lot` (M/M); hitnrun2 allows stops up to 1% of entry, about 41.8 USD/oz (`hitnrun2_strategy_service.py:38,103`). Phase 11 measures paper stop distances per candidate; Phases 11 and 12 stop on any below-minimum line.
- Leverage sizing can meet a venue margin rejection; the daily cap ignores unrealized loss (M/L). Size stays ≤ `EXNESS_MAX_LOTS`.
- While paused, hitnrun2 re-arms on rejection (`hitnrun2_strategy_service.py:130-132`) and re-signals each 1m bar while its condition holds: one REJECTED order and one WARNING per bar (bounded). Phase 11 records the count.
- A store write fails on pause (L/M): the route returns 500 while the in-memory pause holds; retry the pause. A failed write on resume leaves the store paused, so a restart starts paused (the safe direction).
- The pause survives a restart; strategy state does not (warmup, open direction). Planned restarts while live follow the "Restart while live" runbook (Phase 09 writes it).

## Rollback
Before deploy A: revert on `develop`. After: revert, then fast-forward `master` [ASK], through the "Restart while live" runbook in `docs/deployment.md`. Without `EXNESS_LEVERAGE`/`EXNESS_RISK_PER_TRADE` support an `exness` entry at 250 USD is rejected `below_min_lot` again. The `safeguards` collection may stay; old code ignores it.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
