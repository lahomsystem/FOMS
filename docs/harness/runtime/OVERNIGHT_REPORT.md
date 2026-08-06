# OVERNIGHT_REPORT — 감사 로깅 T4~T-CP2 (2026-08-06 야간, 2차 런)

플랜: `docs/plans/2026-08-05-system-audit-logging-plan.md` / 원장: `OVERNIGHT_LEDGER.md`
승인: **커밋까지** (push 제외). 시작 HEAD `db1bfa24`.
1차 런(T2·T3·T-CP1): push `d7f0d9ea` CI 4/4 green 종결.

## 완료 task (BLOCKED 0)

| task | SHA | 검증 원문 |
|---|---|---|
| T4 첨부 soft delete·이벤트·outbox·전역 필터 | `3ec9bfd2` | 메인 직접 110 passed(신규 35·권한·게이트 4종)+APP_OK. 위임분 PG 6(마이그레이션 왕복·EXPLAIN BitmapOr)·첨부 관련 856·PG 전수 652·전체 4473 passed(6 fail은 무관 기존 환경 문제, clean HEAD 재현 확인) |
| T5 관리자 from→to·403/CSRF DB 기록·독립 writer | `9d02f0f5` | 메인 직접 76 passed+APP_OK. 위임분 PG 7(rollback 후 감사 행 잔존 인과 증명)·연관 599·smoke 게이트 253 |
| T6 access_logs 부활(파일 접근 3곳) | `ea8a1abc` | 메인 직접 103 passed+APP_OK. 위임분 PG 8(FK 실증·Index Scan)·PG 전수 667·뮤테이션 검증(계측 제거 시 11 red) |
| T-CP2 검증 | — | `pre_push_smoke.ps1` **exit 0** + hygiene 15 passed. push는 승인 범위 밖 |

## 가정하고 진행한 결정 (주요)

1. T4 tombstone 차단 응답 = **404**(권한 판정 후 — 존재 비노출), outbox는 본체·썸네일
   **2행**(handler 무수정 제약), blob 유예 7일, 복구는 outbox PENDING 한정(409 가드).
2. T5 독립성 증명은 **PG 레인**(SQLite는 커넥션 공유로 인과 증명 불가 — 문서화).
   dedupe는 프로세스당 캐시(감쇠 1/4 v1 한계).
3. T6 403/404/tombstone 접근은 **미기록**, 로컬 send_file 분기 미계측(운영 R2 한계 명시),
   additional_data 절단 시 유효 JSON 유지(truncated 플래그).
4. 신규 restore 라우트는 write_guard·mutation_policy manifest 2종 등재(static gate 강제).
5. failopen 인벤토리·regional 2파일·AI_STATUS의 타 세션 잔여 M은 미스테이징 유지.

## push·CI 상태 + ⚠ 의존성

- **push 안 함**(승인 범위). 이번 런 커밋 4개: `3ec9bfd2`·`9d02f0f5`·`ea8a1abc` + 문서
  (직전 잔여 문서 3개 포함 시 push 대상 총 7~8개).
- **⚠ 마이그레이션 체인 의존**: `attach_life_00` → down_revision=`account_self_00`
  (타 세션 계정 셀프서비스 v1, 748eb337) → `access_log_00`이 그 뒤.
  **cherry-pick push 전에 origin에 `account_self_00` 마이그레이션 존재 확인 필수** —
  없으면 해당 세션 push 선행 또는 함께 승인 필요(임의 동반 push 금지).
- push 후: `gh run list`로 전 워크플로 green 확인(perf-gate 포함).

## 아침 체크리스트

1. push 결정 — 먼저 `git ls-remote`+origin 로그에서 `account_self_00` 반영 여부 확인,
   반영돼 있으면 자기 몫 cherry-pick push, 아니면 사용자 판단.
2. push 후 CI 전 워크플로 green + 스테이징에서 첨부 삭제→복구 1회 실동작 확인
   (마이그레이션 2개 자동 적용 확인 포함).
3. Phase 3(T8 security_logs 구조화~T11)은 `/overnight ... T8~T-CP3 실행`으로 재개.
