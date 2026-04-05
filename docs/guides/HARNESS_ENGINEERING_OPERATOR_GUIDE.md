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

This script is **validation only** in Phase 2. It does not execute upstream `./setup`.

### gstack QA dry-run
```powershell
powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun
```

### Codex wrapper dry-run
```powershell
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "AGENTS.md" -DryRun
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile implement -Plan "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md" -DryRun
```

## Current Phase 2 Boundary
- `tools/harness/setup_gstack.ps1`: detection/reporting only
- `tools/harness/import_gstack_source_slice.py`: repeatable importer for the pinned setup/host-config source slice
- `tools/harness/run_codex.ps1`: Codex CLI wrapper for review / implement / QA prompts
- `tools/harness/run_gstack_qa.ps1`: QA preflight that delegates to `run_codex.ps1`
- `.agents/skills/gstack/VENDOR.md`: vendor boundary contract
- `.agents/skills/gstack/upstream/SNAPSHOT.md`: pinned upstream docs snapshot (`04b709d91a3f10efa1c816c6ddb4c8cafa735da8`)
- `.agents/skills/gstack/upstream/AGENTS.md`: upstream skill inventory snapshot
- `.agents/skills/gstack/upstream/LICENSE`: upstream MIT license text
- `.agents/skills/gstack/setup`: pinned upstream setup entrypoint source
- `.agents/skills/gstack/hosts/*.ts`, `.agents/skills/gstack/scripts/host-config*.ts`: pinned host-config source slice

Phase 2 now includes a pinned upstream documentation snapshot, the exact repo-local `setup` entrypoint source, and the host-config slice that defines Codex/Cursor/Claude wiring. QA is modeled correctly as a Codex skill flow rather than a fake `gstack qa` binary. The PowerShell wrappers still stop at dry-run or explicit preflight failures until the remaining runtime assets, Codex CLI, and generated QA skills are present.

## Current Windows Runtime Gate
- `git`: required
- `node`: required
- `bun`: required
- `Git Bash` or `WSL`: one of them required for upstream setup on Windows
- repo-local `setup` entrypoint: present at `.agents/skills/gstack/setup`
- normalized Windows command form: `wsl bash -lc "cd '/mnt/c/.../.agents/skills/gstack' && bash ./setup --host codex"`
- `codex`: required for wrapper-driven review/implement/QA execution
- repo-local QA skill: expected under `.agents/skills/gstack-qa/` or vendor-internal generated `.agents/skills/gstack/.agents/skills/gstack-qa/`
- runtime asset subset: still missing (`browse/`, `bin/`, `review/`, `qa/`, `gstack-upgrade/`, templates or generated skills)

## Vendor Rule
- Keep upstream gstack content inside `.agents/skills/gstack/`
- Do not rewrite FOMS policy into vendored upstream files
- Apply FOMS-specific behavior through wrapper scripts, bundles, rules, and guides

## Verification
- App import success string: `APP_OK`
- Shared workflow: `.agents/workflows/verify-result.md`
- Harness bundles: regenerate after policy or plan changes
