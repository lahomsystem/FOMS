# Progress Log

## Session: 2026-04-05

### Phase 0: Policy Alignment
- **Status:** complete
- **Started:** 2026-04-05
- Actions taken:
  - Read execution skills and planning-file templates.
  - Re-audited the master plan via two independent subagents.
  - Patched the master plan to reflect audit findings before implementation.
  - Created `task_plan.md`, `findings.md`, and `progress.md` in the project root.
  - Implemented Phase 0 in parallel tracks: policy/rules alignment and hook/runtime alignment.
  - Resolved duplicate session-stop risk, fail-open logging, canonical `APP_OK`, shell ownership, and verification workflow consistency.
  - Ran final Phase 0 verification and closing audit.
- Files created/modified:
  - `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.cursor/rules/00-project-context.mdc`
  - `.cursor/rules/50-win11-shell.mdc`
  - `.agents/workflows/verify-result.md`
  - `.cursor/hooks.json`
  - `.cursor/hooks/session_stop.py`
  - `.cursor/hooks/auto_memory.py`
  - `.cursor/hooks/post_task_quality_check.py`
  - `.cursor/hooks/hook_payload_debug.py`
  - `.cursor/hooks/shared_utils.py`
  - `.cursor/hooks/cleanup_temp.py`
  - `.gitignore`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 1: Bundle Generator Core
- **Status:** complete
- Actions taken:
  - Defined versioned harness source registry in `tools/harness/manifest.yaml`.
  - Added runner profiles for `cursor`, `claude`, and `codex` in `tools/harness/profiles/`.
  - Implemented `tools/harness/build_context_bundle.py` with deterministic markdown generation and manifest/profile validation.
  - Added `tests/harness/test_context_bundle.py` and extended it to 11 passing checks.
  - Generated `docs/context/HARNESS_BUNDLE_CURSOR.md`, `HARNESS_BUNDLE_CLAUDE.md`, and `HARNESS_BUNDLE_CODEX.md`.
  - Ran Phase 1 audit, fixed generator dependency/schema issues, synchronized plan status, and regenerated bundles.
- Files created/modified:
  - `tools/harness/manifest.yaml`
  - `tools/harness/profiles/cursor.yaml`
  - `tools/harness/profiles/claude.yaml`
  - `tools/harness/profiles/codex.yaml`
  - `tools/harness/build_context_bundle.py`
  - `tests/harness/test_context_bundle.py`
  - `docs/context/HARNESS_BUNDLE_CURSOR.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE.md`
  - `docs/context/HARNESS_BUNDLE_CODEX.md`
  - `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`

