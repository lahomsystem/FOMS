# AS 영업/택배 ↔ 영업 실측 일정 연동 — 설계 브리프 (CEO)

작성 2026-09-09. 목적: `/erp/as?tab=sales_delivery` 의 AS 건을 **영업담당의 실측 방문 일정에 배정**해서,
영업담당이 실측 나가는 길에 물건을 전달하게 만든다. 본 문서는 목업/구현 위임의 단일 브리프다.

## 0. 조사로 확정된 사실 (앵커)

### 0.1 AS 영업/택배 탭
- 라우트 `foms/web/cs/as_dashboard.py:234` (`GET /erp/as`), 탭 화이트리스트 `foms/services/as_dashboard_filters.py:49`.
- 탭 모집단 = **미완료 AS ∩ sales_delivery=true** — `foms/services/as_dashboard_read_model.py:64-67`.
  플래그 SSOT = `structured_data.shipment.sales_delivery` (`as_dashboard_helpers.py:156-161`).
  incomplete 탭과 상호배타(`read_model.py:60-63`). 운영 현재 4건 규모.
- 행 보강 `foms/services/as_dashboard_display.py:538`, `r.is_sales_delivery` = `:598`.
  주소는 `erp_display.apply_erp_display_fields_to_orders` 가 덮어씀. 좌표는 `Order.lat/lng` 컬럼 직독.
- 탭 카운트 = SUM(CASE) 단일 쿼리 `read_model.py:127-141`.
- 템플릿 `templates/cs/partials/as_dashboard_body.html` — 탭 네비 `:94-130`, PC 표 12열 `:217-255`,
  주소 셀 + `find-schedule-btn` `:331-345`, nearby 모달 `:546-599`, 스크립트 핀 `:629-643`.
- 모바일 카드 `templates/cs/partials/as_mobile_order_card.html:143-156`, 태블릿 대조 `tablet_as_compare_body.html:209-215`.
- 토글(영업/전달 체크)은 타임라인 헤더 `as_card_macros.html:94-97` / `as_round_chart.html:158-160`,
  저장은 `POST /api/update_order_field` (`foms/api/orders/field_update.py:623-627`, 응답에 `sales_delivery` 포함 `:327`).
  전용 라우트 `POST /erp/orders/<id>/as/classification` (`foms/api/cs/as_orders.py:941-973`) 는 현재 호출자 없음.

### 0.2 실측 화면 ("영업 실측")
- **코드에 "영업 실측" 이라는 이름은 없다.** 실체 = `/erp/measurement` 대시보드 본체
  (`foms/web/measurement/dashboard.py:119-498`). 탭 없음. 자가실측/지방은 배지·플래그로 구분,
  나머지가 곧 영업 방문 실측 (`status_constants.py:7` 주석: "C. 실측 (영업 방문 또는 고객 셀프)").
- 실측일 SSOT = `order_schedule_dates(kind='measurement')` (`models.py:232-253`),
  원천 `structured_data.schedule.measurement.date` (콤마 복수 가능, `foms/services/measurement_dates.py:21-63`).
  싱크 컬럼 `Order.measurement_date` = **첫 날짜만**.
- 담당자(영업담당) = `structured_data.parties.manager` → 폴백 `Order.manager_name`
  (`dashboard.py:281-290`), 색 팔레트 `foms/services/measurement_manager_colors.py`.
- 메인 표 8열(상세/고객/발주사/주소/전화/시간/제품/담당자) `templates/measurement/partials/dashboard_main.html:762-878`,
  상세행 `:881-1090`, 좌측 날짜 패널 `:117-145`, 표시 상한 300 (`measurement_read_model.py:109`).
- 좌표 = `Order.lat/lng/geocode_status` 컬럼. 지오코딩 SSOT `foms/services/geocode_helpers.py:130`,
  상태 4종 success/pending/failed/address_error.

### 0.3 nearby / schedule_link (재사용 자산 + 핵심 공백)
- **`GET /api/orders/nearby` 후보는 시공 일정뿐이다.** `type` 하드코딩 `"시공"`
  (`foms/services/schedule_recommendations.py:100`), 후보 로더 `load_construction_nearby_valid_items:112`.
  → **실측 일정은 후보 pool 에 아예 없다. 이번 작업의 핵심 공백.**
