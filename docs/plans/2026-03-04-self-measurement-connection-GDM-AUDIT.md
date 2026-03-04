# 자가실측 대시보드 연결 구현 — GDM 감리 보고서

**감리 일자:** 2026-03-04  
**대상 계획서:** `docs/plans/2026-03-04-self-measurement-connection-plan.md`  
**감리 주체:** Grand Develop Master (GDM)

---

## 1. 무엇을 발견했는가 (What was found)

### 1.1 계획서 요구사항 대비 구현 현황

| 계획서 § | 요구사항 | 구현 위치 | 준수 |
|----------|----------|-----------|------|
| 2.1 UI | 긴급 옆 "자가실측" 체크박스, ID `erp-self-measurement` | `erp_beta_tab.html` L71~74 | ✅ |
| 2.1 JS | 저장 시 `is_self_measurement` 최상위 전송 | `erp_beta_js.html` L696 (JSON.stringify 최상위) | ✅ |
| 2.1 JS | 불러오기 시 체크박스 상태 반영 | `erp_beta_js.html` L470~471 (`data.is_self_measurement`) | ✅ |
| 2.2 API | GET 응답에 `is_self_measurement` | `erp_orders_structured.py` L100 | ✅ |
| 2.2 API | PUT에서 payload 저장 | `erp_orders_structured.py` L131, L143~144 | ✅ |
| 2.3 실측 | 자가실측 주문 실측 대시보드 포함 | `erp_measurement_dashboard.py` L95~102 (`or_(..., Order.is_self_measurement == True)`) | ✅ |
| 2.3 실측 | 4체크 완료 시 목록에서 제외 | `erp_measurement_dashboard.py` rows 루프 + `self_measurement_four_checks_done()` | ✅ |
| 2.3 실측 | 패널 카운트 동기화 | 동일 파일 panel_orders 루프 + 동일 헬퍼 | ✅ |
| 2.4 시공 | 4체크 미완료 시 타일/목록 제외 | `erp_construction_page.py` + `services.erp_display.self_measurement_four_checks_done()` | ✅ |
| 2.4 시공 | enriched에 `is_self_measurement` 전달 | 동일 파일 L143 | ✅ |
| 2.5 배지 | 실측/시공 리스트 고객명 옆 배지 | `erp_measurement_dashboard.html` L493~494, `erp_construction_filters_grid.html` L236~237 | ✅ |

### 1.2 Rollback(역방향 이동) 검증

- **요구:** 체크 해제 시 시공에서 사라지고 실측으로 복귀.
- **구현:** 시공은 `is_self and not all_done → continue`이므로, 4체크 중 하나라도 False가 되면 `all_done`이 False → 해당 주문은 시공 목록/타일에서 제외됨. 실측은 `is_self and all_done → continue`이므로, all_done이 False인 주문은 실측에서 제외되지 않음(다시 실측에 노출). **✅ 로직 일치.**

### 1.3 GDM 원칙 대비 평가 (계획서 §3)

- **구조적 의심:** "어떤 대시보드에서 보일지"를 Gating Filter(4체크 AND)로만 판단. 신규 워크플로우 이벤트/상태 없음. **✅ 준수.**
- **오컴의 면도날:** 4개 체크 AND 한 번으로 시공 진입 여부 판단, 5줄 수준 로직. **✅ 준수.**

### 1.4 기타 발견

- **데이터 소스:** 계획서는 fillBetaForm에서 "sd.is_self_measurement 보강"을 언급했으나, 구현은 API 응답 최상위 `data.is_self_measurement` 사용. GET이 최상위에서 내려주므로 단일 소스로 적절함. **✅ 개선적 준수.**
- **기존 자가실측 경로:** `order_edit`/`order_pages`/`add_order`/`self_measurement_dashboard` 등 기존 `is_self_measurement` 플로우와 충돌 없음. ERP Beta 경로(structured API)와 주문편집 폼 경로가 공통 Order 컬럼만 사용.

---

## 2. 무엇을 검토/검증했는가 (Scope of audit)

