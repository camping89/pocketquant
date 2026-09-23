---
title: The halt that was not there
date: 2026-09-23
summary: "Seeding the index futures in production found three defects inside twenty minutes, including a trading halt we had modelled from a source four years out of date. The data had the answer; the review before it did not ask."
---

# The halt that was not there

## What happened

Phase 5's code had been deployed dormant. Today the three futures symbols were seeded
into production during a Wednesday CME session and backfilled to 5000 bars on every
interval. Before the full backfill, every symbol and interval was fetched at `n=5` and
checked against the calendar grid, and all 21 came back aligned. That probe turned out to
be the cheap part.

Within twenty minutes of real data flowing, three defects appeared that 826 passing tests
had not caught.

## The halt

Session 6 modelled a 15:15-15:30 Chicago trading halt for ES, NQ and YM, "confirmed
against CME's published contract hours". CME removed that halt in June 2021. The 1m bars
showed it at once: all three symbols had a traded bar for every minute of that window on
every weekday, with hundreds of ES contracts a minute. The upstream calendar library,
which we had overridden, had it right.

The lesson is not "check sources better". Session 6 did check a source, and many
third-party hours pages still list the halt. The lesson is that once real bars exist,
they outrank any document about when bars should exist. The check that settled this took
one query.

## The drop that took too much

Correction 23 had fixed a real problem: on the delayed free feed, the newest 1m bar is
still being written, so the adapter drops it. But it dropped "the newest bar left after
our clock cutoff". For daily and weekly bars the forming bar was already past the cutoff,
so the rule threw away the last closed bar instead. The unit tests had used an hourly
fixture where both rules gave the same answer. Asking "what is the newest daily bar we
stored?" found it.

## The warning every five seconds

The quote reconciler tries to subscribe every tracked symbol to a realtime feed every
five seconds. Futures have no realtime provider until Phase 6, so each tick logged three
WARNINGs and an INFO line claiming three symbols had been added. None of this was
reachable until a futures symbol existed, which is why no test saw it.

## What stays open

The week-long Task 12 gate cannot pass yet, and the reasons are design questions rather
than bugs. On a feed about twelve minutes behind, buckets look partial for twelve minutes
after they close. On a thin contract such as YM, the vendor omits minutes with no trades,
which Binance never does, so the integrity scan will report gaps that cannot be filled.
Both need a decision about what "complete" means for a delayed, sparse feed.
