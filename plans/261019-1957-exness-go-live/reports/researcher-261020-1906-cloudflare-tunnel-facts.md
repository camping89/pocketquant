# Cloudflare Tunnel rollout facts (2026-10-20)

**Bottom line:** the plan works as written. Run cloudflared in the same compose file and point it at `http://web:80`. Switch www first, then @, by deleting each DNS record and adding the matching tunnel route straight away. Remove the web `ports:` only after both hostnames are verified. Fix `deploy/vps/11-verify.sh` in the same change, because it checks host :80.

The SSE endpoints have one real risk. They send nothing while prices are unchanged. The Cloudflare edge drops a response that stays silent past its read timeout. That is true today and stays true through the tunnel.

Labels: **[V]** means checked against a source or repo file. **[I]** means my inference.

## 1. Compose service

```yaml
  cloudflared:
    image: cloudflare/cloudflared:2026.10.2
    container_name: pocketquant-cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN}
      TUNNEL_METRICS: 127.0.0.1:60123
    depends_on:
      web:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "cloudflared", "tunnel", "--metrics", "127.0.0.1:60123", "ready"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    logging:
      driver: json-file
      options: { max-size: "5m", max-file: "3" }
```

**Image and version pin**
- [V] The image is `cloudflare/cloudflared` on Docker Hub. Tags use the form `YYYY.MM.patch` and are multi-arch for amd64 and arm64. `latest` currently points to 2026.10.2.
- [V] Releases come often. The last five shipped between 2026-09-24 and 2026-10-20. Pin an exact tag rather than `latest`.

**Image internals**
- [V] The runtime base is `distroless/base-debian13:nonroot`, running as user 65532.
- [V] The image sets `ENTRYPOINT ["cloudflared","--no-autoupdate"]` and `CMD ["version"]`. Your `command:` replaces `CMD`.
- [I] The second `--no-autoupdate` in the command is redundant but harmless.

**Token**
- [V] `TUNNEL_TOKEN` is the documented env var for `--token`. It works for remotely-managed tunnels only.
- [V] `TUNNEL_TOKEN_FILE` also works, from version 2025.4.0. It keeps the token out of `docker inspect`.

**Healthcheck**
- [V] `cloudflared tunnel ready` exists. It was merged in PR #1135 on 2024-11-18.
- [V] The command sends a GET to `http://<metrics>/ready`. It returns an error unless the status is 200.
- [V] It also fails with "--metrics has to be provided" if the metrics address is not set. So the metrics address is required.
- [V] The image has no shell, curl or wget. The exec-form `["CMD", ...]` above is the only kind of healthcheck that can work.
- [V] Inside containers, metrics bind to `0.0.0.0:20241-20245` by default. That exposes `/metrics` and `/config` to other containers. Binding to 127.0.0.1 avoids this, and the healthcheck runs in the same network namespace.
- [I] On why the flag appears twice: env-only setups with a bare `tunnel ready` are reported to work, but I did not confirm in source that `IsSet` honours the env var. Passing `--metrics` explicitly removes that doubt.

**Restart policy**
- [I] Use `unless-stopped`, to match the other services in the file.

## 2. Dashboard paths and payment

**Where tunnels live**
- [V] Since 2026-02-20, tunnels are managed in the main dashboard under **Networking > Tunnels**.
- [V] On 2026-10-12, the Zero Trust "Networks" menu items were removed in favour of the Networking menu. That change was rolled out to all customers.
- [I] The old path "Zero Trust > Networks > Tunnels" in older guides no longer exists.

**Adding a route**
- [V] Open **Networking > Tunnels**, pick the tunnel, then go to the **Routes** tab. Select **Add route**, then **Published application**.
- [V] Enter the subdomain and domain, then the Service URL (`http://web:80`), and select **Save**.
- [V] The current name is "Published application route". "Public hostname" is the older name for the same thing.

**Payment card**
- [V] Every account includes 1,000 tunnels. The 2026 changelogs mention payment only when buying more tunnels.
- [V] Zero Trust *Free plan* onboarding has historically required a payment method, even though it charges nothing. Cloudflare staff and community threads confirm this, as recently as 2026.
- [I] Tunnel management in the main dashboard probably needs no Zero Trust onboarding or card. I found no official statement saying so. The user will find out at the first step.

## 3. Hostname conflicts and switching @ and www

**Conflicts**
- [V] The dashboard does not overwrite an existing record. It rejects the route with "An A, AAAA, or CNAME record with that host already exists".
- [V] The official fix is to delete the existing DNS record, or choose another hostname.
- [V] The CLI flag `--overwrite-dns` needs `cloudflared tunnel login` (cert.pem), so it is not usable from the dashboard alone.
- [V] Saving a route creates a proxied CNAME to `<UUID>.cfargotunnel.com`.

