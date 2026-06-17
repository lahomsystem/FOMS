# gstack Upstream Snapshot

- Upstream repo: `https://github.com/garrytan/gstack`
- Pinned commit: `c7ae63201ab193a7dc7fb7e0d81238645111ffac` (VERSION `1.58.1.0`)
- Captured on: `2026-06-17`
- Scope: Phase 2 pinned documentation snapshot plus setup/host-config source slice, static runtime assets, and build/generated-skill source layer for FOMS harness integration; local Windows setup has now been verified against this pinned slice

## Included Files
- `AGENTS.md` - upstream skill inventory and build conventions
- `LICENSE` - upstream MIT license text
- `setup` - upstream setup entrypoint source
- `package.json` / `VERSION` - upstream build metadata pinned to the same commit
- `hosts/*.ts` - upstream host registry/config slice
- `scripts/host-config.ts` / `scripts/host-config-export.ts` - host-config support source
- `ETHOS.md` - upstream runtime guidance referenced by skills
- `review/*`, `qa/*`, `gstack-upgrade/*` - static runtime markdown/templates/migrations required by the next Codex-facing slice
- `bin/*` (text scripts only), `browse/*`, `design/*` - source layer required before local Windows build/runtime enablement
- `scripts/discover-skills.ts`, `scripts/gen-skill-docs.ts`, `scripts/resolvers/*` - generated-skill support source
- `**/SKILL.md.tmpl` - upstream skill templates that drive generated SKILL docs
- This `SNAPSHOT.md` - pinned commit, extracted architecture notes, and FOMS integration rules

## Intentionally Excluded For Now
- Generated `.agents/skills` outputs for any host remain local setup artifacts, not pinned snapshot source
- Generated per-host sidecar directories (`.agents/`, `.cursor/`, `.factory/`, `.kiro/`, `.openclaw/`, `.opencode/`, `.slate/`) remain local setup artifacts
- Compiled binaries (`browse/dist/`, `design/dist/`, upstream compiled `bin/gstack-global-discover`) remain local setup artifacts, not pinned snapshot source
- `node_modules/`, `bun.lock`, and linked root skill directories under `.agents/skills/gstack-*`

Reason: FOMS pins upstream intent, the exact setup entrypoint, the static runtime markdown/migration layer, and the build/generated-skill source layer in git. Setup-generated runtime outputs are reproducible local artifacts and should stay out of the pinned snapshot boundary.

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
The next implementation step after the successful local setup is Phase 3 runner UX integration: refresh generated bundles, document Cursor-installed Claude/Codex entrypoints, and keep setup-generated runtime outputs ignored while adding repeatable verification/drift controls.
