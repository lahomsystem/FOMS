# GDM 훅·로그 점검 보고서

> **지휘**: Grand Develop Master  
> **일자**: 2026-02-19  
> **범위**: Hook 실행 파일 6개 + 로그 파일 5개 (코드·논리·의미 있는 기록 여부)
> **주의**: 1~4장은 조치 전 분석, 5장은 실제 반영 결과입니다.

---

## 1. 훅 코드·동작 논리 적절성

### 1.1 요약

| 훅 | 스크립트 | 논리 적절성 | 비고 |
|----|----------|-------------|------|
| sessionStart | session_start.py | ✅ 적절 | project_root fallback, conv_id fallback, 20개 세션 유지, stdout JSON |
| stop | session_stop.py | ⚠️ 주의 | conv_id가 "unknown"이면 **여러 세션 블록이 동일**해 첫 번째만 갱신됨. fallback 키 없음 |
| afterFileEdit | track_edits.py | ✅ 적절 | file_path/path/filePath, edits/changes fallback, 50개 유지, 상대경로·UTF-8 |
| preCompact | pre_compact.py | ✅ 적절 | EDIT_LOG·TASK_REGISTRY 기반 체크포인트, 복원 지침 명시. conv_id fallback 없음 |
| beforeShellExecution | guard_shell.py | ✅ 적절 | deny/ask/allow 분류, command 다중 키, 로그에 "(payload에 command 없음)" 표기 |
| afterAgentResponse | incident_rca_guard.py | ✅ 적절 | RCA 키워드·필수 섹션·카테고리 추론·반복 추적·자동 승격 힌트, payload에서 텍스트 추출 |

### 1.2 상세

- **session_stop.py**
  - `conversation_id`만 사용. Cursor가 `conversationId`/`session_id`로 넘기면 "unknown"이 됨.
  - 세션 블록 매칭이 `### Session: {conv_id[:8]}` 기준이라, conv_id가 모두 "unknown"이면 **동일한 "unknown" 블록이 여러 개** 있고, `_update_session_block`의 정규식이 **첫 번째 "### Session: unknown"만** 갱신함. → 세션별 종료 시각·편집 파일이 잘못된 블록에 붙을 수 있음.
  - **권장**: session_start와 동일하게 `conversationId`, `session_id` fallback 추가. conv_id가 "unknown"일 때는 "가장 최근 세션 블록"을 갱신하는 규칙을 두거나, 블록에 일시를 넣어 구분하는 방안 검토.

- **pre_compact.py**
  - `conversation_id`만 사용. fallback 없음 (세션 표시만이라 치명적이진 않음).
  - EDIT_LOG에서 최근 10줄, TASK_REGISTRY에서 "진행중" 행만 추출하는 로직은 적절함.

- **guard_shell.py**
  - DANGEROUS_PATTERNS / WARN_PATTERNS 순서대로 deny → ask → allow 판단. 로그는 항상 append. 논리 일관적.

- **incident_rca_guard.py**
  - payload 전체를 문자열로 walk해 텍스트 추출 → incident 키워드 2개 이상 또는 "incident rca"/"장애" → 필수 섹션 누락 검사, 카테고리 추론, 30일 반복 추적, 2회 이상 시 AUTOPROMOTE 힌트. RCA 워크플로와 잘 맞음.

---

## 2. 의미 있는 로그 기록 여부

### 2.1 현황

| 로그 파일 | 훅 | 실행 | 의미 있는 기록 |
|-----------|-----|------|----------------|
| EDIT_LOG.md | afterFileEdit | ✅ | ❌ 파일 경로·편집량이 `unknown`, 0으로만 기록 |
| SESSION_LOG.md | sessionStart / stop | ✅ | ❌ 세션 ID·상태·편집 파일이 `unknown` 또는 빈 값 |
| SHELL_GUARD_LOG.md | beforeShellExecution | ✅ | ❌ Command 컬럼이 비어 있거나 "(payload에 command 없음)" |
| COMPACT_CHECKPOINT.md | preCompact | ✅ | ⚠️ 시각·세션은 기록되나 "최근 편집"이 EDIT_LOG 의존이라 unknown·0 반복 |
| INCIDENT_HOOK_LOG.md | afterAgentResponse | ✅ | ✅ 장애 맥락일 때만 기록. 현재는 행 없음(정상) |

### 2.2 원인 정리

- **Cursor 쪽**: 훅 호출 시 **stdin으로 넘기는 JSON**에 `file_path`, `command`, `conversation_id` 등이 **비어 있거나**, 스키마가 **다른 키 이름**(예: `path`, `commandText`)일 가능성.
- **스크립트 쪽**: 이미 `file_path`/`path`/`filePath`, `command`/`commandText`/`cmd` 등 fallback을 넣었으나, **실제 전달 키**를 모르면 더 넣기 어렵다.

### 2.3 결론

- 훅 **실행** 자체는 되고, **시각·Decision(allow/deny)·파일 개수 제한·덮어쓰기** 등 **논리는 적절**함.
- **의미 있는 로그**는 **Cursor가 페이로드를 채워줄 때만** 가능. 현재는 대부분 unknown/빈 값이라 **의미 있는 기록은 거의 없음**.

---

## 3. 권장 조치

| 우선순위 | 조치 | 목적 |
|----------|------|------|
| 1 | **session_stop.py**에 `conversationId`, `session_id` fallback 추가 | stop 시 conv_id 수신 가능 시 정확한 세션 블록 갱신 |
| 2 | **페이로드 디버그 옵션** 도입 (예: `CURSOR_HOOK_DEBUG=1`일 때 stdin raw를 `HOOK_PAYLOAD_DEBUG.json`에 1회 기록) | Cursor 실제 키 확인 후 스크립트 수정 |
| 3 | pre_compact.py에 conv_id fallback 추가 (선택) | 체크포인트 세션 표기 일관성 |
| 4 | HOOKS_STATUS.md에 "의미 있는 기록은 Cursor 페이로드 전달에 의존" 명시 유지 | 재점검 시 참고 |

---

## 4. 검증 체크리스트 (조치 후)

- [ ] session_stop fallback 추가 후, 세션 로그에서 conv_id가 채워지는 환경에서 "편집 파일"/"종료"가 해당 세션에만 갱신되는지 확인
- [ ] 디버그 옵션으로 실제 페이로드 캡처 후, track_edits / guard_shell에서 사용할 키 이름 반영
- [ ] `python .cursor/hooks/<각 스크립트>.py` 로 stdin `{}` / 샘플 JSON 넣어서 로그·stdout 동작만 로컬 검증 가능

---

## 5. 반영 결과 (2026-02-19)

- `session_stop.py`
  - `conversation_id`/`conversationId`/`session_id` fallback 유지
  - conv_id가 `unknown`일 때 **진행중/미종료 세션 블록** 우선 갱신하도록 보강
- `pre_compact.py`
  - conv_id fallback(`conversationId`, `session_id`) 추가
- `session_start.py`, `session_stop.py`, `track_edits.py`, `pre_compact.py`, `guard_shell.py`
  - 공통 payload debug 유틸(`.cursor/hooks/hook_payload_debug.py`) 연동
  - `CURSOR_HOOK_DEBUG=1` 시 `docs/context/HOOK_PAYLOAD_DEBUG.jsonl` 기록
  - 기본은 훅별 1회 캡처(`CURSOR_HOOK_DEBUG_ONCE=1`)
- `docs/context/HOOKS_STATUS.md`
  - 현재 적용 상태/디버그 사용법/보강 조치 반영
