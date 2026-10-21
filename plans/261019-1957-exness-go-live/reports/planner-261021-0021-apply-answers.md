# Planner: apply the 2026-10-21 answers to the Exness go-live plan

Source: `plans/261019-1957-exness-go-live/reports/kongming-261021-0010-answers-reanalysis.md`. User approved "apply all" on 2026-10-21 00:21 (Asia/Bangkok). Phases 01-04, 07, `src/`, `web/`, `docs/`, `deploy/` are untouched.

## Edits

### plan.md
- Overview "Sources": adds the kongming 2026-10-21 report and the 00:21 decision.
- Conventions, entry-gate bullet: the coordinator stops on any worker summary with `NOT_YET` or `Status: BLOCKED`, whatever the runner outcome.
- Conventions, [ASK] bullet: each question leads with `Recommended: <reply>` and a one-line reason.
- Ops recipe, dispatch line: now reads "user-approved 2026-10-21; `cicd.yml:11` has `workflow_dispatch`; Task 8.9 checks workflow state and token scope read-only".
- Phases table, row 10: effort `about 3-4h + CI (backfill)`. The Status column is unchanged, and the table still has 12 rows.
- User decisions (binding): new dated bullet `2026-10-21 00:21` with items (1)-(7).
- U3: wording kept; adds "Sole exception: the Task 9.3 fallback token, only if the dashboard rejects both expressions".
- Deep backfill while armed, Mitigation: now reads "Phase 10 runs the decided 1m backfill (Task 10.3) before the flag goes on".
- Test matrix, e2e row: adds "single-order pause after the first entry".
- Whole-Plan Consistency Sweep: new "Decision delta (2026-10-21 00:21 answers)" list; the "Reconciled" line adds the Phase 10 effort and says the open questions are resolved.
- Unresolved questions: each of the six keeps its Answer line and gains a "Resolved 2026-10-21 00:21" line pointing to the edited task. New last line: "Open questions: none".

### phase-05
- Ratchet [ASK]: the question leads with `Recommended: raise the ceiling`.

### phase-06
- Entry gate: adds `npm --version` exits 0, else NOT_YET with a pointer to the kongming report. No NVM steps were added.

### phase-08
- Gates preamble: adds "lead with the recommended reply and its reason".
- Task 8.3 step 1: the facts name both local env files and note "user pre-agreed 2026-10-21". The question leads with "Recommended: yes" and names both files.
- Task 8.4: the question leads with "Recommended: yes".
- Task 8.9 step 1: the workflow-list probe is replaced by two read-only checks: workflow `.state` must print `active`, and the camping89 scopes must include `repo`. The step also says not to dispatch here, because every run deploys. `dispatch auth ok` is recorded only when both checks pass.

### phase-09
- Gates preamble: recommended-reply lead. The gates line adds the fallback `[USER] token stored`.
- Task 9.3 Facts: adds the 2026-10-21 operator re-check and the "no token unless both expressions are rejected" decision.
- Task 9.3 question: adds the `starts_with()` fallback expression and the line "if you already deployed the rule and 2FA, check and reply". New reply form: `2fa on, both rejected: <errors>`.
- Task 9.3: new Fallback block that runs only if both expressions are rejected. The user creates one token (Zone WAF Edit + Zone Read, pocketquant.xyz only, at most 7 days) and stores it uncommitted at `pocketquant-config/cloudflare/api-token`. The agent creates the rule through the Rulesets API, passing the token on stdin only. Verify was extended to match.
- Tasks 9.8 and 9.9: the questions lead with "Recommended: yes".
- Task 9.14: new step 1. When the fallback ran, the user revokes the token (`token revoked`) and the agent deletes the file. Verify checks the file is gone.

### phase-10
- Frontmatter effort: `about 3-4h + CI (backfill)`.
- Context, deep-backfill bullet: records "Decided 2026-10-21: 1m for the three :EXNESS symbols to the M1 edge; nothing else", with the stored depths.
- Gates preamble: recommended-reply lead. The gates line drops `[ASK] Task 10.3`.
- Task 10.2 Goal: changed from "two [ASK]s" to "Task 10.3 and the Task 10.5 [ASK]".
- Task 10.3: rewritten as a decided task with three steps. Step 1 is an edge probe (a read-only snippet). Step 2 runs the three symbols one at a time with the background facility, using `(E-15)*5/7` days for FX and metals and `E-15` for BTCUSD. Step 3 writes ship-log lines: failures are recorded and arming proceeds, while exit 3 goes to the Failure Protocol. Verify counts the `M1 edge:` line and three `backfill` lines.
- Task 10.5: the question leads with "Recommended: yes" and states the Task 10.3 ship-log lines.
- Risk: new bullet about an aborted run past the edge. The old bullet now says "runs the decided 1m backfill first".

