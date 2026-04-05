# gstack Vendor Boundary

## Status
- State: planned vendor boundary established
- Upstream: `https://github.com/garrytan/gstack`
- Local path: `.agents/skills/gstack/`
- Import strategy: copy-vendor snapshot first, subtree later if repeated upstream sync becomes necessary

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
1. Pin an upstream tag or commit.
2. Record the upstream revision here.
3. Copy the approved upstream snapshot into this directory.
4. Keep FOMS overlays outside vendored files whenever possible.

## Notes
- Browser ownership stays unchanged:
  - Cursor browser MCP: exploration, manual debugging
  - gstack runtime: repeatable QA, smoke, canary, benchmark
- Until upstream snapshot is imported, Phase 2 PowerShell scripts operate in detection and dry-run mode only.
