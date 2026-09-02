# 정산 대시보드 아키텍처 지도 (기존 계약 전수) — 2026-09-02

## 결론 (10줄)

1. 차트 라이브러리 = **없음**. `static/js/settlement/dashboard.js`가 목업의 인라인 SVG 렌더 함수(`lineChart`/`columnChart`/`sparkSvg`)를 그대로 이식했다(perf G2 — 외부 CDN 스크립트 금지가 테스트로 강제됨). 새 탭도 이 패턴을 따라야 한다.
2. period 파라미터 계약은 두 축이 분리돼 있다. 요약·분석 탭 = `GET /api/settlement/aggregates?month_from=YYYY-MM&month_to=YYYY-MM&granularity=day|week|month`(완료**월** 축). 실무 탭 = `GET /api/settlement/rows?period=all|7|30|31&...`(완료 후 **경과일** 축, 완전히 다른 의미).
3. 탭 등록점은 정확히 4곳(템플릿 tablist 버튼, `role=tabpanel` pane, JS `collectEls()`의 앵커 dict, CSS `.s-agrid`류 그리드) + 계약 테스트 상수(`_TABS`, `_SECTION_HOST_IDS` 등)까지 **5곳**. 하나라도 빠지면 `test_settlement_dashboard_render.py`가 정확 일치(exact match)로 red.
4. **`templates/settlement/`·`foms/web/settlement/`·`foms/services/settlement/`는 닫힌집합 게이트(SLG)가 막는다** — 실구현은 전부 `cs/` 하위 플랫 모듈(`settlement_dashboard.py`, `settlement_aggregation.py`, `settlement_rows.py`)로 우회했다. 새 네이버 정산 데이터도 같은 원칙: `foms/services/integrations/naver_commerce/`(이미 허용된 `integrations/`) 또는 `foms/services/cs/`, `foms/web/cs/`, `foms/api/cs/` 아래 플랫 모듈로 넣어야 새 CI 게이트가 안 생긴다.
5. 이 화면은 ERP 셸 프래그먼트 요청(`X-FOMS-ERP-SHELL: 1` + `?view=fragment`)과 전체 문서 요청 둘 다 같은 body partial을 렌더한다 — 자산 `<link>`/`<script>`는 반드시 **body partial 안에만** 둔다(shell 문서의 styles/scripts 블록에 두면 프래그먼트 경로에서 통째로 빠진다).
6. `?v=` 캐시 핀은 자산(CSS 2개·JS 2개) 하나당 **저장소 전역에 정확히 1곳**만 존재해야 한다는 계약 테스트가 있다(`test_settlement_asset_pins_are_single_repo_wide`) — 현재 4개 자산 모두 `?v=20260902b`로 통일돼 있다. 새 자산을 추가하면 그 자산도 이 패턴(핀 1곳 + 두 계약 테스트: 소스 리터럴 + 렌더 결과)을 새로 만들어야 한다.
7. 집중 모드는 `body.foms-settle-focus:has(.foms-settlement-root)` CSS 스코프 + `localStorage` 기억 + `window`(document 아님) 레벨 Esc 리스너로 구현된다. 셸 프래그먼트 스왑으로 정산 루트가 사라지면 `:has()`가 자동으로 무력화된다(body 클래스가 남아도 안전).
8. 실무 탭(operations.js)은 요약/분석 탭과 **다른 API**(`/api/settlement/rows`)를 쓰고, **다른 상태 노드**(`data-settlement-ops-*` 접두어)를 쓰며, 첫 로드를 탭 활성화까지 지연(`MutationObserver`가 `data-settlement-active-tab` 속성을 관찰)한다. 같은 루트 안에 3개 JS 모듈이 공존해도 이름이 겹치지 않게 설계된 구조라 — 네이버 탭도 독립 JS 파일 + 독립 데이터 소스 + 독립 상태 노드 접두어(`data-settlement-nv-*` 류)로 넣는 것이 기존 패턴과 정합적이다.
9. **테스트 계약 5스위트(≈425+ 케이스)**가 렌더·소스리터럴 이중 검사를 한다 — 새 탭/섹션 추가 시 `test_settlement_dashboard_render.py`의 `_TABS`/`_SECTION_HOST_IDS`/`_REQUIRED_ANCHORS` 등 상수를 함께 갱신해야 하며, `test_settlement_aggregation.py`의 "커널 반환 스키마 정확 일치" 계약도 키를 추가하는 순간 red가 된다(의도된 설계 — 함께 갱신).
10. **충돌 위험 낮음**: `git branch -a`에 `feat/settlement-wide`(origin/deploy와 완전히 동일 tip, 고유 커밋 0)·`session/settle-dash`·`session/settle-perf`·`session/settle-tabs`·`promo/settle-perf-20260901`가 있지만 전부 이미 `origin/deploy`에 merge된 과거 세션이다. 현재 진행 중인 경쟁 브랜치는 없다(2026-09-02 조사 시점).

---

## 1. 라우트 & 템플릿 구성

### 1.1 라우트

- `GET /erp/settlement` — `foms/web/cs/settlement_dashboard.py:81-110` (`erp_settlement_page_bp`, `url_prefix='/erp'`).
  - `@login_required` (`foms/web/cs/settlement_dashboard.py:82`) + 서버 판정 `can_view_settlement_dashboard()`(`:46-58`, `:94`). GET은 `enforce_order_mutation_policy`의 write-method 가드 밖이라(`_WRITE_METHODS`는 POST/PUT/PATCH/DELETE만) 이 핸들러가 **직접** 403을 낸다(`:94-95`).
  - 정책 상수 SSOT: `SETTLEMENT_DASHBOARD_POLICY_ID = "SETTLEMENT_DASHBOARD_READ"`(`:37`) — 페이지·API·템플릿이 **이 상수 하나**를 공유. `user_can()`은 policy_id 오타에 조용히 `False`를 주므로 문자열을 여러 곳에 하드코딩하지 않는다.
  - 허용 집합(`can_view_settlement_dashboard`, `:46-58`) = `FINANCE_MUTATION`과 동일 — ADMIN/MANAGER/STAFF+CS/STAFF+SALES. 담당자별 매출(분석 탭)만 `can_view_manager_breakdown()`(`:61-78`)으로 ADMIN/MANAGER로 추가 제한 — **서버 payload 단계에서** 키를 뺀다(클라 숨김 금지 원칙).
  - 분기(`:97-101`): `wants_erp_shell_tab_body(request)`가 참이면 `cs/partials/settlement_dashboard_body.html`(body partial만), 아니면 `cs/settlement_dashboard.html`(전체 문서). `apply_erp_shell_fragment_headers(response, request)`(`:109`)로 프래그먼트 헤더를 붙인다.
  - 뷰가 넘기는 컨텍스트: `erp_sub_nav_active='settlement'`, `department_options=SETTLEMENT_DEPARTMENT_OPTIONS`(`foms/web/cs/completion_dashboard.py:39`, 실무 탭 청구 폼의 부서 SSOT).

- `GET /api/settlement/aggregates` — `foms/api/cs/settlement.py:81-120` (`settlement_api_bp`, `url_prefix='/api/settlement'`).
- `GET /api/settlement/rows` — `foms/api/cs/settlement.py:123-158`.

### 1.2 ERP 셸 프래그먼트 헤더 계약

