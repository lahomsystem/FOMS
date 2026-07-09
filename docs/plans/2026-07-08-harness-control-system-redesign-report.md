# FOMS 하네스 컨트롤 시스템 재설계 — 구축 전 보고서

> 작성: 2026-07-08 | **개정 v2 (동일자)** | 상태: **사용자 승인 대기 (RPI Plan 단계)**
> 방법: Worker 5명 병렬 정밀 감사(코드 리뷰 3 + 딥리서치 2) → 독립 검증 2회(red team 반박 감사 + 백지 원점 재평가) → Advisor 3자 대조 최종 판정
> 범위: `.claude/` · `.cursor/` · `tools/harness/` · `scripts/ops/` · `docs/harness/` · MCP · 스킬 · CI
> **v2 주의: §5 실행 계획은 §8(3자 검증 최종 계획)로 대체됨. §2 심각도 일부 재등급.**

---

## 1. 총평 (Executive Summary)

**진단: "주먹구구"라는 자기평가는 절반만 맞다.**

- **골격은 업계 정론과 일치**: AGENTS.md SSOT(2025.12 Linux Foundation AAIF 표준 채택), MCP 최소화(postgres·context7 — 2026 "도구 과다=컨텍스트 오염" 합의와 정확히 일치), 결정적 Stop 게이트 + pre-push 스모크(하네스 엔지니어링 표준 패턴), 분류 로직 SSOT 위임(task_classifier). 이 방향들은 버릴 게 아니라 지킬 자산.
- **문제는 3가지 축**:
  1. **안전 코드가 정책 문서보다 약하다** — production push 차단이 문서엔 있고 코드엔 구멍 (P0/P1 5건)
  2. **분류기가 사실상 오작동** — 일반 한국어 지시문에서 레벨이 랜덤 강등/승격 (P0, 금일 실사례 3회)
  3. **죽은 표면이 살아있는 표면을 압도** — 원샷 스크립트 ~17개 상주, 번들 6종 3,532줄(실질 콘텐츠 2종), gstack 57개 중 실사용 2개, 런타임 로그 git 오염 + 무한성장

**권고: 전면 재구축이 아니라 "안전 수술 → 다이어트 → 현대화" 3단계.** 업계 래칫 원칙(모든 컴포넌트는 막는 과거 실패 1건을 명명해야 생존) 기준으로 감량하면 유지보수 표면이 절반 이하로 준다.

---

## 2. 정밀 진단 — 검증된 결함 목록

### 2.1 P0 — 즉시 수정 (안전·오작동)

| # | 위치 | 결함 | 검증 |
|---|---|---|---|
| P0-1 | `tools/harness/task_classifier.py:531-534` | 한국어 레벨 오버라이드가 단일 음절 bare substring (`하`/`상`/`중` + `진행` 공존 시 발동). "총동원**하**여 진행"→low 강등, "**상**세하게 진행"→high 오승격. `진행`은 한국어 지시문에 상시 존재 → 사실상 랜덤 | Advisor 재현: 금일 세션 preflight 3회 오판(low→high→top 요동) + 코드 직독 |
| P0-2 | `.claude/hooks/guard_shell.py:127-132` | WARN 패턴(`git push --force`, `git reset --hard` 등)이 `{"decision":"approve"}` 출력 = **위험 명령 무확인 자동 승인**. 주석("사용자에게 확인")과 동작 불일치 | 코드 직독 확인 |
| P0-3 | `.cursor/hooks/guard_shell.py:28` | 강제푸시 DENY 브랜치 목록 `(main\|master\|deploy)` — **`production` 누락**. CLAUDE.md 절대규칙과 코드 드리프트 | Grep 확인 |

### 2.2 P1 — 높음