### Phase 2: gstack Adapter Layer
- **Status:** complete
- Actions taken:
  - Phase 1 closed after audit, verification, and plan/bundle synchronization.
  - Audited Phase 2 boundaries in parallel for Windows-safe vendor and adapter design.
  - Created `.agents/skills/gstack/VENDOR.md` as the repo-local vendor boundary contract.
  - Added `tools/harness/setup_gstack.ps1` for Win11 prerequisite detection and `-WhatIf` preflight.
  - Added `tools/harness/run_gstack_qa.ps1` for URL/scenario validation and `-DryRun` QA contract.
  - Added `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` to document source-of-truth, browser ownership, bundle refresh, and Phase 2 entrypoints.
  - Verified both Phase 2 scripts via `powershell -NoProfile -File ... -WhatIf/-DryRun`.
  - Pinned upstream gstack HEAD to `04b709d91a3f10efa1c816c6ddb4c8cafa735da8`.
  - Imported a docs-first upstream snapshot into `.agents/skills/gstack/upstream/` (`SNAPSHOT.md`, `AGENTS.md`, `LICENSE`).
  - Updated Phase 2 wrappers to require the pinned snapshot before any non-dry-run path can proceed.
  - Tightened Windows runtime gating to match upstream expectations: `node + bun + (Git Bash or WSL)`.
  - Added `tools/harness/run_codex.ps1` to standardize review / implement / QA Codex CLI prompts around `HARNESS_BUNDLE_CODEX.md`.
  - Reworked `tools/harness/run_gstack_qa.ps1` to delegate QA through Codex + repo-local gstack QA skills instead of a nonexistent `gstack qa` binary.
  - Added `tools/harness/import_gstack_source_slice.py` to repeatably import the pinned upstream setup/host-config source slice.
  - Imported the pinned upstream `setup`, `package.json`, `VERSION`, `hosts/*.ts`, and `scripts/host-config*.ts` into `.agents/skills/gstack/`.
  - Corrected the printed Windows shell-bridge setup command to use normalized WSL/Git Bash paths plus `bash ./setup --host codex`.
  - Extended `tools/harness/import_gstack_source_slice.py` with `--include-runtime-static` to import static runtime assets.
  - Imported `ETHOS.md`, `review/*`, `qa/*`, and `gstack-upgrade/*` as the next Phase 2 runtime subset.
  - Updated preflight output to distinguish static runtime asset readiness from the still-missing generated Codex skill layer.
  - Extended `tools/harness/import_gstack_source_slice.py` with `--include-build-source` and a pinned local `--source-root` path for build/generated-skill source import.
  - Root-caused a `UnicodeDecodeError` during build import to upstream compiled `bin/gstack-global-discover` and updated the importer to skip non-UTF8 artifacts.
  - Imported the remaining Phase 2 build/generated-skill source layer: `bin/*` (text only), `browse/*`, `design/*`, discovery/resolver scripts, and `SKILL.md.tmpl` templates.
  - Updated preflight output to distinguish imported build-source readiness from the still-missing generated Codex skill layer and compiled browse binary.
  - Installed Bun (`1.3.11`) and Codex CLI (`0.118.0`) locally, confirmed Codex login status, and executed repo-local `setup --host codex --no-prefix` via explicit Git Bash.
  - Generated repo-local Codex skills, compiled Windows browse/runtime binaries (`browse.exe`, `find-browse.exe`, `gstack-global-discover.exe`), and installed Playwright Chromium through the pinned upstream setup flow.
  - Fixed Windows readiness detection bugs: Git Bash discovery from installed Git, usable-WSL validation, and `browse.exe` detection in preflight.
- Files created/modified:
  - `.agents/skills/gstack/VENDOR.md`
  - `.agents/skills/gstack/setup`
  - `.agents/skills/gstack/package.json`
  - `.agents/skills/gstack/VERSION`
  - `.agents/skills/gstack/ETHOS.md`
  - `.agents/skills/gstack/bin/*`
  - `.agents/skills/gstack/browse/*`
  - `.agents/skills/gstack/design/*`
  - `.agents/skills/gstack/hosts/*.ts`
  - `.agents/skills/gstack/review/*`
  - `.agents/skills/gstack/qa/*`
  - `.agents/skills/gstack/gstack-upgrade/*`
  - `.agents/skills/gstack/*/SKILL.md.tmpl`
  - `.agents/skills/gstack/scripts/host-config*.ts`
  - `.agents/skills/gstack/scripts/discover-skills.ts`
  - `.agents/skills/gstack/scripts/gen-skill-docs.ts`
  - `.agents/skills/gstack/scripts/resolvers/*`
  - `.agents/skills/gstack/upstream/SNAPSHOT.md`
  - `.agents/skills/gstack/upstream/AGENTS.md`
  - `.agents/skills/gstack/upstream/LICENSE`
  - `.gitattributes`
  - `tools/harness/import_gstack_source_slice.py`
  - `tools/harness/setup_gstack.ps1`
  - `tools/harness/run_codex.ps1`
  - `tools/harness/run_gstack_qa.ps1`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`

### Phase 3: Runner UX Integration
- **Status:** complete
- Actions taken:
  - Updated runner profiles so Cursor, Claude-in-Cursor, and Codex-in-Cursor point to their generated harness bundles explicitly.
  - Added Cursor runner-routing guidance to `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, and `.cursor/agents/grand-develop-master.md`.
  - Updated `tools/harness/run_codex.ps1` to force `codex exec -s workspace-write` and to steer PowerShell calls toward `-NoProfile`.
  - Updated `tools/harness/run_gstack_qa.ps1` dry-run messaging so it reflects preflight gating accurately after setup completion.
  - Updated the operator guide to document the completed Windows setup path and current runner entrypoints inside Cursor.
  - Regenerated `HARNESS_BUNDLE_CURSOR.md`, `HARNESS_BUNDLE_CLAUDE.md`, and `HARNESS_BUNDLE_CODEX.md` after runner-note/profile updates.
  - Re-verified Codex review dry-run and QA dry-run against the refreshed bundles.
  - Confirmed equivalent operator readiness for Cursor-hosted runners by verifying installed Claude/Codex extension assets plus matching local bundle and wrapper entrypoints.
