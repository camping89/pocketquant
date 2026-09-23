---
phase: 6
title: "Polling Quote Adapter and Contract-Aware Trading Math"
status: in-progress
priority: P1
effort: "1.5d"
dependencies: [5]
---

## Context

(Advice Phase 5.) Two independent pieces that together deliver G2 and G3: a realtime
quote adapter that polls TradingView while the session is open, and contract-aware
PnL so that a 0.25-point ES move on 2 contracts is 25.00 USD rather than 0.50.

The margin accounting that shipped in plan `260628-2013`
(`docs/journals/2026-06-28-paper-broker-futures-accounting.md`) stays exactly as it
is. Only the unit conversion is added. The PnL arithmetic lives in two places in
`PositionAggregate` — `reduce_quantity` (the `realized` computation) and the
`unrealized_pnl` property — both of which multiply `_calculate_pnl_per_unit(...)` by
`quantity`. Putting the multiplier on the aggregate keeps the change to those two
lines instead of scattering it across the broker.

## Tasks

### Task 1 — `PerContractCommissionModel`

**Goal.** Futures commission is charged per contract, not as a percentage of notional.

**Target files and symbols.**
- `src/pocketquant/core/domain/trading/commission_model.py` — the `CommissionModel`
  Protocol (lines 4-5) and `PercentageCommissionModel` (lines 8-13).

**Steps.**
1. Add:
   ```python
   class PerContractCommissionModel:
       """Flat fee per contract, the CME convention. `quantity` is contracts."""
       def __init__(self, usd_per_contract: float) -> None:
           self._usd_per_contract = usd_per_contract

       def compute(self, price: float, quantity: float) -> float:
           return abs(quantity) * self._usd_per_contract
   ```
2. Export it from `src/pocketquant/core/domain/trading/__init__.py` alongside
   `PercentageCommissionModel`.
3. Do not change `PercentageCommissionModel` or the Protocol.

**Success criteria.** `PerContractCommissionModel(2.5).compute(4500.0, 2) == 5.0`.

**Verify.** `uv run pytest tests/core_test/unit/domain/trading/test_commission_model.py -q` exits 0.

---

### Task 2 — Contract multiplier on `PositionAggregate`

**Goal.** Realized and unrealized PnL are expressed in account currency for any
contract size.

**Target files and symbols.**
- `src/pocketquant/core/domain/position/entities.py` — `PositionAggregate` fields
  (lines 28-44), `open` factory (lines 47-89), `reduce_quantity` (lines 127-190, the
  `realized = pnl_per_unit * quantity` line), `unrealized_pnl` property (lines 223-227),
  `market_value` (line 235), `cost_basis` (line 239), `to_mongo` (lines 245-263),
  `from_mongo` (lines 265-286).

**Steps.**
1. Add a field `multiplier: float = 1.0` with the docstring "account currency per 1.0
   of price move per contract; 1.0 for linear instruments".
2. Add `multiplier: float = 1.0` as a keyword parameter of the `open` classmethod and
   pass it into the constructor.
3. In `reduce_quantity`, change `realized = pnl_per_unit * quantity` to
   `realized = pnl_per_unit * quantity * self.multiplier`.
4. In the `unrealized_pnl` property, change the return to
   `self._calculate_pnl_per_unit(self.current_price) * self.quantity * self.multiplier`.
5. Leave `market_value` and `cost_basis` as `quantity * price` — they are notional
   quantities used for display and the existing margin checks, and changing them
   would alter the shipped margin accounting. Add a one-line comment stating that.
6. Write `multiplier` in `to_mongo` and read it in `from_mongo` with
   `doc.get("multiplier", 1.0)`, so existing position documents load as linear.
7. `TradeClosedEvent.pnl` already carries `realized`, so it inherits the multiplier
   with no further change. Confirm by reading `reduce_quantity`'s event construction.

**Success criteria.** A 2-contract ES position entering 4500.00 and exiting 4500.25
with `multiplier=50.0` realizes exactly 25.00.

**Verify.** `uv run python -c "
from pocketquant.core.domain.position.entities import PositionAggregate
from pocketquant.core.domain.position.enums import PositionSide
p = PositionAggregate.open(subscription_id='s', symbol='ES1!:CME_MINI', side=PositionSide.LONG, entry_price=4500.00, quantity=2, multiplier=50.0)
p.reduce_quantity(2, 4500.25)
print(round(p.realized_pnl, 6))"` prints `25.0`.

---

### Task 3 — Thread `ContractSpec` through the paper broker

**Goal.** A paper broker created for a futures symbol prices its fills in contracts.

**Target files and symbols.**
- `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py` — `__init__`
  (lines 108-125), `_open_position` (line 561), `_can_afford` (lines 487-500),
  `_commission` (lines 484-485).
