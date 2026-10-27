# Phase 09 — Paper position ownership and explicit subscriptions (Deploy C point)

- Unload: drop the subscription's paper position and disconnect a paper broker with no holders. Exness keeps the venue position and logs a WARNING.
- Restart: the position mirror closes paper rows at boot with one log line.
- Replace `EventRegistry` with explicit `bus.subscribe` calls; keep the order (strategy before broker).
- Drop the paper `_orders` map and the decorative `@event_handler`.

Verify: reconcile, restart-resume, live collector and paper broker tests.
