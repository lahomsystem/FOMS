# AS 영업/택배 ↔ 영업 실측 일정 배정 — 설계서

작성 2026-09-09 · 상태: **승인 대기** · 브리프: `docs/plans/2026-09-09-as-sales-delivery-measurement-link-brief.md`
목업: Claude Design 캔버스 "AS 전달 배정 화면" (아트보드 5장)

## 1. 목적과 범위

AS 대시보드 영업/택배 탭(`/erp/as?tab=sales_delivery`)의 전달 건을 **영업담당의 실측 방문 일정**에 배정해,
영업담당이 실측 나가는 길에 물건을 전달하게 한다.

**범위 안**: 배정/해제/재배정/일정변경 확인, 전달 완료 기록, 택배 전환, AS 탭·실측 대시보드·모바일 3표면 렌더,
nearby 후보에 실측 일정 추가.
**범위 밖**: 알림톡·푸시 발송, 자동 배정(추천만 하고 사람이 누른다), 택배사 API 연동(송장번호는 수기 입력),
지방 실측·자가실측(후보에서 제외).

**사용자 결정 (2026-09-09)**
- 상태는 **3단계**: `미배정 → 배정 → 전달완료`. 창고 픽업(챙김) 단계는 만들지 않는다.
- 근처 실측 후보가 0건이면 **택배 전환을 우선 제안**한다.

## 2. 데이터 모델

### 2.1 신규 키 (SSOT)

`structured_data.shipment.sales_delivery_link`

```
{
  ref_order_id: int,          # 실측 주문 id
  ref_kind: "measurement",    # 고정
  ref_date: "YYYY-MM-DD",     # 배정 시점 실측일 D0 (서버가 재조회해서 기록)
  ref_manager: str,           # 배정 시점 실측 담당자 이름 스냅샷
  assigned_at: iso,
  assigned_by_user_id: int|null,
  assigned_by: str,
  source: "as_sales_delivery_modal",
  ack_ref_date: "YYYY-MM-DD"|null,   # 일정 변경을 확인 처리한 기준일
  status: "assigned" | "delivered",
  delivered_at: iso|null,
  delivered_by: str|null
}
```

`structured_data.shipment.sales_delivery_method` = `"sales"`(기본) | `"parcel"`
`structured_data.shipment.sales_delivery_parcel` = `{carrier, tracking_no, sent_at, sent_by}` (method=parcel 일 때만)

### 2.2 표시 상태 유도 (읽기 SSOT, 순수 함수)

| 표시 상태 | 조건 |
|---|---|
| 미배정 | method != parcel 이고 link 없음 |
| 배정 | link.status == "assigned" |
| 전달완료 | link.status == "delivered" |
| 택배 | method == "parcel" (link 은 해제되어 없음) |
| 일정 변경 | 배정 상태 + drift state ∈ (ref_moved, ref_gone) |

### 2.3 기존 축과의 관계 (절대 규칙)

- `structured_data.schedule.as_visit.schedule_link` **침범 금지**. 그건 "AS 기사 방문일을 남의 시공일에 맞춤"
  축이고 1주문 1링크다. 덮어쓰면 AS 방문일이 실측일로 오염된다.
- legacy 키 `schedule.as_visit.shipment_recommendation` 부활 금지(읽는 코드 3곳 생존).
- 신규 키 3개는 **서버 전용**이다 → `foms/api/orders/erp_orders_structured.py` 의
  `_AS_SERVER_OWNED_SHIPMENT_KEYS` 에 등재. 안 하면 ERP 폼 PUT 이 stale shipment 로 되써서 배정이 사라진다.

## 3. 서비스 계층

**신규** `foms/services/orders/sales_delivery_link.py` — Flask/DB 임포트 금지 순수 모듈
(`as_schedule_link.py` 와 같은 규율. 공유가 아니라 **복제**다: 경로·상태·액션이 다르다).

```
LINK_PATH = ("shipment", "sales_delivery_link")
read_link(sd) / write_link(sd, ...) / clear_link(sd) / ack_link(sd, ref_current_date)
mark_delivered(sd, *, at, by) / unmark_delivered(sd)
set_method(sd, method, parcel=None)
evaluate_drift(sd, ref_current_date) -> {state, ref_order_id, ref_date, ref_current_date, ref_manager}
derive_display_state(sd) -> "unassigned"|"assigned"|"delivered"|"parcel"
```

drift 상태값: `none | ok | ref_moved | acked | resolved | ref_gone`
(`both_moved` 는 이 축에 없다 — 전달 건 자체에는 날짜가 없으므로 기준일만 움직인다).
`deepcopy` + `flag_modified` 는 호출자 책임(프로젝트 규약).

## 4. 후보 조회 API

### 4.1 확장: `GET /api/orders/nearby?kind=measurement`

