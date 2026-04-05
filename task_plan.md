# Task Plan: Cursor·Claude·Codex Harness Engineering

## Goal
Execute the approved harness-engineering master plan phase by phase so Cursor, Claude, and Codex share one coherent FOMS policy and verification system.

## Current Phase
Phase 2

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
- **Status:** in_progress (runtime asset subset import + local tool availability pending)

### Phase 3: Runner UX Integration
- [ ] Connect Cursor, Claude, and Codex runner flows
- [ ] Document runner-specific entrypoints
- [ ] Update GDM/operator guidance
- **Status:** pending

### Phase 4: Harness Verification
- [ ] Add harness CI and drift checks
- [ ] Add hook or workflow smoke coverage
- [ ] Strengthen verification workflow
- **Status:** pending

### Phase 5: Operator Handoff
- [ ] Finalize operator guide
- [ ] Record archive/index updates
- [ ] Prepare daily-use examples
- **Status:** pending

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

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| None yet | 1 | Re-audit completed before implementation |

## Notes
- Re-read this file before each phase transition.
- Do not start the next phase until current phase verification and audit are complete.
