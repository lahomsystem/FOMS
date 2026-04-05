# FOMS Harness Engineering Operator Guide

## Purpose
- Keep Cursor, Claude, and Codex aligned on one FOMS policy graph.
- Separate **policy** from **runtime tooling**.
- Make Windows-first operator entrypoints explicit.

## Source Of Truth
- Portable baseline: `AGENTS.md`
- Claude session augmentation: `CLAUDE.md`
- Cursor enforcement: `.cursor/rules/*.mdc`
- Shared verification contract: `.agents/workflows/verify-result.md`
- Generated runner bundles:
  - `docs/context/HARNESS_BUNDLE_CURSOR.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE.md`
  - `docs/context/HARNESS_BUNDLE_CODEX.md`

## Browser Ownership
- Cursor browser MCP: exploration, manual debugging, ad-hoc reproduction
- gstack runtime: repeatable QA, smoke, canary, benchmark

## Bundle Refresh
```powershell
python "tools/harness/build_context_bundle.py" --all
```

Use the generated bundle that matches the runner you are about to use.

## Phase 2 Scripts
### gstack setup preflight
```powershell
powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf
```

### gstack QA dry-run
```powershell
powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun
```

## Current Phase 2 Boundary
- `tools/harness/setup_gstack.ps1`: detection/reporting only
- `tools/harness/run_gstack_qa.ps1`: validation + dry-run contract
- `.agents/skills/gstack/VENDOR.md`: vendor boundary contract

Until the upstream gstack snapshot is imported and pinned, Phase 2 scripts intentionally stop at dry-run or explicit preflight failures.

## Vendor Rule
- Keep upstream gstack content inside `.agents/skills/gstack/`
- Do not rewrite FOMS policy into vendored upstream files
- Apply FOMS-specific behavior through wrapper scripts, bundles, rules, and guides

## Verification
- App import success string: `APP_OK`
- Shared workflow: `.agents/workflows/verify-result.md`
- Harness bundles: regenerate after policy or plan changes
