# pocketquant-bff

Stateless FE gateway. Serves `pocketquant-web/dist`, reads Mongo/Redis, writes desired-state, and enqueues backtest requests over HTTP (`/api/v1`).

Owns no trading runtime: no scheduler, no WS feed, no strategy RAM, no reconcile/worker loop. Crashing or restarting `pocketquant-bff` never interrupts live trading — that runs headless in `pocketquant-app`. Reads stay available from static Mongo/Redis data even while `pocketquant-app` is down.

Top layer beside `pocketquant-app`; the two never import each other.