- 계획서 §2.1~§2.5 전 항목과 실제 코드 매핑.
- 실측 base_query 변경 시 자가실측 포함 조건(`or_`) 및 기존 비자가실측 조건과의 공존 여부.
- 실측 rows/panel_orders, 시공 step_stats/enriched 두 루프에서 동일 4체크 정의 사용 여부.
- 배지 노출 위치(고객명 옆) 및 템플릿 변수(`r` / `o`) 정합성.

---

## 3. 왜 이 결론인가 (근거 및 매뉴얼 준수)

- **계획서:** "4개 필수 체크리스트 … 모두 체크완료 … 실측에서 제거, 시공으로 이동" / "하나라도 체크 풀리면 시공에서 사라지고 실측으로 복구"를 명시. 현재 구현은 두 조건을 각각 "실측 rows/panel 제외"와 "시공 타일/목록 제외"로만 처리하여, 신규 상태/이벤트 없이 기존 Order 불리언 필드만 사용. **매뉴얼(계획서) 100% 준수.**
- **GDM 원칙:** 단순화(추가 상태 없음), 구조적 의심(표시 여부를 데이터 통과 조건으로만 정의), 오컴(최소 로직) 모두 충족.

---

## 4. 감리 결론

| 항목 | 판정 |
|------|------|
| 계획서 §2 전조항 이행 | **합격** |
| Rollback 요구사항 | **합격** |
| GDM 원칙(§3) 적용 | **합격** |
| 기존 자가실측/지방 플로우와의 정합성 | **이상 없음** |

**종합:** `2026-03-04-self-measurement-connection-plan.md` 상의 구현이 코드에 반영되어 있으며, 요구사항 및 GDM 원칙에 부합한다. 운영 전 실측/시공 화면에서 자가실측 주문 4체크 완료·해제 시나리오만 수동으로 한 번씩 확인할 것을 권장한다.

---

## 5. 사후 이슈: 배지 미노출 (2026-03-04 보완)

### 현상
실측/시공 대시보드에서 "자가실측" 배지가 보이지 않음.

### 근본 원인 (구조적 의심)
- **실측:** 템플릿에서 `getattr(r, 'is_self_measurement', False)` 사용. Jinja2에는 **getattr가 내장되어 있지 않음**. Flask가 별도로 노출하지 않으면 undefined 또는 잘못된 평가로 조건이 거짓이 됨.
- **시공:** `o.is_self_measurement`만 사용 시, 키가 없거나 undefined일 때 예외/미표시 가능.

### 수정 (단순화 우선 · 오컴)
- **실측** `erp_measurement_dashboard.html`: `getattr(r, ...)` 제거 → **속성 직접 접근** `r.is_self_measurement|default(false)`.
- **시공** `erp_construction_filters_grid.html`: `o.is_self_measurement|default(false)` 로 통일해 키 부재 시에도 안전하게 표시.

데이터는 이미 서버(Order / enriched)에서 내려오므로, Jinja에서는 **속성/키 접근 + default 필터**만 사용하도록 정리함.

---

## 6. 배지 노출 위치 및 미노출 원인 분석 (철저 분석)

### 6.1 "자가실측" 배지가 노출되는 화면·위치 (코드 기준)

| # | 화면(URL/라우트) | 템플릿/데이터 | 노출 위치(UI) | 데이터 소스 |
|---|------------------|----------------|----------------|-------------|
| 1 | **ERP 대시보드(메인)** `/erp/dashboard` | `partials/erp_dashboard_grid.html` | 작업 큐 그리드 **고객** 열 | `enriched`(dict). `o.is_self_measurement` (뷰 주입) |
| 2 | **ERP 실측** `/erp/measurement` | `erp_measurement_dashboard.html` | 테이블 **고객** 열 | `rows`(Order). `r.is_self_measurement` |
| 3 | **ERP 도면작업실** `/erp/drawing-workbench` | `erp_drawing_workbench_dashboard.html` | 테이블·모바일 카드 **주문/고객** | `rows`(dict). `r.is_self_measurement` (뷰 주입) |
| 4 | **ERP 생산** `/erp/production/dashboard` | `partials/erp_production_filters_grid.html` | 그리드 **고객** 열 | `enriched`(dict). `o.is_self_measurement` (뷰 주입) |
| 5 | **ERP 출고** `/erp/shipment` | `erp_shipment_dashboard.html` | 테이블 **고객** 셀 | `rows`(Order). `r.is_self_measurement` |
| 6 | **ERP 시공** `/erp/construction/dashboard` | `partials/erp_construction_filters_grid.html` | 그리드 **고객** 열 | `enriched`(dict). `o.is_self_measurement` |
| 7 | **ERP 시공 완료** `/erp/completion` | `partials/erp_completion_scripts.html` (JS) | 완료·AS 건 요약 줄(고객명 옆) | `/api/orders/completion` 응답 `is_self_measurement` |
| 8 | **ERP AS** `/erp/as` | `erp_as_dashboard.html` | 테이블·카드 **고객** 셀 | `rows`(Order). `r.is_self_measurement` |
| 9 | **자가실측 전용** `/self_measurement_dashboard` | `self_measurement_dashboard.html` | 4개 섹션 테이블 **고객명** 셀 | 전 행 자가실측이므로 항상 배지 |

