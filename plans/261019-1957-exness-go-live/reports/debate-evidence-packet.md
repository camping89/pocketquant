# Debate evidence packet: Exness go-live plan

Date: 2026-10-20. Plan: `plans/261019-1957-exness-go-live/` (10 phases in run order; cooked phase by phase with `eve-cook-plan` in strict numeric order). [V] means verified in source, a probe or docs. [I] means inference.

## Binding user decisions (do not reverse)
- One plan only. Phase file order equals execution order.
- Capital is at most 250 USD and trades are 0.01 lot. Account leverage is 1:1000 (`EXNESS_LEVERAGE=1000`).
- `EXNESS_DAILY_LOSS_CAP=25` is in account currency (realized PnL per UTC day). `EXNESS_MAX_LOTS=0.01`. `EXNESS_RISK_PER_TRADE=0.10` is a fraction (10%).
- The pause blocks entries only. It is global and in process, and it resets on restart. `GET /admin/safeguards` is public; pause and resume need the admin token. Exits are never gated.
- Keep live trading on and use pause to disable it (D4).
- TLS: Cloudflare Tunnel, rolled out in three rounds with no downtime.
- The SPA follows the approved mockup:
  - a PAPER/LIVE badge from `broker`;
  - a RUNNING/STARTING/STOPPED pill that replaces `status-dot.tsx`;
  - an Exness strip with Pause (one click), Resume (confirm) and an ENTRIES PAUSED badge;
  - a confirm on LIVE Start; paper Start is one click;
  - Delete in the card footer and one `.btn-danger` class;
  - `moneyHint` with one chip per group and a `title` on every mutating button;
  - the dead UI files are deleted.
- The light log is `unexpected_count`/`unexpected_ranges` on the 1m `integrity.issues_found` WARNING.
- The CLAUDE.md KISS rules apply: three files per flow at most, two hops at most, a second real caller before any new abstraction, and dead code deleted in the same change.

## Code facts (scout, 2026-10-20)
- [V] Neither hitnrun2 nor engulfing moves its SL after entry. The SL is set once at signal time (`hitnrun2_strategy_service.py:151`, `engulfing_strategy_service.py:170`). No modify-SL path exists in the Exness or paper adapter. So `trades.sl_price` minus entry is the entry stop distance.
- [V] `margin_percent` is used only in test fixtures (`"1"`), and no repo doc gives its unit. [I] It is MT5-style, so 1 means 1%.
- [V] A prod redeploy (master push) restarts the app. Running subscriptions come back through reconcile (5 s), because their docs persist in Mongo. Strategy buffers are cleared on start, and nothing preloads history. Warmup takes:
  - hitnrun2 XAUUSD 1m: 480 closed bars, about 8 open-market hours. [V] The guard is at `hitnrun2_strategy_service.py:93`. Earlier advice said "minutes", which is wrong.
  - engulfing EURUSD 1h: 20 bars, about 21 open hours.
- [V] Paper broker state lives in memory only, so paper positions are lost on restart.
- [V] `deploy/vps/11-verify.sh` curls `http://localhost:${WEB_PORT:-80}` (lines 118-127) and requires an `ss` listener on that port (173-185). Both checks fail once the `web` `ports:` line is removed, so they must change in the same commit. `WEB_PORT` is also used in `deploy/compose.prod.yml:8-9` and `docs/deployment.md:99,117`.
- [V] SPA patterns:
  - `refetchInterval: 5_000` is used in `strategy-list-sidebar.tsx:25` and `use-open-position.ts:36`.
  - `api-client.ts` has `apiPost`, `apiPatch` and `apiFetch`, with no 401 retry yet (Phase 01 adds it).
  - `start-stop-button.tsx` has an inline confirm modal; no shared confirm component exists.
- Paper validation E2, a mid-schedule redeploy versus the C1–C5 checks:
  - C5 (sessions) and C3 (integrity) are unaffected.
  - "Running 2" recovers through reconcile.
  - The CB==0 count reads `docker logs --since` from a recreated container, so lines from before the deploy are lost. The plan already says a deploy only shortens that row's log window.
  - `sync_1m` p95 reads job history from Mongo, which survives restarts.
- [V] E2 ends on Mon 2026-11-02, and Phase 07 currently requires it, so Phase 10's dated observation window cannot hold.

## Cloudflare Tunnel facts (research, 2026-10-20; report `researcher-261020-1906-cloudflare-tunnel-facts.md`)
- [V] Use the image `cloudflare/cloudflared` and pin an exact tag (for example `2026.10.2`). It is distroless with no shell or curl. Run it as `command: tunnel --no-autoupdate run` with `TUNNEL_TOKEN` in the environment and `restart: unless-stopped`.
- [V] Healthcheck: set `TUNNEL_METRICS: 127.0.0.1:60123` and use `test: ["CMD","cloudflared","tunnel","--metrics","127.0.0.1:60123","ready"]`. The `tunnel ready` command exists (PR #1135). It fails if no metrics address is set.
- [V] Dashboard path in 2026: Networking > Tunnels > (tunnel) > Routes > Add route > Published application. The Zero Trust "Networks" menu was removed on 2026-10-12. The Zero Trust Free plan has historically asked for a card.
- [V] The dashboard rejects a route whose hostname already has an A/AAAA/CNAME record, so the old record must be deleted first. A CNAME at the apex works through flattening. Removing a route does not delete its DNS CNAME, so remove `tunnel-test` by hand.
- Switch order:
  1. Test `tunnel-test` fully (SPA pages and a long SSE stream).
  2. Switch www, then @, by deleting each record and adding its route at once.
  3. Keep host port 80 until both are verified; rollback is restoring the A record.
  4. Remove the `web` `ports:`.
- [V] The zone SSL mode does not affect tunnel traffic.
- [V] Docker-published ports bypass ufw. cloudflared in the same compose project reaches `web:80` by service name.
- [V] Mongo, Redis and Portainer also publish host ports. [I] They are exposed unless the prod `.env` binds them to 127.0.0.1 (not checked). This is out of scope, but worth flagging.
- [V] SSE: the tunnel does not buffer `text/event-stream`. The edge cuts a request after 125 s with no bytes, and both SSE endpoints have no heartbeat. [I] Quiet streams are already cut today through the proxy, and the tunnel does not make it worse. A `: ping` every 15–30 s would fix it.

## Open questions carried into the debate
1. Must Phase 07 (the master push) wait for E2 to close on 2026-11-02, or may it ship with live off earlier? A deploy resets the paper run's warmup and paper positions, and shortens the C1 log window.
2. The phase order puts several master pushes (07, 08) and live steps behind user gates. Is that the best order for the earliest safe first live trade?
3. Should an SSE heartbeat be in scope, given the tunnel cutover is when the user will test SSE?
4. KISS: is anything in Phases 04–06 bigger than needed?
