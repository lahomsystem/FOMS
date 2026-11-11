# 태블릿 UI 최종 구현 — 생산 페르소나 설계서 (2026-11-09, 리뷰 ①②③ 반영판 · **사용자 승인 2026-11-09**)

> 지시서 `docs/plans/2026-11-09-tablet-production-ui-meta-prompt.md`. 원장 `docs/plans/2026-11-09-tablet-production-ui-ledger.md`(리뷰 finding 전량·재확인). 전수표 `docs/plans/2026-11-09-tablet-production-ui-inventory.md`. 목업 `docs/design/mockups/tablet-production-ui.html`(F1~F8 — 리뷰 반영 전 그림이라 ① 레일 단추 위치·② 카드 "공정 n/5"·시트 "시공팀" 줄·뷰어 위 글·"1/3" 은 이 문서가 정본). 기준 코드 origin/deploy `ea4376ea1`.
> 이 문서는 **코드를 고치기 전의 설계**다. 승인 뒤 플랜(`…-plan.md`)의 task 로 구현한다.

## 0. 한 줄 요약

태블릿 가로 표면(레일·사이드 시트·생산 칸반)은 2026-07 에 이미 있다. 생산팀 계정으로 스테이징 실화면을 전수 점검한 결과, **생산 사람이 태블릿 하나로 하루 일을 끝내지 못하는 이유는 새 화면이 없어서가 아니라 ① 첫 화면·권한 구멍 ② 작업 시트 안에 공정 체크·불량·연락처가 빠진 것 ③ 도면을 여러 장 크게 못 보는 것**이다. 기존 화면을 그대로 두고 칸 몇 개만 채운다. 새 쓰기 API 0, DB 변경 0, 새 JS 파일 0(인쇄를 고르면 작은 것 1개).

## 1. 배경과 확정 결정 (사용자, 2026-11-09 — 다시 묻지 않는다)

| 번호 | 결정 |
|---|---|
| D0 | 이 세션에서 바로 조사·목업까지 진행 |
| D1 | 기종 = **갤럭시 탭**(가로 약 1280×800 CSS px). 세로로 돌리면 폰 화면이 되는 현 구조는 둔다 |
| D2 | **사람마다 계정, 사람마다 태블릿** → "사람마다 [확인]" 구조 그대로 |
| D3 | 생산팀은 **생산·출고·시공 일정**을 봐야 하고 **고객 이름·주소·전화번호도 다 볼 수 있어야** 한다 |
| D7 | **금액은 생산팀에게 가린다**(완료 보드의 출고가·예약금·잔금·미수 합계·현금영수증·정산 배지, 모바일 주문 상세의 품목 금액). 서버 분기로 값도 안 보낸다 |
| D4 | 지금 작업 지시는 구두·전화 + 카톡 발주방 PUSH + 종이 출력. **작업지시서 인쇄(F8)는 이번에 같이 만든다**(D8) |
| D5 | 장갑 끼고 씀 · 와이파이 안정 · 가끔 연결이 얼어요 |
| D6 | 태블릿은 생산 외 시공·CS·영업·출고·도면도 씀. 이번은 생산 1순위, 다른 팀 표면은 점검만(결함 기록) |

설계자가 정한 것(리뷰 ② 판정 수용, 승인 때 뒤집을 수 있음): 레일 9탭은 **지금처럼**(F-18) · 변경 브리핑 모달은 **지금처럼 매 진입**(코드가 의도한 마찰, F-12) · 컨트롤타워 시트는 **403 문구만**(F-02) · AS 행 403·출고팀 STAFF 배정 403 은 **별건**(F-10).

## 2. 페르소나

**생산팀 직원(STAFF, 팀 PRODUCTION)** — 공장 작업대, 갤럭시 탭 가로, 장갑. 하루 할 일: ① 오늘 만들 것 보기 ② 도면·규격·자수·특이사항 읽기 ③ 제작 시작→공정 5단계 체크→제작 완료, 불량·보류·수정 제작 ④ 바뀐 것(도면 바뀜·시공일 변경·취소) 알아채고 [확인] ⑤ 상차·시공 일정 읽고 넘기기 ⑥ 알림·공지·연락처·화면 크기. 운영 10-27 실측 생산팀 계정 0명 — 종이·카톡으로 일한다. 운영 계정은 사용자가 만든다.

**다른 팀**(D6): 도면·출고·시공·CS 는 전용 태블릿 표면이 있고 생산 계정에서도 렌더된다(전수표 C4). 결함만 기록(F-10·F-20).

## 3. 회사 단계 흐름과 생산의 접점 (워커 C 요약 — 원문 `…-worker-C.md`)

| 단계 | 생산이 봐야/눌러야 하는 것 | 근거 |
|---|---|---|
| 접수·실측·도면 | 없음(보드 밖, 알림 없음) | `production_change_alerts.PROD_STAGES` |
| 고객컨펌 | 제작대기 버킷에 이미 뜬다. [제작 시작]은 컨펌 퀘스트 승인 + 도면 CONFIRMED 일 때만(아니면 409) | `foms/api/production/orders.py:813-831` |
| 컨펌 → 생산 | 퀘스트 최종 승인이 곧 전이(2026-09-17부터) | `quest_transition_service.py` |
| 생산 | 카드·시트·KPI. 제작 시작/완료/취소/완료 취소/수정 제작·공정 5체크·불량·보류·[변경 확인]. 알림 4종 벨+폰 | `orders.py:745-1729` |
| 생산 → 시공·출고 | [제작 완료] → 단계 시공·버킷 제작완료. 출고 겹축·2주 판·시공팀 배정은 **출고 보드**에서 읽는다(생산팀 200) | `state_axes.py`, 전수표 #10 |
| 시공·CS·완료·AS | 없음. AS → 재제작 경로 없음(시공 불가 `product_defect`·[수정 제작]만) | 워커 C |
| 옆길 | 도면 바로 반영(합치기 없이 매번 폰) · 시공일 변경 · 주문 취소(묘비 14일) · **품목 일부 취소는 알림 없음** · 관리자 되돌림은 run 을 안 건드림 | 워커 C |

## 4. 전수 점검 결과 (전수표 — 모집단 24, 판정 144칸, 대조군 4)

생산 보드 자체(가로 칸반·세로 큐)는 쓸 만하다(KPI·필터·변경 표시·보류·수정 제작·전체화면, 44px 미만 타깃 0). 빈 곳:
**A. 첫 화면·권한(높음)** F-01 로그인 뒤 컨트롤타워 + 도킹 시트 403 상자 · F-02 컨트롤타워·AS 행 탭 403("다시 시도"만) · F-07 세로 하단 탭에 생산 없음.
**B. 작업 시트(높음)** F-03 공정 5체크·불량이 가로에 없음 · F-04 전화·주소가 가로 카드·시트에 없음(D3) · F-15 인쇄 없음(D4).
**C. 도면(높음)** F-05 시트는 전달본 첫 1장, 칸반에서 못 열고, 장 넘기기 없음.
**D. 그 밖** F-06 가로 배율 손잡이 없음 + 브리핑 목록 130% 깔림 · F-13 품목 취소 알림 없음 · F-11 금액 노출(Q-A) · F-08/F-09/F-10/F-12/F-14/F-16/F-17/F-18/F-19/F-20 기록·미룸.

