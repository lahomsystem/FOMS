# 워커 B 보고 원문 — 태블릿 표면·게이트·기능표 (2026-11-09)

> 원장 `2026-11-09-tablet-production-ui-ledger.md` §3.B 의 본문. 워커(Fable 5.1, effort high, 읽기 전용, 워크트리 `ea4376ea1`) 보고를 그대로 붙였다. 총괄 재확인 결과는 원장 §6 에.

## 표 1. 생산 보드 기능 1:1 (PC 그리드 / 태블릿 칸반 / 작업 시트 / 모바일 큐)

| 기능 | PC 그리드 | 태블릿 칸반 | 작업 시트 | 모바일 큐·바텀시트 | 근거 |
|---|---|---|---|---|---|
| 제작 시작 | 있다(관리자 경고 변형 포함) | 있다(열 이동 버튼, 도면 게이트면 칩) | 있다 | 있다(`can_act_production` 아니면 배지만) | `filters_grid.html:85-104` · `scripts.html:288-291` / `tablet_kanban_body.html:359-369` · `tablet-production-kanban.js:49-53,169-180` / `tablet_sheet.html:183-192` · `tablet-domain-sheets.js:139-145,734-737` / `mobile_queue.html:50-66` |
| 제작 완료 | **부분** — 그리드 행엔 "제작중" 배지만, 접힘 상세 패널 안 버튼 | 있다 | 있다 | 있다 | `filters_grid.html:105-107` · `scripts.html:675` / `tablet_kanban_body.html:370-373` / `tablet_sheet.html:196-197` / `mobile_queue.html:71-72` |
| 수정 제작(사유) | **없다(UI)** — 함수만 있고 버튼 없음("모바일 카드 data-action 용") | 있다 — `window.prompt` 사유 | 있다 — 공용 사유 시트 | 있다 | `scripts.html:298-325` / `tablet_kanban_body.html:374-377` · `tablet-production-kanban.js:58-63,78-83` / `tablet_sheet.html:201-202` · `tablet-domain-sheets.js:177-183` / `mobile_queue.html:73` |
| 제작 취소 | 없다(UI, 함수만) | **없다** | 있다(사유) | 있다 | `scripts.html:327-334` / 칸반 열 이동은 start·complete·rework 3종만 `tablet_kanban_body.html:26-28` / `tablet_sheet.html:194-195` · `tablet-domain-sheets.js:187-193` / `mobile_queue.html:74` |
| 완료 되돌림(uncomplete) | 없다(UI, 함수만) | **없다** | 있다 — confirm 만(사유 없음, PC·모바일은 사유 시트) | 있다 | `scripts.html:336-343` / `tablet_sheet.html:199-200` · `tablet-domain-sheets.js:197-201` / `mobile_queue.html:83` |
| 보류 / 보류 해제(사유) | **없다** — 409 `HOLD_ACTIVE` 재시도 confirm 만 | **표시만**(배지·스트립·KPI 보류 탭) + 409 자기해제 | **있다**(유일한 토글 표면, `/production/hold`) | **없다**(409 재시도만) | `scripts.html:221-225,261-271` / `tablet_kanban_body.html:231-236,281-300` · `tablet-production-kanban.js:149-157` / `tablet_sheet.html:176-182` · `tablet-domain-sheets.js:209-264` / `mobile_queue.html:71-87` |
| 공정 5단계 체크(재단·엣지·도장·조립·검수) | **없다** | **없다** | **없다** | 있다(카드 "공정 N/5" → 바텀시트 lazy GET/POST) | JS 는 항상 실림 `dashboard_body.html:161` 이지만 시트 마크업은 `mobile_queue.html:113` 에만 include, 트리거 `data-foms-prod-steps-open` 는 `mobile_queue.html:96` 에만 · `production_steps_sheet.html:38-50` · `foms-production-steps.js:167-188,281-300` · API `foms/api/production/orders.py:1398,1436` |
| 불량 보고(사유 4종) | 없다 | 없다 | 없다 | 있다 | `production_steps_sheet.html:52-68` · `foms-production-steps.js:251-269` · 화이트리스트 `orders.py:83,1522` |
| 변경 [확인](change-ack)·빨간 표시 | **없다**(change-ack 호출 0건) | 있다 — 카드 스트립·묘비·"변경 N" 필터·브리핑 모달·행별 확인 | 있다 — 변경 알림 + [변경 확인] + 확인된 이력 | **없다** | `tablet_kanban_body.html:195-247,96-103,328-392` · `tablet-domain-sheets.js:269-293,415-440` / `tablet_sheet.html:69-108` / `collect_production_change_alerts` 는 `dashboard.py:195-205` 가 행에 붙이지만 PC·모바일 템플릿은 안 그림 |
| ├ 도면 재전달(수정 중 배지, RETURNED·TRANSFERRED) | 있다 | 있다 | 있다 | 있다 | `filters_grid.html:65-67` / `tablet_kanban_body.html:238-247` / `tablet_sheet.html:22-24` / `erp_mobile_queue_card_v2.html:55-57` |
| ├ 도면 바뀜(바로 반영)·시공일 변경(from→to 빨강)·취소(묘비) | 없다 | 있다 | 있다(묘비 제외) | 없다 | `tablet_kanban_body.html:220-236(kind drawing/construction_date), 195-216(묘비)` / `tablet_sheet.html:76-87` |
| 도면 보기 | 첨부 모달(실측·도면·시공 탭, 여러 장, `GlobalImageViewer.open(list, index)`) | **없다** — 첨부 수 배지만 | **1장만**(현재 전달본 중 첫 이미지), 장 넘기기 불가, 바뀐 도면 구분 없음 | 카드 썸네일 5+N → 전역 뷰어 갤러리 | `modals.html:1-19` · `scripts.html:19-215,212-213` / `tablet_kanban_body.html:322-326` / `dashboard.py:383-407`(첫 항목에서 return) · `tablet_sheet.html:150-167,219-229`(단건 리스트) / `erp_mobile_queue_card_v2.html:109-189` · 뷰어 핀치·스와이프·더블탭 `layout-scripts-core.js:24-33,102-105` |
| 품목·규격·총 자수·특이사항 | 제품명만(열) | 품목·규격·재질·자수·취소품목 | 총 자수(W/300)·규격표·특이사항 | 제품 부제만(자수·특이사항 없음) | `filters_grid.html:127-137` / `tablet_kanban_body.html:270-291` / `tablet_sheet.html:110-147` / `erp_mobile_queue_card_v2.html:99-103` |
| 상차일/시공일/D-day | 시공일·실측일 열 + 경보 배지 D-n | 시공 M/D·D-day 칩(지연·임박 유채) — 상차일 없음 | "상차 M/D" 표기 — **값은 시공일**(`_prod_sheet_load_md(construction_date)`) | `queue_card_schedule` 필터 1줄(추정) | `filters_grid.html:138-149,45-59` / `tablet_kanban_body.html:343-358`(주석 `:5-8`) / `dashboard.py:434,445` · `tablet_sheet.html:29` / `erp_mobile_queue_card_v2.html:25-27` |
| 출고 배정(shipment update) | 없다 | 없다 | 없다(`shipment-assign` 은 출고 시트 전용) | 없다 | `tablet-domain-sheets.js:444-497` 는 있지만 `tablet_sheet.html` 에 버튼 없음 |
| 필터 — 공장 | 없다 | 있다(클라이언트) | — | 없다 | `tablet_kanban_body.html:85-89` · `tablet-domain-sheets.js:535-543` |
| 필터 — 검색 | 서버 `q` | 클라이언트 `textContent` 포함 검색(서버 `q` UI 는 CSS 로 숨김) | — | 서버 `q` | `filters.html:16` / `tablet_kanban_body.html:90` · `tablet-domain-sheets.js:531-533` · PC 필터 카드 은닉 `foms-tablet-production-kanban.css:88-90` / `mobile_filters.html:129-135` |
| 필터 — 단계·팀·긴급·경보 | 있다(단계 10종·팀 6종·긴급·경보 + 경보 타일·파이프라인 클릭) | **없다**(URL 파라미터만 살아 있음) | — | 단계 칩·서랍만 | `filters.html:23-57` · `dashboard_body.html:47-116` / `mobile_filters.html:156-195` |
| 필터 — 변경 | 없다 | 있다(토글, `changed_count` 강조) | — | 없다 | `tablet_kanban_body.html:96-103` · `tablet-domain-sheets.js:547-550` |
| 필터 — 내 것(mine) | 숨은 input(토글 UI 없음) | **없다** — 토글은 모바일 셸 헤더에 있고 가로에서 그 헤더가 숨음(추정: 쿠키 `erp_mine_only` 잔존 가능) | — | 숨은 input, 토글은 셸 헤더 | `filters.html:6-8` / `erp_mobile_shell_header.html:3,54-58` · `production_dashboard_filters.py:49` / `mobile_filters.html:122-124` |
| 정렬 | 실측일·시공일 헤더 정렬(sort/dir) | 서버 기본 정렬 그대로(시공일 빠른 순), UI 없음 | — | 없다 | `filters_grid.html:30-31` / `dashboard.py:131` |
| 일괄 선택 | **비활성** — 전체선택 체크박스만 있고 행 체크박스·벌크 바 없음(`erp-grid-order-check` 생산 폴더 0건) | 없다(`tablet-bulk-select.js` 는 주문 대시보드 entry CHAIN 전용) | 없다 | 없다 | `filters_grid.html:23` / `tablet-bulk-select.js:1-30` |
| 관리자 강제 진행(409 게이트 뚫기, 사유 시트) | 있다 | 있다 | 있다 | 있다 | `modals.html:28-33` · `scripts.html:244-257` / `tablet-production-kanban.js:114-138` · `tablet_kanban_body.html:411-414` / `tablet-domain-sheets.js:106-130` / `mobile_queue.html:116-119` — 전용 "단계 되돌림" UI 는 없음(되돌림 = 위 취소·완료취소·수정제작 3종, `_production_steps_edit_required` 게이트 `orders.py:70,99`) |
| 전체화면 | 없다 | 있다(localStorage 기억, 크롬 접기) | — | 없다 | `tablet_kanban_body.html:36-41,104-108` · `tablet-domain-sheets.js:596-637` · CSS `:245-310` |
| 밀도 토글 | 없다 | **없다**(완료 그리드·출고에만) | — | 없다 | `data-foms-density` 는 `tablet_completion_grid_body.html:98`, `shipment/partials/dashboard_main.html:88` 만 |
| KPI 타일 | 경보 4(긴급·실측D-4·시공D-3·생산D-2) + 파이프라인 단계 타일 | 5(오늘 라인·오늘 상차·지연·이번 주 자수·보류 — 4개 탭 필터) | — | 3버킷 스탯(대기·중·완료, 지연·임박 플래그) | `dashboard_body.html:46-117` / `tablet_kanban_body.html:46-82` · `dashboard.py:288` / `mobile_queue.html:19-38` |
| 페이지네이션/행 상한 | 50건/쪽 | 전량, 상한 300(`PRODUCTION_KANBAN_MAX_ROWS`) + 초과 공지 | — | 50건/쪽 pager | `production_read_model.py:30,33` · `filters_grid.html:201-239` / `dashboard.py:143-151` · `tablet_kanban_body.html:111-117` / `mobile_queue.html:103` |
| 알림 벨 | 헤더 벨(가로 태블릿에선 `.foms-shell-desktop-only` 가 CSS 로 숨음) | 레일 벨(`data-foms-notif-open`) | — | 셸 헤더 벨 | `dashboard_body.html:16-22` · 숨김 `foms-tablet-production-kanban.css:88-90` / `foms_tablet_rail.html:37-43` / `erp_mobile_shell_header.html:74-82` |
| 고객 연락처·주소 | 있다(열) | **없다**(고객명·발주사만) | **없다** | 있다(tel: 링크·지도 링크) | `filters_grid.html:125-126` / `erp_mobile_queue_card_v2.html:192-195,201-205` |
| 금액 | 없다 | 없다 | 없다 | 없다 | 읽은 네 템플릿 모두 amount/price 0건(카드 매크로 grep 0) |
| (추가) QR 라벨·타임라인 360 | 없다 | 없다 | 없다 | 있다 | `mobile_queue.html:100` · `erp_mobile_queue_card_v2.html:67-69` |

