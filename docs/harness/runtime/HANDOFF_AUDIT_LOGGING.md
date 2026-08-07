# 인수인계 — 감사 로깅 (2026-08-07, 새 세션 재개용)

정본 문서: 스펙 `docs/specs/2026-08-05-system-audit-logging-design.md` /
플랜 `docs/plans/2026-08-05-system-audit-logging-plan.md` /
원장 `docs/plans/2026-08-05-system-audit-logging-ledger.md` /
보존기간 분석 `docs/plans/2026-08-07-audit-retention-analysis.md`

## 현재 상태 (한 줄)
T1~T11 전부 구현·검증 완료. **T8·T9·T10까지 원격 반영**(`ede72253`, CI green).
T11 + 문서 일부가 로컬 커밋으로 남아 있고, 잔여 작업 2건이 지시 대기 중.

## 원격 반영 완료
| 범위 | 원격 SHA | 확인 |
|---|---|---|
| T1~T3 (로깅 부트스트랩·금액 이벤트·주문 생성) | `d7f0d9ea` | CI 4/4 green |
| T4~T6 (첨부 soft delete·관리자 감사·파일 접근) | `156cb70c` | CI 4/4 green + 스테이징 E2E 13/13 |
| T8~T10 (security_logs 구조화·수명주기·Sentry) | `ede72253` | FOMS CI·PG Lane·perf-gate green (Harness 1건은 타 세션 AI_STATUS 초과가 원인, 후속 커밋에서 해소 확인) |

## 미push 로컬 커밋 (자기 세션)
- `a9b8ecb7` T11 — 사용자 삭제→비활성화 + FAILOPEN disposition 분리
- `05ba41f1` 3차 런 문서 마감 (원장·보고서·AI_STATUS)
- `82a1d752` 보존기간 정량 분석 문서
- `67f95d45` 보존기간 권고안 반영(security 1095·channel 1095·access 730·notification 365)

## 잔여 작업 (사용자 지시 완료 — 새 세션에서 착수)

### A. T11 cherry-pick 충돌 해결 (사용자: "내가 합쳐보기" 승인)
- 증상: `push_own_session_commits.py`로 `a9b8ecb7` pick 시 5파일 충돌
  (`foms/services/user_deletion.py`·`foms/web/auth/routes.py`·
  `tests/domains/test_user_delete.py`·`test_user_deletion.py`·
  `docs/harness/foms_failopen_inventory.json`).
- 원인: 타 세션이 원격에 `UserDeletionBlockedError`(가입 거절 흐름) 도입 — 같은 함수군.
- 지시: **충돌 내용을 먼저 분석해 "섞어도 안전한지" 판단 후, 안전하면 병합하고
  테스트로 확인. 위험하면 병합하지 말고 사용자에게 보고.**
- 판단 기준: T11은 `detach_user_references_for_deactivate`(신설, 운영 필드만 NULL)와
  `detach_user_references_for_delete`(기존, 전 필드 NULL) 2종 분리가 핵심.
  타 세션의 `UserDeletionBlockedError`는 삭제 차단 예외 — **의미상 충돌 없음**(공존 가능).
  검증: `pytest tests/domains/test_user_delete.py test_user_deletion.py
  test_failopen_inventory.py test_admin_audit_trail.py -q` + `APP_OK`.

### B. 파일 열람 기록 화면 (사용자: "지금 바로" 승인)
- 현재 `access_logs`는 writer만 있고 조회 UI 0 (설계상 "SQL 전용"이었음).
- 만들 것: 관리자 감사 영역(`foms/web/admin/audit.py` + `templates/admin/`)에
  **파일 열람 기록 탭** — 누가·언제·어떤 파일(storage_key)·어느 주문·IP·UA,
  필터(사용자·기간·action FILE_VIEW/FILE_DOWNLOAD/FILE_PRESIGNED·주문번호),
  페이지네이션. `security_logs.html` 최신 구조를 그대로 따를 것(같은 세션이 T8에서
  필터·페이지네이션 패턴 완성).
- 제약: ADMIN 전용(`role_required(["ADMIN"])`), 인덱스는 `(user_id, timestamp)`·
  `(timestamp)` 기존 것 활용(신규 인덱스 불필요), 템플릿에 인라인 스타일 금지,
  JS/CSS 신규 로드 시 `?v=` 범프, XSS 이스케이프 계약 테스트 필수.
- 완료 기준: 신규 계약 테스트(필터 동작·권한 차단·XSS) + `APP_OK` + smoke exit 0.

## 사용자 액션 대기
- **Sentry**: dev(FOMS-DEV)에 `SENTRY_DSN` 등록 완료 상태. Railway 로그에
  `Sentry initialized environment=...` 줄 확인만 남음. 운영 적용은 별도 지시.
- 로컬 실측 완료: errorhandler(Exception) 하에서도 이벤트 도달 확인,
  비밀번호·전화번호 마스킹 확인(URL·헤더·쿠키·예외 메시지 4곳).

## 운영 주의 (승격 전 필수)
1. purge cron은 미리보기가 아니라 **실삭제**(`--apply`가 receipt-purge cron에 체이닝됨).
   운영 반영 전 보존기간 최종 확인 — 현재 보안/발송 3년·파일열람 2년·알림 1년.
2. **운영 DB는 아직 T4~T11 마이그레이션 전** — `order_events`가 여전히 CASCADE라
   주문 hard purge가 감사 이력을 함께 지운다. T9 승격이 이 문제의 해소 조건.
3. `security_logs`에 `timestamp` 단독 인덱스 부재(실측) — 감사 화면이 전체 스캔.
   7년 규모에서 급격히 악화. 인덱스 1개로 해소 가능(별건 이월).

## 이월 (별건)
- EXTERNAL mutation writer 22곳 감축(T11 ③) — 인벤토리 타 세션 점유로 미착수.
- `security_logs` PII 분리(연락처 12.6%·주소 11.8% 혼입 실측).
