# 인수인계 — 감사 로깅 (2026-08-08 갱신, 잔여 작업 A·B 완료)

정본 문서: 스펙 `docs/specs/2026-08-05-system-audit-logging-design.md` /
플랜 `docs/plans/2026-08-05-system-audit-logging-plan.md` /
원장 `docs/plans/2026-08-05-system-audit-logging-ledger.md` /
보존기간 분석 `docs/plans/2026-08-07-audit-retention-analysis.md`

## 현재 상태 (한 줄)
T1~T12 + 가독성 P4 A·B **운영 승격 완료**(2026-08-10, production `47f270e6`, PR #63),
**P4 C 운영 승격 완료**(2026-08-10, production `7ceedde4`, PR #69) — 쓰기 라우트 감사
커버리지 **100%**(AUDITED 142·EXEMPT 30·UNAUDITED 0, 게이트가 0 유지를 강제).
잔여는 사용자 액션(Sentry 로그 육안)과 D 단계(열람 기록 여부 결정)뿐.

## 원격 반영 완료
| 범위 | 원격 SHA | 확인 |
|---|---|---|
| T1~T3 (로깅 부트스트랩·금액 이벤트·주문 생성) | `d7f0d9ea` | CI 4/4 green |
| T4~T6 (첨부 soft delete·관리자 감사·파일 접근) | `156cb70c` | CI 4/4 green + 스테이징 E2E 13/13 |
| T8~T10 (security_logs 구조화·수명주기·Sentry) | `ede72253` | FOMS CI·PG Lane·perf-gate green (Harness 1건은 타 세션 AI_STATUS 초과가 원인, 후속 커밋에서 해소 확인) |
| T11 병합본 + 보존기간 권고안 + Sentry env 판정 | `e4aea16b` | Harness·perf-gate green, PG Lane red → 후속 커밋에서 근본 수정(아래) |
| T12 파일 열람 기록 화면 + PG 레인 시드 수정 | 아래 push 참조 | domains 4193·PG 712·smoke exit 0 |

## 잔여 작업 2건 — 완료 (2026-08-08)

### A. T11 병합 (사용자: "안전 판단 후 병합" 지시) — DONE
- 타 세션이 원격에 넣은 `UserDeletionBlockedError`(가입 거절 가드)와 T11(삭제→비활성화)은
  **의미상 공존 가능**으로 판정하고 병합했다. 판단 근거와 결과:
  - 차단 검사·`_detach_notification_user_states` 는 **hard delete 경로에만** 남긴다.
    비활성화는 `users` row 가 남아 FK 가 계속 유효하므로 차단할 이유가 없다
    (그 거부 메시지가 안내하던 "계정 비활성화"가 곧 이 경로다).
  - deploy 에서 뒤늦게 추가된 FK 컬럼 14종은 **운영 참조**로 분류(비활성화 시 NULL).
  - delete 라우트의 `except UserDeletionBlockedError` 는 제거(비활성화는 던지지 않음),
    거부 계약은 `reject_user` 라우트 테스트 2건으로 이전.
- 원격 반영 `e4aea16b`(T11 병합본 + 문서 4커밋).

### B. 파일 열람 기록 화면 — DONE
- `GET /admin/file-access-logs`(ADMIN 전용) + `templates/admin/file_access_logs.html`.
  필터 = 열람자·행위·기간(KST)·주문번호·파일 키, 페이지네이션 50행, 신규 인덱스 0.
- 함정 2개가 실제로 있었다(둘 다 계약 테스트로 고정):
  1. `access_logs.timestamp` 는 naive=UTC 인데 화면 입력은 KST 날짜 — 그대로 비교하면
     한국 오전 9시 이전 열람이 전날로 샌다(`_kst_date_bound_utc`).
  2. 주문 필터는 `additional_data` JSON **문자열** 매칭이라 구분자 없이 LIKE 하면
     주문 12 조회가 주문 123 을 끌고 온다(뮤테이션으로 red 실증 후 가드).

## 사용자 액션 대기
- **Sentry**: dev(FOMS-DEV)에 `SENTRY_DSN` 등록 완료 상태. Railway 로그에
  `Sentry initialized environment=...` 줄 확인만 남음. 운영 적용은 별도 지시.
- 로컬 실측 완료: errorhandler(Exception) 하에서도 이벤트 도달 확인,
  비밀번호·전화번호 마스킹 확인(URL·헤더·쿠키·예외 메시지 4곳).

## 운영 주의 (승격 전 필수)
1. purge cron은 미리보기가 아니라 **실삭제**(`--apply`가 receipt-purge cron에 체이닝됨).
   운영 반영 전 보존기간 최종 확인 — 현재 보안/발송 3년·파일열람 2년·알림 1년.
2. ~~운영 DB 마이그레이션 전~~ → **2026-08-10 해소**. 7종 적용(alembic `seclog_time_00`),
   `order_events` CASCADE FK 제거 확인 — 주문 hard purge 가 더 이상 감사 이력을 지우지 않는다.
3. ~~`security_logs` timestamp 인덱스 부재~~ → **2026-08-10 해소**
   (`ix_security_logs_timestamp_id`, SEC-LOG-TIME-00).

## 이월 (별건)
- EXTERNAL mutation writer 22곳 감축(T11 ③) — 인벤토리 타 세션 점유로 미착수.
- `security_logs` PII 분리(연락처 12.6%·주소 11.8% 혼입 실측).
- `access_logs.additional_data` 를 JSON 문자열 → JSONB 컬럼 승격(주문 축 조회가 지금은
  문자열 LIKE 다 — 관리자 cold path 라 당장 문제는 아니나 원장이 커지면 Seq Scan).
- `security_logs` `timestamp` 단독 인덱스 신설(아래 운영 주의 3번과 동일 건).
