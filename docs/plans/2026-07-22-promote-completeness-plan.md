# Promote Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or execute sequentially. Checkbox tasks.

**Goal:** Production promote 전에 patch-id 인식 baseline 구멍을 보고하고, own-only promote runner로 PR까지 만든다.

**Architecture:** P0 순수 분석 모듈(`promote_completeness`) → P1 runner가 사전검사 후 `origin/production` worktree cherry-pick → promo branch + `gh pr --base production`. 세션 격리·충돌 자동해결·deploy HEAD merge 금지.

**Tech Stack:** Python 3, git CLI, gh CLI (P1), pytest, sibling harness imports.

## Global Constraints
- Win11 PowerShell docs; production 직접 push 금지
- cherry-pick 충돌 = exit 3, worktree keep
- 한글 docstring; 타입 힌트

---

## Task 1: P0 failing tests

**Files:**
- Create: `tests/harness/test_promote_completeness.py`

- [ ] Write fixtures: bare remote, `production` base, deploy tip with dep→feat on same file
- [ ] Assert analyze(feat only) → incomplete, missing=dep
- [ ] Cherry-pick dep onto production (new SHA); assert analyze(feat) → complete (dep is cherry `-`)
- [ ] Analyze([dep,feat]) on empty prod gap → complete
- [ ] Run pytest — expect FAIL (no module)

## Task 2: P0 implement

**Files:**
- Create: `tools/harness/promote_completeness.py`
- Modify: `AGENTS.md`, `CLAUDE.md` (preflight one-liner)

- [ ] Implement `analyze_promote_completeness` + CLI
- [ ] Pytest green
- [ ] Manual: optional dry-run on real e300cb98 (smoke)

## Task 3: P1 failing tests + implement

**Files:**
- Create: `tools/harness/promote_own_to_production.py`
- Create: `tests/harness/test_promote_own_to_production.py`

- [ ] Test incomplete blocks without `--allow-incomplete`
- [ ] Test success path with mocked `gh` + no push to production ref
- [ ] Implement mirror of push_own
- [ ] Pytest green

## Task 4: Docs closeout

- [ ] `DECISIONS.md` entry
- [ ] Cross-link isolation design §2.6
- [ ] Dual final verification by main agent
