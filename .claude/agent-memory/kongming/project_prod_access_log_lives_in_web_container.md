---
name: prod-access-log-lives-in-web-container
description: To prove whether a browser action reached prod, read the nginx access log of the `web` container; the api request log is DEBUG-only, so "zero api lines" proves nothing
metadata:
  type: project
---

For "did the owner's click reach the server" questions on prod, read `docker compose logs --since <t> web` (nginx access log, json-file driver, 5m x 3): it shows method, path, status, client IP and UA per request. The api container's `RequestLoggingMiddleware` logs `http.request` at DEBUG only, and prod runs INFO, so an empty api log is expected and not evidence.

**Why:** 2026-11-02 Phase 17 obs-3: owner replied CLOSED but `manual_action` stayed null. The nginx log showed zero non-GET requests and no drawer detail GETs (`/snapshot`, `/orders`, `/trades`) after the page load; the drawer was never opened. Opening the drawer fires those three GETs at once (hooks in `web/src/hooks/use-subscription-detail.ts`), so their absence is a cheap "drawer opened?" check.

**How to apply:** before re-asking an owner to repeat a UI step, grep the web log for the expected `POST .../close|cancel` line and its status (202 ok, 401 token prompt cancelled, 409 ACTION_PENDING). Give the owner click-by-click steps and what success looks like (grey "close requested" text, then the position line disappears); the SPA shows no success toast.
