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
- Upstream gstack `/qa` is a skill workflow, not a standalone `gstack qa` terminal subcommand.
- Upstream host config includes `cursor`, but the current upstream `setup` entrypoint is clearly wired first for `claude`, `codex`, `kiro`, and `factory`; FOMS should pin Codex repo-local integration first instead of assuming Cursor install parity.
- The exact upstream setup entrypoint can be pinned without a full subtree import by bringing in `setup`, `package.json`, `VERSION`, `hosts/*.ts`, and `scripts/host-config*.ts`.
- For Windows shell bridges, the runnable form should normalize paths first and invoke `bash ./setup --host codex`, not raw `./setup` against a Windows-style path.
- A useful next chunk after the setup slice is the static runtime asset layer: `ETHOS.md`, `review/*`, `qa/*`, and `gstack-upgrade/*`.
- The remaining heavy layer is the build/generated-skill surface: `bin/`, `browse/`, `design/`, broader scripts/resolvers, and generated `.agents/skills`.
- The build/generated-skill **source** layer can be imported safely from the pinned local upstream checkout before any Bun-backed execution.
- Upstream keeps a compiled `bin/gstack-global-discover` artifact alongside text scripts; a text-only importer must skip that non-UTF8 binary.
- In this workspace, Claude and Codex are primarily used as Cursor-installed VS Code extensions, so runner documentation must describe extension entrypoints as well as CLI wrappers.
- Git for Windows provides a usable `bash.exe` even when `bash` is not on PATH; preflight checks should derive Git Bash from the installed `git.exe` path instead of treating the machine as missing a shell bridge.
- On this machine, `wsl.exe` exists but no WSL distro is configured, so `Get-Command wsl` alone is a false-positive readiness signal.
- Bun-backed Windows setup produces `browse.exe` / `find-browse.exe` / `gstack-global-discover.exe`, so Windows readiness checks must not assume extensionless Unix-style binary names.
- Codex CLI login status is already available through the local ChatGPT-backed login, so wrapper verification can go beyond dry-run once sandbox defaults are made explicit.
- Codex wrapper-driven runs inherit the local Codex sandbox default unless FOMS passes one explicitly; the default read-only sandbox is too restrictive for generated gstack QA commands.
- Installed Cursor extension presence plus bundle/entrypoint availability is the practical “equivalent operator confirmation” for Phase 3, because Claude/Codex-in-Cursor do not expose a repo-local interactive dry-run primitive like the standalone wrappers do.
- The actual vendored repo-local QA skill lives at `.agents/skills/gstack/qa/SKILL.md`; wrapper detection must not rely only on generated or linked `gstack-qa` variants.
- `hook_runtime_log()` needs an stderr fallback to stay compatible with the project-wide “fail-open only if logged” policy when filesystem logging is unavailable.
- A lightweight scripted baseline for `verify-result` is enough to automate `APP_OK`, spec discovery, and verification-item collection without pretending the whole code review checklist can be reduced to one command.
- `verify_result.py` and `.cursor/hooks/post_task_quality_check.py` were using different “latest Spec” resolution rules, so reminders and scripted verification could point at different source documents.
- The largest avoidable token cost in daily harness usage was always-on injection of the harness master plan plus cross-runner policy files that the active runner did not own.
- After slimming the profiles and regenerating bundles, the default bundle footprint dropped to `251` lines / `15942` bytes for Cursor and `251` lines / `16043` bytes for Codex; Claude stayed larger at `399` lines / `24013` bytes because it intentionally keeps Claude-specific policy in its default bundle.
- The safest second-step optimization after slim daily bundles was not more trimming, but adding explicit `_HARNESS` expanded bundles for harness-internal tasks while keeping daily entrypoints lean.
- `run_codex.ps1` can distinguish harness-internal targets/plans from ordinary app work with path-based heuristics, which is enough to auto-route Codex reviews/implementation to the expanded harness bundle without touching QA defaults.
- After the split, Codex and Cursor daily bundles stayed at `251` lines while their harness-only variants grew to `758` lines; Claude daily stayed at `399` lines and Claude harness expanded to `906` lines.
- A non-zero native `codex exec` exit in PowerShell does not automatically fail the wrapper process; without explicitly returning `$LASTEXITCODE`, CI and calling scripts can see a false success.
- `db.py` is a DB core file in this repo but Wave 3 path heuristics do not currently classify it as `db/api/auth core path`.
- `verify_result.py` currently throws a raw traceback for an invalid `--spec` path because `resolve_spec_path()` exceptions are uncaught in `main()`.
- `spec_utils.py` chooses the latest spec by `mtime` only, which is vulnerable to cross-environment drift and non-deterministic tie behavior.
- `.cursor/hooks/post_task_quality_check.py` only keeps the latest spec basename, so nested specs are announced with the wrong `docs/specs/...` path.
- `AGENTS.md` already treats deployment and harness infrastructure as RPI core scope, but `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, and generated bundles still contain narrower DB/Auth/API wording in places.
- Some runner docs still read as if bundles are automatically loaded by Cursor or extensions; the real automatic bundle read path exists only inside `run_codex.ps1`, while extension sessions need explicit operator reference/opening.
- `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md` header and checklist state no longer match the implemented Wave 3 reality.

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
| Pin a docs-first upstream snapshot before enabling runtime execution | Preserves upstream intent and license now, while keeping Windows runtime activation gated behind a separate verification step |
| Treat Windows gstack runtime prerequisites as `node + bun + (Git Bash or WSL)` | Matches upstream guidance better than the earlier loose `node or bun` assumption and prevents false-readiness signals |
| Route repeatable QA through `codex exec` + repo-local gstack QA skill | Fixes the incorrect assumption that upstream exposes a `gstack qa` CLI and aligns the wrapper layer with actual upstream host semantics |
| Import a targeted upstream source slice before attempting full subtree vendorization | Materializes the exact `setup --host codex` contract while keeping Phase 2 smaller and easier to audit |
| Import static runtime markdown/migration assets before the Bun-backed build layer | Keeps the next step concrete and low-risk while exposing the true remaining blockers |
| Import the build/generated-skill source layer from the pinned local checkout before trying real Bun execution | Lets FOMS finish Phase 2 vendor pinning without pretending the Windows build path already works |
| Treat compiled non-UTF8 upstream artifacts as intentionally excluded from the source-layer importer | Prevents binary leakage into the repo-local vendor zone and keeps Phase 2 text-only and auditable |
| Use explicit runner-entry bundles for Cursor, Claude-in-Cursor, and Codex-in-Cursor | Aligns extension UX with the same harness graph instead of maintaining separate ad-hoc operator instructions |
| Force `codex exec -s workspace-write` from FOMS wrappers | Prevents local Codex defaults from silently downgrading wrapper runs into a read-only mode that blocks generated QA/runtime commands |
| Use a dedicated harness CI workflow for bundle drift and hook smoke | Keeps harness regressions visible without overloading the main app test workflow |
| Treat the vendored `qa/SKILL.md` path as canonical for repo-local QA detection | Fixes the false “QA skill missing” result after local setup and keeps wrapper preflight tied to the real upstream layout |
| Add hook subprocess smoke plus `APP_OK` contract tests in `tests/harness` instead of scripting full verify-result immediately | Closes the highest-value Phase 4 coverage gap with minimal harness-only risk |
| Script `verify-result` as a baseline command rather than a full static-analysis gate | Keeps the workflow trustworthy and auditable while avoiding shallow fake automation of manual review items |
| Centralize latest-Spec lookup in `tools/harness/spec_utils.py` | Keeps post-task reminders and scripted verification aligned on the same document-selection rule |
| Treat default runner bundles as daily-use slim contexts, not all-purpose archive dumps | Cuts token cost for common Cursor/Codex work while preserving manual access to full plan/policy sources when harness-internal work actually needs them |
| Split expanded harness context into dedicated `_HARNESS` profiles instead of re-bloating the daily bundles | Preserves low-cost day-to-day execution while keeping a first-class full-context path for harness internals |
| Let `run_codex.ps1` auto-select the harness bundle for harness-related targets/plans when `BundlePath` is not explicitly overridden | Reduces operator burden and keeps Codex reviews/implementation aligned with the right context size automatically |
| Implement Wave 3 routing as deterministic wrapper logic instead of an extra LLM classifier | Avoids paying an extra API call for routing while keeping the policy auditable and testable in PowerShell/Python |
| Keep wrapper console output ASCII-safe even though Korean override input is supported | PowerShell 5 script parsing is fragile with non-ASCII literals unless BOM handling is controlled; ASCII output avoids runtime/parser drift on Win11 |
| Keep `run_gstack_qa.ps1` on daily bundle by default, but stop forcing `-BundlePath` into `run_codex.ps1` | Preserves the low-cost QA default while still allowing Wave 3 risk/override promotion when needed |
| Treat the post-audit fix batch as a separate hardening phase with its own Spec | Makes the audit-fix work explicit and prevents completed Wave 3 records from hiding new runtime/doc drift |
| Make wrapper and verification-tool failures structured and deterministic before adding any new harness features | Runtime trust and document truthfulness are higher priority than further optimization |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Plan did not explicitly include rules and verify workflow in Phase 0 | Patched the plan before execution |
| Phase 0 verification was too weak for hook idempotency and policy consistency | Expanded verification checklist in the plan |
| Closing audit found residual policy drift (`AGENTS.md` RPI linkage, `verify-result` noise, spec sort, shell wording) | Fixed before closing Phase 0 |
| Initial Phase 1 implementation used an external YAML parser and non-plan output paths | Reworked generator to use strict JSON syntax in `.yaml` files and aligned outputs to `docs/context/HARNESS_BUNDLE_*.md` |
| Phase 2 needs real gstack vendor import before non-dry-run execution | Introduced `VENDOR.md` boundary and Win11-safe dry-run scripts first |
| Full upstream runtime import would over-couple Phase 2 to Bun/Node/browser build assumptions too early | Imported a pinned upstream documentation snapshot first and kept wrapper scripts explicitly preflight-only |
| Initial QA wrapper incorrectly assumed a global `gstack qa` executable | Replaced it with a Codex-driven wrapper model and documented that `/qa` is a skill flow |
| Runtime entrypoint was documented but not materialized in the vendor zone | Added a repeatable importer and brought in the pinned `setup` + host-config source slice |
| After entrypoint pinning, the remaining blocker surface was still too broad | Split it into static runtime assets vs Bun-backed build/generated-skill assets and imported the static layer first |
| Build-source import crashed with `UnicodeDecodeError` | Root-caused it to upstream compiled `bin/gstack-global-discover` and updated the importer to skip non-UTF8 artifacts |
| Preflight treated bare `wsl.exe` discovery as a valid shell bridge | Replaced it with a usable-WSL check and explicit Git Bash discovery logic |
| Preflight looked only for `browse/dist/browse`, which is wrong on Windows | Updated it to accept the actual Windows output path `browse/dist/browse.exe` as ready |
| Wrapper-driven Codex QA inherited a restrictive read-only sandbox | Updated `run_codex.ps1` to force `workspace-write` and added runner-entry documentation for Cursor-installed Claude/Codex flows |
| Phase 3 document set still contained “gstack browse not introduced yet” text after setup completed | Updated the policy docs and phase trackers before advancing to Phase 4 |
| Wrapper QA detection missed the actual vendored `qa/SKILL.md` path and could fail real QA execution | Added the canonical vendored path to both wrappers, improved bundle-path errors, and aligned the operator guide |
| Hook runtime logging could still fail silently when both repo and temp file writes failed | Added an stderr fallback in `shared_utils.hook_runtime_log()` |
| `verify-result` assumed a Spec always exists | Added a no-Spec fallback so baseline verification can still run cleanly |
| `verify-result` had no executable baseline for CI or operators | Added `tools/harness/verify_result.py`, harness tests, and a harness-CI step for the scripted baseline |
| Slim-bundle profile tests initially triggered a static import diagnostic in basedpyright | Switched the test helper to load `build_context_bundle.py` via `importlib.util.spec_from_file_location()` instead of a non-package import |
| `run_codex.ps1` picked up a PSScriptAnalyzer warning after the auto-routing refactor | Reused the base prompt array in the final prompt assembly so the helper variable is no longer dead code |
| Wave 3 spec still had audit blockers before implementation (`models.py` mismatch, override/precedence ambiguity, QA routing ambiguity) | Patched the spec, indexed it in `ARCHIVE_INDEX.md`, and linked it from the master plan before coding |
| PowerShell 5 failed to parse the first Wave 3 implementation because the script contained non-ASCII literals without an encoding-safe path | Rewrote `run_codex.ps1` to remain ASCII-only while still recognizing Korean override input via Unicode codepoint helpers |
| `run_gstack_qa.ps1` originally kept passing the default daily `-BundlePath`, which would have blocked Wave 3 auto-promotion inside `run_codex.ps1` | Changed the wrapper to validate the daily bundle by default but only pass `-BundlePath` when the operator explicitly sets one |
| Post-Wave-3 audit found runtime/doc/spec drift after the main implementation was already marked complete | Started `docs/specs/2026-04-05-harness-post-audit-hardening_SPEC.md` and separated the follow-up hardening batch from the completed Wave 3 execution record |
| `run_gstack_qa.ps1` failed the new exit-code propagation test when it invoked `run_codex.ps1` in-process | Switched the QA wrapper to launch the nested Codex wrapper through the current PowerShell host as a separate process, then forward that child exit code |

## Resources
- `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/hooks.json`
- `.cursor/hooks/*.py`
- `.cursor/rules/*.mdc`
- `.agents/workflows/verify-result.md`

## Visual/Browser Findings
- gstack runtime setup now completes on Windows with generated Codex skills and `browse.exe` present.
- Live wrapper-driven Codex QA is partially validated: the repo-local QA skill and browse runtime are discoverable, but deeper smoke scenarios still need follow-up hardening for nested prompt/orchestration quality.
- The harness now has an executable verification baseline (`verify_result.py`) plus operator-facing examples and fallback rules, so the handoff surface is no longer documentation-only.
- The next hardening batch should target trust boundaries first: wrapper exit codes, structured verify-result failures, deterministic spec resolution, and truthful operator wording.
- The completed hardening batch removed the highest-risk audit gaps without changing Wave 3 routing behavior itself; it made failure reporting, Spec handling, and runner instructions trustworthy.
