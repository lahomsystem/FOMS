# 리뷰어 ① 반증 — 보고 원문 (2026-11-09)

> 원장 §5 의 본문. 리뷰어(Fable 5.1 high, 읽기 전용, HEAD `ea4376ea1`) 보고를 그대로 붙였다. 총괄 재확인·반영은 원장 §6.

## 심각 순 상위 5

1. **F2 ③ 공정 블록 "컨테이너 1곳 일반화"는 성립하지 않는다.** `foms-production-steps.js` 는 리스트·불량 칩·상태·헤더 카운트를 전부 `document.querySelector` 첫 매치로 잡고(6곳), `currentOrderId` 는 `[data-foms-prod-steps-open]` 탭에서만 세워지며, 가로 DOM 에도 세로 오프캔버스 사본이 **앞에** 있어 시트 안 사본은 영영 선택되지 않는다. (확인됨)
2. **F7 ① "`/` 재리다이렉트도 같은 함수를 타므로 함께 바뀐다"는 거짓.** `listing.py:158` 과 `post_auth_navigation.py:100-101` 이 `url_for('erp_dashboard.erp_dashboard')` 를 직접 부른다. (확인됨)
3. **F7 ② 읽기 전용 시트에 `can_edit=False` 만 주면 승인 단추가 그대로 남는다.** `tablet_dashboard_sheet.html:95-105` 의 승인 단추는 퀘스트 DTO 로 렌더되고 서버(`quest.py:370`)는 팀 불일치로 거부 → 죽은 단추. (확인됨)
4. **F1 ① "레일 맨 아래 배율 단추"는 130% 에서 화면 밖이다.** 레일은 fixed + overflow-y auto, zoom 으로 뷰포트 CSS 높이 615px — 9탭+벨+아바타(약 680px)만으로 넘친다. (확인됨·수치는 계산)
5. **F-13 60초 합치기는 "품목 취소 2개"를 한 줄로 덮어쓴다.** `_find_recent_notification` 이 같은 라벨 60초 내 row 의 title/message 를 덧써 첫 품목 이름이 사라지고 push 도 안 나간다. 호출 지점 `:46` 은 해시 헬퍼 안(실제 tx `:71-82`, commit `:91`). (확인됨)

## 표