| # | 위치 | 결함 |
|---|---|---|
| P1-1 | `.claude/hooks/guard_shell.py:26,41-45` | 강제푸시 정규식이 `--force`가 브랜치명보다 앞일 때만 매치. `git push -f`, `git push origin production --force`, `--force-with-lease` 전부 미차단. plain `git push origin production`은 로그도 없이 통과 (문서 정책 미강제) |
| P1-2 | `task_classifier.py:121-147` | 고강도 한국어 어휘 공백 — "초정밀/총동원/모든 가용 자원/총력/정밀 감사"가 TOP/WIDE 키워드에 없음 → 오버라이드 없어도 auto가 low |
| P1-3 | `task_classifier.py:668-672` | 자연어發 오탐 강등이 **무경고 통과** (risky_ack는 auto≥high일 때만 발동) |
| P1-4 | `docs/harness/runtime/SESSION_LOG.md` (1,915줄) | session_start(블록+20개 로테이션)와 session_stop(테이블 행+무제한 append)이 **다른 포맷으로 같은 파일 기록** → 로테이션 무력화 + 파일 손상 + 무한 성장 |

### 2.3 P2 — 중간 (구조 부채)

- **런타임 로그 git 추적**: SESSION_LOG(229KB)·EDIT_LOG·SHELL_GUARD_LOG(×2벌)·COMPACT_CHECKPOINT 전부 추적 → 매 세션 워킹트리 오염(동시 세션 git 레이스 실사례의 원인 축)
- **SHELL_GUARD_LOG 경로 2벌**: Claude→`docs/context/`, Cursor→`docs/harness/logs/` — 감사 로그 분기
- **EDIT_LOG 포맷 충돌**: Cursor(`- \`file\``) vs Claude(`| 표 |`) 같은 파일에 교차 기록 → 상대 파서 실패
- **`track_edits.py:18,77-79`**: 트리 밖 편집(전역 메모리·스크래치패드)이 prefix 매칭 실패로 EDIT_LOG 오염
- **fail-open 규칙 절반만 적용**: guard_shell 로그실패 `except: pass`(무기록), track_edits·session_stop엔 hook_log 자체가 없음 — 프로젝트 절대규칙 위반
- **`run_codex.ps1:179-199,479-509`**: 경로 allowlist를 PowerShell에서 재구현 — task_classifier와 이중 SSOT
- **원샷 스크립트 상주**: tools/harness ~13개(ept_b8·gnv_b6·erp_beta·railway_db_gate·ptc), scripts/ops ~4개(simple_backup shim·add_geocode·verify_phase_d·prune_perf) — 완료 이니셔티브 잔재
- **테스트 공백**: Claude 훅 8개 중 quality_check만 테스트. P0-2·P1-4·track_edits 누수 전부 CI 그물 밖
- **번들 6종 3,532줄**: 소스 881줄의 3~4배 복제. Claude·Cursor는 네이티브 로딩과 중복 — 실효는 Codex 경로뿐인데 Codex는 휴면(7월 활동 0)

### 2.4 P3 — 위생

`.cursor/agents/`(빈 폴더), `.cursor/debug-f2330d.log`, stale `.cursor/artifacts/`, `.codex/` gitignore 미등록, CLAUDE_HOOK_LOG 로테이션 부재, settings.local.json 실험 잔재, DECISIONS.md 정렬 이탈 1건

### 2.5 건강 판정 (유지 자산)

- **Stop 게이트(quality_check)**: 결정적·테스트 완비 — 업계 표준 패턴 그대로
- **shared_utils UTF-8 정본화**: cp949 근본 방어 견고
- **perf 스킬 SSOT+포인터 구조**: 실측 결과 진짜 얇은 포인터 — 건강
- **MCP 2종 최소화**: 2026 합의 선취
- **훅 이중 구현 자체는 정당**: Cursor/Claude I/O 계약이 물리적으로 달라 병렬 구현 불가피 — 단 **정책 상수(위험 패턴)는 공유 데이터로 추출해야 재드리프트 차단**

---

## 3. 딥리서치 종합 (근거)

### 공식 문서 (code.claude.com/docs 검증)
- **훅 파이썬 구조는 공식 권장 패턴** — 전면 교체 불필요. 신기능: prompt-based hooks, `if` 필드 필터, PostToolBatch 등 활용 여지
- **플러그인 패키징은 "선택적 권장"** — 팀 공유·버전 관리 필요 시만. 현 단계 defer 타당 (기존 P5 defer 결정과 일치)
- **커맨드 vs 스킬**: 스킬(SKILL.md)이 lazy 로드 + 지원파일 + progressive disclosure로 우위. 신규는 스킬로
- **CLAUDE.md 권장 ≤200줄** (현재 160줄 — 통과) + `.claude/rules/` path-scoped 모듈화 + `@import` 지원

