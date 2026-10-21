# Exness go-live ship log

Deploy A: 2026-10-21T13:48:45Z, app StartedAt 2026-10-21T13:53:07.880224002Z, dispatch auth ok, data ports loopback, just tunnel ok, live trading off
SSE pocketquant.xyz: 137 data lines at 2026-10-21T17:04:48Z
Break-glass drill: pause over SSH ok at 2026-10-21T17:05:05Z
Flood check: 1 000, 299 200 (no 429; the 300 requests took about 4 min), pause 200 at 2026-10-21T17:09:14Z
Deploy B: 2026-10-21T17:57:28Z, app StartedAt 2026-10-21T17:00:45.780720968Z, admin token rotated
M1 edge: 360 calendar days
backfill XAUUSD:EXNESS 1m days 246: fetched=354240 inserted=354240 total_bars=354268
backfill EURUSD:EXNESS 1m skipped: user decision 2026-10-22, not needed now
backfill BTCUSD:EXNESS 1m skipped: user decision 2026-10-22, not needed now
Deploy C (armed): 2026-10-21T18:49:23Z, app StartedAt 2026-10-21T18:46:57.827862924Z, entries paused across the restart, every subscription paper
