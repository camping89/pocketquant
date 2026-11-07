---
name: exness-docs-vs-live-shapes
description: Exness endpoints absent from the OpenAPI YAML (access-point discovery) have docs examples that differ from live responses; verify shape against a real response before building on it
metadata:
  type: project
---

The Exness docs page `/documentation/access-point-host-discovery` shows `"access_point": "ap-qwerty123.trading.exness.com"` (bare host) and labels itself "request-shape example only" pending a YAML contract. The live prod response on 2026-10-13 returned a full URL (`https://ap-<id>.exness.com`). The endpoint is not in `exness_api.yaml` 1.0.2 at all.

**Why:** Phase 01 of the exness plan burned a prod deploy cycle on this (spike exited 1 on the host allowlist). Phases 06/07 reuse `allowed_access_point(body["access_point"])`.

**How to apply:** For any Exness field not backed by the YAML, treat docs examples as hints, parse defensively (URL or host), and point to the recorded spike fixture / journal as the authority. Prefer a cheap in-container pre-flight before a long spike run.
