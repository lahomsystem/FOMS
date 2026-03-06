# 🛠️ GDM 개발 계획서: ERP Beta '실측일/시공일 UI 재배치' 및 '실측 일정 미러링 패널 구성'

> **2차 더블체크 완료** (2026-03-05 23:31 KST)
> 사용자의 구체적인 목표("ERP 주문 입력 시 실측 일정을 확인해서 바로 접수할 수 있게")를 위해 ERP Beta UI/UX를 개선하는 정밀 계획서입니다.
> **보완 이력:** 60일→14일 범위 확정, 필터링 로직 명시, 30초 자동 갱신 추가, API 배치 파일 확정, Flatpickr 연동 디테일 추가, **RCA 반영: mine/q 파라미터 대시보드 동기화 요구사항 추가** (ERP Beta 패널과 실측 대시보드 건수 일치 필수).

---

## 1. 개요 및 기획 의도
- **목표:** ERP Beta 입력 폼(`edit_order.html` 안의 `erp_beta_tab.html`) 화면에서 사용자가 다른 대시보드로 이동하지 않고도 **"진행 중인 실측 일정 현황"**을 즉시 확인하면서 실측일과 시공일을 편리하게 지정할 수 있도록 UI를 혁신합니다.
- **핵심 요구사항:**
  1. 기존 넓게 차지하던 `실측일`, `시공일` 입력 필드의 가로폭을 절반으로 줄여 콤팩트하게 배치.
  2. 현재 실측 대시보드 좌측에 있는 **"날짜별 실측 일정 (14일 기준)"** 패널을 ERP Beta 화면 왼쪽에 미러링(복제)하여 일정을 보며 날짜를 고를 수 있도록 배치. (**30초 주기 자동 갱신**으로 거의 실시간 동기화)

---

## 2. GDM 코드베이스 분석 (Current Architecture & Constraints)

### 2-1. 기존 UI 레이아웃 (`erp_beta_tab.html`)
현재 날짜 입력 부분은 `row g-2` 그리드 하위에서 아래와 같이 배치되어 있습니다:
- `<div class="col-md-6">` : 실측일 (`#erp-measurement-date`)
- `<div class="col-md-6">` : 실측시간 (`#erp-measurement-time`)
- `<div class="col-12">` : 실측 특이사항 (Collapse 확장 시 노출됨)
- `<div class="col-md-6">` : 시공일 (`#erp-construction-date`)

**변경 후 순서 (사용자 요구):**
- ① 실측일 → ② 실측 특이사항 → ③ 실측시간 → ④ 시공일

**문제점:** 실측일과 시공일이 각각 다른 블록으로 흩어져 있고 한 줄이나 반 줄을 너무 차지하고 있어, 좌측에 패널을 띄울 공간 효율성이 떨어집니다.

### 2-2. 미러링할 실측 일정 컴포넌트 (`erp_measurement_dashboard.html`)
- 실측 대시보드는 백엔드 라우트(`apps/erp_measurement_dashboard.py`)에서 `measurement_panel_dates` 데이터를 렌더링 서버사이드로 주입합니다.
- 하지만 `erp_beta_tab.html`은 `edit_order.html`이나 모달, 주문 추가 페이지(`add_order.html`) 등 여러 곳에서 동적으로 호출되므로 **서버사이드(`Jinja2`) 렌더링에만 의존할 수 없습니다.**
- **따라서(GDM Actionable Insight):**
  AJAX(Fetch)를 통해 백엔드에서 14일치 날짜별 실측 건수를 JSON으로 받아와 클라이언트(JS)에서 동적으로 `measurement-panel-list` UI를 그려내는(Hydration) **"비동기 미러링 패널"** 방식을 사용해야 합니다.

---

## 3. 핵심 조치 계획 (Implementation Plan)