- **배지 HTML:** `<span class="badge bg-info text-white ms-1" title="자가실측"><i class="fas fa-ruler-combined"></i> 자가실측</span>`

### 6.2 데이터 흐름 요약

- **ERP 실측:** `erp_measurement_dashboard.py`에서 `base_query`에 `Order.is_self_measurement == True` 포함 → `all_rows` 로드 후 4체크 미완료 자가실측은 `rows`에 포함. 템플릿은 `{% for r in rows %}`에서 `r.is_self_measurement|default(false)`로 배지 표시.
- **ERP 시공:** `erp_construction_page.py`에서 4체크 완료된 자가실측만 목록/타일에 포함하고, `enriched`에 `'is_self_measurement': is_self` 넣어 전달. 템플릿은 `o.is_self_measurement|default(false)`로 배지 표시.
- **자가실측 전용 대시보드:** `dashboards.self_measurement_dashboard()`가 `Order.is_self_measurement == True`로만 조회하므로, 여기 테이블의 모든 행에 배지를 붙이면 됨(추가 조건 불필요).

### 6.3 배지가 안 보일 수 있는 원인 (체크리스트)

| 원인 | 적용 화면 | 설명 |
|------|-----------|------|
| **보고 있는 화면이 다름** | 전부 | 스크린샷에 "진행중", "발주방 등록 전", "실족" 등이 있으면 **자가실측 전용 대시보드**(`/self_measurement_dashboard`)임. 계획서상 배지는 원래 **ERP 실측/시공** 두 화면에만 구현되어 있었고, 자가실측 전용 대시보드에는 **아이콘만** 있었음(배지 없음). → **조치:** 자가실측 전용 대시보드에도 동일 배지 추가(§6.1 표 #3). |
| **해당 주문이 자가실측이 아님** | ERP 실측/시공 | 주문 상세에서 "자가실측" 체크를 안 했거나, API PUT으로 `is_self_measurement`가 저장되지 않으면 DB가 False. → 배지 조건 `r.is_self_measurement|default(false)`가 거짓. |
| **ERP 시공에서 4체크 미완료** | ERP 시공 | 자가실측 주문은 4체크(실측완료·영업발주 업로드·도면 발송·발주 업로드)가 **모두 완료**되어야 시공 대시보드 목록에 포함됨. 하나라도 미체크면 시공 목록에 아예 안 나와서 배지도 안 보임. |
| **ERP 실측에서 4체크 완료** | ERP 실측 | 4체크 **전부 완료**된 자가실측 주문은 실측 대시보드 목록에서 **제외**되어 시공으로만 보임. 그래서 실측 화면에서는 해당 주문 행 자체가 없어 배지가 안 보이는 것이 정상. |

### 6.4 결론 및 조치

- **노출 위치:** 위 §6.1 표의 3개 화면·3개 템플릿 위치에서만 "자가실측" 배지가 노출되도록 코드가 있음(자가실측 전용 대시보드는 본 분석 반영 시 배지 추가).
- **미노출 시:** (1) 지금 보는 URL이 `/erp/measurement` 또는 `/erp/construction/dashboard` 또는 `/self_measurement_dashboard` 인지 확인, (2) 해당 행의 주문이 DB/API 기준 `is_self_measurement == True`인지, (3) ERP 시공이면 4체크 완료 여부를 확인하면 됨.

---

## 7. 클린코드 감리: 자가실측 배지·4체크 관련 (2026-03-04)

**요청:** 배지 미노출 수정 과정에서 생긴 지저분한/잘못된 코드 여부 감리. 클린코드 원칙 적용.

### 7.1 발견 사항 및 조치

| 구분 | 발견 | 판정 | 조치 |
|------|------|------|------|
| **중복 로직** | 자가실측 4체크 완료 여부(measurement_completed AND regional_sales_order_upload AND regional_blueprint_sent AND regional_order_upload)가 실측 대시보드 2곳·시공 대시보드 2곳에서 각각 동일하게 반복됨. | 🔴 DRY 위반 | `services/erp_display.py`에 `self_measurement_four_checks_done(order)` 헬퍼 추가. 실측·시공 뷰에서 해당 함수만 호출하도록 통일. |
| **일관성** | Jinja 배지 조건이 전 구간 `변수\|default(false)` 사용. API/뷰에서 dict·Order 혼용하나 접근 방식 통일됨. | 🟢 양호 | 유지. |
| **잘못된 코드** | `erp_orders_structured.py`의 `setattr(order, 'is_self_measurement', ...)` — SQLAlchemy Column에 대한 basedpyright 대응용. 런타임 동작은 정상. | 🟡 수용 가능 | 근본 해결은 모델을 `Mapped[]` 등으로 전환 시 정리. 당분간 유지. |
| **배지 마크업** | 동일 HTML이 9개 템플릿+1개 JS에 반복. 한 줄 단위라 매크로/include 도입은 선택. | 🟡 개선 여지 | 변경 없음. 스타일 통일성은 유지됨. 필요 시 추후 `{% macro self_measurement_badge() %}` 등으로 DRY화 가능. |
| **JS 시공완료** | `o.is_self_measurement` 사용. API가 키를 항상 내려주므로 undefined 시 삼항 연산자로 빈 문자열 반환되어 안전. | 🟢 양호 | 유지. |

### 7.2 수정 요약 (본 감리에서 반영)

1. **`services/erp_display.py`**
   - 추가: `self_measurement_four_checks_done(order)`  
   - 비자가실측이면 False, 자가실측이면 4개 필드 AND 결과 반환. docstring으로 용도 명시.

2. **`apps/erp_measurement_dashboard.py`**
   - `panel_orders` 루프: 4체크 인라인 블록 제거 → `if self_measurement_four_checks_done(order): continue`
   - `all_rows` → `rows` 루프: 동일하게 헬퍼만 사용하도록 변경.

3. **`apps/erp_construction_page.py`**
   - 타일 건수 루프: 4체크 인라인 블록 제거 → `if getattr(o, 'is_self_measurement', False) and not self_measurement_four_checks_done(o): continue`
   - 목록(enriched) 루프: 동일 조건으로 continue. `enriched`에 넣는 `is_self_measurement` 값은 `getattr(o, 'is_self_measurement', False)` 한 번만 사용.

### 7.3 클린코드 원칙 대비

- **DRY:** 4체크 판단은 한 곳(헬퍼)에서만 정의. ✅  
- **단일 책임:** 헬퍼는 “4체크 완료 여부”만 반환. 실측/시공의 “제외/포함” 의미는 각 뷰에서 continue 조건으로만 사용. ✅  
- **가독성:** 루프 안 조건이 한 줄로 줄어 “자가실측 4체크 완료 시 스킵”이 명확. ✅  
- **오류 가능성:** 기존과 동일 동작(비자가실측 → False, 4체크 미완료 → False). ✅  

### 7.4 감리 결론 (클린코드)

| 항목 | 판정 |
|------|------|
| 중복 제거(4체크 로직) | **조치 완료** (헬퍼 추출) |
| 잘못된 코드·버그 | **없음** (setattr는 타입 체커 대응, 동작 정상) |
| 지저분한 코드 | **정리 완료** (반복 블록 제거) |
| 일관성(배지 조건·데이터 소스) | **양호** |