- 기본값 `kind=construction` 유지 → 기존 계약 테스트(`test_orders_boundary_contract.py:69,82`) 무손상.
- 신규 로더 `load_measurement_nearby_valid_items(db, ref_date, exclude_id)` in
  `foms/services/schedule_recommendations.py`:
  - 후보 = `OrderScheduleDate.kind=='measurement'` 이고 date >= ref_date
  - 제외 = 삭제/자가실측(`is_self_measurement` 또는 status SELF_MEASUREMENT/SELF_MEASURED)/지방(`is_regional`)
  - load_only + `selectinload(schedule_dates)`, DB 캡 2500, 좌표는 `geocode_status=='success'` 행만 신뢰
- item 스키마 = 기존 + `type: "실측"`, `manager`, `manager_color`, `assigned_count`
  (`assigned_count` = 그 실측 주문에 이미 배정된 전달 건 수. 3건 이상이면 프론트가 "동선 과부하" 경고)
- 응답에 `parcel_suggested: true` 추가 — 30km 내 후보 0건일 때. 프론트는 이때 택배 전환을 우선 노출한다.
- 반경 30km·리스트별 5건·경로계산 15건 예산은 그대로. **route_timeout_sec=3.0 을 넘긴다**
  (현재 nearby 는 None 이라 무제한 — 실측 후보는 건수가 많아 타임아웃을 반드시 건다).

### 4.2 역방향 맵 (실측 대시보드용)

`foms/services/orders/sales_delivery_map.py` — `build_sales_delivery_by_ref(db, *, cap=300) -> {ref_order_id: [row]}`

- 모집단 = 미완료 AS ∩ `sales_delivery=true` (기존 `_sales_delivery_true_filter` 재사용) 전량 로드.
  현재 운영 4건 규모라 인덱스 없이 안전. cap 초과 시 `truncated=True` 공시(대시보드 캡 공시 규약).
- **JSONB 역질의(ref_order_id 로 WHERE) 금지** — 인덱스가 없다. 파이썬 dict 로 뒤집는다.

## 5. 쓰기 API

**신규** `POST /api/orders/<int:order_id>/sales-delivery` (`erp_orders_as_bp`, `@login_required @erp_edit_required`)

| action | body | 효과 |
|---|---|---|
| `assign` | `ref_order_id` | 링크 생성(status=assigned). ref_date·ref_manager 는 **서버가 실측 주문에서 재조회**(클라 값 불채택) |
| `reassign` | `ref_order_id` | 기존 링크 교체, ack 리셋 |
| `ack` | — | 변경된 실측일을 그대로 수용(`ack_ref_date` 기록) |
| `unassign` | — | 링크 해제. 멱등(이미 없으면 mutation 없이 200) |
| `deliver` | — | status=delivered + 시각·행위자 |
| `undeliver` | — | status=assigned 로 되돌림 |
| `parcel` | `carrier?, tracking_no?` | method=parcel + 링크 해제 |
| `parcel_cancel` | — | method=sales 복귀 |

- 400: 잘못된 action / ref_order_id 없음 / 자기참조 / 실측일 없는 주문
- 404: 기준 주문 없음·삭제됨 · 409: ack·reassign 인데 링크 없음
- 쓰기는 `execute_order_mutation`(`_run_sd_mutation` 패턴) 경유, `command_id="AS_SALES_DELIVERY"`,
  정책 id 신설 `POLICY_AS_SALES_DELIVERY`, If-Match 지원.
- 감사: `AS_SALES_DELIVERY_CHANGED` — **`audit_message_display` 라벨 등재 필수**(누락 시 감사 화면 공백).
- AS 타임라인 system 로그: `assign` / `unassign` / `deliver` / `parcel` 4개만 남긴다(ack·reassign 은 소음).
- 응답 `{success, link, drift, display_state, method}`.
- **레지스트리 4종 등재**: AUTH-01 `foms_order_mutation_policy_manifest.json`,
  WRITE-GUARD-01 `foms_write_guard_manifest.json`, REV-99 `order_mutation_writer_scan.py` 재생성,
  FAILOPEN-01 `failopen_scan.py` 재생성.

## 6. 읽기 모델·렌더

### 6.1 AS 영업/택배 탭

- `as_dashboard_display.apply_as_dashboard_row_display_fields` 에 추가:
  `r.sales_delivery_state`, `r.sales_delivery_link`(칩용 축약 dict), `r.sales_delivery_drift`, `r.sales_delivery_method`.
- 기준 실측 주문의 현재 실측일은 **렌더된 행 집합 한정 배치 조회**(`in_(ref_ids)`), 전체 스캔 금지.
- 요약 pill(미배정/배정/전달완료/택배)은 탭 카운트 SQL 을 건드리지 않고 **렌더된 행에서 파이썬 집계**
  — 기존 정규식 계약(`test_erp_as_dashboard_tabs.py:389-417`)이 탭 마크업을 고정하고 있어 그쪽은 손대지 않는다.
