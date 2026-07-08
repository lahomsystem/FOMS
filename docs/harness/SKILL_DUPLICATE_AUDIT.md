# Skill Duplicate Audit (2026-06-17)

Full scan: `python tools/harness/audit_skills.py`

## Root causes

### 1. Codex `/browse` + `/gstack-browse` style doubles (FOMS workspace)

| Source | Path | `name:` field |
|--------|------|---------------|
| Global Codex | `~/.codex/skills/gstack-browse/` | `browse` |
| FOMS vendor | `.agents/skills/gstack/browse/SKILL.md` | `browse` |

Codex discovers **both** global `~/.codex/skills/*` and repo `.agents/skills/**/SKILL.md`.
Directory uses `gstack-` prefix; frontmatter `name:` does not → UI shows mixed `/gstack-*` and `/*`.

### 2. Claude nested generated trees (226 SKILL.md files)

| Source | Path |
|--------|------|
| Linked (correct) | `~/.claude/skills/gstack-*/SKILL.md` |
| Generated noise | `~/.claude/skills/gstack/.agents/skills/gstack-*/` |
| Generated noise | `~/.claude/skills/gstack/.cursor/skills/gstack-*/` |

`./setup` writes host outputs **inside** the gstack install dir; Claude skill scan is recursive.

### 3. Cross-host copies (expected, not UI duplicates alone)

Same skill name in `~/.codex/skills`, `~/.cursor/skills`, `~/.claude/skills` is normal (one per runner).
Duplicates in **one** runner UI come from (1) or (2).

### 4. caveman (5 copies of `name: caveman`)

| Host | Path |
|------|------|
| claude | `~/.claude/skills/caveman` |
| codex | `~/.codex/skills/caveman` |
| cursor | `~/.cursor/skills/caveman` |
| foms | `.agents/skills/caveman` |
| home | `~/.agents/skills/caveman` |

In FOMS workspace Codex sees global + repo + home `.agents` → repeated `/caveman`.

## Cleanup applied

See `docs/archive/oneoff-scripts/cleanup_skill_duplicates.ps1`:

1. Remove `~/.claude/skills/gstack/.agents/` and `.cursor/` (setup artifacts)
2. Remove `~/.agents/skills/caveman` (redundant home copy)
3. Gitignore FOMS vendor workflow `SKILL.md` (keep `.tmpl` + setup validation via `.tmpl`)
4. Remove committed vendor leaf `SKILL.md` that Codex would double-load

## Cursor UI count (why 191 happened)

Cursor **merges** these roots into one slash-command list:

| Root | Role |
|------|------|
| `~/.cursor/skills` | Cursor user skills |
| `~/.cursor/skills-cursor` | Cursor built-ins (~18) |
| `~/.claude/skills` | Claude extension in Cursor |
| `~/.codex/skills` | Codex extension in Cursor |

191 ≈ 55 (cursor gstack copy) + 57 (claude) + 63 (codex) + 18 (built-ins) − overlap.

**Fix:** gstack canonical tree = **`~/.claude/skills/gstack-*` only**. Do not copy to `~/.cursor/skills`. Remove `~/.codex/skills/gstack-*` (Codex in Cursor shares Claude list). Remove `_gstack-command` duplicate.

After cleanup: **~78 skills** (57 gstack/claude + 18 built-ins + 3 codex perf helpers).

## Per-host counts (after cleanup, 2026-06-17)

| Host | SKILL.md count | Notes |
|------|----------------|-------|
| claude | 57 | was 226 (nested `.agents/.cursor` + source tree dupes) |
| codex | 63 | includes `.system`, perf-*, caveman, gstack meta |
| cursor | 55 | gstack workflow set |
| foms `.agents/skills` | 0 | vendor `SKILL.md` gitignored/removed |

Duplicate **name groups** across all roots: **55** (down from 107). Remaining groups are mostly the same workflow exposed on claude + codex + cursor (expected).

## Re-check

```powershell
python tools/harness/audit_skills.py
```
