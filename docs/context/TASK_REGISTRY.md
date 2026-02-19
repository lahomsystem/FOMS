# Task Registry

> AI 세션 간 작업 추적. 세션이 바뀌어도 진행 상황을 유지합니다.

## 활성 작업

| ID | 상태 | 설명 | 시작일 | 최종 업데이트 |
|----|------|------|--------|-------------|
| CLEAN-001 | 완료 | docs 중복·폐기 문서 점검 (파일 정리 계획표) | 2026-02-18 | 2026-02-18 |
| CLEAN-002 | 완료 | .cursor/artifacts 미사용/중복 아티팩트 점검 | 2026-02-18 | 2026-02-18 |
| CLEAN-003 | 완료 | .gitignore 정리 (*.tmp, *.bak 추가) | 2026-02-18 | 2026-02-18 |
| CLEAN-004 | 완료 | scripts/ 사용처 확인 (db_admin, incident_smoke 사용 중) | 2026-02-18 | 2026-02-18 |
| CLEAN-005 | 완료 | 루트·임시 파일 점검 (해당 없음) | 2026-02-18 | 2026-02-18 |
| NEXT-001 | 완료 | order_pages.py에서 edit_order 분리 → apps/order_edit.py, order_edit_bp 등록·템플릿 url_for 일괄 변경 | 2026-02-18 | 2026-02-18 |
| NEXT-002 PART-003 | 완료 | erp_construction_dashboard.html partial 분리 (styles, filters_grid, modals, scripts) | 2026-02-19 | 2026-02-19 |
| NEXT-002 PART-004 | 완료 | erp_production_dashboard.html partial 분리 (styles, filters_grid, modals, scripts) | 2026-02-19 | 2026-02-19 |
| NEXT-002 PART-005 | 완료 | calculator.html partial 분리 (wdcalculator/partials/wdcalculator_*.html) | 2026-02-18 | 2026-02-18 |
| NEXT-003 | 완료 | pytest 도입 (tests/, conftest.py, test_app_smoke.py, test_api_orders.py — 7 passed) | 2026-02-19 | 2026-02-19 |
| NEXT-004 | 완료 | db_admin 비밀번호 환경변수화 (FOMS_ADMIN_DEFAULT_PASSWORD) | 2026-02-19 | 2026-02-19 |
| SLIM-035 | 보류 | app.py 300줄 이하 (일단 중단) | - | 2026-02-18 |
| ERP-SLIM-10 | 완료 | 시공 대시보드 → apps/erp_construction_page.py (erp_construction_page_bp) | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-9 | 완료 | 생산 대시보드 → apps/erp_production_page.py (erp_production_page_bp) | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-8 | 완료 | AS 대시보드 → apps/erp_as_page.py (erp_as_page_bp) | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-7 | 완료 | 출고 대시보드 → apps/erp_shipment_page.py (erp_shipment_page_bp) | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-6 | 완료 | 실측 대시보드 → apps/erp_measurement_dashboard.py (erp_measurement_dashboard_bp) | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-5 | 완료 | erp_drawing_workbench → apps/erp_drawing_workbench.py (erp_drawing_workbench_bp) | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-4 | 완료 | erp_dashboard → apps/erp_dashboard.py (erp_dashboard_bp) | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-3 | 완료 | can_edit_erp, erp_edit_required → services/erp_permissions.py | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-1 | 완료 | 템플릿 필터 6개 → services/erp_template_filters.py | 2026-02-18 | 2026-02-18 |
| ERP-SLIM-2 | 완료 | display 헬퍼 → services/erp_display.py | 2026-02-18 | 2026-02-18 |
| SLIM-025 | 완료 | app.py 슬림다운 테스크 계획표 작성 (2026-02-18-app-slim-task-plan.md) | 2026-02-18 | 2026-02-18 |
| SLIM-024 | 완료 | erp.py 분리 상세 계획 작성 (2026-02-17-erp-split-plan.md) | 2026-02-17 | 2026-02-17 |
| SLIM-023 | 완료 | index+add_order → order_pages_bp, order_display_utils | 2026-02-17 | 2026-02-17 |
| SLIM-022 | 완료 | /api/orders 캘린더 API → orders_bp (FullCalendar 이벤트) | 2026-02-17 | 2026-02-17 |
| SLIM-021 | 완료 | 주소/경로 API 4개 → erp_map_bp 통합 (calculate_route, address_suggestions, add_address_learning, validate_address) | 2026-02-17 | 2026-02-17 |
| SLIM-020 | 완료 | structured API → apps/api/erp_orders_structured.py (structured GET/PUT, parse-text, erp/draft) | 2026-02-17 | 2026-02-17 |
| SLIM-019 | 완료 | blueprint API → apps/api/erp_orders_blueprint.py (upload/get/delete) | 2026-02-17 | 2026-02-17 |
| SLIM-018 | 완료 | Quest API → apps/api/quest.py (quest GET/POST/approve/status) | 2026-02-17 | 2026-02-17 |
| SLIM-017 | 완료 | Phase 4-5h(4): confirm/customer → erp_orders_confirm_bp | 2026-02-17 | 2026-02-17 |
| SLIM-016 | 완료 | Phase 4-5h(3): drawing/request-revision, drawing/complete-revision → erp_orders_revision_bp 확장 | 2026-02-17 | 2026-02-17 |
| SLIM-015 | 완료 | Phase 4-5h(2): AS API 3개 → erp_orders_as_bp (as/start, as/complete, as/schedule) | 2026-02-17 | 2026-02-17 |
| SLIM-014 | 완료 | Phase 4-5h(1): CS 완료 API → erp_orders_cs_bp (cs/complete) | 2026-02-17 | 2026-02-17 |
| SLIM-013 | 완료 | Phase 4-5g: 시공 API → erp_orders_construction_bp (construction/start, construction/complete, construction/fail) | 2026-02-17 | 2026-02-17 |
| SLIM-012 | 완료 | Phase 4-5f: 생산 API → erp_orders_production_bp (production/start, production/complete) | 2026-02-17 | 2026-02-17 |
| SLIM-011 | 완료 | Phase 4-5e: 도면 담당자 지정/확정 API → erp_orders_draftsman_bp (assign-draftsman, batch-assign-draftsman, confirm-drawing-receipt) | 2026-02-17 | 2026-02-17 |
| SLIM-010 | 완료 | Phase 4-5d: 도면 수정 요청/체크 API → erp_orders_revision_bp (request-revision, request-revision-check) | 2026-02-17 | 2026-02-17 |
| SLIM-009 | 완료 | Phase 4-5c: 도면 창구 업로드 → erp_orders_drawing_bp (drawing-gateway-upload) | 2026-02-17 | 2026-02-17 |
| SLIM-008 | 완료 | Phase 4-5b: 도면 전달/취소 API → apps/api/erp_orders_drawing.py (transfer-drawing, cancel-transfer) | 2026-02-17 | 2026-02-17 |
| SLIM-007 | 완료 | Phase 4-5a: 주문 Quick API → apps/api/erp_orders_quick.py (quick-search, quick-info, quick-status) | 2026-02-17 | 2026-02-17 |
| SLIM-006 | 완료 | Phase 4-4: 지도/주소/유저 API → apps/api/erp_map.py 분리 (map_data, users, generate_map, update_address) | 2026-02-17 | 2026-02-17 |
| SLIM-005 | 완료 | Phase 4-3: 실측 API → apps/api/erp_measurement.py 분리 (measurement/update, measurement/route) | 2026-02-17 | 2026-02-17 |
| SLIM-002 | 완료 | feature/erp-beta-rename-to-erp → deploy 머지·푸시 | 2026-02-16 | 2026-02-16 |
| SLIM-003 | 완료 | Phase 4 준비: apps/erp.py 구조 파악 및 1차 분리 후보 선정 | 2026-02-16 | 2026-02-16 |
| SLIM-004 | 완료 | Phase 4-1: 알림 API → apps/api/notifications.py 분리 (feature/erp-split-notifications) | 2026-02-16 | 2026-02-16 |
| SLIM-001 | 완료 | app 슬림다운 Phase 1: services/ 도입 (1-1~1-4 완료) | 2026-02-16 | 2026-02-16 |

## 완료된 작업

| ID | 설명 | 완료일 |
|----|------|--------|
| CTX-001 | Cursor Rules 8개 생성 | 2026-02-15 |
| CTX-002 | MCP 6개 최적화 | 2026-02-15 |
| CTX-003 | Skills 4개 설치 | 2026-02-16 |
| CTX-004 | Subagents 6개 생성 | 2026-02-16 |
| CTX-005 | Context Engineering 시스템 구축 | 2026-02-16 |
| SLIM-001a | services/ 폴더 생성 + business_calendar 이동 | 2026-02-16 |
| SLIM-001b | erp_policy → services/erp_policy.py | 2026-02-16 |
| SLIM-001c | storage → services/storage.py | 2026-02-16 |

## 작업 등록 규칙
- 새 작업 시작 시 여기에 등록
- 상태: `진행중`, `대기`, `완료`, `취소`
- 세션 종료 시 자동 업데이트 (Hook)