### 업계 정론 (Anthropic engineering · Addy Osmani · Cognition · LF/AAIF)
- **래칫 원칙**: 모든 규칙·훅·번들은 "막는 과거 실패 1건"을 명명 못 하면 삭제
- **AGENTS.md 오픈 표준** (6만+ 저장소, LF 재단): 멀티툴 규칙 단일화는 표준이 해결 — 도구별 파일은 얇은 포인터로
- **컨텍스트 엔지니어링**: 정적 번들 → progressive disclosure (요약 인덱스 상시 + 본문 on-demand)
- **멀티에이전트 합의**: 병렬 분해 가능한 조사엔 orchestrator-worker 유효, 상호의존 코드 편집 분할은 위험 — Advisor/Worker 프로토콜에 "병렬 분해 가능성" 게이트 명시 권장
- **생성·평가 분리**: 자가 채점 편향 차단 위해 생성 세션과 분리된 리뷰 게이트(Agent-as-judge)
- **3-도구 병행 판정**: "하나의 주력 하네스(Claude Code) + AGENTS.md 이식성 + Cursor/Codex는 on-demand 세컨드 오피니언"이 2026 정론. 상시 3벌 유지 반대

---

## 4. 목표 아키텍처

```
[규칙]   AGENTS.md (SSOT, 핵심 체크리스트로 압축)
          ├─ CLAUDE.md (Claude 세션 보강, ≤200줄 유지)
          │   └─ .claude/rules/*.md (함정·도메인 지식 path-scoped 모듈화)
          └─ .cursor/rules/*.mdc (얇은 포인터화)

[안전]   guard policy 상수 = 공유 데이터 1벌 (tools/harness/guard_policy.py or JSON)
          ├─ .claude/hooks/guard_shell.py (소비자)
          └─ .cursor/hooks/guard_shell.py (소비자)
         → production push·force push 전 변형 차단, WARN은 "ask"로

[분류]   task_classifier v2 — 명시 태그만 오버라이드 신뢰 + 고강도 어휘 보강 + 오탐 강등 억제

[로그]   공통 로그 유틸 (로테이션·포맷 단일화) + 런타임 로그 전부 gitignore
         SESSION/EDIT/SHELL_GUARD 각 1벌·1포맷·상한 有

[컨텍스트] 번들 6종 → Codex용 1~2종만 유지 (Claude/Cursor는 네이티브 로딩)
           HARNESS 컨텍스트는 스킬(SKILL.md) progressive disclosure로 전환

[검증]   Stop 게이트(유지) + pre-push 스모크(유지) + Claude 훅 스모크 테스트 신설
         + 분리-리뷰 게이트: 머지 전 /code-review 또는 gstack-codex 세컨드 오피니언 (on-demand)

[도구]   MCP 2종 유지 · gstack 문서 카탈로그를 실사용 세트(browse·qa·review·investigate)로 축소
         Codex/Cursor = 상시 병행 아닌 검증자 역할
```

---

## 5. 실행 계획 (승인 후 Worker 위임)

### Phase 0 — 안전 수술 (P0/P1, 즉시)
| 작업 | 파일 | 완료 기준 |
|---|---|---|
| 0-1 분류기 오버라이드 재작성: bare substring 폐기, 명시 태그(`[레벨:상]` 등)만 신뢰. TOP/WIDE 어휘 보강. 자연어發 강등 억제 | `task_classifier.py` | 오분류 3사례 재현 테스트 + 기존 `pytest tests/harness/test_task_classifier.py` green |
| 0-2 guard 정책 상수 공유화 + 구멍 봉합: `-f`/`--force-with-lease`/순서무관/plain production push 차단, WARN→ask 스키마 | `.claude/hooks/guard_shell.py`, `.cursor/hooks/guard_shell.py`, 신규 공유 상수 | 우회 변형 전 케이스 차단 테스트 |
| 0-3 SESSION_LOG 포맷 통일 + 공통 로테이션, 손상 파일 재생성 | `session_start.py`, `session_stop.py` (양 하네스) | 로테이션 회귀 테스트 |
| 0-4 track_edits 트리밖 누수 수정 (commonpath 판정) + fail-open hook_log 전 훅 적용 | `track_edits.py`, `guard_shell.py`, `session_stop.py` | 트리밖 편집 제외 테스트 |