### phase-11
- Context: new 2026-10-21 decision bullet covering the recommended strategy, the single-order run, and D3 = A with no manual order.
- Gates preamble: recommended-reply lead. The 11.8 gate is noted as single-order.
- State record: `paused after first entry` is added to the note lines (not a key).
- Task 11.1: Goal updated. Step 3 treats a `paused after first entry` line as intended paused. New step 4 runs the 11.9 step 0 check once and pauses on a hit. The old step 4 is now step 5. Verify updated.
- Task 11.3: the Goal says the agent recommends. Step 1 adds the recommendation rule. The step 2 question becomes `Recommended: <...>`, says the run is single-order and that SL/TP come from the strategy, and accepts `yes`, another id, or `not now`. Step 4 maps `yes` to the recommended candidate.
- Tasks 11.5 and 11.6: the questions lead with "Recommended: yes" plus a reason.
- Task 11.8: the facts add the single-order line with the strategy SL/TP rules. The question reads "Recommended: yes ... for one order?".
- Task 11.9: new step 0, a background watch of up to 2 h. It polls Mongo `positions` every 60 s, then pauses and records `paused after first entry`. Goal, targets and Verify updated. Step 3 notes when extra trades are possible.
- Task 11.12: the question leads with `Recommended: pause`. Step 2 handles `keep on` by resuming when paused.
- Risk: new bullet saying more than one order is possible while no worker watches.

### phase-12
- Gates preamble: recommended-reply lead. The 12.4 and 12.6 question texts are unchanged; see deviation 4.

## Deviations from the report (each checked)
1. The report's scope check `gh auth status --user camping89 | grep -c "'repo'"` does not work: `gh auth status` has no `--user` flag (`gh auth status --help`, gh 2.101.0). I replaced it with `gh auth status --json hosts --jq '... select(.login=="camping89") | .scopes' | grep -cw repo`. I ran it tonight: it printed 2 with GH_TOKEN set, and the scopes are `gist, read:org, repo, workflow`. The workflow `.state` check printed `active`. Pass is therefore "prints ≥ 1".
2. The single-order watch reads Mongo `positions` (`subscription_id`, `opened_at`; open and closed rows) instead of `GET /subscriptions/<id>/positions`. That route returns open positions only (`strategy_query_service.py:70-71` → `find_open_by_subscription`, `is_closed: False`), so a trade that opened and closed between two polls would be missed. Field names are verified at `position_repository.py:38` and `entities.py:264`.
3. The 11.1 hook is a separate step 4 that runs before the restart check, not a clause inside the old step 4. That way an open position seen after a restart is paused before the stop-and-report.
4. Phases 12.4 and 12.6 and Task 11.11 got only the preamble rule, with no concrete recommended reply. The report gives none, and inventing a weekend-hold or AC6-void recommendation would be a new judgment call.
5. The edge probe tries `(360, 330, 300, 270, 240, 210, 180)` instead of stopping at 240. It also has a `none` outcome that skips the runs, so the decided task cannot dead-end.
6. U3 gains a one-line cross-reference to the fallback token; its wording is otherwise unchanged.
7. The npm open item from the report is not added, because the coordinator states the block is resolved (Node 24.21.0 reinstalled at 00:15). Only the Phase 06 gate was added.

## Verification
- `grep -rc ORCA_RICH_MD` over the plan dir: no file has a match.
- Lines containing `[ASK]`, before → after: 05 3→3, 06 1→1, 07 0→0, 08 6→6, 09 5→5, 10 7→6, 11 11→12, 12 4→4.
  - Phase 10 dropped by 1 because Task 10.3 is no longer an [ASK]. Its title line and its mention in the gates line are gone; the Task 10.2 Goal line still names the 10.5 [ASK].
  - Phase 11 rose by 1 because the new Context bullet names "the 11.3 [ASK]".
  - Every real-money gate is still present: 8.3, 8.4, 9.8, 9.9, 10.5, 11.3, 11.5, 11.6, 11.8, 11.11 and 11.12.
- The plan.md phase table lists 12 rows (01-12), and every Status cell still reads `Pending`.
- The edited files were saved with CRLF on the first write (Windows Python text mode) and converted back to LF. HEAD and the untouched phase files are LF, so git shows no line-ending churn.

## Concerns
- [I] If the dashboard rejects both expressions, the Rulesets API may apply the same plan limits, so the token fallback may not help. Task 9.3 step 2 tells the worker to read the current API docs and to try the `starts_with()` expression too.
- The single-order watch only works while a worker runs: about 2 h in 11.9 step 0, plus each re-run's 11.1 check. After a `no_entry` exit, entries stay on until the next run (24 h), so more than one trade can happen. This is recorded in the Phase 11 Risk section. A hard guarantee would need an in-app "pause after next fill" feature, which is a code change outside this plan.

Status: DONE_WITH_CONCERNS
Summary: All approved edits are applied to plan.md and phases 05, 06 and 08-12; the [ASK] line counts change only in Phase 10 (-1, Task 10.3 decided) and Phase 11 (+1, a Context mention). The report's `gh auth status --user` scope check was replaced with a working command verified tonight.
Concerns/Blockers: the single-order pause holds only while a worker watches; the Cloudflare token fallback may meet the same plan limits as the dashboard.
