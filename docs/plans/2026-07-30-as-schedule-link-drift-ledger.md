# Progress Ledger — AS 일정 매칭 링크 + 기준일 변경 감지 (2026-07-30)

스펙: `docs/specs/2026-07-30-as-schedule-link-drift-design.md`
플랜: `docs/plans/2026-07-30-as-schedule-link-drift-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T0 출고 `추가` 버튼 침묵 수정 (선행, 스펙 밖) | DONE | `APP_OK` + 58 passed. 미커밋 |
| T1 링크 서비스 순수 함수 | DONE | `as_schedule_link.py` 신규(순수함수, Flask/DB 무의존), 16 passed |
| T2 링크 API | DONE | `POST /api/orders/<id>/as/schedule-link` 4 action, 17 passed. write-guard·policy 매니페스트 등재 |
| T3 가까운 일정 찾기 매칭 버튼 | DONE | `.js-as-schedule-link` + `_searchState.excludeId` 사용, 무음실패 방지(parseJsonResponse+catch) |
| T4 드리프트 계산 + 대시보드 표시 | DONE | 배치 `in_(ids)` 1회, `drift_count` 배너 + 배지 매크로, 3 passed |
| T5 재적용/무시/해제 액션 | DONE | 재적용=기존 `saveDateField` 재사용 + relink, 5 passed |
| T6 출고 apply/cancel 링크 동기화 | DONE | 같은 tx 내 AS sd 변형(as_sd_mutator), 클로버 방지 가드, 28 passed |
| T7 기존 적용분 백필 | DONE | `tools/maintenance/backfill_as_schedule_links.py`(dry-run 기본, 멱등), 로컬 대상 0건 → pytest로 멱등 증명 |
| T8 최종 검증·커밋·푸시 | DONE | pre_push_smoke exit 0(253 passed), 커밋 `68be7a3a` → deploy push, ci_watch 감시 |

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

### T1~T7 (2026-07-30)
- `pytest tests/domains -q` → 3763 passed / 5 failed. 실패 3종(`test_rev_99`·`test_state_guard` ×2,
  `test_failopen_inventory`)은 **우리 변경 이전 HEAD 에서도 red** — 임시 worktree(HEAD detach)로 확인.
  원인은 타 세션 커밋 `8983dc6b`(ERP 낙관잠금)가 writer 인벤토리를 재생성하지 않은 것.
- 인벤토리 3종 재생성(`state_writer_scan.py` / `order_mutation_writer_scan.py` / `failopen_scan.py`)
  → 41 passed. 신규 EXTERNAL writer 없음(추가된 1건 `as_recommendation.py:191` 은 CANONICAL).
- `pytest tests/postgres -q` → 147 passed, 494 skipped(로컬 DSN 없는 레인 skip).

## 미해결 / 대기

- 스펙 승인 대기 → 승인 전 T1~T8 착수 금지.
- T0 커밋 여부는 사용자 결정(스펙 작업과 분리 커밋 권장).
- 출고 #3207 의 실제 거부 사유는 아직 미확인 — T0 수정 후 화면에 뜨는 메시지로 확정 필요
  (유력: `NO_SHIP_DATE`, 기준 출고건 시공일 없음).
