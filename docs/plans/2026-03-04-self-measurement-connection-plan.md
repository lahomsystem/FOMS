# 자가실측 대시보드 연결 계획서

이 계획서는 "긴급" 체크박스 옆에 "자가실측" 체크박스를 신설하여 처리 시스템을 통합하고, 자가실측 대시보드 진행 관리에 맞춰 ERP 시공 대시보드로 자동 연계되는 로직을 설계합니다. **GDM 원칙(구조적 의심, 오컴의 면도날)**에 입각하여 최소한의 코드로 구현합니다.

## 1. 개요 및 요구사항
1. **UI 개선:** ERP Beta 패널(`erp_beta_tab.html`) "긴급" 체크박스 근처에 "자가실측" 체크박스 편입.
2. **라우팅(Route) 필터링 및 Workflow 인계:** 
   - 자가실측 주문은 **최초 ERP 실측 대시보드**에 정상적으로 표시됨 (자가실측 대시보드와 동시 표시).
   - 단, 자가실측 대시보드의 **4개 필수 체크리스트**(0. 실측완료, 1. 영업발주 업로드, 2. 도면 발송, 3. 발주 업로드)가 "모두" 체크완료 상태가 되기 전까지는 ERP 시공 대시보드 진입이 차단됨.
   - 4개 체크가 **모두 완료**되면 **ERP 실측 대시보드에서 제거**되고, **ERP 시공 대시보드**로 이동(편입)하여 이후 ERP 프로세스를 동일하게 진행함.
   - **Rollback (역방향 이동):** 체크박스를 해제하여 하나라도 체크가 풀릴 경우, 시공 대시보드에서 즉시 사라지고 다시 실측 대시보드로 돌아오게(복구 시킴) 만들어야 함.
   - **배지 표기 (UI 반영)**: ERP 파이프라인(실측 및 시공 대시보드 모두) 리스트에 노출되는 기간 동안 직관적인 **`자가실측`** 배지(Badge)를 추가하여 쉽게 식별할 수 있도록 함.

## 2. 세부 구현 계획

### 2.1 프론트엔드 (UI & JS 연동)
**대상:** `templates/partials/erp_beta_tab.html`, `templates/partials/erp_beta_js.html`
- **UI:** 긴급 체크박스와 동일한 `div.form-check` 구조로 `erp-self-measurement` ID를 가진 인풋 생성.
- **JS 로직:**
  - 저장 시 `buildPayload`: `is_self_measurement: document.getElementById('erp-self-measurement').checked` 송신.
  - 데이터 로딩 시 `fillBetaForm`: `GET`해온 데이터에 맞춰 체크박스 상태 렌더(`sd.is_self_measurement` 보강 활용).

### 2.2 백엔드 (API & DB 저장)
**대상:** `apps/api/erp_orders_structured.py`
- `GET /api/orders/<id>/structured` 의 응답 페이로드에 `is_self_measurement: order.is_self_measurement` 추가 (UI 렌더링 지원).
- `PUT /api/orders/<id>/structured` 에 수신 데이터 저장 로직 추가:
  ```python
  is_self_measurement = payload.get('is_self_measurement')
  if is_self_measurement is not None:
      order.is_self_measurement = bool(is_self_measurement)
  ```
- **JS 주의:** `is_self_measurement`는 `erpCollectStructured()` 내부가 아닌, `erpSaveStructured()`의 `JSON.stringify({...})` 블록 최상위에 추가해야 백엔드 `payload.get()`으로 정확히 추출됨.

### 2.3 디스플레이 조건부 노출 (ERP 실측 대시보드)
**대상:** `apps/erp_measurement_dashboard.py`
- 영구 배제 기능을 없애고, 자가실측 4개 옵션이 **전부 체크완료 되었을 때만** 실측 대시보드 리스트에서 가리도록 로직 구성.
- `all_rows`를 가공하여 표시할 `rows`를 필터링하는 파이썬 로직 내부에 조건을 추가합니다:
  ```python
  # 실측 대시보드 렌더링 필터 최하단 추가
  is_self = getattr(order, 'is_self_measurement', False)
  if is_self:
      all_done = (order.measurement_completed and 
                  order.regional_sales_order_upload and 
                  order.regional_blueprint_sent and 
                  order.regional_order_upload)
      if all_done:
          continue # 4개 요건 모두 만족 시 실측 대시보드에서 표시 제외 (시공 대시보드로 이관)
  ```
- **패널 카운트 동기화:** `panel_orders` 루프(날짜 패널 건수 집계, L207~218)에도 동일 Gating 조건을 적용하여 **날짜 패널 카운트**와 **목록 구성**의 일관성을 보장한다. (패널에만 카운트가 남고 리스트에 없는 불일치 방지)

### 2.4 디스플레이 연계 (ERP 시공 대시보드 Gating)
**대상:** `apps/erp_construction_page.py`
- `_display_stage_for_order` 추출 직후 및 `orders` 순회 로직(`enriched` 리스트 구성) 에 Python 계층 필터 추가.
- 자가실측 주문(`is_self_measurement == True`)의 경우, 아직 자가실측 4단계 프로세스가 덜 끝났다면 목록(`enriched`)과 카운트(`step_stats`)에서 모두 제외(continue) 처리.
  ```python
  # 1) 타일 건수 순회 및 2) 목록 순회 루프 내부
  is_self = getattr(o, 'is_self_measurement', False)
  if is_self:
      # 자가실측 대시보드의 필수 4대 체크리스트
      all_done = (o.measurement_completed and 
                  o.regional_sales_order_upload and 
                  o.regional_blueprint_sent and 
                  o.regional_order_upload)
      if not all_done:
          continue # 시공 대시보드에 아직 노출 안 함
  ```
  따라서 4개 체크가 끝나는 **즉시** 시공(출고) 대시보드의 "시공대기" 혹은 해당하는 상태로 노출됨.

### 2.5 자가실측 배지 UI 표기 (ERP 실측 / 시공 대시보드 공통)
**대상:** `templates/erp_measurement_dashboard.html`, `templates/erp_construction_dashboard.html`
- 실측 및 시공 대시보드 파이프라인으로 노출되는 자가실측 주문 건의 경우, 카드 및 리스트 UI 내 **고객명 또는 상태 표기 옆**에 직관적인 뱃지 추가:
  ```html
  {% if order.is_self_measurement %}
      <span class="badge bg-info text-white"><i class="fas fa-ruler-combined"></i> 자가실측</span>
  {% endif %}
  ```
- **데이터 흐름:** `apps/erp_construction_page.py`의 `enriched` 딕셔너리에 `is_self_measurement`를 포함하여 UI로 넘김.

## 3. GDM 원칙 적용 평가
- **구조적 의심 (Structural Doubt):** "자가실측 상태로 변경하면 어떻게 되나?"라는 우회로 대신 "자가실측 플래그가 참이면 어떤 대시보드에서 보일지(What to show)"를 데이터 통과 조건 즉 **Gating Filter** 방식의 선명한 로직으로 설계했습니다.
- **오컴의 면도날 (Occam's Razor):** 주문 Workflow 이벤트를 새로 추가하거나 상태전이에 따른 신규 Status 맵핑 없이, 4개의 체크박스 `True/False` 의 AND 연산 하나로 "시공 진입 가능" 여부를 판독해 내는 코드 5줄로 해결합니다.
