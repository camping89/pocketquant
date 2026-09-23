---
title: The quote that expired between polls
date: 2026-09-23
summary: "Phase 6 made futures trade in contracts and gave them a realtime feed. The design fork the plan predicted arrived, a review found a history-corruption hazard the pollers made reachable, and production found a TTL no test could see."
---

# The quote that expired between polls

## What happened

Phase 6 taught the pipeline that one ES point is 50 dollars. Positions carry the
contract multiplier, sizing floors to whole contracts, commission can be charged per
contract, and ES, NQ and YM finally have a realtime feed: a poller that asks
TradingView for the newest 1m bar once a minute while CME is open. Eight commits, 865
tests, and 43 guards, each of which was broken on purpose and turned a test red.

## The fork the plan saw coming

Task 5 said the live paper broker is shared per broker type, so it cannot carry a
per-symbol spec. It said to thread a multiplier through the order, and to stop if that
took more than three edits. It took more: the broker is reached only through
`IBrokerPort`, the order may not carry the spec, and the engine had no way to learn a
symbol's spec at all. So the Failure Protocol ran, and the alternative the plan itself
had named won. The spec rides on the strategy config, resolved where configs are
built, and the pool is keyed by type and spec. The cost is honest and written down:
each futures spec now has its own paper account.

The same thread surfaced something the plan had not listed. The UI does not read PnL
from the broker. It reads a second, persisted copy of every position that
`PositionAppService` builds from fill events. Without the multiplier there, an ES trade
would have shown one fiftieth of its PnL.

## What the review found

An independent review before the deploy found the dangerous one. A cancelled
`asyncio.to_thread` does not stop its thread. The TradingView client already discarded
its scraper instance after a timeout for exactly that reason, but not after a
cancellation. Before this phase nothing cancelled a fetch in normal operation. Now
quote pollers share the client with the history sync and are cancelled whenever a
symbol is unsubscribed. A poller cancelled mid-fetch would have left a thread reading
the socket that the next history fetch then shared: ES bars stored under NQ, each one
well-formed enough to pass every integrity check.

## What production found

Two minutes after the deploy, the ES latest-quote endpoint answered 404 while NQ and YM
answered normally. The quote cache expired after 60 seconds, and the poller runs every
60 seconds. A futures price that held still for one poll simply vanished. No unit test
could have seen it: the TTL and the poll interval were each correct on their own and
wrong only together. The fix is the rule the phase had already written for staleness
thresholds, three polls.

## What stays open

G2, a live paper ES session, cannot trade at the default 10,000 balance: sizing
correctly finds that such an account cannot hold one 390,000-dollar contract. Whether
futures run with a larger paper balance or a margin-based cap is a risk-policy
decision, not a bug. G3 ran on production data instead: 132 ES trades, every one exact
to the cent, with a Sharpe that matches the CME session calendar to twelve digits.

## Lesson

Two values that are each correct can be wrong together. The quote TTL was chosen for
a socket that ticks many times a second, and the poll interval for an endpoint that
can ban us. Nothing connected them until a symbol lived on both. When a new kind of
source enters an existing path, list every timing constant that path already has and
check each one against the new cadence.
