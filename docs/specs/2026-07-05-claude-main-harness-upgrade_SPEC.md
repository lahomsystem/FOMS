# Claude-main 하네스 업그레이드 Spec (2026-07-05)

## 1. 배경/목표
Claude Code를 메인 러너로 전환. 조사 결과(2026-07-05 세션): Cursor 훅 8종 대비 Claude 훅 3종만 배선, MCP 7종이 비정본 위치(`.claude/settings.json` `mcpServers` — Claude Code 정본은 루트 `.mcp.json`), Stop 훅은 조언성 리마인더뿐, CLAUDE.md 과체중, 권한 allowlist에 일회성 잔재. 사용자 승인: "CEO advisor 모드로 완료될 때까지 진행".

## 2. 범위 (P1~P6 중 P5 제외)
- **P1 MCP**: 루트 `.mcp.json` 신설 — `postgres`, `context7`만 유지. `filesystem`(네이티브 도구 중복)·`memory`(네이티브 파일 메모리 대체)·`sequential-thinking`/`mcp-reasoner`(네이티브 extended thinking 대체)·`markitdown`(Read가 문서 처리) 퇴역. `.claude/settings.json`의 `mcpServers` 블록 제거.
- **P2 훅 패리티**: `.claude/hooks/`에 3종 신설 + settings.json 배선
  - `session_start.py` (SessionStart): AI_STATUS 안내 + RPI 리마인더를 additionalContext로 주입 (Cursor `session_start.py` 등가, SESSION_LOG 기록 포함)
  - `user_prompt_submit.py` (UserPromptSubmit): `tools/harness/task_classifier.py` `classify_payload()` 호출 → level/route/RPI/prompt_lines를 additionalContext로 주입 (Cursor `before_submit_prompt.py` 등가)
  - `pre_compact.py` (PreCompact): `docs/harness/runtime/COMPACT_CHECKPOINT.md` 갱신 (Cursor 등가)
- **P4 결정적 Stop 게이트**: `track_edits.py`가 `.py` 편집을 pending 상태 파일에 기록 → `quality_check.py`(Stop)가 pending 있으면 `python -c "import app"` 실행, 실패 시 exit 2로 턴 종료 차단(에러 원문 전달), 성공 시 pending 클리어. 훅 자체 오류는 fail-open + `docs/harness/logs/` 로그 (묵시적 삼킴 금지).
- **P3 CLAUDE.md 다이어트**: Cursor 러너 라우팅 절 제거(Cursor rules/AGENTS.md 소관), 중복 압축. 번들 재생성 필수.
- **P6 위생**: settings.json 권한 allowlist에서 channel-io 일회성 curl 8건 제거.

## 3. 비범위
- P5 플러그인 패키징 (가치 대비 유지비 — defer, DECISIONS 기록)
- Cursor/Codex 훅·번들 구조 변경 (기존 유지)
- AGENTS.md 정책 내용 변경

## 4. 검증 기준 (2026-07-05 전 항목 통과)
- [x] `python -c "import app; print('APP_OK')"` → APP_OK
- [x] 신설 훅 3종: 샘플 stdin JSON 주입 시 exit 0 + 올바른 JSON/컨텍스트 출력, 페이로드 깨져도 fail-open+로그 (garbage 입력 exit 0 확인)
- [x] Stop 게이트: .py pending + import 실패 시 exit 2, import 성공 시 exit 0·pending 클리어 (`test_claude_stop_gate.py` 4건 고정)
- [x] `pytest tests/harness -q` → **81 passed**
- [x] `python tools/harness/build_context_bundle.py --all` 재생성 후 번들·프로파일 계약 17 passed
- [x] `.claude/settings.json` JSON 파싱 정상, hooks 배선 6이벤트 (SessionStart/UserPromptSubmit/PreCompact/PreToolUse/PostToolUse/Stop)

## 5. 실행 중 추가 근본수정 (Worker 발견)
- shared_utils stdin/stdout을 UTF-8 바이너리 버퍼로 정본화 — Win11 cp949 로케일에서 한글 페이로드 깨짐→분류 오작동/mojibake 잠복 버그
- quality_check `_force_utf8_streams()` — cp949 콘솔에서 훅 크래시 방지
- task_classifier 한글 레벨 키워드 보강 + `prompt_text` 레벨 신호 미반영 결함 수정 (CLI `--prompt` 경로에서 영어 키워드조차 레벨 미반영이던 버그, `run_codex.ps1`/`classify_payload` 하위호환 확인) + `HARNESS_TEXT_KEYWORDS`("harness"/"하네스") 텍스트 신호 신설
- preflight 실동작 증명: 본 세션 UserPromptSubmit에서 `[HARNESS PREFLIGHT] level=top ... (auth keywords + harness keyword)` 자동 주입 확인