| 번호 | 설계서 위치 | 주장 | 깨짐 여부 | 근거 경로:행 | 고치면 되는 한 줄 |
|---|---|---|---|---|---|
| 1 | §5 F2 ③ | `foms-production-steps.js` 컨테이너 1곳 일반화 | **깨짐** | `static/js/production/foms-production-steps.js:55-57,159,191-194`(document 전역 6곳) · `:271-279` openSheet 가 Bootstrap Offcanvas 필수 · `:283,252` `currentOrderId==null` 이면 즉시 return · `:167` loadSteps 는 openSheet 안에서만 | 시트 블록은 `data-foms-prod-steps-sheet="<id>"` 루트를 받아 스코프 객체(root 기준 querySelector)로 재작성하고, fragment 삽입 뒤 `foms:erp-shell-fragment-swapped`(`fragment-loader.js:135`) 또는 시트 인라인 `<script>`(선례 `tablet_sheet.html:210-232`)에서 `loadSteps(id, root)` |
| 2 | §5 F2 ③ | 세로 바텀시트 마크업을 그대로 시트 안에 | **깨짐** | `dashboard_body.html:128-131` 터치 기기는 `wants_mobile_width_surfaces` True(`feature_flags.py:271`) → 가로 DOM 에도 `mobile_queue.html:113` 오프캔버스가 칸반(`:155`)보다 앞에 존재. `id="foms-prod-defect-reasons"`·`data-foms-prod-steps-sheet-list` 중복 | id 없애고 data-속성만, 스코프 객체 |
| 3 | §5 F1 ② | 카드 "공정 n/5" 단추 탭 = 시트 열기 | **깨짐** | `foms-production-steps.js:304-313` capture 리스너가 `stopImmediatePropagation` 후 세로 오프캔버스를 연다 · `tablet-side-sheet.js:90-91,424` `button` 은 INTERACTIVE 라 카드 탭 위임도 안 탐 | 카드 글은 `<span>` 으로, 또는 `data-foms-sheet-url` 경로 |
| 4 | §5 F7 ① | `/` 재리다이렉트가 같은 함수를 탐 | **깨짐** | `foms/web/orders/listing.py:158-159` · `post_auth_navigation.py:100-101` 직접 dashboard | 두 곳을 `authenticated_home_url`/`redirect_to_authenticated_home` 로, `test_post_auth_navigation.py:36,61` 에 PRODUCTION 사례 |
| 5 | §5 F7 ① | PC(마우스) 생산팀 착지 | 조건부 | `post_auth_navigation.py:42-44` 모바일 코호트 아니면 `order_pages.index` | 팀 분기를 `should_use_erp_mobile_home` 밖에 둘지 명시 |
| 6 | §5 F7 ① | switch_user 전례 자리 | 버팀 | `auth/routes.py:585-588` 시공팀 분기 뒤 `request.referrer or authenticated_home_url` | 분기를 `:585` 옆에 |
| 7 | §5 F7 ①·§6 | 협력사·프리랜서 충돌 없음 | 버팀 | `partner_scope.py:26-,204-207`, `http.py:251` · `freelancer_scope.py:352,360-365,85` | 생산팀 분기는 `partner_org_id is None` 조건 |
| 8 | §5 F7 ② | `can_edit=False` 로 읽기 전용 | **깨짐(부분)** | `tablet_dashboard_sheet.html:65,84` 두 링크는 분기 가능 · `:87-88` `bs.link_endpoint` · `:95-105` 승인 단추는 `q.*` 로만 · API `quest.py:375-376` | 승인 단추·현재 작업 링크도 `can_edit_erp` 로 감싸기 |
| 9 | §5 F7 ② | 같은 DTO, 쿼리 변화 없음, 금액 없음 | 버팀 | `dashboard_dto.py:67-68` · `dashboard.py:655-665` | — |
| 10 | §5 F7 ② | 최상위 문서 열기 | 조건부 | `dashboard.py:641-642` `Sec-Fetch-Dest: document` 면 `/edit/<id>` 302 → 생산팀 두 번 튕김 | 생산팀은 `erp_order_mobile_detail` 로 302 |
| 11 | §5 F2 ④ | 전체 목록 쿼리 0 | 버팀 | `drawing_confirm_cleanup.py:93-108` · `drawing_workbench_display.py:80-139` | 그대로 |
| 12 | §5 F2 ④ | "바뀐 도면" 데이터 이미 로드 | 조건부 | `dashboard.py:462` alerts 는 주문 단위, 파일 key 없음 | 장마다 표시하려면 `drawing_transfer_history` TRANSFER(hotfix) `files`(`erp_orders_drawing.py:413-414`) + ack 윈도 비교 |
| 13 | §5 F3 | 뷰어 API 두 사본 | 버팀 | `layout-scripts-core.js:110,171,629` · `layout_scripts.html:486,547,1005` | — |
| 14 | §5 F3 | PDF 는 뷰어 밖 | 조건부 | `layout-scripts-core.js:110-144` 확장자 필터 없음 | 서버 JSON 에 `_PROD_SHEET_IMG_EXT`(`dashboard.py:328`)로 이미지만 |
| 15 | §5 F3 | 게이트 | 버팀 | `tablet-domain-sheets.js:28-44` | — |
| 16 | §5 F1 ① | `ui-zoom.js` 가 레일 단추를 잡음 | 버팀 | `ui-zoom.js:55-64, 43` | include 만(variant 새로) |
| 17 | §5 F1 ① | 레일 72px·계약 | 조건부 | `foms-tablet-rail.css:25-41, 174-189` · 계약 `test_tablet_rail_contract.py:93,110-123` | 단추를 브랜드 바로 아래 또는 벨 위, 세로 3단 48px |
| 18 | §5 F1 ③ | 60vh 보정 | 버팀 | `foms-tablet-production-kanban.css:926` · `foms-ui-zoom.css:4` | — |
| 19 | §5 F6 ① | `_primary_ids`·`production`·시험 | 버팀 | `erp_mobile_shell.html:26-55` · `test_foms_nav_badges.py:38` | `elif` 를 `_construction_only` 꼴로 |
| 20 | §7 F-13 | 호출 `:46` 뒤, 합치기 그대로 | **깨짐** | `erp_orders_item_cancel.py:44-47` 해시 · tx `_mutate :71-82`, commit `:91` · `production_change.py:68-98,150-155` 덧쓰기·push 생략 | `_mutate` 안 `:78` 뒤 `apply_…(kind="item_cancel", merge=False)`(`:91` 뒤 finalize), 라벨 `_KIND_LABEL` 추가 |
| 21 | §7 F-13 | `PROD_STAGES` 밖 | 버팀 | `production_change.py:135-136` | — |
| 22 | §7 F-13 | 매니페스트 불변 | 조건부 | REV-99 writer 인벤토리가 `erp_orders_item_cancel.py lineno 78` 을 핀 | 삽입은 `:78` 뒤에만, 아니면 `refresh_inventories.py` 후 커밋 |
| 23 | §5 F8 | `erp_order_label` 꼴 | 버팀 | `dashboard.py:878-915`, `orders/label.html` 31줄 | 팀 게이트는 `_can_edit_production_steps`(`api/production/orders.py:99-120`) 재사용 |
| 24 | §5 F8 | 도면 이미지 생산팀 200 | 버팀 | `files/routes.py:210-233` → `user_can_read_order` | — |
| 25 | §5 F8 | GET 매니페스트 비대상 | 버팀 | `test_auth_enforcement.py:132-145` | — |
| 26 | §5 F8 | label.html 인라인 스타일 0 | 조건부 | `label.html:23-30` 인라인 `<script>` 있음 | 인쇄 단추 JS 는 외부 파일로 |
| 27 | §8 | 공정 체크 실패 시 되돌림 | 버팀(무의미) | `foms-production-steps.js:292-299` 낙관 갱신 없음 | 문구만 |
| 28 | §8 | alert 문구·confirm 계약 | 버팀 | `tablet-domain-sheets.js:134,261,296` · 계약 `:73,99` | — |
| 29 | §6 세로 | 70vh 미보정 | 버팀 | 130% 실높이 91% 상한, 머리·닫기 보임(계산) | 선택 |
| 30 | §9 | `test_production_dashboard_query_count.py` 가 시트 쿼리 보장 | **깨짐(오귀속)** | `:133-164` 대시보드만 | 시트 라우트용 카운트 단언 새로 |
| 31 | §9 | 새 JS 300줄 래칫 | 조건부 | `file_size_baseline.json:245` 에 `foms-production-steps.js` 등재 | — |
| 32 | 전수표 #19 ② "O" | 모바일 상세 취소 품목 제외 | 조건부(△) | `order_detail_mobile_v2.html:223-226` 라벨 붙여 표시 | △ 로 |
| 33 | 전수표 #6 ① "O" | 상차·시공일 순 | 버팀 | `production_read_model.py:314` | — |
| 34 | 전수표 #3·#2 | 403 원인 | 버팀 | `dashboard.py:653-654`, `erp_permissions.py:366-380` | — |

## 확인 못 한 것
- 실제 갤럭시 탭 쿠키 `foms_vw`·`foms_ptr` 값(실기기 미확인).
- 130% 레일 높이 수치(680px)는 계산.
- `bs.link_endpoint` 가 생산팀에게 어느 페이지로 가는지.
- `erp_quest_display.py:407` approvable_teams 가 사용자 팀을 안 보는지(함수 본문 미열람).
