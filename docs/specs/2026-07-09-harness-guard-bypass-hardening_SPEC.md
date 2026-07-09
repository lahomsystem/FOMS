# 하네스 가드 우회 봉합 + ci_watch false-green 수정 Spec (2026-07-09)

## 1. 배경
2026-07-09 전체 시스템 점검(적대 리뷰 + Advisor 재검증)에서 07-08 재설계 신규 코드의 결함 확정:
- **G-1 (P1)**: `guard_policy.normalize()`가 `\n`→공백 치환, `_split_segments()`는 `;`/`&&`/`||`만 인식 → 다줄 명령의 2번째 줄부터 위험 명령 무력화. 재현: `git status\ngit push --force origin production` → allow.
- **G-2 (P2)**: `KEY=VAL` prefix, `env/nohup/timeout/xargs` 래퍼, `bash -c '...'`/`sh -c "..."`, 서브셸 `(...)`, 명령치환 `$(...)` 내부의 git push가 첫 토큰 디스패치를 우회 → 전부 allow.
- **C-1 (P2)**: `ci_watch.poll_completion()`이 폴링 상한 도달 시 미완 run 반환, `watch_once()`는 failure만 집계 → in_progress를 ALL GREEN exit 0 오판. `--quick`은 정상(4).
- **C-2/C-3 (P3)**: `list_runs --limit 8` 밀림 가능성, `until_final` 소진 시 exit 2로 문서 계약(0/1 수렴) 불일치.
- **P-1 (P3, 실발생 3회)**: `post_push_watch._is_push_command()` 부분문자열 매칭 → echo/python 인용 페이로드를 push로 오탐, "production" 단어만으로 오라우팅.

## 2. 수정 범위
1. **guard_policy**: 개행을 세그먼트 경계로 보존(`;`와 동급). `KEY=VAL` prefix 스킵, 래퍼(`env`,`nohup`,`timeout <n>`,`xargs`) 실명령 재귀 판정, `bash|sh|pwsh -c/-lc "<str>"` 내부 문자열 재귀 분류, 서브셸/명령치환 괄호 스트립 후 재분류. 기존 allow(false positive 0) 회귀 금지 — CONTENT_SAFE/DB 컨텍스트 로직 유지.
2. **ci_watch**: 폴링 상한 도달 후 `all_completed()` 재확인 — 미완이면 exit 4(진행 중) 반환(블로킹·quick 계약 일치화). `--limit` 8→20. `until_final` 라운드 소진 시 exit 1(실패 취급) + docstring 계약 갱신.
3. **post_push_watch**: push 감지를 guard_policy 토크나이저 재사용으로 교체 — 실제 실행 명령 세그먼트에서 `git push`/`gh pr merge`가 명령 위치일 때만 매치. 브랜치 판정도 토큰(“push 인자”) 기반, 문자열 "production" 오라우팅 제거.
4. **테스트**: 실증 우회 전 케이스(개행/env/nohup/timeout/xargs/bash -c/서브셸/치환) deny·ask 고정, ci_watch 블로킹 in_progress→4, post_push 오탐 3종(echo 페이로드/python -c 인용/dry-run) 미주입 고정.

## 3. 비범위
settings.json deny 글롭 확장(가드가 1차, branch protection이 최종 벽 — 글롭은 보조라 유지), Cursor hooks.json 구조 변경.

## 4. 검증 기준 (2026-07-09 전 항목 통과)
- [x] 재현됐던 우회 12종 전부 deny/ask — Advisor 직접 재주입 ALL PASS, 개행 우회는 Claude·Cursor 훅 stdin 주입으로 양 경로 deny 확인 (Cursor는 `_sanitize_command` 개행 보존 수정 포함)
- [x] false positive 대조군 5종 여전히 allow
- [x] ci_watch: 영구 in_progress 모킹 시 블로킹 exit 4 (`test_watch_once_in_progress_over_poll_ceiling_exits_4`), quick exit 4 유지, until_final 소진 exit 1, cp949 콘솔 계약 테스트 2건 추가(`_force_utf8_streams`는 기존 존재 확인)
- [x] post_push_watch: 오탐 3종(echo 페이로드/python -c/dry-run) 무주입, push 성공 페이로드는 브랜치 정라우팅 주입 — guard_policy `find_push_segments` 재사용으로 교체
- [x] `pytest tests/harness -q` **238 passed**, `APP_OK`