- 헤더/쿼리 상수 SSOT: `foms/services/common/erp_navigation_contract.py:86-97`.
  - `ERP_SHELL_REQUEST_HEADER = "X-FOMS-ERP-SHELL"`(`:86`), 활성값 `"1"`(`:87`).
  - `ERP_VIEW_QUERY_PARAM = "view"`(`:90`), `VIEW_FRAGMENT = "fragment"`(`:93`).
  - 판정 헬퍼: `foms/services/common/erp_shell_http.py` — `get_erp_shell_view_mode()`(`:10-26`), `wants_erp_shell_tab_body()`(`:29-31`), `apply_erp_shell_fragment_headers()`(`:41-`).
- 테스트에서 프래그먼트를 재현하려면 `client.get("/erp/settlement?view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})` (실제 헬퍼: `tests/domains/test_settlement_dashboard_render.py:75-77` `_SHELL_HEADERS`/`_FRAGMENT_URL`).

### 1.3 템플릿 3종 세트

- `templates/cs/settlement_dashboard.html`(전체 문서, 11줄) — `cs/layout.html`을 extends, `{% block content %}`가 body partial을 `{% include %}`. **자산 `<link>`/`<script>`를 이 파일의 layout 블록으로 옮기면 안 된다** — 주석(`:3-10`)이 명시: 프래그먼트 경로는 이 셸을 안 거치므로 옮기면 탭 진입 시 CSS도 JS도 없는 화면이 된다.
- `templates/cs/partials/settlement_dashboard_body.html`(389줄) — 실제 화면 전체(헤더·서브내비·탭바·필터바·상태 3종·pane 3개·툴팁). 자산 링크(`:20-21`, `:388-389`)와 `?v=` 핀이 **이 파일에만** 있다.
- `templates/cs/partials/settlement_operations_body.html`(205줄) — 탭2(실무) 내용물. `settlement_dashboard_body.html:238`이 `#foms-settle-ops-mount` 안쪽에 `{% include %}`.

### 1.4 탭 등록 계약 (`data-settlement-tab` / aria 배선)

`templates/cs/partials/settlement_dashboard_body.html:61-93`:

```html
<div class="s-tabs" role="tablist" aria-label="정산 대시보드 화면">
  <button role="tab" id="foms-settle-tab-summary" data-settlement-tab="summary"
    aria-controls="foms-settle-pane-summary" aria-selected="true" tabindex="0">…</button>
  <button role="tab" id="foms-settle-tab-ops" data-settlement-tab="ops"
    aria-controls="foms-settle-pane-ops" aria-selected="false" tabindex="-1">…</button>
  <button role="tab" id="foms-settle-tab-analytics" data-settlement-tab="analytics"
    aria-controls="foms-settle-pane-analytics" aria-selected="false" tabindex="-1">…</button>
  <button class="s-tab s-tab--focus" data-settlement-focus aria-pressed="false">⤢ 집중 모드</button>  <!-- 탭 아님, role=tab 없음 -->
</div>
```

- 버튼 `id/aria-controls` ↔ pane `id/aria-labelledby`가 1:1 (예: `templates/cs/partials/settlement_dashboard_body.html:141-142` 요약 pane).
- pane 등록: `<div class="s-pane" role="tabpanel" id="foms-settle-pane-X" data-settlement-pane="X" aria-labelledby="foms-settle-tab-X" tabindex="0" hidden>`. 기본 탭(summary)만 `hidden` 속성이 없다(`:141` vs `:236,247`).
- 선택 상태 SSOT는 **버튼의 `aria-selected`**(사람이 읽는 표시)와 **루트의 `data-settlement-active-tab`**(CSS/JS가 읽는 기계 판정, 예: `:44` 초기값 `"summary"`) 둘. CSS는 후자만 본다(`static/css/settlement/settlement-dashboard.css:149` `[data-settlement-active-tab="ops"] .s-filterbar { display:none }`).
- JS 쪽 등록: `static/js/settlement/dashboard.js` `activateTab()`(`:1754-1774`)이 `data-settlement-tab`/`data-settlement-pane`을 순회하며 상태를 맞춘다. `collectEls()`(`:1848-1935`)의 `tabs`/`panes` 배열(`root.querySelectorAll('[data-settlement-tab]')`/`'[data-settlement-pane]'`)이 새 탭 버튼/pane을 자동으로 주워담으므로, **탭을 추가해도 이 두 줄은 안 고쳐도 된다** — 단, `renderAll()`(`:1609-1620`)에는 새 탭 전용 렌더 함수를 명시적으로 등록해야 한다(자동 발견 아님).

### 1.5 집중 모드(`:has()` 스코프, window 리스너 규율)

- CSS 스코프: `static/css/settlement/settlement-dashboard.css:130-136`.
  ```css
  body.foms-settle-focus:has(.foms-settlement-root) header.bg-light,
  body.foms-settle-focus:has(.foms-settlement-root) nav.layout-global-nav,
  body.foms-settle-focus:has(.foms-settlement-root) .erp-settlement > .erp-pro-header,
  body.foms-settle-focus:has(.foms-settlement-root) .erp-settlement > .erp-pro-nav { display: none !important; }
  body.foms-settle-focus:has(.foms-settlement-root) .s-focusbar { display: flex; }
  ```
  `:has()`로 스코프하는 이유(`:127-129` 주석): 셸 프래그먼트 스왑으로 정산 루트가 사라지면 `body` 클래스가 남아 있어도 다른 화면 크롬은 안 접힌다.
- JS: `static/js/settlement/dashboard.js:270-296` — `FOCUS_CLASS='foms-settle-focus'`, `FOCUS_STORAGE_KEY='foms.settlement.focus'`. `setFocusMode(on)`이 `document.body.classList.toggle` + `localStorage` 기억(`try/catch`로 프라이빗 모드 방어).
- **window 리스너 규율**: Esc 키는 `window.addEventListener('keydown', ...)`(`:1982-1985`)로 **document가 아니라 window**에, 그리고 프래그먼트 재실행 시 중복 등록 방지를 위해 `window.__FOMS_SETTLEMENT_DASHBOARD_BOUND` 싱글톤 가드(`:1975-1980`) **안에서 1회만** 등록. 이유(`:1982` 인접 주석): 루트 위임 리스너로는 포커스가 차트 밖(예: 탭바)에 있을 때 Esc를 못 받는다.
- 집중 모드 토글 버튼은 720px 이하에서 CSS로 숨김(`static/css/settlement/settlement-dashboard.css:448-450`) — 모바일 셸은 접을 크롬이 다르다는 이유.

### 1.6 CSS `?v=` 핀 위치

전부 `templates/cs/partials/settlement_dashboard_body.html`에만 존재(정확히 한 파일, 한 곳):

```
:20  css/settlement/settlement-dashboard.css   ?v=20260902b
:21  css/settlement/settlement-operations.css  ?v=20260902b
:388 js/settlement/dashboard.js                ?v=20260902b
:389 js/settlement/operations.js               ?v=20260902b
```

계약 테스트(아래 §5)가 "자산 하나당 저장소 전역에서 핀이 정확히 1개"를 강제하므로, 이 핀을 다른 파일에 복제하면 실패한다.

---

## 2. JS 아키텍처

### 2.1 차트 라이브러리 = 없음 (외부 CDN 0, perf G2)

