# Task Plan: Cursor·Claude·Codex Harness Engineering

## Goal
Execute the approved harness-engineering master plan phase by phase so Cursor, Claude, and Codex share one coherent FOMS policy and verification system.

## Current Phase
Post-audit harness hardening complete

## Phases

### Phase 0: Policy Alignment
- [x] Re-audit the master plan from macro to micro and micro to macro
- [x] Patch the plan with non-blocking corrections before execution
- [x] Align hooks, top-level docs, rules, and verification contracts
- **Status:** complete

### Phase 1: Bundle Generator Core
- [x] Define harness manifest and runner profiles
- [x] Build context bundle generator
- [x] Add harness tests for generated bundles
- **Status:** complete

### Phase 2: gstack Adapter Layer
- [x] Add repo-local gstack vendor zone
- [x] Create Windows-safe setup and QA wrapper scripts
- [x] Define overlay policy boundaries
- [x] Import static runtime asset subset
- [x] Import build/generated-skill source layer
- [x] Install required local runtimes (`bun`, `codex`)
- [x] Run repo-local `setup --host codex --no-prefix`
- [x] Generate Codex skills and compile Windows browse runtime
- **Status:** complete

### Phase 3: Runner UX Integration
- [x] Connect Codex wrapper to generated runtime with explicit `workspace-write` sandbox
- [x] Document Cursor-inside-Claude/Codex runner entrypoints
- [x] Update GDM/operator guidance for runner routing
- [x] Refresh generated bundles after runner-note updates
- [x] Re-verify Codex/QA dry-runs against refreshed bundles
- [x] Cursor/Claude extension presence 기준 동등 운영자 확인
- **Status:** complete

### Phase 4: Harness Verification
- [x] Add harness CI and drift checks
- [x] Add hook or workflow smoke coverage
- [x] Strengthen verification workflow
- **Status:** complete

### Phase 5: Operator Handoff
- [x] Finalize operator guide
- [x] Record archive/index updates
- [x] Prepare daily-use examples
- **Status:** complete

### Wave 3: Auto Level Routing
- [x] Final deep audit of the Wave 3 spec
- [x] Fix spec blockers before implementation
- [x] Implement `run_codex.ps1` auto level routing (`low / medium / high / top`)
- [x] Add override parsing and risky downgrade protection
- [x] Sync `run_gstack_qa.ps1` with Wave 3 routing rules
- [x] Update operator/policy documents for Wave 3
- [x] Add wrapper behavior tests and pass full harness verification
- **Status:** complete

### Post-Audit Harness Hardening
- [x] Re-read AI status, archive index, and decisions before hardening
- [x] Draft the post-audit hardening Spec and treat the user "계속" response as approval to proceed
- [x] Fix wrapper exit-code propagation and `db.py` risk classification
- [x] Harden `verify_result.py`, `spec_utils.py`, and post-task hook Spec contracts
- [x] Sync policy/docs wording, Wave 3 spec completion state, and regenerate generated bundles
- [x] Re-run harness verification and re-audit the fixed findings
- **Status:** complete

