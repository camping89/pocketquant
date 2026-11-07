---
name: phase17-delete-bson-sizing-and-id-checks
description: Measured BSON size of a delete_many {_id:{$in:[...]}} filter with 200k UUIDv7 string ids (9.27 MiB) and the offline id-list consistency checks used before the Phase 17 prod STF delete
metadata:
  type: project
---

A `{"_id": {"$in": ids}}` filter with 200,554 UUID strings (36 chars) encodes to 9.27 MiB of BSON (about 48 B per id); 100,273 ids = 4.58 MiB. Below the 16 MiB command limit, so the Phase 17 Task 17.6 script ran unchunked. Chunk only above roughly 300k ids per list.

**Why:** 2026-11-03 pre-delete checkpoint for plan 261101-0843 Phase 17. Measured with `bson.encode` locally on `reports/stf-delete-ids.json`; prod ids are plain strings (the LIST script's `json.dumps` with no `default=` proves it), Mongo 7.0.45, sync PyMongo.

**How to apply:** for any future exact-id prod delete, reuse the offline checks that gave GO: no duplicate or cross-list ids; every id a UUIDv7 whose embedded timestamp is before the cut-off (here the paper start 2026-11-02T10:12Z); the protected subscription ids absent from every list; list sizes reconciled to the pre-change counts (orders 250 STF + 9 orphans = 259 = 241 filled + 18 rejected). A crash mid-delete leaves no `mismatch=` line; the re-run then reports `listed > deleted` for that collection, and the Task 17.7 re-list to zero is the real proof.