**태블릿 가로에서 생산팀이 못 하는 일(한 줄씩)**
- 공정 5단계 체크 — 칸반·시트 모두 없음(모바일 바텀시트 전용).
- 불량 보고 — 없음.
- 도면 여러 장 보기·장 넘기기·바뀐 도면 구분 — 시트는 첫 이미지 1장만, 칸반은 열기 자체가 없음.
- 서버 검색·단계·팀·긴급·경보 필터 — PC 필터 카드가 CSS 로 숨어 URL 로만 가능.
- 내 것(mine) 토글 — 셸 헤더가 숨어 손이 안 닿음(추정).
- 정렬 바꾸기 — 시공일 빠른 순 고정.
- 고객 연락처·주소 보기 — 카드·시트 어디에도 없음.
- 제작 취소·완료 취소 — 칸반 카드에서는 불가, 시트를 열어야 함.
- 보류 — PC·모바일은 걸 수조차 없고, 태블릿 시트만 가능(역방향 격차).
- 일괄 선택·밀도 토글·QR 라벨 — 없음.
- 출고 배정 — 네 표면 모두 없음(출고 보드로 가야 함).

## 표 2. 게이트·핀

### 2-a. 태블릿 JS 활성 조건과 로드 위치

| 파일(줄 수) | JS 게이트 | 서버/템플릿 게이트 · 로드 위치 · 핀 |
|---|---|---|
| `tablet-side-sheet.js`(479) | MQ `(min-width:992px) and (orientation:landscape) and (pointer:coarse)` **AND** `getComputedStyle(body)['--foms-tablet-ui']==='ready'` `:50-68` | 전역 `layout_scripts.html:100` `?v=20260727a` defer |
| `tablet-domain-sheets.js`(820) | 같음 `:28-46` | `tablet_kanban_body.html:409` `?v=20260921a` (칸반 include 조건 `dashboard_body.html:154` = `erp_mobile_v2_enabled and coarse_pointer_surfaces`) + 출고 entry CHAIN |
| `tablet-production-kanban.js`(191) | 같음 `:29-46` | 전역 `layout_scripts.html:110` `?v=20260921a` |
| `tablet-bulk-select.js`(272) | 같음 `:35-56` | `erp-dashboard-entry.js` CHAIN(주문 대시보드만, `:28-29` 주석) |
| `tablet-measurement.js`(360) | 같음 `:26-37` | `layout_scripts.html:109` `?v=20260720a` |
| `tablet-measure-form.js`(2909) | MQ 없음(실측 표면 존재가 게이트) | `layout_scripts.html:102` `?v=20261008p` |
| `tablet-density-toggle.js`(106) | JS 게이트 없음 — CSS 소유 `:10-11` | `layout_scripts.html:101` `?v=20260713a` |
| `tablet-rail-nav.js`(90) | `.foms-tablet-rail` DOM 존재 `:26-28` | `layout_nav.html:236-238` `?v=20260712a`, 조건 `erp_mobile_v2_enabled and (/erp ∪ /wdcalculator)` |
| `tablet-drawing-gallery.js`(411) | MQ AND 마커 `:41-49` | `drawing/partials/tablet_gallery_body.html:176` `?v=20260930a` |
| `tablet-drawing-review.js`(528) | **MQ 만**(마커 없음) `:37-56` | `tablet_gallery_body.html:177` `?v=20260727b` |
| `tablet-construction-workmode.js`(405) | MQ AND 마커 `:30-41` | `construction/dashboard.html:17` `?v=20260715a` |
| `tablet-completion-sheet.js`(316) | 게이트 없음(파샬 렌더 = 코호트) `:5-6` | `cs/partials/tablet_completion_grid_body.html:171` `?v=20260713b` |
| `tablet-as-compare.js`(159) | 게이트 없음(CSS 소유) `:13-14` | `cs/partials/as_dashboard_body.html:750-751` `?v=20260714a`, `erp_mobile_v2_enabled` |
| `split-shell.js`(107) | `[data-foms-split-shell]` DOM `:8` | `foms_split_shell.html:31` `?v=20260531c`(주문 `dashboard_main.html:27`) |
| `runtime/foms-pointer-hint-boot.js`·`screen`·`viewport`·`shell-mode-boot.js` | — | **src 로 로드되지 않는 SSOT 사본**. 실제는 `layout_head.html` 인라인(셸 모드 `:53-65`, 화면 크기 `:70-89`, pointer `:91-108`, screen `:118-131`, viewport `:133-165`). 쿠키 `foms_ptr`(coarse/fine, 1년) · `foms_scr`(긴 변) · `foms_vw`(세션 wide/narrow). 시험이 `foms-shell-mode-boot.js` 가 head 에 **없음**을 고정(`test_tablet_shell_t0_contract.py:169`) |