## Key Questions
1. Which policy files are the canonical source for all runners?
2. How should hook failures be logged without blocking developer flow?
3. Where is the exact boundary between Cursor browser MCP and gstack runtime?
4. How should Codex consume generated context on Windows in a repeatable way?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use Hybrid gstack + FOMS harness | Keeps FOMS governance while adding stronger QA/runtime patterns |
| Finish Phase 0 before gstack vendor work | Prevents building adapters on top of unstable policy |
| Use plan audits before execution | Lowers architectural drift before code changes |
| Do not start Phase 1 until Phase 0 runtime checks pass | Matches the approved phase gate and avoids policy drift |
| Use strict JSON syntax inside `.yaml` files for Phase 1 | Keeps planned filenames while avoiding a new YAML dependency |
| Pin upstream commit `04b709d91a3f10efa1c816c6ddb4c8cafa735da8` as a docs-first snapshot for Phase 2 | Locks the upstream reference now without prematurely enabling Bun/Node/browser runtime paths on Windows |
| Use `codex exec` as the generic non-interactive runner wrapper substrate | Official Codex CLI supports non-interactive execution and stdin prompts, which matches FOMS PowerShell wrapper needs |
| Materialize the pinned `setup` contract via a targeted source slice before importing the full runtime tree | Keeps Phase 2 auditable while removing the abstract-entrypoint blocker |
| Split the runtime subset into static assets first, build/generated assets second | Improves phase visibility and avoids pulling Bun-heavy parts before the contract is stable |
| Import the build/generated-skill source layer from the pinned local upstream checkout and skip compiled non-UTF8 artifacts | Preserves a minimal auditable vendor boundary while avoiding accidental binary import on Windows |
| Treat Cursor-installed Claude/Codex extensions as runner UX on top of the same generated harness bundles | Keeps IDE usage and CLI usage aligned under one policy graph |
| Force `codex exec -s workspace-write` in FOMS wrappers | Prevents repeatable QA/review flows from inheriting a restrictive read-only sandbox that blocks generated skill commands |
| Treat installed Cursor extension presence plus bundle/entrypoint verification as the Phase 3 equivalent operator confirmation | Cursor-hosted Claude/Codex runners do not expose a standalone CLI-style interactive dry-run contract inside the repo |
| Treat `.agents/skills/gstack/qa/SKILL.md` as the canonical repo-local QA skill path, with generated/linked variants as optional alternates | The vendored upstream tree exposes `qa/SKILL.md` directly, so wrapper detection must anchor on the real source path |
| Use `tools/harness/verify_result.py` as the scripted baseline for the shared verify-result workflow | Turns the APP_OK/spec-discovery contract into an executable step while leaving deeper review items manual |
| Track post-audit runtime/doc hardening in a dedicated follow-up Spec | Keeps the audit-fix batch auditable instead of silently mutating a completed Wave 3 record |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `UnicodeDecodeError` while importing build-source files | 1 | Root-caused to upstream compiled `bin/gstack-global-discover`; importer now skips non-UTF8 artifacts and continues with text source files only |
| WSL appeared available because `wsl.exe` existed, but no distro was configured | 1 | Preflight now checks usable WSL state and prefers explicit Git Bash discovery from the installed Git for Windows path |
| Windows browse runtime compiled to `browse.exe`, but preflight only checked `browse` | 1 | Preflight now accepts both `browse` and `browse.exe` so Windows readiness reports accurately |
| Phase 3 docs still said gstack browse was “not introduced yet” | 1 | Synced top-level policy docs to the completed runtime/setup state before starting Phase 4 |
| QA wrappers missed the actual vendor QA skill path `.agents/skills/gstack/qa/SKILL.md` | 1 | Added the canonical vendored skill path to wrapper detection and aligned the operator guide with the real repo layout |
| verify-result remained a documentation-only workflow | 1 | Added `tools/harness/verify_result.py`, tests, CI integration, and operator guide entrypoints |
| Post-Wave-3 audit found remaining wrapper/doc/spec drift | 1 | Started a dedicated post-audit hardening phase with its own Spec before applying follow-up fixes |

## Notes
- Re-read this file before each phase transition.
- Do not start the next phase until current phase verification and audit are complete.
- Post-plan optimization wave 1 (2026-04-05): unified recursive Spec resolution, aligned session-start RPI scope, and slimmed default runner bundles. See `progress.md` and `docs/context/DECISIONS.md`.
- Post-plan optimization wave 2 (2026-04-05): split dedicated `_HARNESS` bundles from daily bundles and added Codex auto-routing for harness-related targets/plans.
- Wave 3 (2026-04-05): added deterministic `low / medium / high / top` routing in `run_codex.ps1`, QA wrapper pass-through rules, manual override parsing, risky downgrade protection, and wrapper-level regression tests.
- Post-audit hardening (2026-04-05): follow-up fixes cover wrapper exit-code trust, deterministic Spec contracts, nested Spec reminder paths, RPI wording drift, and Wave 3 spec completion sync.
