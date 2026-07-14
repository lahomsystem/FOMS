# AI 작업 이력
> 최근 20개만 유지. 이전 기록은 git log 참조.
> 이 파일은 Cursor Hook(session_stop) 또는 Antigravity Workflow에 의해 자동 업데이트됩니다.

| 날짜 | 작업 | 수정 파일 | 커밋 |
|------|------|-----------|------|
| 2026-07-14 | fragment 인라인 스크립트 잠복 결함 전량 수술(Y): 시공·생산·주문·이력 DOMContentLoaded 5블록+top-level 누적 6건 → per-swap/once-only 분리, orders dashboard_scripts 고아 체인 7파일 사문 제거(~2,900줄, 테스트는 라이브 트윈 재지정) | construction/production scripts.html, orders/index.html, history_dashboard_body.html, dashboard_scripts_* 삭제 7, 계약 테스트 5종 재지정 | (이번 push) |
| 2026-07-14 | 실기기 QA 5결함(X1~X5): FOUC(fragment CSS 선로드)·실측 캡처 전삭제·히어로 1줄·동선 mine+지도 오버레이·출고 수정 버튼(DOMContentLoaded→위임) | erp-shell.js, layout_scripts.html, measurement(capture 삭제·mobile_list·routes·route-strip), map_generator.py+map.py+erp_map.py, shipment_mobile_queue.html | 9fad207e |
| 2026-07-14 | 세션 자동 기록 | tablet-measure-form.js, pr_body_production.txt, perf-gate.yml 외 2개 | 9be7d305 |
| 2026-07-14 | 세션 자동 기록 | perf-gate.yml, test_staging_perf_gate.py, staging_perf_gate.py 외 2개 | 93c10b1c |
| 2026-07-14 | 세션 자동 기록 | test_erp_order_shared_form_scripts.py, erp_order_js.html, erp-order-shared.js 외 2개 | 89cf7b3d |
| 2026-07-14 | 모바일 W1~W4 소탕(사용자 4분기 확정): 실측 빠른수정 삭제(캡처 유지)·도면 요약 카드(버전·전달·메모·마법사)·출고 차량/회차 신설·CS 부재중 클라 필터 + 카카오 실도로 ETA(route-eta) | measurement/mobile_list+mobile.js, drawing workbench.py+카드/홈, shipment settings.py+display, queue_card_v2, foms-call-filter.js(신규), foms-route-strip.js, measurement/routes.py | 3efa9f40·641b80d5·9b0afb73 |
| 2026-07-14 | 세션 자동 기록 | test_tablet_t2_contract.py, layout_scripts.html, foms-tablet-measurement.css 외 2개 | f1d77e5f |
| 2026-07-14 | 세션 자동 기록 | foms_namespace_surface_tests.py, test_erp_template_filters.py, dashboard_main.html 외 2개 | f1d77e5f |
| 2026-07-14 | 세션 자동 기록 | perf_budgets.json, test_tablet_t2_contract.py, test_tablet_rail_contract.py 외 2개 | c572ba9b |
| 2026-07-14 | 세션 자동 기록 | test_tablet_t2_contract.py, test_tablet_rail_contract.py, layout_head.html 외 2개 | df1fded8 |
| 2026-07-13 | 세션 자동 기록 | tablet-side-sheet.js, foms-tablet-side-sheet.css, test_tablet_t2_contract.py 외 2개 | 46dc6180 |
| 2026-07-13 | 세션 자동 기록 | dashboard_grid.html, dashboard_read_model.py, test_tablet_rail_contract.py 외 2개 | 46dc6180 |
| 2026-07-13 | 세션 자동 기록 | calculator.html, tablet-skin.css, regional_dashboard.html 외 2개 | 56266eb3 |
| 2026-07-13 | 태블릿 T7: PC 크롬 소거(대시보드 pcbar/5타일·시공·출고 컬럼)+계산기 접힘+마법사 나가기+보류/현금영수증 API+레일 벨/아바타+long-press 벌크 | tablet_dashboard_topbar, foms-tablet-*.css, tablet-bulk-select.js, production/orders.py, cs/dashboard.py 외 | c6a278f6·4e37eb66 |
| 2026-07-13 | 태블릿 T6 목업 프레임 완전체 — 탭별 KPI·필터·전용 시트 6종(정산 발행·배정·관리·워크모드)·밀도 토글·CSV + 병치 대조 결함 4건 봉합 | tablet_*_sheet 라우트/템플릿 6종, tablet-side-sheet.js(URL 계약), tablet-density-toggle.js, foms-tablet-construction.css 외 | 9213f7aa~2ee1fa16 |
| 2026-07-12 | 태블릿 T5: 탭별 목업 표면(도면 갤러리·완료 금액 그리드·AS 전후 대조·시트 파이프라인·계산기 표피) + JS 캐시체인·가드 자충돌·perf 캡 봉합 | tablet_gallery/completion_grid/as_compare body, foms-tablet-*.css, tablet-side-sheet.js, completion_dashboard.py, as_dashboard_display.py, perf_budgets.json | eb354b29~aa63d491 |
| 2026-07-12 | 모바일 실기능 B라운드 완주(Wave1~3) — 통화기록·공정스텝·패킹·실측캡처·시공게이트·QR·sync큐 + perf 예산 재시드 | foms/api/{orders,production,shipment,measurement,construction}, foms-write/qr-scan.js, perf_budgets.json | 351f1276~3958fa91 |
| 2026-07-12 | 태블릿 모드 완결: split 퇴출(fine/none 창 전용)+fragment 레일 동기(tablet-rail-nav.js)+foms_split_enabled v2 전용+AS·이력 시트+출고 게이트 통합 | foms-split-view/shell/bridge.css, layout_nav/head, tablet-rail-nav.js, tablet-side-sheet.js, foms-shipment-mobile.css, context_processors.py, orders/dashboard.py | f4942486·a796f23f |
| 2026-07-12 | 태블릿 가로 크롬 교체+전역 72px 레일(전 /erp) + AS 카메라 바 v3 누출 봉합 | 13-foms-shell-bridge.css, foms-tablet-rail.css/html, layout_nav/layout_head, foms_split_view.py, context_processors.py, as-dashboard-body.css, test_tablet_rail_contract.py | 1c8858fe·6583cfba |
| 2026-07-12 | v2에 v3 기능 이식 완결(A1~A8) — CS 히어로·퀘스트 칩·상태 필터 칩·생산 3버킷·실측/시공 히어로·헤더 정렬 fix | dashboard_mobile_v2_body, mobile_queue/list, queue_card v1·v2, dashboard_filters, foms-v2-*.css | 147883bc·a13dfc57·645190f2·2545c595 |
| 2026-07-11 | v3 라이트 테마·QA 7결함·디자인 리뷰·360° 상세 직행 | foms-mobile-v3.css, partials/v3/*, layout_head.html, test_shell_v3_contract.py | 04eab6e6·a1704f63·cedeec24·a1799538 |
| 2026-07-11 | 모바일 v3 셸(Field OS) C1~C6 — variant 판정 SSOT·페르소나 홈 6종·주문360°·계약 테스트 | feature_flags.py, context_processors.py, templates/partials/v3/*, static/{css,js}/v3/*, order_timeline_v3.py, test_shell_v3_contract.py | deb2ed9b·62f3e3cd·cfdfe65c·02b0366a |
