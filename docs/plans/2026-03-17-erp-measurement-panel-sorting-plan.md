# ERP Beta 매저먼트 패널 주소 정렬 및 시간 표시 플랜

## 1. 개요
현재 ERP Beta 탭의 실측 일정 패널(`erp-beta-measurement-panel`)은 단순히 클릭 시 날짜별 '이름'과 '주소'를 보여주며, 시간순으로 정렬되어 있습니다.
사용자의 요구사항에 따라 
1) 가까운 주소 끼리 정렬 (시, 군, 구 기준)
2) 이름, 주소 외에 '시간'을 명시적으로 표시하도록 수정합니다.

## 2. 문제 분석 (근본 원인 파악)
- 현재 `apps/api/erp_measurement.py`의 `/api/erp/measurement/summary` 엔드포인트에서 `cases.sort(key=lambda x: str(x.get('time') or ''))`로 시간순으로만 정렬 중입니다.
- 주소를 기준으로 가까운 곳끼리 묶기 위해 문자열 기반 정렬(시/도, 시/군/구)이 필요하지만, '경기도'와 '경기', '서울특별시'와 '서울' 등 표기법이 혼재되어 정렬이 분산될 수 있습니다.
- UI상 JS에서 시간에 대한 배지(`<span class="badge">`)가 구현되어 있으나, 백엔드에서 ERP Beta 데이터의 `structured_data` 내 실측 시간을 명시적으로 fallback으로 읽어오는 로직이 누락되었거나, 시각적으로 명확하지 않은 점이 있습니다.

## 3. 수정 설계 및 구현 계획
### 3.1. 백엔드 (`apps/api/erp_measurement.py`)
- **주소 정규화 헬퍼 함수 (`normalize_address_for_sort`) 도입**:
  - `경기도` -> `경기`, `서울특별시` -> `서울` 등 앞부분의 행정구역명을 통일하여 주소 정렬의 정확도를 높입니다.
- **ERP Beta `time` 데이터 폴백 추가**:
  - `order.structured_data['schedule']['measurement']['time']` 위치에서 직접 시간을 추출해 시간 정보를 더 확실히 내려줍니다.
- **정렬 로직 변경**:
  - 기존: `cases.sort(key=lambda x: str(x.get('time') or ''))`
  - 변경: `cases.sort(key=lambda x: (normalize_address_for_sort(x.get('address')), str(x.get('time') or '')))`
  - 주소가 우선 정렬되고, 주소가 같거나 비슷한 곳 내에서 시간이 정렬되도록 합니다.

### 3.2. 프론트엔드 (`templates/partials/erp_beta_js.html`)
- **시간 표시 강화**:
  - 시간이 있을 경우 눈에 띄게 `[오전] 홍길동`, `[14:30] 고유경` 형태로 시간 배지를 명시적으로 배치합니다. 시간 정보가 없으면 `[시간미정]` 배지를 표시하여 정보 누락을 방지합니다.

## 4. 검증 계획 (GDM)
1. 백엔드 API `/api/erp/measurement/summary`를 호출하여 날짜별 데이터가 주소(시/도 단위) 기준으로 잘 그룹화 되어 있는지 확인합니다.
2. 프론트엔드 UI상에서 날짜를 클릭했을 때 리스트업 되는 데이터에 시간 배지와 주소가 정상적으로 출력되는지 확인합니다.
3. 코드 변경 사항이 `grand-develop-master.md` 원칙(단순화 우선, 증상 우회 금지)을 준수하는지 점검합니다.
