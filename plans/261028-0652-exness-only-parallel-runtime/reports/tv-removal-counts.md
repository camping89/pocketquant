# TradingView removal counts

No backup was taken before this delete (D32).
Columns: tracked_symbols symbols bars subscriptions_tv subscription_01a178ef symbols_index_future symbols_cme_calendar

before: 3 3 154768 1 1 3 3
note: step-1 find_one returned BTCUSDT:BINANCE, which has no asset_class/calendar_id (pre-migration doc; from_mongo defaults them); full listing confirmed the keys on all three TRADINGVIEW docs, so the field names are verified.

Delete responses:

```json
{"symbol":"ES1!:TRADINGVIEW","status":"removed","deleted":{"tracked_symbols":1,"subscriptions":1,"symbols":1,"bars":51771,"sync_status":7,"backtest_orders":0,"backtest_trades":0,"backtest_runs":0,"orders":10,"positions":9,"trades":9,"job_history_runs":22228,"cache_keys":9}}
{"symbol":"NQ1!:TRADINGVIEW","status":"removed","deleted":{"tracked_symbols":1,"subscriptions":0,"symbols":1,"bars":51659,"sync_status":7,"backtest_orders":0,"backtest_trades":0,"backtest_runs":0,"orders":0,"positions":0,"trades":0,"job_history_runs":22228,"cache_keys":9}}
{"symbol":"YM1!:TRADINGVIEW","status":"removed","deleted":{"tracked_symbols":1,"subscriptions":0,"symbols":1,"bars":51350,"sync_status":7,"backtest_orders":0,"backtest_trades":0,"backtest_runs":0,"orders":0,"positions":0,"trades":0,"job_history_runs":22226,"cache_keys":9}}
```

after: 0 0 0 0 0 0 0

## D-2 deploy

### Before

```text
label=d2-before ts=2026-10-29T07:45:30Z mem_used_mb=1992 mem_available_mb=1633 swap_used_mb=107 load1=0.73 psi_some_avg10=0.00 oom=0 boot_id=f924e146-dc50-495f-a770-daca73f8fe37
pocketquant-web cpu=0.00% mem=3.898MiB / 3.814GiB
pocketquant-app cpu=2.82% mem=159.7MiB / 3.814GiB
pocketquant-cloudflared cpu=0.43% mem=45.54MiB / 3.814GiB
pocketquant-portainer cpu=0.04% mem=28.12MiB / 3.814GiB
pocketquant-mongodb cpu=0.98% mem=1.413GiB / 3.814GiB
pocketquant-redis cpu=0.73% mem=7.961MiB / 3.814GiB
```

### After

```text
label=d2-after ts=2026-10-29T07:54:47Z mem_used_mb=1817 mem_available_mb=1808 swap_used_mb=107 load1=0.42 psi_some_avg10=0.00 oom=0 boot_id=f924e146-dc50-495f-a770-daca73f8fe37
pocketquant-web cpu=0.00% mem=3.379MiB / 3.814GiB
pocketquant-app cpu=6.06% mem=98.28MiB / 3.814GiB
pocketquant-cloudflared cpu=0.35% mem=45.57MiB / 3.814GiB
pocketquant-portainer cpu=0.00% mem=27.98MiB / 3.814GiB
pocketquant-mongodb cpu=0.77% mem=1.414GiB / 3.814GiB
pocketquant-redis cpu=1.07% mem=7.996MiB / 3.814GiB
```