서버 게이트(확인됨): 칸반 = `is_mobile_v2_shell(variant) and wants_coarse_pointer_surfaces(request)` `dashboard.py:113-114`(쿠키 없으면 True 폴백 `feature_flags.py:149-150`); legacy 그리드 = `wide_only_surfaces`(`foms_scr`≥992) `dashboard_body.html:145`; 모바일 큐 = `mobile_width_surfaces`(`foms_ptr=fine` + `foms_vw=wide` 면 생략) `:128`.

### 2-b. CSS 번들 체인과 핀(현재 값)

- `layout_head.html:265` `foms-mobile-surfaces.css?v=20261109a`(v2 셸 게이트) — **태블릿 레이어는 여기 없음**(`foms-mobile-surfaces.css:50-52` 이관 주석, 시험 `test_tablet_t2_contract.py:109-110` 이 부재를 고정).
- `layout_head.html:271-272` `foms-tablet-bundle.css?v=20261109a` — 게이트 `erp_mobile_v2_enabled and (/erp ∪ order_edit.edit_order ∪ /wdcalculator)`. 브리프의 "bundle ← surfaces" 체인은 **옛 구조**다(확인됨).
- `foms-tablet-bundle.css:8-20` @import 핀: landscape `20260826a` · side-sheet `20261109a` · measurement `20261109a` · production-kanban `20261109a` · completion-grid `20261109a` · drawing-gallery `20261109a` · drawing-detail `20260727a` · rail `20261109a` · as-compare `20260724a` · construction `20261109a`.
- 마커 SSOT: `foms-tablet-side-sheet.css:21-23` `body.erp-mobile-v2-layout { --foms-tablet-ui: ready; }`.
- 기타: `foms-ui-zoom.css?v=20261109b`(`layout_head:230`) · `erp-pro.css?v=20261109a`(`:236`) · 생산 페이지 로컬 `foms-v2-domain-heroes.css?v=20261108a`·`foms-production-steps.css?v=20261105s`(`dashboard.html:34-35` = `dashboard_fragment.html:41-42` 동기) · `foms-reason-sheet.css?v=20261109a` + `foms-reason-sheet.js`·`foms-admin-override.js?v=20260921a`(`tablet_kanban_body:411-414`, `mobile_queue:116-119`, `modals:28-33`).