### Phase 1: 백엔드 API 신설 (비동기 날짜별 실측 건수 제공)
1. **API 신설:** `GET /api/erp/measurement/summary` → **파일: `apps/api/erp_measurement.py`** (기존 실측 API Blueprint에 추가)
   - 역할: 오늘부터 향후 **14일**치 날짜 리스트와, 각 날짜별 "실측 주문 개수", "주말/휴일 여부"를 계산해 JSON 배열로 반환.
   - 로직: 기존 `erp_measurement_dashboard.py`의 `measurement_counts` 계산 로직(`extract_all_measurement_dates` 활용)을 그대로 함수화하여 재사용.
   - **⚠️ 필수 필터링 (대시보드와 건수 일치를 위해 반드시 적용):**
     - `self_measurement_four_checks_done(order)` → 자가실측 4체크 완료 건 **제외** (시공 이관 완료)
     - `Order.is_regional != True` → 지방실측 **제외** (진짜 실측 필요 건만 집계)
     - `~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])` → 자가실측 상태 **제외** (단, `is_self_measurement == True`인 건은 포함)
     - 위 조건은 `erp_measurement_dashboard.py:95-103` + `188-190`과 동일해야 함.
   - **⚠️ 대시보드 동기화 파라미터 (건수 일치를 위해 필수):**
     - **`mine`**: `request.args.get('mine') == '1'` 이고 `current_user` 존재 시, `panel_orders`에 `is_order_mine_for_user(o, current_user)` 필터 적용 (L169–173 동일). 기본값/미전달 시 전체 건수.
     - **`q` (검색)**: `search_q = (request.args.get('q') or request.args.get('manager') or '').strip()` → `_erp_order_search_filter(base_query, search_q)` 적용 (L86, L93 동일). `base_query`에 검색 필터를 먼저 적용한 후 위 필터 및 `panel_orders` 계산.
   
```json
// API 응답 예시
{
  "success": true,
  "panel_dates": [
    {
      "date": "2026-03-05", "day_label": "목", "count": 21,
      "is_weekend": false, "is_holiday": false, "is_today": true
    },
    ...
  ]
}
```

### Phase 2: ERP Beta 폼 Layout 재구조화 (HTML/CSS)
**파일:** `templates/partials/erp_beta_tab.html`

1. 날짜 입력 영역 상위 구조를 **2단 레이아웃**으로 변경합니다.
   - **왼쪽 (`col-md-4`):** 실측 일정 미러링 패널
   - **오른쪽 (`col-md-8`):** 기존 제품 입력 폼 및 날짜 배치 영역
   
2. **우측 폼 필드 순서 재배치 (실측일 → 실측 특이사항 → 실측시간 → 시공일):**
   ```html
   <div class="row g-2">
       <div class="col-md-6">
           <label class="form-label mb-1">실측일</label>
           <!-- Flatpickr 달력 input -->
       </div>
       <div class="col-12">
           <!-- 실측 특이사항 (Collapse) -->
       </div>
       <div class="col-md-6">
           <label class="form-label mb-1">실측시간</label>
           <!-- select + input -->
       </div>
       <div class="col-md-6">
           <label class="form-label mb-1">시공일</label>
           <!-- Flatpickr 달력 input -->
       </div>
   </div>
   ```

3. **왼쪽 미러링 패널 영역 마크업:**
   ```html
   <div class="card border-0 shadow-sm h-100 mb-3">
     <div class="card-header bg-white py-1 px-2 fw-bold small">
       <i class="fas fa-calendar-day"></i> 실측 일정 현황
     </div>
     <div class="card-body p-1" style="max-height: 400px; overflow-y: auto;">
       <div id="erp-beta-measurement-panel" class="measurement-panel-list">
         <!-- JS로 로딩 스피너 및 데이터 바인딩 -->
       </div>
       <div class="small text-muted mt-1 px-1">향후 14일 기준 · 30초 자동 갱신 (클릭 시 실측일에 입력됨)</div>
     </div>
   </div>
   ```

### Phase 3: 프론트엔드 비동기 렌더링 및 UI 바인딩 (JS)
**파일:** `templates/partials/erp_beta_js.html`

1. **데이터 Fetch 및 Render (Hydration):**
   - 페이지 로딩 완료 후 `loadMeasurementPanel()` 비동기 함수 즉시 실행.
   - **API 호출 시 `mine` 파라미터 동기화:** `getErpMineOnlyCookie()`(또는 동일 로직)로 ERP Beta 화면의 "내 담당만" 상태를 읽어, `mine=1` 또는 `mine=0`을 쿼리 스트링에 포함. (대시보드와 건수 일치를 위해 필수)
   - (선택) `q` 파라미터: edit_order/add_order에 검색 UI가 있으면 해당 검색어를 `q`로 전달. 없으면 생략.
   - 패널의 각 날짜(item) 디자인은 기존 `measurement-panel-item-oneline` 클래스를 동일하게 부여해 일관성 있는 CSS 디자인을 계승.
   
