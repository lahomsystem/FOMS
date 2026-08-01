# 출고 AS 일정추천 모달 — 타임라인 본문 + 카카오 지도 (2026-07-30)

## 배경 / 현상

출고 대시보드 `AS 일정추천` 모달(`#shipmentAsRecommendModal`)의 추천 카드 본문이 **legacy AS 내용
(`structured_data.shipment.as_content` / `as_content_2`)** 을 그대로 렌더한다. AS 기록 SSOT는
2026-07-24 타임라인 개편(T1~T19) 이후 append-only `shipment.as_log` 로 이동했고, `as_content` 쓰기는
퇴역했다. 따라서 모달은 **개편 이전 시대의 본문만** 보여주며, 그 이후 남긴 통화/방문/자재/일정/시스템
기록은 전혀 보이지 않는다.

또한 같은 모달의 `지도` 버튼은 **Leaflet + OpenStreetMap 타일**(unpkg CDN 동적 로드)로 지도를 그린다.
AS 대시보드(`static/js/cs/as-dashboard.js`)의 동일 기능은 이미 **카카오 지도 SDK**를 쓴다. 같은
`#scheduleMapModal` 마크업을 두 페이지가 공유하는데 렌더러만 두 종류인 상태다.

## 근본 원인

1. 본문: 추천 payload 생성 경로(`shipment_as_recommendation_cache._as_content_html` →
   `schedule_recommendations` → `recommendations._compute_recommendation_payload`)가 타임라인 개편
   때 함께 옮겨지지 않았다. 후보 풀 DTO가 `as_content_html` / `as_content_text` 만 실어 보낸다.
2. 지도: 카카오 전환(AS 대시보드)이 표면별로 진행되어 출고 쪽 구현(Leaflet)이 남았다. 두 구현이
   같은 모달·같은 `/api/calculate_route` 를 쓰면서 코드만 중복된다.

## 설계

### A. 타임라인 본문 (요청 1)

- 렌더는 **기존 SSOT 매크로 재사용**: `templates/cs/partials/as_card_macros.html` 의
  `render_as_timeline(order_id, view, can_edit=False)`. `can_edit=False` 면 헤더(비용 판정/영업전달),
  프리셋, quick-add 폼, 항목별 수정/삭제 버튼이 전부 빠지고 앵커 + 역시간순 스트림 + legacy 앵커만
  남는다 → 모달이 필요한 읽기 전용 형태가 매크로 파라미터 하나로 성립한다.
- 뷰 데이터는 `foms/services/orders/as_log.build_as_timeline_view(sd, recent_limit=8)`.
  legacy `as_content` 는 이 뷰의 `legacy` 앵커로 이미 포함되므로 **기존 `as_content_html` 표시는 대체
  (삭제)** 한다 — 두 경로를 병행하면 같은 본문이 두 번 나온다.
- 주입 위치는 **후보 풀/타깃 캐시가 아니라 API 계층 `_enrich_recommendations`**:
  - 캐시(`shipment_as_recommendation_cache`)에 HTML을 넣으면 `as_log` 변경 시 staleness 위험이 생기고
    (append/patch/delete는 asrec 캐시를 무효화하므로 정합은 되지만) 후보 풀은 최대 800건이라
    렌더 비용이 폭증한다.
  - `_enrich_recommendations` 는 캐시 hit/miss 이후 항상 실행되고, 실제 추천된 AS 주문만
    (중복 제거 후 보통 ≤ 20건) 대상이므로 **요청당 1회 배치 쿼리 + 소수 렌더**로 끝난다. 값은 항상
    DB 기준 최신이다.
  - `return_targets=False`(prewarm) 경로는 렌더를 건너뛴다.
- 더보기: `render_as_timeline` 은 `v.has_more` 면 `.as-timeline__more` 버튼을 낸다. 그 클릭 핸들러는
  `as-dashboard.js` 에만 있어 출고 페이지에서는 죽은 버튼이 된다 → 매크로에 `show_more=true`
  파라미터를 추가하고, 출고 모달은 `false` 로 넘겨 "이전 기록 N건은 AS 대시보드에서 확인" 정적
  안내를 렌더한다.
- CSS: 타임라인 스타일(`.as-timeline*`, `.as-tl-item*`, `.as-tl-chip*`)이 AS 대시보드 전용
  `static/css/contexts/cs/as-dashboard-body.css` 에만 있다. 출고 페이지에 그 파일을 통째로 링크하면
  테이블 셀 규칙까지 새는 위험이 있으므로, **타임라인 코어 규칙만
  `static/css/components/foms-as-timeline.css` 로 이전**하고 CS/출고 양쪽이 링크한다.
  테이블 셀 전용(`.as-tl-cell*`, `.as-tl-expand*`)은 CS 파일에 남긴다.

### B. 카카오 지도 (요청 2)

