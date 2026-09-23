# 실측 모바일: "다음 방문" 히어로 → 오늘 체크리스트 + 이미지 저장 — 작업 브리프 (초안 · 스펙 승인됨)

> 2026-09-23 · 사용자 확정 디자인 = 목업 A안 "오늘 체크리스트".
> 목업: `C:\Users\USER\AppData\Local\Temp\claude\c--DEV-FOMS\2e387428-3d04-4e33-9305-52c837834463\scratchpad\measure-glance-v7.html` (A 탭).
> 이 브리프는 **초안**이다. CEO 는 계약을 고칠 수 있다. 단 아래 "이름 고정" 표의 이름은 바꾸지 않는다(워커·테스트가 병렬로 같은 이름을 쓴다).

## 1. 사용자 요구 (원문 요지)
1. 모바일 실측 화면의 "다음 방문" 히어로(`foms-v2dh-hero`)를 **삭제**하고, 그 자리에 한눈에 보는 목록을 넣는다. **아래 실측 카드(queue-card-v2)는 그대로.**
2. 목록 머리에 **이미지 저장** 버튼. 저장 결과는 **PC 에서 저장되는 PNG 와 완전히 같아야 한다**(열 간격·폰트·제목·담당자 간격 줄까지). `mine`(내 일정) 상태면 자기 일정만.
3. 목록의 주문 줄을 누르면 아래 해당 주문 카드로 스크롤 이동.
4. 체크 칸 = **"실측만 완료"**(카드의 "실측 완료"=도면 넘김 버튼과 다른 개념). 저장 계약은 승인된 스펙 `docs/specs/2026-09-23-measurement-visit-check_SPEC.md` 가 정본.
5. 담당자 이름 또는 전화 버튼을 누르면 바로 전화(`tel:`).
6. 설명성 주석 문구(예: "어제 17:00 확정 일정 · 시간은 예정…")는 화면에 넣지 않는다.

## 2. 도메인 사실 (설계 제약 — 어기면 틀린 안내가 된다)
- 방문 시간은 **전날 17시경 확정된 예정값**이다. 당일에는 영업 담당이 고객과 직접 조율해 시간·순서가 바뀌고 **ERP 에 반영하지 않는다.**
- 따라서 목록에 **"다음 방문"·ETA·시간순 강조·"바뀜" 배지·자동 재정렬을 만들지 않는다.** 시간은 작은 회색 글자로만 보여 준다.
- 당일 ERP 에서 믿을 수 있는 신호 = 오늘 명단 + 새 방문 체크(`measurement_visits`). `measurement_completed`·카드의 "실측 완료" 버튼은 **도면 넘김** 개념이라 체크리스트 수치에 쓰지 않는다.
- 이미지 저장의 주 사용 시점 = 전날 17시 확정 직후 **내일 날짜**를 골라 단톡방 공유. 저장은 **선택한 날짜**(`selected_date`)를 따른다.

