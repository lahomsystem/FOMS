# gstack Upstream Snapshot

- Upstream repo: `https://github.com/garrytan/gstack`
- Pinned commit: `04b709d91a3f10efa1c816c6ddb4c8cafa735da8`
- Captured on: `2026-04-05`
- Scope: Phase 2 pinned documentation snapshot plus setup/host-config source slice for FOMS harness integration

## Included Files
- `AGENTS.md` - upstream skill inventory and build conventions
- `LICENSE` - upstream MIT license text
- `setup` - upstream setup entrypoint source
- `package.json` / `VERSION` - upstream build metadata pinned to the same commit
- `hosts/*.ts` - upstream host registry/config slice
- `scripts/host-config.ts` / `scripts/host-config-export.ts` - host-config support source
- This `SNAPSHOT.md` - pinned commit, extracted architecture notes, and FOMS integration rules

## Intentionally Excluded For Now
- Full upstream runtime source tree (`browse/`, `design/`, `bin/`, `review/`, `qa/`, `gstack-upgrade/`, skill directories)
- Compiled binaries (`browse/dist/`, `design/dist/`)
- Automatic `./setup` execution
- Runtime enablement inside FOMS wrappers

Reason: Phase 2 is still validating a Windows-safe integration boundary. FOMS now pins both upstream intent and the exact setup entrypoint, but runtime activation still waits until the remaining runtime asset subset and local tool assumptions are verified.

## Extracted Notes From Upstream README
- gstack positions itself as a repo-local skill/runtime pack for multiple AI coding agents, not Claude only.
- For Codex repo-local installs, upstream explicitly points to `.agents/skills/gstack` as the project path.
- Upstream expects `git`, `bun`, and on Windows also `node`.
- Upstream setup writes skills into per-host directories and uses `./setup --host <runner>` for host-specific installs.
- Windows guidance says the browse server falls back to Node.js because Bun has Playwright transport issues on Windows.

## Extracted Notes From Upstream Architecture
- Core runtime model is a long-lived browser daemon with localhost HTTP, not one browser launch per command.
- State is tracked via `.gstack/browse.json`; health checks are the primary liveness signal on Windows.
- Command latency target after warm start is sub-second.
- SKILL documents are generated from templates and should not be hand-edited when upstream source-of-truth is elsewhere.
- Upstream warns not to commit compiled `browse/dist/` and `design/dist/` binaries.

## Extracted Notes From Upstream CLAUDE.md
- Upstream requires bisectable commits and specific-file staging instead of broad `git add .`.
- Upstream treats project-specific commands as repo-owned configuration that should live in the project's own guidance file.
- Upstream expects browser interaction to route through the gstack browse skill, but FOMS intentionally keeps ad-hoc/manual browsing on Cursor browser MCP.

## FOMS Integration Rules
- FOMS policy source of truth stays in `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*.mdc`, `.agents/workflows/*.md`, and generated harness bundles.
- gstack remains a vendor/runtime dependency zone, not the top-level policy owner.
- Cursor browser MCP keeps ownership of exploration, reproduction, and manual debugging.
- gstack runtime is reserved for repeatable QA, smoke, canary, and benchmark flows.
- `tools/harness/setup_gstack.ps1` and `tools/harness/run_gstack_qa.ps1` must remain explicit about whether the repo only has a pinned snapshot or a runnable upstream runtime.

## Next Runtime Gate
The next Phase 2 implementation step is to import the minimum runtime asset subset required for `bash .agents/skills/gstack/setup --host codex`, or deliberately switch to a full upstream subtree if that proves smaller and safer.
