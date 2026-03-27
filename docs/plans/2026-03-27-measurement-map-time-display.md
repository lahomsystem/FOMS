# 실측 대시보드 지도 주문 건 정보 '실측 시간' 표시 구현 계획서

## 1. 개요
사용자 요청에 따라 실측 대시보드의 지도 뷰(Map View) 좌측 사이드바에 표시되는 주문 건 목록(카드)에 '실측 시간' 정보를 추가로 노출합니다.

## 2. 작업 대상 파일 및 변경 사항

### 2.1. `services/map_snapshot.py`
- **대상 함수**: `_extract_order_display_fields(order)`
- **변경 내용**:
  - `measurement_time = order.measurement_time` 변수 추출 추가
  - `order.is_erp_beta`이고 `order.structured_data`가 있는 경우, `sd.get('schedule', {}).get('measurement', {}).get('time')` 값을 확인하여 존재할 경우 `measurement_time`을 덮어씀.
  - 반환 딕셔너리에 `'measurement_time': measurement_time` 추가.
- **대상 함수**: `build_measurement_snapshot(orders, manager_filter=None)`
  - **변경 내용**: `orders_list`에 딕셔너리를 추가할 때 `'measurement_time': ctx.get('measurement_time')` 항목 추가.

### 2.2. `apps/api/erp_map.py`
- **대상 함수**: `_extract_map_order_display(order)`
- **변경 내용**:
  - `measurement_time = order.measurement_time` 변수 추출 추가
  - `order.is_erp_beta`이고 `order.structured_data`가 있는 경우 `sd.get('schedule', {}).get('measurement', {}).get('time')` 값을 확인하여 존재할 경우 `measurement_time`을 덮어씀.
  - 반환 딕셔너리에 `'measurement_time': measurement_time` 추가.
- **대상 함수**: `_build_map_payload(orders, ...)`
  - **변경 내용**: `orders_list`에 딕셔너리를 추가할 때 `'measurement_time': display.get('measurement_time')` 항목 추가.

### 2.3. `templates/map_view.html`
- **대상 함수**: `updateOrderList(orders)`
- **변경 내용**:
  - 사이드바 주문 카드 HTML 생성 로직(`html += `) 내에 고객, 연락처, 주소, 제품 정보가 표시되는 `.order-info` 영역 수정.
  - 기존 연락처(`phone`) 행 아래 또는 제품(`product`) 행 근처에 '실측 시간'을 표시하는 행 추가. (예: `<div class="order-info-row"><span class="order-info-label">실측 시간:</span><span class="order-info-value">${escapeHtml(order.measurement_time || '-')}</span></div>`)

## 3. 검증 계획 (1:1 코드 비교)
- API 변경으로 인해 `/api/map_data` 및 `/api/generate_map` 응답의 `orders` 배열 내에 `measurement_time`이 정상적으로 포함되어 내려오는지 확인.
- 클라이언트 단(`updateOrderList`)에서 `order.measurement_time`을 읽어 사이드바 UI에 에러 없이 렌더링되는지 확인.
- 레거시 데이터(DB의 `measurement_time` 컬럼)와 ERP Beta 데이터(`structured_data`의 `schedule.measurement.time`) 모두 적절하게 파싱되는지 확인.
