# 실측일·시공일 다중 날짜 계획서 — GDM 최종 더블체크

**대상 계획서:** `docs/plans/2026-03-04-multiple-dates-plan.md`  
**검증일:** 2026-03-04  
**원칙:** 근본 원인 해결, 구시대 방식 금지, 계획서와 실제 코드 1:1 대조.

---

## 1. 계획서·코드 대조 요약

| 구분 | 계획서 | 실제 코드 | 판정 |
|------|--------|-----------|------|
| 실측일 DB | `Order.measurement_date` (String) | 사용처 다수 (erp_measurement_dashboard, order_edit, dashboards, api) | ✅ |
| 시공일 DB | `Order.scheduled_date` (String) | 동일 | ✅ |
| ERP Beta 경로 | `schedule.measurement.date`, `schedule.construction.date` | `(sd.get('schedule') or {}).get('measurement') or {}).get('date')` 등 | ✅ |
| order_edit.py L171, L175 | measurement_date / scheduled_date 저장 | L171 `setattr(order, 'measurement_date', measurement_date)`, L175 동일, L197/L201에 schedule 반영 | ✅ |
| formatDateToKorean | L1583~1592, 단일 날짜 정규식 | L1583~1593 `/^(\d{4})-(\d{2})-(\d{2})$/` → CSV 시 미매칭 | ✅ 수정 필요(계획 반영) |
| erp_beta_tab 입력 | id="erp-measurement-date", id="erp-construction-date" | L164 type="date", L195 type="date" | ✅ type="text" 변경 필요 |
| erpNewItemRow | 항목별 measurement_date, construction_date | 현재 항목에 날짜 필드 없음, data-erp 수집은 `obj[inp.dataset.erp]=inp.value` | ✅ 계획대로 추가 시 자동 수집 |
| dashboards.py func.date() | "6곳" 수정 | L144, L151, L160 (measurement_date 3곳), L172 (scheduled_date 1곳) = **4곳** | ⚠️ 4곳으로 정정 (scheduled_date 포함 5곳) |

---

## 2. 계획서 누락·보완 필요 사항

### 2.1. 실측 대시보드 — 구간(use_range) 쿼리

**위치:** `apps/erp_measurement_dashboard.py` L96~98

**현재:**  
`Order.measurement_date >= date_from`, `Order.measurement_date <= date_to` (단일 날짜 전제)

**문제:**  
값이 `"2026-03-13, 2026-03-14"` 같은 CSV이면 문자열 비교로 동작해, 구간 필터가 잘못 동작하거나 누락됨.

**보완:**  
- 구간 선택 시에는 `Order.measurement_date`/structured_data에 대한 단순 크기 비교 대신,  
  **Python 레벨**에서 `extract_all_measurement_dates(order)`로 추출한 날짜 중 `range_start`~`range_end`에 하나라도 들어오면 포함하도록 필터링하거나,  
- 또는 DB에서는 넓게 가져온 뒤(예: `Order.measurement_date.isnot(None)` 등) 메모리에서 `extract_all_measurement_dates`로 구간 필터 적용.

**권장:**  
구간 모드에서도 단일일과 동일하게, 먼저 넓은 조건으로 후보를 가져온 뒤, `extract_all_measurement_dates`로 구간 내 포함 여부를 판단하는 방식으로 통일.

---

### 2.2. 출고/시공 대시보드 — 구간(use_range) 목록 필터

**위치:** `apps/erp_shipment_page.py` L260~265

**현재:**  
`date_value = _get_order_construction_date(order)` (단일 문자열) 후 `date_from <= date_value <= date_to` 비교.

**문제:**  
`date_value`가 CSV면 문자열 비교가 되어, 구간 필터가 잘못됨.

**보완:**  
`extract_all_construction_dates(order)`를 사용해, 반환된 날짜 중 하나라도 `[date_from, date_to]` 안에 있으면 `rows`에 포함하도록 수정.  
(계획서에는 단일일 `selected_date in extract_all_construction_dates(order)`만 명시되어 있음.)

---

### 2.3. FullCalendar API — 쿼리 및 이벤트 생성

**위치:** `apps/api/orders.py` L306~318, L334~415

**쿼리 (L313~317):**  
`Order.measurement_date.between(start_date_only, end_date_only)`  
→ CSV 저장 시 문자열 between으로는 의도한 구간 조회가 되지 않음.

**보완:**  
- 날짜 구간 필터는 완화(예: `Order.measurement_date.isnot(None)` 등)한 뒤,  
- 이벤트 생성 루프에서 `measurement_date`/`scheduled_date`를 `split(',')`으로 나누고,  
- 각 날짜마다 **별도 이벤트**를 만들어 `events`에 append (계획서 3.5와 일치).

**이벤트 생성 (L372~415):**  
현재는 주문당 이벤트 1개. 계획서대로 CSV면 `split` 후 날짜별로 이벤트 추가 필요.

---

### 2.4. 계획서 미포함 — 추가 수정 필요 파일

| 파일 | 용도 | 필요한 수정 |
|------|------|-------------|
| `apps/api/erp_map.py` | 실측/시공 지도 날짜 필터 | L99, L101: `Order.measurement_date == date_filter`, `Order.scheduled_date == date_filter` → CSV/항목 대응 (ILIKE 또는 후보 로드 후 `extract_all_*` 포함 여부 판단). L130~136, L266~268, L300~306 등 동일 논리 적용. |
| `apps/api/erp_measurement.py` | 실측 API 날짜 조건 | L115, L128~133: 단일 `date_filter` 비교 → CSV 및 `structured_data.items[].measurement_date` 반영한 포함 로직으로 변경. |