- `src/pocketquant/core/infra/brokers/broker_factory.py` — `BrokerFactory.create`,
  the `"paper"` branch (lines 32-44).
- `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py` — `create_broker`
  (lines 111-136) and the placeholder at line 151.

**Steps.**
1. Add a `contract_spec: ContractSpec = LINEAR_SPEC` keyword parameter to
   `PaperBrokerAdapter.__init__` and store it as `self._contract_spec`.
2. In `_open_position`, pass `multiplier=self._contract_spec.multiplier` into
   `PositionAggregate.open(...)`.
3. In `_can_afford` (line 499-500), keep the notional check on
   `fill_price * order.quantity` — that is the margin accounting that shipped in plan
   `260628-2013` and is explicitly out of scope. Add a one-line comment saying so.
4. In `BrokerFactory.create`, read `config.get("contract_spec")` and
   `config.get("commission_per_contract")`. When `commission_per_contract` is not
   `None`, build a `PerContractCommissionModel`; otherwise keep
   `PercentageCommissionModel(bps=commission_bps)`. Pass the spec through.
5. In `BacktestSandboxAppService.create_broker`, add a
   `contract_spec: ContractSpec = LINEAR_SPEC` parameter and pass it through. Leave
   the `placeholder_broker` at line 151 on the default linear spec.
6. Every new parameter defaults to the linear spec, so every existing caller and test
   keeps its current behaviour.

**Success criteria.** Existing paper-broker tests pass unchanged and a spec-carrying
broker produces contract-scaled PnL.

**Verify.** `uv run pytest tests/core_test/infra/brokers/ tests/backtest_test/engine/ -q` exits 0.

---

### Task 4 — Contract-aware position sizing

**Goal.** Sizing for a futures symbol yields a whole number of contracts.

**Target files and symbols.**
- `src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py` —
  `PositionCalculatorDomainService.calculate` (lines 17-46).

**Steps.**
1. Add a keyword parameter `contract_spec: ContractSpec | None = None` after
   `commission_model`.
2. After `size = min(risk_amount / price_risk, cap)` (line 41), insert:
   ```python
   if contract_spec is not None and contract_spec.multiplier != 1.0:
       size = size / contract_spec.multiplier
   if contract_spec is not None and contract_spec.lot_step:
       size = math.floor(size / contract_spec.lot_step) * contract_spec.lot_step
   ```
   Dividing by the multiplier first is what makes `risk_amount / price_risk` mean
   "contracts" rather than "index points of exposure".
3. Recompute `notional = size * entry_price * (contract_spec.multiplier if contract_spec else 1.0)`.
4. Return `PositionCalculation(0.0, 0.0, 0.0, 0.0)` when the floor produces `0` — a
   sub-one-contract signal must not open a fractional futures position.
5. Import `math`. Keep the default path (`contract_spec=None`) byte-identical for crypto.

**Success criteria.** With the ES spec and a balance that affords 1.7 contracts, the
result is 1.0.

**Verify.** `uv run pytest tests/backtest_test/engine/test_r7_worked_example_defaults.py -q` exits 0.

---

### Task 5 — Wire the spec into the strategy and backtest paths

**Goal.** A strategy or backtest on `ES1!:CME_MINI` picks up the ES spec without the
caller naming it.

**Target files and symbols.**
- `src/pocketquant/engine/strategy/strategy_app_service.py` —
  `_get_or_create_broker` (lines 421-432) and the sizing call site (grep for
  `PositionCalculatorDomainService.calculate`).
