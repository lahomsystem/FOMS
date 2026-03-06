# GDM 검증: ERP 실측 패널 미러링 계획서 교차검증 보고

> **검증 일시:** 2026-03-05  
> **대상:** `docs/plans/2026-03-05-erp-measurement-panel-mirroring-plan.md`  
> **방법:** Grand Develop Master 프로토콜에 따른 코드베이스 교차검증

---

## 1. 검증 요약

| 항목 | 결과 | 비고 |
|------|------|------|
| 파일/라인 참조 정확성 | ✅ | 실제 코드 위치와 일치 |
| API 설계 | ✅ | `erp_measurement_bp` 기존 Blueprint 활용 가능 |
| 필터링 로직 정합성 | ✅ | L95–103, L185–203 기준 일치 |
| Flatpickr 연동 규칙 | ⚠️ | API 시그니처 1건 보완 권장 |
| 의존성/임포트 | ⚠️ | 추천 패키지 구조 1건 |

---

## 2. 상세 검증 결과

### 2-1. Phase 1 — API (`GET /api/erp/measurement/summary`)

| 검증 항목 | 계획서 기술 | 실제 코드 | 판정 |
|-----------|-------------|-----------|------|
| API 배치 | `apps/api/erp_measurement.py` | ✅ 존재, `url_prefix='/api/erp/measurement'` | ✅ |
| 14일 범위 | 오늘 ~ 향후 14일 | `range_end = today_kst + timedelta(days=14)` (L179) | ✅ |
| `extract_all_measurement_dates` | L191 활용 | `erp_measurement_dashboard.py` L54–77 정의 | ✅ |
| `self_measurement_four_checks_done` | 패널 루프에서 제외 | L189–190 `if self_measurement_four_checks_done(order): continue` | ✅ |
| base_query 필터 | L95–103 | `Order.is_regional != True`, `~Order.status.in_(...)`, `is_self_measurement` 예외 | ✅ |
| `_load_holidays_for_year` | 휴일 여부 | `erp_measurement_dashboard.py` L26–34 정의 | ✅ |

**구현 시 참고:**
- `extract_all_measurement_dates`, `self_measurement_four_checks_done`, `_load_holidays_for_year`를 `erp_measurement_dashboard.py`에서 import하여 사용.
- `panel_orders` 수집 로직(L169–173)과 동일한 `base_query` + `mine_filter_active` 적용 필요. 대시보드와 건수 일치를 위해 **`mine=1` 쿼리 파라미터 지원 권장**.

---

### 2-2. Phase 2 — HTML 레이아웃 (`erp_beta_tab.html`)

| 검증 항목 | 계획서 | 실제 | 판정 |
|-----------|--------|------|------|
| 실측일 ID | `#erp-measurement-date` | L170 | ✅ |
| 실측시간 | `#erp-measurement-time-select`, `#erp-measurement-time` | L176–185 | ✅ |
| 실측 특이사항 | `#erp-collapse-measure-note` | L188–199 | ✅ |
| 시공일 | `#erp-construction-date` | L203–207 | ✅ |
| 현재 순서 | 실측일 → 실측시간 → 특이사항 → 시공일 | 확인됨 | ✅ |
| 목표 순서 | ① 실측일 → ② 특이사항 → ③ 실측시간 → ④ 시공일 | — | 구현 시 적용 |

---

### 2-3. Phase 3 — JS/Flatpickr 연동

| 검증 항목 | 계획서 | 실제 | 판정 |
|-----------|--------|------|------|
| Flatpickr 전역 | `window._erpMeasurementDatePicker` | `erp_beta_js.html` L1937 | ✅ |
| mode | `multiple` | `opts = { mode: 'multiple', ... }` | ✅ |
| `setDate` 사용 | `setDate(dateStr, true)` | L492: `setDate(dates)` (배열) | ⚠️ |