`static/js/settlement/dashboard.js:1-25`(모듈 헤더 주석) 명시: 목업(`docs/design/mockups/settlement-dashboard-v1-executive.html` `<script>` `:330-883`)의 SVG 렌더 함수를 시그니처까지 그대로 이식. 외부 차트 라이브러리(Chart.js/D3/ECharts 등) 사용 금지 — `tests/domains/test_settlement_dashboard_render.py:468` `test_no_chart_library_globals_in_dashboard_js`와 `:453` `test_settlement_sources_reference_no_external_host`(외부 호스트 URL 0, `www.w3.org` SVG 네임스페이스만 예외)가 강제한다.

재사용 가능한 렌더 헬퍼(전부 `static/js/settlement/dashboard.js`):

| 함수 | 줄 | 용도 |
|---|---|---|
| `lineChart(ctx, host, cfg)` | `:303-400` | crosshair 스냅 + 툴팁 + 키보드(←→) 라인 차트 |
| `columnChart(ctx, host, cfg)` | `:401-522` | 막대(+비교선) 차트. **숨은 pane에서 그리면 `clientWidth===0`이라 폴백 폭(400px/lineChart는 640px)로 눌린 채 남는다** — 탭 활성화·리사이즈 시 `renderAll()` 재호출이 유일한 해법(`activateTab()` 주석 `:1738-1752` 실측 수치 포함) |
| `sparkSvg(values, accent)` | `:523-545` | KPI 타일용 미니 스파크라인 |
| `renderBarList(ctx, host, items)` | `:1177-1214` | 가로 막대 리스트(담당자별/단계별/부서별/AS — 분석 탭 공용, CSS % 폭이라 폭 0 함정 밖) |
| `showTip`/`hideTip` | `:217-266` | 툴팁 공용(위치는 `--s-tt-x`/`--s-tt-y` CSS 커스텀 프로퍼티로 — 인라인 style 금지 규칙 준수) |
| `appendKpi(wrap, spec)` | `:557-601` | KPI 타일 1장 렌더(라벨·값·델타·스파크) |
| `fmtMan/fmtWon/fmtTick/fmtCount` | `:82-113` | 숫자 포맷터(원→만원, "2억 1,430만" 등) |
| `esc(text)` | `:70-75` | SVG 안 텍스트 이스케이프 |
| `niceScale/cumsum/sum` | `:114-141` | 축 스케일·누적·합계 유틸 |

### 2.2 모듈 구조 (dashboard.js, 1990줄)

- 색 사전(`:38-50`): `ACCENT`/`CTX`/`BLUE_BUCKET4`/`ORANGE_RAMP5`/`FAM`/`CHANNEL_COLORS` 등 — dataviz 팔레트 하드코딩. 재사용 시 이 사전을 확장하거나 새 계열색을 추가한다(§13 색 전략: B=지표 계열색+D=카드 가족 틴트, `docs/design/mockups/settlement-color-study.html`).
- 싱글톤/재마운트 규율(`:14-19` 주석, ERP 셸 프래그먼트 재실행 대응 — perf G4):
  1. `document`/`window` 리스너는 `window.__FOMS_SETTLEMENT_DASHBOARD_BOUND`(`:1975`) 뒤에서 1회만.
  2. 실제 마운트는 루트의 `data-settlement-mounted` 표식(`:1937`)으로 루트당 1회만.
  3. `mountAll()`을 스크립트 재실행 시점(`:1989` 파일 끝)과 `foms:erp-shell-fragment-swapped`/`foms:main-content-swapped` 이벤트(`:1977-1978`) **양쪽**에서 호출.
- 데이터 로드: `load(ctx)`(`:1671-1701`) — `fetch(buildUrl(ctx), {credentials:'same-origin', headers:{Accept:'application/json'}})`. `try/catch` + `body.success !== true` 검증(프로젝트 규칙 준수). `res.status === 403`은 별도로 `showState(ctx,'denied')`. 응답 지연 경쟁 방지용 `seq` 카운터(`:1657,1673,1679,1692,1699`) — 늦게 온 응답이 최신 화면을 덮지 않게.
- `buildUrl(ctx)`(`:1652-1666`): `granularity` + (`month` 모드면 `month_from`=6개월 전, 아니면 당월만) → `month_from`/`month_to`.
- 상태 전환: `showState(ctx, kind, detail)`(`:1634-1650`) — `loading`/`error`/`denied`/`ready` 4종. 상태 노드는 **pane 밖·루트 직속**(요약·분석 두 탭이 공유하는 단일 fetch이므로, pane 안에 두면 숨은 탭에서 실패 문구가 안 보이는 무음 실패가 난다 — 템플릿 주석 `:115-122`와 동일 논리).
- 렌더 진입점: `renderAll(ctx)`(`:1609-1620`) 하나. 탭 3(분석)도 `renderAnalytics(ctx)`(`:1595-1607`)를 그 안에서 호출 — "렌더 진입점을 두 벌로 만들면 한쪽만 고치는 회귀가 난다"는 설계 원칙(주석 다수 반복).
- 탭 배선: `activateTab(ctx, key, moveFocus)`(`:1754-1774`), `onTabKeydown`(←→/Home/End, `:1776-1795`), `bindControls(ctx)`(`:1796-1846`, 루트 안쪽에만 리스너 — 루트가 스왑으로 사라지면 리스너도 같이 사라짐).
- `collectEls(root)`(`:1848-1935`): 모든 DOM 앵커를 한 번에 querySelector로 모아 `ctx.els`에 담는 패턴. 새 탭/섹션 추가 시 여기에 항목을 추가해야 한다(자동 발견 아님, `tabs`/`panes` 배열만 예외).

### 2.3 실무 탭(operations.js, 917줄) — 독립 서브모듈

- **다른 데이터 소스**: `GET /api/settlement/rows` **하나만**. 집계 API(`aggregates`)를 부르지 않는다(`:1-11` 헤더 주석 — "한 화면에 소스가 둘이면 같은 숫자가 두 계산 경로로 갈려 조용히 어긋난다").
- **다른 상태 노드 접두어**: `data-settlement-ops-*`(요약 탭의 `data-settlement-loading`/`-error`/`-denied`와 이름이 겹치면 서로 다른 탭의 노드를 서로 잡는다 — 헤더 주석 `:9-16`).
- `buildUrl(ctx)`(`:187-198`): `period`/`settlement`/`channel`/`aging`/`page` 5개 쿼리 파라미터.
- 공통 GET 헬퍼 `getJson(url)`(`:200-217`) — 실패는 `throw`, 호출부(`loadRows`)가 상태 노드로 옮긴다.
- **탭 활성화까지 첫 로드 지연**: `watchTabActivation(ctx)`(`:865-877`) — 셸이 탭 전환 이벤트를 안 쏘므로(`dashboard.js`에 `dispatchEvent` 없음), CSS가 이미 SSOT로 쓰는 `data-settlement-active-tab` 속성을 `MutationObserver`로 관찰. 두 번째 신호를 발명하지 않고 기존 신호를 재사용하는 패턴 — 새 탭도 같은 패턴을 재사용할 수 있다.
- 마운트 싱글톤: `window.__FOMS_SETTLEMENT_OPS_BOUND`(`:906`), `data-settlement-ops-mounted`(`:879`) — dashboard.js와 동일 규율, 별도 네임스페이스.
- 실행 버튼 2종(`paymentConfirmUrl`/`settlementIssueUrl`, `:52-58`): `POST /api/orders/<id>/payment-confirm`(원클릭)과 `POST /api/orders/<id>/settlement/issue`(department·amount·reason 3필수 — 폼). CSRF 헤더 없이 same-origin 세션 인증(기존 관례 `static/js/orders/erp-order-shared.js:2893`).
- 마크업은 `createElement`+`textContent`만 사용(`innerHTML` 금지) — 고객명이 그대로 들어오는 자리라 이스케이프 실수 여지를 없앤다.