2. **30초 자동 갱신 (준실시간 동기화):**
   - 페이지 로딩 후 `setInterval(loadMeasurementPanel, 30000)`으로 **30초마다 API 재호출** → 패널 데이터 자동 갱신.
   - 다른 사용자가 실측일을 변경/추가해도 최대 30초 이내에 ERP Beta 화면에 반영됨.
   - 갱신 중에도 사용자가 선택(highlight) 중인 날짜의 시각적 상태는 유지.
    
3. **원스텝(One-Step) 연동 UX 로직:**
   - 미러링 패널에 렌더링된 특정 날짜 블록(`.measurement-panel-item`)을 **클릭(click)**하면:
     1. 해당 블록이 활성화(highlight) 디자인 피드백 제공.
     2. 우측의 **`#erp-measurement-date`** input 칸에 해당 날짜 문자가 **자동으로 즉각 채워짐.**
     3. 담당자는 일정을 살피고 ➡ 바로 표에서 해당 날짜를 골라 클릭 ➡ 일정이 자동으로 입력 폼에 꽂히는 극강의 편의성 확보.
   - **⚠️ Flatpickr 연동 필수 규칙:**
     - 실측일 input은 `flatpickr(mode: 'multiple')`로 바인딩되어 있으므로, 단순 `input.value = '...'` 설정은 **금지** (내부 상태 불일치 발생).
     - 반드시 `window._erpMeasurementDatePicker.setDate(dateStr, true)` Flatpickr API를 통해 설정해야 함.
     - 기존 선택 날짜에 **추가(append)** 시: 현재 dates 배열 → push → `setDate([...existing, newDate])` 패턴 사용.

---

## 4. 디자인 수정 미리보기 (UI Architecture)

기존 상하 수직 정렬이었던 구조를 좌/우 패널 체계로 분리하여 모니터 뷰포트의 폭을 넓게 활용합니다.
(모바일/작은 화면에서는 자동으로 상/하단(`col-12`) 반응형 정렬 적용)

```text
[ ERP Beta 편집 화면 Layout ]
+------------------------------------------+
| 🔍 검색 및 기초 정보 (그대로 넓게 사용)         |
+------------------------------------------+
| 📅 날짜 및 스케줄 지정 영역                  |
| +--------------------------------------+ |
| | [좌측 패널: 실측일정표(미러링)]  [우측 패널: 필수 입력 폼]       |
| | 26-03-05 (목) [21건]      | ① 실측일 [ 2026-03-05 📅 ]  |
| | 26-03-06 (금) [11건]      | ② 실측 특이사항 [▼ 펼치기]      |
| | 26-03-07 (토) [주말][0건] | ③ 실측시간 [오전/오후/종일]      |
| | 26-03-08 (일) [주말][0건] | ④ 시공일 [ 2026-03-15 📅 ]  |
| +--------------------------------------+ |
+------------------------------------------+
| 📦 제품 항목(1..n) 및 결제 정보 (그대로 넓게 사용)|
+------------------------------------------+
```

## 5. 단계별 검증 절차 (QA Protocol)
- **API 건수 확인:** `GET /api/erp/measurement/summary` 응답의 `count`가 실제 [실측 대시보드] 메뉴에 가서 눈으로 보는 숫자와 완전히 똑같은지 비교.
  - 특히 자가실측 4체크 완료 건, 지방실측 건이 정확히 제외되는지 확인.
- **mine/q 동기화 확인:** `?mine=1` 호출 시 대시보드 "내 담당만" 활성 상태와 건수 일치. `?q=검색어` 호출 시 대시보드 검색 결과와 건수 일치. 클라이언트는 `getErpMineOnlyCookie()`로 ERP Beta의 "내 담당만" 상태와 동기화하여 API 호출.
- **자동 갱신 확인:** 다른 브라우저/탭에서 실측일을 변경한 뒤, ERP Beta 화면에서 30초 이내에 패널 건수가 갱신되는지 확인.
- **클릭 연동 테스트:** 좌측 표에서 날짜를 누르면 오른쪽 `실측일` 칸에 날짜가 즉시 바뀌는지, Flatpickr 달력 플러그인과 충돌이 없는지 검사.
- **CSS 충돌 방어:** `edit_order.html` 내 기존 CSS와 겹치거나 레이아웃 붕괴 현상이 없는지 브라우저 너비 줄여가며 반응형(Responsive) 테스트.