- Files created/modified:
  - `CLAUDE.md`
  - `.cursor/rules/00-project-context.mdc`
  - `.cursor/agents/grand-develop-master.md`
  - `tools/harness/profiles/cursor.yaml`
  - `tools/harness/profiles/claude.yaml`
  - `tools/harness/profiles/codex.yaml`
  - `tools/harness/run_codex.ps1`
  - `tools/harness/run_gstack_qa.ps1`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 4: Harness Verification
- **Status:** complete
- Actions taken:
  - Added `.github/workflows/harness-ci.yml` for harness-only verification on `main` / `deploy` push and pull_request.
  - Added bundle line-ending normalization for `docs/context/HARNESS_BUNDLE_*.md` in `.gitattributes`.
  - Wired the harness workflow to compile Cursor hooks, run `tests/harness`, regenerate all harness bundles, and fail on bundle drift.
  - Re-audited Phases 0–4 and fixed the real QA-wrapper path bug by teaching both wrappers that `.agents/skills/gstack/qa/SKILL.md` is the canonical vendored QA skill location.
  - Hardened Phase 0/2 infrastructure after the audit: `hook_runtime_log()` now falls back to stderr, `import_gstack_source_slice.py` now uses a fetch timeout, Git-derived `bash.exe` is preferred over an arbitrary PATH `bash`, and bundle-path failures now stop with explicit messages.
  - Added `tests/harness/test_hooks_smoke.py` to cover hook registration contracts, subprocess smoke for all registered hook entrypoints, and the `APP_OK` verify-result baseline command.
  - Added `tools/harness/verify_result.py` plus `tests/harness/test_verify_result.py` to script the shared verification baseline (`APP_OK`, spec discovery, verification-item collection).
  - Updated `AGENTS.md`, `verify-result.md`, `CLAUDE.md`, the harness CI workflow, and the operator guide so the documented runtime/verification contracts match the now-verified behavior.
- Files created/modified:
  - `.github/workflows/harness-ci.yml`
  - `.gitattributes`
  - `.cursor/hooks/shared_utils.py`
  - `tools/harness/import_gstack_source_slice.py`
  - `tools/harness/setup_gstack.ps1`
  - `tools/harness/run_codex.ps1`
  - `tools/harness/run_gstack_qa.ps1`
  - `tests/harness/test_hooks_smoke.py`
  - `tools/harness/verify_result.py`
  - `tests/harness/test_verify_result.py`
  - `AGENTS.md`
  - `.agents/workflows/verify-result.md`
  - `CLAUDE.md`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 5: Operator Handoff
- **Status:** complete
- Actions taken:
  - Extended `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` with daily-use runner examples, bundle/verification examples, explicit fallback paths, and archive/indexing rules.
  - Closed the remaining plan/tracker items by reflecting the scripted verify-result baseline and operator-facing handoff guidance.
- Files created/modified:
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Post-Plan Optimization: Token-Efficient Daily Bundles
- **Status:** complete
- Actions taken:
  - Added `tools/harness/spec_utils.py` and unified latest-Spec discovery between `verify_result.py` and `.cursor/hooks/post_task_quality_check.py`.
  - Expanded `.cursor/hooks/session_start.py` so the RPI reminder explicitly covers harness-core changes (`Hooks/Rules/Agents/Verification`) as well as large feature work.
  - Slimmed daily runner profiles by removing the always-on harness master plan from all bundles and removing `CLAUDE.md` from Cursor/Codex default bundles.
  - Updated `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/agents/grand-develop-master.md`, and `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` so runner entry instructions match the slim-bundle policy.
  - Added `tests/harness/test_profile_contracts.py` plus recursive-Spec / session-start coverage in `tests/harness/test_hooks_smoke.py`.
  - Regenerated all harness bundles and recorded the new bundle sizes: Cursor `251` lines / `15942` bytes, Claude `399` lines / `24013` bytes, Codex `251` lines / `16043` bytes.
