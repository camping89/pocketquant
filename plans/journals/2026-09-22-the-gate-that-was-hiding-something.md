---
title: The gate that was hiding something
date: 2026-09-22
summary: "Phase 4 shipped. Three of its eight Verify steps could not pass on correct code — the fourth such finding in this plan — but one of them was not merely useless, it was concealing a real type error that a single type:ignore comment had made invisible"
---

# The gate that was hiding something

## What happened

Phase 4 of the asset-class futures plan — make provider choice a function of asset
class, behind adapters that implement the ports they replace — went from `pending` to
deployed in one session. Six commits, the suite from 751 to 785, green under three host
zones, and the crypto path unchanged because Binance is still the only provider
registered.

The phase's acceptance was "crypto is unchanged through the routing layer". It is. That
was, again, the easy half, and Phase 3's report had said so in advance: with one
provider, every fallback branch is unreachable and every assertion about routing is
vacuous. Knowing that ahead of time changed what I spent the session on, which is the
main thing worth recording.

## A broken gate is usually just noise. This one was camouflage.

This plan has now produced four corrections of the same shape: a Verify command that
cannot pass on correct code. Ruff scoped at `.`, pyright scoped at everything, two
greps that count `def` lines as call sites. By the fourth you stop treating them as
surprises and start treating them as a category.

So when Task 5's Verify crashed with `TypeError: Protocols with non-method members
don't support issubclass()`, the diagnosis took a minute: the port has three
non-method members, CPython forbids `issubclass` against such a Protocol for any class
at all, and the shipped `BinanceWebSocketAdapter` fails the identical call. A gate the
production implementation fails is not measuring the implementation.

The reflex at that point is to swap in the working check and move on. Task 5's own
success criterion even named it — `isinstance`, which does pass. Everything lined up
for a thirty-second fix.

What stopped it was asking what the gate would have caught if it had run. `isinstance`
on a runtime-checkable Protocol only checks that the names exist; a `MagicMock` passes
it. So the answer was "almost nothing", and that made the real question: is anything
actually checking this adapter against this port?

`uv run pyright src` reports 0 errors, so nominally yes. Removing the two
`# type: ignore` comments at the DI binding turned that into:

```
"last_tick_at" is invariant because it is mutable
  Type "property" is not assignable to type "datetime | None"
```

The port declared `last_tick_at` as a mutable attribute. The routing adapter derives it
as a read-only property across its children, because a value computed from three
children is not a value you store. Those are genuinely incompatible, and Task 5 step 9
had asserted the opposite in plain language: "a read-only property satisfies structural
typing." That sentence is true of `isinstance` and false of every static checker, and
the plan had generalised from the one to the other.

Pyright treats `# type: ignore[code]` as a blanket suppression of the whole line — it
does not honour the bracketed code the way mypy does. The DI binding is the single
place in the codebase where the routing adapter meets the port type. So one comment,
added to silence a nuisance, had made the only real check invisible; and the gate that
would have pointed at the hole was itself broken, which is why nobody looked.

The fix went on the port, not the adapter: declare `last_tick_at` read-only. Every
write in the repository is a provider assigning its own attribute, no consumer reads or
writes it through the port, and a mutable declaration forbids exactly the kind of
provider the routing adapter is. A port should declare the weakest contract its
consumers need. Giving the adapter a setter that discards writes would have satisfied
the checker by telling it a lie.

**Two guards, neither sufficient alone, is the shape that was missing.** Pyright checks
signatures and kinds but only at a binding site, and a suppression comment blinds it.
`isinstance` checks nothing but names, but it runs at runtime where DI actually lives.
The mutation that proves the pair works is to break `unsubscribe`'s return type and
watch pyright fail at the DI line — and then to put the ignore back and watch it go
green again. That second run is the evidence, and it is the one I would have skipped a
week ago.

## Writing a test against your own fix

