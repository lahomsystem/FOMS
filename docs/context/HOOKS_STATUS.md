# Hooks 동작 상태

> 훅이 **실행되는지** vs **의미 있는 데이터가 기록되는지**를 구분합니다.  
> **상세 점검**: `docs/context/GDM_HOOKS_ANALYSIS_2026-02-19.md`

## 현재 상황 요약

| 로그 파일 | 훅 | 실행 여부 | 의미 있는 기록 |
|-----------|-----|-----------|----------------|
| `EDIT_LOG.md` | `afterFileEdit` | ✅ 실행됨 | ⚠️ Cursor payload에 파일/변경 정보가 없으면 `unknown`, 0으로 기록 |
| `SESSION_LOG.md` | `sessionStart`, `stop` | ✅ 실행됨 | ⚠️ Cursor payload에 세션 ID가 없으면 `unknown`으로 기록 |
| `SHELL_GUARD_LOG.md` | `beforeShellExecution` | ✅ 실행됨 | ⚠️ Cursor payload에 command가 없으면 빈 값 또는 `(payload에 command 없음)` |
| `COMPACT_CHECKPOINT.md` | `preCompact` | ✅ 실행됨 | ⚠️ 최근 편집 목록은 `EDIT_LOG.md` 품질에 의존 |
| `INCIDENT_HOOK_LOG.md` | `afterAgentResponse` | ✅ 실행됨 | ✅ 장애 맥락에서만 기록 (정상) |

## 확인 방법

- 실제 payload 확인(적용 완료):
- `CURSOR_HOOK_DEBUG=1` 설정 시 `docs/context/HOOK_PAYLOAD_DEBUG.jsonl`에 훅별 payload 기록
- 기본은 훅별 1회 캡처 (`CURSOR_HOOK_DEBUG_ONCE=1`)
- 반복 캡처가 필요하면 `CURSOR_HOOK_DEBUG_ONCE=0`
- Cursor 문서: <https://cursor.com/docs/agent/hooks>

## 적용된 조치 (2026-02-19)

- 공통 디버그 유틸 추가: `.cursor/hooks/hook_payload_debug.py`
- debug 적용 훅:
- `.cursor/hooks/session_start.py`
- `.cursor/hooks/session_stop.py`
- `.cursor/hooks/track_edits.py`
- `.cursor/hooks/pre_compact.py`
- `.cursor/hooks/guard_shell.py`
- fallback 강화:
- `conversation_id` / `conversationId` / `session_id`
- `file_path` / `path` / `filePath` / `file` / `target_file` / `uri`
- `command` / `commandText` / `cmd` / `shell_command` / `input` / `text`
- `session_stop` 보강:
- conv_id가 `unknown`일 때 "진행중/미종료 세션 블록"을 우선 갱신
- `pre_compact` 보강:
- conv_id fallback (`conversationId`, `session_id`) 반영

## 결론

- 훅 실행·논리는 정상입니다.
- 로그 품질은 최종적으로 Cursor가 전달하는 payload 품질에 좌우됩니다.
- 다음 점검은 `HOOK_PAYLOAD_DEBUG.jsonl` 기반으로 키 매핑을 고정하면 됩니다.
