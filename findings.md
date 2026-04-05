# Findings & Decisions

## Requirements
- Re-audit the approved harness-engineering master plan in two directions.
- If the plan is sound, execute it phase by phase.
- Use parallel agents where tasks are truly file-disjoint and independent.
- Audit each phase before starting the next one.

## Research Findings
- FOMS already has strong governance in `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, `.cursor/hooks`, `.cursor/agents`, and `.agents/workflows`.
- The master plan was broadly sound, but Phase 0 needed stronger file coverage and verification depth.
- `sessionEnd` and `stop` both call `session_stop.py` in `.cursor/hooks.json`, so duplicate-close handling must be addressed in Phase 0.
- Current hook implementations use broad exception swallowing in several places, which conflicts with FOMS root-cause-oriented policy.
- `CLAUDE.md` currently treats `APP_OK` as the canonical success marker; the plan was updated to match it.
- Windows baseline in FOMS is PowerShell 5.x compatibility, so `powershell -NoProfile -File ...` should be the default documented command form.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Execute using phase checkpoints | Matches user request and reduces architectural drift |
| Patch plan before code | Phase 0 should start from a corrected execution contract |
| Create planning files in project root | Required by planning-with-files for a multi-phase task |
| Keep both `sessionEnd` and `stop`, but make `session_stop.py` idempotent | Safer across Cursor versions than assuming only one event fires |
| Standardize shared repo commands on PowerShell 5.x, not `pwsh` | Matches workspace rules and user environment |
| Use manifest + runner profiles + generated bundles as the Phase 1 harness core | Keeps source registry, runner intent, and consumable artifacts separate and deterministic |
| Start Phase 2 with contract-first vendor boundary and dry-run scripts | Lets us validate Windows operator flow before importing upstream gstack runtime |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Plan did not explicitly include rules and verify workflow in Phase 0 | Patched the plan before execution |
| Phase 0 verification was too weak for hook idempotency and policy consistency | Expanded verification checklist in the plan |
| Closing audit found residual policy drift (`AGENTS.md` RPI linkage, `verify-result` noise, spec sort, shell wording) | Fixed before closing Phase 0 |
| Initial Phase 1 implementation used an external YAML parser and non-plan output paths | Reworked generator to use strict JSON syntax in `.yaml` files and aligned outputs to `docs/context/HARNESS_BUNDLE_*.md` |
| Phase 2 needs real gstack vendor import before non-dry-run execution | Introduced `VENDOR.md` boundary and Win11-safe dry-run scripts first |

## Resources
- `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/hooks.json`
- `.cursor/hooks/*.py`
- `.cursor/rules/*.mdc`
- `.agents/workflows/verify-result.md`

## Visual/Browser Findings
- None yet. Browser/runtime work begins in later phases.