### 2-c. 세로(≥992 coarse portrait)가 폰 화면이 되는 규칙

| 파일:행 | 규칙 |
|---|---|
| `foms-shell.css:11` | `@media (max-width: 991.98px), ((min-width: 992px) and (pointer: coarse) and (orientation: portrait))` → 모바일 셸 스타일 켬 + `.foms-shell-desktop-only`·`.erp-pro-header`·`.erp-dashboard-layout` 숨김(`:24-40`) |
| `erp-pro/11-queue-family-mobile.css:7-17` | 같은 쿼리로 `.erp-dashboard-layout`(legacy 그리드) 숨김 |
| `erp-pro/13-foms-shell-bridge.css:130-136` | 같은 조합에서 `.layout-header`·글로벌 내비 숨김(무조건 블록) |
| `foms-split-view.css:61-63` | split 은 `992–1365.98 + (pointer: fine | none)` 만 — coarse 는 어느 방향에도 split 아님, portrait 토큰 금지(`tests/domains/test_p2_gate.py`) |
| `foms-mobile-v2-surfaces-hide.css:23-31` | `≥992 and (landscape | fine | none)` 에서만 모바일 대시보드 숨김 → 세로 coarse 는 모바일 큐 표시 |
| `foms-tablet-production-kanban.css:55,64` | 보드는 base `display:none`, landscape MQ 에서만 노출 → 세로에선 칸반 사라지고 모바일 큐만 |
| 가로 보완: `13-foms-shell-bridge.css:158-165` | `body:has(.foms-tablet-rail)` 이면 `.layout-header`·글로벌 내비·`.erp-pro-nav` 숨김(레일이 크롬 대체) |

## 표 3. 재사용 부품

