# Justfile Cross-Platform Compatibility Analysis

**Date:** 2026-01-20
**Analyzer:** debugger
**File:** `d:\w\_me\pocketquant\justfile`
**Status:** Critical - Multiple compatibility issues identified

## Executive Summary

Current justfile contains platform-specific syntax preventing execution on non-Windows systems. Issues include Windows CMD conditionals and Unix-only path separators. Just provides built-in cross-platform capabilities via `os()` function and conditional expressions that should be used instead.

## Issues Identified

### Critical Issues

1. **Line 9: Windows CMD Syntax**
   ```justfile
   @if not exist ".venv" uv venv
   ```
   - `if not exist` is Windows CMD syntax
   - Fails on Linux/macOS (requires shell-specific conditionals)
   - Should use just's conditional expressions or platform-agnostic commands

2. **Line 15: Unix Path Separator**
   ```justfile
   .venv/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port {{port}}
   ```
   - Forward slashes work on Windows but path is wrong
   - Correct Windows path: `.venv\Scripts\uvicorn.exe`
   - Unix path: `.venv/bin/uvicorn`

### Secondary Issues

3. **Missing `uv` on Current System**
   - `uv` command not found during testing
   - No fallback to standard Python venv creation
   - Could cause silent failures

4. **No Shell Configuration**
   - Relies on system default shell
   - Windows may use PowerShell, CMD, or bash (Git Bash, WSL)
   - Unix systems use sh/bash
   - Inconsistent behavior across environments

## Technical Analysis

### Just Cross-Platform Features

Testing confirmed just provides:

1. **OS Detection Functions**
   ```justfile
   os()        # Returns: "windows", "linux", "macos"
   os_family() # Returns: "windows", "unix"
   ```

2. **Platform-Specific Recipes**
   ```justfile
   [windows]
   recipe_name:
       # Windows-only commands

   [unix]
   recipe_name:
       # Unix-only commands
   ```

3. **Conditional Expressions**
   ```justfile
   var := if os() == "windows" { "value1" } else { "value2" }
   ```

### Current vs Required Behavior

| Recipe | Current | Windows Required | Unix Required |
|--------|---------|------------------|---------------|
| install | `if not exist` CMD check | `.venv\Scripts\python.exe` | `.venv/bin/python` |
| start | `.venv/bin/uvicorn` | `.venv\Scripts\uvicorn.exe` | `.venv/bin/uvicorn` |

## Recommended Solutions

### Option 1: Conditional Variables (Recommended)

**Pros:**
- Clean, maintainable
- Single recipe definition
- Explicit platform handling

**Implementation:**
```justfile
# Cross-platform paths
venv_python := if os() == "windows" { ".venv\\Scripts\\python.exe" } else { ".venv/bin/python" }
venv_uvicorn := if os() == "windows" { ".venv\\Scripts\\uvicorn.exe" } else { ".venv/bin/uvicorn" }

install:
    @{{venv_python}} -m venv .venv 2>/dev/null || echo "venv exists"
    uv pip install -e ".[dev]"

start port="8765": install
    docker compose -f docker/compose.yml up -d
    {{venv_uvicorn}} src.main:app --reload --host 0.0.0.0 --port {{port}}
```

### Option 2: Platform-Specific Recipes

**Pros:**
- Maximum flexibility per platform
- Can optimize for platform-specific features

**Cons:**
- Code duplication
- Harder to maintain

**Implementation:**
```justfile
[windows]
install:
    @if not exist ".venv" python -m venv .venv
    .venv\Scripts\pip.exe install -e ".[dev]"

[unix]
install:
    @test -d .venv || python3 -m venv .venv
    .venv/bin/pip install -e ".[dev]"

# Start recipes follow same pattern
```

### Option 3: Shell Scripts for Complex Logic

**Pros:**
- Handles complex conditionals
- Native platform features

**Cons:**
- Requires maintaining separate scripts
- Defeats purpose of just simplicity

**Skip - Unnecessary complexity for current needs**

## Proposed Fix (Option 1)

```justfile
# PocketQuant Development Tasks
# Requires: just, docker
# Optional: uv (faster pip alternative)

# Cross-platform executable paths
python := if os() == "windows" { ".venv\\Scripts\\python.exe" } else { ".venv/bin/python" }
pip := if os() == "windows" { ".venv\\Scripts\\pip.exe" } else { ".venv/bin/pip" }
uvicorn := if os() == "windows" { ".venv\\Scripts\\uvicorn.exe" } else { ".venv/bin/uvicorn" }

default:
    @just --list

# Install dependencies in virtual environment
install:
    @{{python}} -m venv .venv 2>/dev/null || echo "Virtual environment exists"
    {{pip}} install -e ".[dev]"

# Start everything: venv → deps → docker → server
start port="8765": install
    docker compose -f docker/compose.yml up -d
    {{uvicorn}} src.main:app --reload --host 0.0.0.0 --port {{port}}

# Stop containers (data preserved)
stop:
    docker compose -f docker/compose.yml stop

# View container logs
logs service="":
    docker compose -f docker/compose.yml logs -f {{service}}
```

### Key Changes

1. **Variables with Conditionals** - Define platform-specific paths at top
2. **Removed `uv` Dependency** - Use standard Python venv (more portable)
3. **Graceful venv Creation** - `2>/dev/null || echo` instead of shell conditionals
4. **Escaped Backslashes** - Windows paths use `\\` in just strings

## Testing Required

Test matrix on clean systems:

| Platform | Shell | Commands |
|----------|-------|----------|
| Windows 11 | PowerShell 7 | `just install`, `just start` |
| Windows 11 | CMD | `just install`, `just start` |
| Ubuntu 22.04 | bash | `just install`, `just start` |
| macOS 14 | zsh | `just install`, `just start` |

## Performance Impact

- Negligible: Variable evaluation happens once per recipe invocation
- No shell spawning overhead for conditionals (just built-in)

## Security Considerations

- No changes to exposed ports or network config
- Removes dependency on external `uv` command (reduces supply chain risk)
- Standard Python venv creation (well-tested, secure)

## Migration Steps

1. Backup current justfile
2. Apply proposed changes
3. Test `just install` on Windows
4. Test on Linux VM/container if available
5. Update README.md to remove `uv` requirement
6. Commit with message: `fix(just): add cross-platform path support`

## Alternative: Keep uv Support

If `uv` performance is critical:

```justfile
install:
    @{{python}} -m venv .venv 2>/dev/null || echo "venv exists"
    @command -v uv >/dev/null 2>&1 && uv pip install -e ".[dev]" || {{pip}} install -e ".[dev]"
```

This falls back to standard pip if `uv` unavailable.

## Unresolved Questions

1. Should we keep `uv` requirement or make it optional?
2. Do we need platform-specific Python versions (python vs python3)?
3. Should docker commands also check platform (Docker Desktop vs native)?
4. Do we need a `clean` recipe to remove `.venv` cross-platform?

## Sources

- [GitHub - casey/just: 🤖 Just a command runner](https://github.com/casey/just)
- [Just: A Command Runner](https://just.systems/)
- [Introduction - Just Programmer's Manual](https://just.systems/man/en/)
