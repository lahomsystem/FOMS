# erp.py 슬림다운 계획표

> **기준일**: 2026-02-17  
> **목표**: apps/erp.py **500줄 이하** 달성  
> **원칙**: 한 번에 1개 모듈, 단계마다 `python -c "import app; print('APP_OK')"` 검증

---

## 1. 현재 상태 (코드 검증)

| 항목 | 현재 | 목표 |
|------|------|------|
| **apps/erp.py** | **2,061줄** | 500줄 이하 |
| **app.py** | 300줄 | ✅ 달성 |

### erp.py 블록 구성 (라인 기준)

| 블록 | 라인 범위 | 대략 줄 수 | 비고 |
|------|-----------|-----------|------|
| 헬퍼/권한 | 33~57 | ~25 | can_edit_erp, erp_edit_required |
| 템플릿 필터 | 81~158 | ~78 | split_count, split_list, strip_product_w, spec_w300, format_phone, spec_w300_value |
| display 헬퍼 | 159~428 | ~270 | _ensure_dict, apply_erp_display_fields*, _erp_get_*, _erp_alerts, _sales_domain_*, _drawing_* |
| erp_dashboard | 428~838 | ~411 | 메인 대시보드 |
| drawing_workbench | 840~1099 | ~260 | 도면 작업실 목록 |
| drawing_workbench_detail | 1101~1317 | ~217 | 도면 작업실 상세 |
| measurement_dashboard | 1319~1498 | ~180 | 실측 대시보드 |
| shipment_dashboard | 1500~1750 | ~251 | 출고 대시보드 |
| as_dashboard | 1752~1791 | ~40 | AS 대시보드 |
| production_dashboard | 1793~1948 | ~156 | 생산 대시보드 |
| construction_dashboard | 1950~2079 | ~130 | 시공 대시보드 |

**주문 API**: Phase 4-5a~h에서 이미 apps/api/erp_orders_*.py로 분리 완료.

---

## 2. 분리 전략 (우선순위순)

### Phase A: 헬퍼/필터 → services·Blueprint 분리

| ID | 작업 | 대상 | 예상 줄 수 | 산출물 | 검증 |
|----|------|------|-----------|--------|------|
| **ERP-SLIM-1** | 템플릿 필터 6개 분리 | 81~158 | ~78줄 | `services/erp_template_filters.py` 또는 erp_bp에 유지(필터는 Blueprint에 등록 필요) | 템플릿 렌더 |
| **ERP-SLIM-2** | display 헬퍼 분리 | 159~428 | ~270줄 | `services/erp_display.py` | 대시보드 동작 |
| **ERP-SLIM-3** | can_edit_erp, erp_edit_required 분리 | 33~57 | ~25줄 | `services/erp_permissions.py` (또는 apps/auth 확장) | 권한 검증 |

**의존성**: display 헬퍼는 템플릿 필터보다 먼저 분리 가능. can_edit_erp는 app.py에서 re-export될 수 있음 → services로 옮기고 app.py에서 `from services.erp_permissions import can_edit_erp` 사용.

### Phase B: 대시보드 페이지 Blueprint 분리

| ID | 작업 | 라우트 | 예상 줄 수 | 산출물 | 검증 |
|----|------|--------|-----------|--------|------|
| **ERP-SLIM-4** | erp_dashboard 분리 | /erp/dashboard | ~411줄 | `apps/erp_dashboard.py` (erp_dashboard_bp) | /erp/dashboard 200 |
| **ERP-SLIM-5** | drawing_workbench 분리 | /erp/drawing-workbench, /erp/drawing-workbench/\<id\> | ~477줄 | `apps/erp_drawing_workbench.py` | 도면 작업실 목록·상세 |
| **ERP-SLIM-6** | measurement_dashboard 분리 | /erp/measurement | ~180줄 | `apps/erp_measurement_page.py` | /erp/measurement |
| **ERP-SLIM-7** | shipment_dashboard 분리 | /erp/shipment | ~251줄 | `apps/erp_shipment_page.py` | /erp/shipment |
| **ERP-SLIM-8** | as_dashboard 분리 | /erp/as | ~40줄 | `apps/erp_as_page.py` 또는 erp_bp 잔여에 유지 | /erp/as |
| **ERP-SLIM-9** | production_dashboard 분리 | /erp/production/dashboard | ~156줄 | `apps/erp_production_page.py` | /erp/production/dashboard |
| **ERP-SLIM-10** | construction_dashboard 분리 | /erp/construction/dashboard | ~130줄 | `apps/erp_construction_page.py` | /erp/construction/dashboard |

