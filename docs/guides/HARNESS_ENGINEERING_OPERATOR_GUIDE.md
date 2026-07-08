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

These bundles are operator-facing reference artifacts. Cursor/Claude/Codex extension sessions do not auto-load them on their own; the operator must open or reference them explicitly.

## Runner Entry Points In Cursor
- Cursor built-in agent: `docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md`
- Cursor harness-internal work: `docs/harness/bundles/HARNESS_BUNDLE_CURSOR_HARNESS.md`
- Claude extension in Cursor: `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md`
- Claude harness-internal work: `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE_HARNESS.md`
- Codex extension / Codex CLI in Cursor: `docs/harness/bundles/HARNESS_BUNDLE_CODEX.md`
- Codex harness-internal work: `docs/harness/bundles/HARNESS_BUNDLE_CODEX_HARNESS.md`
- Exploratory/manual browser work: Cursor browser MCP
- Repeatable smoke/QA browser work: gstack browse/qa skills invoked in a Claude/Cursor session

The daily bundles are intentionally slimmed for token efficiency. Use the `_HARNESS` variants only when the task itself edits harness architecture, hooks, rules, bundles, or verification flows.

## Task Level And RPI Judgment
- The former shared task classifier (`task_classifier.py`), prompt auto-entry hooks, and the Codex wrapper chain (`run_codex.ps1` / `run_gstack_qa.ps1`) were retired on 2026-07-08 (`docs/harness/policy/DECISIONS.md`).
- Task level and RPI judgment follow the documented rules (CLAUDE.md session-start protocol, AGENTS.md core-change protocol).
- Core-change gates are enforced in code by the Stop hook, `scripts/ops/pre_push_smoke.ps1`, and branch protection.

## Phase 2 Scripts
### gstack setup preflight
```powershell
powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf
```

This script is **validation only** in Phase 2. It does not execute upstream `./setup`.

## Current Phase 2 Boundary
- `tools/harness/setup_gstack.ps1`: detection/reporting only
- `tools/harness/import_gstack_source_slice.py`: repeatable importer for the pinned setup/host-config slice, static runtime assets, and build/generated-skill source layer
- `.agents/skills/gstack/VENDOR.md`: vendor boundary contract
- `.agents/skills/gstack/upstream/SNAPSHOT.md`: pinned upstream docs snapshot (`04b709d91a3f10efa1c816c6ddb4c8cafa735da8`)
- `.agents/skills/gstack/upstream/AGENTS.md`: upstream skill inventory snapshot
- `.agents/skills/gstack/upstream/LICENSE`: upstream MIT license text
- `.agents/skills/gstack/setup`: pinned upstream setup entrypoint source
- `.agents/skills/gstack/hosts/*.ts`, `.agents/skills/gstack/scripts/host-config*.ts`: pinned host-config source slice
- `.agents/skills/gstack/ETHOS.md`, `review/*`, `qa/*`, `gstack-upgrade/*`: imported static runtime asset subset
- `.agents/skills/gstack/bin/*`, `browse/*`, `design/*`, `scripts/discover-skills.ts`, `scripts/gen-skill-docs.ts`, `scripts/resolvers/*`, `**/SKILL.md.tmpl`: imported build/generated-skill source layer

Phase 2 now includes a pinned upstream documentation snapshot, the exact repo-local `setup` entrypoint source, the host-config slice that defines Codex/Cursor/Claude wiring, the static runtime asset subset for `review`, `qa`, `gstack-upgrade`, and `ETHOS`, the build/generated-skill source layer (`bin`, `browse`, `design`, resolvers, and templates), and a completed Windows `setup --host codex --no-prefix` run. QA is modeled correctly as a skill flow rather than a fake `gstack qa` binary: repeatable QA runs through the gstack browse/qa skills invoked in a Claude/Cursor session (the former `run_gstack_qa.ps1` -> `run_codex.ps1` Codex wrapper chain was retired on 2026-07-08).

## Current Windows Runtime Gate
- `git`: required
- `node`: required
- `bun`: required
- `Git Bash` or configured `WSL`: one of them required for upstream setup on Windows
- repo-local `setup` entrypoint: present at `.agents/skills/gstack/setup`
- normalized Windows command form: `& "C:\Program Files\Git\bin\bash.exe" -lc "cd '/c/.../.agents/skills/gstack' && bash ./setup --host codex --no-prefix"`
- static runtime assets: present for `ETHOS.md`, `review/*`, `qa/*`, and `gstack-upgrade/*`
- build/generated-skill source layer: present for `bin/*`, `browse/*`, `design/*`, `scripts/discover-skills.ts`, `scripts/gen-skill-docs.ts`, `scripts/resolvers/*`, and `**/SKILL.md.tmpl`
- `codex`: optional; used only for on-demand second opinions through the `gstack-codex` skill
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

### Repeatable QA and Codex second opinions
- Repeatable QA and release smoke: invoke the **gstack browse/qa skills** inside a Claude/Cursor session (Skill invocation, e.g. `/gstack-qa`, `/gstack-browse`) against the target URL/scenario.
- Codex second opinions (review/challenge/consult): use the on-demand **`gstack-codex` skill** instead of a standing wrapper.

### Bundle refresh + verification baseline
```powershell
python "tools/harness/build_context_bundle.py" --all
python "tools/harness/verify_result.py" --json
```

## Fallback Paths
- Bundle looks stale or runner guidance disagrees: run `python "tools/harness/build_context_bundle.py" --all` first
- gstack QA skill looks missing: confirm `.agents/skills/gstack/qa/SKILL.md` exists, then re-run `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf`
- Browser task is exploratory or manual: use Cursor browser MCP, not gstack runtime
- Git Bash / WSL bridge looks broken: re-run `setup_gstack.ps1 -WhatIf` and inspect shell-bridge output before attempting real setup
- Spec-bound verification is required but no spec is found: create or point `tools/harness/verify_result.py --spec ...` at the correct `*_SPEC.md` file before closing the task

## Indexing Rules
- New cross-session technical decisions: record in `docs/harness/policy/DECISIONS.md`
- New durable analysis, evolution, incident, or long-lived plan docs: add an entry to `docs/ARCHIVE_INDEX.md`
- Session-local working files such as `docs/context/analysis/task_plan.md`, `docs/context/analysis/findings.md`, and `docs/context/analysis/progress.md` do not need archive index entries
