# Phase 15 report: D-2 release (PASS)

Resumed 2026-11-02 08:09Z after the plan fix that counts the D-1 deploy day (commit 36e43585). The first attempt (06:20Z) stopped at Task 15.1 with `days=0` and ran no prod write.

## Entry gate (2026-11-02 08:09Z)

- EG (1) git status on src web deploy tests scripts docs .github: empty.
- EG (2) HEAD = origin/develop = 36e435858597fd7e5d549e8b1d2d11ea75599772.
- EG (3) phase-14 report ends `Result: PASS`.
- Line 2: `12`.
- Line 3: `33` commits in origin/master..origin/develop.
- Line 4: `midnight_passed=yes` (d1_deployed_at=2026-11-01T14:50:40Z).
- Line 5: `subs=4 stopped=4 exness=0`.
- Line 6: AGNOSTIC `0`.
- Line 7: LIVECHK `trader_live=False`.

## Task 15.1 (2026-11-02 08:10Z)

```
symbols=3 days=3 non_cascade=0 late=0 repair_1d=0
```

## Task 15.2 (2026-11-02 08:10Z)

- `subs_legacy=4`
- `indexes=_id_,ix_subscriptions_dedup_triple,ix_subscriptions_strategy_code`
- `prev_master=ba6cba9`
- free_before: `Mem:            3905        2130         309           1        1465        1493`

## Pre-release counsel and pre-check (2026-11-02 08:13Z)

kongming: GO for Task 15.3 and the migration and push. It added one read-only pre-check. It also said that if the Task 15.6 index list still shows `dedup_triple` (an old-code restart recreated the index before the roll), the fix is to re-run MIGRATE and then the 15.6 script again.

Pre-check output:

```
7.0.45
019ebe98-209c-71f2-af3d-981810e2d783 hitnrun2 BTCUSDT:BINANCE '1m' datetime False
019f0e9b-b206-76b6-b14f-23ab958c1c4e engulfing BTCUSDT:BINANCE '1m' datetime False
01a15754-39ed-73e3-921e-df085eb4a786 hitnrun2 XAUUSD:EXNESS '1m' datetime False
01a15754-3ab5-7258-b46b-ad98e1f3471f engulfing EURUSD:EXNESS '1h' datetime False
```

Backup of all 4 subscription documents and the index list: local `.cache/subs-backup-261102.json` (git-ignored).

## Task 15.3 owner ASK

Sent to the coordinator at 08:14Z with `Recommended: yes`.

Owner reply via the coordinator (08:43Z): `yes`.

## Task 15.4 MIGRATE runs

Run 1, 2026-11-02 08:43:18Z:

```
subs_modified=4 missing=0
indexes=_id_,ix_subscriptions_strategy_code
```

## Task 15.5 release push

Pre-push MIGRATE, 2026-11-02 08:43:32Z:

```
subs_modified=0 missing=0
indexes=_id_,ix_subscriptions_strategy_code
```

Pre-push LIVECHK: `trader_live=False`.

- `d2_pushed_at=2026-11-02T08:43:47Z`
- Push printed `released` (origin/master = origin/develop = 36e435858597fd7e5d549e8b1d2d11ea75599772).
- Master run id `41415187720`.
- Master run `41415187720`: `completed success 36e435858597fd7e5d549e8b1d2d11ea75599772` (equals origin/develop).

## Task 15.6 post-deploy checks (2026-11-02 08:51Z)

```
indexes=_id_,ix_subscriptions_dedup_intervals,ix_subscriptions_strategy_code
params=8 entry_type=market exit_mode=sl_tp
rows=4 one_interval=4
read_without_token=401
```

- LIVECHK on the new trader: `trader_live=False`.
- Trader log since `d2_pushed_at` (74 lines): `reconcile.failed` count `0`, `reconcile.unknown_template` count `4` (the 4 legacy subscriptions use the removed `hitnrun2` and `engulfing` codes).
- free_after: `Mem:            3905        2121         410           1        1374        1505`
- `.cache/ssh/vps_key` removed.

The old index was not recreated between the migration and the roll, so no extra MIGRATE run was needed.

Result: PASS