### 2.4 KPI/테이블/빈·로딩·오류 상태 공통 패턴

- KPI 타일: `appendKpi()`(dashboard.js `:557-601`) + `renderKpis()`(`:602-650`, 요약)/`renderAnalyticsKpis()`(`:1278-1318`, 분석) — 둘 다 같은 `appendKpi` 재사용.
- 빈 상태: `data-settlement-empty="<key>"` 속성 + `.s-empty` 클래스(회색 점선 박스, Bootstrap `.alert` 아님 — `static/js/runtime/script.js:10`이 5초 뒤 자동 닫기 때문에 상시 안내는 `.alert` 금지).
- 로딩/오류/거부 3종은 **서로 다른 노드**(무음 실패 금지 원칙) — 요약/분석 공유(`data-settlement-loading/-error/-denied`, 루트 직속) vs 실무 전용(`data-settlement-ops-loading/-error`, denied는 셸이 전역 처리).
- 숫자 포맷터(§2.1의 `fmtMan`/`fmtWon`/`fmtTick`/`fmtCount`)는 dashboard.js 전용, operations.js는 별도 소형 포맷터(`money`/`count`/`toMan`/`fmtMan`/`fmtDay`, `:87-120`)를 갖고 있다 — **두 파일이 헬퍼를 공유하지 않는다**(별도 IIFE라 스코프가 다름). 네이버 탭을 dashboard.js 안에 넣으면 기존 포맷터 재사용 가능, 별도 JS 파일로 빼면 포맷터를 복제하거나 공용 모듈로 승격해야 한다.

### 2.5 기간 선택기(필터바) — 요약/분석 공유, 실무는 별도

- 필터바(`.s-filterbar`, 템플릿 `:101-113`)는 **문서에 한 벌만** — 요약·분석 탭이 공유하는 단일 상태. `dashboard.js`의 `syncToggles(ctx)`(`:1707-`)와 `collectEls()`의 `granButtons`/`cmpToggle`/`cumToggle`이 이 한 벌을 배선한다. 실무 탭에서는 CSS(`[data-settlement-active-tab="ops"] .s-filterbar{display:none}`)로 감춘다 — `s-hidden` 클래스를 쓰지 않는 이유(템플릿 주석 `:98-100`)는 그 클래스가 `showState()`의 권한거부 분기 전용 자리라서 겹치면 403 해제가 탭 상태까지 되돌리기 때문.
- 다른 탭이 이 필터바를 "구독"하는 방법: 없음 — `renderAll()`이 요약/분석 렌더 함수를 한 번에 다 부르므로 "구독" 개념 자체가 없고, 필터 변경 시 `load(ctx)` 재호출 → `state.data` 갱신 → `renderAll()`이 두 탭 모두 다시 그린다.

---

## 3. API 레이어

### 3.1 `foms/api/cs/settlement.py`

| 엔드포인트 | 줄 | 파라미터 | 권한 |
|---|---|---|---|
| `GET /api/settlement/aggregates` | `:81-120` | `month_from`(기본 전월, KST), `month_to`(기본 이번달), `granularity`(기본 `"day"`) | `can_view_settlement_dashboard()`(FINANCE_MUTATION 집합) + `can_view_manager_breakdown()`(ADMIN/MANAGER만 `managers`/`managers_total` 유지, `_MANAGER_ONLY_KEYS`, `:39,116-118`) |
| `GET /api/settlement/rows` | `:123-158` | `period`(기본 `"all"`), `settlement`(기본 `"all"`), `channel`(기본 `"all"`), `aging`(기본 `""`), `page`(기본 1) | `can_view_settlement_dashboard()`와 동일 게이트 |

- 두 엔드포인트 모두 `@login_required` + 핸들러 내부 직접 판정(GET이라 `enforce_order_mutation_policy` write-gate 밖, 모듈 docstring `:15-18`).
- 응답 포맷 공통: `{'success': True/False, 'data': ..., 'error': ...}`(`_error()` 헬퍼 `:76-78`). `ValueError`는 사람이 읽는 한글 사유를 그대로 400으로 전달(내부 스택 노출 없음).
- **노출 계약이 명시적으로 다르다**(`:9-13` 모듈 docstring) — `aggregates`는 주문 행 원본 절대 미노출(집계 버킷만). `rows`는 실무 탭용이라 고객 성명+주문번호까지 노출하되 연락처·주소·현금영수증 원문은 여전히 금지. 두 계약은 각자 전용 테스트로 고정 — 한쪽 완화로 다른 쪽을 정당화 금지.
- 캐싱 없음(코드에 캐시 데코레이터·헤더 조작 없음). 스펙 §10 Q3에서 "v1 기본 무캐시, 실측 후 결정"으로 남겨둔 열린 질문(`docs/specs/2026-08-31-settlement-dashboard_SPEC.md:157`).

### 3.2 `foms/services/settlement_aggregation.py` (1030줄)

핵심 공개 함수:

```python
def aggregate_settlement(
    db: Any, *, month_from: str, month_to: str, granularity: str = "month",
) -> dict:
    """반환 키: range/kpi/buckets/prev_buckets/prev_totals/aging/aging_unknown/
    channels/managers/managers_total/settlement_status/stages/unknown_completion.
    Raises: ValueError — month 형식 오류, granularity 미지원, 범위 역전, 12개월 초과."""
```
(`:981-1030`)

- 모집단은 3쿼리만(`_population_filters()`, `:474-486` — 완료 대시보드 `_completion_base_query`와 **정확히 동일**한 3조건) + `_channel_map()`(N+1 없는 단일 배치, `:487-499`) + `_load_rows()`(`:515-526`, 200건 캡 없이 전량, 날짜 술어 없음).
- 200건 캡 우회의 핵심: SQL로는 캡 없는 전량 SELECT, 집계(GROUP BY·KPI·aging·채널)는 **파이썬 커널이 1회 순회**로 처리(`:104-980`의 수십 개 `_build_*` 헬퍼). 출고가/예약금/잔금 등 금액은 저장 컬럼을 믿지 않고 항상 재파생(`_row_amounts`, `:374-390`).
- 재사용 가능한 순수 함수(부작용 없음, 네이버 정산 집계에도 참고 가능): `completion_month_key`/`completion_day_key`(`:104-133`), `week_key`(`:171-183`), `aging_bucket`(`:192-203`), `_month_range`/`_previous_month_range`(`:250-283`).

### 3.3 `foms/services/settlement_rows.py` (434줄)

```python
def list_settlement_rows(
    db: Any, *, period: str = "all", settlement: str = "all", channel: str = "all",
    aging: str = "", page: int = 1, per_page: int = PER_PAGE,
) -> dict:
    """반환 키: rows/page/per_page/total_count/total_pages/totals/filters/
    aging_options/aging_summary/as_of.
    Raises: ValueError — 필터 값이 허용 집합 밖."""
```
(`:361-434`)

