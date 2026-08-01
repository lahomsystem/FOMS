# 컨텍스트 원장·훅 위생 재설계 v2 — 3-agent 리뷰 반영 확정판

날짜: 2026-07-28 · 브랜치: deploy · 상태: v1 → 3-agent 교차 리뷰(반증/단순화/플랫폼 팩트체크) → 오케스트레이터 재검증 → **v2 확정**

## 0. v1 대비 변경 요약 (리뷰가 뒤집은 것)

| v1 설계 | 리뷰 판정 | v2 |
|---|---|---|
| SessionEnd 훅 신설 + 48h sweep | 반증: "진행중 누적"의 진짜 원인은 **동일 session_id 중복 블록**(재현 확인). 20블록 캡 때문에 48h sweep은 상시 no-op. SessionEnd는 크래시 미보장·Stop과 중복 발화 | **CUT.** `prepend_session_block` 중복 흡수로 근본 수정 |
| AI_STATUS 수술로 37K→5K | 반증: 최대 덩어리는 핵심 모듈 22.1K자+기록 보관 11.2K자 — v1 수술 범위로는 15~20K 잔존 | **소비 제한으로 전환**: session_start 지시를 "상단 40줄(limit=40)"로. 파일 대수술 불필요 |
| 계약 테스트 3조건(개수·30일 TTL·상한) | 30일 TTL은 날짜 갱신 writer가 없어 구조적 무력화 → 전 항목 `keep:` 연극 + 타 세션 push까지 red | **2 assert로 축소**: ① 상단 40줄 ≤ 4,000자 ② 본문에 `**종료**` 있는 항목이 "진행 중" 섹션 잔존 금지(현행 부패 4건을 오탐 0으로 잡음) |
| pre_compact 소스 1순위 = session_commit_ledger.json | ledger 키=full UUID인데 pre_compact는 8자 절단 → 100% miss. 커밋 전 압축 시 항상 빈 결과 | 소스 = `git log --oneline -5` + branch/HEAD + pending_verify + EDIT_LOG. session_id는 원본 보관 |
| (v1에 없던 발견) | `.cursor/hooks/`에 동일 결함 쌍둥이. pre_compact "복원 지침 6단계"가 압축 직후 4문서 재독 지시(최대 누수). SESSION_LOG 무잠금 RMW 유실 실측(12중 1 유실). `_find_block` matches[0] 폴백이 타 세션 블록 clobber | v2 §2에 전부 편입 |

**전면 리빌드 기각 근거**: 훅 기본 동작은 실측 정상(EDIT_LOG 갱신·stdout JSON 유효·Stop 게이트 pending 기록·훅당 70-81ms). fail-open 골격+가드 테스트 73케이스는 검증된 자산. 결함은 국소 6곳 — 리빌드는 리스크 순증.

## 1. 실측 근거 (오케스트레이터 직접 검증 완료)

- 훅 지연: track_edits 81ms / guard_shell 79ms / 기타 70-73ms (python 기동 55ms 포함). Bash 1회당 PostToolUse 2훅 = ~146ms 부가.
- SESSION_LOG 중복: `e38945c7`·`c3c7bd06`·`93aa1305` 각 2블록 실재. 원인: resume/clear/compact 시 SessionStart 재발화 → 같은 id로 새 블록 prepend, Stop은 최신 블록만 갱신.
- `hook_log_utils._find_block`: id 미매치 시 "열린 블록 아무거나 → matches[0]" 폴백 → 타 세션 live 블록 clobber (재현 확인).
- SESSION_LOG 쓰기 3함수 무잠금 read-modify-write. 동일 저장소 `session_commit_ledger.py`는 tmp+`os.replace` 원자 저장 사용 — SESSION_LOG만 미적용.
- `session_commit_ledger.json` 키 = full UUID(37세션). `pre_compact.py:99` `[:8]` 절단.
- AI_STATUS 59,135자: 핵심 모듈 22,107 / 최근 완료 19,557 / 기록 보관 11,219 / 헤더 3,271(2번째 줄 3,256) / live 3섹션(진행중+검증필요+이슈) 합 2,066.
- pre_compact 복원 지침이 AI_STATUS+CHANGELOG+DECISIONS+ARCHIVE_INDEX 재독 지시 — `.claude`·`.cursor` 양쪽.
- SESSION_LOG 소비자(읽는 코드) 0 — 쓰는 훅 4개뿐.
- CLAUDE_HOOK_LOG.md 부재 = 훅 fail-open 발화 이력 0 (로거는 정상 구현·lazy 생성).
- 플랫폼 사실(리뷰3): SessionStart source에 `fork` 존재(현 훅 docstring 누락). statusline `context_window.remaining_percentage` 실재·초반 null. PostCompact 이벤트 실재(공식 문서 + exe 심볼) — additionalContext 주입 가능성은 실측 미검증.

## 2. v2 작업 목록

### T1. `tools/harness/hook_log_utils.py` 코어 수리 (신규 훅 0개)
1. `prepend_session_block`: 동일 session_id 기존 블록 발견 시 새 블록으로 **흡수(제거 후 삽입)** — 중복 블록 근본 제거
2. SESSION_LOG 쓰기 3함수(`prepend_session_block`/`update_session_block`/`append_with_rotation`): tmp 파일 + `os.replace` 원자 저장 + `msvcrt.locking` 파일락(Windows; 실패 시 기존 경로 fail-open+로그)
3. `_find_block`: `matches[0]` 최종 폴백 제거 — id 미상이면 no-op + `hook_log` 기록. ("열린 블록" 폴백도 제거 — clobber 벡터 동일)
4. 기존 `tests/harness` 해당 테스트 갱신 + 중복 흡수·no-op 케이스 추가