- `src/pocketquant/core/domain/backtest/config.py` — `BacktestConfig` (lines 8-40).
- `src/pocketquant/engine/backtest/backtest_dispatch.py` — the `create_broker` call at
  line 92.
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py` — the `create_broker`
  call at line 106.

**Steps.**
1. Add `contract_spec: ContractSpec = LINEAR_SPEC` to `BacktestConfig` as the last
   field (dataclass ordering: it has a default, so it may follow the existing
   defaults).
2. In `backtest_dispatch.py` and `backtest_strategy_loader.py`, resolve the symbol's
   spec via `SymbolLookupHelper` before building the config, and pass it into both
   `BacktestConfig(...)` and `sandbox.create_broker(...)`.
3. In `strategy_app_service._get_or_create_broker`, the broker is shared across
   subscriptions of the same broker type, so it CANNOT carry a per-symbol spec.
   Instead: keep the broker linear and resolve the spec per order. Read the sizing
   call site and pass `contract_spec=` into
   `PositionCalculatorDomainService.calculate`, and pass `multiplier=` through the
   order into `_open_position`. If that thread proves to need more than three call
   edits, STOP and follow the Failure Protocol — a broker keyed by
   `(broker_type, contract_spec)` is the alternative and is a design decision, not an
   improvisation.
4. Do not add a `contract_spec` field to `OrderAggregate`. The order carries a
   quantity in contracts; the spec belongs to the symbol.

**Success criteria.** A backtest config for a futures symbol carries the ES spec and
the broker prices fills with it.

**Verify.** `uv run pytest tests/backtest_test/ -q` exits 0.

---

### Task 6 — Contract math tests

**Goal.** G2's worked example is a test, not a manual observation.

**Target files and symbols.**
- New file `tests/core_test/infra/brokers/test_paper_broker_contract_spec.py`.

**Steps.**
1. Write 6 tests:
   - `test_es_round_trip_realizes_25_usd`: 2 contracts, entry 4500.00, exit 4500.25,
     `multiplier=50.0`, zero commission → realized PnL exactly 25.00.
   - `test_es_round_trip_with_per_contract_commission`: the same with
     `PerContractCommissionModel(2.5)` → realized 25.00 and total commission 10.00
     (2 contracts entry + 2 contracts exit).
   - `test_nq_multiplier_20`: 1 contract, 1.00-point move → 20.00.
   - `test_ym_multiplier_5`: 1 contract, 1.00-point move → 5.00.
   - `test_linear_default_is_unchanged`: `multiplier=1.0` reproduces the current
     crypto arithmetic.
   - `test_equity_curve_has_no_jump_at_fill_beyond_commission`: assert the balance
     delta at fill time equals `realized_pnl - commission`.

**Success criteria.** 6 tests pass.

**Verify.** `uv run pytest tests/core_test/infra/brokers/test_paper_broker_contract_spec.py -q` exits 0 and prints `6 passed`.

---

### Task 7 — `TradingViewQuoteAdapter` (the realtime port)

**Goal.** A polling quote source that is quiet while the market is closed and emits
the existing quote-dict contract.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_quote_adapter.py`.
- Symbol: `TradingViewQuoteAdapter`, satisfying the 9-member
  `IRealtimeQuoteProviderPort` Protocol.
- Contract reference: the quote dict produced by
  `src/pocketquant/core/infra/binance/binance_mappers.py:93-106` — keys `symbol`,
  `timestamp`, `last_price`, `volume`, `bid`, `ask`, `change`, `change_percent`,
  `open_price`, `high_price`, `low_price`, `prev_close`.

**Steps.**
1. Constructor takes `client: ITradingViewClient`, `settings: Settings` and
   `calendar_factory: TradingCalendarFactory`.
2. `subscribe(symbol, callback)` records `(symbol, callback)` and starts one
   `asyncio.Task` per symbol. `unsubscribe(symbol)` cancels that task and removes the
   entry. Return the composite symbol as the subscription key, matching
   `BinanceWebSocketAdapter`.
3. Each poll task loops: resolve the calendar; when
   `calendar.is_open(datetime.now(UTC))` is False, sleep
   `settings.tradingview_poll_seconds` and continue WITHOUT calling the client; when
   open, fetch the latest 1m bar, and if its `close` differs from the previously
   emitted close, build the quote dict and `await` the callback.
4. Build the quote dict with `timestamp` set to the bar's UTC `datetime`,
   `last_price` to its close, and every other key `None` — exactly the Binance shape,
   so `QuoteAppService.on_quote_update` needs no change.
   `volume` must be a PER-POLL DELTA, not the bar total. The downstream `add_tick`
   contract treats `volume` as the increment contributed by this tick, so emitting a
   cumulative bar total would inflate accumulated volume on every poll within the
   same minute. Keep `self._last_seen[symbol] = (bar_datetime, bar_volume)` and emit
   `bar_volume - previous_volume` when the polled bar has the SAME `datetime` as the
   previous poll, or the full `bar_volume` when the bar has rolled to a new
   `datetime`. Clamp a negative delta to `0.0` and log it at DEBUG — an upstream
   revision can make the total go down.
   Note in the docstring that `tick_count` is 1 per poll, so tick counts measure poll
   cadence rather than market activity.
5. `last_tick_at` is set on every successful emission. `is_connected()` returns
   `client.is_authenticated() and bool(self._tasks)`.
6. `run_forever()` awaits an `asyncio.Event` that is never set, so
   `WsSubscriptionAppService` and the lifespan task management behave as they do for
   the WS adapter; let `CancelledError` propagate.
7. `connect()` and `disconnect()` start and cancel all tasks respectively.
8. Log per-poll at DEBUG only.
9. Register it in `src/pocketquant/app/di/market_data.py` inside the
   `RoutingRealtimeQuoteAdapter` providers dict under the key `"tradingview"`.

