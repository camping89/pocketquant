# Closing the open work after the 1d cascade fold release

Advisory, 2026-11-08. Read-only: nothing committed, pushed or changed on prod. Evidence comes from `git show fc173b5f`, the readers of `job_history.details` in `src/` and `web/`, `docs/deployment.md`, the two plans, and the local `.cache/d16.py` (gitignored copy of the rebuilt D16 script, 2026-11-04). "Fact" = read in the repo; inference is labelled.

## TL;DR

`fc173b5f` is acceptable as shipped; no reader breaks, one pre-existing wording quirk in the runs table applies to it, and no code change is needed. Add one sentence to the `docs/deployment.md` runbook. Record the D16 amendment and the dated final run as a `## Follow-ups` section in plan `261103-1741` (not in the closed MTF plan), paste the script there so the run is reproducible, and update the phase-05 report's "Unresolved" list. Everything else (release, the amendment itself, the planner folder) waits for the owner, and all three fit in one question.

## Q1: Review of `fc173b5f`

Verified facts:
- Writers of `details[]`: `_sync_by_intervals` with status `result.status` (`completed` on success, `sync_jobs.py:349-352`), `skipped` (`:307`), `error` (`:336`); now `sync_integrity` with `issues_found` (`:511`). The repository `record_detail` (`job_history_repository.py:131-160`) takes `status: str` and `error: str | None`, free text, no enum.
- Readers of `details`: `run-detail-drawer.tsx:96-112` renders each row; `d.status` goes through `statusColor`/`statusLabel`, whose fallback for an unknown value is grey `#94a3b8` and the raw string (`job-status-palette.ts:25-31`); `d.error` is only the `title` tooltip of the pill (`:105`). `job-runs-table.tsx:31` computes `failedCount = details.filter(d => d.status !== 'completed')` and prints `N (M failed)` (`:51-53`). `JobRunDetail.status` is typed `string` (`web/src/types/job-history.ts:12-22`), so no TS change is forced.
- Unaffected: `aggregate_stats` groups by the run's `status`, not details (`job_history_repository.py:244-254`); `GET /{job_id}/runs` filters the run status (`system_jobs.py:21-35`); `remove_symbol_details` pulls by `details.symbol` (`:301-305`), which the new entry sets, so symbol removal cleans integrity rows too. No reader in `src/` or `web/` parses `details.error`.
- Size: `SYNC_INTERVALS` has 7 members (`sync_jobs.py:56-64`), 6 tracked symbols, so the worst case is 42 entries, under the "about 50" comment on `record_detail`; only issues are written, and the 2026-11-07 reproduction found 0. Each `error` string is bounded by the two `[:5]` slices (inference: under 1 KB).
- Helper: `_record_detail` has two real callers (the `detail` closure and `sync_integrity`), which meets the CLAUDE.md rule. The WHY comment on the write states the reason. Test `test_integrity_issues_are_stored_on_the_run` asserts the call, the status, the misaligned count and the gap text.

Judgement:
- `status="issues_found"` and the summary in `error`: acceptable. `error` is the schema's only free-text slot, nothing treats it as a failure signal, and the drawer shows it exactly where a human looks (tooltip on the pill). The filler zeros for `bars_fetched`, `bars_inserted`, `filtered_existing` are forced by the signature; changing the signature for one caller would be more code for no reader.
- One quirk, pre-existing and not introduced here: the runs table counts every non-`completed` detail as "failed", so a closed-market `skipped` row already prints as failed, and an integrity run with two issues prints `2 (2 failed)`. In the drawer the pill is grey with the literal `issues_found`. Both are readable. If the owner wants it tidier later, the smallest change is in `job-runs-table.tsx:31` (`d.status === 'error'`) and an amber entry for `issues_found` in the palette; do not bundle that into this release.
- Nothing to fix before release. Verdict: ship as is.

## Q2: Docs

Verified: the only prose about `job_history` is `docs/deployment.md` "Sync gap repair" (`:219`): "Check for bar-data gaps when `job_history` shows `missed` events for `sync_backfill`... The web `/monitor` page shows the same audit for all symbols." `README.md` and `docs/system-architecture.md` do not name `sync_integrity` or the details array. No doc describes the detail schema (owned by `record_detail`, so none should).

