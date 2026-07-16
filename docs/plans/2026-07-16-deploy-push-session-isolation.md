# Deploy Push Session Isolation Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Block silent co-push of other sessions' commits on `git push … deploy` via session ledger + ask + own-only temp worktree cherry-pick.

**Architecture:** `session_commit_ledger` records SHAs per session_id; `deploy_push_scope` classifies `origin/deploy..HEAD`; `guard_policy` asks on foreign/unknown; `push_own_session_commits` cherry-picks own SHAs in `c:/tmp` worktree. Hooks pass `project_root` + `session_id`.

**Tech Stack:** Python 3, git CLI, pytest, existing Cursor/Claude shell hooks.

## Global Constraints

- deploy plain push only; production/force unchanged
- ask not deny; dual approval paths (full include / own-only)
- deploy push classify failure → ask + log (no silent allow swallow)
- Win11 PowerShell; Korean docs in AGENTS/CLAUDE
- Ledger file gitignored under `docs/harness/runtime/`

## Files

| File | Role |
|------|------|
| `tools/harness/session_commit_ledger.py` | JSON ledger R/W |
| `tools/harness/deploy_push_scope.py` | Range vs ledger classify |
| `tools/harness/push_own_session_commits.py` | Own-only runner |
| `tools/harness/guard_policy.py` | Wire deploy scope → ask |
| `.cursor/hooks/guard_shell.py` | Pass root + session_id |
| `.claude/hooks/guard_shell.py` | Pass root + session_id |
| `.cursor/hooks/after_shell_execution.py` | Record commits + keep CI marker |
| `.claude/hooks/post_push_watch.py` or new Bash PostToolUse helper | Record commits on Claude |
| `.gitignore` | Ignore ledger JSON |
| `AGENTS.md` / `CLAUDE.md` | Document dual path |
| `tests/harness/test_session_commit_ledger.py` | Unit |
| `tests/harness/test_deploy_push_scope.py` | Unit + incident fixture |
| `tests/harness/test_push_own_session_commits.py` | Integration temp remotes |
| `tests/harness/test_guard_policy.py` | Update deploy expectations |

---

### Task 1: Session ledger

- Create: `tools/harness/session_commit_ledger.py`
- Test: `tests/harness/test_session_commit_ledger.py`
- gitignore ledger path

### Task 2: deploy_push_scope

- Create: `tools/harness/deploy_push_scope.py`
- Returns: `empty` | `own` | `foreign` | `unknown` + label/sha lists
- Test incident pattern: two SHAs, session owns one → foreign

### Task 3: guard_policy + hooks

- `classify_command(cmd, *, project_root=None, session_id=None)`
- deploy target + not dry-run → scope check when root set; no root → ask
- Update CASES: context-free deploy → ask; hook tests with root+empty → allow via dedicated tests
- Wire both guard_shell hooks

### Task 4: Commit recording

- after_shell_execution: on successful `git commit`, append HEAD for session
- Claude PostToolUse Bash: same helper (extend post_push_watch or thin `record_commit_ledger.py` hook)

### Task 5: Own-only runner

- `push_own_session_commits.py` CLI + library
- Integration test with temp bare remote

### Task 6: Docs

- AGENTS.md / CLAUDE.md deploy push dual path
- Mark design spec status 승인됨

### Task 7: Verify

- `pytest tests/harness/test_session_commit_ledger.py tests/harness/test_deploy_push_scope.py tests/harness/test_push_own_session_commits.py tests/harness/test_guard_policy.py -q`
- `python -c "import app; print('APP_OK')"`
