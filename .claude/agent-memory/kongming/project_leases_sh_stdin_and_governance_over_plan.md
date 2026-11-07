---
name: leases-sh-stdin-and-governance-over-plan
description: deploy/vps/leases.sh uses docker exec -i and swallows the rest of a `bash -s` heredoc; call it `< /dev/null` or last. Also the 2026-10-30 precedent that docs/governance wins over older plan doc steps.
metadata:
  type: project
---

`deploy/vps/leases.sh` (installed as `/opt/pocketquant/bin/leases.sh`) runs `docker exec -i ... python -c`
inside a process substitution. When a plan step pipes a script through `ssh HOST 'bash -s' <<'EOF'`,
the `-i` attaches the remaining script as stdin and every line after the `leases.sh` call is lost.
Phase 09 Task 9.9 hit it (verify script was split); Phase 10 Tasks 10.3/10.4 had it in the heredocs.
Call-site workaround: `bash /opt/pocketquant/bin/leases.sh < /dev/null`, or make it the last line.
Root fix advised 2026-10-31: drop `-i` in leases.sh (`python -c` never reads stdin), prove with a piped
`ssh HOST 'bash -s'` repro that prints a line after the leases.sh call. `11-verify.sh:146` calls
leases.sh and inherits stdin, so a piped verify run was also affected until the root fix lands.

Precedent (2026-10-30, Phase 09 checkpoint): `docs/governance/documentation-rules.md` (owner-approved,
newer than the plan) overrode plan tasks that asked docs to copy code-owned values (TTLs, fractions,
grace periods, event names). The runner recorded a "Correction" block in the phase file with the
replacement Verify greps. Kongming judged this sound. Row 0 (cutover) does not count toward the ten
handover rows; rows >= 1 ("after the last fix", 6142249f shipped by D-6) do.

**Why:** both are non-obvious from the code and bite the next prod-verification run.

**How to apply:** when reviewing or writing a VPS heredoc step, check for `docker exec -i` children;
when a plan step conflicts with `docs/governance/`, governance wins and the deviation is recorded in
the phase file, not silently.
