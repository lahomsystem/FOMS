# AI 작업 이력
> 최근 20개만 유지. 이전 기록은 git log 참조.
> 이 파일은 Cursor Hook(session_stop) 또는 Antigravity Workflow에 의해 자동 업데이트됩니다.

| 날짜 | 작업 | 수정 파일 | 커밋 |
|------|------|-----------|------|
| 2026-08-13 | AS fragment dTTFB 예산 초과(181 > 168) 근본 해소: 페이로드는 wire 51K 고정이라 코드 회귀가 안 보였음 → 스테이징 실측 분해로 render 17ms vs 헤더 106ms 확인(압축 무죄 — identity 99ms), EPT-B7 `phase()` 계측으로 지출처 확정(tab_counts=27·list_query=21·row_display=49 중 rd_sanitize 18/rd_timeline 17). 수정 2건: ① 같은 모집단을 세던 `_count_cases` 2회를 SUM(CASE) 단일 스캔으로 병합('total'은 'incomplete' 재사용) ② 순수 함수 `sanitize_as_content_html` LRU 메모이즈(2048칸·입력 8KB 상한, 초과는 캐시 우회) — 행 100 × 2필드 BeautifulSoup 재파싱 제거. 검증: 스테이징 웜 실측 rd_sanitize 18→0·tab_counts 27→15·dHDR 129→96, CI perf-gate 2런 연속 AS dTTFB 96 PASS, AS 도메인 663 + pre_push_smoke 322 green. 예산 168 불변 유지 | foms/services/as_content_safety.py, foms/services/as_dashboard_read_model.py, foms/services/as_dashboard_display.py, foms/web/cs/as_dashboard.py, tests/domains/test_as_content_safety.py | a3bdcf9c·cb1834f5·a4f15f97·0fc3ac24 |
| 2026-07-27 | AS 대시보드 타임라인 개편(T1~T16): as_log append-only 타임라인 + 무상/유상 2단계 판정, 구 contenteditable 2탭 에디터 퇴역, PC/모바일/태블릿 3표면 매크로 SSOT, 시스템 이벤트 실흐름 배선, 검색 as_log 확장, sanitize 미종결 태그 XSS 봉합·2단 상한, lost-update/clobber 서버 보존 가드 — 태스크별 리뷰 루프 + 최종 whole-branch 리뷰 + pre_push_smoke exit 0(253 passed) | foms/services/orders/as_log.py, foms/api/cs/as_orders.py, templates/cs/partials/as_card_macros.html, static/js/cs/as-dashboard.js, foms/services/as_dashboard_display.py 외 | 6473d3b3~876836e1 |
| 2026-07-27 | 세션 자동 기록 | regional_dashboard.html, test_tablet_rail_contract.py, test_tablet_as_compare_contract.py 외 2개 | abddac61 |
| 2026-07-24 | 생산 보드 5차: 필터 바 단순화 — [필터] 토글·필터 접기·상태 select 제거, 공장 select를 검색 앞, 변경 버튼 상시 노출(검색=전체 조건) — pytest 212 passed + 필터 바 렌더 동작검증 | tablet_kanban_body.html, tablet-domain-sheets.js, foms-tablet-production-kanban.css 외 | (미커밋) |
| 2026-07-24 | 생산 보드 4차: 제작 취소 깨끗한 되돌림(rework/hold 정리·제작이력 승인간주) + 라벨 인쇄 제거(통합바 1줄) + 전체화면 토글(크롬 접기·복원버튼·실측 캡90) — pytest 212 passed + Playwright 전체화면·F-1 실측검증, 리뷰 Critical/Major 0 | production/orders.py, production_dashboard_display.py, tablet_kanban_body.html, foms-tablet-production-kanban.css, tablet-domain-sheets.js 외 | (미커밋) |
| 2026-07-24 | 생산 보드 3차: 제작취소 버튼 nowrap + 고정 바 재배치(KPI 5열·pcbar통합·필터접기·열캡 실측265) + 완료 이력(hold_history 보존·무채 배지) — pytest 200 passed + Playwright 재배치·이력 실측검증, 리뷰 Major 1+Minor 3 반영 | production/orders.py, production_dashboard_display.py, tablet_kanban_body.html, tablet_sheet.html, filters_grid.html, foms-tablet-production-kanban.css, tablet-domain-sheets.js 외 | (미커밋) |
| 2026-07-24 | 생산 보드 2차 P4~P8(보류 해제 confirm·사유 가시성 스트립·제작/완료 취소 rollback·보류 KPI/D+n/임박경고·PC 배지) — pytest 187 passed + Playwright 태블릿·PC 21/21 PASS | production/orders.py, production_dashboard_display.py, dashboard.py, tablet_kanban_body.html, tablet_sheet.html, filters_grid.html, tablet-domain-sheets.js 외 | (미커밋) |
| 2026-07-24 | 생산 보드 프로세스 가드 3종(전이 전제조건·보류 게이트·수정 제작 rework) — 스펙 docs/plans/2026-07-24-production-process-guards-plan.md, pytest 159 passed + Playwright 태블릿 28/28 PASS | production/orders.py, dashboard.py, tablet_sheet.html, tablet_kanban_body.html, tablet-production-kanban.js, tablet-domain-sheets.js 외 | (미커밋) |
| 2026-07-23 | 세션 자동 기록 | erp-order-shared.js, test_erp_order_edit_mobile_form.py, test_p1_mockup_structure.py 외 2개 | a8e3b168 |
| 2026-07-23 | 세션 자동 기록 | test_p1_mockup_structure.py, test_tablet_t2_contract.py, test_erp_spec_calc_followup.py 외 2개 | 3c328837 |
| 2026-07-23 | 세션 자동 기록 | test_tablet_t2_contract.py, test_p1_mockup_structure.py, test_erp_spec_calc_followup.py 외 2개 | 31f05379 |
| 2026-07-23 | 세션 자동 기록 | erp_order_tab_mobile.html, test_erp_order_edit_mobile_form.py, foms-form-field.css 외 2개 | 31f05379 |
| 2026-07-23 | 세션 자동 기록 | test_erp_order_edit_mobile_form.py, test_erp_order_shared_form_scripts.py, test_erp_spec_calc_followup.py 외 2개 | 79c2d9a2 |
| 2026-07-23 | 세션 자동 기록 | test_erp_order_edit_mobile_form.py, wizard_shell.html, foms-mobile-surfaces.css 외 2개 | 79c2d9a2 |
| 2026-07-23 | 세션 자동 기록 | wizard_shell.html, layout_head.html, foms-mobile-surfaces.css 외 2개 | 9aad209a |
| 2026-07-23 | 세션 자동 기록 | mobile.css, final-review.md, erp_order_js.html 외 2개 | 78872888 |
| 2026-07-23 | 세션 자동 기록 | erp_order_js.html, wizard_shell.html, layout_head.html 외 2개 | 78872888 |
| 2026-07-23 | 세션 자동 기록 | test_p1_mockup_structure.py, test_tablet_t2_contract.py, layout_head.html 외 2개 | bae12980 |
| 2026-07-23 | 세션 자동 기록 | test_erp_spec_calc_followup.py, test_p1_mockup_structure.py, test_erp_order_shared_form_scripts.py 외 2개 | 08b7ad25 |
| 2026-07-23 | 세션 자동 기록 | test_production_kanban_full_window.py, tablet_kanban_body.html, dashboard.py 외 2개 | 08b7ad25 |
| 2026-07-23 | 세션 자동 기록 | test_wdcalculator_product_settings.py, wdcalculator_body.html, blueprint.py 외 2개 | 36f97651 |