- 응답 `{success, by_distance, by_date, by_combined, search_radius_km, ref_lat, ref_lng}`,
  item `{id, customer_name, address, date, type, score_text, dist_km, lat, lng, distance_km?, duration_min?}`.
  반경 30km 단일, 리스트별 상위 5, 경로계산 ≤15건, DB 캡 2500, 지오코딩 워커 10.
- 재사용 가능 함수: `haversine_km:79`, `resolve_nearby_start_coordinates:177`,
  `compute_construction_nearby_success_payload:228`, `compute_construction_nearby_fallback_payload:379`.
- 링크 SSOT `foms/services/orders/as_schedule_link.py` — 경로 `schedule.as_visit.schedule_link`,
  **1 주문 1 링크, ref_kind='construction' 고정, 의미는 "AS 방문일을 남의 시공일에 맞춤"**.
  API `POST /api/orders/<id>/as/schedule-link` (`foms/api/cs/as_orders.py:1508`), drift 7상태.
- 프론트 모달 로직 전량 `static/js/cs/as-dashboard.js:2037-2380`.

### 0.4 UI 규약
- 토큰 2층: 정본 `static/css/foundation/foms-tokens.css` (`--foms-*`), 브리지 `erp-pro/01-intro-tokens.css` (`--erp-*`).
- 컴포넌트 클래스 `.erp-pro-btn/--primary`, `.erp-pro-badge/--*`, `.erp-pro-table`, `.erp-pro-card`, 칩은 `components/foms-*.css`.
- 모달 = Bootstrap 5 네이티브 (`getOrCreateInstance`), z=1070.
- 코호트 3종 legacy/v2/v3 — `foms/services/feature_flags.py:257`.
- 금지: 인라인 스타일 / jQuery / `JSON.parse('{{ x|tojson }}')`. 자산 변경 시 `?v=YYYYMMDD<rev>` 범프 필수.
- 목업 관행: `docs/design/mockups/*.html` 단일 자립 HTML, `mk-` 셸 + 섹션별 `#sec-*` 스코프 인라인 style,
  한국어 캡션·`.mk-note`(설계노트)/`--q`(미해결)/`--new`(신규)·`.mk-todo`(저장 필요 데이터) 범례.

## 1. 페르소나·문제 (deep think)

**P1 CS/AS 접수 담당 (사무실 PC)** — AS 건을 "영업/전달" 로 체크하는 순간 다음 행동이 없다.
누가 언제 가져다 줄지는 전화·카톡. 원하는 건 "이 주소 근처에 곧 가는 실측 일정이 있나?" 한 번의 조회와 배정.
공포: 배정해뒀는데 실측일이 밀리거나 취소되면 물건이 안 간다(= drift).

**P2 영업담당 (차 안, 모바일/태블릿)** — 자기 실측 일정만 본다. 전달 건은 별도 통보라 누락된다.
원하는 건 "오늘 내 실측 3건 중 위례 건 근처에 전달 1건, 뭘 챙겨야 하나" + 전달 완료 체크.
공포: 창고에서 물건 안 챙기고 출발.

**P3 관리자** — 미배정 전달 건이 며칠 묵었는지, 언제 택배로 돌릴지 판단.

## 2. 설계 결정 (CEO)

**D1. 새 축을 만든다. `as_visit.schedule_link` 를 재사용하지 않는다.**
그 링크는 "AS 기사 방문일을 시공일에 맞춤" 이고 1주문 1링크다. 전달 배정은 대상(실측)·의미(물건 운반)·
상태(픽업/전달)가 다르다. 덮어쓰면 AS 방문일이 실측일로 오염된다.
→ 신규 키 `structured_data.shipment.sales_delivery_link`
`{ref_order_id, ref_kind:"measurement", ref_date(D0), ref_manager, assigned_at, assigned_by_user_id, assigned_by,
  source:"as_sales_delivery_modal", ack_ref_date, status, status_at, status_by}`.
`status ∈ assigned | picked | delivered | failed`. 별도로 `sales_delivery_method ∈ sales | parcel`(+송장번호).

**D2. nearby 는 확장하되 기본값을 바꾸지 않는다.** `GET /api/orders/nearby?kind=measurement` 추가(기본 construction).
후보 로더 `load_measurement_nearby_valid_items` 신설 — 실측일 ≥ 기준일, 자가실측·지방 제외(영업 방문 실측만),
item 에 `manager`(영업담당) 추가. 기존 계약 테스트(`test_orders_boundary_contract.py:69,82`) 무손상.

