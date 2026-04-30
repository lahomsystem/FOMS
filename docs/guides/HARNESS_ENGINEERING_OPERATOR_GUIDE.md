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
  - `docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md`
  - `docs/harness/bundles/HARNESS_BUNDLE_CURSOR_HARNESS.md` (harness-internal only)
  - `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md`
  - `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE_HARNESS.md` (harness-internal only)
  - `docs/harness/bundles/HARNESS_BUNDLE_CODEX.md`
  - `docs/harness/bundles/HARNESS_BUNDLE_CODEX_HARNESS.md` (harness-internal only)

## Browser Ownership
- Cursor browser MCP: exploration, manual debugging, ad-hoc reproduction
- gstack runtime: repeatable QA, smoke, canary, benchmark

## Bundle Refresh
```powershell
python "tools/harness/build_context_bundle.py" --all
```

Use the generated bundle that matches the runner you are about to use.

These bundles are operator-facing reference artifacts. Cursor/Claude/Codex extension sessions do not auto-load them on their own; the operator must open or reference them explicitly. The only repo-local automatic bundle injection path is `tools/harness/run_codex.ps1`, which reads the selected bundle into its prompt.

## Runner Entry Points In Cursor
- Cursor built-in agent: `docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md`
- Cursor harness-internal work: `docs/harness/bundles/HARNESS_BUNDLE_CURSOR_HARNESS.md`
- Claude extension in Cursor: `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md`
- Claude harness-internal work: `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE_HARNESS.md`
- Codex extension / Codex CLI in Cursor: `docs/harness/bundles/HARNESS_BUNDLE_CODEX.md` + `tools/harness/run_codex.ps1`
- Codex harness-internal work: `docs/harness/bundles/HARNESS_BUNDLE_CODEX_HARNESS.md` or `run_codex.ps1` auto-routing
- Exploratory/manual browser work: Cursor browser MCP
- Repeatable smoke/QA browser work: generated gstack runtime assets after `setup --host codex`

The daily bundles are intentionally slimmed for token efficiency. Use the `_HARNESS` variants only when the task itself edits harness architecture, hooks, rules, bundles, or verification flows.

## Shared Task Classification
- `tools/harness/task_classifier.py` is the single deterministic classifier for Cursor prompt hooks, the Codex wrapper, and Claude/Codex plugin preflight.
- It returns `route_kind`, `level`, `context_mode`, runner bundle paths, RPI flags, user-direction flags, and resource hints as JSON.
- Direct preflight example:
```powershell
python "tools/harness/task_classifier.py" --profile auto --prompt "review tools/harness/run_codex.ps1" --json
```
- Plugin panels may not always execute repo hooks. When a Claude/Codex-in-Cursor panel does not show the auto-entry message, run the preflight command or use `run_codex.ps1` so the same classification is applied.

## Prompt Auto Entry In Cursor
- Cursor now uses `.cursor/hooks/before_submit_prompt.py` on `beforeSubmitPrompt`.
- The hook consumes the shared classifier and shows prompt-side intent (`review`, `implement`, `qa`, or `generic`) plus the shared `low / medium / high / top` task level.
- Matching prompts receive a short wrapper-first `agentMessage` automatically:
  - review -> `tools/harness/run_codex.ps1 -Profile review -Target ...`
  - implement -> `tools/harness/run_codex.ps1 -Profile implement -Plan ...`
  - qa -> `tools/harness/run_gstack_qa.ps1 -Url ... -Scenario ...`
- Harness/core/deploy implementation prompts also get an automatic RPI reminder because `-Profile implement` requires an approved plan/spec.
- This is prompt-time routing guidance only. It does **not** secretly run wrappers, and it does **not** auto-inject the full bundle body. Full bundle injection still happens only inside `run_codex.ps1`.

## Wave 3 Auto Level Routing
- `tools/harness/run_codex.ps1` calls `tools/harness/task_classifier.py` and uses its `low / medium / high / top` result.
- Default mapping:
  - `low` / `medium`: daily bundle
  - `high` / `top`: `_HARNESS` bundle
- `run_gstack_qa.ps1` keeps the daily Codex bundle by default, but override- or risk-driven promotion can still happen inside `run_codex.ps1`.
- Manual override is supported through `-AdditionalPrompt`:
  - fixed tag: `[level=top]`, `[레벨=최상]`
  - natural language: `이번 건 최상으로 진행`
