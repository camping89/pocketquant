# Machine baseline

D25 measurements on the prod VPS, record only (D31: the only machine stop is the OOM rule in plan.md Conventions). Warm-up seconds: n/a (no standby trader exists yet).

oom_baseline=f924e146-dc50-495f-a770-daca73f8fe37 0

## Idle, before the loop-lag probe

```text
label=baseline ts=2026-10-28T14:42:16Z mem_used_mb=2114 mem_available_mb=1507 swap_used_mb=104 load1=0.81 psi_some_avg10=0.00 oom=0 boot_id=f924e146-dc50-495f-a770-daca73f8fe37
pocketquant-web cpu=0.00% mem=8.992MiB / 3.814GiB
pocketquant-app cpu=11.99% mem=432.2MiB / 3.814GiB
pocketquant-cloudflared cpu=0.47% mem=46.18MiB / 3.814GiB
pocketquant-portainer cpu=0.00% mem=32.15MiB / 3.814GiB
pocketquant-mongodb cpu=1.10% mem=1.325GiB / 3.814GiB
pocketquant-redis cpu=2.80% mem=8.629MiB / 3.814GiB
```

## D-1 deploy (single app)

### Before

```text
label=d1-before ts=2026-10-29T06:30:41Z mem_used_mb=2078 mem_available_mb=1546 swap_used_mb=106 load1=0.66 psi_some_avg10=0.00 oom=0 boot_id=f924e146-dc50-495f-a770-daca73f8fe37
pocketquant-web cpu=0.05% mem=9.672MiB / 3.814GiB
pocketquant-app cpu=11.55% mem=432.9MiB / 3.814GiB
pocketquant-cloudflared cpu=0.64% mem=46.43MiB / 3.814GiB
pocketquant-portainer cpu=0.00% mem=30.27MiB / 3.814GiB
pocketquant-mongodb cpu=1.55% mem=1.331GiB / 3.814GiB
pocketquant-redis cpu=6.88% mem=9.449MiB / 3.814GiB
```

### After

```text
label=d1-after ts=2026-10-29T06:42:17Z mem_used_mb=1806 mem_available_mb=1818 swap_used_mb=108 load1=0.75 psi_some_avg10=0.00 oom=0 boot_id=f924e146-dc50-495f-a770-daca73f8fe37
pocketquant-web cpu=0.00% mem=3.895MiB / 3.814GiB
pocketquant-app cpu=3.13% mem=156.7MiB / 3.814GiB
pocketquant-cloudflared cpu=0.39% mem=45.48MiB / 3.814GiB
pocketquant-portainer cpu=0.00% mem=27.75MiB / 3.814GiB
pocketquant-mongodb cpu=0.76% mem=1.335GiB / 3.814GiB
pocketquant-redis cpu=1.56% mem=7.949MiB / 3.814GiB
event_loop_lag_max_s=0.016
```