- Files created/modified:
  - `tools/harness/spec_utils.py`
  - `tools/harness/verify_result.py`
  - `.cursor/hooks/post_task_quality_check.py`
  - `.cursor/hooks/session_start.py`
  - `tools/harness/profiles/cursor.yaml`
  - `tools/harness/profiles/claude.yaml`
  - `tools/harness/profiles/codex.yaml`
  - `tests/harness/test_hooks_smoke.py`
  - `tests/harness/test_profile_contracts.py`
  - `CLAUDE.md`
  - `.cursor/rules/00-project-context.mdc`
  - `.cursor/agents/grand-develop-master.md`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `docs/context/DECISIONS.md`
  - `docs/context/HARNESS_BUNDLE_CURSOR.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE.md`
  - `docs/context/HARNESS_BUNDLE_CODEX.md`
  - `findings.md`
  - `progress.md`

### Post-Plan Optimization: Harness-Only Expanded Bundles
- **Status:** complete
- Actions taken:
  - Added dedicated expanded profiles: `cursor-harness`, `claude-harness`, and `codex-harness`.
  - Regenerated six bundles so daily work stays slim while harness-internal tasks can load `_HARNESS` variants on demand.
  - Updated `tools/harness/run_codex.ps1` with `ContextMode` support plus automatic harness-path detection so review/implement flows switch to `HARNESS_BUNDLE_CODEX_HARNESS.md` when the target or plan is harness-related.
  - Updated operator/policy docs to distinguish daily entry bundles from harness-internal entry bundles.
  - Expanded CI drift checking from the original three bundles to all `docs/context/HARNESS_BUNDLE_*.md` outputs.
  - Recorded the new generated bundle sizes: Cursor daily `251` lines / `16294` bytes, Cursor harness `758` lines / `35941` bytes, Claude daily `399` lines / `24654` bytes, Claude harness `906` lines / `44250` bytes, Codex daily `251` lines / `16550` bytes, Codex harness `758` lines / `36025` bytes.
- Files created/modified:
  - `tools/harness/profiles/cursor-harness.yaml`
  - `tools/harness/profiles/claude-harness.yaml`
  - `tools/harness/profiles/codex-harness.yaml`
  - `tools/harness/profiles/cursor.yaml`
  - `tools/harness/profiles/claude.yaml`
  - `tools/harness/profiles/codex.yaml`
  - `tools/harness/run_codex.ps1`
  - `.github/workflows/harness-ci.yml`
  - `CLAUDE.md`
  - `.cursor/rules/00-project-context.mdc`
  - `.cursor/agents/grand-develop-master.md`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `docs/context/DECISIONS.md`
  - `docs/context/HARNESS_BUNDLE_CURSOR_HARNESS.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE_HARNESS.md`
  - `docs/context/HARNESS_BUNDLE_CODEX_HARNESS.md`
  - `docs/context/HARNESS_BUNDLE_CURSOR.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE.md`
  - `docs/context/HARNESS_BUNDLE_CODEX.md`
  - `tests/harness/test_profile_contracts.py`
  - `findings.md`
  - `progress.md`

### Wave 3: Auto Level Routing
- **Status:** complete
- Actions taken:
  - Re-audited the Wave 3 spec with parallel reviewers and fixed the plan/verification mismatches before coding.
  - Approved and patched `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`, indexed it in `docs/ARCHIVE_INDEX.md`, and linked it from the master plan.
  - Rebuilt `tools/harness/run_codex.ps1` as a deterministic `low / medium / high / top` classifier with:
    - path/scope/verification heuristics
    - fixed-tag and natural-language override parsing
    - risky downgrade protection for non-interactive runs
    - daily vs `_HARNESS` bundle routing
    - level-aware prompt guidance
  - Fixed a PowerShell 5 parser failure by making the wrapper ASCII-safe while still recognizing Korean override input through Unicode codepoint helpers.
  - Updated `tools/harness/run_gstack_qa.ps1` so QA keeps the daily bundle by default without blocking Wave 3 promotions inside `run_codex.ps1`.
  - Added `tests/harness/test_run_codex_levels.py` to cover:
    - low daily routing
    - high harness routing
    - top override routing
    - Korean natural-language override parsing
    - risky downgrade protection
    - QA wrapper default-bundle behavior
  - Synced Wave 3 policy/guidance into `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/agents/grand-develop-master.md`, `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`, and `docs/context/DECISIONS.md`.
  - Regenerated all harness bundles and re-ran the full harness verification suite.