| 부품 | 파일 | 지금 하는 일 | 생산에 쓰려면 바꿀 것 | 신규 API |
|---|---|---|---|---|
| 도면 전체화면 뷰어 + 판정 오버레이 | `static/js/foms/tablet-drawing-review.js`(528) · 뷰어 정본 `static/js/runtime/layout-scripts-core.js:10`(+인라인 사본 `layout_scripts.html:386`) | `[data-foms-drawing-viewer]` 썸네일 탭 → `data-foms-drawing-files`(JSON 리스트) 로 `GlobalImageViewer.open(files, idx)`; `[data-viewer-extra]` 노드를 셸·`#global-viewer-footer` 에 append, close() 가 전수 제거(`core.js:171`); 판정 key 는 `getIndex()`; 사유 칩 4종 `:47` | 생산 시트 `drawing_thumb` 를 단건 → 리스트(`resolve_final_drawing_files` 전체, `dashboard.py:383-407`)로 바꾸고 `data-foms-drawing-files` 부착; 액션바를 "확정/수정요청" 대신 "변경 확인·제작 시작" 등으로 교체; MQ 만 보는 게이트(`:56`)에 마커 추가 여부 결정 | 없음(뷰어·ack API 재사용) |
| 도면 갤러리 카드·크기 토글·long-press 벌크 | `tablet-drawing-gallery.js`(411) · `templates/drawing/partials/tablet_gallery_body.html`(177) · `foms-tablet-drawing-gallery.css`(889) | 카드 갤러리(sm/md/lg localStorage), 필터바(정렬·D-3·전달대기·검색), KPI 4, 기존 PC 체크박스 구동 벌크 | 카드 데이터원을 생산 행으로; 벌크는 생산에 체크박스·배치 API 가 없어 **못 쓴다** | 벌크만 필요 |
| 도면 관리 시트 fragment | `templates/drawing/partials/tablet_sheet_body.html`(113) · `foms/web/drawing/tablet_sheet.py:130-185` | 시트 N·PNG 스트립·버전 이력·전달 버튼 | 생산 시트에 "현재 전달본 N장 스트립 + 회차/버전" 섹션으로 이식(`_build_version_timeline :98` 재사용) | 없음 |
| 시공 작업 모드 3분할 | `templates/construction/partials/tablet_workmode_body.html`(193) · `tablet-construction-workmode.js`(405) · `foms-tablet-construction.css`(825) | 좌 타임라인(오늘/내일/주간 칩) · 중앙 대형 뷰어(숨긴 갤러리를 `erp-attachment-preview-open.js` 가 자동 바인딩) · 우 완료 게이트; 시공 불가 사유 4종 | 열 = 제작대기/중/완료 또는 오늘 상차; 중앙에 도면 대형 뷰어; 우측에 공정 5체크+불량+보류. `erp-attachment-preview-open.js` 는 현재 `wizard_shell.html:90` 에만 로드 → 생산 페이지에 실어야 함 | 없음(steps/defect/hold 기존 API) |
| 완료 시트 폼 패턴 | `tablet-completion-sheet.js`(316) | 시트 안 `form[data-foms-settlement-issue]` submit document 위임 → POST → 행 dim·배지 갱신(리로드 없음) | 공정 체크 토글을 "리로드 없는 in-place 갱신" 으로 만들 때 본보기(지금 생산 시트는 전부 `location.reload`) | 없음 |
| 공용 사유 바텀시트 | `partials/shared/foms_reason_sheet.html` · `foms-reason-sheet.js` · `foms-admin-override.js` | `FomsReasonSheet.open({title, actionLabel, reasons, detailLabel, onSubmit})`, 관리자 409 재시도 | 이미 칸반·시트·모바일 세 곳에 실림(`tablet_kanban_body:411-414`) — 완료취소에 사유를 붙일 때 그대로 | 없음 |
| 공정 체크 바텀시트(Bootstrap offcanvas) | `production_steps_sheet.html`(37) · `foms-production-steps.js`(345) · `foms-production-steps.css` | 모바일 카드 → 시트 1개 공용, GET/POST steps, 불량 4칩 | 태블릿 가로: `tablet_kanban_body.html` 에 include + 카드/시트에 `data-foms-prod-steps-open` 버튼 추가만 하면 동작(JS 는 이미 전역 로드 `dashboard_body:161`, 게이트 없음) — 단 70vh 미보정(`foms-production-steps.css:89`) | 없음 |
| 사이드 시트 크롬 | `tablet-side-sheet.js`(479) · `foms-tablet-side-sheet.css` | `data-foms-sheet-url` fragment 로드, headless 헤더, 도킹(주문 대시보드만 `:334-341`) | 생산을 도킹(320px 상시)으로 바꾸려면 `isOrdersDashboard()` 를 `.erp-dashboard-production` 까지 확장 | 없음 |
| 밀도 토글 | `tablet-density-toggle.js`(106) · `partials/shared/foms_density_toggle.html` | `data-density-target` 그리드에 `data-foms-density=40|48|56` | 칸반 카드 밀도용 CSS 3단 추가 필요 | 없음 |

## 표 4. 계약 시험 고정 문자열(바꾸면 빨강)

