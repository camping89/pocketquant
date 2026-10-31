# Paper daily rows

Paper start: 2026-10-30T07:10:22Z, subscription 01a15754-39ed-73e3-921e-df085eb4a786

| UTC day | trader lag ≥ 0.5 s (count) | lag max api / worker / trader (00z 03z 04z 12z) | listener errors | scheduler skip lines | 429 retry day / 7d | terminal 429 order ops | lease.lost | leases | entry_skipped by reason | 1m Exness t0_t5 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Early close (D37)

No UTC day completed after Paper start, so the table has no row. Evidence at 2026-10-31T02:33Z, read from the api, worker and trader logs since 2026-10-30T07:10Z:

```text
signal_latency_1m_exness 26 (t0_t5_ms p50 267, p95 699, max 714)
signal_latency_any 56
listener_errors 0
lease_lost 0
rate_limited_retry 2
error lines 0
label=now ts=2026-10-31T02:33:00Z mem_used_mb=2049 mem_available_mb=1576 swap_used_mb=142 load1=1.07 psi_some_avg10=0.00 oom=0
```

Waived by the owner, not met: 14 consecutive daily rows, weekly rows 1 and 2, and the 7-day job metrics.

Verification verdict: PASS 2026-10-31T02:40Z (owner-accepted early close, D37)