### Phase C: erp_bp 정리

| ID | 작업 | 목표 |
|----|------|------|
| **ERP-SLIM-11** | erp_bp 역할 최소화 | 공통 필터·redirect·허브 또는 삭제(전부 분리 시) |
| **ERP-SLIM-12** | app.py Blueprint 등록 | 신규 erp_*_bp 등록 |

---

## 3. 세부 실행 가이드

### ERP-SLIM-2: services/erp_display.py (우선)

- **이동 함수**: `_ensure_dict`, `apply_erp_display_fields`, `_erp_get_urgent_flag`, `_erp_get_stage`, `_erp_has_media`, `_erp_alerts`, `_sales_domain_fallback_match`, `_can_modify_sales_domain`, `_drawing_status_label`, `_drawing_next_action_text`, `apply_erp_display_fields_to_orders`
- **의존성**: Order, get_db, services.erp_policy, sessions 등
- **re-export**: app.py와 apps.erp에서 `apply_erp_display_fields_to_orders`, `can_edit_erp` 사용처 확인 후 import 경로 수정

### ERP-SLIM-4: erp_dashboard 분리

- **파일**: `apps/erp_dashboard.py`
- **라우트**: `@erp_dashboard_bp.route('/erp/dashboard')` 또는 prefix `/erp`로 등록
- **템플릿**: `erp_dashboard.html` (기존)
- **url_for**: `erp_dashboard.erp_dashboard` → `url_for('erp_dashboard.erp_dashboard')` 등 전면 수정 필요

### 템플릿 필터 (ERP-SLIM-1)

- Flask Blueprint의 `app_template_filter`는 해당 Blueprint에 등록된 라우트의 템플릿에서만 사용 가능.
- 대시보드가 분리되면 각 Blueprint에 필터를 등록하거나, app에 공통 필터로 등록.
- **권장**: `services/erp_template_filters.py`에 함수 정의, 각 Blueprint 또는 app에서 `app.add_template_filter(fn, 'name')` 로 등록.

---

## 4. 예상 erp.py 최종 구조 (~500줄)

```
1. imports, Blueprint 생성 (~30줄)
2. can_edit_erp, erp_edit_required (또는 services에서 import) (~10줄)
3. 템플릿 필터 등록 (services에서 import 후 register) (~15줄)
4. erp_bp.route 남은 것 없음 → erp_bp 삭제 또는 허브용 1개
5. app.py: erp_dashboard_bp, erp_drawing_workbench_bp 등 7개 등록
```

**목표**: erp.py를 **erp 허브** 또는 **완전 제거**하여, 대시보드별 Blueprint만 app.py에 등록.

---

## 5. 검증 체크리스트 (매 ERP-SLIM 완료 후)

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] `python app.py` → 서버 기동
- [ ] 해당 대시보드 페이지 수동 접근 (200 OK)
- [ ] url_for 엔드포인트 수정 (예: `erp_dashboard.erp_dashboard`)
- [ ] ReadLints (신규/수정 파일)
- [ ] TASK_REGISTRY 갱신

---

## 6. 진행 상태 (갱신용)

| ID | 상태 | 완료일 |
|----|------|--------|
| ERP-SLIM-1 | 완료 | 2026-02-18 |
| ERP-SLIM-2 | 완료 | 2026-02-18 |
| ERP-SLIM-3 | 완료 | 2026-02-18 |
| ERP-SLIM-4 | 완료 | 2026-02-18 |
| ERP-SLIM-5 | 완료 | 2026-02-18 |
| ERP-SLIM-6 | 완료 | 2026-02-18 |
| ERP-SLIM-7 | 완료 | 2026-02-18 |
| ERP-SLIM-8 | 완료 | 2026-02-18 |
| ERP-SLIM-9 | 완료 | 2026-02-18 |
| ERP-SLIM-10 | 완료 | 2026-02-18 |
| ERP-SLIM-11 | 완료 | 2026-02-18 |
| ERP-SLIM-12 | 완료 | 2026-02-18 |

---

## 7. 활용 자원

| 구분 | 자원 | 용도 |
|------|------|------|
| Rules | 02-architecture, 06-safe-changes | Blueprint 패턴, 한 번에 1개 모듈 |
| Agents | python-backend, code-reviewer | 구현·검증 |
| 문서 | GDM_EXECUTION_PLAN.md, 2026-02-16-app-slim-down.md | 참조 |