- AS 대시보드의 카카오 구현(`as-dashboard.js` `loadKakaoSdk`/`addSchedulePin`/`renderScheduleMap`/
  `openScheduleMap`)을 **공용 모듈 `static/js/common/foms-schedule-map.js`** 로 추출한다
  (`window.FOMS_SCHEDULE_MAP.open({modalEl, containerEl, routeInfoEl, ref, target, scoreText})`).
  - CS·출고 양쪽이 이 모듈을 호출하고, 출고 쪽 Leaflet 로더·타일·마커·폴리라인 코드(약 130줄)와
    unpkg CDN 주입을 **삭제**한다.
  - 모듈이 소유: SDK 1회 주입(`window.__fomsKakaoSdkPromise` 재사용 — 프래그먼트 재실행 idempotent),
    generation 토큰(모달 연속 오픈 레이스), `/api/calculate_route` 응답 캐시, 컨테이너 초기화,
    SDK 차단 환경 폴백(경로 텍스트는 유지).
  - 출고 모달은 프래그먼트 스왑 시 `#scheduleMapModal` 을 body로 재부모화하므로, 모듈은
    `document.getElementById` 대신 **호출자가 넘긴 엘리먼트**를 쓴다.
- 카카오 JS 키: `templates/shipment/partials/dashboard_main.html` 의 `#scheduleMapContainer` 에
  `data-kakao-js-key` 추가 + `foms/web/shipment/dashboard.py` 렌더 컨텍스트에
  `kakao_js_key=KAKAO_JS_API_KEY` 전달(AS 대시보드와 동일 SSOT).
- 지도 컨테이너/핀/경로정보 CSS는 이미 전역(`erp-pro/09-mobile-erp-optimization.css`)이라 추가 없음.
- 로컬 dev 한계(기지식): 카카오 콘솔에 localhost 미등록이면 SDK가 401 → 모듈이 "지도를 불러오지
  못했습니다" 폴백을 낸다. 지도 타일 자체의 최종 확인은 스테이징(lahom-dev) 또는 Referer 스푸핑
  하네스로 한다.

### 캐시/버전 범프 (양쪽 공통)

- `shipment-dashboard.js`, 새 `foms-schedule-map.js`, `as-dashboard.js`, 새/기존 CSS 링크의 `?v=` 를
  범프하고 **직접 핀 전수 grep**으로 누락을 막는다(서비스워커 staticCacheFirst 때문에 no-cache
  헤더만으로는 구버전이 계속 실행된다).

## 범위 밖 (하지 않는다)

- 모달에서 타임라인 기록 추가/수정/삭제(quick-add·PATCH·DELETE 배선) — 읽기 전용 유지.
- `as_content` 컬럼/키 정리, 후보 풀 DTO에서 `as_content_*` 제거(검색 지문에 쓰임).
- AS 대시보드의 지도 UX 변경(모듈 추출은 동작 동일 유지).

## 검증 전략

- 백엔드: pytest 신규 — 추천 payload `as_timeline_html` 존재/`as-tl-item` 포함/수정·삭제 버튼 부재,
  `as_log` 기록이 legacy 본문 대신 노출, prewarm 경로 미렌더.
- 회귀: `tests/domains/test_as_timeline_*`, `tests/domains/test_erp_mobile_layout_and_shipment.py`,
  `tests/domains/test_shipment_dashboard_mobile.py`, `tests/performance/test_perf_regression_guard.py`.
- 프론트: `node --check`, 핀 전수 grep, 실제 브라우저(모달 열기 → 카드 본문 `as-tl-item` 확인,
  지도 버튼 → 카카오 타일 + 폴리라인 + 경로 정보).
- 최종: `python -c "import app; print('APP_OK')"` → `scripts/ops/pre_push_smoke.ps1` exit 0 →
  deploy push(세션 격리) → `ci_watch`.

## Task 목록

| Task | 내용 | 완료 기준 |
|---|---|---|
| T1 | 타임라인 CSS 컴포넌트 분리 + 양쪽 링크 | 새 `components/foms-as-timeline.css` 에 코어 규칙 존재, CS 파일에 중복 0, `.as-tl-cell*`/`.as-tl-expand*` 는 CS 잔류, AS 대시보드 렌더 회귀 없음 |
| T2 | 매크로 `show_more` 파라미터 + 출고용 partial | `render_as_timeline(..., show_more=False)` 가 `.as-timeline__more` 미출력 + 안내문 출력, 기존 CS 호출부 동작 불변(테스트 통과) |
| T3 | `_enrich_recommendations` 타임라인 렌더 주입 | 신규 pytest green (payload 필드·내용·버튼 부재·prewarm 스킵), 배치 쿼리 1회(N+1 없음) |
| T4 | `shipment-dashboard.js` 본문 렌더 교체 + `?v=` 범프 | `as_content_html` 소비 제거, 카드에 타임라인 마크업 주입, `node --check` 통과, 핀 grep 일치 |
| T5 | 공용 지도 모듈 추출 + CS/출고 전환, Leaflet 제거 | `leaflet` 문자열 0건, 양쪽 `?v=` 범프, perf guard 통과, `node --check` 통과 |
| T6 | 출고 라우트/템플릿 `kakao_js_key` 배선 | `#scheduleMapContainer[data-kakao-js-key]` 렌더 확인(테스트 또는 HTTP 렌더), APP_OK |
| T7 | 최종 검증·커밋·푸시 | pre_push_smoke exit 0, deploy push, `ci_watch` green |