- `PER_PAGE = 60`(`:60`, 완료 대시보드 태블릿 그리드 `_paginate`와 같은 크기).
- 2단 스코프 설계(`:399-402` 주석): 스코프(기간·정산상태·채널)까지 좁힌 모집단이 aging 막대의 분모, 거기서 aging 하나를 더 좁힌 것이 목록 — 한 번 읽은 모집단으로 aging 막대와 목록 둘 다 낸다(`aging_summary`가 aging 선택과 무관한 이유).
- 정렬: 미수 먼저, 그 안에서 경과일 오래된 순(`_sort_key`, `:283-296`).

---

## 4. CSS 클래스 네이밍 체계

### 4.1 네임스페이스·토큰

- 루트 네임스페이스 클래스: `.foms-settle`(모든 선택자가 이 안에 스코프됨). 목업 원본은 독립 문서라 `.card`/`.grid`/`.badge`/`.legend` 같은 맨이름을 썼는데, Bootstrap 5·`erp-pro.css`가 전역 선착순이라(`layout_head.html:239,248`) 이름 충돌 방지를 위해 전부 `s-` 접두어로 개명(`static/css/settlement/settlement-dashboard.css:1-32` 헤더 주석).
- 토큰: `--s-*` 접두어로 `.foms-settle` 안에만 선언(`:34-58`) — `--s-bg`/`--s-surface`/`--s-accent`/`--s-good`/`--s-bad`/`--s-critical` 등. 전역 `foundation/foms-tokens.css`와 이름 충돌 방지.
- 실무 탭은 `s-ops-` 2차 접두어(`settlement-operations.css`) — 같은 루트 안에 사는 요약/분석 탭 선택자와 겹치지 않게. 계약 테스트가 "`.s-filterbar`가 문서에 정확히 1개"임을 고정(`settlement_operations_body.html:18` 주석).

### 4.2 그리드·카드·KPI

- 요약 탭 그리드: `.s-grid { display:grid; grid-template-columns: repeat(12, minmax(0,1fr)); }`(`:197-199`) + 명시적 `grid-column`/`grid-row` 배치(`.s-card--main{1/10, 2/4}`, `.s-side{10/13,2}`, `.s-card--aging{1/6,4}`, `.s-card--stages{6/13,4}`, `.s-card--channel{10/13,3}`).
- 분석 탭 그리드: `.s-agrid { grid-template-columns: repeat(12, minmax(0,1fr)); }`(`:352-357`) + `.s-span8`/`.s-span4`(`grid-column: span 8/4`) — **요약 탭과 다른 배치 시스템**(명시 좌표 대신 span 카드).
- KPI 타일: `.s-kpis{ grid-template-columns: repeat(5, minmax(0,1fr)) }`(요약, `:211-213`) vs `.s-agrid > .s-kpis{ repeat(4,...) }`(분석, `:357`).
- 카드 공통: `.s-card`(`:201`), 헤더 `.s-card-head`/`.s-card-title`/`.s-card-sub`(`:205-208`).

### 4.3 반응형 = `@media`, container query 아님

- `settlement-dashboard.css`에 `@container`/`container-type` **없음**(grep 결과 0건). 반응형은 전부 `@media (max-width: 1500px/1120px/720px)`(`:430-460`)로 처리 — viewport 기준.
- 이는 프로젝트 전역 관례("공용 부품 좁은 폭 분기 = container query")와는 다른 선택이다 — 정산 대시보드는 **화면 전체를 차지하는 페이지**라 container query 필요성이 낮았던 것으로 보인다(추정). 네이버 탭이 좁은 사이드 패널 등에 재사용될 계획이 있다면 container query 도입을 재검토할 필요가 있다.

### 4.4 다크 모드 = 없음

- `.foms-settle { color-scheme: light; }`(`:36`) 고정 — `prefers-color-scheme`/`[data-theme]` 분기 **전혀 없음**(grep 결과 0건). 이 화면은 라이트 전용으로 확정 지어진 화면이다(목업 v3의 다크 버전은 라이트로 교체됨 — `docs/plans/2026-08-31-settlement-dashboard-mockup-ledger.md` T10).

### 4.5 빈 상태·상태 3종 시각 언어

- `.s-empty`(회색 점선 박스, `:314-321`), `.s-state--loading/--error/--denied`(각각 다른 색/문구, `:326-339`) — Bootstrap `.alert` 금지(자동 닫힘 문제).

---

## 5. 테스트 계약 전수

5개 파일, 함수 수: `test_settlement_dashboard_render.py`(76개), `test_settlement_operations_render.py`(59개), `test_settlement_dashboard_api.py`(21개), `test_settlement_rows_api.py`(31개), `test_settlement_aggregation.py`(다수, 1448줄) — 원장 기록상 "정산 5스위트 합계 425+ green"(`docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md:704`).

### 5.1 새 탭이 반드시 만족해야 할 계약 (파일:함수)

| 계약 | 파일:함수 | 요지 |
|---|---|---|
| 자산 실재·비어있지 않음 | `test_settlement_dashboard_render.py:334,345` | `static/{CSS_ASSET}`/`{JS_ASSET}` 존재 + 200자 초과 |
| `?v=` 핀 필수 | `:354` `test_settlement_assets_are_pinned_in_template` | 템플릿 링크에 핀 있어야 함 |
| 핀 저장소 전역 유일성 | `:369` `test_settlement_asset_pins_are_single_repo_wide` | 자산당 핀 값이 저장소 전체에서 **정확히 1개** |
| 렌더 결과에도 핀 유지 | `:386,400` | 프래그먼트·전체문서 둘 다 |
| `<script>` defer 필수 | `:414,427,436` | perf G1, 예외 없음(allowlist 불허) |
| 외부 CDN 0 | `:453` `test_settlement_sources_reference_no_external_host` | `www.w3.org`만 예외 |
| 차트 라이브러리 전역 금지 | `:468` `test_no_chart_library_globals_in_dashboard_js` | Chart.js/D3/ECharts 등 |
| 인라인 style 금지 | `:486,499` | 속성·블록 둘 다 |
| `JSON.parse('{{ \|tojson }}')` 금지 | `:508` | Jinja→JS는 `data-*` |
| 섹션 host id 서버 렌더 | `:522` `_SECTION_HOST_IDS`(`:112-122`) | JS가 채우기 전에도 앵커가 있어야 함 |
| 목업 잔재 문구 금지 | `:587,607` `_MOCKUP_LEFTOVERS = ("MOCKUP","예정","해피콜","가정치")` | 없는 데이터를 있는 것처럼 보여주면 안 됨 |
| 탭 3종 wiring | `:1053` `test_tab_bar_renders_three_tabs_with_expected_wiring` — `_TABS` 상수(`:180-187`)와 exact 매칭 | 탭 추가 시 이 튜플 갱신 필수 |
| 모든 탭에 매칭 pane | `:1098` `test_every_tab_has_a_matching_tabpanel` | |
| 필터바 공유·중복 금지 | `:1239,1263` | 탭마다 필터바 복제 금지 |
| 탭 전환 시 재렌더 경로 | `:1285` `test_tab_activation_rerenders_charts_through_the_resize_render_path` | 숨은 pane 폭 0 함정 재현 확인 |
| 화살표 키 이동 | `:1315` `test_arrow_keys_move_between_tabs_without_global_listeners` | |
| 분석 카드 서버 렌더 | `:1425` `test_analytics_cards_are_server_rendered` | |
| 권한 게이트 카드(담당자별) | `:1448,1469,1484` | 키 부재 시 카드째 숨김, STAFF payload 실제 검증 |
| 렌더 진입점 단일성 | `:1602,1724` `test_analytics_renders_through_the_single_render_entry_point` | `renderAll` 하나만 |

