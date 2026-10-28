# Compose rolling swap for `api` / `worker` / `trader`

Researcher report, 2026-10-28. The researcher ran the risky claims in a throwaway compose project on Docker Desktop (Engine 29.9.2, Compose v5.6.0, nginx 1.27.5), not on the Linux VPS.

## Bottom line
- **What works:** a 20-line function in the repo's deploy script. It scales the service to 2 with `--no-recreate`, waits until the new container is healthy, then runs `docker stop` and `docker rm` on the old container by the ID captured before scaling.
- **What nginx needs:** `resolver 127.0.0.11 valid=5s`, a variable `proxy_pass`, `proxy_connect_timeout 2s`, and the default `proxy_next_upstream error timeout`.
- **What does the draining:** uvicorn's own SIGTERM behaviour. Healthchecks and Docker DNS do not drain anything.
- **Test result:** in three measured swaps under continuous load, this nginx config returned zero errors.

## Q1. A rolling replacement with Compose v2

**Facts:**
- `--scale` sets how many containers a service runs, `--no-recreate` keeps existing containers as they are, and `--no-deps` does not start linked services ([compose up](https://docs.docker.com/reference/cli/docker/compose/up/)).
- A service with `container_name` cannot scale beyond one container ([services reference](https://docs.docker.com/reference/compose-file/services/)). Today the backend has `container_name: pocketquant-app` (`deploy/compose.prod.yml:60`). The new `api`, `worker` and `trader` services must not set it.
- Container names are `<project>-<service>-<n>`, and the next number is the highest existing number plus one (compose `pkg/compose/service_containers.go`). In prod the names will be `pocketquant-prod-api-N`, with N going up on every deploy.
- `docker compose up -d --no-deps --scale api=2 --no-recreate api` created one new container from the new config and left the old one running (observed).
- **Gotcha 1 (observed):** if a stopped container of the service already exists, the same command restarts that old-config container instead of creating a new one. Remove exited containers first.
- **Gotcha 2 (from source):** scaling down with `--no-recreate` keeps the lowest container numbers, which means it keeps the old container (`pkg/compose/reconcile.go`). Never scale down that way. Stop the old container by its captured ID.
- **docker-rollout** ([wowu/docker-rollout](https://github.com/wowu/docker-rollout), v0.14, 2026-07-12) is a single bash script that runs the same steps. It requires that the service has no `container_name` and no `ports`, and it says it needs a proxy.
- **Compose version on the VPS: unknown.** Docker is installed with `get.docker.com` (`deploy/vps/10-deploy.sh:18-20`, `deploy/vps/one-time/00-server-setup.sh:45-47`), and deploys use `docker compose` (`10-deploy.sh:50`). Check it with `docker compose version`.

**Ranking:** (1) a function in the repo's deploy script: no extra install, version-controlled, and the trader needs custom health handling anyway. (2) docker-rollout pinned to the v0.14 tag URL: acceptable, but its health-based drain hook does nothing for plain nginx (see Q5).

## Q2. Fixed host ports
- **Observed:** a second container publishing the same host port fails ("driver failed programming external connectivity"). Two replicas cannot share a fixed host port.
- **Fact:** `app` publishes no host port; it listens on 41921 inside the network only (`compose.prod.yml:53-91`). `web` also publishes none (`compose.prod.yml:8`). Only the loopback ports of mongodb, redis and portainer are published (`:99-100, 126-127, 148-149`). Nothing here blocks scaling.

## Q3. `stop_grace_period` and signals
- **Fact:** `stop_grace_period` is how long Compose waits after the stop signal before SIGKILL (default 10 s); `stop_signal` defaults to SIGTERM ([services reference](https://docs.docker.com/reference/compose-file/services/)). Compose writes it into the container's `StopTimeout` (`pkg/compose/create.go:381`; observed `StopTimeout=7` for `7s`), so a plain `docker stop <id>` honours it too ([docker stop](https://docs.docker.com/reference/cli/docker/container/stop/)).
- **Fact:** `deploy/Dockerfile:63` uses exec-form `CMD` with no `ENTRYPOINT`; `compose.prod.yml:64` overrides it with an exec-form list. No `init:` and no tini.
- **Inference:** uvicorn is PID 1 and receives SIGTERM directly. uvicorn installs its own SIGTERM handler (uvicorn 0.40.0 `server.py`, locked at `uv.lock:1124`), so the PID 1 default-signal rule does not block shutdown.
- **Fact (uvicorn 0.40.0 source):**
  - Lifespan startup runs before the socket is bound, so the port refuses connections while startup runs.
  - On SIGTERM, uvicorn stops accepting connections, then waits for open connections up to `timeout_graceful_shutdown`, which defaults to `None` (forever). Only then does lifespan shutdown run.
  - Open SSE streams therefore hold shutdown until SIGKILL.
- **Recommendation:** `api` gets `--timeout-graceful-shutdown 10` and `stop_grace_period: 30s`. `trader` gets a grace period longer than its drain plus broker disconnect (inference, not measured).

## Q4. nginx re-resolving the service name
- **Docs:** a variable `proxy_pass` host is resolved with the `resolver`; several addresses are used round-robin ([proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)). `resolver` caches by TTL, and `valid=` overrides it ([resolver](https://nginx.org/en/docs/http/ngx_http_core_module.html#resolver)). Docker's embedded DNS is `127.0.0.11` ([Docker networking](https://docs.docker.com/engine/network/)).
- **Docs:** `proxy_next_upstream` defaults to `error timeout`, and it moves to the next server only if nothing was sent to the client yet. Inference: a refused connection happens before anything is sent, so POST requests also fail over.
- **Fact (observed):** a variable `proxy_pass` with no URI part passes the request URI unchanged, the same as today's `proxy_pass http://app:41921;` (`web/nginx.conf:26`). Do not add a path to the variable.
- **Trap (observed):** if any static `proxy_pass http://api:41921` or an upstream with that name exists anywhere in the config, the variable form matches that group and never re-resolves.
- **Observed:** a static `proxy_pass` resolves once at nginx start and kept hitting the old IP after the swap. Today's `web/nginx.conf:26` breaks under a rolling swap.
- **Alternative:** nginx 1.27.3+ supports `server api:41921 resolve;` in an upstream with a `zone` ([upstream resolve](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#resolve)); the web image is 1.27.5. It needed `max_fails=0` to reach zero errors, so it ranks second.

## Q5. Draining the old container before it stops
- **Observed:** Docker DNS adds the new container's A record when it starts, about 7 s before it is healthy. It removes the old record only when the container exits, not on SIGTERM. Health status does not affect DNS.
- **Observed:** without a connect timeout, nginx hung about 3 s on a removed IP. With `proxy_connect_timeout 1s` there were zero errors.
- **Recipe that held up in testing:**
  1. The new container is in DNS while it starts but refuses connections until lifespan startup finishes, and nginx moves to the next server on `error`.
  2. Only after the new container is healthy, run `docker stop` on the old one. uvicorn closes its listener at once, so new connections go to the new container. In-flight requests finish within `--timeout-graceful-shutdown`.
  3. After the old container exits, its record drops. nginx's cached copy expires within `valid=5s`, and any connect to the dead IP fails within `proxy_connect_timeout 2s` and moves on.
  4. Inference: SSE streams on the old container are cut at the graceful timeout, and the browser's EventSource reconnects through nginx to the new container.

## Recommended recipe

nginx, replacing `web/nginx.conf:26`:
```nginx
resolver 127.0.0.11 valid=5s ipv6=off;
location /api/ {
    set $api_upstream http://api:41921;   # no URI part; no static proxy_pass to api anywhere
    proxy_pass $api_upstream;
    proxy_connect_timeout 2s;
    proxy_next_upstream error timeout;    # default, kept explicit
    # ...existing headers / SSE settings unchanged
}
```

Deploy function for `deploy/vps/10-deploy.sh`:
```bash
dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }
roll() {  # roll <service> <health-timeout-s>
  local svc=$1 t=${2:-120} old new i
  docker ps -aq --filter label=com.docker.compose.project=pocketquant-prod \
    --filter label=com.docker.compose.service="$svc" \
    --filter status=exited --filter status=created | xargs -r docker rm
  old=$(dc ps -q "$svc")
  [ -z "$old" ] && { dc up -d --no-deps "$svc"; return; }
  dc up -d --no-deps --no-recreate --scale "$svc=2" "$svc"
  new=$(dc ps -q "$svc" | grep -vxF "$old")
  for i in $(seq "$t"); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$new")" = healthy ] && break; sleep 1
  done
  if [ "$(docker inspect -f '{{.State.Health.Status}}' "$new")" != healthy ]; then
    docker logs --tail 50 "$new"; docker stop "$new"; docker rm "$new"; return 1
  fi
  docker stop "$old" && docker rm "$old"   # honours stop_grace_period
}
roll api 120; roll worker 120; roll trader 180
dc up -d --remove-orphans   # inference: a no-op for rolled services
```

- **api and worker:** use the function as written. `api` needs `--timeout-graceful-shutdown 10` and `stop_grace_period: 30s`. `worker` has no inbound traffic; its only overlap risk is two workers running jobs at once, which the worker lease prevents.
- **trader:** the same Docker sequence (start new, wait healthy, SIGTERM old) is safe only if "healthy" means "standby, not trading" and the new trader takes a lease that the old one releases during shutdown. Design inference, not verified.
- **Scripts that use the fixed name `pocketquant-app`** (fact): `10-deploy.sh:72` and `11-verify.sh:145, 157, 171, 188, 198, 250, 255, 266, 306, 318`. Replace with `$(dc ps -q api)`.

## Limitations
- All tests ran on Docker Desktop, not the Ubuntu VPS; DNS-removal timing may differ there.
- The backend in the test was simulated (nginx with a SIGTERM trap and a delayed start), not the real uvicorn app or real SSE.
- Several Compose claims come from main-branch source, which may differ from the VPS release.

## Unresolved
1. The Compose and Engine versions on the VPS are unknown. Run `docker compose version`.
2. The `api` lifespan runs migrations while the old `api` still serves. Every migration must be backward-compatible (expand, then contract) for the overlap.
3. The trader lease and standby-health design must exist before the trader overlap is safe.
4. `web` keeps a fixed `container_name` and is recreated on every deploy because its image tag changes, which leaves a short cloudflared→web gap this recipe does not cover.
5. The first deploy that renames `app` to `api`/`worker`/`trader` is a one-time cutover: `--remove-orphans` removes `pocketquant-app`. That transition needs its own sequence.
6. The TTL that Docker DNS returns is unverified. Set `valid=` explicitly in nginx regardless.
