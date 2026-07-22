# Production promote completeness (baseline) Spec
> 작성일: 2026-07-22 | 상태: 🟢 승인됨 (순차 구현 — CEO HOLD SCOPE)

## 1. What

### 1.1 최종 결과물
에이전트가 production 승격 전, **세션 소유 SHA만으로는 안 보이는 baseline 구멍**을
patch-id 인식으로 보고한다. 이어서 own-only promote runner가 같은 검사를 통과한 뒤
`c:/tmp` worktree + cherry-pick + `gh pr --base production` 한다.

### 1.2 기능 요구사항
1. **P0 `promote_completeness`**: 승격 대상 SHA 집합이 건드린 파일에 대해
   `origin/production..<sha> -- <files>` ∩ `git cherry +` − promote_set
   → missing deps. `git cherry -` = 이미 동등 패치(false positive 제거).
2. CLI: `--shas` / `--session-id`, `--base-ref`(기본 `origin/production`),
   `--json` 선택. exit 0=complete, 2=incomplete, 1=git/error.
3. **P1 `promote_own_to_production`**: push_own 미러. base=`origin/production`,
   성공 시 promo 브랜치 push + `gh pr create --base production`.
   기본은 completeness incomplete면 exit 2(중단). `--allow-incomplete`만 우회.
4. cherry-pick 충돌 → exit 3, worktree 보존, 자동 해결 금지.

### 1.3 예외/제약
- 세션 격리(A) 약화 금지. deploy HEAD 전체 merge 금지. production 직접 push 금지.
- rename/복사로 ancestry에 안 잡히는 의존은 잔여 위험(문서화만).
- Phase 1 창별 worktree 강제 비범위. feature-flag trunk 비범위.

## 2. How

### 2.1 수정 대상
| 파일 | 변경 |
|------|------|
| `tools/harness/promote_completeness.py` | 신규 분석 API+CLI |
| `tests/harness/test_promote_completeness.py` | 신규 TDD |
| `tools/harness/promote_own_to_production.py` | 신규 P1 runner |
| `tests/harness/test_promote_own_to_production.py` | 신규 |
| `AGENTS.md` / `CLAUDE.md` | promote preflight 한 줄 |
| `docs/harness/policy/DECISIONS.md` | 결정 기록 |
| `docs/specs/2026-07-16-…isolation…` §2.6 | Phase 후속 교차참조 |

### 2.2 아키텍처
- 기존 패턴: `push_own_session_commits.py` + `session_commit_ledger` sibling import.
- Completeness는 순수 분석(네트워크 fetch는 CLI 옵션/`--fetch`).
- P1만 `git fetch origin production` + `gh`.

### 2.3 영향
- guard_policy 자동 차단은 본 스펙 비범위(후속). 에이전트/문서 게이트.

## 3. Steps
- [ ] P0 테스트 → 구현 → AGENTS
- [ ] P1 테스트 → 구현
- [ ] DECISIONS + isolation design 교차참조
- [ ] 이중 최종 점검

## 4. 검증 기준
- [ ] pytest harness 신규+회귀 green
- [ ] fixture: missing dep → incomplete; cherry-pick 동등 후 → complete
- [ ] P1: mock gh, `--base production`, no `HEAD:production`
- [ ] `APP_OK`
