# Research Report: VS Code python.defaultInterpreterPath Cross-Platform Configuration

**Date:** 2026-03-22
**Research Duration:** 30 minutes
**Status:** Complete

---

## Executive Summary

The error "Path contains unresolved variables" occurs because `${workspaceFolder}` variables in `python.defaultInterpreterPath` **cannot be resolved in global user settings** — they must be set in workspace-scoped settings (`.vscode/settings.json`).

**Recommended solution:** Use `python.defaultInterpreterPath` with `${workspaceFolder}` **only in workspace-scoped `.vscode/settings.json` files**, not in global user settings.

---

## The Problem

Setting `"python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python"` in global user settings causes the Python extension to report "Path contains unresolved variables" because workspace-folder variables cannot be resolved outside a workspace context.

The extension was evaluating the literal path string `W:\\Tools\\VSCode\\${workspaceFolder}/python-embedded/python.exe` without first expanding the variable.

---

## The Solution

### For Workspace-Scoped Settings (✓ Recommended)

Store the setting in `.vscode/settings.json` (workspace-local):

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python"
}
```

This works cross-platform because:
- `${workspaceFolder}` is expanded in the workspace context
- `.venv/bin/python` is the standard POSIX path (macOS/Linux/Windows with WSL)
- VS Code automatically resolves this to the correct platform-specific path

### For Global User Settings (✓ Alternative)

If you must set globally, use a relative path without variables:

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python"
}
```

**Limitation:** Relative paths may not work with the debugger in all scenarios.

### Not Recommended ✗

Avoid this in global user settings:
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python"
}
```

The variable cannot be resolved globally, causing the warning.

---

## Technical Details

### Variable Resolution Scope

The fix (PR #1334 in vscode-python-environments) changed the behavior to:
1. **Check if path contains workspace-scoped variables** (`${workspaceFolder}`)
2. **Skip evaluation during global resolution** (don't throw error)
3. **Allow proper evaluation in workspace context** (later in startup)

This means the setting is technically valid—the error is a false warning from global scope evaluation.

### Cross-Platform Path Compatibility

For `.venv/bin/python`:
- **macOS/Linux:** `.venv/bin/python` → directly executable
- **Windows (native CMD):** `.venv\Scripts\python.exe` → requires backslashes
- **Windows (WSL/Git Bash):** `.venv/bin/python` → works in POSIX environment

**Key finding:** Using `.venv/bin/python` in VS Code settings works cross-platform because VS Code interprets paths in workspace-scoped settings, not native shell format.

---

## Official Documentation

According to [VS Code Python settings reference](https://code.visualstudio.com/docs/python/settings-reference), `python.defaultInterpreterPath` supports variables including:
- `${workspaceFolder}` — path of the folder opened in VS Code
- `${workspaceRootFolderName}` — folder name without slashes
- `${cwd}` — current working directory
- `${file}` — current opened file

**However:** These are primarily documented as supported in general, but workspace-scoped variables have limitations when evaluated at global scope.

---

## Recommended Configuration

### Workspace Level (.vscode/settings.json)

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python"
}
```

**Advantages:**
- ✓ Portable across machines and projects
- ✓ Works on both macOS and Windows
- ✓ Properly resolved in workspace context
- ✓ No false "unresolved variables" warning
- ✓ Debugger-compatible

### Global User Settings (if needed)

If you want a global fallback, omit the variable:

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python"
}
```

---

## Source References

| Source | Purpose |
|--------|---------|
| [VS Code Python Settings Reference](https://code.visualstudio.com/docs/python/settings-reference) | Official documentation on `python.defaultInterpreterPath` and supported variables |
| [Issue #25869 (vscode-python)](https://github.com/microsoft/vscode-python/issues/25869) | Reported bug: "Path contains unresolved variables" error |
| [Issue #1316 (vscode-python-environments)](https://github.com/microsoft/vscode-python-environments/issues/1316) | Root cause: workspace-scoped variable evaluation at global scope |
| [PR #1334 (vscode-python-environments)](https://github.com/microsoft/vscode-python-environments/pull/1334) | Fix: skip workspace-scoped variables during global resolution |
| [VS Code Python Environments Documentation](https://code.visualstudio.com/docs/python/environments) | Environment discovery and configuration |

---

## Unresolved Questions

1. Does the fix in PR #1334 completely eliminate the warning in current Python extension versions (2026.4+), or does the false warning still appear in some edge cases?
2. Does relative path `.venv/bin/python` in global user settings work consistently with VS Code's Python extension for all scenarios (debugging, linting, testing)?
3. Are there performance implications of using workspace-scoped `python.defaultInterpreterPath` across multiple workspaces?