## 5. 바꾸는 것 — 프레임마다 "지금 → 바뀐 칸 → 쓰는 기존 부품"

원칙: 기존 화면 그대로, 바뀐 칸만. 글은 해요체·같은 말 한 번·기계 말 금지.

### F1 생산 보드(가로) — `templates/production/partials/tablet_kanban_body.html`, 레일 `templates/partials/shared/foms_tablet_rail.html`
- 지금: 레일 + KPI 5 + 필터줄 + 칸반 3열. 카드엔 칩 10종이 이미 있다.
- ① **레일에 화면 크기 단추** — 기존 `templates/partials/shared/foms_ui_zoom_control.html` 을 변형 `rail` 로 include(변형 1개 추가, 세로 3단 48px). 자리는 **브랜드 F 바로 아래**(130% 에서도 스크롤 없이 보임 — 레일은 fixed+overflow 라 맨 아래는 넘친다). JS 는 `static/js/foms/ui-zoom.js:43,55-64` 가 `[data-foms-ui-zoom-ctl]` 을 전수 갱신·document 위임하므로 0줄. 저장 키 `foms-ui-zoom:<id>:touch` 세로와 공유. 레일 72px·`.foms-tablet-rail__item` 계약 유지.
- ② **브리핑 모달 목록 높이** — `static/css/foundation/foms-tablet-production-kanban.css:926` `max-height: 60vh` → `calc(60vh / var(--foms-ui-zoom, 1))`. `test_tablet_t2_contract.py` 에 새 test 함수(60vh 보정; `:416-423` 은 265px 캡, `:426-438` 은 pcbar 인쇄 금지). 번들 `foms-tablet-bundle.css` @import 핀 + `layout_head.html` 핀 올림.
- 카드엔 손대지 않는다(리뷰 ②: 공정 진행은 시트에서, 카드 단추는 세로 시트를 여는 부작용 — 리뷰 ① #3).

### F2 작업 시트(가로 400px) — `templates/production/partials/tablet_sheet.html`, 뷰 `foms/web/production/dashboard.py:408-468`
- 지금: 고객명·배지 / "#id · 상차 M/D" / 변경 알림+[변경 확인] / 총 자수 / 규격 표 / 특이사항 / 도면 전달본 1장 / 단추(제작대기: [보류]·[제작 시작] / 제작중: [보류]·[제작 취소]·"생산 완료" / 제작완료: [보류]·[완료 취소]·[수정 제작], `tablet_sheet.html:176-203`).
- ① **연락처·주소 한 줄**(머리 아래): 전화번호 글자 + [전화](`tel:`) · 주소 + [지도] — 모바일 상세(`templates/orders/partials/order_detail_mobile_v2.html:139,150`)와 같은 값·링크. 뷰 모델에 전화·주소(이미 로드된 `order`·`sd`, 쿼리 0). 기존 `.foms-prod-sheet__card` 스타일 재사용.
- ② **공정 체크 5단계 + [불량 보고] 블록**(규격 표 아래): 마크업은 세로 바텀시트(`production_steps_sheet.html:15-35`)의 목록·칩을 쓰되 **id 없이 data-속성만**(가로 DOM 에도 세로 오프캔버스가 칸반보다 앞에 있어 id·첫 매치가 겹친다 — 리뷰 ① #2). JS `static/js/production/foms-production-steps.js` 는 지금 document 전역 7곳(`getElementById` `:52`, `:56,159,162,191-194`)·전역 `currentOrderId`(`:18,275`)라 **루트 `[data-foms-prod-steps-sheet="<id>"]` 기준 스코프 객체로 재작성**하고, 시트 삽입 때(`foms:erp-shell-fragment-swapped`, `fragment-loader.js:135` 또는 시트 인라인 선례 `tablet_sheet.html:210-232`) `loadSteps(id, root)` 를 부른다. 세로 오프캔버스는 같은 스코프 객체의 한 인스턴스로 그대로 동작. API `GET/POST …/production/steps`·`POST …/defect` 그대로. 체크 48px, 즉시 저장, 실패 시 문구(§8). 이 파일은 래칫 기준선에 있어(`file_size_baseline.json`) 늘어나도 된다.
- ③ **도면 전달본 N장 스트립**: `_prod_sheet_drawing_thumb`(`dashboard.py:383-405`, 첫 장 return)를 **이미지 전체 목록**(`_PROD_SHEET_IMG_EXT` `:328` 로 거름, 쿼리 0)으로. 탭 = F3. 비이미지(PDF)는 "파일 열기" 링크. "1/3"·"바뀐 도면" 글은 **넣지 않는다**(뷰어가 "n / N" 을 띄우고, 변경 알림 섹션이 "도면 바뀜"을 이미 말함 — 리뷰 ②).
- ④ **링크 "상세 · 인쇄"** — 상세 → `/erp/orders/<id>/mobile`(생산팀 200), 인쇄 → F8 페이지(새 탭). `/edit/<id>` 링크는 두지 않는다.
- ⑤ 단추 글 **"생산 완료" → "제작 완료"**(세로 카드·설계서와 같은 말, `tablet_sheet.html:169,197`; 계약 시험은 confirm 문구만 고정).
- 그대로: "상차 M/D"(값은 시공일 키와 같다 — 공장 말 그대로 둠), [제작 취소], 변경 알림·[변경 확인]·총 자수·규격 표·특이사항·단추 줄·confirm 문구. "시공팀 배정" 줄은 넣지 않는다(출고 보드에서 읽음 — 데이터는 `sd['shipment']['construction_workers']`, D3 충족).

### F3 도면 전체화면 보기 — 새 JS 없음
- 지금: 전역 `GlobalImageViewer`(핀치·스와이프·더블탭·"n / N" counter 내장 `layout-scripts-core.js:262-264`), 시트는 1장만 넘긴다.
- 바뀐 칸: 스트립 썸네일을 기존 마운터 `static/js/foms/erp-attachment-preview-open.js`(`galleryFilesFromNodes` `:147` → `GlobalImageViewer.open(files, idx)` `:163-167`)가 읽는 갤러리 마크업으로. 이 마운터는 모바일 큐 번들(`foms_mobile_queue_attachment_preview_bundle.html:4`)로 생산 페이지에 이미 실리는지 T3-1 에서 확인(안 실리면 로드 1줄). 뷰어 위 글·아래 단추는 **넣지 않는다**(닫으면 바로 시트 — 리뷰 ②). 이미지만 넘긴다(뷰어는 확장자 필터 없음 — 리뷰 ① #14).

### F6 세로(800×1280) — `templates/partials/shared/erp_mobile_shell.html:48-56`(시공팀 `elif` `:48-50`, 기본 `:54-56`)
- 지금: 큐 카드는 충분(주소·연락처·시공·담당·단추·"공정 n/5"). 하단 탭이 대시보드·실측·출고·시공·계산기·더보기.
- 바뀐 칸: 팀 분기 `elif` 1개 — PRODUCTION 이면 기본 탭 `['production','shipment','construction','dashboard']`(허용 목록 그대로, `_construction_only` 꼴). QR 막대 위치(F-17)는 미룸.

### F7 첫 화면 — `foms/services/post_auth_navigation.py`, `foms/web/orders/listing.py:158`, `foms/web/auth/routes.py:585`, `static/js/foms/fragment-loader.js:92-100`, `foms/web/orders/dashboard.py:641-642`
- 지금: 로그인 → `/` → 컨트롤타워, 도킹 시트 403 상자(F-01). 행 탭 403(F-02).
- ① **생산팀 착지 = 생산 보드** — 조건 `team == PRODUCTION and partner_org_id is None and not 프리랜서`, **기기 무관**(PC 도). 바꿀 곳 세 곳 + 하나: `authenticated_home_url`(`:31-44`), `post_auth_navigation.py:100-101`(`next` 가 `/`일 때 직접 dashboard), `listing.py:158-159`(직접 dashboard) → 한 함수로 모으고, `routes.py:585` switch_user 분기도 referrer 앞에. 협력사(`partner_scope`)·프리랜서(`freelancer_scope.py:352`) 홈은 건드리지 않는다.
- ② **403 문구** — `fragment-loader.js` renderError 가 status 를 받아 403 이면 "이 주문은 보기만 할 수 있어요." + [상세](모바일 상세 링크, 로더는 orderId 를 안다 `load(orderId, url)`). 읽기 전용 시트 렌더는 하지 않는다(승인 단추 등 잔존 위험 — 리뷰 ① #8). `erp_dashboard_tablet_sheet` 의 `Sec-Fetch-Dest: document` 302(`dashboard.py:641-642`)는 `can_edit_erp` 아니면 모바일 상세로.
- 레일 9탭은 그대로(D3·설계자 결정).

### F8 작업지시서 인쇄(A4 1장) — D8 로 포함, 새 읽기 라우트 `GET /erp/production/print/<id>`
- 전례 `erp_dashboard.erp_order_label`(`dashboard.py:878-915`, 단독 HTML `orders/label.html`, 새 탭). 권한 = 로그인 + `_can_edit_production_steps`(`foms/api/production/orders.py:99-120`, CS·SALES·PRODUCTION) 재사용. 내용: 주문번호·고객·전화·주소·발주사·상차/시공일 / 규격 표(취소 품목 제외) / 특이사항 / 최종 도면(장마다 1쪽, `/api/files/view/<key>` 생산팀 200) / 공정 체크 빈 칸 5. CSS 새 파일 1(`static/css/contexts/production/print.css` — `contexts/production/` 폴더도 새로), 인쇄 단추 JS 는 외부 파일(label.html 의 인라인 script 전례를 따르지 않음). GET 이라 쓰기 매니페스트 비대상. 생산 보드 pcbar 엔 인쇄 단추를 두지 않는다(계약 시험 `foms-prod-pcbar__actions` 부재).

## 6. 권한·게이트·세로 폴백

- 생산팀이 쓰는 API 는 전부 이미 200(워커 A 표 2). **새 쓰기 API 0, 권한 확대 0**(F7 ② 를 문구로 줄였으므로).
- 태블릿 게이트 그대로: `(min-width:992px) and (orientation:landscape) and (pointer:coarse)` + `body.erp-mobile-v2-layout` 의 `--foms-tablet-ui:ready`. 칸반 서버 게이트 글자 고정(`test_production_kanban_full_window.py`).
- 세로 = 폰 화면(D1). 세로엔 공정·연락처·상세가 이미 있다 — F6 탭 한 칸만.
- 운영 코호트: 스테이징은 새 계정도 바로 태블릿 표면. 운영 `FOMS_V3_SHELL_COHORT` 는 사용자가 확인.
- 폰 알림은 레일 벨 패널의 "휴대폰 알림 받는 3단계"로 사람마다 켠다.

## 7. 알림·변경 확인

- 4종은 벨+폰+카드 표시가 이미 있고 [확인]은 사람마다(D2, 워커 C H12).
- F-13 **품목 일부 취소 알림**: `foms/api/drawing/erp_orders_item_cancel.py` 의 `_mutate`(`:71-82`) 안 **취소 적용(`:75-76`) 뒤·커밋(`:91`) 전**에 `apply_production_change_alert(kind="item_cancel", merge=False)` 1줄 + 커밋 뒤 `finalize_…`. `merge=False` 인 이유 = 60초 합치기가 같은 라벨 row 의 title/message 를 덧써 품목 2개 중 첫 이름이 사라지고 폰도 안 간다(`production_change.py:148-156`). 라벨은 `_KIND_LABEL` 에 "품목 취소" 1줄(기본 "주문 변경"은 흐림). 본문 "주문 #N — ○○ 1개 취소". 카드 스트립은 종류별 행(`tablet_kanban_body.html:184-197`, 아이콘 분기 `:185`)·모달(`:376-378`)의 else 분기 그대로. REV-99 writer 인벤토리가 이 파일 lineno 를 핀하므로 삽입 뒤 `refresh_inventories` 후 커밋.
- F-12 브리핑 모달은 그대로(코드 주석 "의도된 마찰", `tablet_kanban_body.html:347-351`).

## 8. 장갑·연결 끊김 (D5)

- 계약(`foms-tablet-landscape.css:23-55`)은 행 48px·타깃 44px·입력 16px. 그 위에서 새 체크박스·단추는 48px.
- 실패 문구 통일: `tablet-domain-sheets.js:110-134, 257-262` 와 `foms-production-steps.js:263,296` 의 alert → "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요." 공정 체크는 낙관 갱신이 없어(`:292-299`) 되돌릴 것이 없다. 오프라인 저장은 범위 밖. 확인 창 수·문구는 그대로(window.confirm 4 + 제작 취소 사유 시트 1 + 보류 재시도 1, 계약).

## 9. 시험

- 계약 갱신: `test_tablet_t2_contract.py`(60vh 보정 새 함수), `test_tablet_rail_contract.py`(레일 자식 추가 뒤 72px·`__item` 단언 통과), `test_tablet_domain_sheets_contract.py`(confirm 불변·새 링크 단언), `tests/domains/test_post_auth_navigation.py:36,61`(PRODUCTION 사례), 하단 탭 분기는 기존 시험이 없어 **새 시험**, `test_production_change_notification.py`(item_cancel row 팀 3·merge 없음), CSS 번들 핀을 보는 시험 `test_tablet_t2_contract.py`·`test_tablet_rail_contract.py`·`test_tablet_as_compare_contract.py`·`test_shipment_change_alert_render.py`, JS 핀 동기 `tests/performance/test_entry_chain_parallel_contract.py`(domain-sheets.js 핀 = 출고 CHAIN 핀), 래칫(새 JS 는 인쇄 단추 파일뿐, 300줄 아래).
- 새 단언: ① 생산팀 로그인·`/`·switch_user 모두 → 생산 보드(PC 도) ② 시트 fragment 에 전화·주소·공정 목록(5)·불량 칩(4)·도면 목록 N·"상세" 링크, id 중복 0 ③ 시트 라우트 쿼리 수 단언 **새로**(`test_production_dashboard_query_count.py` 는 v2 env 없이 대시보드 fragment 만 센다 — 리뷰 ①③) ④ 403 문구·상세 링크(JS 계약 문자열) ⑤ 인쇄 페이지(Q-F 때) 생산팀 200·도면팀 403·취소 품목 제외.
- 실화면(뷰포트 캡처만): 1280×800·1024×768·800×1280, 배율 100/80/130, 생산팀 + 관리자 대조군 + PC 마우스 음성 대조군. 하네스는 세션 스크래치패드 `tablet_shot.py`(새 폴더 금지).
- 자산 핀: 자식 CSS(`static/css/foundation/foms-tablet-production-kanban.css`·`foms-tablet-rail.css`, `static/css/components/foms-tablet-side-sheet.css`) 바꾸면 `foms-tablet-bundle.css` @import 핀과 `layout_head.html` 핀 함께.

## 10. 범위와 단계

- 포함: F1 ①②, F2 ①~⑤, F3, F6, F7 ①②, F8(D8), F-13, D5 문구, **생산팀 금액 가리기(D7)**.
- 제외·미룸: 오프라인 저장, 출고 배정 쓰기(출고팀 STAFF 403 별건 보고), AS→재제작, 생산 할 일 보드 노출, 회사 지식 404, 공지·프로필 레일, QR 막대 위치, AS 행 시트 URL(별건 1줄), 다른 팀 태블릿 2차, "바뀐 도면" 장별 표시.
- 단계(11-09 D12 로 갱신): **P0 생산팀 첫 화면**(§12 — 전체 주문 한 줄 + 착지, 전체 화면 작업 시트, 탭 둘) → **P1 착지·권한**(F7 ②, F6, D7 금액 가리기 — F7 ① 은 P0 가 대신함) → **P2 작업 시트**(F2 ①②④⑤, F1 ②, D5 문구, F1 ①) → **P3 도면·공정·알림**(F2 ③, F3, F-13) → **P4 인쇄**(F8). P1·P2 만 나가도 값어치가 있다.

## 11. 사용자 결정 (2026-11-09 질문 창 — 원장 §8)

- **Q-A 금액 → 생산팀에겐 가린다(D7)**. 가리는 자리: 완료 보드(`/erp/completion` PC 표·태블릿 그리드·모바일 카드·CSV)와 그 KPI(미수 합계·정산 대기), 모바일 주문 상세 품목 금액(`order_detail_mobile_v2.html` 제품 칸). 판정은 팀 PRODUCTION 서버 분기 하나(기존 `policy_can('SETTLEMENT_DASHBOARD_READ')` 꼴의 읽기 술어를 재사용하거나 새 술어 1개), 템플릿은 칸을 비우지 않고 **열·줄 자체를 뺀다**.
- **Q-F 인쇄 → 이번에 같이(D8)**. F8 포함, 시트 링크 "상세 · 인쇄".
- **진행 → 설계 승인, 구현 시작(D9)**.

## 12. 생산팀 전용 첫 화면 (2026-11-09 작업자 시안 뒤 추가 — D10·D12·D13, 원장 §8.1·§9)

시안 `docs/design/mockups/tablet-production-ui-alternatives.html`(안 1~4). §5 의 F1~F8(기존 레일·옆 시트 고치기)은 그대로 두고, 생산팀에게는 **따로 첫 화면**을 준다. 레일은 남되 뒤로(D13).

### 12.1 전체 주문 한 줄 (안 1) — `GET /erp/production/home` · `erp_production_page.erp_production_home`
- 누가: 공정 체크를 할 수 있는 사람과 같은 답(관리자·CS·영업·생산, `_PRODUCTION_STEPS_EDIT_TEAMS`). 도면·시공팀 403. 협력사 403.
- 무엇: `Order.active_filter()`·ERP 주문·단계 `PRODUCTION_HOME_STAGE_CODES`(도면 + 고객컨펌·생산·시공 — 접수·실측은 제외) 를 **시공일 순**(`apply_production_dashboard_sort` 기본, 없음은 뒤), 캡 `PRODUCTION_KANBAN_MAX_ROWS`(300). 쿼리 빌더는 칸반과 같은 `build_production_orders_query` 에 `stage_codes` kwarg 하나 더한 것. 행 변환은 `build_production_home_enriched_rows`(도면 단계도 남김). 금액 키는 뷰 모델에 없다(D7).
- 큰 글자(지금 단계) = `production_home_stage`: 보류 / 도면 기다림 / 컨펌 기다림 / 제작 대기 / `<첫 미완 공정> 중` / 검수 끝 / 제작 완료. 공정 5칸은 `structured_data.production.steps`(없으면 5칸 미완).
- 날짜 머리줄 = `production_home_day`: "오늘 11/9 (월)" · "내일 …" · "11/12 (목) · D-3" · "… · n일 지남" · "시공일 없음".
- 위 막대: 전체 / 생산 중(제작 대기~검수 끝·보류) / 바뀐 것(미확인 변경 알림 — `collect_production_change_alerts`) 세 칸, 찾기(이름·주소·번호·#id, 화면 안 필터), "HH:MM 에 받음" + [다시 받기](새로고침 링크). 연결이 끊기면 붉은 줄 "연결이 끊겼어요. 보이는 것은 HH:MM 에 받은 것이에요."(D5).
- 카드(100px): 단계 큰 글자 | 이름 #id · 품목·규격·색 · 주소(바뀐 것은 붉은 한 줄) | 공정 5칸 | 도면 n장. 탭 → 12.2 전체 화면 작업 시트(T0-2 전엔 모바일 상세 `/erp/orders/<id>/mobile`).
- 파일: `foms/services/production_home_read_model.py`(새), `foms/services/production_dashboard_display.py`(공개 함수 1), `foms/services/production_read_model.py`(kwarg), `foms/web/production/dashboard.py`(라우트), `templates/production/home.html`(새, `production/layout.html` 확장 + 세로엔 `erp_mobile_shell.html`), `static/css/contexts/production/home.css`(새 폴더), `static/js/production/foms-production-home.js`(새, 보이기/숨기기만, 300줄 아래).
- 시험: `tests/domains/test_production_home.py`(시공일 순·단계 글자·탭 숫자·금액 0·403·공정 정의 = API).

### 12.2 전체 화면 작업 시트 (안 2) — `GET /erp/production/sheet/<id>` (T0-2)
- 옆 시트 뷰 모델(`erp_production_tablet_sheet`, `dashboard.py:408-468`)을 함수로 빼서 둘이 같이 쓴다. 더하는 키: 전화·주소·실측일·출고일, 도면 이미지 전체 목록(F2 ③), 공정 5줄(누가·몇 시). 왼쪽 6할 도면(넘기기 72px·썸네일·PDF 는 파일 열기, 뷰어는 F3 마운터), 오른쪽 고객·만들 것·공정·[불량 알리기]·[보류]·[제작 완료](검수 전 회색)·위 막대 [인쇄](F8)·[상세]. 쓰기는 전부 기존 API(공정 체크·불량·보류·시작/완료). 공정 JS 는 F2 ② 의 스코프 재작성 결과를 그대로 쓴다.
- 12.1 카드 링크를 이 라우트로 바꾼다.

### 12.3 첫 화면 탭 — 날짜 · 내 공정 · 바뀐 것 · 찾기 (D13 → D17·D18, 2026-11-10 사용자 "최우선은 생산" · "3안으로")
- 사용자 세 요청을 생산 첫 화면에: ① 글자 크기 조절 ② 이유 없는 빈 공간 없이 ③ 날짜별로 시공을 한눈에. 시안 `docs/design/mockups/tablet-production-home-v2.html` 안 3.
- **날짜(첫 화면, `?tab=date` 기본)**: 왼쪽 2주 띠 = 지난 7일(한 줄) · 오늘부터 11일 · 그 뒤(한 줄), 줄마다 막대(제작 완료·만드는 중·제작 대기·도면 기다림, SVG 좌표라 인라인 style 없음)와 "만들 것 / 전체". 띠 아래 = 지난 시공일(7일 넘음)·시공일 없음. 오른쪽 = 고른 날 한 장: 만들 것(제작 대기~검수 끝·보류)은 공정 4칸과 큰 줄(바뀐 것 → 만드는 중 → 제작 대기 순), 도면·컨펌 기다림과 제작 완료는 작은 칸 3열, 아래에 다음에 만들 것이 있는 날 미리 보기(화면이 비지 않게). 날 고르기는 보이기/숨기기만(`?day=` 로 처음 고른 날, 모르면 오늘). `production_home_days(rows, today, selected, past_hidden=)`.
- **글자 크기**: 제목 줄에 `foms_font_scale_control.html`(열쇠 `/erp/production`). `home.css`·`sheet.css` 의 px 글자는 전부 `calc(Npx * var(--foms-fs, 1))`. 띠 너비·칸도 배율을 따라가고, 띠 위치는 제목 줄 실제 높이(`--fph-bar-h`, JS 가 잼).
- **내 공정**: 공정 4탭(사람마다 마지막 탭 localStorage), 그 공정이 첫 미완인 생산 중 주문만, [<공정> 끝] = `POST …/production/steps`. 일의 양은 보이지 않는다(D11). 줄 아래 "곧 올 것" = 바로 앞 공정에 와 있는 주문(재단은 제작 대기) — 줄이 적어도 빈 화면이 아니다.
- **바뀐 것**: 받은함 = `collect_production_change_alerts` 의 alerts + 취소 주문(묘비), [확인했어요] = `POST /api/orders/<id>/production/change-ack`. 옛 "이번 주" 탭의 요일 칸은 날짜 탭이 대신해 없앴다(`?tab=week` 는 날짜로).
- **찾기(`?tab=all`)**: 12.1 의 전체 주문 한 줄 목록(찾기 칸·보기 칸·날짜 묶음 접기) 그대로.
- 머리 숫자 "전체 N건" = 캡과 무관한 실제 총계(`stats['total']`).
- **11-10 리뷰·실화면 고침(P6, 원장 §16)**: "내 공정" 탭 숫자 = 공정 줄에 선 주문 수(한 규칙 `production_home_queue_key`), 보류 표시는 생산 단계(제작 대기~검수)일 때만 — 도면·컨펌 단계 보류는 기다림. "바뀐 것" 숫자 = 받은함 장 수(취소 주문 포함, 모든 탭에서 셈). [다시 받기] 는 직접 고른 날만 주소에 붙인다(`days.auto`). 날짜 장 글자는 "도면·컨펌 기다림", 지난 시공일 단추는 `N건 +안 읽은 수`. 글자를 키우면 글자가 든 칸 폭도 같이(큰 줄 도면 칸 · 내 공정 시공일 칸 · 도면 파일 칸), 바뀐 줄은 품목 줄 두 줄까지. 칸반 옆 시트 바닥 단추는 넘치면 다음 줄, 붙은 긴 주소는 칸 안에서 끊는다. 작업 시트 뒤로 단추는 "생산" — 첫 화면에서 왔으면 고른 날·탭으로 돌아간다(같은 출처·같은 경로만).
- **D20(11-10) · 운영 실측 고침(P8, 원장 §17 M1~M4)**: 바뀐 것(탭 숫자 · 받은함 · 빨간 테두리 · 정렬 · 찾기 거르기)은 생산 단계 주문(제작 대기~검수 끝)만 — 도면·컨펌 기다림과 제작 완료 주문의 변경은 치지 않는다(취소 주문 묘비는 그대로). 내 공정 줄과 곧 올 것은 시공일 빠른 순(지난 날 맨 앞 · 시공일 없음 맨 뒤). 큰 줄의 품목·치수 글은 두 줄까지. 날짜 장 미리 보기는 6줄까지 채운다 — 뒤 장들("그 뒤" 포함)의 만들 것을 띠 순서로 잇고(한 장이면 그 장 제목, 여러 장이면 "다음에 만들 것 n"), 모자라면 남은 자리만큼 지난 7일의 만들 것을 "밀린 것" 으로(자기 자신은 안 닮, 아래 두 장에는 없음). 아래 단추는 "지난 시공일 N건" + 작은 글 "M건 더". 큰 줄의 긴 이름은 말줄임표로 줄고 주문 번호는 늘 보인다. **D21(11-11)**: 만들 것 줄(날짜 탭 큰 줄 · 내 공정 줄)의 이름 오른쪽에 `발주 <발주사> · 담당 <영업 담당>`(`orderer_name` · `manager_name`, 빈 쪽은 빼고 둘 다 없으면 안 그림) — 자리가 모자라면 그 글만 다음 줄로, 낱말 단위 줄바꿈. **시인성(11-11, 사용자 "전부 회색이라 구분이 안 돼")**: 글 한 덩이가 아니라 조각(`_by_parts` → `.fph-by.is-o` / `.is-m`)으로 그린다 — 머리말(발주/담당)은 12px 회색, 이름은 굵게, 발주사는 진한 글자 · 담당은 남색(`--fph-brand-dark`). 칩 · 테두리 · 그림 없이 글자 색 · 굵기만, 가운뎃점 대신 조각 사이 틈. 날짜 큰 줄의 이름 글자 크기는 14px 그대로(한 줄에 들던 것이 안 밀리게).
- **D22(11-11, 사용자 "제작 대기 뒤 바뀐 것만") 변경 알림 기준선**: 변경 감지 창의 시작은 먼저 옛 규칙으로 정한다 — 본인의 마지막 `PRODUCTION_CHANGE_ACK`, 없으면 마지막 파이프라인 진입(`STAGE_CHANGED`, to 가 `PROD_STAGES` 안이고 from 이 그 밖), 없으면 `erp_stage_updated_at`, 없으면 `created_at`. 그다음 주문의 지금 단계(`erp_stage_code`)가 생산·시공이면 **마지막 생산 진입 시각을 바닥으로 깔고 둘 중 늦은 쪽**을 쓴다. 생산 진입 = 단계 이동 이벤트(`STAGE_CHANGED` · `STAGE_OVERRIDE` · `CUSTOMER_CONFIRMED` · `PRODUCTION_STARTED`) 중 to 가 생산·시공이고 from 이 그 밖인 것(컨펌 끝과 컨펌에서 바로 [제작 시작] 은 `STAGE_CHANGED` 를 안 남긴다). 생산 → 시공 · 완료 취소 · 수정 제작은 안쪽 이동이라 바닥을 안 옮긴다. 지금 컨펌 단계인 주문(되돌린 것 포함)에는 바닥이 없어 전과 같다. 같은 규칙이 미확인 알림과 상설 이력에 똑같이 쓰이고, 생산 첫 화면 · 생산 보드 · 작업 시트가 함께 따른다(`production_change_alerts.py` `_production_entry_floor`). `erp_stage_updated_at` 은 제작 완료 · 수정 제작 때도 갱신돼 바닥으로 쓰지 않는다.
- **11-11 자잘한 것 정리(P13, 원장 §25)**: 곧 올 것 줄도 긴 이름은 이름만 말줄임 · 번호는 늘 보임. 전체 화면 작업 시트(가로 태블릿)는 머리 줄 한 줄 고정 + 몸통이 남은 높이를 채움(페이지 높이 = 화면 높이). 칸반 옆 시트 머리 줄은 떠 있는 닫기 단추 자리를 비운다. 날짜 장 나누기는 캡 · 정렬과 같은 납작 열 `erp_construction_date` 를 쓴다(R6). 날짜 탭 읽기 모델은 `foms/services/production_home_days.py`(나머지는 `production_home_read_model.py`).
- 제목 줄 오른쪽(받음 표시 · 글자 손잡이 · [다시 받기])은 한 묶음 `.foms-prod-home__tools` — 줄이 넘치면 셋이 같이 내려간다(단추 하나만 떨어져 한 줄이 비지 않게).

### 12.4 착지 (F7 ① 갱신)
- **D19(11-10, 사용자 "누구나 새 첫 화면") 태블릿 레일 "생산" = 첫 화면**: 태블릿 가로 레일(`foms_tablet_rail.html` ← `build_tablet_rail_items`)의 생산 단추는 첫 화면을 볼 수 있는 사람(`can_view_production_home` — `foms/services/production/home_access.py`, 문지기 `_require_home_user` 와 한 규칙: 관리자 · CS · 영업 · 생산, 협력사 제외)이면 `/erp/production/home` 으로 간다. 못 보는 팀과 켜진 프리랜서는 보드 그대로. PC 메뉴 · 폰 아래 메뉴 · split 셸 레일(마우스 좁은 창 전용) · 로그인 뒤 착지는 그대로. `/erp/production` 아래(첫 화면 · 전체 화면 시트)는 전부 레일 생산 강조(`resolve_tablet_rail_active_id`, 조각 이동 뒤에는 `data-foms-rail-match`). 옛 생산 보드는 첫 화면 탭 줄 끝 [보드](`data-foms-home-board`, 온전한 페이지 이동 `data-foms-erp-no-shell`)로 들어간다. 전에는 레일이 누구에게나 보드로 가서 새 첫 화면은 주소를 쳐야만 보였다(운영엔 생산팀 계정이 없어 아무도 못 봄).
- `is_production_home_user(user)`(`post_auth_navigation.py`) = 팀 PRODUCTION 이고 협력사 아님(프리랜서는 영업팀만 가능해 따로 보지 않음). `authenticated_home_url`·`resolve_post_login_redirect`(legacy `/`)·`listing.py index()`·`routes.py switch_user` 네 곳이 `production_home_url()` 로. 기기 무관. 시험 `tests/domains/test_post_auth_navigation.py` 4 사례(PC 로그인·`next=/`·`/`·CS 대조군).
- **D15(11-09 저녁) 도장 공정 삭제** — 공정은 재단·엣지·조립·검수 4단계. `_PRODUCTION_STEP_DEFS`(API)·`PRODUCTION_HOME_STEP_DEFS` 에서 paint 제거, 옛 주문의 `production.steps` 에 남은 paint 는 읽을 때(API GET·`_ensure_production_steps`·첫 화면·시트·모바일 큐 "공정 n/N") 걸러 낸다. 데이터 이행 없음. 시안 그림의 도장 칸은 옛 그림.

## 14. 출고 탭 — 하루치 출고표에서 시공자 배정 (D23~D31, 2026-11-11 — **승인됨: "이대로 만들기"**)

### 14.0 한 줄
태블릿 가로 출고 탭을 "하루치 출고표 한 장"으로 바꾼다. 줄은 시공자 묶음 카드로 모이고, 맨 끝 시공자 칸을 누르면 이름판이 떠서 누르는 즉시 저장된다. 세부정보는 줄을 누르면 오른쪽 서랍. 시안 = `docs/design/mockups/tablet-shipment-styled-sheet.html` 안 17(누른 모습은 16n 이름판 · 16s AS 서랍).

### 14.1 결정 (사용자 — 다시 묻지 않는다, 원장 §27)
- **D23** 출고 탭의 일 = 출고 스케줄 짜기(포장 · 상차 준비는 생산). **D24** 정하는 것 = 누가 가는지 · 몇 시에 · 날짜 옮기기 · 협력사 희망일 확정. 보통 오전/오후 2타임, 한 집에 여러 명이 갈 수 있다. 짜는 사람 = 출고 담당, 권한 = 출고 · 관리자 · CS.
- **D25** 여러 명이 가면 자수는 사람 수로 나눠 센다. **D26** 시공자 배정이 핵심 · 단순 · 직관, AS 일정도 같이 짠다(AS 전담 기사가 있고 가끔 시공팀도 AS 를 간다).
- **D27** 바탕 = 회사 엑셀 출고일지(칸 9개와 순서). **D28** 표는 단순하게, 세부(특히 AS 내용)는 누르면 서랍 — AS 는 AS 탭에서 받아 온다.
- **D29** 엑셀 생김새와 본문 칠(주황 · 파랑 · 분홍)은 뺀다, 같은 시공자 색 묶음만 남긴다. **D30** 모양 = 안 17 시공자 묶음 카드. 이름 누르는 곳 = 칸 옆 이름판, 세부 = 오른쪽 서랍(질문 창이 답 없이 닫혀 권고안으로 둠).
- **D31(11-11 질문 창 "영업팀은 막기")** 출고 배정 · 시공시간 · AS 넣기를 쓸 수 있는 사람 = 관리자 · CS팀 · 출고팀뿐. 영업팀은 PC 를 포함해 출고 탭을 보기만 한다.

### 14.2 지금 (워커 조사 + 총괄이 코드로 확인)
- 태블릿 가로의 `/erp/shipment` 는 이미 전용 그리드를 그린다: `templates/shipment/partials/tablet_ship_grid.html`(6칸 · 시공팀 머리줄), 줄을 누르면 오른쪽 배정 시트 `GET /erp/shipment/tablet-sheet/<id>`(`tablet_sheet.html` — 팀 고르기 · 시간 `09:00`/`14:00`/직접 · [배정 적용]). 문지기는 CSS(`static/css/contexts/shipment/shipment-dashboard-columns.css` — `body.erp-mobile-v2-layout` + 터치 가로).
- 줄 = ORM `Order`(추가 쿼리 없음, `foms/web/shipment/dashboard.py:604-680`). 그날 조건 = 일정 표 `construction` 이 그날, 또는 AS 상태이고 `as_visit` 이 그날. **AS 는 별도 표가 아니라 같은 주문의 상태**다.
- 저장 `POST /api/erp/shipment/update/<id>`(`foms/api/shipment/settings.py:189`): `construction_workers`(이름 배열 · 최대 10) · `construction_time`(자유 글) · `site_extra`. 동시 수정은 `settings_version`/`If-Match`, 중복은 `Idempotency-Key`. **알림 · 푸시 없음**(이벤트 · 변경 원장 · 감사 로그만).
- **출고팀은 지금 쓰기 403**: 정책 `SHIPMENT_EDIT` 는 CS · SALES · SHIPMENT 인데(`foms/services/orders/order_mutation_policy.py:209`) 그 앞의 `@erp_edit_required`(관리자 · CS · SALES, `foms/services/erp_permissions.py:366`)가 먼저 막는다 — 정책과 데코레이터가 어긋난 상태. AS 추천 4종(`foms/api/shipment/recommendations.py`)도 같다. 시공일 쓰기만 출고팀이 된다(`can_edit_construction_schedule`).
- 시공시간 칸이 둘: 출고 표가 보이는 `sd.shipment.construction_time`(자유 글) 과 주문의 `sd.schedule.construction.time`(오전 · 오후 · 종일).
- 자수: 줄 합 `visible_spec_units`. 사람별 잔여 `compute_team_remaining_units_for_date`(`dashboard.py:305`)는 여러 명이면 사람마다 전부 빼고, `construction` 만 세므로 AS 는 안 센다. 태블릿 묶음 집계 `_compute_shipment_team_group_meta` 는 첫 시공자가 전부 가진다.
- 시공자 설정 = `{name, capacity(기본 10), off_dates}`(`foms/services/erp_shipment_settings.py:99`) — AS 전담 표시는 없다.
- AS 넣기 = 기존 추천: 그날 출고건 근처(길 30분 이하 · 건마다 2개)의 방문일 없는 AS. `apply` 는 AS 방문일을 그 출고건 시공일로, 작업자를 그 출고건의 **ID 배정**으로 복사한다(이름 배열은 안 쓴다 — `foms/services/shipment/as_recommendation.py` 머리말).
- AS 세부를 주는 JSON API 는 없다. HTML 조각 둘: `GET /erp/as/card-detail/<id>` · `GET /erp/as/timeline/<id>?readonly=1`(`foms/web/cs/as_dashboard.py:153,194`).
- [이미지 저장] `static/js/shipment/image-export.js` 는 PC 표 DOM 을 읽는다(태블릿에서는 숨겨져 있지만 DOM 에 있다).
- 운영에 SHIPMENT 팀 활성 계정 0명(`foms/services/notifications/shipment_change.py:66` 주석, 08-05 조회).

### 14.3 바꾸는 것 — 주소 · 줄 · 저장 API 는 그대로, 태블릿 그리드와 시트만
- **표(안 17)** `tablet_ship_grid.html`: 6칸 → 출고일지 9칸. 세로 선 없음 · 왼쪽 맞춤 · 줄 46px. 시공자 묶음마다 카드(시공자 없음 묶음이 맨 위, 그다음 설정에 적힌 시공자 순, 설정에 없는 이름은 뒤). 묶음 안은 일반 줄 뒤에 AS 줄.

  | 칸 | 값 |
  |---|---|
  | 번호 | 화면 순서 1..N |
  | 대리점 | `orderer_name`. AS 줄은 검은 `AS` 딱지 |
  | 제품명 | 그날 품목 첫 이름 + `외 n` |
  | 규격 | 줄 자수 합(소수 한 자리). AS 줄은 접수 내용 앞머리 한 줄(넘치면 …) |
  | 현장주소 | `address` 한 줄(넘치면 …) |
  | 고객 | 이름만(전화는 서랍) |
  | 시공시간 | `shipment.construction_time`. 비었으면 주문의 오전 · 오후 · 종일을 흐린 글로 |
  | 영업 담당 | `manager_label` |
  | 시공자 | 사람 색 덩어리(10색, 묶음 순서대로 번호 — PC 는 이름 순이라 같은 사람이 PC 와 다른 색일 수 있다), 같은 사람 줄은 위아래로 붙음. 없으면 빨간 점선 `＋ 시공자` |

  본문 칠은 없다(D29). 금액 없음(D7). 위 줄 = 날짜 이동 · `N건` · `시공자 없음 n` · 글자 손잡이 · [AS 넣기] · [이미지 저장].
- **묶음과 사람별 집계** 새 서비스 `foms/services/shipment/tablet_day_sheet.py`(템플릿 안 계산을 서비스로): 묶음 목록(키 = 첫 시공자 — 기존 규칙 그대로) + 사람별 `건수 · 자수`. 자수는 **줄 자수 ÷ 그 줄 시공자 수**(D25), AS 줄은 건수만.
- **이름판** 새 JS `static/js/shipment/tablet-ship-assign.js`(300줄 안): 시공자 칸을 누르면 그 칸 옆에 판. 이름마다 사람 색 띠 · `n건 · m자`(용량을 넘으면 숫자 빨강 — 막지는 않음, 지금 정책 그대로) · 그날이 `off_dates` 면 `쉼`(흐림). 이름을 누르면 그 줄에 넣기/빼기 → 바로 저장(기존 API, `settings_version` + `Idempotency-Key`). [직접 쓰기](설정에 없는 이름 · 지역 이름) · [비우기]. 판을 닫으면 그날 조각을 다시 받아 묶음을 새로 그린다(묶음 재배치는 서버 한 곳에서). 409 는 "다른 사람이 먼저 고쳤어요" + 다시 받기.
- **서랍** `tablet_sheet.html` 을 넓힌다(주소 `GET /erp/shipment/tablet-sheet/<id>` 그대로): 고객 · 전화 · 주소 전체 · 품목 전부(이름 · 규격) · 현장 메모(읽기) · 시공시간([오전 8시] · [오후 1시] · 직접 → 같은 저장 API). 시트 안 "팀 고르기 + [배정 적용]" 은 이름판이 대신하므로 뺀다. **AS 줄**이면 `AS 정보` 묶음: AS 탭의 읽기 조각(`/erp/as/timeline/<id>?readonly=1`)을 서랍 안에 불러 붙이고 [AS 탭에서 열기](`/erp/as?focus_order=<id>`).
- **AS 넣기** 위 줄 단추와 표 아래 `＋ 날짜 없는 AS — 이 날에 넣기`: 누르면 서랍에 기존 추천 목록(고객 · 주소 · 접수 내용 한 줄 · `○○ 현장에서 n분`) + [이 날에 넣기](`apply`) · 넣은 것은 [되돌리기](`cancel`). 새 API 없음.
- **[이미지 저장]** 기존 `image-export.js` 를 태블릿 위 줄에서 부른다(나오는 그림은 지금 PC 와 같은 출고일지 표).
- **자수 나누기(D25)** `compute_team_remaining_units_for_date` 도 같은 규칙으로 — 두 명이 간 22.4자 줄은 각자 11.2자. 이 함수를 부르는 곳은 태블릿 시트(`dashboard.py` `erp_shipment_tablet_sheet`) 한 곳이라 **바뀌는 것은 태블릿의 사람별 잔여뿐**이다. PC 패널은 날짜별 합계(`compute_shipment_panel_aggregates` — 주문 자수를 한 번만 셈)라 바뀌지 않는다(초안의 "PC 숫자도 바뀐다"는 틀렸음 — 11-11 워커가 코드로 확인).

### 14.4 권한 (D24 — 코어 변경)
- 새 헬퍼 `can_edit_shipment(user)`(`erp_permissions.py`): 관리자, CS팀, 출고팀 STAFF · MANAGER(협력사 · 비활성 제외). **영업팀(SALES — 실측 `MEASURE` 포함)은 안 된다(D31).** 정책 `SHIPMENT_EDIT` 의 팀도 CS · SHIPMENT 로 고치고 매니페스트를 다시 만든다. 새 데코레이터로 `POST /api/erp/shipment/update/<id>` 와 AS 추천 4종의 `@erp_edit_required` 를 바꾼다. 정책과 데코레이터가 같은 규칙을 본다.
- 화면의 `can_edit_shipment` 값(`dashboard_main.html:39`)도 이 헬퍼에서 온다 → 출고팀에게 PC 편집 칸도 열리고, 영업팀에게는 PC · 모바일 편집 칸이 닫힌다.
- 그대로: 시공팀(읽기만 · 내 것만) · 협력사 · 켜진 프리랜서 · VIEWER 는 쓰기 불가. 시공일 쓰기(`can_edit_construction_schedule` — 영업 포함)는 건드리지 않는다.
- 사용자 몫: 운영에 출고팀 계정이 없다 — 출고 담당 계정의 팀을 출고팀으로 두어야 한다(관리자 · CS 계정은 지금도 된다).

### 14.5 시험
- 권한: 관리자 · CS · 출고팀 STAFF 가 배정 저장 · AS 추천/넣기/되돌리기 통과, 영업팀 · 시공팀 · 협력사 · VIEWER 403(되돌리면 실패).
- 집계: 묶음 순서(없음 먼저 · 설정 순 · 묶음 안 AS 뒤) · 번호 · 두 명 줄 자수 반씩 · AS 는 건수만 · 잔여 계산(되돌리면 실패).
- 템플릿: 칸 9개 순서 · `AS` 딱지 · `＋ 시공자` · 본문 칠 클래스 없음 · 금액 없음 · 인라인 style 없음 · 글자 `calc(Npx * var(--foms-fs, 1))` · 자산 핀.
- 스테이징 실화면(1280×800 터치): 쓰기는 가상 주문 `CLAUDE-TEST-` 로만(배정 저장은 알림이 없다). 시공일 옮기기는 누르지 않는다(실제 직원 방으로 알림).

### 14.6 단계 (각 단계 = 스테이징까지, 운영은 지시 때)
| 단계 | 일 |
|---|---|
| P14-1 | 권한: `can_edit_shipment` + 데코레이터 교체 + 시험 |
| P14-2 | 묶음 · 사람별 집계 서비스 + 자수 나누기(D25) + 시험 |
| P14-3 | 표(안 17) + 이름판 + CSS · JS |
| P14-4 | 서랍 넓히기 + AS 정보 |
| P14-5 | AS 넣기 목록 · [이미지 저장] |

### 14.7 뒤로 · 구현 전에 확인할 것
- 뒤로: 날짜 옮기기(쓰면 도면 · 생산 · 시공팀과 협력사로 알림이 나간다 — 서랍 단추로 따로) · 협력사 희망일 확정을 태블릿 서랍에(지금은 표 위 2주 판 그대로) · AS 전담 표시(설정에 칸이 없다 — 1차는 설정 순서로만) · [출고 확정] · 이름판에서 순서 바꾸기.
- 확인: ① AS 넣기는 ID 배정만 복사하므로 넣은 뒤 AS 줄 시공자 칸(이름 배열)에 이름이 보이는지 — 안 보이면 P14-5 전에 따로 보고. ② 출고팀 계정이 AS 탭 읽기 조각을 열 수 있는지. ③ 숨겨진 PC 표에서 [이미지 저장] 이 그대로 되는지.