### Phase 1 — 다이어트 (구조 부채)
- 런타임 로그 전부 gitignore + git 추적 해제, SHELL_GUARD_LOG 경로 1벌 통일, EDIT_LOG 포맷 통일
- 원샷 스크립트 ~17개 → `docs/archive/` 이관 또는 삭제 (래칫 감사표 첨부)
- 번들 6→2 감축 (CI drift 게이트·pre_push_smoke 갱신 동반)
- `run_codex.ps1` 경로판정 중복 제거 (분류기 반환값 재사용)
- 위생: 빈 폴더·디버그 로그·stale artifacts 삭제, `.codex/` gitignore
- Claude 훅 스모크 테스트 신설 (8개 전부 최소 payload exit 0 + 회귀 3건)

### Phase 2 — 현대화 (선택, Phase 1 안정 후)
- CLAUDE.md 함정 절 → `.claude/rules/` path-scoped 모듈 분리
- HARNESS 번들 → 스킬 progressive disclosure 전환
- gstack 문서 카탈로그 실사용 세트로 축소
- 분리-리뷰 게이트 운영 규칙화 (머지 전 세컨드 오피니언)
- Advisor/Worker 프로토콜에 "병렬 분해 가능성" 게이트 문구 추가 (전역 CLAUDE.md)

### 제외 (명시적 비-작업)
- 플러그인 패키징: defer 유지 (공식 판정 "선택적", 팀 공유 수요 없음)
- Cursor 훅 폐지: 안 함 (Cursor 병행 사용 중 — 정책 상수만 공유화)
- 훅 아키텍처 전면 교체: 안 함 (공식 권장 패턴 확인됨)

---

## 6. 리스크·롤백

| 리스크 | 완화 |
|---|---|
| guard 강화로 정상 명령 오차단 | WARN=ask(차단 아님) + 차단 케이스 테스트 우선 작성 |
| 분류기 재작성으로 기존 태그 오버라이드 회귀 | 기존 fixed-tag 테스트 유지 + 신규 케이스 추가만 |
| 번들 감축 시 CI drift 게이트 파손 | harness-ci.yml·pre_push_smoke 동일 커밋 내 동반 수정 |
| 로그 gitignore 전환 시 이력 유실 우려 | 전환 시점 스냅샷 1회 archive 커밋 |
| 각 Phase 종료 | `pytest tests/harness` + `APP_OK` + pre_push_smoke exit 0 |

---

## 7. 승인 요청 (v1 — §8로 대체됨)

~~1. Phase 0 즉시 착수 2. Phase 1 범위 3. Phase 2 포함 여부~~ → §8.5 참조

---

# §8. 독립 검증 결과와 최종 계획 (v2 — §5·§7 대체)

사용자 지시로 1차 감사를 신뢰하지 않는 독립 검증 2회 수행:
- **Advisor 2 (red team)**: 1차 보고서 주장 전건을 실행 재현으로 공격. 평결 **신뢰도 7/10** — "핵심 결함 전부 실측으로 버팀, 단 심각도 캘리브레이션 오류 + 누락 5건 + 재현 명령 오류"
- **Advisor 3 (백지, 1차 보고서 비공개)**: 원점 재평가. 평결 **전체 학점 C** — "A급 뼈대(정책 문서 B+·Stop 게이트 B+·perf/RUM CI A-) 위에 강제력 0의 투기적 메타-레이어(분류기 D+·번들 D·guard D)"
- 3자 불일치 항목은 Advisor(본 세션)가 코드 직독으로 최종 판정 (판정 근거 각 항목에 명시)

## 8.1 3자 일치 (확정 사실)

