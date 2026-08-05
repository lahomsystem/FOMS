# AS 미완료 지도 — Progress Ledger

플랜: `docs/plans/2026-08-05-as-incomplete-map-plan.md`

| Task | 내용 | 상태 | 검증 |
|---|---|---|---|
| T1 | 백엔드 dashboard=as 분기 + 쿼리 SSOT | DONE | test_as_map_snapshot.py 5 passed + APP_OK |
| T2 | 색상 SSOT + folium 파리티 + ?v 범프 | DONE | test_foms_map_generator 9 passed(AS 색 케이스 포함), ?v=20260805a 단일 핀 |
| T3 | map_view.html as 분기 | DONE | 렌더 스모크(test_map_view_renders_with_as_dashboard_param) green |
| T4 | 진입점 redirect dashboard=as+bucket | DONE | redirect Location 테스트 green, as_dashboard 계열 96 passed |
| T5 | 스테이징 QA (gstack browse) | PENDING | - |
| T6 | AI_STATUS·커밋·push·CI green | PENDING | - |

## 메모
- 운영 실측치(2026-08-05): 미완료 52건 / 좌표없음 9 / 지오실패 0 / 지방 0.
- 사용자 확정(2026-08-05): 새 화면 이동 방식·버킷 필터 포함·상세는 /erp/as?focus_order 새 탭.
- namespace 계약(`foms_namespace_surface_tests`) __all__에 신규 함수 반영.
- AS 마커는 담당자 팔레트 대신 상태색(use_manager_colors=False) — 실측 담당자 설정과 무관 모집단.
