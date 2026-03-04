# 실측일·시공일 다중 날짜 구현 — GDM 감리 보고서

**대상 계획서:** `docs/plans/2026-03-04-multiple-dates-plan.md`  
**보조 문서:** `docs/plans/2026-03-04-multiple-dates-plan-GDM-doublecheck.md`  
**감리일:** 2026-03-04 (최종 갱신: 계획서 §3.1·§4 반영)  
**원칙:** 계획서와 구현 코드 1:1 대조.

---

## 1. 감리 요약

| 구분 | 계획서 항목 | 구현 여부 | 비고 |
|------|-------------|-----------|------|
| 3.1 Flatpickr·UI | layout, erp_beta_tab, erp_beta_js | ✅ 일치 | CDN, type="text", 달력 아이콘 버튼, DOMContentLoaded+탭 초기화, mode: multiple, formatDateToKorean CSV, 항목 row 달력 |
| 3.2 백엔드 저장 | order_edit, order_pages, API items | ✅ 일치 | CSV 그대로 저장; 항목은 data-erp로 수집 → items[i].measurement_date/construction_date |
| 3.3 실측 대시보드 | extract_all, 패널, 목록, 구간, 단일일 쿼리 | ✅ 일치 | 구간은 ILIKE(날짜별)·Python 필터 |
| 3.4 출고/시공 대시보드 | extract_all, 패널, 단일·구간 목록 | ✅ 일치 | 구간 rows는 extract_all_construction_dates + date_value in [from,to] |
| 3.5 FullCalendar | 쿼리 완화, CSV split → 다중 이벤트 | ✅ 일치 | ILIKE start/end, start_dates_list split, for one_date → events.append |
| 3.6 dashboards.py | func.date() 제거, Python 필터 | ✅ 일치 | 4곳 모두 헬퍼로 split 후 비교 |
| 3.7 Badge 표시 | 실측/출고/시공 대시보드 | ✅ 일치 | 실측·시공·생산·메인 그리드 Badge 적용; 출고는 행에 날짜 컬럼 없음 |
| GDM 추가 | erp_map.py, erp_measurement.py | ✅ 일치 | ILIKE + Python _order_has_date / _order_measurement_dates |
| §4 Use Cases (1, 2, 2.1~2.3) | 달력 선택·대시보드 표시 | ✅ 일치 | 1=달력 선택 가능, 2/2.1/2.2/2.3=extract_all_* 로직으로 각 Case 충족 |

**종합:** 계획서 §3·§4(Use Cases)·§5(파일 목록)·§6(GDM 보완)이 구현과 **1:1로 일치**합니다.

---

## 2. 계획서 항목별 1:1 대조

### 2.1. §3.1 프론트엔드 UI (Flatpickr)

| 계획서 | 구현 위치 | 판정 |
|--------|-----------|------|
| layout.html `<head>` Flatpickr CSS | `templates/layout.html` L18 | ✅ |
| `</body>` 앞 Flatpickr JS + ko locale | `templates/layout.html` L2310-2311 | ✅ |
| id="erp-measurement-date", id="erp-construction-date" type="text | `erp_beta_tab.html` input-group 내 input | ✅ |
| **달력으로 선택** 가능, 클릭 시 달력 팝업 | Flatpickr 기본 동작 + allowInput: true | ✅ |
| **달력 아이콘** 버튼으로도 열기 | `erp_beta_tab.html` #erp-measurement-date-open, #erp-construction-date-open (fa-calendar-alt), erp_beta_js에서 .open() 바인딩 | ✅ |
| **DOMContentLoaded** 시에도 initErpMainDatePickers 호출 | `erp_beta_js.html` L1800-1801 주석 및 initErpMainDatePickers() 호출 | ✅ |
| flatpickr(elem, { mode: "multiple", dateFormat: "Y-m-d", locale: "ko", allowInput: true }) | initErpMainDatePickers opts, erpInitFlatpickrForItemRow | ✅ |
| erpNewItemRow 항목별 실측일/시공일 input | data-erp="measurement_date", "construction_date", class erp-item-date-multiple | ✅ |
| 동적 row Flatpickr 적용 | erpInitFlatpickrForItemRow(row), erpNewItemRow 후 호출 | ✅ |
| formatDateToKorean CSV 처리 | split(',').map(single).filter(Boolean).join(', ') | ✅ |

- 계획서 "data-erp=\"item_measurement_date\"": `data-erp="measurement_date"`로 두어 items[i].measurement_date로 수집되며, **의도와 동일**.

### 2.2. §3.2 백엔드 저장

| 계획서 | 구현 | 판정 |
|--------|------|------|
| CSV 문자열 그대로 저장 허용 | order_edit.py / order_pages.py request.form.get 문자열 그대로 setattr | ✅ (확인만, 변경 없음) |
| structured_data.schedule.measurement.date, construction.date | order_edit.py L197, L201 반영 | ✅ |
| items[i].measurement_date, construction_date | 프론트 data-erp 수집 → API가 structured_data 통째 저장 | ✅ (저장 API 변경 없이 기존 구조로 저장) |