### 5.2 실무 탭(operations) 전용 추가 계약

| 계약 | 파일:함수 | 요지 |
|---|---|---|
| 과입금 칸 필수 | `test_settlement_operations_render.py:324` | CEO L-1 회귀 방지 |
| 컬럼 순서 리터럴 정확 일치 | `:336` `test_grid_headers_are_complete_and_in_contract_order` — `_GRID_HEADERS`(`:111-114`) = `("고객","채널","완료일","출고가","예약금","잔금","과입금","경과일","현금영수증","정산상태","액션")` | 11칸 순서 고정, 헤더 문자열 정확 매칭(`re.findall(r"<th\b[^>]*>\s*([^<]+?)\s*</th>")`) |
| 부서 코드/라벨 하드코딩 금지 | `:374,388` | 서버 SSOT(`SETTLEMENT_DEPARTMENT_OPTIONS`) 재사용 |
| 요약 탭과 선택자 충돌 금지 | `:548` `test_surface_does_not_reuse_summary_tab_selectors` | `s-ops-` 접두어 강제 |
| 자기 상태 노드 소유 | `:564` `test_ops_tab_owns_its_own_loading_and_error_nodes` | |
| API 파라미터 전수 전송 | `:643` `test_js_sends_every_api_filter_param` | period/settlement/channel/aging/page |
| API 응답 키 전수 바인딩 | `:655` `test_js_binds_every_api_response_key` | |
| 행 필드 전수 바인딩 | `:672` `test_js_binds_every_exposed_row_field` | |
| 뮤테이션 same-origin·CSRF 미사용 | `:751` `test_mutations_are_same_origin_session_auth_without_csrf_header` | |
| 페이지네이션(넘버 페이저, 무한스크롤 금지) | `:778` | 경리 업무는 "몇 페이지째"가 작업 기록 |
| 탭 활성화까지 첫 로드 지연 | `:865` `test_first_load_is_deferred_until_the_ops_tab_is_active` | |
| aging 막대 = CSS 폭(SVG 아님) | `:881,894` | 폭 0 함정 회피 |

### 5.3 API 계약(`test_settlement_dashboard_api.py`/`test_settlement_rows_api.py`)

- 권한 매트릭스: `test_actor_matrix_is_the_finance_matrix`(`:176`), `test_settlement_get_allowed_actors`/`_denied_actors`(`:199,216`) — `FINANCE_MUTATION`과 정확히 같은 actor 집합.
- 정책 등록성: `test_settlement_policy_is_registered`(`:305`), `test_settlement_policy_fields_match_finance`(`:315`), `test_settlement_policy_not_in_ancillary_allowlist`(`:362`).
- 응답 스키마: `test_api_success_envelope_and_m1_schema`(`:375`) — M1 스키마 정확 일치(신규 키 추가 시 red, 의도된 설계).
- 담당자 은닉: `test_manager_breakdown_is_served_to_managers`/`_stripped_from_payload_for_staff`(`:411,422`).
- 파라미터 검증: `test_api_defaults_to_previous_and_current_month_day_granularity`(`:447`), `test_api_invalid_params_return_400`(`:473`), `test_api_accepts_all_supported_granularities`(`:487`).
- `rows` API: 필드셋 정확 일치(`test_row_shape_is_exactly_the_agreed_field_set`, `test_settlement_rows_api.py:141`), PII 미노출(`:169,187`), 페이지네이션(`:206,231,249`), 필터 400(`:263`), 정렬(`:334,355`), aging_summary 불변식(`:417,434,450,473,486`).

### 5.4 manifest / inventory / closed-set 게이트 (신규 라우트·모듈 등록 의무)

grep 대상: "manifest"·"inventory"·"closed set"·"allowlist"·"audit_message_display"·"PTC" — 정산 화면과 직결되는 것만 정리.

| 게이트 | 파일:라인 | 무엇을 강제하나 | 정산/네이버 관련 상태 |
|---|---|---|---|
| SLG 닫힌집합(templates 최상위) | `tests/contracts/runtime/foms_namespace_surface_tests.py:2355` `test_slg_literal_gap_templates_top_level_dirs_closed_set`, 허용집합 `:2249-2265` | `templates/` 바로 아래 디렉토리가 정확히 이 집합과 일치(`admin/auth/channel/construction/cs/drawing/macros/measurement/orders/partials/production/shipment/wdcalculator`) | **`cs`는 이미 허용됨** — `settlement/`은 없음(spec §6이 제안했던 `foms/web/settlement/`가 실제로는 `foms/web/cs/settlement_dashboard.py`로 우회 구현된 이유) |
| SLG 닫힌집합(foms/web 최상위) | `:2366` `test_slg_literal_gap_foms_web_top_level_dirs_closed_set`, 허용집합 `:2267-2280` | 동일 원리, `foms/web/` | `cs` 허용, `settlement` 없음 |
| SLG 닫힌집합(foms/api 최상위) | `:2377`, 허용집합 `:2282-2298` | 동일, `foms/api/` | `cs` 허용 |
| SLG 닫힌집합(foms/services 최상위) | `:2388`, 허용집합 `:2300-2321` | 동일, `foms/services/` | `cs`·**`integrations`**(네이버 커머스 클라이언트 경계, 주석 `:2317-2318`) 둘 다 허용 — 네이버 정산 API 클라이언트는 `foms/services/integrations/naver_commerce/` 아래에 자연스럽게 들어간다 |
| PTC 루트 allowlist | `tests/contracts/runtime/test_ptc_physical_exactness.py:19-70+` | 저장소 루트 파일/디렉토리 목록 정확 일치 | 정산 관련 항목 없음(새 top-level 파일/디렉토리를 만들지 않는 한 무관) |
| PTC 기타 인벤토리 | `test_ptc_physical_exactness.py:176,188` | `static/js/runtime/`, `foms/services/common/` 파일 인벤토리 정확 일치 | 정산 파일은 이 두 디렉토리에 안 들어가므로 무관 |
| 정산 자산 캐시 핀 유일성 | §5.1 상단 | 신규 CSS/JS 자산마다 핀 계약 2벌 필요 | 네이버 탭이 새 CSS/JS 파일을 만들면 이 패턴을 그대로 복제해야 함 |
| audit_message_display 라벨 | `tests/domains/test_audit_action_coverage.py`(`:314` `test_wired_paths_do_not_write_security_log_directly`, `:323` `test_wired_paths_build_sentences_with_the_display_ssot`) | 새 감사 action은 라벨 등재 필수(메모리 기록과 일치) | **정산 대시보드 자체는 GET-only라 미해당**(`docs/plans/2026-08-31-settlement-dashboard-mockup-ledger.md` T14: "GET 전용이라 manifest 2종 등재 불요"). 네이버 탭도 읽기 전용이면 무관, 새 mutation(예: "재동기화" 버튼)을 추가하면 해당됨 |
| FINANCE_MUTATION 라우트 manifest | `docs/harness/foms_order_mutation_policy_manifest.json:488-491`(`erp_orders_completion.api_settlement_issue` 예시) | POST/PUT/PATCH/DELETE 라우트는 이 manifest에 등록돼야 `enforce_order_mutation_policy` 게이트가 인식 | 기존 실무 탭 버튼(`payment-confirm`/`settlement/issue`)은 이미 등록됨(신규 아님). 네이버 탭에 새 mutation route를 추가하면 이 manifest에 항목 추가 필요 |