## 3. 앵커 (경로:행 — origin/deploy `dc33f64ef` 기준)
- 히어로 블록: `templates/measurement/partials/mobile_list.html:1-66` (주석·`_mhero` 계산·`foms-v2dh-hero`). 요약줄 `foms-visit-summary`(16-24)과 0건 상태 `foms-v2dh-status`(66-80)는 **유지**. 카드 목록 `erp-measurement-mobile-card`(92-106).
- 히어로 행 선정: `foms/web/measurement/dashboard.py:482-497`(`mobile_hero_row`, `mobile_hero_time_hm`), 컨텍스트 전달 `:567-568`. 다른 템플릿에서 안 쓴다(grep 확인됨).
- 모바일 큐 행 dict: `dashboard.py:462-480` — `rows` 와 **같은 순서**. 키: `id, customer_name, address, product_subtitle, manager_name, measurement_completed, structured_data, channel_source` 등(`build_mobile_queue_order_row`).
- PC 이미지 저장: `static/js/measurement/image-export.js` 전체(442줄). `#btn-export-image` 1개만 바인딩, `document.querySelector('.measurement-table')` 캡처, `onclone` 에서 `prepareExportTable`.
- PC 표 마크업: `templates/measurement/partials/dashboard_main.html:790-925` (`.measurement-table`, `data-col-key`, `tr.measurement-row`, `td.manager-cell[data-bg]`, `td.meas-time-cell[data-daypart]`). 이 표는 **모바일에서도 DOM 에 있지만 CSS 로 숨겨져** 있다(`erp-measurement-desktop-shell`).
- 모바일 v2 표면 조립: `dashboard_main.html:58-66` (`mobile_filters`·`mobile_dates`·`mobile_list` include). v3 셸에서는 이 표면이 안 뜬다(`shell_variant != 'v3'`) — 범위 밖.
- JS 로드 체인: `static/js/measurement/measurement-entry.js:10-19` (`MEAS_JS_V = '20260901a'`), 스크립트 태그 핀 `templates/measurement/partials/dashboard_scripts.html:1` (`measurement_js_v = '20260901a'`).
- 페이지 CSS 링크 선례: `dashboard_main.html:5-6` (`measurement-sales-delivery.css` 를 이 partial 최상단에 link — 전체 페이지·프래그먼트 양쪽에 실린다).
- 공용 히어로 CSS(`foms-v2-domain-heroes.css`, `foms-route-strip.css`)는 시공·v3 가 같이 쓴다 → **삭제·수정 금지.**

## 4. 계약 — 이름 고정
| 대상 | 고정 이름 |
|---|---|
| 목록 패널 | `<section class="foms-meas-glance" data-meas-glance aria-label="실측 한눈 목록">` (히어로 자리, 요약줄 바로 아래. `mobile_queue_rows` 있을 때만) |
| 머리 | `.foms-meas-glance__head` · 제목 `.foms-meas-glance__title` · 수치 `.foms-meas-glance__count` ("N곳 · 실측 d · 남은 r", d = `measurement_visit_done` 수) |
| 서버 행 키 | `mobile_queue_rows` 각 행에 `measurement_visit_done`(bool: `structured_data.measurement_visits` 에 `selected_date` 키 존재) — `dashboard.py` 행 조립 루프, 새 쿼리 0 |
| 체크 API | `POST /api/orders/<id>/measurement-visit` body `{date, done}` → `{success, data:{date,done,at,by_name,changed,mutation_receipt}, error}` (스펙 §3) |
| 저장 버튼 | `<button type="button" class="foms-meas-glance__save" data-meas-export-image>` 아이콘 `fa-file-image` + "이미지 저장" |
| 담당자 묶음 | `.foms-meas-glance__grp` / 머리 `.foms-meas-glance__gname`(이름 + 진행 막대 `.foms-meas-glance__prog` + "실측 d/n"). 이름은 `manager_phone` 있으면 `<a class="foms-meas-glance__mgr" href="tel:{{정규화 번호}}" data-queue-card-call-link>` + 전화 아이콘 버튼 `<a class="foms-meas-glance__call" href="tel:…" aria-label="{{담당자}} 전화">`, 없으면 텍스트 — 담당자가 바뀔 때마다 새 묶음(행 순서 그대로, 재정렬 금지) |
| 줄 | `<div class="foms-meas-glance__row{% if o.measurement_visit_done %} is-done{% endif %}">` 안에 ① 체크 버튼 `<button type="button" class="foms-meas-glance__check" data-meas-visit-toggle="{{id}}" data-meas-visit-date="{{selected_date}}" aria-pressed="true|false" aria-label="{{고객명}} 실측 체크">`(`can_edit_erp` 거짓이면 `disabled`) ② `<a class="foms-meas-glance__go" href="#meas-card-{{id}}" data-meas-glance-go="{{id}}">` 이름 `.foms-meas-glance__name`(+ `channel_mark(o.channel_source|default(none, true))`), 주소 `.foms-meas-glance__addr`, 제품 `.foms-meas-glance__prod`, 시간 `.foms-meas-glance__time`(schedule.measurement.time 원문, 없으면 생략) |
| 카드 앵커 | 기존 `.erp-measurement-mobile-card` div 에 `id="meas-card-{{ o.id }}"` 추가(그 외 카드 마크업 불변) |
| 이동 강조 | 대상 카드 div 에 `is-glance-flash` 클래스 1800ms |
| 새 CSS | `static/css/contexts/measurement/measurement-mobile-glance.css` — `dashboard_main.html` 최상단 link(선례와 같은 자리), `?v=20260923a` |
| 새 JS | `static/js/measurement/mobile-glance.js` — 줄 클릭 → 카드 스크롤+강조. entry CHAIN 에 추가 |
| JS 핀 | `MEAS_JS_V`·`measurement_js_v` → `'20260923a'` (테스트가 옛 핀을 복제해 단언하면 같이 올린다 — `grep -rn "20260901a" tests/`) |

