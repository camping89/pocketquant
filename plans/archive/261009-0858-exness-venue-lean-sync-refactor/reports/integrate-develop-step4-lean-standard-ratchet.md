# Integrate develop, step 4: lean coding standard and code metric ratchet

`develop` now has a lean coding standard (829 → 294 lines in English, 826 → 294 in the `docs/vi/` mirror) and a code metric ratchet that runs in every leg of the CI `tests` job. The ceiling is frozen at develop's own numbers: `max_tiny_share = 0.48` and `max_delegations = 77`. CI run 38370477789 passed every job, the ratchet step succeeded in all three timezone legs, and the deploy verify step printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`.

## Commits on develop (pushed as cf72d08..4e99e61)

| Commit | Subject |
|---|---|
| 12f73cc | ci: gate the tests job on a code metric ratchet frozen at develop's numbers |
| 4e99e61 | docs(standards): rewrite the code standard as lean rules of thumb |

I ported the intent of the old-master commits and did not cherry-pick them. `scripts/code_metrics.py` and `tests/scripts/test_code_metrics.py` were added in ae22835; the standard rewrite, the `[tool.code-metrics]` ceiling and the CI step were added in 6a0d01c. The script was not changed between those two commits.

## Coding standard

| File | Before | After |
|---|---|---|
| `docs/code-standards.md` | 829 lines | 294 lines |
| `docs/vi/code-standards.md` | 826 lines | 294 lines |

The new file has 15 H2 sections: Principles, When to Extract a Helper, File and Function Size, Naming, Routes & Services, Dependency Injection, Domain & Repositories, Composite Symbol Format, Strategy IDs, Async Suspension Points, Comment Policy, Testing, Performance, Quality Gate, and Configuration & Secrets. The two mirrors have identical headings.

What develop keeps, unlike old master's rewrite:
- **English prose, with a Vietnamese mirror.** Old master wrote Vietnamese prose; develop's docs are English with `docs/vi/` kept in sync.
- **The full naming convention.** `### Class Naming by Layer` and `### Naming Principles & Exemptions` stay, because `CLAUDE.md` points to them by name. I corrected the file column where it was false: query and command models live beside their service (no `*_query.py` or `*_command.py` files exist), routes are `app/routes/{feature}.py`, and configs live in `config.py` or `value_objects.py`.
- **The Comment Policy section is byte-identical** to the old one (checked with `diff`).
- **The async-suspension patterns** keep their heading, which `docs/system-architecture.md:716` cites. I trimmed them and fixed the publish-before-subscribe example: develop's `register_sync_jobs` is `async`, and the wiring that matters is `set_sync_container(container)` before the first `await` in `app/main.py`.
- **The suffix routing rule from step 2** is kept word for word (suffix = data provider, `provider_id_for()`, `UnknownDataProviderError`, `DATA_PROVIDER_DEFAULTS`).
- **The 3 DI providers and scalar service methods from step 3.**

What I dropped:
- Restatements and duplicates: Clean Architecture Rules (stated twice), the layer tables, Import Organization (ruff `I` enforces it), Deprecated Patterns, the Import Contracts table and the Quality Checklist.
- Stale rules: the 200-LOC module rule and its exception list, the Service Extract-Method pattern, the Integrity Repair Flow walkthrough, the strategy-id rename history, and a link to a debugger report that does not exist in this repo.
- One internal contradiction: the old Error Handling section said services "catch/log/return error dicts", while two other sections said services never try/catch. The new text keeps the never-try/catch rule and allows a specific catch only where the code genuinely recovers.

Every class, file and function the new standard names was checked to exist on develop.

## Metric ratchet

`uv run python scripts/code_metrics.py --json` on develop's `src/pocketquant` (also written to `reports/metrics-develop-ratchet.json`):

| Metric | develop (frozen) | old master frozen value |
|---|---|---|
| `functions_total` | 949 | — |
| `functions_measured` | 775 | — |
| `tiny` | 372 | — |
| `tiny_share` | 0.48 | 0.4754 |
| `delegations` | 77 | 63 |
| functions over 60 lines | 27 | — |

