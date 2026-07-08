# gstack Vendor Boundary

## Status
- State: pinned upstream documentation snapshot + setup/host-config source slice + static runtime assets + build/generated-skill source layer imported + Windows `setup --host codex --no-prefix` verified locally
- Upstream: `https://github.com/garrytan/gstack`
- Local path: `.agents/skills/gstack/`
- Import strategy: copy-vendor snapshot first, targeted source slice second, subtree later if repeated upstream sync becomes necessary
- Pinned upstream commit: `c7ae63201ab193a7dc7fb7e0d81238645111ffac` (VERSION `1.58.1.0`)

## Imported Upstream State
- `upstream/SNAPSHOT.md`: FOMS-side pinned snapshot notes and integration rules
- `upstream/AGENTS.md`: upstream skill inventory and build conventions
- `upstream/LICENSE`: upstream MIT license text
- `setup`: pinned upstream setup entrypoint source
- `package.json` / `VERSION`: pinned build metadata for the imported slice
- `hosts/*.ts`: pinned host registry/config for Cursor, Claude, Codex, and related hosts
- `scripts/host-config.ts` / `scripts/host-config-export.ts`: pinned host-config support source for `setup`
- `ETHOS.md`: pinned runtime guidance referenced by upstream skills
- `review/*`: pinned review markdown assets
- `qa/*`: pinned QA skill source and references
- `gstack-upgrade/*`: pinned upgrade skill source and migrations
- `bin/*` (text scripts only): pinned command/runtime helper layer, excluding compiled binary artifacts
- `browse/*`: pinned browse source/bin/script layer required before local build
- `design/*`: pinned design source layer required before local build
- `scripts/discover-skills.ts`, `scripts/gen-skill-docs.ts`, `scripts/resolvers/*`: pinned generated-skill source layer
- `**/SKILL.md.tmpl`: pinned upstream skill templates used by generated skill docs
- Generated runtime outputs can now be materialized locally through the pinned setup flow; source-of-truth for vendored upstream content still remains the imported source/template layer
- The pinned repo-local setup entrypoint is `bash .agents/skills/gstack/setup --host codex --no-prefix`

## Rules
- Keep upstream gstack content inside this directory.
- Do not copy FOMS policy into vendored upstream files.
- Apply FOMS-specific behavior through:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.cursor/rules/*.mdc`
  - `tools/harness/*.ps1`
  - `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`

## Expected next import step
1. Keep setup-generated runtime outputs (`node_modules`, linked skills, per-host generated directories, compiled binaries) ignored so vendor source stays auditable.
2. Finish runner UX integration by refreshing generated harness bundles and runner guidance after the successful Codex setup path.
3. Decide whether the pinned source-layer strategy still stays smaller/cleaner than a full upstream source subtree after the first successful local build.
4. Add CI/drift checks so local setup success is re-verifiable without committing generated runtime outputs.

## Notes
- Browser ownership stays unchanged:
  - Cursor browser MCP: exploration, manual debugging
  - gstack runtime: repeatable QA, smoke, canary, benchmark
- Upstream `/qa` is a **skill flow**, not a standalone `gstack qa` terminal subcommand.
- In FOMS, repeatable QA is modeled as gstack browse/qa skills invoked directly in a Claude/Cursor session (the former `run_gstack_qa.ps1` -> `run_codex.ps1` Codex wrapper chain was retired on 2026-07-08; see `docs/harness/policy/DECISIONS.md`).
- `setup_gstack.ps1 -WhatIf` now validates the repo-local `setup` entrypoint, detects Git Bash from installed Git for Windows, and rejects unusable bare `wsl.exe` false positives.
- The build-source import intentionally skips compiled non-UTF8 artifacts such as upstream `bin/gstack-global-discover`.
