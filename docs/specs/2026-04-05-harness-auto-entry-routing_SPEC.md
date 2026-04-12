# Harness Auto Entry Routing Spec
> 작성일: 2026-04-05 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
Cursor 세션에서 사용자가 review / implement / QA / harness-core 성격의 명령을 입력하면, `beforeSubmitPrompt` 단계에서 해당 의도를 자동 분류하고 에이전트에게 올바른 하네스 진입 경로(wrapper/bundle/RPI 요구)를 자동 주입한다. 결과적으로 사용자는 기존처럼 자연어 명령을 쓰더라도, 에이전트는 가능한 한 `tools/harness/run_codex.ps1` 또는 `tools/harness/run_gstack_qa.ps1` 기준으로 움직이게 된다.

### 1.2 기능 요구사항
1. `.cursor/hooks.json`에 `beforeSubmitPrompt` 훅을 등록한다.
2. 새 훅은 사용자 prompt와 첨부/경로 힌트를 읽어 `review`, `implement`, `qa`, `generic` 중 하나의 진입 유형을 분류해야 한다.
3. `review` 또는 `implement`로 분류된 요청이 하네스/코어 범위(`tools/harness/`, `.cursor/hooks/`, `.cursor/rules/`, `.cursor/agents/`, `docs/specs/`, `AGENTS.md`, `CLAUDE.md`, `db.py` 등)를 건드리면, 훅은 하네스 번들/래퍼 경로와 RPI 요구를 포함한 `agentMessage`를 반환해야 한다.
4. `qa`로 분류된 요청은 URL/시나리오 힌트가 있을 때 `tools/harness/run_gstack_qa.ps1` 우선 경로를 제시해야 한다.
5. 분류 근거가 약하거나 일반 대화인 경우에는 조용히 통과시키되, 잘못된 강제 라우팅으로 정상 작업을 방해하면 안 된다.
6. 훅 로직은 테스트 가능하도록 별도 Python 모듈로 분리하고, 훅 엔트리포인트는 그 모듈을 호출하는 얇은 래퍼로 유지한다.

### 1.3 예외/제약 조건
- Cursor 훅은 prompt에 대용량 bundle 본문을 직접 주입하지 않는다. 짧은 시스템 메시지로 wrapper/bundle/RPI 우선 경로만 지시한다.
- Hook는 fail-open을 유지해야 한다. 분류 실패나 payload 이상 시 세션을 막지 않고 `continue: true`로 통과시킨다.
- 기존 `sessionStart`, `afterAgentResponse`, `beforeShellExecution` 계약을 깨면 안 된다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `.cursor/hooks.json` | `beforeSubmitPrompt` 훅 등록 |
| `.cursor/hooks/before_submit_prompt.py` | 새 훅 엔트리포인트 추가 |
| `tools/harness/prompt_router.py` | 사용자 프롬프트 분류 및 agentMessage 생성 로직 분리 |
| `tests/harness/test_hooks_smoke.py` | 새 훅 smoke/메시지 계약 검증 추가 |
| `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` | auto-entry 동작과 한계 문서화 |
| `task_plan.md`, `findings.md`, `progress.md`, `docs/ARCHIVE_INDEX.md`, `docs/harness/policy/DECISIONS.md` | 이번 변경 기록 동기화 |

### 2.2 아키텍처 방향
- 기존 hook 패턴(`session_start.py`, `post_task_quality_check.py`)을 그대로 따라 `continue + agentMessage` 계약을 유지한다.
- 진입 분류는 Python 모듈에서 처리하고, 하네스 코어 경로 판별 규칙은 `run_codex.ps1`의 기존 heuristics와 최대한 동일한 범위를 유지한다.
- 목표는 “완전 자동 실행”이 아니라 “사용자 명령 시 자동 라우팅 안내/강화”이다. Cursor 훅 제약을 넘는 동작은 시도하지 않는다.

### 2.3 의존성 및 영향 범위
- DB 마이그레이션 없음
- 영향 범위: Cursor IDE 훅 동작, harness operator UX, hook smoke test
- 외부 의존성 추가 없음

## 3. Steps — 실행 단계
- [x] Step 1: auto-entry routing Spec과 작업 로그를 갱신해 범위를 고정한다.
- [x] Step 2: `beforeSubmitPrompt`용 failing test를 작성하고 기대 메시지 계약을 고정한다.
- [x] Step 3: `prompt_router.py`와 `before_submit_prompt.py`를 구현하고 `.cursor/hooks.json`에 연결한다.
- [x] Step 4: operator guide 및 관련 계획/결정 로그를 동기화한다.
- [x] Step 5: hook smoke, targeted pytest, lints로 동작을 검증한다.

## 4. 검증 기준
- [x] `python -m compileall -q ".cursor/hooks"` 통과
- [x] `python -m pytest tests/harness/test_hooks_smoke.py -q` 통과
- [x] 새 `beforeSubmitPrompt` 훅 subprocess smoke 통과
- [x] harness/core implement 또는 review prompt에서 wrapper/bundle/RPI 안내가 `agentMessage`로 생성됨
- [x] 일반 대화 prompt는 과도한 auto-entry 메시지 없이 통과함

## 5. 참고 자료
- 관련 결정: `docs/harness/policy/DECISIONS.md`의 Wave 3 / post-audit hardening 항목
- 관련 스펙: `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`
- 관련 가이드: `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