`pyproject.toml` now ends with:

```toml
[tool.code-metrics]
max_tiny_share = 0.48
max_delegations = 77
```

The script was ported unchanged except for one line. Pyright reported `"splitlines" is not a known attribute of "None"` on `__doc__.splitlines()`, so the argparse description now reads `(__doc__ or "").splitlines()[0]`.

## CI step

`.github/workflows/cicd.yml`, job `tests`, directly after `Check import contracts (layered architecture)`:

```yaml
      - name: Code metrics ratchet
        run: uv run python scripts/code_metrics.py --ratchet
```

The `tests` job runs once per timezone (UTC, Asia/Ho_Chi_Minh, America/Chicago), so the ratchet runs three times, as `lint-imports` already does.

## Injected-regression proof

I added a temporary module `src/pocketquant/ratchet_probe.py` containing one pure delegation (`def run(self): return self.client.fetch()`), ran the ratchet, then deleted the module and ran it again:

```
::error title=code-metrics::tiny_share 0.4807 > 0.48
::error title=code-metrics::delegations 78 > 77
exit=1
exit after revert=0
```

`git status --short src` was empty afterwards.

## Tests

Old master had `tests/scripts/test_code_metrics.py`. I ported it to the same path; develop already keeps script tests in `tests/scripts/`. It has 9 tests and all pass.

## Docs made true

- `README.md` "Tests & Gates": added the ratchet command.
- `CLAUDE.md:23`: the code-standards pointer now lists "testing, quality gate + code metric ratchet" instead of "schema, testing, perf".
- `docs/deployment.md:21` and its vi mirror: the `tests` job description now names the three timezone legs, the host-zone check and the ratchet step.
- `docs/README.md:12` and its vi mirror: the Code Standards row describes the new sections.
- `scripts/README.md`: a `code_metrics.py` entry, and the scope line mentions the metric gate.
- No change was needed in `docs/project-overview-pdr.md:342`: its link `code-standards.md#routes--services` pointed at no heading before, and now resolves to `## Routes & Services`.

## Gate

- `uv run lint-imports`: `Contracts: 8 kept, 0 broken.`
- `uv run ruff check src scripts/code_metrics.py tests/scripts/test_code_metrics.py`: `All checks passed!`. Both new files pass `ruff format --check`.
- `uv run pyright src scripts/code_metrics.py tests/scripts/test_code_metrics.py`: `0 errors, 0 warnings, 0 informations`.
- `just test` (Docker running): `4 failed, 954 passed, 1 skipped, 4 errors`. The failures and errors are the same 4 pre-existing Windows `time.tzset` tests as in step 3 (`test_utc_runtime_guard.py` ×3, `test_cron_trigger_timezone.py` ×1). There are 954 passes now, against 945 in step 3; the difference is the 9 new script tests. No new failures.
- `uv run python scripts/code_metrics.py --ratchet`: exit 0.

## CI

Run 38370477789 (head 4e99e61) succeeded on every job: `tests (UTC)`, `tests (Asia/Ho_Chi_Minh)`, `tests (America/Chicago)`, `build-web`, `build-app`, `cleanup-tags` and `deploy`. The `Code metrics ratchet` step concluded `success` in all three `tests` legs. Each leg's pytest reported `958 passed, 1 skipped`. The deploy job's "Verify on VPS" step printed `=== Verdict: HEALTHY (20/20 passed, 0 warnings, 0 failures) ===`.

## Verdict

Done. The standard matches develop as it is after steps 1-3, and CI fails any later change that raises the tiny share or the delegation count. The ≤ 30% tiny share and ≤ 20 delegations from the phase goal are recorded as an aspiration, not a gate.

## Unresolved questions

- The phase goal's aspiration (≤ 30% tiny share, ≤ 20 delegations) was set against old master's numbers. Develop starts further from it (0.48 / 77). Whether to keep those targets for develop is a user decision; I left them as written.
