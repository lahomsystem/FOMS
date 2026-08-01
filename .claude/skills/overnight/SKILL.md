---
name: overnight
description: 밤샘 무인 작업 오케스트레이션 — 짧은 작업 지시 하나로 플랜+progress ledger 생성, 퇴근 전 승인 1회, 이후 SDD 위임 루프로 자율 실행·검증·커밋, 아침 보고서까지. /overnight <작업 설명>으로 발동.
disable-model-invocation: true
---

# /overnight — 밤샘 무인 작업 오케스트레이션

사용자가 `/overnight <작업 설명>` 한 줄로 발동한다. 이 스킬이 로드되면 아래 4단계를 순서대로 수행한다. 목표: **사용자 개입은 퇴근 전 승인 1회가 전부**, 이후 아침 보고서까지 자율 완주.

## 원칙 (전 단계 공통)

- **메인 세션 = 오케스트레이터.** 구현 노동은 전부 서브에이전트 위임(SDD). 메인 컨텍스트는 판단·검증·ledger 갱신에만 쓴다 — 이게 최대 토큰 절약이자 컨텍스트 생존책이다.
- **모델 티어링 명시**: 탐색/기계적 변환=`sonnet`(대량이면 `haiku`), 일반 구현=`opus`, 최종 리뷰=`opus`. Agent 호출 시 model 파라미터 생략 금지.
- **파일 핸드오프**: 서브에이전트 브리프는 파일로 작성해 경로만 전달(`$CLAUDE_JOB_DIR/tmp` 또는 `c:/tmp`). 대화 히스토리 붙여넣기 금지.
- **검증 무신뢰**: 서브에이전트 "완료" 보고는 주장일 뿐 — diff 직접 확인(git diff) + 검증 명령 직접 실행 후에만 ledger에 완료 기록.
- **ledger = SSOT**: 컨텍스트가 압축돼도 ledger 파일이 진실. 모든 상태 변화는 즉시 ledger에 기록(작업 후가 아니라 그 자리에서).
- **CTX-GATE 준수**: [CTX-GATE] 주입이 오면 무인 조항대로 — ledger·AI_STATUS 굳히고 권고 없이 계속.
- **git**: 커밋은 task 단위로 UTF-8 파일 + `git commit -F`. **push는 기본 금지**(아침 검수 후 사용자가) — Phase 1 승인에서 사용자가 "push까지"를 명시 선택한 경우에만 pre_push_smoke exit 0 → deploy push → ci_watch까지 수행. production은 어떤 경우에도 금지.

## Phase 0 — 안전 점검 (2분, 실패 시 여기서 멈추고 보고)

1. `git status --short` + `git log origin/deploy..HEAD --oneline` — 워킹트리에 타 세션 미커밋 변경·미push 커밋이 있으면 **사용자에게 보고하고 처리 방침을 승인 질문에 포함**(무인 중 남의 작업 위에 쌓는 사고 방지).
2. `python -c "import app; print('APP_OK')"` — 시작점이 green인지. red면 밤샘 부적격, 원인부터 보고.
3. 권한: 이 세션의 권한 모드가 무인에 충분한지 판단이 안 되면 승인 질문에 "권한 프롬프트가 뜨면 밤새 멈춘다 — auto 모드/allowlist 확인" 경고 1줄 포함.

## Phase 1 — 플랜 + ledger + 승인 1회

1. 작업 설명(args)을 분해해 플랜 파일 작성: `docs/plans/<오늘날짜>-<slug>-overnight-plan.md`
   - task별로: 목적 / 대상 파일(경로) / **완료 기준(통과해야 할 검증 명령 명시)** / 위임 모델 티어 / 변경 금지 경계
   - 완료 기준 없는 task는 플랜에 넣지 마라 — 검증 불가능한 task는 무인 부적격.
2. progress ledger 생성: `docs/harness/runtime/OVERNIGHT_LEDGER.md`
   - 형식: `| # | task | 상태(PENDING/IN_PROGRESS/DONE/BLOCKED) | 검증 결과 | 커밋 SHA |`
3. **승인 게이트 (유일한 사용자 개입)**: AskUserQuestion 1회 — 플랜 요약(task 수·예상 규모·리스크) 제시, 옵션: (a) 승인—커밋까지 (b) 승인—push까지 포함 (c) 플랜 수정. Phase 0에서 발견한 경고도 여기 포함.
   - 응답이 오면 즉시 Phase 2. 이후 사용자 응답을 기다리는 질문은 금지 — 모든 모호함은 플랜의 명시 가정으로 해소하고 ledger에 가정을 기록하라.

## Phase 2 — 자율 실행 루프 (밤샘 본체)

ledger의 PENDING task를 순서대로, 전부 소진할 때까지:

1. task를 IN_PROGRESS로 마킹 → 브리프 파일 작성(컨텍스트·경로·완료 기준·경계·알려진 함정 — 프로젝트 CLAUDE.md·메모리에서 관련 항목 발췌) → 서브에이전트 위임(모델 명시). 독립 task 2개 이상이면 병렬 디스패치.
2. 결과 검증(무신뢰): git diff 직접 확인 + task의 완료 기준 명령 직접 실행. 통과 원문을 ledger 검증 결과 칸에 기록.
3. 통과 → task 단위 커밋(-F, 한글 메시지) → ledger DONE+SHA 기록.
4. 실패 → 실패 내용 담은 수정 브리프로 **재위임 최대 2회**. 그래도 실패면 ledger에 BLOCKED+실패 원문 기록하고 **다음 task로 진행** — 밤새 한 task에 갇히는 것이 최악이다. BLOCKED가 후속 task의 전제면 그 task들도 BLOCKED(사유: 의존) 처리.
5. 매 task 종료 시 ledger 저장 확인. 3 task마다 `docs/AI_STATUS.md` "진행 중" 섹션을 현재 상태로 1줄 갱신(상단 40줄 예산 준수 — 계약 테스트가 감시한다).

## Phase 3 — 아침 보고서

전 task 소진 후:

1. 최종 검증: 이 밤에 편집된 영역의 테스트 전체 + `import app` + (계약) `pytest tests/harness/test_hook_log_hygiene.py -q`.
2. push 승인이 있었으면: `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` exit 0 → `git push origin deploy` → `python tools/harness/ci_watch.py <HEAD SHA> deploy` (run_in_background) + `gh run list`로 perf-gate까지 확인.
3. 보고서 작성: `docs/harness/runtime/OVERNIGHT_REPORT.md`
   - 완료 task(SHA·검증 원문) / BLOCKED task(실패 원문·시도 이력·권장 다음 수) / 가정하고 진행한 결정 목록 / push·CI 상태 / 사용자가 아침에 확인할 체크리스트 3줄
4. 마지막 사용자-대면 메시지로 보고서 요약(한글) 출력. AI_STATUS "진행 중"에서 이 작업 항목을 결과 반영해 갱신.

## 발동 예시

```
/overnight AS 대시보드 모바일 카드에 유상/무상 배지 추가하고 관련 계약 테스트 작성
/overnight docs/plans/2026-07-22-...report.md의 PACKET-HARNESS-00부터 10개 packet 구현
```

작업 설명이 비어 있으면: "무엇을 밤샘 작업할지 한 줄로 알려달라"고 묻고 대기(이때는 아직 무인 아님).
