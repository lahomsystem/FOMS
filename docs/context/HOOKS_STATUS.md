# Hooks 동작 상태

> 훅이 **실행되는지** vs **의미 있는 데이터가 기록되는지**를 구분합니다.

## 현재 상황 요약

| 로그 파일 | 훅 | 실행 여부 | 기록 내용 |
|-----------|-----|-----------|-----------|
| EDIT_LOG.md | afterFileEdit | ✅ 실행됨 (시각 기록) | ❌ 파일 경로/편집량이 `unknown`, 0으로만 찍힘 |
| SESSION_LOG.md | sessionStart / stop | ✅ 실행됨 | ❌ 세션 ID·편집 파일이 `unknown` |
| SHELL_GUARD_LOG.md | beforeShellExecution | ✅ 실행됨 | ❌ Command·Pattern이 비어 있음 |

**결론:** 훅 스크립트는 **호출되고 실행**됩니다. 다만 **Cursor가 stdin으로 넘기는 JSON 페이로드**가 비어 있거나, 스크립트가 기대하는 키(`file_path`, `command`, `conversation_id` 등)와 Cursor 실제 전달 키가 다를 가능성이 있습니다.

## 원인 가능성

1. **Cursor 버전/환경**: 훅 호출 시 stdin에 페이로드를 넣지 않거나, 다른 키 이름을 사용
2. **Windows 환경**: 경로·인코딩 등으로 페이로드가 스크립트에 제대로 전달되지 않음
3. **훅 스키마 변경**: Cursor 문서의 `file_path`, `command` 등과 실제 배포된 스키마 불일치

## 확인 방법

- **실제 페이로드 확인**: 환경변수 `CURSOR_HOOK_DEBUG=1` 이 있으면 훅이 받은 raw JSON을 `docs/context/HOOK_PAYLOAD_DEBUG.json`에 한 번 씁니다. (스크립트에 해당 옵션 추가 시)
- **Cursor 문서**: [Cursor Agent Hooks](https://cursor.com/docs/agent/hooks) 에서 각 훅의 Payload 스키마 확인

## 조치

- 훅 스크립트에 **다양한 키 이름 fallback** 적용 (예: `path`, `filePath`, `commandText` 등).
- 위 디버그로 실제 전달 키를 확인한 뒤, 그에 맞게 스크립트 수정.
