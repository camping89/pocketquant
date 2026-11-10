# Phase 04: Track B release to master and post-deploy checks

## Entry gate (2026-11-09 15:42Z)

- EG (1) `git status --porcelain -- src web deploy tests scripts docs .github`: empty.
- EG (2): `synced` (HEAD `0c672ff0` = `origin/develop`).
- EG (3): `reports/phase-03-hitnrun2-strategy.md` last line `Result: PASS`.
- EG (4) `git diff --stat origin/master origin/develop -- src tests | tail -1`: ` 4 files changed, 522 insertions(+), 1 deletion(-)`.
- KEY, LIVECHK: `trader_live=False`.

## Task 04.1 — Pre-release record

prev_master=684e2ab
free_before=Mem:            3905        2512         431           1         961        1124
commits_to_release=9

- Develop CI for the feature commit: run `42646391531` `completed success 150ceb32`; the later commit `0c672ff0` touches only `plans/**` and triggers no CI.

## Task 04.2 — [ASK] release

- Question intent: release hitnrun2 to prod by pushing develop:master (one strategy file, registry entry and tests; 9 commits; no schema, route or config change; no subscription; live off; trader restart warms up the three paper subscriptions; rollback re-roll sha-684e2ab). Asked via the Orca coordinator (msg_3234fdb8af65), led with `Recommended: yes`.
- Answer (msg_9cb7afb024ec, 2026-11-10 00:20Z): yes.

release_ask=yes

## Task 04.3 — Release push and master run

pushed_at=2026-11-10T00:21:15Z

- Push: `684e2ab1..0c672ff0  master -> origin/master`; `released`.
- Master run `42727652717`: `completed success 0c672ff023487c6a7a06dd5cb9d4cdcece67350e`, equal to `git rev-parse origin/develop`.

## Task 04.4 — Post-deploy checks

prod_has_hitnrun2=yes codes=hitnrun2,triple_screen

- LIVECHK (new container `pocketquant-prod-trader-20`): `trader_live=False`.
- Trader log since `pushed_at`: 80 lines; `grep -c -E "reconcile\.(failed|load_failed|unknown_template)"` prints `0`; `grep -c -i -E "error|exception|traceback"` prints `0`.

existing_sub id=01a19bbf-0b3a-70e3-903e-f93e361acbf8 intervals_key=15m,1h,4h state=running/running broker=paper parameters=[('entry_type', 'stop'), ('exit_mode', 'strategy')]
existing_sub id=01a19bbf-9788-7487-8c7e-9f110ed8c595 intervals_key=1h,4h,1d state=running/running broker=paper parameters=[('entry_type', 'stop'), ('exit_mode', 'strategy')]
existing_sub id=01a19bc0-26ec-76ba-b83e-edeb84f021d4 intervals_key=5m,15m,1h state=running/running broker=paper parameters=[('entry_type', 'stop'), ('exit_mode', 'strategy')]

- SUBSDIFF: `subs_unchanged`.

free_after=Mem:            3905        2142         670           1        1092        1494

- `.cache/ssh/vps_key` removed.
- Advisory note: the release was approved by the owner and is reversible by re-rolling `sha-684e2ab`; no Verify failed, so `kongming` was not spawned.

Result: PASS
