---
name: quote-sse-buffered-by-logging-middleware
description: Quote SSE (/api/v1/quotes/stream) emitted nothing in prod since 176ad15 because RequestLoggingMiddleware buffers every response body except a path allow-list that only named the bars stream; found at Phase 06 T6.19 step 7 (2026-10-19)
metadata:
  type: project
---

Prod quote SSE was dead for every provider (Binance included) until the Phase 06 fix: `RequestLoggingMiddleware.dispatch` consumes `response.body_iterator` for any path not in `SKIP_BODY_PREFIXES`, and that tuple listed only `/api/v1/market-data/bars/stream`. Symptom: no response headers at all until client disconnect, `http.response` logged with a tiny `duration_ms` but a timestamp at disconnect, no `sse.quote.*` error logs.

**Why:** the Exness phase's step 7 (`grep -c '"bid":'` on the quote stream) was the first end-to-end check of the quote SSE since the bff merge; nobody had curl-tested it. Counsel on 2026-10-19 was: fix in-phase in its own commit (detect streaming by `text/event-stream` content type rather than a path list), re-release develop->master, re-run step 7.

**How to apply:** any new SSE/streaming route must not be body-captured by the logging middleware; if the fix kept a path list, extend it. When an SSE endpoint "returns nothing, not even headers" while Redis is fresh, suspect a BaseHTTPMiddleware consuming `body_iterator` before suspecting the route.