- Files created/modified:
  - `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`
  - `docs/ARCHIVE_INDEX.md`
  - `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
  - `tools/harness/run_codex.ps1`
  - `tools/harness/run_gstack_qa.ps1`
  - `tests/harness/test_run_codex_levels.py`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.cursor/rules/00-project-context.mdc`
  - `.cursor/agents/grand-develop-master.md`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `docs/context/DECISIONS.md`
  - `docs/context/HARNESS_BUNDLE_CURSOR.md`
  - `docs/context/HARNESS_BUNDLE_CURSOR_HARNESS.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE_HARNESS.md`
  - `docs/context/HARNESS_BUNDLE_CODEX.md`
  - `docs/context/HARNESS_BUNDLE_CODEX_HARNESS.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Post-Audit Harness Hardening
- **Status:** complete
- Actions taken:
  - Re-ran the audit evidence for wrapper failure handling, invalid `--spec`, runner wording drift, bundle-loading phrasing, and local runtime readiness.
  - Re-read `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, and `docs/context/DECISIONS.md` under the RPI research step before starting the fix batch.
  - Created `docs/specs/2026-04-05-harness-post-audit-hardening_SPEC.md` to track the audit-fix batch separately from completed Wave 3 implementation.
  - Updated planning files so the current phase is now explicit post-audit hardening rather than silently mutating the completed Wave 3 record.
  - Fixed wrapper exit-code trust by making `run_codex.ps1` return the native Codex exit code and by moving `run_gstack_qa.ps1` to a separate nested PowerShell process for child-wrapper execution.
  - Added `db.py` to the high-risk DB/API/auth path heuristics in `run_codex.ps1`.
  - Hardened `verify_result.py` to return structured failure JSON/text for invalid `--spec` instead of emitting a traceback.
  - Replaced mtime-only latest-spec selection with deterministic filename/path ordering in `tools/harness/spec_utils.py`.
  - Corrected nested spec reminder paths in `.cursor/hooks/post_task_quality_check.py`.
  - Synced `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/agents/grand-develop-master.md`, the operator guide, the master plan, and the Wave 3 spec so RPI scope and runner wording match the real harness behavior.
  - Regenerated all harness bundles and re-verified the full harness suite plus targeted dry-run evidence.