**Flatpickr API 보완:**
- 계획서: `setDate(dateStr, true)`
- Flatpickr `mode: 'multiple'`에서는 `setDate(dates: string[] | Date[], triggerChange?: boolean)` 사용.
- **단일 날짜 클릭(교체):** `setDate([dateStr])` 또는 `setDate([dateStr], true)`
- **기존 날짜에 추가:** `const existing = window._erpMeasurementDatePicker.selectedDates.map(d => d.toISOString().slice(0,10)); setDate([...existing, newDate])`

---

### 2-4. CSS 클래스명

| 계획서 | 실제 (`erp_measurement_dashboard.html`) | 판정 |
|--------|----------------------------------------|------|
| `measurement-panel-list` | L75 | ✅ |
| `measurement-panel-item` | L79 | ✅ |
| `measurement-panel-item-oneline` | L79 | ✅ |
| `measurement-panel-date`, `measurement-panel-day`, `badge-count` | L82–86 | ✅ |

---

## 3. 발견된 이슈 및 보완 제안

### 🟡 보완 1: Flatpickr `setDate` 시그니처

**계획서 L132:** `window._erpMeasurementDatePicker.setDate(dateStr, true)`

**권장 수정:**
```
- 단일 날짜 설정(클릭 시 교체): setDate([dateStr], true)
- 기존 날짜에 추가: const existing = [...]; setDate([...existing, newDate], true)
```

### 🟡 보완 2: API `mine` 필터

대시보드와 건수 일치를 위해 `GET /api/erp/measurement/summary?mine=1` 지원 권장. `erp_measurement_dashboard.py` L169–173에서 `mine_filter_active` 적용 여부와 동일하게 처리.

---

## 4. 최종 판정

| 구분 | 판정 |
|------|------|
| **계획서 신뢰도** | ✅ **높음** — 파일 경로, 라인 번호, 클래스명, 함수명이 실제 코드와 일치 |
| **구현 가능성** | ✅ **즉시 구현 가능** — 보완 1·2 반영 시 충분 |
| **RPI 프로토콜** | ✅ Spec 기반 계획 완료 — 사용자 승인 후 구현 진행 가능 |

---

## 5. 구현 완료 (2026-03-06)

| Phase | 파일 | 구현 내용 |
|-------|------|-----------|
| 1 | `apps/api/erp_measurement.py` | `GET /api/erp/measurement/summary` 추가, mine=1 지원 |
| 2 | `templates/partials/erp_beta_tab.html` | 2단(col-md-4/col-md-8), 필드순서(실측일→특이사항→시간→시공일), 패널+스타일 |
| 3 | `templates/partials/erp_beta_js.html` | `loadMeasurementPanel()`, 30초 간격, 클릭→Flatpickr `setDate([dateStr], true)` |

---

## 6. 검증·구현에 사용한 소스

- `apps/erp_measurement_dashboard.py` (L54–77, L85–220)
- `apps/api/erp_measurement.py`
- `templates/partials/erp_beta_tab.html` (L166–211)
- `templates/partials/erp_beta_js.html` (L490–492, L1937–1946)
- `templates/erp_measurement_dashboard.html` (L75–91, L175–233)
- `services/erp_display.py` (`self_measurement_four_checks_done`)

---

## 7. GDM 구현·계획서 1:1 소스코드 비교 검증

> **검증 일시:** 2026-03-06  
> **방법:** 계획서 §3 각 조항과 실제 구현 코드를 항목별로 대조

### Phase 1 — API (계획 L42–65 vs `erp_measurement.py` L31–102)

