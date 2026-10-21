# Planner: apply the 2026-10-21 00:43 decisions and audit fixes

Source: `plans/261019-1957-exness-go-live/reports/kongming-261021-0033-open-items-audit.md` (Q1-Q3, gate-time defaults, section 5 defects). No commit.

## Edits (one line each)

- `phase-01-admin-token-auth.md` front matter: `status: pending` -> `completed` (`ed85d1d` is on `origin/develop`, checked with `git log --oneline -3 origin/develop`).
- `phase-02-subscription-broker-selection.md`: no edit; its front matter already said `status: completed` (`94b5a98` is on `origin/develop`).
- `plan.md` phase table: rows 01 and 02 `Pending` -> `Completed`; the table still has 12 rows.
- `plan.md` Overview "Sources": added the open-items audit and the 00:43 decisions.
- `plan.md` decision line 00:21 item (6): the token sentence now reads "a short-lived API token was the last resort if both were rejected (withdrawn at 00:43)".
- `plan.md` "User decisions (binding)": new line `2026-10-21 00:43` with (1) accept the unwatched risk, 4 h watch, bound; (2) no Cloudflare API token, stop for counsel, reverses the token part of 00:21 (6); (3) Task 11.12 `keep on` after a clean round trip; gate-time defaults applied.
- `plan.md` U3: removed the "Sole exception" token sentence.
- `plan.md` "Out of scope (flagged)": one line for the `IdempotencyMiddleware` replay (`core/common/idempotency/middleware.py:17-34,44-52`, re-read tonight).
- `plan.md` 00:21 sweep line "Cloudflare fallback": dropped the token and revoke references.
- `plan.md` sweep: new "Decision delta (2026-10-21 00:43)" block listing where each change landed.
- `plan.md` "Unresolved questions": added an "Updated 00:43" line under the strategy question and under the Cloudflare question; removed the token wording; "Open questions: none (2026-10-21 00:43)".
- `phase-09` gates line: removed the `token stored` fallback gate; it now says the phase stops for counsel if both expressions are rejected.
- `phase-09` Task 9.3 Facts: the 00:21 token sentence was replaced by the 00:43 decision (no API token; Free-plan limits apply through the API too).
- `phase-09` Task 9.3: deleted the 3-step token fallback block. `both rejected` now stops the phase as a failed Verify (Failure Protocol to `kongming` with both expressions and errors). Removed the fallback parts of Success criteria and Verify.
- `phase-09` Task 9.14: deleted the revoke step (old step 1), the `api-token` file check and "no Cloudflare token left". One step remains.
- `phase-11` Context: new 00:43 decision bullet.
- `phase-11` Task 11.8 facts: the single-order sentence now says the pause after the first entry holds while the watch runs (about 4 h), and that more trades can open one at a time under the 25 USD cap after an unwatched window (accepted).
- `phase-11` Task 11.9 step 0: "up to about 2 h" -> "about 4 h"; `TRIES=120` -> `TRIES=240`.
- `phase-11` Task 11.11 step 2: the [ASK] question now leads with the recommended reply: `accept` when only `clamped True`, `stop` when `balance_deals > 0`. Replies are `accept` and `stop`.
- `phase-11` Task 11.12 step 1: defines a clean round trip (11.9-11.11 passed, `sl seen`, an AC6 line or an accepted void). It recommends `keep on` when clean, else `pause`, and states the Phase 12 effect of each.
- `phase-11` Risk "More than one order": 2 h -> 4 h. Added the bound: one open position per subscription (`exness_broker_adapter.py:200-205`) and the 25 USD daily cap (`:261-263`), about 50 USD per UTC day worst case, about 100 USD if a window straddles midnight UTC, plus gap slippage. Marked as accepted 2026-10-21 00:43 with no in-app feature.
- `phase-12` Context: new 00:43 bullet. Rows normally observe a trading system; after a `pause` choice they record a paused system until 12.6.
- `phase-12` Task 12.4: the question now leads with "Recommended: 2" and its reason.
- `phase-12` Task 12.6 step 2: the question now leads with "Recommended: `yes` (five rows passed, no stop event) | `no` (what did not pass)".

## Verification

- Marker string: none of the edited files contains it. One match remains in `reports/planner-261021-0021-apply-answers.md:74`. That line is the 00:21 report saying no file had a match, and the file was outside my edit scope.
- "token fallback" / "WAF Edit": 0 in `plan.md` and `phase-09`.
- "2 h" and `TRIES=120` in `phase-11`: 0.
- Phase table: 12 rows (01-02 Completed, 03-12 Pending). `ak plan validate .` prints `[OK]`.
- Line endings: these files are CRLF in `HEAD` and in the working tree. Every line has a CR, before and after the edits. I kept CRLF and converted nothing. The brief said LF.

## Notes

- Citation drift: the audit cites `exness_broker_adapter.py:199-203` and `:262-264`. A re-grep of `origin/develop` and the working tree puts the checks at `:200-205` (held check and "position already open") and `:261-263` (cap). The plan cites the re-grepped lines. Phase 05 edits this file, so these lines will shift.
- Phase status was set by editing the files directly, not through `ak plan phase close`. Two reasons: that command checks every checkbox and sets status `done`, not `completed`, and the store maps this plan under the id `pocketquant/261009-0858` (`ak plan list`), which I did not trust for a write.
- Inference: a `NOT_YET` exit at Task 9.3 would fail a Phase 09 re-run at its own entry gate. Task 9.2 deletes the `tunnel-test` route, and the gate curls it. That is why `both rejected` routes through the Failure Protocol and not a `NOT_YET` exit.
- `plan.md` front matter still says `status: pending` with two phases completed. I left it unchanged because it was not requested.

Status: DONE_WITH_CONCERNS
Summary: Decisions Q1-Q3, the gate-time defaults for 11.11, 12.4 and 12.6, the Phase 01/02 status fix and the IdempotencyMiddleware out-of-scope line are applied to plan.md and phases 01, 09, 11 and 12 (phase-02 was already completed).
Concerns/Blockers: These files are CRLF, not LF, and were kept CRLF. One marker-string match remains in the 00:21 report, which was outside scope.
