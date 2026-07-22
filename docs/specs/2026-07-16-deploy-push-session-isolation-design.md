# Deploy Push Session Isolation — Design

> 작성일: 2026-07-16 | 상태: ✅ 완료 (Phase 0 구현)  
> 근거 사고: 2026-07-16 12:37 `origin/deploy` 푸시가 알림 세션 커밋(`93398eb4`)과 타 창 WD 계산기 커밋(`289137e7`)을 한 번에 반영

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물

여러 LLM 작업 창이 **동일 워킹트리·`deploy` 브랜치**를 공유해도, `git push`로 스테이징에 올릴 때 **묵시적으로 타 세션 미검증 커밋이 동반 반영되지 않게** 한다.

- Push 직전 범위(`origin/deploy..HEAD`)를 검사한다.
- 타 세션 SHA / 세션 불명 / 레저 누락이면 **ask**(하드 deny 아님).
- 사용자는 **전체 포함 승인** 또는 **자기 몫만**을 명시 선택한다.
- 「자기 몫만」은 공유 트리에서 HEAD 전체를 push하지 않고, **임시 worktree + 자기 SHA cherry-pick + `HEAD:deploy` push**로 수행한다(production 승격 패턴과 대칭).

### 1.2 기능 요구사항

1. **Session ledger**: 커밋 성공 시 현재 `session_id` → SHA 목록에 append(중복 무시).
2. **Push scope 검사**: `git push`가 `deploy`(또는 `HEAD:deploy` 등 deploy 도달 refspec)를 향할 때만 적용.
3. **판정**
   - scope가 비어 있음 → allow
   - scope ⊆ 현재 세션 ledger → allow
   - 그 외(foreign / unknown / ledger 없음) → ask
4. **Ask UX**: foreign·unknown SHA와 subject를 보여주고 선택지 2개 — `전체 포함 승인` / `자기 몫만`.
5. **Own-only runner**: `c:/tmp/foms-deploy-own-*` worktree를 `origin/deploy` 기반으로 생성 → 자기 SHA만 cherry-pick → push → 정리(충돌 시 보존·중단).
6. **Cursor·Claude 공통**: 판정 SSOT는 `tools/harness/`; 훅은 동일 모듈 소비.
7. **문서**: `AGENTS.md` / `CLAUDE.md`에 deploy push 이원화·자기몫=임시 WT를 명시. production cherry-pick 규칙은 유지·교차 참조.

### 1.3 예외·제약 (비목표 포함)

- **적용 브랜치**: `deploy` plain push만. `production`·force는 기존 `guard_policy` 우선.
- **상시 창별 worktree 강제 아님** (Phase 1 후속, 선택 표준).
- **DB/포트 격리 아님** (Phase 2, 필요 시).
- author/이메일로 세션 구분하지 않음(이미 동일).
- dry-run push는 scope 게이트 생략(또는 allow).
- cherry-pick 충돌 시 임의 해결 금지 — 의존 커밋 포함 여부를 사용자에게 확인(production 규칙과 동일).
- 훅 판정 실패 시 deploy push를 묵시 allow로 swallow하지 않음 → **ask 격상 + 런타임 로그**.

### 1.4 합의된 정책 선택 (brainstorming)

| 항목 | 선택 |
|------|------|
| 강제 수준 | B — ask (confirm) |
| 세션 구분 | C — ledger 마커 + 없으면 범위 ask 폴백 |
| 승인 의미 | C — 이원화(전체 포함 / 자기 몫만) |
| 브랜치 범위 | A — `deploy`만 |
| 구현 접근 | 세션 레저 + guard ask (상시 worktree 강제 아님) |
| 자기 몫만 실행 | 임시 worktree + cherry-pick (토론 최종 결론) |

## 2. How — 어떻게 만드는가

### 2.1 아키텍처

```
[git commit 성공]
    → session_commit_ledger.append(session_id, sha)

[git push … deploy | HEAD:deploy]
    → deploy_push_scope.classify(range, session_id, ledger)
    → own-only  → allow
    → empty     → allow
    → else      → ask (라벨 + SHA 목록 + 선택지)
         ├ 전체 포함 승인 → 기존 공유 트리 push
         └ 자기 몫만     → push_own_session_commits.run(...)
                           (공유 트리 HEAD 전체 push 재차단)
```

### 2.2 구성 요소

| 구성 | 경로 | 책임 |
|------|------|------|
| Session ledger 모듈 | `tools/harness/session_commit_ledger.py` | JSON R/W, append, query by session |
| Ledger 파일 | `docs/harness/runtime/session_commit_ledger.json` | gitignore 런타임 상태 |
| Push scope | `tools/harness/deploy_push_scope.py` | `origin/deploy..HEAD` vs ledger 분류 |
| Guard 확장 | `tools/harness/guard_policy.py` | deploy push 시 scope → ask/allow |
| Commit 추적 | Cursor `after_shell_execution` / Claude 동등 경로 | commit 성공 시 ledger 갱신 |
| Own-only runner | `tools/harness/push_own_session_commits.py` | tmp worktree + cherry-pick + push |
| 테스트 | `tests/harness/test_session_commit_ledger.py`, `test_deploy_push_scope.py`, guard 회귀 | 단위·통합 |
| 문서 | `AGENTS.md`, `CLAUDE.md`, 본 design | 운영 규칙 |