**Apex**
- [V] A CNAME at the apex (@) is legal on Cloudflare. CNAME flattening is on by default at the apex on all plans.
- [V] Proxied records return Cloudflare anycast IPs both before and after the switch.
- [I] Because of that, visitors' DNS caches do not matter. The only outage is the seconds between deleting a record and saving its route.

**Switch order (fastest, smallest blast radius)**

1. Confirm tunnel-test.pocketquant.xyz first. Check the SPA deep links (`/strategies`, `/monitor`), `/api/...`, and one SSE stream held for several minutes.
2. Switch www. In **DNS > Records**, delete `www`. Then in **Tunnels > Routes**, add the `www` route to `http://web:80`. Test it.
3. Switch @ the same way. Delete the `@` A record, then add the route with the subdomain left empty. Test it.
4. Keep the web `ports: 80` until both hostnames have run cleanly. This keeps rollback trivial: delete the CNAME and recreate the proxied A record to the VPS IP.
5. Remove `ports:` from web and recreate only that service.

Inferred risks for this sequence:
- [I] A resolver that queries during the gap may cache NXDOMAIN for the zone's negative TTL. With a gap of a few seconds this risk is small, but not zero. Do it at low traffic.
- [I] Editing the existing record into a CNAME in the DNS page does not avoid the gap. The tunnel would still lack the ingress rule, and adding the route afterwards hits the same conflict error.

## 4. Removing a route does not delete its DNS record

