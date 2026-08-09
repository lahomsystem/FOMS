# 실행 플랜 — 출고 대시보드 시공일 변경 알림 (`**C`)

스펙: `docs/specs/2026-07-30-shipment-construction-date-change-alert-design.md` (승인 후 착수)
원장: `docs/plans/2026-07-30-shipment-construction-date-change-alert-ledger.md`
브랜치: `deploy` (푸시는 세션 커밋만 cherry-pick)

task 마다 완료 기준의 명령이 실제로 통과해야 DONE. T1 은 나머지 전부의 전제다.

---

## T1 — 시공일 변경 이벤트 SSOT 통합 (전제, 가장 위험)

**수정** `foms/services/order_date_sync.py` (`before_flush` 훅 `:282-315`)

- `OrderScheduleDate` 재빌드 시 이미 계산하는 construction 날짜 집합의 **이전/이후를 diff**
  하고, 달라졌으면 `OrderEvent(event_type="CONSTRUCTION_DATE_CHANGED")` 를 같은 flush 에
  add 한다(같은 훅에서 이미 row 를 add/delete 하는 선례가 있다).
- payload `{"from": <정규화된 이전값>, "to": <정규화된 이후값>, "source": <경로 힌트>}`.
  다중값은 콤마 연결, 순서 정규화(집합 비교라 순서 차이로 허위 이벤트를 만들지 않는다).
- actor: 요청 컨텍스트면 세션 사용자, 아니면 `None`(부팅 백필·스크립트).
- **기존 emit 2곳 제거**: `foms/api/erp_orders_structured.py:427-432`,
  `foms/api/orders/field_update.py:459-464` — 중복 방지. 제거 후에도 두 경로에서
  이벤트가 **정확히 1건** 생기는지 테스트로 고정.

**신규 테스트** `tests/domains/test_construction_date_event_ssot.py` — 경로별로 이벤트 1건:
PUT 전체저장 / PATCH 필드 / `update_order_field(scheduled_date)` /
**시공불가 재예약**(`foms/api/construction/orders.py:465`) /
**품목별 시공일 인라인 패치**(`foms/services/erp_inline_patch.py:66`) /
**레거시 편집 폼**(`foms/web/orders/edit.py:225`) / 엑셀 임포트 broadcast.
추가: 값이 안 바뀐 저장은 이벤트 0건, 날짜 표기만 다른 저장(`2026-07-20` vs `2026/07/20`)도 0건.

**완료 기준**
`python -m pytest tests/domains/test_construction_date_event_ssot.py tests/domains/test_production_change_alerts.py -q` green
(생산 칸반 기존 테스트가 함께 green 이어야 한다 — 소비자가 공유된다).

---

## T2 — 출고 변경 수집 서비스

**신규** `foms/services/shipment_change_alerts.py` — `production_change_alerts.py` 와 동형.

- `collect_shipment_change_alerts(db, orders, user_id) -> dict[int, dict]`
- 배치 1쿼리: `OrderEvent.order_id.in_(ids)` +
  `event_type.in_(("SHIPMENT_CHANGE_ACK", "CONSTRUCTION_DATE_CHANGED"))`
- 개인 윈도 = 본인 최근 ack 이후. 반환 `{"alerts": [...], "history": [...]}`,
  항목 `{"kind": "construction_date", "label": "시공일 변경", "from_md": "8/5", "to_md": "8/12"}`
- 배너용 요약(칩 최대 5 + overflow)도 같은 패스에서 만든다 — AS 배너 선례
  (`foms/services/as_dashboard_display.py` `_drift_banner_chip`).

**완료 기준**
`python -m pytest tests/domains/test_shipment_change_alerts.py -q` green — 윈도 판정
(ack 전/후), 다건 이벤트 병합 표기, 쿼리 횟수 1회 단언(N+1 가드).

---

## T3 — ack API

**신규 라우트** `POST /api/orders/<int:order_id>/shipment/change-ack`
(`foms/api/shipment/` 하위, 생산 선례 `foms/api/production/orders.py:983` 복제)

- Order 무변경 — `OrderEvent(SHIPMENT_CHANGE_ACK)` 1건만.
- 권한: 출고 편집 정책(`_shipment_edit_decision`) + 시공팀 차단(`recommendations.py:224-230`).
- idempotency receipt 는 선례 형태 그대로.
- 성공 후 출고 dashboard family 캐시 무효화.
- write-guard/policy 매니페스트 등재 필수(신규 라우트는
  `test_auth_enforcement.py::test_static_gate_every_mutation_route_classified` 가 잡는다).

**완료 기준**
`python -m pytest tests/domains/test_shipment_change_ack_api.py tests/domains/test_auth_enforcement.py -q` green —
비로그인 차단·권한 없음 차단·ack 후 alerts 비고 확인·연속 ack 멱등.

---

## T4 — PC 대시보드 표시

**수정** `foms/web/shipment/dashboard.py`(수집 호출, **캐시 밖**),
`templates/shipment/partials/dashboard_main.html`(배너 + `tr.shipment-row` 배지)

