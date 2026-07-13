# AI 작업 이력
> 최근 20개만 유지. 이전 기록은 git log 참조.
> 이 파일은 Cursor Hook(session_stop) 또는 Antigravity Workflow에 의해 자동 업데이트됩니다.

| 날짜 | 작업 | 수정 파일 | 커밋 |
|------|------|-----------|------|
| 2026-07-13 | 태블릿 T7: PC 크롬 소거(대시보드 pcbar/5타일·시공·출고 컬럼)+계산기 접힘+마법사 나가기+보류/현금영수증 API+레일 벨/아바타+long-press 벌크 | tablet_dashboard_topbar, foms-tablet-*.css, tablet-bulk-select.js, production/orders.py, cs/dashboard.py 외 | c6a278f6·4e37eb66 |
| 2026-07-13 | 태블릿 T6 목업 프레임 완전체 — 탭별 KPI·필터·전용 시트 6종(정산 발행·배정·관리·워크모드)·밀도 토글·CSV + 병치 대조 결함 4건 봉합 | tablet_*_sheet 라우트/템플릿 6종, tablet-side-sheet.js(URL 계약), tablet-density-toggle.js, foms-tablet-construction.css 외 | 9213f7aa~2ee1fa16 |
| 2026-07-12 | 태블릿 T5: 탭별 목업 표면(도면 갤러리·완료 금액 그리드·AS 전후 대조·시트 파이프라인·계산기 표피) + JS 캐시체인·가드 자충돌·perf 캡 봉합 | tablet_gallery/completion_grid/as_compare body, foms-tablet-*.css, tablet-side-sheet.js, completion_dashboard.py, as_dashboard_display.py, perf_budgets.json | eb354b29~aa63d491 |
| 2026-07-12 | 모바일 실기능 B라운드 완주(Wave1~3) — 통화기록·공정스텝·패킹·실측캡처·시공게이트·QR·sync큐 + perf 예산 재시드 | foms/api/{orders,production,shipment,measurement,construction}, foms-write/qr-scan.js, perf_budgets.json | 351f1276~3958fa91 |
| 2026-07-12 | 태블릿 모드 완결: split 퇴출(fine/none 창 전용)+fragment 레일 동기(tablet-rail-nav.js)+foms_split_enabled v2 전용+AS·이력 시트+출고 게이트 통합 | foms-split-view/shell/bridge.css, layout_nav/head, tablet-rail-nav.js, tablet-side-sheet.js, foms-shipment-mobile.css, context_processors.py, orders/dashboard.py | f4942486·a796f23f |
| 2026-07-12 | 태블릿 가로 크롬 교체+전역 72px 레일(전 /erp) + AS 카메라 바 v3 누출 봉합 | 13-foms-shell-bridge.css, foms-tablet-rail.css/html, layout_nav/layout_head, foms_split_view.py, context_processors.py, as-dashboard-body.css, test_tablet_rail_contract.py | 1c8858fe·6583cfba |
| 2026-07-12 | v2에 v3 기능 이식 완결(A1~A8) — CS 히어로·퀘스트 칩·상태 필터 칩·생산 3버킷·실측/시공 히어로·헤더 정렬 fix | dashboard_mobile_v2_body, mobile_queue/list, queue_card v1·v2, dashboard_filters, foms-v2-*.css | 147883bc·a13dfc57·645190f2·2545c595 |
| 2026-07-11 | v3 라이트 테마·QA 7결함·디자인 리뷰·360° 상세 직행 | foms-mobile-v3.css, partials/v3/*, layout_head.html, test_shell_v3_contract.py | 04eab6e6·a1704f63·cedeec24·a1799538 |
| 2026-07-11 | 모바일 v3 셸(Field OS) C1~C6 — variant 판정 SSOT·페르소나 홈 6종·주문360°·계약 테스트 | feature_flags.py, context_processors.py, templates/partials/v3/*, static/{css,js}/v3/*, order_timeline_v3.py, test_shell_v3_contract.py | deb2ed9b·62f3e3cd·cfdfe65c·02b0366a |
| 2026-07-09 | 세션 자동 기록 | pr_body_production.txt, commit_msg.txt, test_erp_order_shared_form_scripts.py 외 2개 | 08f6a620 |
| 2026-07-09 | 세션 자동 기록 | commit_msg.txt, test_erp_order_shared_form_scripts.py, 04-filter-table-badges-buttons.css 외 2개 | 08f6a620 |
| 2026-07-09 | 세션 자동 기록 | ci_watch.py, test_post_task_ci_gate.py, test_ci_watch.py 외 2개 | bf9fc1f2 |
| 2026-07-09 | 세션 자동 기록 | commit_msg.txt, test_erp_order_edit_mobile_form.py, test_erp_order_shared_form_scripts.py 외 2개 | bf9fc1f2 |
| 2026-07-09 | 세션 자동 기록 | test_post_push_hook.py, test_ci_watch.py, CLAUDE.md 외 2개 | bbb065aa |
| 2026-07-07 | 세션 자동 기록 | wdcalculator_scripts.html, wdcalculator-entry.js, wdcalculator_scripts_config.html | e67c643f |
| 2026-07-07 | 세션 자동 기록 | erp_order_tab_mobile.html, test_erp_order_shared_form_scripts.py, erp-order-shared.js 외 2개 | be5ab4f1 |
| 2026-07-06 | 세션 자동 기록 | channel_policy.py, test_channel_integration_smoke.py, test_channel_dispatch.py 외 1개 | 4b3513b8 |
| 2026-07-04 | 세션 자동 기록 | commit_msg_docs.txt, commit_msg_mytasks.txt | 8d9311e6 |
| 2026-07-03 | 세션 자동 기록 | _merge_msg_prod.txt, commit_msg.txt, map_view.html 외 2개 | 21e38f32 |
| 2026-07-03 | 세션 자동 기록 | commit_msg.txt, map_view.html, _commit_msg_estimate_push.txt 외 2개 | 21e38f32 |
| 2026-07-03 | 세션 자동 기록 | test_erp_order_shared_form_scripts.py, erp_order_js.html, test_channel_integration_smoke.py 외 2개 | dd79672b |
| 2026-07-03 | 세션 자동 기록 | test_erp_orders_structured_put.py, test_erp_order_shared_form_scripts.py, erp_order_js.html | dd79672b |
| 2026-07-02 | 세션 자동 기록 | commit_msg_badge_css_fix.txt, test_erp_measurement_mobile_render.py, erp-pro.css 외 2개 | 294635d8 |
| 2026-07-02 | 세션 자동 기록 | commit_msg_segmented_counts.txt, test_erp_measurement_mobile_render.py, test_erp_measurement_manager_sync.py 외 2개 | ff9e0294 |
| 2026-07-02 | 세션 자동 기록 | commit_msg.txt, test_erp_order_shared_form_scripts.py, estimate-preview.js 외 2개 | a24dff5c |
| 2026-07-02 | 세션 자동 기록 | test_erp_order_shared_form_scripts.py, estimate-preview.js, erp_order_js.html 외 2개 | 3471502a |
| 2026-07-02 | 세션 자동 기록 | measurement_read_model.py, commit_msg_regional_measurement.txt, dashboard.py 외 2개 | 3471502a |
| 2026-07-02 | 세션 자동 기록 | commit_msg.txt, test_estimate_service.py, estimate_defaults.py 외 1개 | 0fa05f76 |
| 2026-07-02 | 세션 자동 기록 | test_estimate_service.py, estimate_defaults.py, commit_msg.txt 외 1개 | c40e2ad1 |