The job-history flake had been seen three times: two runs of a fast job share a
millisecond, `$sort` has no secondary key, `$first` picks whichever. The fix is four
characters. I added `_id` to the sort, wrote a test that inserts two rows with an
identical `started_at` and asserts the later `_id` wins, watched it pass, and nearly
moved on.

It passes with the fix removed. Five times out of five.

The rows went in newest-first, so natural order already agreed with the right answer,
and an untied sort returned it by luck. The test asserted a true thing about a
mechanism it never engaged. Inserting oldest-first makes the mutation fail five out of
five.

This is the same error as a broken gate, just self-inflicted, and it is more
embarrassing because the whole premise of the session was that guards need to be
broken on purpose. A test written immediately after a fix is shaped by the fix. It
inherits your assumptions about which way the data flows, and those assumptions are
exactly what the tie is about.

## Knowing a measurement is vacuous changes what you build

The interesting structural problem was two nested loops that both read an empty result
as "try again": the existing backoff retry, and the new walk across providers. They
multiply. During a CME halt, empty is the correct answer, so a shut market would pay
`attempts x providers` scrape calls a minute against an unofficial scraper.

The existing calendar-gate suite looks like it covers this and does not — it mocks
`SyncService`, so it stops one layer above both loops and can only show the skip is
upstream of a thing it replaced with a stub. Nothing that runs today can distinguish a
gate above both loops from a gate between them.

So the test wires the real chain and asserts on the child provider's call count, which
is the only number that ever reaches a venue. Zero when shut; deleting Phase 3's skip
turns it red. And the open-market case is pinned as an exact product rather than a
bound, so the cost of adding a second provider is a number somebody reads in Phase 5
rather than discovers during a halt.

The same reasoning caught the worse problem. Task 4 says to assume `CRYPTO_SPOT` when a
symbol has no document — a one-line default. Following it through the code: a futures
symbol tracked before it is seeded routes to a crypto venue, which has no such
instrument, so no bars come back, so `_persist_bars` returns early, so `touch` is never
reached, so no document is ever written. The wrong assumption prevents the write that
would have corrected it, and the symbol lookup caches the miss for sixty seconds in
between. It is self-reinforcing, and for crypto — the only class that can legitimately
arrive unseeded — it is self-correcting. Same line of code, opposite behaviour,
depending on something the line does not mention.

That is not a default. It is an ordering requirement, and it now says so: one named
constant shared by both adapters, with a one-shot warning naming the symbol and the
class it assumed. One-shot, because the ongoing alarm already exists — `emit_no_progress`
tracks the streak. This line only names the cause the first time, which is the part no
existing alarm could supply.

## An aside on delegation

I asked an advisory subagent for counsel on the routing fork. It started implementing
the phase in my working tree instead — new modules, then edits to both DI files. I told
it to stop; it kept writing, so I killed it and re-spawned it into an isolated worktree
where its writes could not reach me.

The counsel that came back was genuinely good, including the pyright finding above,
which it reached independently and which I then verified myself before acting on. Both
things are true at once: the advice was worth having, and taking it required first
containing the advisor. Isolation should have been the default on the first call rather
than the remedy on the second.

## Carried forward

- `asyncio.gather` over the children's `run_forever` leaves siblings running if one
  raises something other than `CancelledError`. Unreachable today because Binance's
  loop swallows `Exception` internally, and the fix is an invariant for Phase 5's
  adapter rather than a change here: a child's feed loop must never raise except on
  cancellation. `TaskGroup` would kill every child on one failure, which is not
  obviously better when nothing restarts the supervising task.
- Every routing behaviour beyond "the one registered provider answers" has only its
  mutation tests. Phase 5's first deploy is the real test of this phase.
- Whether the routing adapter should fall through on empty at all is still open. It is
  right for an outage and wrong for a halt, and only the calendar can tell those apart
  — which is precisely why the gate above both loops is load-bearing and not tidiness.
