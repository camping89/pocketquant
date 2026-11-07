---
name: safeguards-live-trading-mirror-design
description: 2026-10-31 decision rationale - the api cannot see the trader's EXNESS_LIVE_TRADING (compose pins api/worker false), so the trader writes its flag into the safeguards doc at takeover; display and add_symbol read the mirror, order gates never do; no write on lease loss.
metadata:
  type: project
---

Design advised 2026-10-31 (Kongming GO): the trader lease holder writes `settings.exness_live_trading`
into the singleton `safeguards` doc (`live_trading` field) in `take_over`, before any broker connects.
GET/pause/resume overlay the stored value in the response; `add_symbol` checks the stored trader flag.
`Safeguards.live_trading` (DI, env) stays the only input to BrokerFactory and ExnessClient order gates.

Why the two visible bugs existed: `deploy/compose.prod.yml` pins `EXNESS_LIVE_TRADING="false"` on api
and worker (owner decision: the api must never be able to send an order), so the api's own setting is
always false; the strip showed OFF and exness subscription creates were always rejected.

Rejected: env mirror under a second var (reports the file, not the running trader), api->trader HTTP
call, flag on the lease doc (LeaseRepository is generic for both leases).

Deliberately NOT written on `on_lost`: a lost lease may already belong to a new holder that wrote its
own value; a late `false` would show OFF while the new trader is armed (the dangerous direction).
Known staleness: a trader stopped without a successor leaves the last value (shows ON while nothing
trades - conservative). Optional refinement if that bites: route also checks the trader lease expiry.

**How to apply:** any future change that makes `get_safeguards` in `app/di/adapters.py` read the
store would arm the broker from a Mongo doc - refuse it. Keep the test that stored true + env false
still makes BrokerFactory/ExnessClient refuse.
