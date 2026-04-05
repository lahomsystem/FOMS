# gstack Vendor Boundary

## Status
- State: pinned upstream documentation snapshot + setup/host-config source slice imported
- Upstream: `https://github.com/garrytan/gstack`
- Local path: `.agents/skills/gstack/`
- Import strategy: copy-vendor snapshot first, targeted source slice second, subtree later if repeated upstream sync becomes necessary
- Pinned upstream commit: `04b709d91a3f10efa1c816c6ddb4c8cafa735da8`

## Imported Upstream State
- `upstream/SNAPSHOT.md`: FOMS-side pinned snapshot notes and integration rules
- `upstream/AGENTS.md`: upstream skill inventory and build conventions
- `upstream/LICENSE`: upstream MIT license text
- `setup`: pinned upstream setup entrypoint source
- `package.json` / `VERSION`: pinned build metadata for the imported slice
- `hosts/*.ts`: pinned host registry/config for Cursor, Claude, Codex, and related hosts
- `scripts/host-config.ts` / `scripts/host-config-export.ts`: pinned host-config support source for `setup`
- Current vendor import is **not** a full runtime source tree yet
- The pinned repo-local setup entrypoint for later runtime enablement is `bash .agents/skills/gstack/setup --host codex`

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
1. Import the runtime asset subset required by `setup --host codex` (`bin/`, `browse/`, `review/`, `qa/`, `gstack-upgrade/`, templates or generated skills).
2. Decide whether that subset remains smaller/cleaner than a full upstream source subtree.
3. Keep FOMS overlays outside vendored files whenever possible.
4. Do not enable non-dry-run wrappers until the runtime path is pinned in docs and scripts.

## Notes
- Browser ownership stays unchanged:
  - Cursor browser MCP: exploration, manual debugging
  - gstack runtime: repeatable QA, smoke, canary, benchmark
- Upstream `/qa` is a **skill flow**, not a standalone `gstack qa` terminal subcommand.
- In FOMS, repeatable QA is currently modeled as `run_gstack_qa.ps1` -> `run_codex.ps1` -> `codex exec` + repo-local gstack QA skill.
- `setup_gstack.ps1 -WhatIf` now validates the repo-local `setup` entrypoint and prints the normalized WSL/Git Bash command form.
- Even after source-slice import, Phase 2 PowerShell scripts stay in detection and dry-run mode until the runtime assets and local tools are present.
