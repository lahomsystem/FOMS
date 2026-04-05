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
- [ ] Add repo-local gstack vendor zone
- [ ] Create Windows-safe setup and QA wrapper scripts
- [ ] Define overlay policy boundaries
- **Status:** in_progress

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

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| None yet | 1 | Re-audit completed before implementation |

## Notes
- Re-read this file before each phase transition.
- Do not start the next phase until current phase verification and audit are complete.