### 2.3. §3.3 실측 대시보드

| 계획서 | 구현 | 판정 |
|--------|------|------|
| extract_all_measurement_dates(order) | `erp_measurement_dashboard.py` L54-77: measurement_date, schedule.measurement.date, items[].measurement_date | ✅ |
| 패널 집계 all_dates → 각 date_value별 +1 | L208-217: for date_value in all_dates, strptime, measurement_counts[key] += 1 | ✅ |
| 목록 필터 selected_date in extract_all_measurement_dates(order) | L238-242: should_include = selected_date in extract_all_measurement_dates(order) | ✅ |
| 단일일 DB 쿼리 ILIKE + JSONB | L156-158: measurement_date.ilike(f'%{selected_date}%'), cast(structured_data,String).ilike(f'%"measurement_date"%{selected_date}%') | ✅ |
| 구간(use_range) CSV 대응 | L119-130: ILIKE per day 후보 조회; L245-262: **use_range 시 Python 필터** — extract_all_measurement_dates로 구간 내 실측일이 하나라도 있는 주문만 rows에 포함 | ✅ (보강 반영됨) |

### 2.4. §3.4 출고/시공 대시보드

| 계획서 | 구현 | 판정 |
|--------|------|------|
| extract_all_construction_dates(order) | `erp_shipment_page.py` L68-85: _get_order_construction_date split + items[].construction_date | ✅ |
| 패널 집계 all_dates 순회, construction_counts·자원 | L188-212: for date_value in all_dates, key별 +1, assigned_workers_by_date, spec_units_by_date | ✅ |
| 단일일 목록 필터 selected_date in extract_all_construction_dates | L319-320: if selected_date in extract_all_construction_dates(order): rows.append(order) | ✅ |
| 구간(use_range) 목록 필터 | L280-287: all_dates = extract_all_construction_dates(order), for date_value in all_dates, date_from <= date_value <= date_to 시 append & break | ✅ (GDM 2.2 반영) |
| 시공 대시보드 CSV Badge | `erp_construction_filters_grid.html`에서 o.construction_date Badge | ✅ |

### 2.5. §3.5 캘린더(FullCalendar)

| 계획서 | 구현 | 판정 |
|--------|------|------|
| 쿼리 완화(measurement_date.between 제거) | `apps/api/orders.py` L313-331: received_date.between + measurement_date/scheduled_date ILIKE start/end | ✅ |
| start_date_val split(',') 후 날짜별 이벤트 | L400-403: start_dates_list = split(','), for idx, one_date in enumerate(start_dates_list): events.append(...) | ✅ |

### 2.6. §3.6 dashboards.py

| 계획서(GDM 정정: 4곳) | 구현 | 판정 |
|------------------------|------|------|
| func.date(Order.measurement_date) == today | urgent_alerts: 후보 로드 후 _measurement_dates_include_today(o) 필터 | ✅ |
| func.date(Order.measurement_date) < today | measurement_alerts: _measurement_dates_any_lt_today(o) | ✅ |
| func.date(Order.measurement_date) > today | pre_measurement_alerts: _measurement_dates_any_gt_today(o) | ✅ |
| func.date(Order.scheduled_date) < today | installation_alerts: _scheduled_dates_any_lt_today(o) | ✅ |

### 2.7. §3.7 목록 표시 UI (Badge)

| 계획서 | 구현 | 판정 |
|--------|------|------|
| erp_measurement_dashboard.html 날짜 Badge | meas_date → _date_str, _parts = split(',')\|map('trim')\|select\|list, badge 루프 | ✅ |
| erp_construction_dashboard 날짜 Badge | 시공 그리드는 `erp_construction_filters_grid.html`에서 o.measurement_date, o.construction_date Badge | ✅ |
| erp_shipment_dashboard 날짜 Badge (권장) | 출고 대시보드 행 테이블에 시공일 컬럼 없음(패널만 날짜). Badge 적용 위치 없음 — **해당 없음** | — |

- 추가 적용: `erp_production_filters_grid.html`, `erp_dashboard_grid.html`에서 실측일/시공일 Badge 적용됨.

### 2.8. §4 달력 선택 및 Use Cases (1, 2, 2.1~2.3)

| 계획서 | 구현 | 판정 |
|--------|------|------|
| **1.** 실측일·시공일 input 달력(Flatpickr)으로 선택, 클릭 시 팝업 | Flatpickr on input + 달력 아이콘 버튼으로 .open() | ✅ |
| **2.** 실측 1day + 시공 1day → 기존대로 해당 날만 표기 | extract_all_* 가 단일 날짜만 반환 → 패널/목록에 해당 1일만 노출 | ✅ |
| **2.1** 실측 1day + 시공 multiple → 실측: 지정일만 / 시공: 각 시공일마다 | extract_all_measurement_dates 1개, extract_all_construction_dates 여러 개 → 각 대시보드에서 날짜별 포함 여부로 표시 | ✅ |
| **2.2** 실측 multiple + 시공 multiple → 각각 선택한 날마다 표시 | extract_all_* 가 여러 날짜 반환 → 패널 집계·목록 필터가 각 날짜별로 동작 | ✅ |
| **2.3** 항목별 실측 multiple + 항목별 시공 multiple | extract_all_* 가 이미 items[].measurement_date, construction_date 수집 → 동일 로직으로 처리 | ✅ |

