# Spike: two Exness ticks sessions on one key

Window (UTC): 2026-10-28T13:01:02+00:00 to 2026-10-28T13:36:06+00:00. Rate fraction 0.05. Segments: A 600 s solo, B 900 s with the second session, C 600 s solo.

| Symbol | A p99 quote age s | B p99 quote age s | C p99 quote age s | B own ticks | B own max gap s |
|---|---|---|---|---|---|
| EURUSD:EXNESS | 2.025 | 2.057 | 2.03 | 740 | 3.0 |
| XAUUSD:EXNESS | 1.599 | 1.637 | 1.614 | 1095 | 2.001 |
| BTCUSD:EXNESS | 1.523 | 1.506 | 1.476 | 902 | 2.001 |

| Condition | Value | Pass |
|---|---|---|
| Prod WS failure lines = 0 | 0 | True |
| B p99 quote age <= A + 1.0 s, every symbol | see table | True |
| Own session ticks > 0 and max gap <= 10 s, EURUSD and XAUUSD | see table | True |
| Prod exness.rate_limited lines = 0 | 0 | True |

Spike session own WS lines (record only): 0

Result: PASS
F1: A (hot standby with tick overlap)
