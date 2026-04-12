# Step 6 Large File Decomposition Inventory

> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 분리된 전용 스펙: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`

## 1. 목적

Step 6의 목적은 “지금 바로 대형 파일을 분해하는 것”이 아니라, 현재 남아 있는 monolithic hotspot을 **정확히 inventory**하고 이후 execution batch가 따라야 할 **별도 decomposition spec**의 입력값을 고정하는 것이다.

이번 inventory는 다음 원칙을 따른다.

- 구조 개편 PR에 실제 대형 리팩터링을 섞지 않는다.
- `business_calendar` module과 `/calendar` 축은 사용자 지시대로 계속 제외한다.
- generated bundle과 tooling-only giant file은 product runtime 분해와 분리한다.
- 실제 분해는 future batch에서 contract freeze + verification baseline을 먼저 깔고 진행한다.

## 2. 스캔 기준

- Python: 500줄 초과
- HTML/Jinja template: 800줄 초과
- JS: 300줄 초과
- CSS: 500줄 초과

## 3. Threshold Scan Summary

### 3.1 Python hotspots

| 경로 | 줄 수 | 메모 |
|------|------:|------|
| `apps/api/orders.py` | 911 | nearby geocode + calendar + field/status mutation 혼재 |
| `apps/api/chat/routes.py` | 889 | upload + rooms + messages + page route 혼재 |
| `foms/services/erp_policy.py` | 764 | canonical policy engine, business day helper 결합 |
| `apps/api/wdcalculator.py` | 710 | WDCalculator API + 별도 DB lifecycle |
| `apps/api/attachments.py` | 641 | storage/presign/upload/search + schema ensure 혼재 |
| `models.py` | 612 | persistence 계약 중심, separate track 필요 |
| `apps/api/erp_map.py` | 594 | map page + JSON API + geocode/address helper 혼재 |
| `foms/services/channel_wam_service.py` | 569 | canonical WAM service hotspot |
| `foms/services/storage.py` | 526 | canonical storage abstraction hotspot |
| `apps/api/events.py` | 526 | event/revert machinery 집중 |
| `apps/erp_dashboard.py` | 524 | page blueprint 단일 파일 hotspot |
| `apps/api/notifications.py` | 506 | notification/realtime API hotspot |

### 3.2 HTML/Jinja hotspots

| 경로 | 줄 수 | 메모 |
|------|------:|------|
| `templates/wdcalculator/partials/wdcalculator_scripts.html` | 3493 | 최대 인라인 JS partial |
| `templates/partials/erp_beta_js.html` | 2516 | shared ERP Beta inline JS monolith |
| `templates/layout.html` | 2196 | global shell + notification/badge inline script/style |
| `templates/regional_dashboard.html` | 2161 | 대형 dashboard template |
| `templates/partials/erp_dashboard_styles.html` | 1498 | dashboard CSS-in-template hotspot |

### 3.3 JS hotspots

| 경로 | 줄 수 | 메모 |
|------|------:|------|
| `static/js/measurement/dashboard.js` | 574 | Step 5 이후 canonicalized 되었지만 여전히 큰 단일 JS |
| `static/js/wam/attachments.js` | 479 | WAM attachment UI logic 집중 |

### 3.4 CSS hotspots

| 경로 | 줄 수 | 메모 |
|------|------:|------|
| `static/css/erp-pro.css` | 3595 | 전역 ERP style monolith |
| `static/css/style.css` | 1020 | legacy global style monolith |

## 4. Priority Inventory Matrix

### 4.1 Tier A — Step 6에서 반드시 inventory/spec에 명시할 대상

| 경로 | 줄 수 | 현재 역할 | 왜 지금 잡아야 하는가 | 권장 future target |
|------|------:|------|------|------|
| `apps/api/orders.py` | 911 | 주문 API + nearby + calendar + field/status mutation | 주문 도메인의 가장 큰 backend hotspot이며 route layer에 geocode/JSONB mutation/permission 계약이 과집중되어 있다 | `foms/api/orders/*` thin adapter + `foms/services/order_*` |
| `templates/wdcalculator/partials/wdcalculator_scripts.html` | 3493 | WDCalculator inline JS partial | 가장 큰 frontend hotspot이며 Jinja data injection, DOM render, fetch, local state가 한 파일에 섞여 있다 | thin partial + `static/js/wdcalculator/*` |
| `templates/partials/erp_beta_js.html` | 2516 | ERP Beta shared inline JS | shared UI contract가 넓고 add/edit order flow 전반이 여기에 묶여 있다 | `static/js/erp/beta/*` + thin include |
| `apps/api/chat/routes.py` | 889 | chat upload/room/message/page route | upload, preview/download, room/member, message 검색이 한 모듈에 공존한다 | `foms/api/chat/*` + `foms/services/chat_*` |
| `foms/services/erp_policy.py` | 764 | canonical ERP policy engine | 이미 canonical source라 경로 이동보다 내부 package split 전략을 별도로 정의해야 한다 | `foms/services/erp_policy/*` internal package |
| `static/css/erp-pro.css` | 3595 | 전역 ERP design/style layer | page/component/layout selector가 한 파일에 누적되어 이후 분해 기준을 먼저 정해야 한다 | `static/css/erp/*` logical slices |

### 4.2 Tier B — inventory에는 넣고 분해는 wave 2 이후로 미루는 대상

| 경로 | 줄 수 | 이유 | 권장 future target |
|------|------:|------|------|
| `apps/api/wdcalculator.py` | 710 | WDCalculator domain API이지만 별도 DB lifecycle을 유지해야 하므로 stepwise split이 필요 | `foms/api/wdcalculator/*` + `foms/services/wdcalculator_*` |
| `apps/api/attachments.py` | 641 | R2/presign/upload/search/patch/delete가 결합되어 있어 storage contract freeze가 선행돼야 한다 | `foms/api/attachments/*` + existing storage services |
| `apps/api/erp_map.py` | 594 | map page + JSON + address/geocode helper가 혼재하며 measurement 이후 다음 map-side inventory 대상이다 | `foms/api/erp_map/*` + map service helpers |
| `apps/api/events.py` | 526 | revert/change-event logic이 route module에 집중 | `foms/api/events/*` + `foms/services/events_*` |
| `apps/api/notifications.py` | 506 | notification send/read/update와 realtime UI 계약이 맞물려 있다 | `foms/api/notifications/*` + existing realtime services |
| `templates/layout.html` | 2196 | global shell과 badge/notification script가 넓은 암묵 계약을 가진다 | partial split + `static/js/layout-*` + `static/css/layout-*` |
| `templates/regional_dashboard.html` | 2161 | 대형 dashboard markup/script hotspot | `templates/regional_dashboard/*` partials + static JS |
| `templates/partials/erp_dashboard_styles.html` | 1498 | dashboard CSS-in-template monolith | static CSS split or sub-partials |
| `static/js/measurement/dashboard.js` | 574 | Step 5 결과물이라 당장 분해보다 canonical contract 유지가 우선이다 | `static/js/measurement/*` internal modules |
| `static/js/wam/attachments.js` | 479 | attachment UI state/event 분리가 가능하지만 WAM event contract 정리가 먼저다 | `static/js/wam/*` internal modules |
| `static/css/style.css` | 1020 | legacy global style이지만 `erp-pro.css`보다 우선순위는 낮다 | `static/css/base/*` |
| `apps/erp_dashboard.py` | 524 | page blueprint hotspot이지만 template/JS inventory가 먼저다 | `foms/web/erp_dashboard/*` |

### 4.3 Tier C / deferred — separate track 또는 명시적 제외

| 경로/영역 | 줄 수 | 처리 방향 |
|-----------|------:|-----------|
| `business_calendar` / `/calendar` | 제외 | 사용자 지시대로 migration scope 밖 유지 |
| `models.py` | 612 | persistence/schema track으로 분리, Step 6 execution 대상 아님 |
| `tests/test_foms_namespace_imports.py` | 1483 | test-only giant file, product runtime decomposition과 분리 |
| `tools/research_center/coding_research_center.py` | 1223 | tooling-only, separate tools governance track |
| `foms_map_generator.py` | 918 | standalone generator, separate tools/scripts track |
| `static/wdplanner/assets/index-*.js` | generated | hand-authored decomposition 대상이 아니라 build output/dedup 문제 |
| `backups/` tree | 제외 | runtime/source-of-truth inventory 대상 아님 |

## 5. Candidate-specific decomposition boundaries

### 5.1 `apps/api/orders.py`

- `GET /orders/nearby`: geocode, route scoring, `ThreadPoolExecutor`, fallback logic를 서비스 레이어로 분리
- `GET /orders`: FullCalendar projection/query shaping을 별도 projection helper로 분리
- `POST /update_order_field`: allowlist, `structured_data`, `flag_modified`, `sync_erp_flat_columns`, geocode enqueue를 mutation service로 분리
- `POST /update_order_status`, `POST /bulk_update_order_status`: status/trash semantics와 `OrderEvent` 생성 책임을 분리

### 5.2 `templates/wdcalculator/partials/wdcalculator_scripts.html`

- Jinja data injection을 먼저 `data-*`/config node로 축소
- base components / notes / products / estimate calculation / sidebar persistence / save-refresh를 모듈 경계로 분리
- inline style-heavy render block은 JS 분리와 별개로 별도 hardening 항목으로 취급

### 5.3 `templates/partials/erp_beta_js.html`

- payment, structured data, address search, item rows, AS receive modal, attachment patching을 feature block으로 분해
- shared global(`ORDER_ID`, `ERP_BETA_ENABLED`, `window.__ERP_*`) contract를 먼저 freeze

### 5.4 canonical service/CSS 계열

- `foms/services/erp_policy.py`: 내부 package split 우선, external import path churn 최소화
- `static/css/erp-pro.css`: token/layout/component/page 계층으로 logical split, selector rename은 separate batch

## 6. Contract Freeze and Test Gap Notes

### API candidates

- route path, method, JSON shape를 golden/contract test로 먼저 고정한다
- queue job path/enqueue call은 Step 3에서 다룬 canonical contract를 유지한다
- `structured_data` mutation은 `copy.deepcopy` + `flag_modified` 계약을 유지한다

### Template/JS candidates

- DOM id/class/data attribute와 `window.*` global name을 public surface로 간주한다
- load order와 include chain을 바꾸는 순간 thin wrapper/shim 또는 explicit smoke가 필요하다
- automation gap이 큰 영역(`wdcalculator_scripts.html`, `layout.html`)은 최소 manual checklist를 함께 둔다

### CSS candidates

- selector rename/삭제와 logical file split을 분리한다
- visual behavior를 바꾸지 않는 범위에서만 Step 6 이후 first split을 허용한다

## 7. Recommended execution order after Step 6

1. `apps/api/orders.py` contract freeze + separate execution plan
2. `templates/wdcalculator/partials/wdcalculator_scripts.html` contract freeze + static extraction plan
3. `templates/partials/erp_beta_js.html` decomposition plan
4. `apps/api/chat/routes.py` decomposition plan
5. canonical `foms/services/erp_policy.py` internal package split plan
6. `static/css/erp-pro.css` logical split plan

## 8. Interpretation

- Step 6 결과는 “다음에 무엇을 쪼갤지”를 정한 것이지 “지금 쪼갰다”는 뜻이 아니다.
- root governance spec은 Step 6 완료와 다음 자동 단계만 유지하고, future large-file execution rule은 전용 spec으로 넘겨야 한다.
- `business_calendar` / `/calendar` 축은 이번 inventory에서도 끝까지 제외한다.