## 5. 이미지 저장 계약 (가장 중요)
- **PC 경로 무변경**: 데스크톱에서 `#btn-export-image` 를 누르면 지금과 바이트 단위로 같은 PNG.
- 모바일 버튼 `[data-meas-export-image]` 도 **같은 함수**(`prepareExportTable` 과 같은 캡처 옵션·파일명·제목)로 찍는다. 흉내 금지.
- 모바일에서는 `.measurement-table` 이 숨겨져(`getClientRects().length === 0`) 크기가 0 이다. 해결: 실제 표를 `cloneNode(true)` 해서 화면 밖 호스트(`position:fixed; left:-100000px; top:0; width:2400px` 같은 CSS 클래스 — 인라인 style 금지, 새 CSS 파일의 클래스)에 붙이고 그 클론을 캡처한 뒤 제거한다. `onclone` 안에서 캡처 대상은 `document.querySelector('.measurement-table')`(=숨은 원본) 이 아니라 **클론을 가리키는 표식**(예: `data-meas-export-target`)으로 찾는다. PC 경로에서도 같은 표식 방식으로 통일하되 결과가 같아야 한다.
- 행 범위: 서버가 이미 `mine`·날짜·검색을 반영한 `rows` 로 PC 표를 그리므로 클론도 같은 행 = 요구 2 자동 충족. 추가 필터링 금지.
- 파일 저장: PC 는 지금 방식(`<a download>`) 유지. 모바일(`navigator.canShare && navigator.canShare({files:[file]})`)이면 `navigator.share({files:[file]})` 로 공유창(아이폰 사진 저장·카카오톡), 사용자가 취소(AbortError)하면 조용히 끝, 그 외 실패는 `<a download>` 폴백.
- 0건이면 모바일 버튼은 `disabled`.
- html2canvas lazy 로드 규칙(G2) 유지.
- **의도된 예외 — 캡처 배율**(2026-09-23 통합 검증): PC 는 기존 공식(`max(2, min(dpr, 3))`) 그대로. 모바일(화면 밖 복제본)만 `min(2, sqrt(16777216 / (w*h)))` — iOS 캔버스 면적 한도(16,777,216px)를 넘으면 저장이 실패하기 때문. w·h 는 살아 있는 문서가 아니라 버리는 복제본에 `prepareExportTable` 을 적용해 잰다. 그래서 행이 많으면 모바일 PNG 해상도가 PC 보다 낮다(모양·열 간격·제목은 같다).
- 모바일 제목·파일명 날짜 = 서버가 표를 그린 날짜(`section[data-meas-glance-date]`, 비면 입력의 `defaultValue`). 필터 서랍의 적용 전 입력값을 읽지 않는다. PC 는 기존 규칙 그대로.
- 모바일 복제본은 PC 리사이저의 `.grip-resizable`(td·th `overflow:hidden`)이 없으므로 캡처 호스트 안에서만 같은 규칙을 준다(`measurement-mobile-glance.css`).

