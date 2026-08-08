# 진행 원장 — 감사 로그 가독성·커버리지 (AUDIT-LOG P4)

- 스펙: `docs/specs/2026-08-08-audit-log-readability-coverage-design.md`
- 플랜: `docs/plans/2026-08-08-audit-log-readability-coverage-plan.md`
- 상태: **승인 대기** — 승인 전 어떤 task 도 착수하지 않는다.

| Task | 상태 | 완료 기준(통과할 명령/판정) | 커밋 |
|---|---|---|---|
| A1 표시 SSOT 모듈 신설 | PENDING | 신규 `test_audit_message_display.py` green + edit.py 라벨 이관 회귀 green + 사전 이중정의 0 계약 | — |
| A2 보안 로그 화면 적용 | PENDING | 3경로(구조화/구형식/파싱실패) 계약 + 쿼리수 고정 + 운영 표본 20건 생성 실패 0 + APP_OK·smoke 0 | — |
| A3 거부 로그 분리 | PENDING | 기본 숨김·스위치 계약 + 스테이징 실측 | — |
| B1 주문 3경로 구조화(before→after) | PENDING | 3경로 계약 + PII 최소성 + domains 전수 + 스테이징 실검증 | — |
| B2 문장 조립 SSOT 통일 | PENDING | grep 계약(라우트 직접 조립 0건) | — |
| C1 커버리지 배선(묶음별) | PENDING | 묶음별 계약(행위 1건=원장 1행) + domains 전수 | — |
| C2 커버리지 게이트 | PENDING | 인벤토리 생성 + 인위 red 실증 + smoke 편입 | — |
| D1 열람 규모 계측 | PENDING | 1주 수집 후 수치 보고 → 사용자 결정 | — |
| D2 열람 기록 배선 | BLOCKED | D1 결과에 대한 사용자 결정 필요 | — |

## 결정 기록

- 2026-08-08 사용자: **"계획서만 먼저"** — 구현 착수 전 범위·순서 확정.
- 2026-08-08 사용자: 열람 기록 여부 **보류** — 실측(D1) 후 결정.

## 실측 근거 (2026-08-08, 운영 읽기 전용)

- `security_logs` 24,605행 / 최근 30일 1,471건 / 거부 로그 474건(32%).
- 활성 29명 중 12명 최근 30일 보안로그 0건. wlsghv2 = 주문 변경 126건인데 보안로그 0건.
- 쓰기 라우트 172개 중 102개(59%) 감사 기록 호출 없음.
- 운영 DB에 `security_logs.action/target_type/target_id/detail` 컬럼 없음(T8 미승격).