- Files created/modified:
  - `docs/specs/2026-04-05-harness-post-audit-hardening_SPEC.md`
  - `docs/ARCHIVE_INDEX.md`
  - `docs/context/DECISIONS.md`
  - `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`
  - `tools/harness/run_codex.ps1`
  - `tools/harness/run_gstack_qa.ps1`
  - `tools/harness/verify_result.py`
  - `tools/harness/spec_utils.py`
  - `.cursor/hooks/post_task_quality_check.py`
  - `.github/workflows/harness-ci.yml`
  - `tests/harness/test_run_codex_levels.py`
  - `tests/harness/test_verify_result.py`
  - `tests/harness/test_hooks_smoke.py`
  - `CLAUDE.md`
  - `.cursor/rules/00-project-context.mdc`
  - `.cursor/agents/grand-develop-master.md`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
  - `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
  - `docs/context/HARNESS_BUNDLE_CURSOR.md`
  - `docs/context/HARNESS_BUNDLE_CURSOR_HARNESS.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE.md`
  - `docs/context/HARNESS_BUNDLE_CLAUDE_HARNESS.md`
  - `docs/context/HARNESS_BUNDLE_CODEX.md`
  - `docs/context/HARNESS_BUNDLE_CODEX_HARNESS.md`
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Plan audit | Macro->micro + micro->macro | No blocking architecture failure | Conditional go with refinements applied | ✓ |
| Hook compile | `python -m compileall ".cursor/hooks"` | Exit 0 | Exit 0 | ✓ |
| Hook imports | Updated + remaining hook modules import | Import success | `HOOKS_IMPORT_OK`, `ALL_HOOKS_IMPORT_OK` | ✓ |
| Idempotency smoke | Duplicate `session_stop` prevention | Skip on second run | `IDEMP_OK` | ✓ |
| App import | `python -c "import app; print('APP_OK')"` | `APP_OK` | `APP_OK` | ✓ |
| Harness tests | `python -m pytest "tests/harness/test_context_bundle.py" -q` | All tests pass | `11 passed` | ✓ |
| Bundle generation | `python "tools/harness/build_context_bundle.py" --all` | Exit 0 + bundles written | Exit 0 | ✓ |
| gstack setup dry-run | `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf` | Exit 0 + preflight summary | Exit 0 | ✓ |
| gstack source-slice import dry-run | `python "tools/harness/import_gstack_source_slice.py" --dry-run` | Planned pinned file writes only | `14 files updated` preview | ✓ |
| gstack source-slice import | `python "tools/harness/import_gstack_source_slice.py"` | Pinned source slice written | `14 files updated` | ✓ |
| gstack static runtime import dry-run | `python "tools/harness/import_gstack_source_slice.py" --include-runtime-static --dry-run` | Static runtime subset preview | `13 files updated` preview | ✓ |
| gstack static runtime import | `python "tools/harness/import_gstack_source_slice.py" --include-runtime-static` | Static runtime subset written | `13 files updated` | ✓ |
| Codex review dry-run | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "AGENTS.md" -DryRun` | Exit 0 + prompt preview | Exit 0 | ✓ |
| Codex implement dry-run | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile implement -Plan "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md" -DryRun` | Exit 0 + prompt preview | Exit 0 | ✓ |
| gstack QA dry-run | `powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun` | Exit 0 + command preview | Exit 0 | ✓ |
| gstack snapshot gate | `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf` after snapshot import | Snapshot detected in preflight | `vendor snapshot - ...SNAPSHOT.md` | ✓ |
| gstack QA snapshot gate | `powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun` after snapshot import | Snapshot readiness shown in dry-run summary | `snapshot ready: True` | ✓ |
| gstack setup source gate | `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf` after source-slice import | Repo-local `setup` entrypoint detected | `setup entrypoint - ...\.agents\skills\gstack\setup` | ✓ |
| gstack static subset gate | `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf` after static import | Static runtime subset detected separately from generated skills | `runtime static subset - OK`, `generated codex skills - WARN` | ✓ |
| gstack build-source import dry-run | `python "tools/harness/import_gstack_source_slice.py" --include-runtime-static --include-build-source --dry-run` | Build-source subset preview without binary import failure | `118 files updated`, `bin/gstack-global-discover` skipped as binary | ✓ |
| gstack build-source import | `python "tools/harness/import_gstack_source_slice.py" --include-runtime-static --include-build-source` | Build-source subset written without binary import failure | `118 files updated`, `bin/gstack-global-discover` skipped as binary | ✓ |
| gstack build-source gate | `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf` after build import | Build source detected separately from generated skills and browse binary | `build source layer - OK`, `generated codex skills - WARN`, `browse binary - WARN` | ✓ |
| Bun install | `powershell -NoProfile -Command "irm bun.sh/install.ps1 | iex"` | Bun installed locally | `Bun 1.3.11 was installed successfully` | ✓ |
| Codex CLI install | `npm install -g @openai/codex` | Codex CLI on PATH | `@openai/codex@0.118.0`, `codex --version` OK | ✓ |
| Codex login check | `codex login status` | Logged-in local CLI | `Logged in using ChatGPT` | ✓ |
| gstack setup run | `bash ./setup --host codex --no-prefix` via Git Bash | Generated skills + browse runtime on Windows | `gstack ready (codex)` + browse/runtime compile output | ✓ |
| Windows setup gate | `powershell -NoProfile -File "tools/harness/setup_gstack.ps1" -WhatIf` after setup | Generated skills + browse runtime detected | `generated codex skills - OK`, `browse binary - OK` | ✓ |
| Codex sandbox probe | direct `codex exec` with `-s workspace-write` | External runtime commands usable under wrapper-selected sandbox | Command execution reached Codex tool path under `workspace-write` | ✓ |
| Bundle generation (runner UX refresh) | `python "tools/harness/build_context_bundle.py" --all` | Updated runner bundles written | Exit 0 | ✓ |
| Codex review dry-run (runner UX refresh) | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "AGENTS.md" -DryRun` | Updated prompt + sandbox preview | `codex exec -s workspace-write` shown | ✓ |
| gstack QA dry-run (runner UX refresh) | `powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun` | Updated QA preflight reflects ready setup path | `qa skill - True`, dry-run guidance updated | ✓ |
| Cursor extension confirmation | Extension asset files under `C:\Users\USER\.cursor\extensions` | Claude/Codex-in-Cursor equivalent operator confirmation | `claude-code-settings.schema.json`, `codex-api-*.js` found | ✓ |
| Hook compile smoke | `python -m compileall -q .cursor/hooks` | Hook Python files compile cleanly | Exit 0 | ✓ |
| Harness tests | `python -m pytest tests/harness -q` | Harness-focused tests pass | `19 passed` | ✓ |
| Bundle idempotency | `python "tools/harness/build_context_bundle.py" --all` twice with file hashes | Regeneration is stable within the dirty working tree | `BUNDLE_IDEMPOTENT` | ✓ |
| App import baseline | `python -c "import app; print('APP_OK')"` | Shared verification baseline still passes after harness changes | `APP_OK` | ✓ |
| QA wrapper path recheck | `powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun` | Canonical vendored QA skill detected | `qa source : True`, `qa skill : True` | ✓ |
| Slim-bundle tests | `python -m pytest "tests/harness/test_hooks_smoke.py" "tests/harness/test_profile_contracts.py" "tests/harness/test_verify_result.py" -q` | Recursive spec resolution + slim profile contracts pass | `13 passed` | ✓ |
| Hook compile (post-opt) | `python -m compileall -q ".cursor/hooks"` | Exit 0 | Exit 0 | ✓ |
| Verify-result baseline (post-opt) | `python "tools/harness/verify_result.py" --json` | Success true + APP_OK baseline | `"success": true` | ✓ |
| Slim bundle regeneration | `python "tools/harness/build_context_bundle.py" --all` | Exit 0 + slim bundles written | Exit 0 | ✓ |
| Slim bundle content gate | `rg "plan_harness_engineering_master|Harness engineering master plan|plus CLAUDE\\.md|\\+ \`CLAUDE\\.md\`" docs/context/HARNESS_BUNDLE_CURSOR.md docs/context/HARNESS_BUNDLE_CODEX.md docs/context/HARNESS_BUNDLE_CLAUDE.md` | No stale always-on plan or old Claude entry text | No matches found | ✓ |
| Full harness suite (post-opt) | `python -m pytest tests/harness -q` | All harness tests pass after optimization | `24 passed` | ✓ |
| Harness profile contracts | `python -m pytest "tests/harness/test_profile_contracts.py" -q` | Daily vs `_HARNESS` profile contracts pass | `6 passed` | ✓ |
| Codex auto harness routing | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "tools/harness/build_context_bundle.py" -DryRun` | Harness file review auto-selects `_HARNESS` bundle | `Context : harness`, `Bundle : ...HARNESS_BUNDLE_CODEX_HARNESS.md` | ✓ |
| Codex implement auto harness routing | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile implement -Plan "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md" -DryRun` | Harness plan implementation auto-selects `_HARNESS` bundle | `Context : harness`, `Bundle : ...HARNESS_BUNDLE_CODEX_HARNESS.md` | ✓ |
| Codex daily routing | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "models.py" -DryRun` | Non-harness review stays on daily bundle | `Context : daily`, `Bundle : ...HARNESS_BUNDLE_CODEX.md` | ✓ |
| QA wrapper daily context preservation | `powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun` | QA preflight still uses the daily Codex bundle path | `command : ...run_codex.ps1 -Profile qa ...`, `bundle ready : True` | ✓ |
| Full harness suite (wave 2) | `python -m pytest tests/harness -q` | All harness tests still pass after expanded-bundle split | `27 passed` | ✓ |
| Codex QA wrapper path recheck | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile qa -Url "https://example.com" -Scenario "erp-smoke" -DryRun` | Canonical vendored QA skill advertised in prompt | `QA skill : True`, `.agents/skills/gstack/qa/SKILL.md` shown | ✓ |
| verify-result baseline | `python "tools/harness/verify_result.py" --json` | Structured verification report with APP_OK baseline | `success: true`, `app_import.ok: true` | ✓ |
| verify-result tests | `python -m pytest tests/harness/test_verify_result.py -q` | Script contract tests pass | `5 passed` | ✓ |
| Wave 3 wrapper behavior tests | `python -m pytest tests/harness/test_run_codex_levels.py -q` | Wave 3 routing/override/QA wrapper contracts pass | `8 passed` | ✓ |
| Harness bundles regeneration (wave 3) | `python "tools/harness/build_context_bundle.py" --all` | Updated bundles written after Wave 3 doc changes | Exit 0 | ✓ |
| Full harness suite (wave 3) | `python -m pytest tests/harness -q` | All harness tests pass after Wave 3 | `35 passed` | ✓ |
| Hook compile (wave 3) | `python -m compileall -q .cursor/hooks` | Hook Python files compile cleanly | Exit 0 | ✓ |
| verify-result baseline (wave 3) | `python "tools/harness/verify_result.py" --json` | Shared verification baseline still passes after Wave 3 | `success: true` | ✓ |
| Codex top override dry-run | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "docs/AI_STATUS.md" -AdditionalPrompt "[level=top]" -DryRun` | Manual override promotes daily review to top/harness | `Level : top`, `Context : harness` | ✓ |
| QA wrapper dry-run (wave 3) | `powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun` | QA wrapper preserves daily default without forcing BundlePath into the Codex command preview | `level policy : daily bundle by default`, no `-BundlePath` in preview | ✓ |
| Targeted hardening regressions | `python -m pytest tests/harness/test_verify_result.py tests/harness/test_hooks_smoke.py tests/harness/test_run_codex_levels.py -q` | Modified wrapper/spec/hook contracts pass together | `24 passed` | ✓ |
| Full harness suite (post-audit hardening) | `python -m pytest tests/harness -q` | All harness tests pass after hardening | `41 passed` | ✓ |
| Hook compile (post-audit hardening) | `python -m compileall -q .cursor/hooks` | Hook Python files compile cleanly | Exit 0 | ✓ |
| verify-result success baseline (post-audit hardening) | `python tools/harness/verify_result.py --json` | Structured success report still passes | `success: true` | ✓ |
| verify-result invalid spec contract | `python tools/harness/verify_result.py --json --spec "docs/specs/DOES_NOT_EXIST_SPEC.md"` | Structured failure JSON without traceback | `success: false`, `error.kind: FileNotFoundError` | ✓ |
| `db.py` classification dry-run | `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "db.py" -DryRun` | DB core file promotes to high/harness | `Level : high`, `reason : db/api/auth core path` | ✓ |
| Bundle regeneration idempotency (post-audit hardening) | Python SHA256 compare before/after second `build_context_bundle.py --all` run | No generated-bundle mutation on repeat run | `BUNDLE_IDEMPOTENT` | ✓ |
| verify-result explicit hardening spec | `python tools/harness/verify_result.py --json --spec "docs/specs/2026-04-05-harness-post-audit-hardening_SPEC.md"` | Current hardening Spec resolves and passes | `success: true`, `spec.path: ...post-audit-hardening_SPEC.md` | ✓ |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-04-05 | No existing planning files | 1 | Created root-level planning files |
| 2026-04-05 | `UnicodeDecodeError` while importing build-source layer | 1 | Identified upstream compiled `bin/gstack-global-discover` as non-UTF8 and skipped compiled artifacts in the importer |
| 2026-04-05 | WSL false positive (`wsl.exe` present, distro absent) | 1 | Added usable-WSL detection and explicit Git Bash fallback/discovery |
| 2026-04-05 | Windows browse runtime reported missing after successful setup | 1 | Updated preflight to accept `browse.exe` as the Windows-ready binary |
| 2026-04-05 | Wrapper-driven Codex QA inherited read-only sandbox | 1 | Forced `codex exec -s workspace-write` in `run_codex.ps1` |
| 2026-04-05 | Phase 3 docs still claimed gstack browse was not introduced | 1 | Synced policy docs to the completed Windows setup/runtime state before starting Phase 4 |
| 2026-04-05 | QA wrapper candidates missed the real vendored `qa/SKILL.md` path | 1 | Added the canonical path to wrapper detection and re-verified dry-run readiness |
| 2026-04-05 | `verify-result` was still documentation-only | 1 | Added a scripted baseline, tests, CI integration, and operator-facing usage examples |
| 2026-04-05 | First Wave 3 `run_codex.ps1` draft failed under PowerShell 5 due to non-ASCII literals | 1 | Rewrote the wrapper to stay ASCII-safe and moved Korean override handling into Unicode codepoint helpers |
| 2026-04-05 | New QA-wrapper exit-code test failed because `run_gstack_qa.ps1` invoked `run_codex.ps1` in-process | 1 | Switched QA wrapper execution to a separate nested PowerShell process and forwarded the child exit code |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Post-audit hardening complete |
| Where am I going? | Await user review, commit, or next harness follow-up |
| What's the goal? | One coherent harness for Cursor, Claude, and Codex |
| What have I learned? | See `findings.md` |
| What have I done? | Closed the audit-fix batch with wrapper, verify-result, hook, CI, doc, and bundle hardening |