### 2.3 Ledger 스키마

```json
{
  "sessions": {
    "<session_id>": {
      "shas": ["full-or-abbrev-sha"],
      "updated_at": "2026-07-16T12:36:16+09:00"
    }
  }
}
```

- `session_id`: 훅 payload의 `session_id` 또는 `conversation_id`. 없으면 `"unknown"` → deploy push는 항상 ask.
- SHA는 가능하면 full hex; 비교 시 abbrev prefix 매칭 허용(동일 unique prefix).

### 2.4 Own-only runner 절차

1. `git fetch origin deploy`
2. `git worktree add -B` 임시 브랜치 `c:/tmp/foms-deploy-own-<session8>-<pid>` (base `origin/deploy`)
3. 자기 SHA만 오래된 순 cherry-pick
4. 성공 시 `git push origin HEAD:deploy`
5. 성공 시 worktree remove + 브랜치 삭제
6. cherry-pick 충돌 시: 중단, worktree 보존, 의존 SHA 목록을 stderr/로그로 보고, exit ≠ 0

### 2.5 기존 가드와의 우선순위

1. force + 보호 브랜치 → deny (기존)
2. production 도달 → ask (기존)
3. deploy + scope foreign/unknown → ask (신규)
4. 그 외 → allow

### 2.6 Phase 1 / Phase 2 (후속, 본 Phase 0 비범위)

**Phase 1 — 선택적 창별 worktree (강제 아님)**  
독립·장시간·파일 겹침 위험 작업에 Cursor `/worktree` · Claude `--worktree` 사용. 동시 상한 2–3. `.worktreeinclude`로 `.env` 복사. 일상 한 줄/탐색은 공유 트리 유지.  
(2026 트렌드·YouTube·공식 문서 조사 + 찬성/반대/중립 토론 결론: 전창 강제는 FOMS에서 OneDrive·공유 PG·머지 병목으로 비효율.)

**Phase 2 — DB/포트 격리**  
마이그레이션 병렬이 실제 아플 때만 스키마 접두 또는 컨테이너.

**후속(2026-07-22) — production promote baseline 완전성**  
소유권 격리(A)와 별층: `promote_completeness.py`(파일 교집합 × `git cherry +`) + `promote_own_to_production.py`.  
정본: `docs/specs/2026-07-22-promote-completeness-design.md`.

## 3. Steps — 구현 순서 (고수준)

구현 세부 태스크는 brainstorming 승인 후 `writing-plans`로 `docs/plans/`에 분해한다. 고수준만:

1. ledger 모듈 + gitignore + 단위 테스트
2. deploy_push_scope + 단위 테스트 (오늘 사고 fixture: foreign SHA → ask)
3. guard_policy 배선 + 회귀 테스트
4. commit 성공 시 ledger 기록 훅
5. own-only runner + 통합 테스트 (임시 remote)
6. AGENTS.md / CLAUDE.md 문구
7. DECISIONS.md 한 줄 기록

## 4. 검증 기준

- [ ] `pytest tests/harness` — ledger·scope·guard·own-only 신규/회귀 통과
- [ ] 오늘 사고 패턴 재현 fixture: 타 세션 SHA 포함 deploy push → ask (allow 아님)
- [ ] own-only 경로: 자기 SHA만 원격 tip, 타 SHA 미반영
- [ ] cherry-pick 충돌: non-zero, worktree 잔존, 임의 해결 없음
- [ ] production/force 기존 동작 불변
- [ ] `python -c "import app; print('APP_OK')"` → `APP_OK`
- [ ] 수동: 다창 미푸시 1건 두고 deploy push 시 ask 메시지에 SHA·선택지 노출

## 5. 참고

- 사고 증거: `origin/deploy` reflog 2026-07-16 12:37 `0902c799`→`93398eb4` (포함 `289137e7`+`93398eb4`); 에이전트 트랜스크립트 `ae51c0fc-…` “함께 푸시”
- 기존 SSOT: `tools/harness/guard_policy.py`, `.cursor/hooks/guard_shell.py`, production cherry-pick (`AGENTS.md`)
- 런타임 경로: `tools/harness/paths.py` → `docs/harness/runtime/`
- 토론: 찬성 worktree 강제 / 반대 Phase0만 / 중립 21:21 → 최종 **Phase0 + 자기몫 임시 WT + Phase1 선택 worktree**

## 6. Spec self-review (작성 시)

- Placeholder(TBD/TODO) 없음.
- Phase 0 vs Phase 1 경계 명시(상시 worktree 강제 배제).
- fail-open: deploy push는 ask 격상(완전 swallow 금지) — AGENTS.md 훅 정책과 정합.
- 「자기 몫만」실행 경로가 공유 트리 push와 분리되어 모호성 없음.
