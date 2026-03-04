# 실측일·시공일 다중 날짜 지정(Multiple Dates) 지원 구현 계획서

## 1. 개요
현재 `<input type="date">` 한계로 인해 실측일과 시공일을 단일 날짜로만 저장 및 표시하고 있습니다.
현장 상황에 따라 여러 날에 걸쳐 실측이나 시공이 진행되는 경우(예: 3월 13일, 14일, 15일), 이를 동시 지정하고 대시보드에 선택된 모든 일정에 **각각** 표시되도록 시스템을 개선합니다.

이 계획서는 **오컴의 면도날(Occam's Razor)** 원칙에 따라 DB 스키마(Table) 변경을 최소화하고, 기존의 `VARCHAR(String)` 컬럼에 쉼표(`,`) 형식으로 값을 저장하면서 조회(Filter) 및 화면(UI) 종속성을 해결하는 가장 가벼운 방식으로 설계되었습니다.

### 핵심 요구사항
> **실측일이 3월 13,14,15일 → 실측 대시보드 3월 13일, 14일, 15일에 각각 집계(+1)**
> **시공일이 3월 13,14,15일 → 출고/시공 대시보드 3월 13일, 14일, 15일에 각각 집계(+1)**
> **주문 건 내 세부 품목(Item)별로도 개별 실측일, 시공일을 지정할 수 있어야 함**

---

## 2. DB 컬럼 매핑 (정확한 대응표)

| 용도 | DB 컬럼 (Order) | ERP Beta (structured_data) | 비고 |
|---|---|---|---|
| **실측일** | `measurement_date` (String) | `schedule.measurement.date` | 다중 날짜 대상 |
| **시공일** | `scheduled_date` (String) | `schedule.construction.date` | 다중 날짜 대상 |
| 설치완료일 | `completion_date` (String) | - | 변경 없음 (별개 필드) |

> **주의:** `completion_date`는 "설치완료일"이며, "시공일"이 아닙니다. 시공일은 `scheduled_date` 및 `structured_data.schedule.construction.date`에 매핑됩니다.

---

## 3. 작업 상세 내용

### 3.1. 프론트엔드 UI 변경 (Flatpickr 도입)
**대상 파일:**
- `templates/layout.html` (CDN 추가)
- `templates/partials/erp_beta_tab.html` (input 타입 변경, 달력 아이콘)
- `templates/partials/erp_beta_js.html` (초기화 및 날짜 변환 함수)

**작업 내용:**
1. **Flatpickr 라이브러리 추가:**
   - `layout.html`의 `<head>`에 Flatpickr CSS, `</body>` 앞에 JS 및 한국어 locale CDN을 추가합니다.
2. **입력 요소 타입 변경 및 달력 선택 보장:**
   - 기존 실측일(`<input id="erp-measurement-date">`)과 시공일(`<input id="erp-construction-date">`)을 **달력으로 선택 가능**하도록 `type="text"` + Flatpickr 적용.
   - **클릭 시 달력 팝업**이 열리며, 단일(1day) 또는 다중(multiple) 날짜 선택 가능. 필요 시 입력 옆 **달력 아이콘** 버튼으로도 열기.
   - `placeholder="여러 날짜 선택 가능 (예: 2026-03-13, 2026-03-14)"`, `autocomplete="off"` 부여.
3. **Flatpickr 인스턴스 초기화 (`erp_beta_js.html`):**
   - 통합 실측일/시공일 input에 `flatpickr(elem, { mode: "multiple", dateFormat: "Y-m-d", locale: "ko", allowInput: true })` 적용.
   - **초기화 시점:** ERP Beta 탭 `shown.bs.tab` 시 뿐 아니라 **DOMContentLoaded** 시에도 한 번 호출하여, 탭 전환 전에도 달력이 준비되도록 함.
   - 항목(row)별 실측일/시공일: `data-erp="measurement_date"`, `data-erp="construction_date"` input + `erpInitFlatpickrForItemRow(row)`로 동적 row에도 달력 적용.
4. **`formatDateToKorean()` 함수 수정:**
   - CSV를 `.split(',')` 후 각 날짜 개별 변환해 다시 합치는 로직으로 수정.

### 3.2. 백엔드 데이터 저장 로직 수정
**대상 파일:**
- `apps/api/orders.py` (ERP 주문 저장 API)
- `apps/order_edit.py` (레거시 폼 저장 — L175: `scheduled_date`, L171: `measurement_date`)
- `apps/order_pages.py` (레거시 폼)

**작업 내용:**
1. **구조적 저장 보장:**
   - CSV 문자열 `"YYYY-MM-DD, YYYY-MM-DD"`가 그대로 저장되도록 허용.
   - **실측일**: `Order.measurement_date` (전체/대표) + `structured_data.schedule.measurement.date`
   - **시공일**: `Order.scheduled_date` (전체/대표) + `structured_data.schedule.construction.date`
2. **항목(Item)별 개별 날짜 저장:**
   - `structured_data.items[i].measurement_date` 및 `structured_data.items[i].construction_date` 필드를 추가 수집하여 JSON에 저장합니다.
   - 대표 날짜(Order 필드)는 기존대로 활용하되, 개별 항목 날짜가 존재하면 UI 조회 시 해당 날짜를 우선 표시할 수 있도록 기반 데이터 구조를 마련합니다.

### 3.3. 실측 대시보드 집계 수정 (핵심)
**대상 파일:**
- `apps/erp_measurement_dashboard.py`

**핵심 목표:** 
1. 전체 실측일이 여러 날짜면 각 날짜 패널에 **각각 +1**
2. **세부 품목(Item)에 지정된 개별 실측일**도 모두 추출하여 해당 날짜 패널에 **각각 +1** (단, 같은 주문에 속한 동일 날짜는 한 번만 카운트)

**수정 포인트:**

#### 3.3.1. 모든 날짜 추출 헬퍼 함수 활용 (공통)
```python
def extract_all_measurement_dates(order):
    dates = set()
    # 1. 대표/전체 날짜 파싱
    if order.measurement_date:
        for d in str(order.measurement_date).split(','):
            if d.strip(): dates.add(d.strip())
    # 2. 항목(Item)별 날짜 파싱
    if getattr(order, 'is_erp_beta', False) and getattr(order, 'structured_data', None):
        items = order.structured_data.get('items') or []
        for it in items:
            date_val = it.get('measurement_date')
            if date_val:
                for d in str(date_val).split(','):
                    if d.strip(): dates.add(d.strip())
    return dates
```

#### 3.3.2. 패널 집계 (L169~188) — `measurement_counts` 딕셔너리
```python
# [수정 전] 단일 날짜만 집계
# date_value = str(erp_measurement_date)

# [수정 후] 모든 대표+항목 날짜 파싱 → 각 날짜별로 각각 +1
all_dates = extract_all_measurement_dates(order)
for date_value in all_dates:
    try:
        d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
    except Exception:
        continue
    if d < range_start or d > range_end:
        continue
    key = d.strftime('%Y-%m-%d')
    measurement_counts[key] = measurement_counts.get(key, 0) + 1
```

#### 3.3.3. 목록 필터 (L206~223) — `should_include` 로직
```python
# [수정 전] 단일 비교
# if erp_measurement_date and str(erp_measurement_date) == selected_date:

# [수정 후] 대표 날짜 또는 개별 품목 날짜 중 하나라도 일치하면 포함
all_dates = extract_all_measurement_dates(order)
if selected_date in all_dates:
    should_include = True
```

#### 3.3.4. DB 쿼리 필터 (L121) — JSON 컬럼 검사 포함
```python
# [수정 전] Order.measurement_date == selected_date

# [수정 후] ILIKE로 CSV 파싱 + JSONB 내부 개별 item 날짜 검사
Order.measurement_date.ilike(f"%{selected_date}%") | 
cast(Order.structured_data, String).ilike(f'%"measurement_date"%{selected_date}%')
```

#### 3.3.5. strptime 파손 방지 (L182)
```python
# [수정 전] CSV에서 ValueError 발생
d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()

# [수정 후] split 후 각각 처리 (3.3.1의 수정에 포함)
```

### 3.4. 출고/시공 대시보드 집계 수정 (핵심)
**대상 파일:**
- `apps/erp_shipment_page.py` (출고 대시보드 - 핵심 집계 로직)
- `apps/erp_construction_page.py` (시공 대시보드 - 단순 목록 표시)

**핵심 목표:** 시공일이 `"2026-03-13, 2026-03-14, 2026-03-15"`인 주문 → 출고 대시보드 3월 13일, 14일, 15일에 **각각 집계**

**수정 포인트 (`erp_shipment_page.py`):**
1. **모든 날짜 추출 헬퍼 함수 추가:**
```python
def extract_all_construction_dates(order):
    dates = set()
    base_date = _get_order_construction_date(order) # 기존 대표 로직
    if base_date:
        for d in str(base_date).split(','):
            if d.strip(): dates.add(d.strip())
            
    if getattr(order, 'is_erp_beta', False) and getattr(order, 'structured_data', None):
        items = order.structured_data.get('items') or []
        for it in items:
            date_val = it.get('construction_date')
            if date_val:
                for d in str(date_val).split(','):
                    if d.strip(): dates.add(d.strip())
    return dates
```

2. **패널 집계 (L164~178):**
   - 위 함수를 통해 반환된 날짜 집합(`all_dates`)을 반복 순회하며 `construction_counts`와 캘린더 자원(인부 등)에 각각 매핑 및 집계(+1)합니다.
3. **목록 필터 (L266~312):**
   - `selected_date in extract_all_construction_dates(order)` 조건을 적용하여, 대표 시공일이든 개별 항목에 지정된 시공일이든 상관없이 해당 날짜 패널을 누를 때마다 일관되게 하단 목록(`rows`)에 포함되도록 수정합니다.

**수정 포인트 (`erp_construction_page.py`):**
- 리스트 형태로만 제공되므로 DB 쿼리 수정은 필요 없으며, 프론트엔드에서 날짜를 Badge로 나누어 표시합니다.



### 3.5. 캘린더 출력 로직 수정
**대상 파일:**
- `apps/api/orders.py` (FullCalendar 연동 API)

**수정 포인트:**
1. **`_get_order_schedule_date()` 헬퍼 (L26~53):**
   - CSV 반환 시, 호출자가 split하여 각 날짜별 이벤트를 생성할 수 있도록 그대로 반환 유지.
2. **FullCalendar 이벤트 생성 (L334~):**
   - `measurement_date`나 `scheduled_date` 문자열에 쉼표가 있을 경우, 각 날짜에 대해 **별도의 이벤트 객체를 생성**하여 `events` 리스트에 추가.
   - 예: 시공일 `"3-13, 3-14, 3-15"` → 3개의 FullCalendar 이벤트 생성 → 달력에 3일 모두 막대 표시.

### 3.6. 레거시 대시보드 필수 수정
**대상 파일:**
- `apps/dashboards.py` (수도권 대시보드)

**수정 포인트 (4곳: measurement_date 3곳 + scheduled_date 1곳):**
```python
# [수정 전] func.date()는 CSV에서 SQL 에러 발생!
func.date(Order.measurement_date) == date.today()       # L144
func.date(Order.measurement_date) < date.today()        # L151
func.date(Order.measurement_date) > date.today()        # L160
func.date(Order.scheduled_date) < date.today()          # L172

# [수정 후] ILIKE 또는 Python 레벨 필터로 변경
Order.measurement_date.ilike(f"%{today_str}%")
```
또는 DB에서 전체 로드 후 Python에서 `split(',')`으로 필터링하는 방식으로 대체.

### 3.7. 목록 표시 UI 개선
**대상 파일:**
- `templates/erp_measurement_dashboard.html`
- `templates/erp_construction_dashboard.html`

**작업 내용:**
- 날짜 표시부에 CSV가 그대로 노출되면 길어지므로, 각 날짜를 Badge나 줄바꿈으로 개별 표시하여 다중 일정임을 인지시킵니다.
- 예: `3/13` `3/14` `3/15` (각각 Badge)

---

## 4. 달력 선택 및 대시보드 표시 로직 (Use Cases)

- **1.** 기존 실측일·시공일 input은 **달력(Flatpickr)으로 선택** 가능해야 하며, 클릭 시 달력 팝업이 열려 단일/다중 날짜 선택이 가능하다.
- **2.** 기존 실측일(1day) + 기존 시공일(1day) 선택 시 → **기존대로** 실측 대시보드 해당 날, 시공 대시보드 해당 날에만 표기.
- **2.1** 실측일(1day) + 주문 건 각각 시공일(multiple) → 실측 대시보드: 지정일만 / 시공 대시보드: 각 선택 시공일마다 표시.
- **2.2** 실측일(multiple) + 주문 건 각각 시공일(multiple) → 실측 대시보드: 각 실측일마다 / 시공 대시보드: 각 시공일마다 표시.
- **2.3** 주문 건 각각 실측일(multiple) + 주문 건 각각 시공일(multiple) → 실측 대시보드: 각 선택 실측일마다 / 시공 대시보드: 각 선택 시공일마다 표시.

아래에서 상세 조건·결과를 정의합니다.

### 4.1. 구분 및 저장 방식
- 입력 시 Flatpickr를 통해 쉼표 처리된 문자열 `"YYYY-MM-DD, YYYY-MM-DD"` 전달
- 서버는 이 문자열을 DB에 그대로 저장하되, 추출 헬퍼 함수에서 `.split(',')`으로 나누어 논리적인 날짜 배열로 처리합니다.
  - **기존(1day) 기준:** 파싱 후 배열 길이(`length`) === 1
  - **선택(multiple days) 기준:** 파싱 후 배열 길이(`length`) > 1

### 4.2. 대시보드 렌더링 기본 원칙
- **실측 대시보드**: 
  `for each 날짜 in 달력 패널`:
    `for each 주문 in 모든_주문`:
      `if 주문의 쪼개진 measurement_dates 배열에 현재_날짜가 포함되면` → 해당 날짜 목록에 주문 표시
- **시공 대시보드**: 
  `for each 날짜 in 달력 패널`:
    `for each 주문 in 모든_주문`:
      `if 주문의 쪼개진 construction_dates 배열에 현재_날짜가 포함되면` → 해당 날짜 목록에 주문 표시

### 4.3. 상세 경우의 수 (Cases)

- **실측** → 실측 대시보드에 표시. **시공** → 출고·시공 대시보드에 표시.

#### Case 2: 기존 실측일 (1day) + 기존 시공일 (1day)
- **조건**: 대표 실측일 1개만 선택, 대표 시공일 1개만 선택 (기존과 동일).
- **결과**: 실측 대시보드 해당 1일만 표기, 시공 대시보드 해당 1일만 표기.

#### Case 2.1: 기존 실측일 (1day) + 주문 건 각각 선택 시공일 (multiple days)
- **조건**: 대표 실측일 1개, 대표 또는 항목별 시공일 여러 개.
- **결과**:
  - 실측 대시보드: 지정된 1개 실측일에만 주문 표시.
  - 시공 대시보드: **선택된 각 시공일마다** 해당 날짜에 주문 표시.
- **예시**: 실측 3/13, 시공 3/20·21·22 → 시공 대시보드 3/20, 3/21, 3/22 패널 모두에 해당 주문 출현.

#### Case 2.2: 기존 실측일 (multiple days) + 주문 건 각각 선택 시공일 (multiple days)
- **조건**: 대표 실측일 여러 개, 대표 또는 항목별 시공일 여러 개.
- **결과**:
  - 실측 대시보드: **선택된 각 실측일마다** 해당 날짜에 주문 표시.
  - 시공 대시보드: **선택된 각 시공일마다** 해당 날짜에 주문 표시.

#### Case 2.3: 주문 건 각각 선택 실측일 (multiple) + 주문 건 각각 선택 시공일 (multiple)
- **조건**: 항목(Item)별로만 실측일·시공일을 여러 개씩 지정(대표 비어 있어도 됨).
- **결과**:
  - 실측 대시보드: **각 항목에서 추출한 각 실측일마다** 해당 날짜에 주문 표시.
  - 시공 대시보드: **각 항목에서 추출한 각 시공일마다** 해당 날짜에 주문 표시.
- **구현**: `extract_all_measurement_dates` / `extract_all_construction_dates`가 이미 `structured_data.items[].measurement_date`, `construction_date`를 합치므로 별도 분기 없이 동일 로직으로 처리됨.

### 4.4. 구현 체크리스트 요약
- **HTML/UI**: 
  - [x] 실측/시공일 `<input>`을 달력 컴포넌트로 변경
  - [x] 다중 선택 기능 완비 (여러 날짜 선택 가능)
  - [x] UI 텍스트필드에 쉼표 구분 표시 및 Placeholder 추가
- **데이터 처리**: 
  - [x] 문자열로 들어온 날짜를 서버에서 배열 개념으로 변환해 길이(기존/선택) 구분
- **대시보드 렌더링**: 
  - [x] 실측 대시보드 특정 날짜 패널 클릭 시 배열 포함 여부로 해당 주문 노출
  - [x] 시공 대시보드 특정 날짜 패널 클릭 시 배열 포함 여부로 해당 주문 노출 
  - [x] (결과) 같은 주문이 Case 2.1 ~ 2.3 조건에 따라 지정된 여러 날짜에 중복 분산 렌더링됨

---

## 5. 수정 대상 파일 완전 목록

| # | 파일 | 수정 내용 | 필수 여부 |
|---|---|---|---|
| 1 | `templates/layout.html` | Flatpickr CDN 추가 | 필수 |
| 2 | `templates/partials/erp_beta_tab.html` | input type 변경, placeholder 부여 | 필수 |
| 3 | `templates/partials/erp_beta_js.html` | Flatpickr 초기화 + formatDateToKorean 수정 | 필수 |
| 4 | `apps/order_edit.py` | CSV 저장 허용 확인 | 필수 |
| 5 | `apps/order_pages.py` | CSV 저장 허용 확인 | 필수 |
| 6 | `apps/erp_measurement_dashboard.py` | **(실측) 패널 집계 + 목록 필터 + 쿼리 수정** | 필수 |
| 7 | `apps/erp_shipment_page.py` | **(출고) 패널 집계 + 목록 필터 + 쿼리 수정** | 필수 |
| 7-1 | `apps/erp_construction_page.py` | 시공일 CSV 표시 대응 | 필수 |
| 8 | `apps/api/orders.py` | FullCalendar 다중 이벤트 생성 | 필수 |
| 9 | `apps/dashboards.py` | func.date() 4곳 수정 (measurement_date 3곳, scheduled_date 1곳) | 필수 |
| 10 | `templates/erp_measurement_dashboard.html` | 날짜 Badge 표시 | 권장 |
| 11 | `templates/erp_shipment_dashboard.html` | 날짜 Badge 표시 | 권장 |
| 12 | `templates/erp_construction_dashboard.html` | 날짜 Badge 표시 | 권장 |
| 13 | `apps/api/erp_map.py` | 날짜 필터 CSV/항목 대응 (L99, L101, L130~136, L266~268, L300~306 등) | 필수 |
| 14 | `apps/api/erp_measurement.py` | 날짜 조건 CSV/항목 대응 (L115, L128~133) | 필수 |

---

## 6. GDM 더블체크 보완 사항 (반드시 반영)

- **실측 대시보드 구간(use_range):** L96~98의 `Order.measurement_date >= date_from` 등은 CSV 시 부적절. 넓게 조회 후 Python에서 `extract_all_measurement_dates`로 구간 포함 여부 판단.
- **출고 대시보드 구간(use_range):** L260~265의 `date_from <= date_value <= date_to`는 CSV 시 오동작. `extract_all_construction_dates(order)`로 바꾸고, 구간 안에 하나라도 있으면 rows에 포함.
- **FullCalendar API (`apps/api/orders.py`):** L313~317의 `Order.measurement_date.between(...)`는 CSV 시 부적절. 쿼리는 완화하고, 이벤트 생성 루프에서 measurement_date/scheduled_date를 `split(',')` 후 날짜별로 이벤트 추가.
- **CSV 형식:** 저장·파싱 시 `split(',')` 후 각 토큰 `strip()`으로 통일.

---

## 7. 원칙 및 모범 사례 준수 사항
1. **단순화 우선 (Simplification First):**
   - N:M 조인 테이블이나 PostgreSQL Array 사용 없이, `String` 컬럼에 CSV 형태로 저장하고 `ILIKE`, Python `split(',')`으로 해결하여 회귀 결함을 차단합니다.
2. **구조적 의심 및 검증:**
   - 캘린더에서 1주문 = 1이벤트라는 패러다임을 깨고, API 레벨에서 1:N 이벤트를 전개(Unnesting)하여 FullCalendar UI에 맞춰 변환합니다.
3. **적용 범위 격리 (Occam's Razor):**
   - Flatpickr 로딩 실패 시에도, `type="text"`에 직접 `YYYY-MM-DD, YYYY-MM-DD`를 입력할 수 있어 우아한 기능 저하(Graceful Degradation)를 보장합니다.