### T2. pre_compact v2 — `.claude`·`.cursor` 쌍둥이 동시
1. 진행중 필터를 `tools/harness/`, 공용 함수로 SSOT화: **"라인에 `**종료**` 포함 시 제외"** 규칙. `.claude/hooks/pre_compact.py`·`.cursor/hooks/pre_compact.py` 양쪽이 import
2. 체크포인트 소스 교체: `git log --oneline -5`(제목 포함) + `git branch --show-current`+HEAD SHA + `.claude_pending_verify.json` + EDIT_LOG(기존). ledger 직접 파싱 안 함
3. "복원 지침 6단계" → **"이 파일이 복원의 전부다. AI_STATUS 등 추가 문서 재독 금지(필요 시 grep)"** 2줄로 교체 — 최대 누수 제거
4. session_id 8자 절단은 표시용으로만, 원본 별도 보관
5. (구현 중 10분 실험) PostCompact 훅이 additionalContext/stdout 주입을 지원하는지 샘플 payload로 실측 → 지원 시 후속 별건으로 PreCompact 파일 우회 폐지 검토(이번 범위 아님, 결과만 스펙에 기록)

> **T2-5 실측 메모 (2026-07-28, claude 2.1.220 / bin/claude.exe 심볼 스캔, 배선 안 함)**
> - 입력 스키마 실재: `{hook_event_name:"PostCompact", trigger:"manual"|"auto", compact_summary:string}` (`executePostCompactHooks` 심볼 확인) — 브리프 샘플 payload 그대로 유효.
> - **출력 주입은 미지원**: `hookSpecificOutput.hookEventName` literal 목록(20종: SessionStart·PostToolUse·UserPromptSubmit·Stop 등)에 **PostCompact 없음** → additionalContext 채널 부재.
> - 결론: PreCompact→파일(COMPACT_CHECKPOINT.md) 경로 유지가 현행 유일 수단. 향후 릴리스에서 위 literal 목록에 PostCompact가 추가되면 그때 재검토.

### T3. AI_STATUS — 소비 제한 + 경량 수술 (오케스트레이터 직접)
1. `session_start.py`(.claude)·`session_start.py`(.cursor) 지시 문구: "docs/AI_STATUS.md **상단 40줄만** 읽어라(Read limit=40)" — 37K → ~1.2K 토큰
2. 파일 재배치(삭제·이관 없음): live 3섹션(진행 중/검증 필요/알려진 이슈)을 헤더 직후로 이동, 헤더 2번째 줄 3,256자 블롭을 3줄 요약으로 압축(원문은 "## 기록 보관"으로 이동), "진행 중" 사망 항목 4건 그 자리 제거
3. source `fork` 값 docstring 반영(.claude session_start)

### T4. 계약 테스트 — 기존 `tests/harness/test_hook_log_hygiene.py`에 추가
1. assert① AI_STATUS 상단 40줄 ≤ 4,000자 (상수 1곳)
2. assert② "## 진행 중" 섹션에 `**종료**` 포함 라인 금지
3. T1 회귀 케이스와 함께 pre_push_smoke 서브셋·Harness CI에서 자동 실행

### T5. 성능 (선택·저위험만)
- PostToolUse:Bash 2훅(record_commit_ledger+post_push_watch)을 단일 디스패처 `post_bash.py`로 병합 — Bash당 python 기동 1회 절약(~70ms). 각 모듈은 함수로 유지(로직 무변경)
- 판정: 훅은 체감 성능 저하의 주범 아님(실측 70-81ms). 세션 체감 지연의 후보는 스킬 프리앰블 bash 체인 등 별도 — 이번 범위 밖, 필요 시 별건 진단

### T6. statusline (별건 분리, 전역 설정)
- 신규 `C:/Users/USER/.claude/statusline.ps1`: stdin JSON 1회 소비 → ctx remaining% 게이지 출력 + caveman 배지 스크립트 호출(**stdin 안 넘김** — caveman은 stdin 미사용 확인). caveman 경로는 해시 하드코딩 금지 — `Get-ChildItem plugins/cache/caveman/caveman/*/src/hooks/caveman-statusline.ps1 | Select -Last 1` 와일드카드 해석
- `statusLine.command` 교체(forward slash)

### T7. CLAUDE.md Compact instructions — 3줄 이내
- "compact 시 보존: 작업 브랜치·HEAD SHA, 검증 명령+마지막 결과, 미해결 실패, 편집 파일 목록. 탐색성 read/grep 결과는 버림." 수준 3줄. 상세는 COMPACT_CHECKPOINT 본문이 담당(상시 비용 0)

### 정리
- 실측이 오염시킨 SESSION_LOG `perftest*`/`jsontest` 블록·pending_verify 테스트 잔재 제거

## 3. 분담·검증

| 작업 | 담당 | 모델 |
|---|---|---|
| T1+T4 (코어+테스트) | 구현 서브에이전트 A | opus |
| T2 (pre_compact 쌍둥이+SSOT 필터) | 구현 서브에이전트 B (A와 병렬) | opus |
| T5 병합 디스패처 | 구현 서브에이전트 B에 포함 | opus |
| T3·T6·T7·정리 | 오케스트레이터 직접(문서·설정) | - |
| 2판정 리뷰(스펙 준수/품질 분리) | 리뷰 서브에이전트 | opus |

완료 기준: `pytest tests/harness -q` green · `APP_OK` · 훅 E2E(실 payload stdin → exit 0 + 산출물 확인) · 중복 prepend→update 시나리오에서 블록 1개·완료 상태 확인 · 동시 12-writer 유실 0 확인 · COMPACT_CHECKPOINT에 종료-잔존 항목 0 · statusline 샘플 JSON → 배지+% 동시 출력.