| 계획서 조항 | 계획 내용 | 구현 소스 | 판정 |
|-------------|-----------|-----------|------|
| L42 | `GET /api/erp/measurement/summary` | `@erp_measurement_bp.route('/summary')` (L31) | ✅ |
| L43 | 파일: `apps/api/erp_measurement.py` | 해당 파일에 구현 | ✅ |
| L44 | 오늘~향후 14일 | `range_end = today_kst + timedelta(days=14)` (L41) | ✅ |
| L45 | `extract_all_measurement_dates` 활용 | `from apps.erp_measurement_dashboard import extract_all_measurement_dates` (L22) + L70 | ✅ |
| L47 | `self_measurement_four_checks_done` 제외 | L67–69 `if self_measurement_four_checks_done(order): continue` | ✅ |
| L48 | `Order.is_regional != True` 제외 | L47 `Order.is_regional != True` | ✅ |
| L49 | `~Order.status.in_(['SELF_MEASUREMENT','SELF_MEASURED'])` | L49 (and 내부) | ✅ |
| L49 | `is_self_measurement == True` 포함 | L51 `Order.is_self_measurement == True` | ✅ |
| L51–64 | 응답: success, panel_dates, date, day_label, count, is_weekend, is_holiday, is_today | L89–102 `panel_dates.append({...})`, L99–102 | ✅ |
| 검증 보완2 | mine=1 쿼리 지원 | L55–59 `mine_filter_active`, L58–59 | ✅ |

### Phase 2 — HTML (계획 L66–108 vs `erp_beta_tab.html` L165–241)

| 계획서 조항 | 계획 내용 | 구현 소스 | 판정 |
|-------------|-----------|-----------|------|
| L69–71 | 2단: 왼쪽 col-md-4, 오른쪽 col-md-8 | L166–167 `col-12 col-md-4` / L194 `col-12 col-md-8` | ✅ |
| L74–93 | 필드 순서: 실측일→특이사항→시간→시공일 | L196→L205→L218→L230 순 | ✅ |
| L96–108 | card, card-header "실측 일정 현황", card-body max-height 400px | L168–180 | ✅ |
| L103 | `id="erp-beta-measurement-panel"` | L173 | ✅ |
| L103 | `class="measurement-panel-list"` | L173 (JS에서 `panel.classList.add` L1966) | ✅ |
| L105 | 안내문 "향후 14일 기준 · 30초 자동 갱신 (클릭 시 실측일에 입력됨)" | L177 | ✅ |

### Phase 3 — JS (계획 L112–134 vs `erp_beta_js.html` L1928–2065)

| 계획서 조항 | 계획 내용 | 구현 소스 | 판정 |
|-------------|-----------|-----------|------|
| L115 | `loadMeasurementPanel()` 페이지 로드 시 실행 | L2027 `loadMeasurementPanel()` | ✅ |
| L116 | `measurement-panel-item-oneline` 클래스 | L1949 `measurement-panel-item-oneline` | ✅ |
| L119 | `setInterval(loadMeasurementPanel, 30000)` | L2028 | ✅ |
| L125–127 | 클릭 시 ① 활성화 ② #erp-measurement-date 채움 | L1971–1975 `is-selected`, `setDate([dateStr], true)` | ✅ |
| L131 | Flatpickr API 사용 (input.value 금지) | L1975 `window._erpMeasurementDatePicker.setDate([dateStr], true)` | ✅ |
| 검증 보완1 | `setDate([dateStr], true)` 배열 형식 | L1975 `setDate([dateStr], true)` | ✅ |

### 추가 구현 (계획서에 없으나 검증·QA 관점에서 반영)

| 항목 | 구현 | 판정 |
|------|------|------|
| 로딩 스피너 | L174–176 `<i class="fas fa-spinner fa-spin"></i> 로딩 중...` | ✅ |
| 선택 상태 유지 (갱신 후) | L1943–1946 Flatpickr selectedDates 동기화 | ✅ |
| 탭 shown 시 재로드 | L2034, L2063 `loadMeasurementPanel()` | ✅ |
| 패널 전용 CSS | L181–191 `#erp-beta-measurement-panel` 스타일 | ✅ |

### 1:1 비교 최종 판정

| 구분 | 판정 |
|------|------|
| **계획서 준수율** | **100%** — 모든 조항이 구현 코드와 대응 |
| **검증 보완 반영** | ✅ Flatpickr `setDate` 시그니처, API `mine` 지원 반영 완료 |