| 시험 파일:행 | 고정 대상 | 뜻 |
|---|---|---|
| `test_tablet_t2_contract.py:54,57-61` | `foms-tablet-landscape.css` 에 코어 MQ 존재, `orientation: portrait` 부재 | 가로 전용 |
| `:103-110` | 번들 @import `foms-tablet-landscape.css?v=`·`../components/foms-tablet-side-sheet.css?v=`; surfaces 에는 둘 다 **없음** | 태블릿 레이어는 bundle 소속 |
| `:119-120`, `:716` | `foms-mobile-surfaces.css') }}?v=20261109a` · `foms-tablet-bundle.css') }}?v=20261109a` | 부모 핀 |
| `:167,185-188,195-196` | `__FOMS_TABLET_SHEET_BOUND`·`/api/foms/fragment/order/`·`/edit?open=erp-order`·`#erp-grid tr.erp-main-row[data-order-id]`·`"a, button, input, select, label, textarea"`·`"role","dialog"`·`"aria-modal","false"` | 시트 JS 계약 |
| `:206-211,219-220` | `.foms-tablet-sheet` `width: 400px`·`width: 380px`·닫기 44px | 시트 CSS |
| `:305-310` | 칸반 파샬에 3버킷 라벨(제작대기/제작중/제작완료) + `foms-kanban-card` | |
| `:328-330` | kanban.js 에 `/production/start`·`/complete`·`/rework` | |
| `:337-339` | `'move': 'rework'`·`data-kanban-action="rework"`·`foms-kanban-card__rework` | |
| `:347,354-357` | `__FOMS_KANBAN_BOUND`; layout_scripts 태그 defer + `?v=` | |
| `:364,758,1132` | side-sheet.js 에 `.foms-kanban-card[data-order-id]` | |
| `:371-372` | dashboard_body 에 `production/partials/tablet_kanban_body.html` + `foms-production-legacy-queue` | |
| `:380-383` | `.foms-kanban { display: none` · `body.erp-mobile-v2-layout .foms-kanban { display: grid` · `... .foms-production-legacy-queue { display: none` | 배타표 |
| `:389-390,403` | `.foms-kanban-chip.is-imminent`·`.is-overdue`·`.foms-kanban-card[data-change-history="1"]:not(.is-changed)` | |
| `:416-426` | `max-height: calc(calc(100dvh / var(--foms-ui-zoom, 1)) - 265px)` 존재, `calc(100dvh - 240px)` 부재 | H9 보정값 고정 |
| `:426-437` | `foms-prod-pcbar__actions`·`__label` **부재** | 인쇄 버튼 금지 |
| `:441-` | 전체화면 CSS 규칙(`is-fullscreen` 크롬 숨김) | |
| `:524-526` | 번들 `foms-tablet-production-kanban.css?v=` import, surfaces 에 부재 | |
| `test_tablet_domain_sheets_contract.py:18,128-129` | `SCRIPT_CACHEBUSTER = "?v=20260921a"` + defer(칸반 바디 태그) | 도메인 시트 핀 |
| `:58-70` | `__FOMS_DOMAIN_SHEETS_BOUND`·`--foms-tablet-ui`·`data-tablet-sheet-action`·`/production/complete`·`/api/erp/shipment/update/`·`credentials`·`.foms-tablet-sheet__close` | |
| `:77-80,91-96,103-104` | `production-start`·`/production/start`·"제작을 시작하시겠습니까"·"제작을 완료하시겠습니까"·`production-cancel`·`/production/cancel`·"제작을 취소하고 제작대기로 되돌릴까요"·`production-uncomplete`·`/production/uncomplete`·"완료를 취소하고 제작중으로 되돌릴까요"·"보류를 해제할까요"·`data-hold-reason` | confirm 문구 글자 그대로 |
| `:110,116,131-136` | `data-tablet-prod-search`; `$(` 부재; 바디 attr `data-tablet-prod-search/factory/reset` + `erp-pro-alert` | |
| `:187-199,206-212` | `{% if (changed_count | default(0, true)) > 0 %}`·`id="foms-prod-change-modal"`·`role="dialog"`·`aria-modal="true"`; `data-prod-change-ackall`·`data-fingerprint` **부재**; JS `foms-prod-change-modal`·`foms:erp-shell-fragment-swapped`·`data-prod-change-row-ack`·`/production/change-ack`; `sessionStorage`·`Promise.all` 부재 | 모달 계약 |
| `:172,175` | 엔드포인트 `erp_production_page.erp_production_tablet_sheet`·`erp_shipment_page.erp_shipment_tablet_sheet` | 라우트 이름 |
| `test_tablet_shell_t0_contract.py:70-99,143-148` | split-show 매트릭스 쿼리, `(min-width: 1366px) {` 부재, portrait 토큰 부재, `html[data-foms-shell="desktop|split"]` 훅 | |
| `:157-169` | 인라인 boot 에 `foms_shell_mode`·`data-foms-shell`, `foms-shell-mode-boot.js` 부재 | |
| `:184-186,191-192,272-274` | 뷰어·모바일 셀렉트 MQ `'(max-width: 991.98px), (pointer: coarse)'`, `max-width: 768px` 부재 | |
| `:207-213,228,240-242` | `function getIndex() { return state.index; }`·`return { init, open, close, getIndex }`·`global-viewer-completion-extra`·swipe `e.preventDefault()`·`'touchcancel', handleTouchCancel` — core.js + 인라인 **양쪽** | 뷰어 append 패턴 |
| `:303-324` | `foms-shell.css` 모바일 opt-in 쿼리 글자 그대로 + "P2-08형 오버레이가 아님" + 3-way hide 열거, `@media (min-width: 992px) {` 부재 | 세로 규칙 |
| `test_tablet_rail_contract.py:60-64,78-80` | nav 에 `partials/shared/foms_tablet_rail.html`·`erp_mobile_v2_enabled`·두 path 조건·`tablet-rail-nav.js` defer | |
| `:110-123,139-142,151,165` | `.foms-tablet-rail { display: none; }`·코어 MQ·`@supports selector(:has(*))`·`padding-left: 72px`·`width: 72px`; split CSS 에 `(pointer: coarse)` 부재; 번들 rail import; `foms-tablet-bundle.css') }}?v=20261109a` | |
| `:200-208,239` | `resolve_tablet_rail_active_id` 경로→id 매핑(`/erp/production/dashboard`→`production` 등) | |
| `test_tablet_bulk_select_contract.py:43-45,51-64,70,80-81,88-92` | `__FOMS_TABLET_BULK_SELECT_BOUND`·MQ·`--foms-tablet-ui`·`pointerdown/move/up/cancel`·`LONG_PRESS_MS`·`erp-grid-order-check`·`new Event("change"`·`erp-grid-bulk-status`·`erp-grid-select-all`·`stopPropagation`·entry `s.async = false`·`.foms-tablet-bulk-bar { display: none; }` 등 | |
| `test_tablet_dashboard_sheet_contract.py:51-55,61-63,72-74` | `resolveSheetUrl`·`getAttribute("data-foms-sheet-url")`·`function load(orderId, url)`·`tablet-side-sheet.js') }}?v=20260727a` | 시트 핀 |
| `:84-88,97,102-105,118-119,141-148` | density: `__FOMS_DENSITY_TOGGLE_BOUND`·`foms_tablet_density`·`setAttribute("data-foms-density"`·`?v=20260713a`·3 버튼·`display: inline-flex` 등 | |
| `test_tablet_drawing_workshop_contract.py:46-59,67-75,84-88,97-123` | "도면 작업실"·크기 토글 3·`data-foms-drawing-bulk-assign`·필터 name 들·KPI 값 4개·카드 `data-foms-sheet-url`·`시트 {{ r.file_count }}`·gallery.js 태그 | |
| `test_tablet_as_compare_contract.py:55-89,116-118,132-178` | `foms-as-compare*`·`접수 시`/`조치 후`/`사진 없음`·`<script`·`style=` 부재·테이블 래퍼 클래스·`foms-tablet-as-compare.css?v=20260724a` | |
| `test_production_kanban_full_window.py:100-102,113-116,141,184-206,219-221,235-236` | 50/51 행·cap 3·`changed_count==1`·마우스 PC 는 `kanban_orders==[]`·`tablet_prod_kpis=={}`·소스 문자열 `kanban_wanted = is_mobile_v2_shell(resolve_shell_variant_cached(` + `and wants_coarse_pointer_surfaces(request)` | 칸반 게이트 글자 고정 |
| `test_production_kpi_slim_projection.py:142-146` | slim == full KPI/step 결과 | |
| `test_production_dashboard_mobile.py:38-51,82-92,125-127,165-172,194-207` | `render_mobile_pager`·`render_queue_card_v2`·`--production`·`data-action="startProduction"`(PC 그리드)·`completeProduction`(PC scripts)·`'badge_only': true`·"50 / 전체 60건"·`?open=erp-order`·"주문 수정"·fragment 에 두 CSS + `v=20260712a`·`v=20260713b`·`<html` 부재 | 모바일 큐 |
| `test_production_steps_api.py:70-73,119-126,149-152,165,178,211-212,233-245,272-276` | step key 순서 `cut,edge,paint,assemble,inspect`·`total==5`·`by_name`·생산팀 허용/도면팀 403·불량 "파손" 이벤트 | API 계약 |
| `test_p1_mockup_structure.py:228-237` | `foms-shell-desktop-only`·`.erp-pro-header`·`.erp-pro-nav`·`display: none !important`·`foms-mobile-v2-critical-css`·`foms-mobile-surfaces.css') }}?v=20261109a` 순서 | |
| `test_admin_override_ui.py:38,61,139-153` | `tablet_kanban_body.html` 에 `foms_reason_sheet.html`+`foms-admin-override.js` 세트, 핀 `20260921a` | |
| `tests/performance/test_entry_chain_parallel_contract.py:243-262` | 칸반 바디 `tablet-domain-sheets.js` 핀 == 출고 entry CHAIN 핀 (드리프트 금지) | |
| `tests/performance/test_page_local_defer_contract.py:83,102` | `order-detail-fragment.js`·`tablet-domain-sheets.js` defer | |

