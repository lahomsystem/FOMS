# 주문 변경 사유 + 보존 실측 — Progress Ledger (ORDER-REASON-00 / RETENTION-00)

- 스펙: `docs/specs/2026-08-13-order-change-reason_SPEC.md`
- 작업 트리: `c:\tmp\foms-s-reason0813` (브랜치 `session/reason0813`, base `origin/deploy e496a9d2`)
- 주의: 메인 트리 `C:\DEV\FOMS` 의 로컬 `deploy` 는 `origin/deploy` 와 갈라져 있다
  (ahead 192 / behind 316, ORDER-DIFF 코드 부재) — **여기서 편집 금지**.

| T | 내용 | 완료 기준 | 상태 | 커밋 |
|---|---|---|---|---|
| T0 | 작업 트리·기준선 | heads 1개 · APP_OK · 기존 4종 36 passed | **DONE** | — |
| T1 | 스펙 문서 | 결정·경로·API·스키마 기재 | **DONE** | — |
| T2 | 서버 SSOT(중요 경로·사유 코드·판정 함수) | 신규 유닛 테스트 green | PENDING | |
| T3 | 모델 + 마이그레이션 | upgrade/downgrade 왕복 · heads 1 · PG 테스트 green | PENDING | |
| T4 | 저장 응답 확장(전체·인라인) + detail reason_code | 계약 테스트: required 판정·detail 예산 | PENDING | |
| T5 | 첨부 API + ACTION_LABELS | readability_3 green · 409/24h/권한 테스트 green | PENDING | |
| T6 | 프론트(PC 모달 · 인라인 배너) | `?v=` 범프 + 전수 grep 일치 · 로컬 스모크 | PENDING | |
| T7 | 이력 탭 표시 | field-changes 응답 reason · 탭 테스트 green | PENDING | |
| T8 | 보존 실측 리포트(운영 읽기전용) | 일평균 행수·90일 추정·크기·분포 표 + 보존안 3개 | PENDING | |
| T9 | 최종 검증·푸시 | pre_push_smoke exit 0 · deploy push · 전 워크플로 green | PENDING | |

## 기준선 (T0 실측, 2026-08-13)

```
alembic heads : senderphone_00 (head)   # 단일
import app    : APP_OK
pytest        : tests/domains/test_{structured_diff,order_field_changes_ledger,
                order_change_history_tab,structured_item_uid}.py = 36 passed
```

## 알려진 함정

- `security_logs.detail` 4,000자 초과 = 통째 표식 → `_DETAIL_CHANGES_BUDGET` 3,200 안에서만.
- 새 action 은 `ACTION_LABELS` 등재 필수(`tests/domains/test_admin_audit_screen_readability_3.py`).
- JS/CSS 수정 시 `?v=` 범프 + 저장소 전수 grep(핀 하드코딩 계약 테스트가 pre_push_smoke 밖).
  현재 핀: `order-change-history.js?v=20260811a` (`templates/orders/partials/edit_order_body.html:610`,
  `tests/domains/test_order_change_history_tab.py:149`).
- `tests/domains` 전체 실행 시 태블릿 계약 3건 red = 타 세션(`8a76c938`) 몫.
- 원장 쓰기 fail-open + `logger.warning(exc_info=True)`.