- 결함 실재: 분류기 substring 버그·guard 우회 구멍·SESSION_LOG 손상(END행 776)·런타임 로그 git 추적·track_edits 누수·번들 3,532줄(수치 정확)·원샷 잔재
- 유지 자산 (3자 모두 동일 4종): **정책 문서(CLAUDE.md/AGENTS.md) · Stop APP_OK 게이트 · pre_push_smoke · perf-gate/rum-daily CI**
- 문제의 본질: 골격이 아니라 **강제력 없는 메타-레이어의 유지세** (90일 실측: 하네스 커밋 101건 중 15건이 순수 잡음, 셸가드 300건 중 유효 차단 1건, APP_OK 게이트 9곳 중복)

## 8.2 1차 보고서 정정 (red team 지적 → Advisor 재검증 확정)

| 항목 | v1 | v2 정정 | 검증 |
|---|---|---|---|
| P1-1 (무음 production push) | P1 | **P0 승격** — plain/순서변경/`-f` 전부 무로그 통과, 양쪽 훅 공통. 진짜 최상위 구멍 | 실행 재현 (2회 독립) |
| P0-3 (Cursor production 누락) | P0 | **P2 강등** — WARN 레이어가 ask로 잡음. 무음 통과 아님 | 실행 재현 |
| P0-1 수사 | "사실상 랜덤" | **"프롬프트의 ~1/3에서 우연 매칭으로 레벨 오염"** (실측 5/15, 무경고 위험 강등 1/15). high→low 강등은 risky_ack가 잡음 | 15프롬프트 실측 |
| P0-1 재현 명령 | `--prompt` | **오류였음** — 오버라이드는 `additional_prompt`만 파싱(:660, 훅 경로는 :742에서 프롬프트를 additional_prompt로 전달). 회귀 테스트는 `classify_payload` 기반으로 작성해야 함 | 코드 직독 확정 |
| ptc_workspace_* | 퇴역 후보 | **활성** (settings.local.json allowlist 등록) — 퇴역 목록에서 제외 | 실측 |
| 번들 감축 | 6→2 | **6→0** — Codex 경로 휴면 + `build_context_bundle.py`로 필요 시 재생성 가능. 사본 상주 불필요 | 3자 중 2자 일치, Advisor 채택 |
| Phase 2 (현대화) | 스케줄 포함 | **삭제** — 보고서 자신의 래칫 원칙(막는 실패 1건 명명) 위반. 필요가 실증되면 그때 별건 | red team 논리 지적 타당 |

## 8.3 신규 확정 결함 (독립 검증이 추가 발견, Advisor 재검증 완료)

| # | 결함 | 근거 |
|---|---|---|
| N1 | **RPI 게이트 우회**: `needs_rpi`가 `route=="implement"` 필수(:678-684) — "리팩토링/정리" 동사면 하네스 코어 변경도 게이트 미발동 | 코드 직독 + 실행 재현 |
| N2 | **guard 레거시 스키마 의존 + deny 백스톱 부재**: top-level `decision`은 구 스키마. Claude Code가 레거시 지원을 끊으면 위험명령 차단 전체가 무음 fail-open. settings.json에 `permissions.deny` 없음 | 공식 문서 대조 |
| N3 | **SESSION_LOG 로테이션 역전**: `chunks[-20:]`(:41-43)가 newest-first 구조에서 **옛 세션 20개를 동결, 새 세션을 폐기** | 코드 직독 + 로그 실측 |
| N4 | **P0-1 무테스트**: 기존 오버라이드 테스트는 명시 태그만 커버 — v1 완료기준("기존 pytest green")은 버그 있어도 통과 | 테스트 직독 |
| N5 | **track_edits 누수가 Stop 게이트 오염**: 트리밖 `.py`가 pending_verify에 등록 → 무관 파일로 게이트 발동 | 코드 직독 |
| N6 | **guard 오탐**: 부분문자열 매칭이 무해한 echo("drop table" 포함 텍스트)를 차단 — 감사 중 라이브 재현 2회 | 실행 재현 |
| N7 | **Cursor `_is_normal_git` 양방향 prefix 매칭** 과대 — 감사 로그 제외 범위 오류 | 코드 직독 |

## 8.4 최종 계획 v2