## 래칫 수치(확인됨)
- 래칫 = `tests/harness/test_file_size_ratchet.py:166-171` — **.js 파일만**, 300줄 이상인데 `file_size_baseline.json.known_large_javascript`(95개) 에 없으면 빨강. 기준선에 있는 파일은 **자라도 안 잡힘**. "인라인 `<script>` 300줄" 은 docstring(`:3`)뿐, 템플릿 인라인 길이를 재는 시험은 **없음**(tests 전체 grep 0).
- 기준선에 있음(자라도 됨): `tablet-domain-sheets.js` 820 · `tablet-side-sheet.js` 479 · `foms-production-steps.js` 345 · `tablet-drawing-review.js` 528 · `tablet-drawing-gallery.js` 411 · `tablet-construction-workmode.js` 405 · `tablet-completion-sheet.js` 316 · `tablet-measurement.js` 360 · `tablet-measure-form.js` 2909.
- 기준선에 **없음**(300 넘기면 빨강 — 남은 줄): `tablet-production-kanban.js` 191(**109**) · `tablet-bulk-select.js` 272(**28**) · `foms-write.js` 208(92) · `tablet-as-compare.js` 159 · `split-shell.js` 107 · `tablet-density-toggle.js` 106 · `tablet-rail-nav.js` 90.
- 템플릿: `scripts.html` 인라인 2블록 874줄 + 158줄(래칫 밖), `tablet_sheet.html` 인라인 22줄, `tablet_kanban_body.html` 415줄(인라인 0), `mobile_queue.html` 119줄.

