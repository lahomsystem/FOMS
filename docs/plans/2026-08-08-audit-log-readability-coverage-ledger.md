# 진행 원장 — 감사 로그 가독성·커버리지 (AUDIT-LOG P4)

- 스펙: `docs/specs/2026-08-08-audit-log-readability-coverage-design.md`
- 플랜: `docs/plans/2026-08-08-audit-log-readability-coverage-plan.md`
- 상태: **A·B 완료 + 운영 승격 완료**(2026-08-10, production `47f270e6`). C·D 는 미착수.

| Task | 상태 | 완료 기준(통과할 명령/판정) | 커밋 |
|---|---|---|---|
| A1 표시 SSOT 모듈 신설 | DONE | 신규 17 passed + edit 관련 83 passed + APP_OK. 사전 이중정의 계약은 red 실증 후 이관으로 green | (아래 커밋) |
| A2 보안 로그 화면 적용 | DONE | 계약 9 passed + 배치 1쿼리 고정 + **운영 30일 전수 1,438건 역파싱 실패 0·개선 877건(60%)** + APP_OK | (A2·A3 커밋) |
| A3 거부 로그 분리 | DONE | 기본 숨김·스위치·페이지링크 계약 green(구조화·구형식 둘 다). 스테이징 실측은 push 후 | (A2·A3 커밋) |
| B1 주문 변경 구조화(before→after) | DONE | 4경로(field_update·regional·status·listing) 계약 5 passed + PII 최소성 계약 + 관련 170 passed | (B1·B2 커밋) |
| B2 문장 조립 SSOT 통일 | DONE | grep 계약 3 passed. 벌크 상태 로그 영문 코드 2곳 해소 | (B1·B2 커밋) |
| C1 커버리지 배선(묶음별) | PENDING | 묶음별 계약(행위 1건=원장 1행) + domains 전수 | — |
| C2 커버리지 게이트 | PENDING | 인벤토리 생성 + 인위 red 실증 + smoke 편입 | — |
| D1 열람 규모 계측 | PENDING | 1주 수집 후 수치 보고 → 사용자 결정 | — |
| D2 열람 기록 배선 | BLOCKED | D1 결과에 대한 사용자 결정 필요 | — |

## 운영 승격 (2026-08-10, PR #63)

- 사용자 명시 승인으로 **deploy 전체 승격**. 승격 커밋 `47f270e6`(병합 트리는 deploy 와 동일).
- 마이그레이션 7종 적용(alembic head `seclog_time_00`), `security_logs` 구조화 컬럼 4/4.
- 데이터 무손실 실측(7개 원장 전부 승격 전 이상), order_events CASCADE FK 제거 확인,
  `ix_security_logs_timestamp_id` 생성 확인, purge 즉시 삭제 0건, healthz 200.
- 백업 `c:/tmp/foms-backups/prod-pre-audit-promote-20260810.dump`(4.4MB·89테이블 검증).
- 함정: `-X theirs` 병합이 `auth/routes.py` 에 승인·거절 라우트를 **중복 정의**로 남겼다
  (옛 위치+새 위치) — Flask 엔드포인트 충돌 직전이었고, 트리를 deploy 기준으로 정정해 해소.
  전체 승격 시 `git checkout origin/deploy -- .` 로 트리 동일성을 강제 확인할 것.
- 미포함: 승격 직후 deploy 에 올라온 타 세션 커밋 `967097ac`(채널톡 AS PUSH).

## 결정 기록

- 2026-08-08 사용자: **"계획서만 먼저"** — 구현 착수 전 범위·순서 확정.
- 2026-08-08 사용자: 열람 기록 여부 **보류** — 실측(D1) 후 결정.
- 2026-08-09 사용자: **A+B 승인**. `/trash` 거부 282회는 권한 변경 없이 **로그 분리만**(A3).

## 실측 근거 (2026-08-08, 운영 읽기 전용)

- `security_logs` 24,605행 / 최근 30일 1,471건 / 거부 로그 474건(32%).
- 활성 29명 중 12명 최근 30일 보안로그 0건. wlsghv2 = 주문 변경 126건인데 보안로그 0건.
- 쓰기 라우트 172개 중 102개(59%) 감사 기록 호출 없음.
- 운영 DB에 `security_logs.action/target_type/target_id/detail` 컬럼 없음(T8 미승격).
