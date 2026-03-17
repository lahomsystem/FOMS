# AI 작업 이력
> 최근 20개만 유지. 이전 기록은 git log 참조.
> 이 파일은 Cursor Hook(session_stop) 또는 Antigravity Workflow에 의해 자동 업데이트됩니다.

| 날짜 | 작업 | 수정 파일 | 커밋 |
|------|------|-----------|------|
| 2026-03-17 | [Phase 2.2] ERP 대시보드 및 생산 대시보드 파이썬 필터를 DB 검색으로 전환 (`.limit` 복원 페이지네이션 포함) | apps/erp_dashboard.py, apps/erp_production_page.py, templates/partials/erp_production_filters_grid.html | - |
| 2026-03-17 | [Phase 2.1] ERP AS / Main / Production 페이지네이션 구조 적용 (Python->DB) | apps/erp_as_page.py, templates/erp_as_dashboard.html, apps/erp_dashboard.py 등 | - |
| 2026-03-17 | [Phase 1.2] 실측 패널 자동입력 롤백 및 측정 지연시간 분석 로깅 추가 | templates/partials/erp_beta_tab.html, templates/partials/erp_beta_js.html, apps/api/erp_orders_structured.py | - |
| 2026-03-17 | [Phase 1.1] Save 병목 및 DB Lock 제거 (psycogreen 패치, system_build_step 불필요 쿼리 통합) | app.py, requirements.txt, apps/api/erp_orders_structured.py, apps/api/orders.py, apps/auth.py | - |
| 2026-03-17 | 세션 자동 기록 | commit_msg.txt, erp_display.py, erp_as_dashboard.html 외 2개 | c82a3fc |
| 2026-03-16 | 세션 자동 기록 | commit_msg.txt, erp_display.py, erp_as_dashboard.html 외 2개 | 13fc566 |
| 2026-03-15 | 세션 자동 기록 | diagnose_measurement_date_missing.py, map_snapshot.py, commit_msg.txt 외 2개 | 6c44185 |
| 2026-03-15 | 세션 자동 기록 | map_snapshot.py, diagnose_measurement_date_missing.py, commit_msg.txt 외 2개 | 6c44185 |
| 2026-03-15 | 세션 자동 기록 | commit_msg.txt, order_date_sync.py, map_snapshot.py 외 2개 | 6c44185 |
| 2026-03-15 | 세션 자동 기록 | order_date_sync.py, map_snapshot.py, erp_map.py 외 2개 | df0563e |
| 2026-03-15 | 세션 자동 기록 | diagnose_order_2662_map.py, commit_msg.txt, map_snapshot.py 외 2개 | df0563e |
| 2026-03-15 | 세션 자동 기록 | commit_msg.txt, map_snapshot.py, erp_map.py 외 2개 | df0563e |
| 2026-03-15 | 세션 자동 기록 | map_snapshot.py, erp_map.py, commit_msg.txt 외 2개 | 131cda5 |
| 2026-03-15 | 세션 자동 기록 | commit_msg.txt, map_snapshot.py, c__Users_USER_AppData_Roaming_Cursor_User_workspaceStorage_533155fc540ce8fdfccbd97527acfc34_images_image-e20e6e15-5c5c-40b2-9910-a8af78fbf7cc.png 외 2개 | 131cda5 |
| 2026-03-15 | 세션 자동 기록 | map_snapshot.py, c__Users_USER_AppData_Roaming_Cursor_User_workspaceStorage_533155fc540ce8fdfccbd97527acfc34_images_image-e20e6e15-5c5c-40b2-9910-a8af78fbf7cc.png, map_view.html 외 2개 | 12c2f6d |
| 2026-03-15 | 세션 자동 기록 | c__Users_USER_AppData_Roaming_Cursor_User_workspaceStorage_533155fc540ce8fdfccbd97527acfc34_images_image-e20e6e15-5c5c-40b2-9910-a8af78fbf7cc.png, map_view.html, erp_map.py 외 2개 | 12c2f6d |
| 2026-03-15 | 세션 자동 기록 | map_view.html, erp_map.py, erp_measurement.py 외 2개 | 12c2f6d |
| 2026-03-15 | 실측 지도 재구현 Spec Phase 1~6 + reset_order_geocode 확대 적용 | erp_map.py, erp_measurement.py, erp_orders_structured.py, order_edit.py, map_view.html, map_snapshot.py, order_geocode.py | - |

### 2026-03-17
- [ERP Beta] 실측 패널(dropdown) 항목 정렬 개선 (가까운 주소: 시/군/구 기준 정렬 후 시간 정렬)
- [ERP Beta] 실측 패널에 시간 정보 명시적 표시 완료 (시간미정 분리 명기)
