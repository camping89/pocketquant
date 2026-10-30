# Machine limits (2 vCPU / 3 GB VPS, D25)

| row | UTC | source | snapshot before | snapshot after | peak RSS MiB / CPU% per container (during the roll) | loop lag max s api/worker/trader (old trader) | warm-up s | takeover_ms | handover_gap_ms | OOM check |
|---|---|---|---|---|---|---|---|---|---|---|
| s2026-10-30 | 2026-10-30T07:10:49Z | day snapshot | used 1911 / avail 1713 / swap 130 MiB, load1 0.82, psi 0.00, oom=0 | n/a | n/a | n/a | n/a | n/a | n/a | OOM_OK |
| h1 | 2026-10-30T06:44:27Z | handover 1 (image) | used 1963 / avail 1662 / swap 118 MiB, load1 1.10, psi 0.00, oom=0 | used 1931 / avail 1694 / swap 130 MiB, load1 2.86, psi 0.00, oom=0 | pocketquant-mongodb 1546/144.0; pocketquant-prod-trader-2 123/101.9; pocketquant-prod-trader-1 101/57.6; pocketquant-prod-api-1 104/11.2; pocketquant-prod-api-2 100/95.1; pocketquant-prod-worker-1 99/47.3; pocketquant-prod-worker-2 97/96.8; pocketquant-cloudflared 55/31.0; pocketquant-portainer 26/0.1; pocketquant-web 10/24.5; pocketquant-redis 8/15.4 | <0.25/<0.25/<0.25 (0.821) | 12 | 58 | 499 | capture OOM_OK; now OOM_OK |