Under the line test, the fact "integrity issues are stored on the run" is owned by code (rule 1) and needs no line. The runbook trigger is the one place that benefits: it names `missed` events as the cue to audit, and the new rows are now the better cue. Add one sentence after the first sentence of that paragraph:

> Check also when the latest `sync_integrity` run in `/monitor` lists details: each row is a (symbol, interval) with missing or misaligned bars, and the pill tooltip holds the gap ranges.

That is the whole doc impact. It belongs in the same develop-only docs commit as the plan updates, or in the code change's follow-up; either is fine.

## Q3: Where the D16 amendment and the final run go

Facts that shape the answer:
- D16 is a decision of plan `261101-0843` (`plan.md:50`), status `completed`; its Phase 17 run passed under that rule. Governance says plans are "records, not authority" (`docs/governance/documentation-rules.md`, "Where Content Goes"). Re-opening a closed plan to rewrite a rule its run already satisfied would make the record lie about what Phase 17 checked.
- Plan `261103-1741` rebuilt the script (`reports/phase-05-...md:56`), ran it under D16 in Task 05.5, and left both open items in its "Unresolved" list (`:125-128`). The script's code is not tracked: `.cache/` is gitignored, and the phase-05 report keeps only the one-off `run_jobs.py` and the output lines.
- The D14 window is the latest 14 days ending at the current UTC midnight (`.cache/d16.py`: `FIRST = LAST - timedelta(days=14)`). On 2026-11-11 `FIRST` is 2026-10-28, so the BTCUSD 2026-10-24 row is outside the comparison on its own. The amendment therefore guards only future vendor revisions on days 8-14 days old; it is not needed for the final run to pass on today's data.

Recommendation: record everything in plan `261103-1741`, which owns the script rebuild and the open items, and leave `261101-0843` untouched.

1. `plans/261103-1741-1d-cascade-fold-and-small-fixes/plan.md`: append a section after "## Risks" (before "## Failure Protocol"):

```markdown
## Follow-ups

| # | Item | Owner decision | Due |
|---|---|---|---|
| F1 | Final D16 run: one read-only run of the script below on or after 2026-11-11, when every day of the 7-day fold window was built by the released code. Pass: `mismatches=0 repair_1d=0`. On pass, retire the script; on a fail inside the window, open a Failure Protocol round. | proposed 2026-11-07 (kongming report `plans/reports/kongming-261107-1227-open-questions-and-prod-state.md`), owner: pending | 2026-11-11 to 2026-11-15 |
| F2 | D16 amendment: for a day older than the 7-day fold window (`_REPAIR_DAYS` in `sync_jobs.py`), a row passes when the stored 1d equals the dry-run aggregate of its stored 1m bars (OHLC tolerance 1e-9, volume 1e-4); vendor equality is required only inside the window. Reason: no job refreshes a 1d bar older than the window since E3, so a vendor revision there is permanent noise. Example: BTCUSD 2026-10-24, vendor volume 113120/113100/113120 across reads, stored 1d within tolerance of its 1m aggregate. | owner: pending | before F1 |

F1 runs with PRODPY (Ops recipe) and this script; it is the phase-05 `.cache/d16.py` plus the F2 branch. Set `D1` to the `d1_deployed_at=` value of `plans/261101-0843-stf-to-mtf-foundation/reports/phase-03-*.md`. If F2 is declined, delete the `if d < WINDOW` branch.
```

followed by a fenced `python` block holding the full `.cache/d16.py` with this change applied after `s_ok, d_ok = eq(st, v), eq(agg, v)`:

```python
WINDOW = LAST - timedelta(days=7)  # _REPAIR_DAYS: the fold never rebuilds a day older than this
...
                if d < WINDOW:
                    ok = st is not None and agg is not None and eq(st, SimpleNamespace(**agg))
                else:
                    ok = s_ok and d_ok and (not post or src == "cascade")
                mismatches += 0 if ok else 1
                print(sym, d.date(), "stored=" + ("equal" if s_ok else "diff"), "dry=" + ("equal" if d_ok else "diff"),
                      "window=" + str(int(d >= WINDOW)), "source=" + str(src), "post_d1=" + str(int(post)),
                      "updated_at=" + str(upd), f"n1m={n}/{total}")
```

