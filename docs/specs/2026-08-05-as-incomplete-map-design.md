# AS 미완료 탭 전체 지도 표시 — 설계 스펙 (2026-08-05)

## 요구사항
- PC AS 탭(`/erp/as?tab=incomplete`) **미완료 탭의 모든 건**을 지도에 표시.
- UX는 실측 지도(`/map_view?dashboard=measurement`)와 **완전히 동일**: kakao pill 마커, 중복그룹 접기/펼치기, 팝업, 지오코딩 폴링, folium 폴백.

## 조사 결과 (핵심 사실)
| 사실 | 근거 |
|---|---|
| 실측 지도 = `/map_view` 공용 페이지. `regional_dashboard.html`엔 지도 없음 | `foms/api/erp_map.py:332`, `templates/measurement/map_view.html` |
| AS 대시보드에 지도 버튼 이미 존재하나 `dashboard` 파라미터 없이 redirect → **generic 분기** | `foms/web/cs/as_dashboard.py:198-201` |
| generic 분기는 `is_regional != True` 제외 + 날짜 필터 결합 → "미완료 전체" 불가 | `foms/api/erp_map.py:92-133` |
| 미완료 판정 SSOT = `incomplete_non_sales_condition` (status AS/AS_RECEIVED + AS_COMPLETED&완료일공란, sales_delivery 제외) | `foms/services/as_dashboard_read_model.py:31-34`, `as_dashboard_helpers.py:254-266` |
| AS 3종 상태 색상이 JS·folium 색상맵에 없어 회색 fallback | `static/js/measurement/map-view-kakao.js:23-30`, `foms/services/common/map_generator.py:69-88` |
| 좌표는 `orders.lat/lng` 단일 소스, 지오코딩 계보(RQ job+outbox) 공유 — 별도 배선 불필요 | `models.py:77-81`, `foms/services/jobs/tasks.py:65-119` |
| 운영 실측치(2026-08-05, 읽기전용): 미완료 52건 / 좌표없음 9 / 지오실패 0 / 지방 0 / 주소없음 0 | production DB read-only 집계 |

## 설계

### 1) 백엔드 — `dashboard=as` 분기 신설
- `/api/map_data?dashboard=as` → measurement 분기와 대칭인 AS 분기.
- 쿼리 빌더 `build_as_incomplete_map_query()` (map_snapshot.py):
  - `Order.active_filter()` + `build_as_tab_query_conditions()['incomplete_non_sales_condition']` **SSOT 재사용** (조건 복제 금지).
  - **날짜 필터 없음** — 미완료 탭 전체가 대상 (탭과 1:1 일치가 목표).
  - `is_regional` 제외 없음 (지방 AS 포함).
  - limit 500 (`ERP_MAP_MAX_LIMIT` 캡 준수), 초과 시 잘림 표시.
- 좌표 없는 건: measurement 패턴(`_enqueue_missing_measurement_geocodes`)과 동일하게 pending 마킹 + RQ enqueue, 클라 계단식 폴링이 해소.
- 스냅샷: `build_measurement_snapshot`을 kind 파라미터로 일반화(또는 동일 DTO의 AS 빌더) → `{orders[], markers[], summary}` 동일 계약.

### 2) 색상 SSOT
- `map_generator._get_status_color`(서버 정본)에 AS 3종 추가, `map-view-kakao.js STATUS_COLORS`에 동기 포팅(파일 상단 동기 주석 계약 준수).
- 제안: `AS_RECEIVED '#dc3545'`(접수=빨강), `AS '#fd7e14'`(처리중=주황), `AS_COMPLETED '#6c757d'`(회색 유지 — 미완료 탭에 오는 AS_COMPLETED는 완료일 공란 오상태 행뿐).

### 3) 프론트 — `map_view.html` as 분기
- `dashboard=='as'`: 날짜·상태 필터 숨김(측정 분기의 상태 고정 패턴 준수), 타이틀 "AS 미완료 지도", 총건수 표기.
- 상태 라벨 맵에 `AS: 'AS처리'` 추가 (AS_RECEIVED/AS_COMPLETED는 이미 존재 `map_view.html:1619-1635`).
- route 모드·mine 필터 **제외** (route는 실측 당일 동선 전용 — AS 미완료는 다일자 혼재라 무의미. 요청 시 후속).
- folium 폴백 `/api/generate_map`에도 as 분기 파리티.

### 4) 진입점
- `as_dashboard.py:198-201` open_map redirect → `url_for('erp_map.map_view', dashboard='as')`. PC·모바일 버튼 모두 이 redirect 경유라 1곳 수정.

## 예상 문제 및 해결 (사전 산출)
1. **지방 AS 제외 회귀** — generic 분기 유용 시 `is_regional != True`로 지방 건 누락. → 전용 as 분기에서 필터 제거. (현재 지방 AS 0건이지만 발생 즉시 누락되는 구조라 필수)
2. **탭↔지도 건수 불일치** — 판정 조건을 지도 쪽에 복제하면 드리프트. → `build_as_tab_query_conditions` SSOT 재사용 + 계약 테스트(탭 카운트 쿼리와 동일 모집단 검증).
3. **AS 상태 회색 마커** — 색상맵 부재. → 서버 정본 추가 + JS 동기 포팅.
4. **좌표 미보유 9건 첫 로드** — RQ enqueue+폴링으로 해소. REDIS 부재 시 동기 폴백(`_resolve_pending_geocodes`)이 건당 최대 10s — 운영은 REDIS 있음, 로컬 dev만 체감. Kakao REST 키는 env fail-fast 기존 계약 유지.
5. **지오코딩 실패 주소** — 기존 경고 배너 + `geocode_status='failed'` 재시도 제외 계약 그대로. 현재 실패 0건.
6. **SW stale JS** — `map-view-kakao.js` 수정 시 `?v` 범프 + 핀 전수 grep 필수 (staticCacheFirst 함정).
7. **팝업 "주문 상세 보기" 컨텍스트** — 현재 주문 대시보드 기준(`selectOrder`). AS 진입 시 `/erp/as?focus_order=<id>` 이동이 자연스러움 → as 분기에서 상세 링크 분기.
8. **500 한도** — 현재 52건으로 여유. 초과 시 잘림을 summary에 노출(묵시 잘림 금지).
9. **로컬 QA 카카오 도메인 차단** — localhost 미등록 → 401 → folium 폴백. 로컬은 folium/DOM 검증, kakao 실검증은 스테이징(lahom-dev)에서.
10. **JSONB 조건 성능** — status IN 3종 선행 축소로 모집단 극소(52) → ILIKE 없음, 성능 가드 비저촉.

## 비범위 (v1)
- route(동선) 모드, mine 필터, 미완료 하위 버킷별 필터, 완료 탭 지도.