**Success criteria.** With a closed calendar the poll task issues zero client calls;
with an open calendar a price change emits one quote dict.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py -q` exits 0 and prints `5 passed` (tests written in Task 8).

---

### Task 8 — Quote adapter tests and a relaxed staleness threshold

**Goal.** The polling adapter is covered, and the 30s staleness watchdog does not fire
on a 60s poll cadence.

**Target files and symbols.**
- New file `tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py`.
- `src/pocketquant/core/infra/binance/binance_websocket_adapter.py` —
  `_stale_connection_watchdog` (around line 237). Read it and note its threshold.
- `src/pocketquant/engine/market_data/app_services/quote_app_service.py` — any
  staleness check on `provider.last_tick_at`.

**Steps.**
1. Write 5 tests with a fake client and a stub calendar:
   `test_closed_market_makes_no_client_call`,
   `test_open_market_emits_quote_on_price_change`,
   `test_unchanged_close_emits_nothing`,
   `test_quote_dict_matches_the_binance_key_set`,
   `test_unsubscribe_cancels_the_poll_task`.
2. Read `_stale_connection_watchdog` and any `last_tick_at` staleness check in
   `quote_app_service.py`. The Binance watchdog belongs to the Binance adapter and is
   not shared, so no change is needed there. If `QuoteAppService` applies a global
   staleness threshold to `provider.last_tick_at`, raise it to
   `max(existing, settings.tradingview_poll_seconds * 3)` and add a comment naming the
   polling provider as the reason. If it does not, change nothing and note that in the
   phase completion note.

**Success criteria.** 5 tests pass and no false staleness alert appears in a
60s-cadence run.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/ tests/app_test/unit/market_data/test_quote_app_service.py -q` exits 0.

---

### Task 9 — Phase gate: G2 and G3

**Goal.** Prove the two user-facing goals on real data.

**Target files and symbols.** None (verification only).

**Steps.**
1. G2: run a paper strategy on `ES1!:CME_MINI` for one full CME session. Execute one
   round trip of 2 contracts entering at 4500.00 and exiting at 4500.25 (or the
   nearest real prices) and confirm the recorded realized PnL is
   `(exit - entry) * 50 * 2` minus commission, and that the equity curve has no jump
   at fill time other than commission.
2. G3: run a 1h backtest on `ES1!:CME_MINI` over the available window. Confirm the
   reported `periods_per_year` is the session-derived value (roughly 5796), not 8760,
   and that dollar PnL equals points x 50 x contracts.
3. Record both numbers in the phase completion note.

**Success criteria.** Both match to the cent.

**Verify.** `uv run pytest tests/ -q && uv run ruff check src tests scripts && uv run lint-imports` exits 0.

## Todo

- [x] Task 1 — `PerContractCommissionModel`
- [x] Task 2 — Contract multiplier on `PositionAggregate`
- [x] Task 3 — Thread `ContractSpec` through the paper broker
- [x] Task 4 — Contract-aware position sizing — the exposure cap sizes ES to zero
      contracts at the default 10,000 balances (plan.md, Session 9)
- [x] Task 5 — Wire the spec into the strategy and backtest paths — via the
      `(broker_type, contract_spec)` pool after the Failure Protocol (Correction 27)
- [x] Task 6 — Contract math tests
- [x] Task 7 — `TradingViewQuoteAdapter` (the realtime port) — Corrections 29, 30
- [x] Task 8 — Quote adapter tests and a relaxed staleness threshold — no global
      staleness check reads `last_tick_at`, so nothing changed there
- [ ] Task 9 — Phase gate: G2 and G3 — G3 verified on production data (132 ES trades
      exact to the cent, Sharpe on 5910 periods a year). G2's live session waits on the
      paper-balance and exposure-cap decision (plan.md, Session 9)

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A shared paper broker per broker type cannot carry a per-symbol spec | High | Medium | Task 5 step 3 names the limit and routes the decision to the Failure Protocol rather than improvising |
| `market_value`/`cost_basis` left unmultiplied desynchronises the margin check | Medium | Medium | Task 2 step 5 makes it a deliberate, commented decision, preserving the shipped accounting |
| Polling at 60s misses intra-bar moves, so paper fills are optimistic | High | Low | Stated trade-off; `tradingview_delayed_data` is surfaced in the UI in Phase 7 |
| A persisted position document without `multiplier` loads wrong | Low | High | Task 2 step 6 defaults it to `1.0` |

**Rollback.** Task 7 and its DI registration revert independently of Tasks 1-6. Tasks
1-6 are additive with linear defaults, so reverting them restores the previous
arithmetic exactly.

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