`eq` already compares a dict against an attribute object with the right tolerances, and `aggregate_ohlcv` returns a dict with `open`, `high`, `low`, `close`, `volume` (`cascade_aggregator.py:41`), so `SimpleNamespace(**agg)` reuses it without a new helper. Keep the last three output lines unchanged so the phase-05 Verify text still reads them.

2. `plans/261103-1741-1d-cascade-fold-and-small-fixes/reports/phase-05-release-and-prod-checks.md`, replace the two "Unresolved" bullets with:

```markdown
## Unresolved

- R4: closed on 2026-11-07. The 11-05 to 11-07 `integrity.issues_found` lines were lost with the redeployed containers; a read-only `check_integrity` run over the same 7-day window printed `issues_total=0` for all six symbols and 5m-1d (`plans/reports/kongming-261107-1227-open-questions-and-prod-state.md`, Q2). `fc173b5f` stores each future issue on the `sync_integrity` run doc.
- The D16 amendment and the final D16 run are tracked as F1 and F2 in `plan.md` "Follow-ups".
```

3. Do not add a D17 to `261101-0843`. If the owner later wants a cross-reference there, one line under its D16 row ("Amended for pre-window days by `261103-1741` F2") is enough, but it is not needed to close the work.

If the owner skips the final run: keep F1 with "owner: declined <date>" rather than deleting it, so the record says the check was considered and why it stopped. Nothing else changes.

## Q4: What closes now, what waits

Can be done now, commits to `develop` only (the owner's "do what you can" covers records and docs, not a release):

1. `docs(plans): track the D16 follow-ups and close R4` — the plan "Follow-ups" section with the script, and the phase-05 "Unresolved" rewrite above. Both files are under `plans/`, exempt from the line test, so pasting the script is allowed.
2. `docs(deployment): point the gap-repair runbook at the integrity run details` — the one sentence in Q2. A `.md`-only push runs no CI job (`cicd.yml` `paths-ignore` lists `**/*.md`), so no deploy side effect and no CI wait.
3. Leave `fc173b5f` as is. No code change, no test change.

Must wait for the owner, and can be asked in one message:

- Release: `develop:master` is an [ASK] by plan convention. Candidate `9f8f3b10` (or the docs commits above on top) carries `fc173b5f` as the only code change. Note for the ask: the deploy recreates `api`, `worker`, `trader` (container `-19`) and drops their logs again, which is the condition the change exists for; a release before 2026-11-09T04:00Z makes Monday's `sync_integrity` the first run whose issues persist.
- D16 amendment (F2): the owner decides; the final run works either way because the known row leaves the window by 2026-11-11.
- `plans/261028-0652-exness-only-parallel-runtime/.claude/agent-memory/planner/`: untracked, uncited, 4 files. Options: delete, move the two reusable notes under `.claude/agent-memory/planner/`, or track where it is. Recommended default: delete; the owner's `e49c0565` tracks agent memory at the repo root only.

Not needed: no change to `261101-0843`, no web change, no test beyond what `fc173b5f` added, no new job or flag.

## Assumptions

- The coordinator's statements that GATES pass, FULLSUITE matches the baseline and develop CI is green on `9f8f3b10` are taken as given (medium: I did not re-run them; they do not change the review verdict, which rests on the readers of `details`).
- `aggregate_ohlcv` returns keys `open`, `high`, `low`, `close`, `volume` (high: the phase-05 script fed its result to `eq` through the same path and printed `dry=equal` on 37 rows).
- The owner's "do what you can to close the work correctly" authorises record and doc commits on `develop` but not a release (high: the plan text makes the release an explicit [ASK] every time).

## Unresolved

- Owner decisions: release yes/no, F2 yes/no, planner folder disposition.
- Whether the owner wants the runs-table "(N failed)" wording and the grey `issues_found` pill tidied later (cosmetic, separate change).
