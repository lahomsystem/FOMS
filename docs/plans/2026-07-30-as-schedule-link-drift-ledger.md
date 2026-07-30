# Progress Ledger — AS 일정 매칭 링크 + 기준일 변경 감지 (2026-07-30)

스펙: `docs/specs/2026-07-30-as-schedule-link-drift-design.md`
플랜: `docs/plans/2026-07-30-as-schedule-link-drift-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T0 출고 `추가` 버튼 침묵 수정 (선행, 스펙 밖) | DONE | `APP_OK` + 58 passed. 미커밋 |
| T1 링크 서비스 순수 함수 | PENDING | |
| T2 링크 API | PENDING | |
| T3 가까운 일정 찾기 매칭 버튼 | PENDING | |
| T4 드리프트 계산 + 대시보드 표시 | PENDING | |
| T5 재적용/무시/해제 액션 | PENDING | |
| T6 출고 apply/cancel 링크 동기화 | PENDING | |
| T7 기존 적용분 백필 | PENDING | |
| T8 최종 검증·커밋·푸시 | PENDING | |

## 검증 기록

### T0 (2026-07-30)
- 결함 3종: D1 `errEl` 항상 null(`closest('[data-as-order-id]')` 가 버튼 자신을 잡음),
  D2 `.catch` 부재 + `r.json()` 무방비, D3 성공 시 `adoptModalFromMain` 이 열린 모달 제거.
- 수정 파일: `static/js/shipment/shipment-dashboard.js`,
  `templates/shipment/partials/dashboard_main.html`(핀 `20260730f`→`g`),
  `templates/cs/partials/as_dashboard_body.html`(동일 핀 동기 범프).
- `python -c "import app; print('APP_OK')"` → `APP_OK`
- `pytest test_shipment_asrec_timeline.py test_shipment_as_recommendations.py
  test_erp_mobile_layout_and_shipment.py test_page_local_defer_contract.py -q` → **58 passed**
- 오케스트레이터 직접 보강 1줄: `adoptModalFromMain` 가드에 `prev.parentNode` 추가
  (detach 된 모달을 `.show` 만 보고 유지하면 새 사본까지 버려 모달이 사라진다).

## 미해결 / 대기

- 스펙 승인 대기 → 승인 전 T1~T8 착수 금지.
- T0 커밋 여부는 사용자 결정(스펙 작업과 분리 커밋 권장).
- 출고 #3207 의 실제 거부 사유는 아직 미확인 — T0 수정 후 화면에 뜨는 메시지로 확정 필요
  (유력: `NO_SHIP_DATE`, 기준 출고건 시공일 없음).
