# Local Deploy Scripts

Scripts in this folder run **on the operator's machine** (Windows / macOS / Linux), NOT on the VPS.

Use for: pre-flight checks, local artifact builds, scp helpers, smoke tests against a live VPS from outside, etc.

## Where scripts go

| Runs on... | Location |
|------------|----------|
| Operator's machine (local) | `deploy/scripts/` (this folder) |
| VPS (must be scp'd up) | `deploy/scripts-to-deploy/` |

`deploy/scripts-to-deploy/` contains everything the VPS executes: `deploy.sh`, `verify.sh`, cron `cleanup.sh`, one-time `server-setup.sh`, and `patches/`.

## Convention

- Shell scripts: `kebab-case.sh` with `#!/usr/bin/env bash` shebang
- Pure-PowerShell helpers: `kebab-case.ps1`
- Cross-platform tasks: prefer the project `justfile` over a script here