### Phase 0 — 안전 수술 (승인 즉시)
| 작업 | 내용 | 완료 기준 |
|---|---|---|
| 0-1 | **guard 재작성**: argv 토큰화 기반(부분문자열 폐지 → N6 오탐 해소), production push 전 변형 차단(P0 승격분), `hookSpecificOutput.permissionDecision` 신스키마 이관 + WARN=ask, `settings.json`에 `permissions.deny` 백스톱(N2), 위험 패턴 상수 공유 1벌(.claude/.cursor 공용) | 우회 변형·오탐 케이스 테이블 전건 테스트 |
| 0-2 | **원격 백스톱**: GitHub `production` 브랜치 보호 설정(로컬 훅보다 강함 — Advisor 3 제안 채택, 사용자 GitHub 설정 필요) | push 거부 실확인 |
| 0-3 | **분류기 결정**: §8.5 결정 A에 따름. 최소안=오버라이드 폴백 삭제+어휘 보강+`classify_payload` 회귀 테스트(N4), 폐기안=분류기·preflight 제거 | 15프롬프트 실측표 재실행 오염 0 |
| 0-4 | **로그 계층 수술**: SESSION_LOG 로테이션 역전 수정(N3)+포맷 통일, track_edits commonpath 판정(N5 게이트 오염 동시 해소), fail-open hook_log 전 훅 적용, 런타임 로그 전부 gitignore | 로테이션·누수 회귀 테스트 |

### Phase 1 — 다이어트
- 번들 6종 전량 폐기 + harness-ci drift 게이트 제거 (`build_context_bundle.py`는 on-demand 도구로 보존)
- 원샷 스크립트 이관/삭제 (ptc 제외 ~15개, 래칫 감사표 첨부)
- `run_codex.ps1` 경로판정 중복 제거 또는 Codex 휴면 확정 시 래퍼 퇴역 (사용자 결정)
- Cursor `_is_normal_git` 수정(N7), APP_OK 9곳 중복 정리(정본 1+소비 참조)
- Claude 훅 스모크 테스트 신설, 위생(빈 폴더·debug 로그·`.codex` gitignore·settings.local 크루프트)
- **주입 콘텐츠 실효성 실측**: 상시 주입물(세션 안내·preflight·rules) 토큰 비용 측정 + 프롬프트 래칫 판정 → 유지/압축/삭제

### 삭제된 Phase 2
래칫 위반으로 계획에서 제외. `.claude/rules` 모듈화·스킬 전환·gstack 축소는 **실패 사례가 실증될 때** 별건 제안.

## 8.5 사용자 결정 필요 (2건)

- **결정 A — 분류기 운명**: ① 수리(오버라이드 폴백 삭제+어휘 보강+테스트, 790줄 유지) ② **폐기(Advisor 3안, Advisor 최종 권고)** — preflight 강제력 0(실측), CLAUDE.md 규칙 문단으로 대체, RPI 게이트는 N1상 이미 우회 가능해 문서 규칙과 차이 없음 ③ 축소(RPI 경로 감지만 남기고 레벨 기계 제거)
- **결정 B — Codex 래퍼**: 유지(중복 제거만) vs 퇴역(7월 활동 0, gstack-codex 스킬로 on-demand 대체)

## 8.6 방법론 교훈 (기록 — §9로 이어짐)

- v1의 "Advisor 직접 재검증" 자가 인증은 과신이었음 — 재현 명령 자체가 틀린 채 확정 보고. **생성·평가 분리(독립 red team)가 이를 잡아냄** = 이번 재설계에 분리-리뷰 게이트를 넣어야 하는 실증 근거가 바로 이 사건
- v1 리서치 인용(업계 정론 프레이밍)은 권위 나열 성격 — 권고는 저장소 실측 근거로만 정당화하도록 v2에서 재구성

---

# §9. 최종 결정 (v3 — 자문 7건 종결, 2026-07-08)

자문 이력: Worker 5(1차 감사·리서치) → Advisor 2(red team, 7/10) → Advisor 3(백지, 학점 C) → Advisor 4(CEO 의사결정) → Advisor 5(딥리서치 실사). 불일치·신규 사실은 Advisor(메인 세션)가 코드 직독/실행으로 전건 재검증.

## 9.1 결정 A — task_classifier(789줄)+preflight: **폐기** ✅ 확정