## H2 · H9 · H10 판정

- **H2(공정 체크·불량 보고가 태블릿 가로 시트에 없다) — 확인됨.** `tablet_sheet.html`·`tablet-domain-sheets.js`·`tablet_kanban_body.html` 어디에도 `production/steps`·`production/defect`·`data-foms-prod-steps-open` 가 없다(전문 읽음). 시트 마크업은 `mobile_queue.html:113` 에만 include. 다만 `foms-production-steps.js` 는 `dashboard_body.html:161` 에서 항상 로드되고 게이트가 없어, include + 버튼 1개면 바로 동작한다(비용 낮음).
- **H9(화면 크기 손잡이가 칸반·시트 높이 `90vh/--foms-ui-zoom` 에 영향) — 조건부(전제 일부 뒤집힘).** ① `90vh` 는 태블릿 CSS 어디에도 없다. 시트는 `top:0; bottom:0` 고정이라 vh 를 안 쓴다(`foms-tablet-side-sheet.css:24-31`); 커밋이 바꾼 건 `max-width: 92vw → calc(92vw/zoom)`(`:31`) 과 주석 1곳. ② 칸반은 열 본문 캡 `calc(100dvh/zoom − 265px)`(`:376`), 전체화면 캡 `−90px`(`:304`), 변경 모달 `80vh/zoom`(`:892`) 로 보정됐고 시험이 고정(`test_tablet_t2_contract.py:416-426`). ③ **미보정**: 변경 모달 목록 `max-height: 60vh`(`foms-tablet-production-kanban.css:926`) — 다이얼로그는 `overflow:hidden`(`:897`) 이라 130% 에선 목록(실제 78%)이 다이얼로그(실제 ≈61.5%)를 넘어 아래 행이 잘릴 수 있다(**추정**, 실화면 필요). `foms-production-steps.css:89` `70vh` 도 미보정(태블릿 가로엔 미렌더라 영향 없음). ④ 배율 키는 `foms-ui-zoom:<uid>:touch`(`layout_head.html:72-75`) 로 세로·가로가 같은 값을 쓰는데, 가로에서는 손잡이 두 곳(`layout_nav.html:68` 위 막대 — 레일이 있으면 `13-foms-shell-bridge.css:158-165` 가 헤더를 숨김 / `erp_mobile_menu_drawer.html:83` — 모바일 셸 전용)이 모두 손에 안 닿아 **세로에서 정한 배율이 가로 칸반에 그대로 걸리고 가로에서는 못 바꾼다**(추정, 실화면 필요). ⑤ 태블릿 CSS 8파일 중 실제 값 변경 7(side-sheet·kanban·completion-grid·construction·drawing-gallery·measurement + rail 은 주석만), landscape·as-compare·drawing-detail 은 무변경(`git show 9d954d01b --stat`).
- **H10(PC 그리드에 있는데 칸반·시트에 없는 기능이 있다) — 조건부 확인.** 있다: 서버 필터(단계·팀·긴급·경보·검색 UI), 정렬 헤더, 고객 연락처·주소 열, 첨부 모달(여러 장·카테고리). 그러나 "일괄 선택·관리자 되돌림" 은 PC 에도 **없다** — 전체선택 체크박스만 있고 행 체크박스·벌크 바가 생산 폴더에 없으며(비활성), 되돌림 3종(수정 제작·제작 취소·완료 취소)은 PC 에 함수만 있고 버튼이 없다(`scripts.html:298-343`). 오히려 **역방향 격차**가 크다: 보류 토글·변경 확인·묘비·KPI 탭 필터·전체화면은 태블릿에만 있고, 제작 완료도 PC 는 접힘 패널 안에만 있다.

## 확인 못 한 것과 이유
- 실화면(배율 70/130%, 세로↔가로 회전, 변경 모달 60vh 잘림, mine 쿠키 잔존) — 읽기 전용 지시라 브라우저를 안 띄웠다. 전부 "추정" 표기.
- 모바일 카드의 상차/시공 1줄 값(`queue_card_schedule` 필터)과 `drawing_preview_only` 가 생산 DTO 에서 어떻게 채워지는지 — 필터·DTO 빌더까지는 안 들어갔다(브리프 범위 밖).
- PC 접힘 상세 패널(`scripts.html:440-720`)이 보여 주는 품목·규격·특이사항의 정확한 범위 — 1193줄 중 액션·첨부 부분만 읽었다.
- `test_production_dashboard_mobile.py:205-206` 의 `v=20260712a`·`v=20260713b` 가 어느 자산의 핀인지 — 현재 heroes/steps 핀(20261108a/20261105s)과 다르므로 다른 자산일 텐데 추적하지 않았다.
