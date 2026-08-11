# AI 작업 이력
> 최근 20개만 유지. 이전 기록은 git log 참조.
> 이 파일은 Cursor Hook(session_stop) 또는 Antigravity Workflow에 의해 자동 업데이트됩니다.

| 날짜 | 작업 | 수정 파일 | 커밋 |
|------|------|-----------|------|
| 2026-08-10 | 주문 삭제·복원 대시보드 즉시 반영(운영 #4717): 삭제 경로 3곳(단건 delete·벌크 삭제 API·legacy bulk_action)에 대시보드 read-slice 캐시 무효화가 없어 TTL 300초 동안 실측 날짜별 집계에 삭제된 주문이 잔존(패널/리스트 캐시 키가 달라 좌우 숫자 불일치). helper `invalidate_dashboard_caches_after_delete_transition`(broad 7 family + AS 추천 캐시)를 commit 직후 호출, 계약 테스트 6종 추가. 스테이징 E2E 삭제 즉시 집계 2→1·복원 복귀 PASS, CI 4/4 green, production 승격 PR #72 머지(`76b9086c`) | foms/services/common/dashboard_cache.py, foms/web/orders/{trash,listing}.py, foms/api/orders/status.py, tests/domains/{test_delete_trash,test_delete_bulk,test_dashboard_cache_invalidation_scope}.py | aa0b788e |
| 2026-08-10 | 채널톡 AS PUSH 신설(AS 접수 내용+AS 첨부 → AS방 230351): ERP 탭·모바일 PUSH 선택 시트·AS 대시보드 3경로, 본문 조립 서버 SSOT(channel_as_message.py)로 통일 + 모바일 선택 시트 풀스크린 눌림 근본 수정(erp-pro 전역 !important 특이도) + 시공 대시보드 캐시 키 정규화·숫자판 모집단 일치(‘긴급 발주’=시공 기준) + 진단 헤더 2종 신설(EPT-B7-PHASES·DASH-SLICES). 실측: 요약 재계산 추정 88ms vs 실측 27ms — 추정 기반 SQL 이관 중단 판단. production 승격 PR #64·#65·#67·#68 | foms/services/channel_as_message.py, foms/api/channel/channel_integration.py, foms/services/common/{dashboard_cache,ept_b7_profile}.py, foms/web/construction/dashboard.py, static/js/cs/as-dashboard.js, templates/orders/partials/erp_channel_push_picker_modal.html 외 | 340b0064 |
| 2026-08-10 | 세션 자동 기록 | dashboard_cache.py, layout_scripts.html, photo-capture.js 외 2개 | f94f534d |
| 2026-08-10 | 세션 자동 기록 | dashboard.py, test_construction_dashboard_cache_key_sharing.py, test_as_dashboard_attachment_modal.py 외 2개 | 2dc54772 |
| 2026-08-09 | 세션 자동 기록 | tablet-measure-form.js, erp-order-shared.js, test_erp_order_shared_form_scripts.py 외 2개 | 45c53c90 |
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