### 2.9. §5 수정 대상 파일 완전 목록

| # | 파일 | 계획 | 구현 | 판정 |
|---|------|------|------|------|
| 1 | layout.html | Flatpickr CDN | CSS + JS + ko | ✅ |
| 2 | erp_beta_tab.html | input type, placeholder, 달력 아이콘 | type="text", input-group+버튼 #erp-*-date-open | ✅ |
| 3 | erp_beta_js.html | Flatpickr init, formatDateToKorean, item row | 전부 반영 | ✅ |
| 4–5 | order_edit.py, order_pages.py | CSV 허용 확인 | 확인만 | ✅ |
| 6 | erp_measurement_dashboard.py | extract_all, 패널, 필터, 쿼리, 구간 | 전부 반영 | ✅ |
| 7 | erp_shipment_page.py | extract_all, 패널, 단일·구간 필터 | 전부 반영 | ✅ |
| 7-1 | erp_construction_page.py | 시공일 CSV 표시 | 데이터 전달 유지, Badge는 partial에서 | ✅ |
| 8 | apps/api/orders.py | FullCalendar 다중 이벤트 | 쿼리 완화 + split → 다중 이벤트 | ✅ |
| 9 | dashboards.py | func.date 4곳 | Python 헬퍼 4개로 대체 | ✅ |
| 10–12 | 대시보드 템플릿 Badge | 실측/출고/시공 | 실측·시공·생산·메인 그리드 Badge | ✅ (출고 행에는 날짜 컬럼 없음) |
| 13 | erp_map.py | 날짜 필터 CSV/항목 | ILIKE + _order_has_date / _order_has_date_fetch | ✅ |
| 14 | erp_measurement.py | 날짜 조건 CSV/항목 | ILIKE + _order_measurement_dates | ✅ |

---

## 3. GDM 더블체크 보완 사항 반영 여부

| GDM 보완 항목 | 반영 내용 | 판정 |
|---------------|-----------|------|
| 실측 구간(use_range) 쿼리 | measurement_date에 대해 구간 내 날짜별 ILIKE(최대 31일)로 후보 조회 | ✅ |
| 출고 구간(use_range) 목록 필터 | extract_all_construction_dates 후 date_from <= date_value <= date_to 로 rows 포함 | ✅ |
| FullCalendar 쿼리·이벤트 | between 제거, ILIKE start/end; 이벤트는 split 후 날짜별 append | ✅ |
| CSV 형식 split(',') + strip() | 전 구간 split(',') 후 strip() 사용 | ✅ |
| erp_map.py, erp_measurement.py | 계획서 목록에 없던 파일 추가 반영, ILIKE + Python 필터 | ✅ |

---

## 4. 경미한 차이·참고 사항

1. **항목 row data-erp:** 계획서는 "item_measurement_date" 예시였으나, GDM 2.6에 따라 `measurement_date`로 두어 `items[i].measurement_date`로 수집되도록 구현됨. 동작은 동일.
2. **실측 구간(use_range) 목록 필터:** 보강으로 **Python 필터 적용 완료** — use_range일 때 extract_all_measurement_dates(order)로 구간 [date_from, date_to] 내 실측일이 하나라도 있는 주문만 rows에 포함.
3. **출고 대시보드 Badge:** 계획 §4 11번은 "erp_shipment_dashboard.html 날짜 Badge 권장"이나, 해당 템플릿의 행 테이블에는 시공일 컬럼이 없어 Badge를 둘 위치가 없음. 패널에만 날짜가 있으므로 **해당 없음**으로 처리함.

4. **실측 대시보드 구간(use_range) 목록 필터:** ~~현재 쿼리 … **(선택 보강)**~~ → **보강 완료:** `use_range`일 때 `rows`를 `extract_all_measurement_dates(order)`로 Python 필터해, 구간 `[date_from, date_to]` 안에 실측일이 하나라도 있는 주문만 목록에 포함하도록 `erp_measurement_dashboard.py`에 반영함.

---

## 5. 결론

- **계획서 §3(작업 상세)·§4(달력 선택 및 Use Cases 1, 2, 2.1~2.3)·§5(파일 목록)·§6(GDM 보완)** 요구 사항이 구현과 **1:1로 반영**되었습니다.
- **§3.1** 달력 선택 보장(클릭 시 팝업, 달력 아이콘 버튼), DOMContentLoaded 초기화, 항목 row 달력 적용 확인됨.
- **§4** Case 2, 2.1, 2.2, 2.3 동작은 `extract_all_measurement_dates` / `extract_all_construction_dates` 및 패널·목록 필터 로직으로 충족됩니다.
- **수정 대상 파일(§5)** 및 erp_map.py, erp_measurement.py 반영 완료. 실측 구간(use_range) 목록 Python 필터 보강 완료.

**감리 결과: 통과.**