위 두 파일은 계획서 “수정 대상 파일 완전 목록”에 없으므로, **추가**하는 것이 안전함.

---

### 2.5. CSV 형식 일관성

**계획서:**  
`"YYYY-MM-DD, YYYY-MM-DD"` 예시 및 `split(',')` 후 `strip()`.

**권장:**  
- 저장/파싱 시 **쉼표만** 기준으로 `split(',')` 하고 각 토큰을 `strip()` 해서 공백 유무에 상관없이 처리.  
- Flatpickr `mode: "multiple"` 출력 형식(쉼표+공백 등)과 백엔드 파싱을 동일 규칙으로 통일할 것.

---

### 2.6. 항목(Item) 날짜 — 저장 경로

**계획서:**  
`structured_data.items[i].measurement_date`, `structured_data.items[i].construction_date` 수집·저장.

**코드:**  
`erp_beta_js.html`에서 item payload는 `row.querySelectorAll('[data-erp]')`로 `obj[inp.dataset.erp] = inp.value` 수집.  
따라서 항목 행에 `data-erp="measurement_date"`, `data-erp="construction_date"` input을 추가하면 `items[i].measurement_date`, `items[i].construction_date`로 전달됨.  
저장 API(`apps/api/orders.py` 등)에서 `structured_data.items`를 그대로 저장하면 됨.  
→ **계획서와 호환**, 구현 시 항목 row에 두 입력 필드만 추가하면 됨.

---

### 2.7. 레거시 order_pages / excel_import

**order_pages.py:**  
L289, L294에서 `measurement_date`, `scheduled_date`를 form에서 그대로 전달. CSV 문자열이 오면 그대로 저장 가능.  
→ “CSV 저장 허용 확인”만 하면 됨 (계획서 3.2).

**excel_import.py:**  
실측일을 단일 날짜로 파싱·저장. 다중 날짜를 엑셀에서 어떻게 넣을지(첫 번째만, 쉼표 구분 등)는 별도 요구사항이 없으면 **현재 동작 유지**로 두고, 계획서에는 “변경 없음” 또는 “선택 사항”으로 명시해 두는 것이 좋음.

---

## 3. 라인 번호 및 섹션 번호 정리

- 계획서 **3.3.2**가 두 번 사용됨(패널 집계 / 목록 필터). 두 번째는 **3.3.3**으로 두는 것이 혼동 방지에 유리함.
- **3.3.4**도 두 번(DB 쿼리 필터 / strptime 파손 방지). 하나는 3.3.4, 다른 하나는 3.3.5 등으로 구분 권장.
- 실제 라인 번호는 파일 수정 이력에 따라 달라질 수 있으므로, 구현 시 “해당 블록/함수” 기준으로 매칭하고, “L121” 등은 참고용으로만 사용할 것.

---

## 4. 최종 체크리스트 (계획서 반영 권장)

- [ ] **3.1** Flatpickr CDN, `type="text"` 변경, `formatDateToKorean` CSV 대응, **erpNewItemRow**에 항목별 실측일/시공일 input 및 Flatpickr 초기화.
- [ ] **3.2** order_edit / order_pages CSV 허용; API에서 `items[i].measurement_date`, `items[i].construction_date` 저장.
- [ ] **3.3** 실측 대시보드: `extract_all_measurement_dates`, 패널 집계, **단일일** 목록 필터, **구간(use_range)** 쿼리/필터 보완, DB 단일일 쿼리(ILIKE/JSONB).
- [ ] **3.4** 출고 대시보드: `extract_all_construction_dates`, 패널 집계, **단일일** 목록 필터, **구간(use_range)** 목록 필터 보완; 시공 대시보드 CSV Badge 표시.
- [ ] **3.5** FullCalendar: 쿼리 완화 + 이벤트 생성 시 CSV split하여 날짜별 이벤트 추가.
- [ ] **3.6** dashboards.py: `func.date(Order.measurement_date)` 3곳, `func.date(Order.scheduled_date)` 1곳 → ILIKE 또는 Python 필터로 변경 (총 4곳).
- [ ] **추가** `apps/api/erp_map.py`, `apps/api/erp_measurement.py` 날짜 필터를 CSV·항목 날짜 반영하도록 수정.
- [ ] **3.7** 실측/출고/시공 대시보드 템플릿에서 날짜 Badge 표시.

---

## 5. 결론

- 계획서의 **데이터 구조, 저장 경로, 대표 파일·로직**은 실제 코드와 **일치**하며, 다중 날짜 도입 방향은 타당함.
- **반드시 보완할 부분:**  
  - 실측/출고 **구간(use_range)** 쿼리·필터,  
  - FullCalendar 쿼리 및 이벤트 다중 생성,  
  - **erp_map.py**, **erp_measurement.py** 날짜 필터.
- **문서 정리:**  
  - dashboards.py “6곳” → “4곳” 정정,  
  - 섹션 번호 중복 정리(3.3.2/3.3.4),  
  - 위 보완 사항을 본 계획서 또는 `2026-03-04-multiple-dates-plan.md`에 반영 후 구현 진행 권장.

이 문서는 `2026-03-04-multiple-dates-plan.md`의 **보조 검증 문서**로, 구현 시 본 계획서와 함께 참고하면 됨.