**결론**: 네이버 정산 데이터가 **읽기 전용**(네이버 API 5종 다 GET)이고 새 최상위 디렉토리를 만들지 않는 한, closed-set/PTC/audit manifest 게이트는 대부분 회피 가능하다. 유일하게 반드시 새로 만들어야 하는 계약은 **자산 캐시 핀 계약**(CSS/JS 신규 파일마다)과 **탭 렌더 계약 테스트**(§5.1 표) 자체다.

---

## 6. 최근 히스토리 및 동시 작업 브랜치

### 6.1 관련 파일 최근 커밋 (`git log --oneline -15`)

```
416a3acfc fix(settlement): 정산 자산 핀 4개를 20260902b 로 통일 — 공통 핀 계약 CI red   ← 현재 워크트리 base
606a178e3 fix(settlement): 집중 모드가 글로벌 헤더·nav 를 못 접던 문제 — .d-flex !important 에 밀림
796d26982 feat(settlement): 정산 대시보드 폭·높이 개편 — 1440 캡 해제·차트 확대·집중 모드
0784ea5e3 perf(settlement): 실무 탭 aging 스트립 6요청을 1요청으로 — 서버가 구간 합계를 함께 낸다
846f8262f fix(settlement): 비교선이 막대를 누르던 문제 + 실무 탭 정렬을 미수 우선으로
2853f28a3 feat(settlement): 분석 탭에 매출 추이 카드 복원 — 목업 v3 span8 (사용자 결정)
7c09a312e feat(settlement): 실무(경리·수금) 탭 — 주문 단위 수금 목록 + 입금 확인·정산 청구
0347d7490 feat(settlement): 분석 탭 화면 — 목업 v3 이식 + 로딩·오류 무음실패 수정
8a5d0650b feat(settlement): /erp/settlement 한 화면에 탭 3개 — 요약·실무·분석 셸
4e9a32fa2 feat(settlement): 분석 탭 집계 확장 — 담당자별 매출·수금 분리·AS 전체·이전 기간 스칼라
2a927d55e feat(settlement): 실무 탭 주문 행 표면 — 별도 API + 노출 계약 분리
aa12fe80c fix(settlement): 메인 차트가 라인처럼 보이던 문제 — 목업 막대 외형 복원 + 툴팁 위치 파손
5e2ce9709 feat(settlement): M3 정산 대시보드 화면 — 목업 확정본 이식
```

방향: M1(집계 서비스)→M2(권한+API)→M3(화면 이식)→SETTLE-TABS(탭 3종 셸+분석 확장+실무 행 표면)→성능(aging 6요청→1요청)→UI 폭·높이 개편+집중 모드→자산 핀 통일. **현재 최신 상태는 "폭·높이·집중 모드까지 다 반영된 안정 버전"**이고, 다음 자연스러운 단계가 이번 네이버 탭 추가다.

### 6.2 브랜치 전수 (`git branch -a | grep settle`)

```
+ feat/settlement-wide            (origin/deploy 와 tip 동일 416a3acfc, 고유 커밋 0)
  promo/settle-perf-20260901      (이미 merge, origin/deploy 대비 새 커밋 0 초과분은 merge PR 흔적뿐)
+ session/settle-dash             (M1~M3 구현 세션, 전부 merge 완료)
* session/settle-naver            (본 워크트리 — 이 리서치 세션)
+ session/settle-perf             (하트비트/fragver 관측 세션, 정산 UI와 무관한 별개 작업)
+ session/settle-tabs             (SETTLE-TABS 세션, 전부 merge 완료)
```

각 브랜치의 `git log origin/deploy..<branch>` 결과, `session/settle-dash`/`session/settle-tabs`/`promo/settle-perf-20260901`의 고유 커밋은 모두 이미 위 §6.1의 `git log`에 나타난 커밋들과 동일(= 이미 `origin/deploy`에 반영됨). `session/settle-perf`는 이름에 "settle"이 들어가지만 실제로는 프래그먼트 버전 키/하트비트 관측(fragver) 작업으로, 정산 대시보드 UI와 무관한 별개 세션이다.

**결론: 정산 대시보드 UI를 현재 동시에 건드리고 있는 다른 세션은 없다.** 충돌 위험은 낮다. 단, 이 조사는 스냅샷이므로 실제 구현 착수 직전에 `git fetch && git log origin/deploy..origin/deploy` 재확인을 권장(메모리: "긴 작업은 중간에도 fetch·겹치면 상류 기준 새 브랜치로 잔여만 얹기").

---

## 7. 확장 레시피

### 7.1 레시피 A — "네이버 정산" 4번째 탭을 새로 만드는 경우

정확한 삽입 지점(파일:라인):