**D3. 역방향(실측 화면)은 전량 로드 후 맵으로 푼다.** 모집단이 작다(미완료 sales_delivery AS = 운영 4건).
JSONB 인덱스 없는 스캔 금지 규약을 지키려면 **역질의 금지** — 대신 sales_delivery 미완료 AS 전량(캡 300)을
로드해 `ref_order_id → [전달건]` 딕셔너리를 만들고, 렌더된 실측 행에만 뱃지를 붙인다.

**D4. drift 는 기존 판정을 일반화한다.** `evaluate_drift` 는 순수 함수라 ref 현재 날짜만 주입하면 kind 무관.
실측일 이동/취소 시 배너·배지, 액션은 재배정/확인/해제.

**D5. 상태 전이는 한 방향 + 되돌리기 1단계.**
미배정 → (배정) assigned → (챙김) picked → (전달) delivered. 각 단계 되돌리기 허용, 이력은 AS 타임라인 system 로그.
택배 전환은 언제든 가능하고 전환 시 링크는 해제된다.

## 3. 화면 (목업 대상)

- **S1 PC AS 영업/택배 탭**: 행에 "전달" 셀 신설 — 미배정 버튼 / 배정칩(담당자·날짜·거리) / drift 배지 / 택배칩.
  상단에 요약 pill(미배정 N · 배정 N · 픽업 N · 전달완료 N). 지금 incomplete 탭만 있는 요약을 이 탭에도.
- **S2 배정 모달**: "실측 일정에 태우기". 후보 카드 = 실측일 D+n · 담당자(색칩) · 거리 · 그 담당자 그날 전달건 수.
  정렬 탭 거리/날짜/복합. 좌표 없으면 주소 토큰 fallback 배너.
- **S3 실측 대시보드**: 행 담당자 셀 옆 "전달 N" 뱃지, 상세행에 전달 카드(고객·품목·주소·픽업 체크).
  날짜 패널 카드에도 그날 전달 건수.
- **S4 모바일 영업담당(v3)**: 오늘 동선 — 실측 카드 아래 접힌 전달 체크리스트(챙김/전달 완료 토글).
- **S5 상태·엣지 노트**: 실측일 이동/취소, 담당자 변경, 실측 완료 후에도 미전달, 택배 전환, 좌표 없음.

## 4. 함정 (반드시 반영)

1. `as_visit.schedule_link` 침범 금지 (D1). legacy 키 `schedule.as_visit.shipment_recommendation` 부활 금지.
2. 신규 서버 전용 shipment 키 → `foms/api/orders/erp_orders_structured.py` 의 `_AS_SERVER_OWNED_SHIPMENT_KEYS` 등재.
   안 하면 ERP 폼 PUT 이 stale shipment 로 통째 되써서 배정이 사라진다.
3. 신규 mutation 라우트 = 레지스트리 4종 등재 (AUTH-01 / WRITE-GUARD-01 / REV-99 / FAILOPEN-01),
   push 전 `pytest tests/domains -q` 전체.
4. 탭 카운트 정규식 계약 `tests/domains/test_erp_as_dashboard_tabs.py:389-417` — 마크업 순서·속성명 고정.
5. `tests/postgres/test_scale_as.py:154-171` — sales_delivery JSONB 술어는 residual filter 로만.
6. 실측 복수 날짜: `Order.measurement_date` 는 첫 날짜만. 배정 D0 는 서버가 `order_schedule_dates` 에서 재조회.
7. 자산 `?v=` 범프 (as-dashboard.js, as-dashboard-body.css, 실측 쪽 CSS).
8. `.alert` 5초 자동 닫힘 — 실패를 alert 로만 알리면 무음 실패가 된다.
9. 좌표 없는 주문(geocode pending/failed) 비율 존재 → fallback UX 필수.

## 5. 검증 명령

- `python -c "import app; print('APP_OK')"`
- `pytest tests/domains -q`
- `pytest tests/domains/test_erp_as_dashboard_tabs.py tests/domains/test_as_schedule_link_api.py tests/domains/test_orders_boundary_contract.py -q`
- `scripts/ops/pre_push_smoke.ps1` exit 0
