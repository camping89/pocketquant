# Red team: Scope & Complexity Critic (contract verifier), 2026-10-28

Findings returned in the reviewer's reply; summarized verbatim-in-substance here for adjudication.

1. Critical — `oom_lines=` gate can never pass (Phase 02 writes three `oom_lines=` lines; Phases 07/08 gates expect one; Phase 10 stops on absolute > 0). Fix: one `oom_baseline=<n>` line in Phase 02; all phases compare against it; optionally use `/proc/vmstat oom_kill`.
2. Critical — `trader.takeover_complete` never emitted (Phase 07 emits one `trader.takeover` with `takeover_ms` and `handover_gap_ms`); Phase 09 docs and Phase 10 count (9 vs 8) and `handover-row.sh` depend on it. Fix: single event; Phase 09/10 aligned.
3. High — Phase 06 parses prod logs as JSON (`json.loads(l[l.index('{'):])`); prod is `LOG_FORMAT=console` with ANSI. Phase 08's `11-verify.sh:177,228` keep JSON-only error patterns. plan.md Unresolved 2 still says JSON spacing. Fix: ANSI strip + key=value in Phase 06; console `[error` token in 11-verify; delete Unresolved 2.
4. High — four drifting VPS measurement script sets (Phase 02 `.cache/machine-snapshot.sh`, Phase 03 copy, Phase 08 `/opt/pocketquant/logs/cutover/*`, Phase 09 `/opt/pocketquant/logs/verify/bin/*`, Phase 10 `d25-summary.sh`), four lease checks with different tz handling, duplicate `docker logs -f` vs `roll()` save, deploy window written four ways. Fix: one helper set installed once (Phase 08), reused; one window rule in plan.md Conventions.
5. Medium — Phase 10 all-day `docker stats` sampler every 30 s for ~17 days and daily D25 rows exceed acceptance (D25 asks baseline, cutover, every handover) and disturb lag measurements on the 2 vCPU host. Question for owner.
6. Medium — Phase 02 writes doc text ("one process that runs the scheduler") that Phase 09's Verify bans; PDR line edited twice. Fix: split-proof wording in Phase 02.
7. Medium — Phase 10 gap-skip window (65 min, all intervals) stricter than acceptance ("bars within one interval of the boundary"). Fix: count only skips whose `bar_start` is within one interval of the release boundary.
8. Medium — one-caller parameters: `hold_lease(on_renewed=None)`, `on_acquired(waiting_since)`, `IBrokerPort.inflight_count`, `BrokerFactory(safeguards_repository=None)` + ValueError, three optional `StrategyAppService` params silently disabling warm-up/successor/realized P&L (14 test constructors omit `calendar_factory`). Fix: required params; sandbox passes explicit no-ops; compute gap inside trader closure.
9. Medium — test helper `_client(paced=False)` (`tests/core_test/infra/exness/test_exness_client.py:118-126`) patches only `min_request_interval`; new order lane not covered. Fix: patch both.

Contract table: `_process_signal` 6 callers incl. `tests/engine_test/test_strategy_reject_delivery.py:137,154,166`, `tests/engine_test/test_contract_spec_wiring.py:120,304` (missing from Phase 06 file list); `OrderFilledEvent` producer `order/entities.py:133` not named (defaults keep it valid).