1. **템플릿 — 탭 버튼 추가**: `templates/cs/partials/settlement_dashboard_body.html:74-78`(분석 탭 버튼) 뒤에 4번째 `<button role="tab" data-settlement-tab="naver" aria-controls="foms-settle-pane-naver" aria-selected="false" tabindex="-1">` 추가. `id="foms-settle-tab-naver"`.
2. **템플릿 — pane 추가**: `:246-382`(분석 pane) 뒤에 `<div class="s-pane" role="tabpanel" id="foms-settle-pane-naver" data-settlement-pane="naver" aria-labelledby="foms-settle-tab-naver" tabindex="0" hidden>` + 내부에 `#foms-settle-naver-mount`(실무 탭 패턴을 따르면 `{% include 'cs/partials/settlement_naver_body.html' %}`로 분리 가능).
3. **새 partial(선택)**: `templates/cs/partials/settlement_naver_body.html` 신설 — `settlement_operations_body.html`을 템플릿으로 삼되 데이터 속성 접두어를 `data-settlement-nv-*`로 분리(요약/실무와 충돌 방지, §2.3 규율과 동일).
4. **새 API**: `foms/api/cs/settlement.py`에 `GET /api/settlement/naver`류 엔드포인트 추가(같은 `settlement_api_bp`, 같은 `can_view_settlement_dashboard()` 게이트 재사용 — 신규 권한 정책 불필요, `SETTLEMENT_DASHBOARD_READ` 그대로 재사용).
5. **새 서비스**: `foms/services/cs/settlement_naver.py`(또는 `foms/services/integrations/naver_commerce/settlement.py` — API 클라이언트 호출은 후자, 집계 가공은 전자 권장) — **워커 전용 호출 제약**(브리프 §"알려진 제약") 때문에 web 프로세스에서 네이버 API를 직접 부르면 안 된다. `tasks.py`에 정산 데이터 수집 잡을 추가하고, DB에 적재된 스냅샷을 웹이 읽는 구조가 필요(기존 `naver_commerce/ingest.py`+`watermark.py` 패턴 재사용).
6. **JS — 독립 파일 신설 권장**: `static/js/settlement/naver.js`(operations.js 패턴 그대로: `ROOT_SELECTOR`/`window.__FOMS_SETTLEMENT_NAVER_BOUND` 싱글톤, `watchTabActivation`으로 첫 로드 지연). `dashboard.js`의 `renderAll()`(`:1609`)에 새 탭 렌더 함수를 등록하지 **않아도 된다** — naver.js가 operations.js처럼 자기 자신을 MutationObserver로 독립 배선하면 dashboard.js를 건드릴 필요가 없다(단, dashboard.js의 `collectEls().tabs/panes`는 querySelectorAll이라 자동으로 4번째 탭 버튼/pane을 인식하므로 탭 전환 자체는 별도 코드 없이 동작).
7. **CSS — 새 파일**: `static/css/settlement/settlement-naver.css`(`.s-nv-` 접두어, `.foms-settle` 스코프 안에 선언, `--s-*` 토큰 재사용).
8. **자산 링크+핀**: `templates/cs/partials/settlement_dashboard_body.html:20-21`/`388-389` 옆에 새 `<link>`/`<script defer>` 2줄 추가, `?v=` 신규 핀(예: `20260902c`) — **기존 4개 자산의 핀과 다른 값이어도 무방**(테스트는 "자산당 1곳"만 검사, 자산 간 핀 값 통일을 요구하지 않는다 — 단 관례상 같은 날 작업이면 같은 값을 씀).
9. **테스트 갱신(필수, 안 하면 기존 계약이 새 탭을 놓치거나 새 코드가 계약 위반으로 red)**:
   - `tests/domains/test_settlement_dashboard_render.py`의 `_TABS`(`:180-187`)에 `("naver", "foms-settle-tab-naver", "foms-settle-pane-naver", "네이버 정산")` 추가 → `test_tab_bar_renders_three_tabs_with_expected_wiring`(`:1053`) 등 관련 함수가 "3개"를 전제하고 있다면 함수명·assertion을 4개로 갱신.
   - 새 CSS/JS 자산이면 `_STATIC_ASSETS`(`:79`)에 추가하거나, `test_settlement_operations_render.py`처럼 **독립 테스트 파일**(`test_settlement_naver_render.py`)을 신설해 §5.1/§5.2 표의 패턴(자산 실재·핀·defer·외부CDN 0·인라인스타일 금지·목업잔재·자기 상태노드 소유)을 그대로 복제하는 편이 기존 파일 비대화를 막는다(실제로 operations가 이 방식을 택함).
   - `test_settlement_dashboard_api.py`의 `test_actor_matrix_is_the_finance_matrix`류는 새 API가 같은 정책 상수를 쓰면 자동 통과(신규 정책 등록 불필요).

### 7.2 레시피 B — 기존 탭(분석)에 네이버 데이터 섹션만 추가하는 경우

실제 선례가 이미 저장소에 있다(`docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md` §S2/§S4, "탭3 분석 집계 확장" — 담당자별 매출·수금 분리·AS 전체를 나중에 추가한 이력). 같은 절차를 밟으면:

1. **커널 확장, 신규 쿼리 0 지향**: `settlement_aggregation.py`의 `_load_rows()`(`:515-526`) SELECT에 네이버 정산 관련 컬럼(예: 커미션/정산예정일 등, `ExternalOrderLink` 조인 또는 별도 네이버 정산 스냅샷 테이블 조인)을 추가 — 기존 사례는 컬럼 2개(`manager_name`, `as_axis_status`)만 더해서 새 파생 3종을 만들었다.
2. `aggregate_settlement()`의 반환 dict(`:1010-1029`)에 새 키(예: `naver_settlement`) 추가 → **`test_settlement_aggregation.py`의 스키마 정확 일치 계약이 즉시 red** — 의도된 설계, 함께 갱신(선례 주석: "커널 반환 스키마에 키를 더하면 계약 테스트 4곳이 즉시 red — 의도된 설계라 함께 갱신한다").
3. **API**: `foms/api/cs/settlement.py`의 `api_settlement_aggregates()`는 `aggregate_settlement()` 반환을 그대로 jsonify하므로 **API 코드 수정 불필요** — 단 `test_api_success_envelope_and_m1_schema`(`test_settlement_dashboard_api.py:375`) 스키마 계약을 갱신.
4. **템플릿**: `templates/cs/partials/settlement_dashboard_body.html:318-378`(단계별/부서별/수금/AS 카드들)과 같은 자리에 `<div class="s-card s-span4" id="foms-settle-an-naver-card">` 카드 신설(분석 탭 `.s-agrid` 안, `s-span4`/`s-span8` 중 선택).
5. **JS**: `renderAnalytics(ctx)`(`dashboard.js:1595-1607`)에 `renderAnalyticsNaver(ctx)` 함수를 추가 등록(기존 `renderAnalyticsChannels`/`renderAnalyticsManagers` 옆). `collectEls()`(`:1848-1935`)에 새 카드의 앵커(`anNaver...`)를 추가.
6. **CSS**: 기존 `.s-blist`/`.s-brow`/`.s-duo` 등 분석 탭 공용 클래스(§4.2)를 재사용하면 CSS 신규 작성 최소화 가능.
7. **권한**: 네이버 정산 데이터가 재무 민감 정보라면 `can_view_manager_breakdown()`처럼 별도 게이트 함수를 새로 만들지, 기존 `SETTLEMENT_DASHBOARD_READ` 그대로 쓸지 결정 필요(선례는 "신규 PII 획득 actor 0"을 사용자 승인 근거로 삼았다 — 네이버 정산 데이터도 같은 논증 절차 필요).
8. **테스트**: `test_settlement_dashboard_render.py`의 `test_analytics_cards_are_server_rendered`(`:1425`, 파라미터화된 카드 목록)에 새 카드 이름/앵커 추가, `test_analytics_omits_the_cards_without_backing_data`(`:1639`)에 빈 상태 케이스 추가.

### 7.3 판단 보류 사항 (브리프 §목표 "결정 필요" 항목에 대한 아키텍처 관점 시사점)

- **레시피 A(별도 탭)**가 기존 계약과의 마찰이 적다 — 실무 탭이 이미 "독립 API+독립 JS+독립 상태노드" 패턴으로 완전히 격리되어 있고, 탭 등록 자체는 `collectEls()`의 `querySelectorAll`이 자동 인식하므로 셸 쪽 변경이 작다.
- **레시피 B(기존 탭 업그레이드, 특히 분석 탭)**는 "커널 스키마 확장 → 계약 테스트 갱신"이 이미 검증된 패턴이라 데이터가 **적은 양**이고 **기존 지표와 자연스럽게 어울리는 경우**(예: 네이버 채널 매출을 기존 "채널별 매출 비중" 카드에 세분화) 적합하다.
- 네이버 정산 API 5종이 "**모든** 데이터를 보여주고 그래프 시각화까지" 요구하는 브리프 목표 규모라면, 레시피 A(별도 탭)가 화면 밀도·로딩 지연(전용 lazy-load) 관점에서 더 안전하다 — 이는 설계 판단이며 최종 결정은 회계팀 페르소나 리서치(다른 산출물)와 함께 사용자 승인이 필요하다.