- 템플릿: `as_dashboard_body.html` 표에 "전달 배정" 열 1개 추가(12열 → 13열, colgroup 동시 수정),
  모바일 카드·태블릿 대조 표면에도 칩 렌더. 매크로는 `as_card_macros.html` 에 `render_sales_delivery_cell` 신설.

### 6.2 실측 대시보드

- `foms/web/measurement/dashboard.py` 에서 `build_sales_delivery_by_ref` 호출 → 행에 `r.sales_delivery_items`.
- 고객 셀 배지 `전달 N`, 상세행에 전달 카드(품목·주소·거리·[전달 완료]), 날짜 패널 카드에 `전달 N` 배지
  (날짜 패널은 60일 base 캐시를 쓰므로 **캐시 키에 전달 맵을 넣지 말고** 배지는 렌더 시점 조인으로 붙인다).

### 6.3 모바일 v3

- 페르소나 홈(sales)에 "오늘 동선" 섹션 — 실측 카드 아래 전달 서브카드 + `전달 완료` 버튼(48px).
- v3 셸은 surfaces 번들을 안 싣는다 → 필요한 CSS 는 `css/v3/foms-mobile-v3.css` 계열에 넣는다.

## 7. 프론트엔드

- `static/js/cs/as-dashboard.js` 에 신규 IIFE `salesDeliveryAssign` — 기존 nearby IIFE 를 **재사용하지 않고 분리**
  (모달·상태·엔드포인트가 다르다). 이벤트는 기존 `addAsDashboardListener` 위임 인프라 사용.
- 모달은 Bootstrap 5 네이티브(`getOrCreateInstance`), 마크업은 `as_dashboard_body.html` 에 `#salesDeliveryModal`.
- fetch 는 try/catch + `data.success` 검증. CSRF 는 전역 인터셉터가 붙인다(수동 금지).
- 실패 알림을 `.alert` 로만 하지 않는다(5초 자동 닫힘 → 무음 실패). 버튼 인라인 상태 텍스트 병행.
- 자산 `?v=` 범프: `as-dashboard.js`, `contexts/cs/as-dashboard-body.css`, 실측 쪽 CSS, v3 CSS.

## 8. 테스트 계약 (신규)

- `tests/domains/test_sales_delivery_link.py` — 순수 함수: 스키마 정확형, 재배정 시 ack 리셋, drift 상태,
  택배 전환이 링크를 지운다, delivered 되돌리기.
- `tests/domains/test_sales_delivery_api.py` — 권한(로그인·erp_edit), 클라 ref_date 무시, 자기참조 400,
  404/409, unassign 멱등, 타임라인 로그 4종만, 감사 라벨 존재.
- `tests/domains/test_nearby_measurement_kind.py` — `kind=measurement` 응답 키, 자가실측·지방 제외,
  후보 0건 시 `parcel_suggested`, 기본값이 여전히 construction.
- `tests/domains/test_as_dashboard_sales_delivery_render.py` — 4상태 셀 렌더, drift 배지, 요약 pill,
  자산 핀 동기화, 기존 탭 카운트 정규식 불변.
- `tests/domains/test_measurement_sales_delivery_render.py` — 실측 행 배지·상세 카드, 캡 공시.
- `tests/domains/test_erp_structured_preserves_sales_delivery.py` — ERP 폼 PUT 후 링크 생존(서버 전용 키).
- `tests/postgres/test_scale_as.py` 확장 — 신규 술어가 Index Cond 에 새지 않음.

## 9. 성능

- 신규 SQL 은 3개뿐: 후보 로더(캡 2500·load_only), 렌더 행 한정 기준일 배치 조회(`in_`),
  역방향 맵 전량 로드(캡 300). 전부 JSONB `ilike` 없음, N+1 없음.
- 실측 대시보드 TTFB 측정 + `EXPLAIN` Seq Scan 확인은 T5 에서 수행(perf 가드 규약).

## 10. 작업 순서 (task ledger 초안)

| T | 내용 | 완료 기준 |
|---|---|---|
| T1 | 순수 서비스 + 테스트 | `pytest tests/domains/test_sales_delivery_link.py -q` green |
| T2 | 쓰기 API + 레지스트리 4종 + 감사 라벨 | `pytest tests/domains -q` green (계약군 포함) |
| T3 | nearby `kind=measurement` | 신규 테스트 green, 기존 boundary 계약 불변 |
| T4 | AS 탭 읽기모델·템플릿·JS·모달 | 렌더 테스트 green, 로컬 dev 화면 확인 |
| T5 | 실측 대시보드 역방향 배지·상세 카드 | 렌더 테스트 green + TTFB 측정 |
| T6 | 모바일 v3 동선 섹션 | 렌더 테스트 green |
| T7 | 전체 게이트 + 스테이징 QA | `pytest tests/domains -q`, pre_push_smoke exit 0, 스테이징 실화면 |

## 11. 검증 명령

```
python -c "import app; print('APP_OK')"
pytest tests/domains -q
pytest tests/postgres/test_scale_as.py -q
scripts/ops/pre_push_smoke.ps1   # exit 0
```