## 6. 파일 소유권 (워커별 편집 허용 — 겹치지 않는다)
| 워커 | 편집 허용 |
|---|---|
| W1 템플릿·CSS | `templates/measurement/partials/mobile_list.html`, `static/css/contexts/measurement/measurement-mobile-glance.css`(신규), `templates/measurement/partials/dashboard_main.html`(최상단 CSS link 1줄만) |
| W2 JS | `static/js/measurement/image-export.js`, `static/js/measurement/mobile-glance.js`(신규: 카드 이동·강조 + 체크 토글 fetch), `static/js/measurement/measurement-entry.js`, `templates/measurement/partials/dashboard_scripts.html`(핀 1줄) |
| W3 서버·API | `foms/api/orders/measurement_visit.py`(신규), `foms/api/orders/__init__.py`(라우트), `foms/api/erp_orders_structured.py`(`_OPERATIONAL_TOP_LEVEL_KEYS` 1줄), `foms/services/order_event_display.py`(라벨 2), `foms/web/measurement/dashboard.py`(히어로 계산 제거 + `measurement_visit_done`), 신규 `tests/domains/test_measurement_visit_api.py` |
| W4 화면 계약 테스트 | 기존 테스트 갱신(`tests/domains/test_dashboard_channel_mark.py` 의 `_mhero` 단언 등, 핀 복제 단언 `grep -rn "20260901a" tests/`) + 신규 `tests/domains/test_measurement_mobile_glance.py`(템플릿·JS·CSS 계약 문자열 + 모바일 렌더) |

화면 밖 캡처 호스트 CSS 클래스 이름은 `foms-meas-export-host` 로 고정(W1 이 CSS 작성, W2 가 사용).

## 7. 검증 명령 (워커 공통 — 각자 자기 몫 + 통합자는 전량)
```
cd c:/tmp/foms-s-meas-glance && pwd
python -c "import app; print('APP_OK')"
node --check static/js/measurement/image-export.js static/js/measurement/mobile-glance.js static/js/measurement/measurement-entry.js
python -m pytest -q tests/domains/test_measurement_mobile_glance.py tests/domains/test_measurement_visit_api.py tests/domains/test_channel_drawing_room_push.py tests/domains/test_drawing_wizard_autosave_guard.py tests/domains/test_dashboard_channel_mark.py tests/domains/test_erp_quest_display.py tests/domains/test_measurement_js_contract.py tests/domains/test_erp_measurement_mobile_render.py tests/domains/test_measurement_time_sort.py tests/domains/test_measurement_undated_ui_contract.py tests/domains/test_measurement_sales_delivery_render.py tests/domains/test_measurement_mobile_queue_query_count.py tests/visual/test_p1_mockup_structure.py tests/performance/test_page_local_defer_contract.py tests/performance/test_perf_regression_guard.py tests/domains/test_erp_runtime_shell_js_contract.py tests/domains/test_drift_ratchet.py tests/harness/test_file_size_ratchet.py
```
- 한글 출력: `PYTHONIOENCODING=utf-8`.

## 8. 공통 규칙·함정
- 작업 디렉터리는 `c:/tmp/foms-s-meas-glance` (명령마다 `cd c:/tmp/foms-s-meas-glance && pwd`). **git 명령 금지**(커밋·push 는 총괄).
- 줄바꿈 LF 유지(대상 파일 전부 LF 확인됨). UTF-8.
- 인라인 `style=` 금지(색 점·진행 막대 폭 포함) → CSS 클래스. 진행 막대 폭은 `<progress>` 또는 `<meter>` 요소나 data 속성+CSS 로. 담당자 색은 기존 팔레트가 queue 행에 없으면 중립 회색 점 하나로 통일(새 팔레트 발명 금지).
- 프래그먼트 스왑 재실행 안전(G4): 전역 리스너는 `window.__FOMS_MEAS_GLANCE_BOUND` 류 가드, 버튼 바인딩은 `data-*-bound` per-DOM 가드(기존 image-export 패턴).
- jQuery 금지. 새 JS 는 IIFE, `'use strict'` 불필요(기존 스타일 따름).
- docs 를 읽어서 단언하는 테스트 금지.
- `foms-hero-*`·`foms-v2dh-*` 공용 CSS 는 건드리지 않는다.
- 행 순서는 서버 순서 그대로(PC 표·PNG 와 같은 담당자 묶음). 번호("1, 2, 3") 달지 않는다.