- 배너: 상단, 파스텔 톤 + 좌측 띠 + 대상 칩(고객명 · #id · `8/5 → 8/12`) + 점프.
  AS 배너와 같은 규약이되 출고 컨텍스트 CSS 에 둔다
  (`static/css/contexts/shipment/dashboard-table-extras.css`, 핀 `20260730c` 범프).
- 행 배지 + `확인` 버튼(`data-order-id`).
- 인라인 스타일 금지, 새 `<script>` 는 defer + 싱글톤 가드.

**완료 기준**
`python -m pytest tests/domains/test_shipment_change_alert_render.py tests/performance/test_perf_regression_guard.py tests/performance/test_page_local_defer_contract.py -q` green —
변경 있는 행에 배지·배너, 없으면 둘 다 부재, ack 후 부재.

---

## T5 — 태블릿 표시

**수정** `templates/shipment/partials/tablet_ship_grid.html`(행 배지),
`templates/shipment/partials/tablet_sheet.html`(스트립 — 생산 시트 `:66-85` 선례)

- 매크로 1개를 PC·태블릿·시트가 공유(표면별 마크업 포크 금지).
- 태블릿 코호트 게이트(서버 `erp_mobile_v2_enabled` + CSS MQ)를 새로 만들지 말고 기존 것 사용.
- 번들 CSS 범프가 필요하면 계약 테스트 2곳 락스텝
  (`test_tablet_rail_contract.py:162`, `test_tablet_t2_contract.py:715`).

**완료 기준**
`python -m pytest tests/domains/test_shipment_tablet_columns_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_tablet_domain_sheets_contract.py -q` green
+ 태블릿 렌더에 배지 존재를 단언하는 케이스 추가.

---

## T6 — 벨 알림 + 푸시

**신규** `foms/services/notifications/shipment_change.py`
(`production_change.py` 형태, 단 merge 결함은 답습하지 않는다)

- `Notification` type `SHIPMENT_ORDER_CHANGED`, `target_type="TEAM"`,
  `target_team=` **실제 팀 코드 확인 후 확정**(현재 이 팀 대상 알림 0건 — 값 검증 필요).
- 60초 debounce + merge(최초 `from` 보존 · 최신 `to` 갱신).
- `fan_out_new_notification` → `ensure_user_states`(공유 row 직접 수정 금지).
- **푸시 타입 등록**: `_DEFAULT_P1_TYPES`(`foms/services/notifications/push_sender.py:47`)에
  `SHIPMENT_ORDER_CHANGED` 추가 — 없으면 enqueue 해도 발송되지 않는다(생산이 그 상태).
- 호출 지점: T1 이벤트 emit 지점과 같은 트랜잭션에서. 커밋 후 finalize(푸시·배지 무효화·realtime).

**완료 기준**
`python -m pytest tests/domains/test_shipment_change_notification.py tests/domains/test_notifications_fan_out.py -q` green —
알림 1건 생성·수신자 팬아웃·debounce merge 시 from 보존·푸시 타입 등록 단언.

---

## T7 — 성능 측정

- 로컬/스테이징 `/erp/shipment?view=fragment` TTFB 측정 → **291ms 예산 내** 확인.
  초과 시 예산을 올리지 말고 쿼리/렌더를 줄인다(예산 상향은 과거 "증상 덮기" 판정 이력).
- `EXPLAIN` 으로 `order_events` 조회 계획 확인. Seq Scan 이면 복합 인덱스
  `(order_id, event_type, created_at)` 마이그레이션 추가(downgrade 포함) — **측정 후에만**.

**완료 기준** 측정값·EXPLAIN 출력을 원장에 기록 + `tests/performance` green.

---

## T8 — 최종 검증·커밋·푸시

- `python -c "import app; print('APP_OK')"`
- `python -m pytest tests/domains -q` (통과 or 사전 red 목록과 동일)
- `python -m pytest tests/postgres -q`
- `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` exit 0
- writer 인벤토리 3종 재생성(신규 EXTERNAL writer 없음 확인)
- 커밋(한글, `-F`) → 세션 커밋만 push → `ci_watch` green

---

## 함정 체크리스트 (모든 브리프에 포함)

1. **T1 이 전체의 전제** — 이벤트가 안 생기면 화면·벨 전부 무음이다. 경로별 테스트를 먼저 통과시켜라.
2. `before_flush` 안에서 `session.add` 는 허용되나, flush 재진입/무한루프를 만들지 마라(같은 훅의 기존 add/delete 패턴을 그대로 따를 것).
3. 변경감지는 **대시보드 슬라이스 캐시 밖**(TTL 300s stale 경고 방지). 선례가 명시적으로 그렇게 정했다.
4. TTFB 예산 291ms — 추가 쿼리는 배치 1회로 묶고 예산은 올리지 마라.
5. `order_events` 는 복합 인덱스가 없다. 측정 없이 선제 인덱스 금지, Seq Scan 확인되면 추가.
6. 푸시는 `_DEFAULT_P1_TYPES` 등록까지 해야 실제로 나간다(생산이 미등록이라 안 나가는 상태).
7. 알림 `user_states` 공유 row 직접 수정 금지 — `fan_out` 훅 경유.
8. 기존 JS/CSS 수정 = `?v=` 전 저장소 동시 범프. 태블릿 번들은 계약 테스트 2곳 락스텝.
9. 신규 mutation 라우트는 write-guard/policy 매니페스트 등재(정적 게이트 테스트가 잡는다).
10. 실패 무음 금지 — fetch 는 방어적 파싱 + `.catch` + 화면 노출.