- [V] Removing a route leaves the CNAME in place. "The DNS record and the tunnel are independent."
- [V] The leftover record keeps answering with an error page (1033 or 1016) until it is deleted by hand. It also blocks re-adding that hostname. This has been an open request since 2021 (cloudflared issue #354).
- Action: after the cutover, delete the route for `tunnel-test` **and** its CNAME in DNS > Records.

## 5. SSL mode

- [V] Cloudflare's tunnel docs say "The zone SSL/TLS mode is separate from the Tunnel route."
- [V] They also say "The connection between Cloudflare and cloudflared is encrypted independently of the zone SSL/TLS mode."
- [V] And: "Automatic, Flexible, Full, and Full (strict) do not change the local HTTP connection." Full (strict) is compatible with tunnel public hostnames.
- [I] No change is required for the cutover. Once no proxied record points at the VPS IP directly, you can set the mode to Full (strict). That only affects non-tunnel records, and it stops a future stray A record from being served over plain HTTP.
- [I] Before switching modes, check whether other proxied A records (for example a portainer subdomain) still point at the VPS. Full (strict) would break any that have no TLS on port 443.

## 6. Docker ports, ufw, and the compose network

**ufw bypass**
- [V] Docker's docs say published ports bypass ufw. Traffic is redirected in the `nat` table before it reaches ufw's INPUT chain.
- [V] Without a host IP, a published port binds to `0.0.0.0` and `[::]`.

**Reaching `web` without a published port**
- [V] Compose attaches every service in the file to `<project>_default`, here `pocketquant-prod_default`. Services resolve each other by service name.
- [V] Containers on the same network reach all container ports without `ports:`.
- [I] So nothing else is needed for the tunnel to reach `web`: add `cloudflared` to the same file with no `networks:` key. An external network is needed only if cloudflared runs from a different compose project.

**Repo findings outside the tunnel itself**
- [V] `mongodb` (`${MONGO_PORT}:27017`), `redis` (`${REDIS_PORT}:6379`) and `portainer` (`${PORTAINER_PORT}:9000`) also publish host ports.
- [I] Unless their `.env` values bind to `127.0.0.1` (not checked, because that file lives in pocketquant-config), ufw does not protect them.
- [V] `deploy/vps/11-verify.sh` curls `http://localhost:${WEB_PORT}` (section 3b) and checks with `ss` that :80 is listening (section 8). Both will FAIL after `ports:` is removed. Update the script in the same change. One option is `docker exec pocketquant-web curl -fsS http://localhost/...`, as the app checks already do.

## 7. WebSockets and SSE through the tunnel

**Buffering**
- [V] Cloudflare's docs say "Proxied traffic through Cloudflare Tunnel is buffered by default". The exception is a response with `Content-Type: text/event-stream`, which cloudflared streams as it arrives.
- [V] Both SSE routes set `media_type="text/event-stream"` and `X-Accel-Buffering: no` (`market_data.py`, `market_data_quotes.py`).
- [V] nginx `/api/` already sets `proxy_buffering off`, `proxy_cache off` and `proxy_read_timeout 86400s`. `gzip_types` does not include `text/event-stream`.
- [I] Buffering should therefore not be a problem. Older reports of tunnel SSE buffering (issue #199 and community threads) involved responses without that content type.

**Timeouts**
- [V] The edge proxy read timeout is 125 s and returns a 524. Only Enterprise can change it.
- [V] A Cloudflare support test showed SSE lasting 30+ minutes, failing only when the server sent nothing for about 100 s.
- [V] Long-lived tunnel connections also drop during cloudflared or edge maintenance.
- [V] Both generators `yield` only when a value changes, and send no heartbeat.
- [I] When markets are closed or a symbol is quiet, streams will be cut at about 100-125 s. This already happens under the current proxied setup, so the tunnel does not cause it. The fix is to send an SSE comment line (`: ping\n\n`) every 15-30 s. The browser's EventSource reconnects on its own, so the impact is reconnect churn, not data loss.

**WebSockets**
- [V] Supported on all plans. They need the zone's WebSockets setting enabled, which is the default, and are subject to the same idle limits.
- [I] The SPA does not need WebSockets through the tunnel. The app's broker WS feed is outbound from the VPS, so the tunnel does not touch it.

## Limitations

- I did not observe the 2026 Routes UI directly. Whether it now offers an overwrite prompt comes only from docs and community posts.
- I did not verify in cloudflared source that the `TUNNEL_METRICS` env var alone satisfies `tunnel ready`. That is why the healthcheck passes the flag explicitly.
- I did not check `.env` in pocketquant-config for the port bind addresses, or which other DNS records exist in the zone.

## Unresolved questions

1. Does the main-dashboard Tunnels page ask for a card or Zero Trust onboarding on this account? The user will see this at the first step.
2. Do other proxied records point at the VPS IP? This decides whether moving to Full (strict) is safe.
3. Are `MONGO_PORT`, `REDIS_PORT` and `PORTAINER_PORT` bound to 127.0.0.1 in the prod `.env`? If not, they are public despite ufw.

## Sources

- [Tunnel in main dashboard (changelog 2026-02-20)](https://developers.cloudflare.com/changelog/2026-02-20-tunnel-core-dashboard)
- [Tunnel changelog 2026](https://developers.cloudflare.com/changelog/product/tunnel/)
- [Cloudflare One changelog, unified navigation 2026-10-12](https://developers.cloudflare.com/changelog/product-group/cloudflare-one/)
- [Add routes](https://developers.cloudflare.com/cloudflare-one/networks/routes/add-routes/)
- [Run parameters](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/cloudflared-parameters/run-parameters/)
- [Tunnel metrics](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/monitor-tunnels/metrics/)
- [Origin parameters](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/cloudflared-parameters/origin-parameters/)
- [Tunnel DNS records](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/)
- [Tunnel common errors](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/troubleshoot-tunnels/common-errors/)
- [HTTPS origins and SSL modes](https://developers.cloudflare.com/tunnel/troubleshooting/https-origins/)
- [Connection limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/)
- [CNAME flattening](https://developers.cloudflare.com/dns/cname-flattening)
- [cloudflared PR #1135 (tunnel ready)](https://github.com/cloudflare/cloudflared/pull/1135)
- [cloudflared Dockerfile](https://github.com/cloudflare/cloudflared/blob/master/Dockerfile)
- [cloudflared releases](https://github.com/cloudflare/cloudflared/releases)
- [Docker Hub tags](https://hub.docker.com/r/cloudflare/cloudflared/tags)
- [cloudflared issue #354 (DNS not cleaned)](https://github.com/cloudflare/cloudflared/issues/354)
- [cloudflared issue #199 (SSE buffering)](https://github.com/cloudflare/cloudflared/issues/199)
- [Community: SSE and 524](https://community.cloudflare.com/t/are-server-sent-events-sse-supported-or-will-they-trigger-http-524-timeouts/499621)
- [Community: Zero Trust free needs a card](https://community.cloudflare.com/t/free-credit-card-required/399917)
- [dockerhomelab compose example](https://dockerhomelab.com/posts/how-to-expose-docker-services-with-cloudflare-tunnel/)
- [ProphetSe7en healthcheck wrapper](https://github.com/ProphetSe7en/cloudflare-tunnel)
- [Docker: packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
- [Docker: port publishing](https://docs.docker.com/engine/network/port-publishing/)
- [Compose networking](https://docs.docker.com/compose/how-tos/networking/)

Status: DONE_WITH_CONCERNS
Summary: All seven questions are answered with sources, and each claim is marked as verified or inferred. The cutover plan is sound if it uses delete-then-add per hostname and removes ports last.
Concerns: 11-verify.sh will fail once host :80 is removed. The SSE endpoints have no heartbeat. mongo, redis and portainer may be publicly exposed despite ufw.