- If auto-classification lands on `high` or `top` and the operator tries to downgrade it, non-interactive execution must include `-AllowRiskyLevelOverride`.
- Wrapper output is ASCII-safe for PowerShell 5 compatibility: `Level`, `AutoLevel`, `Override`, `RiskAck`.

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
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "tools/harness/build_context_bundle.py" -ContextMode harness -DryRun
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "docs/AI_STATUS.md" -AdditionalPrompt "[level=top]" -DryRun
```

## Current Phase 2 Boundary
- `tools/harness/setup_gstack.ps1`: detection/reporting only
- `tools/harness/import_gstack_source_slice.py`: repeatable importer for the pinned setup/host-config slice, static runtime assets, and build/generated-skill source layer
- `tools/harness/run_codex.ps1`: Codex CLI wrapper for review / implement / QA prompts
- `tools/harness/run_gstack_qa.ps1`: QA preflight that delegates to `run_codex.ps1`
- `.agents/skills/gstack/VENDOR.md`: vendor boundary contract
- `.agents/skills/gstack/upstream/SNAPSHOT.md`: pinned upstream docs snapshot (`04b709d91a3f10efa1c816c6ddb4c8cafa735da8`)
- `.agents/skills/gstack/upstream/AGENTS.md`: upstream skill inventory snapshot
- `.agents/skills/gstack/upstream/LICENSE`: upstream MIT license text
- `.agents/skills/gstack/setup`: pinned upstream setup entrypoint source
- `.agents/skills/gstack/hosts/*.ts`, `.agents/skills/gstack/scripts/host-config*.ts`: pinned host-config source slice
- `.agents/skills/gstack/ETHOS.md`, `review/*`, `qa/*`, `gstack-upgrade/*`: imported static runtime asset subset
- `.agents/skills/gstack/bin/*`, `browse/*`, `design/*`, `scripts/discover-skills.ts`, `scripts/gen-skill-docs.ts`, `scripts/resolvers/*`, `**/SKILL.md.tmpl`: imported build/generated-skill source layer

Phase 2 now includes a pinned upstream documentation snapshot, the exact repo-local `setup` entrypoint source, the host-config slice that defines Codex/Cursor/Claude wiring, the static runtime asset subset for `review`, `qa`, `gstack-upgrade`, and `ETHOS`, the build/generated-skill source layer (`bin`, `browse`, `design`, resolvers, and templates), and a completed Windows `setup --host codex --no-prefix` run. QA is modeled correctly as a Codex skill flow rather than a fake `gstack qa` binary. Wrapper-driven Codex runs now force `codex exec -s workspace-write` so generated gstack skills can invoke their runtime commands instead of inheriting an arbitrary global sandbox default.

## Current Windows Runtime Gate
- `git`: required
- `node`: required
- `bun`: required
- `Git Bash` or configured `WSL`: one of them required for upstream setup on Windows
- repo-local `setup` entrypoint: present at `.agents/skills/gstack/setup`
- normalized Windows command form: `& "C:\Program Files\Git\bin\bash.exe" -lc "cd '/c/.../.agents/skills/gstack' && bash ./setup --host codex --no-prefix"`
- static runtime assets: present for `ETHOS.md`, `review/*`, `qa/*`, and `gstack-upgrade/*`
- build/generated-skill source layer: present for `bin/*`, `browse/*`, `design/*`, `scripts/discover-skills.ts`, `scripts/gen-skill-docs.ts`, `scripts/resolvers/*`, and `**/SKILL.md.tmpl`
- `codex`: installed and required for wrapper-driven review/implement/QA execution
- repo-local QA skill: expected under `.agents/skills/gstack/qa/`; generated/linked variants may also appear under `.agents/skills/gstack-qa/` or `.agents/skills/gstack/.agents/skills/gstack-qa/`
- setup-generated or linked QA skill variants are local runtime artifacts and may be gitignored even when the canonical vendored `qa/` source is present
- generated Codex skills: present under `.agents/skills/gstack/.agents/skills/`
- compiled browse binary: present under `.agents/skills/gstack/browse/dist/browse.exe`

## Vendor Rule
- Keep upstream gstack content inside `.agents/skills/gstack/`
- Do not rewrite FOMS policy into vendored upstream files
- Apply FOMS-specific behavior through wrapper scripts, bundles, rules, and guides

## Verification
- App import success string: `APP_OK`
- Shared workflow: `.agents/workflows/verify-result.md`
- Scripted baseline: `python tools/harness/verify_result.py --json`
- Harness bundles: regenerate after policy or plan changes

## Daily Use Examples
### Cursor built-in agent
- Start from `docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md`
- Use Cursor browser MCP for exploratory or manual browser work
- For harness-internal changes, switch to `docs/harness/bundles/HARNESS_BUNDLE_CURSOR_HARNESS.md`

### Claude extension in Cursor
- Start from `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md`
- Open `CLAUDE.md` only when editing or verifying the Claude-only source policy text
- After meaningful edits, run `python "tools/harness/verify_result.py" --json`
- For harness-internal changes, switch to `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE_HARNESS.md`

### Codex review / implement / QA
```powershell
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "AGENTS.md"
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile implement -Plan "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md"
powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke"
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "tools/harness/build_context_bundle.py" -AdditionalPrompt "[level=low]" -NonInteractive -AllowRiskyLevelOverride
```

`run_codex.ps1` now auto-classifies the task first, then selects the Codex bundle. Harness-related reviews/plans land on `high` or `top` unless the operator explicitly overrides them.

### Bundle refresh + verification baseline
```powershell
python "tools/harness/build_context_bundle.py" --all
python "tools/harness/verify_result.py" --json
```

## Fallback Paths
- Bundle looks stale or runner guidance disagrees: run `python "tools/harness/build_context_bundle.py" --all` first
- Wrapper says QA skill is missing: confirm `.agents/skills/gstack/qa/SKILL.md` exists, then re-run `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf`
- Browser task is exploratory or manual: use Cursor browser MCP, not gstack runtime
- Git Bash / WSL bridge looks broken: re-run `setup_gstack.ps1 -WhatIf` and inspect shell-bridge output before attempting real setup
- Spec-bound verification is required but no spec is found: create or point `tools/harness/verify_result.py --spec ...` at the correct `*_SPEC.md` file before closing the task

## Indexing Rules
- New cross-session technical decisions: record in `docs/harness/policy/DECISIONS.md`
- New durable analysis, evolution, incident, or long-lived plan docs: add an entry to `docs/ARCHIVE_INDEX.md`
- Session-local working files such as `docs/context/analysis/task_plan.md`, `docs/context/analysis/findings.md`, and `docs/context/analysis/progress.md` do not need archive index entries
