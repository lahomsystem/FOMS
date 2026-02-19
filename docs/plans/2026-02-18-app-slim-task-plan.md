# app.py 슬림다운 테스크 계획표 (GDM 더블체크 → 300줄 완료까지)

> **기준일**: 2026-02-18  
> **목표**: app.py **300줄 이하** 달성  
> **원칙**: 한 번에 1개 모듈, 단계마다 `python -c "import app; print('APP_OK')"` 검증

---

## 1. GDM 더블체크 결과 (2026-02-18)

| 항목 | 결과 | 비고 |
|------|------|------|
| **앱 기동** | ✅ APP_OK | `python -c "import app; print('APP_OK')"` 통과 |
| **app.py 현재** | **1,536줄** | 목표 300줄 (약 1,236줄 추가 감소 필요) |
| **남은 @app.route** | 11개 | favicon, debug-db, edit_order, upload_excel, download_excel, calendar, wdplanner×3, map_view |
| **url_for BuildError** | ✅ 수정 완료 | calendar, regional/self_measurement/erp_dashboard 등 (orders.api_orders, order_pages.add_order) |
| **분리된 Blueprint** | order_pages, order_trash, orders, dashboards 등 30+ | Phase 2~4 진행 완료 |

### app.py 잔여 블록 (라인 기준)

| 블록 | 라인 범위 | 대략 줄 수 | 분리 후보 |
|------|-----------|-----------|-----------|
| edit_order | 469~946 | ~478 | **order_pages_bp** (또는 order_edit_bp) |
| upload_excel | 947~1157 | ~211 | **excel_bp** 또는 order_pages_bp |
| download_excel | 1158~1294 | ~137 | excel_bp |
| calendar | 1295~1299 | ~5 | **calendar_bp** (라우트만) |
| wdplanner 3개 | 1300~1325 | ~26 | wdcalculator_bp (이미 분리) 또는 유지 |
| map_view | 1326~1336 | ~11 | erp_map_bp 또는 별도 |
| translate_dict_keys, format_value_for_log | 1337~1356 | ~20 | services로 이전 |
| load_menu_config, inject_menu | 1358~1397 | ~40 | services 또는 layout 헬퍼 |
| order_link_filter | 1398~끝 | ~140+ | 템플릿 필터 → Blueprint context_processor |
| context_processor 3개 | 357~424 | ~68 | 유지 또는 services |
| rate_limit_key, allowed_* | 236~343 | ~108 | 유지 (앱 초기화 영역) |

---

## 2. SLIM 테스크 계획표 (우선순위순)

### Phase A: 대형 라우트 분리 (최우선)

| ID | 작업 | 대상 | 예상 감소 | Blueprint | 검증 |
|----|------|------|-----------|-----------|------|
| **SLIM-026** | edit_order 분리 | 469~946 | ~478줄 | order_pages_bp (추가) | /edit/\<id\> GET/POST |
| **SLIM-027** | upload_excel + download_excel | 947~1294 | ~348줄 | **excel_bp** (신규) | /upload, /download_excel |
| **SLIM-028** | calendar 라우트 | 1295~1299 | ~5줄 | calendar_bp (신규) | /calendar |
| **SLIM-029** | map_view | 1326~1336 | ~11줄 | erp_map_bp (추가) | /map_view |

### Phase B: wdplanner·헬퍼 정리

| ID | 작업 | 대상 | 예상 감소 | 비고 |
|----|------|------|-----------|------|
| **SLIM-030** | wdplanner 3라우트 | 1300~1325 | ~26줄 | wdcalculator_bp로 이전 또는 app.py 유지(짧음) |
| **SLIM-031** | translate_dict_keys, format_value_for_log | 1337~1356 | ~20줄 | services/logger_utils 또는 erp 모듈 |
| **SLIM-032** | load_menu_config, inject_menu | 1358~1397 | ~40줄 | services/menu_config.py |
| **SLIM-033** | order_link_filter | 1398~끝 | ~140줄 | 해당 Blueprint context_processor로 이동 |

### Phase C: 최종 정리 (300줄 이하)

| ID | 작업 | 목표 |
|----|------|------|
| **SLIM-034** | 불필요 import·주석 제거 | 라인 수 추가 감소 |
| **SLIM-035** | context_processor·에러핸들러만 유지 | app.py ≈ Flask 초기화 + Blueprint 등록 + 필수 설정 |

---

## 3. 세부 실행 가이드

### SLIM-026: edit_order → order_pages_bp

- **위치**: `apps/order_pages.py`에 `edit_order` 함수 추가
- **route**: `/edit/<int:order_id>` (GET, POST)
- **의존성**: get_db, Order, User, can_edit_erp, format_options_for_display, build_file_view_url 등
- **템플릿 url_for**: `url_for('order_edit.edit_order', order_id=...)` 로 전면 수정 필요

### SLIM-027: excel_bp 신규

- **파일**: `apps/excel_import.py` (또는 `apps/api/excel.py`)
- **라우트**: `/upload` (GET, POST), `/download_excel` (GET)
- **의존성**: pandas, get_db, Order, constants 등

### SLIM-028: calendar_bp

- **파일**: `apps/calendar_page.py`
- **라우트**: `/calendar` → `render_template('calendar.html')` 만 (이미 orders.api_orders 사용)

### SLIM-029: map_view → erp_map_bp

- **파일**: `apps/api/erp_map.py`
- **라우트**: `/map_view` 추가 (페이지 라우트이므로 prefix 확인)

### SLIM-030~033: 헬퍼/필터 이전

- `order_link_filter`: edit_order, index 등에서 사용 → order_pages 또는 공통 context_processor
- `inject_menu`: layout.html에서 사용 → app.py context_processor로 유지 가능 (짧으면)

---

## 4. 예상 app.py 최종 구조 (~300줄)

```
1. imports (~70줄)
2. Flask app 초기화, WhiteNoise, ProxyFix (~30줄)
3. Blueprint 등록 (~100줄)
4. 에러핸들러, rate_limiter, SocketIO (~80줄)
5. 필수 context_processor (inject_statuses, inject_status_list 등) (~50줄)
6. favicon, debug-db, __build (~20줄)
7. teardown, config (~50줄)
```

---

## 5. 검증 체크리스트 (매 SLIM 완료 후)

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] `python app.py` → 서버 기동
- [ ] 해당 페이지 수동 접근 (200 OK)
- [ ] url_for 엔드포인트 수정 (예: `order_pages.edit_order`)
- [ ] ReadLints (신규/수정 파일)

---

## 6. 진행 상태 (갱신용)

| SLIM | 상태 | 완료일 |
|------|------|--------|
| SLIM-026 | 완료 | 2026-02-18 |
| SLIM-027 | 완료 | 2026-02-18 |
| SLIM-028 | 완료 | 2026-02-18 |
| SLIM-029 | 완료 | 2026-02-18 |
| SLIM-030 | 완료 | 2026-02-18 |
| SLIM-031 | 완료 | 2026-02-18 |
| SLIM-032 | 완료 | 2026-02-18 |
| SLIM-033 | 완료 | 2026-02-18 |
| SLIM-034 | 완료 | 2026-02-18 |
| SLIM-035 | **보류** | - | app.py 일단 중단. 다음 착수: `docs/plans/2026-02-18-file-cleanup-and-next-plan.md` |
