# Live re-arm

Re-armed: 2026-10-31T05:12:51Z, run 41171394802, trader StartedAt 2026-10-31T05:12:51.93186476Z, entries paused, exness subscriptions 0
snapshot before: label=before-rearm ts=2026-10-31T04:12:58Z mem_used_mb=2049 mem_available_mb=1576 swap_used_mb=141 load1=0.47 psi_some_avg10=0.00 oom=0
snapshot after: label=after-rearm ts=2026-10-31T05:15:19Z mem_used_mb=1894 mem_available_mb=1730 swap_used_mb=143 load1=0.66 psi_some_avg10=0.00 oom=0
oom: OOM_OK

Config: `pocketquant-config` commit e7cc081 sets `EXNESS_LIVE_TRADING=true` in `vps/default/.env`. The push also published the earlier local-profile commit 39accb0, with the owner's approval.

Flag per role (container env): `api` false, `worker` false, `trader` true. Compose pins the flag off for `api` and `worker`, so only the trader can build the Exness broker and send an order. The api's `GET /api/v1/admin/safeguards` and the SPA Exness strip therefore show `live_trading` off while the trader is armed. The strip's `Entries paused` chip and its Pause and Resume buttons are correct.

Known follow-ups (not blockers): the SPA strip shows the api's flag, not the trader's; the api-side `BROKER_DISABLED` check in `StrategyCommandService.add_symbol` refuses every exness subscription create on the split runtime, so the create runs through the trader (Substitutions table).

Disarmed: 2026-10-31T06:00Z, run 41174376031 (verify 0 failures), `pocketquant-config` 76acb5e; container env api, worker and trader all `EXNESS_LIVE_TRADING=false`; trader safeguards `"live_trading":false,"entries_paused":true`; OOM_OK. Plan closed (D38).