만장일치 수렴 (Advisor 3=폐기, Advisor 4=폐기 78%, Advisor 5=폐기, 1차 Advisor=폐기 권고). 근거:
- 강제력 0 실측 + 레벨 오염 33% + RPI 게이트 이미 우회 가능(N1)
- 업계 선례 부재 — 매 프롬프트 가이던스 주입은 공식 문서 관점에서도 안티패턴 (Advisor 5)
- RPI 안내는 SessionStart 훅+CLAUDE.md 이중화로 잔존 → 고유 상실 미미 (Advisor 4)
- 완전 가역 (git 복원 수분)
- "축소(③)"는 폐기 비용 전액+유지 부담 존속의 최악 조합이라 선택지에서 제거 (Advisor 4)

**삭제 표면 (≈1,032줄+)**: task_classifier.py(789) + prompt_router.py(105) + test_task_classifier.py(138) + user_prompt_submit.py/settings.json UserPromptSubmit 배선 + before_submit_prompt.py/hooks.json beforeSubmitPrompt 배선 + test_run_codex_levels.py 정리(run_gstack_qa 부분은 분리 보존) + test_hooks_smoke.py 라우팅 단언 제거 + 문서 갱신(CLAUDE.md 하네스 자동 배선 절, .cursor/rules/00:37, AGENTS.md, DECISIONS.md 기록).

## 9.2 결정 B — run_codex.ps1(855줄): **퇴역** ✅ 확정

만장일치 (Advisor 4=퇴역 80%, Advisor 5=퇴역). 근거:
- 90일간 막은 실패 0건, 7월 활동 0. PS 레벨 함수 3종(Get-AutoTaskLevel:562·Get-RequestedLevelOverride:379·Get-LevelGuidance:519)은 호출부 0의 **죽은 코드** (Advisor 검증 확정)
- gstack-codex/gstack-claude 스킬 = on-demand 완전 대체재 실재. 상시 래퍼는 업계 역행
- B 퇴역이 분류기의 유일한 구조적 소비자를 제거 → A 폐기와 상호 강화. **A+B는 Phase 1 단일 원자 커밋**으로 실행 (깨진 중간 상태 방지 — Advisor 4)

## 9.3 Phase 0 최종 수정 (Advisor 4·5 실사 반영)

**순서**: 0-1(guard) → 0-4(로그). ~~0-3 분류기~~ → Phase 1로 이동. 0-2는 선택으로 강등(아래).

- **0-1 guard 재작성 확정 설계**:
  - 테스트 케이스 테이블 **선작성(TDD)** — 현재 guard 무테스트가 결함 상주 원인
  - argv 토큰화 = **주 인포서** (glob·정규식은 `HEAD:production`·`-C dir`·플래그 순서 회피 못 막음 — Advisor 5)
  - 신스키마 이관: DANGEROUS=`permissionDecision:"deny"`, WARN=`"ask"` (레거시 `decision:approve` 즉시 제거 — 능동 위험)
  - `permissions.deny` 백스톱 추가하되 **보조**로만 (Bash deny 미강제 버그 리포트 #18846·#18160 존재)
  - 위험 패턴 상수 공유 1벌 (.claude/.cursor 공용)
- **0-4 로그 수술**: 스냅샷 archive 커밋 → `.gitignore`+`git rm --cached` 동일 커밋 → 동시 세션 비활성 시점 실행 (레이스 대비)
- **0-2 원격 백스톱 → "선택" 강등** (Advisor 5 실사): lahomsystem은 **User 계정 — bypass list 불가**. 선택지 (a) admin 미포함 보호=소유자 오조작 못 막음(실효≈0) vs (b) PR 필수=실차단이나 **worktree 직접-push 승격 의례를 PR 머지로 재작성 필요**. Railway auto-deploy는 어느 쪽도 무충돌. 0-1의 훅+deny 2겹이 생기므로 (b) 채택 여부는 사용자 판정 사항.

## 9.4 실행 승인 대기

- Phase 0(0-1 guard, 0-4 로그) + Phase 1(A+B 원자 커밋, 번들 6→0, 원샷 이관, 위생) — **사용자 착수 승인 대기**
- 별건 판정 1건: 0-2 branch protection (b)안 채택 여부 (승격 의례 변경 수반)
