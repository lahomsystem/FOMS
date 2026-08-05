# AS 미완료 지도 — 실행 플랜 (2026-08-05)

스펙: `docs/specs/2026-08-05-as-incomplete-map-design.md`
원장: `docs/plans/2026-08-05-as-incomplete-map-ledger.md`
브랜치: `deploy` (production 승격은 사용자 별도 요청 시 cherry-pick)

## T1. 백엔드 — dashboard=as 분기 + 쿼리 SSOT
- `foms/services/map_snapshot.py`: `build_as_incomplete_map_query()` — active_filter + `incomplete_non_sales_condition`(as_dashboard_read_model SSOT), 날짜 무관, is_regional 포함, limit 500.
- 스냅샷 빌더 일반화(kind='as') 또는 동일 DTO AS 빌더 — `{orders, markers, summary}` 계약 유지.
- `foms/api/erp_map.py` `/api/map_data`: `dashboard=='as'` 분기 + 좌표 결측 pending 마킹·RQ enqueue(measurement 패턴).
- 완료 기준: `pytest tests/domains/test_map_snapshot.py tests/domains/test_map_view_manager_contract.py -q` green + 신규 테스트(미완료 SSOT 모집단=탭 카운트 쿼리 일치, sales_delivery 제외, 지방 포함, AS_COMPLETED 완료일공란 포함) green + `APP_OK`.

## T2. 색상 SSOT + folium 파리티
- `map_generator._get_status_color`에 AS 3종 추가 (`AS_RECEIVED #dc3545`, `AS #fd7e14`, `AS_COMPLETED #6c757d`).
- `map-view-kakao.js STATUS_COLORS` 동기 포팅. `/api/generate_map` as 분기 파리티.
- JS 수정 → `?v` 범프 + 참조 핀 전수 grep.
- 완료 기준: `pytest tests/domains/test_foms_map_generator.py -q` green(색상 케이스 추가), grep으로 구버전 `?v` 잔존 0건.

## T3. 프론트 — map_view.html as 분기
- `dashboard=='as'`: 날짜·상태 필터 숨김, 타이틀 "AS 미완료 지도", 총건수·잘림 표시, 상태 라벨 `AS: 'AS처리'` 추가, 팝업 상세 링크 `/erp/as?focus_order=` 분기.
- 완료 기준: 로컬 서버에서 `/map_view?dashboard=as` 응답 200 + folium 폴백 DOM에 마커 데이터 존재(로컬은 kakao 401 → folium 경로 검증), 콘솔 에러 0.

## T4. 진입점 redirect
- `as_dashboard.py` open_map redirect → `dashboard='as'` (date/status 전달 제거).
- 완료 기준: redirect Location 검증 테스트 green.

## T5. 스테이징 QA (gstack browse, lahom-dev)
- `/erp/as?tab=incomplete` 지도 버튼 → kakao 지도 로드, 마커 수 = 미완료 탭 총건수 일치, 좌표 결측 건 폴링 해소, 팝업·중복그룹 동작, 콘솔/네트워크 에러 0.
- 완료 기준: 위 체크 전부 통과 스크린샷/로그.

## T6. 마무리
- `docs/AI_STATUS.md` 갱신, UTF-8 파일 경유 한글 커밋, pre_push_smoke exit 0, deploy push, CI는 `gh run list`로 해당 SHA 전 워크플로 green 확인.
