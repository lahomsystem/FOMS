# 옛 생산 보드 없애기 — 설계서 (1판)

> 작성일 2026-11-27 | 상태 **승인 대기** | 등급: **코어 변경**(화면 권한 · 프리랜서 범위 · 메뉴 계약 · 라우트 지우기 — 설계 → 승인 → 구현)
> 계기: 사장님 2026-11-27 "legacy 보드 없애" → 질문 창 답 넷(§1).
> 기준 코드 `work/lgspec` `01efc0fc9`. 앞 설계서 `2026-11-21-production-pc-viewer_SPEC.md` §9 · §10(R0 · R1 은 들어갔고 R2 · R3 이 이 설계다) · 원장 `docs/plans/2026-11-09-tablet-production-ui-ledger.md`(D19 · C36).
> 이 문서에서 "확인" = 코드를 직접 읽고 본 것, "추정" = 짐작. 사람 이름은 모두 가짜다.

## 0. 한 줄

옛 생산 보드(`/erp/production/dashboard` — PC 표 · 폰 큐 · 태블릿 칸반 · 옆 시트)를 코드에서 지운다. 그 전에 지금 옛 보드만 쓰는 두 무리 — **켜진 프리랜서**(내 주문만 보기) · **팀 없는 직원 계정** — 를 새 첫 화면(`/erp/production/home`)에 **보기 전용**으로 들인다. 옛 주소 둘은 새 화면으로 넘겨주는 길(302)만 남긴다. 다 만든 뒤 한 번에 올린다.

## 1. 사장님 답 (2026-11-27, 글자 그대로)

1. 프리랜서에게 무엇을 보일까 → **"새 화면에 '내 주문만' 만들어 보내기 (Recommended)"**
   - 질문 창 설명: "프리랜서가 새 생산 화면을 열면 자기가 담당한 주문만 보이게 만든 뒤 그쪽으로 보냅니다(보기만, 단추 없음). 남의 주문이 새지 않는지 시험으로 확인하고 나서 옛 보드를 없앱니다."
2. 팀 없는 직원 계정 → **"새 화면을 보기만 열어 주기 (Recommended)"**
   - 설명: "팀이 없는 직원 계정도 새 생산 화면을 보기 전용으로 볼 수 있게 합니다(단추 없음)."
3. 옛 화면에만 있는 기능 중 살릴 것 → **"필요없어"** — QR 라벨 인쇄 · PC 경보 숫자 · 연락처/주소/실측일/첨부 · 거르기 줄 모두 옮기지 않는다.
4. 순서 → **"한 번에 지우기"**
   - 설명: "프리랜서 · 팀 없는 계정 처리까지 다 만든 뒤, 길 막기와 코드 지우기를 한 번에 올립니다. 그때까지 옛 화면은 지금처럼 열립니다."

앞선 말: **"legacy 보드 없애"**.

이 답은 앞 설계서 §10 의 "R2 → 2주 → R3 → 한 달" 단계를 바꾼다 — 단계 없이 한 번에(답 4). 앞 설계서 §13 결정 4 "넘겨주기는 2주 뒤 접속 기록을 본 다음"도 이 답으로 닫는다.

## 2. 지금 코드의 사실 (확인)

| # | 사실 | 근거 |
|---|---|---|
| 1 | 메뉴 '생산'은 첫 화면을 볼 수 있고 켜진 프리랜서가 아니면 첫 화면, 아니면 옛 보드 | `foms/services/production/nav_target.py:46-55` |
| 2 | 첫 화면을 보는 사람 = 관리자 + 팀 CS(회계 별칭) · SALES(MEASURE 별칭) · PRODUCTION · DRAWING · CONSTRUCTION · SHIPMENT, 협력사 제외 | `foms/services/production/home_access.py:23, 34-45`, `order_mutation_policy.py:60, 302-323` |
| 3 | 그래서 옛 보드로 가는 사람 = **켜진 프리랜서**(팀 SALES 라 볼 수는 있으나 nav_target 이 뺌) · **팀 없는 직원**(첫 화면 403) | 위 둘, 시험 `tests/domains/test_production_home.py:134-143` |
| 4 | 켜진 프리랜서 메뉴는 늘 옛 보드 | `foms/services/auth/freelancer_menu.py:25` |
| 5 | 프리랜서 문지기 허용 목록의 생산 묶음 = 옛 보드 · 옆 시트 · 공정 GET · 상세 묶음 · QR 라벨 · QR 그림 | `foms/services/auth/freelancer_screens/production.py:29-49` |
| 6 | 옛 보드 라우트 문지기는 `@login_required` 하나 | `foms/web/production/dashboard.py:114-116` |
| 7 | 생산 Blueprint 와 템플릿 전역 셋(`production_nav_href` · `production_work_user` · `PRODUCTION_FINISHED_STAGE`)이 **옛 보드 파일 안**에 있고, `home.py:86` · `part_thumb.py:32` · `__init__.py:3` 이 거기서 가져온다 | `dashboard.py:87-108` |
| 8 | 첫 화면은 '내 것만'을 안 읽는다(`False` 고정) | `home.py:329` → `production_home_read_model.py` `build_production_home`(`build_production_orders_query(db, user, '', '', False, ...)`), `home.py:360` 묘비도 `False` |
| 9 | 작업 시트 · 인쇄는 주문 번호로 바로 읽는다 — 주문 읽기 범위(`user_can_read_order`)를 안 본다 | `home.py:398-430`, `:432-454` |
| 10 | 프리랜서는 팀이 SALES 라 지금도 `can_ack_production_change` 가 True — [확인했어요]를 그린다 | `foms/services/production/write_access.py:66-86` |
| 11 | 프리랜서의 `part_view_mode` 는 `readonly`(볼 수 있는 팀이므로) — 태블릿에서 `?tab=parts` 도면 카드 판이 열린다 | `foms/services/production/part_access.py:104-124`, `home.py` `_PARTS_TAB_MODES` |
| 12 | 생산 쓰기 API 열 가지는 프리랜서 "내 주문 일 API" 목록에 있어 문지기를 지나고, 각 API 의 쓰기 판정(관리자 · 생산팀)이 403 을 낸다. **change-ack 만은 통과**한다(10번 때문) | `foms/services/auth/freelancer_order_rights.py:78-87`, `write_access.py:43-86` |

## 3. 프리랜서 '내 주문만' — 가장 조심할 곳

### 3-1. "내 주문"의 규칙 — 옛 보드와 같은 것을 쓴다 (확인)

옛 보드가 프리랜서에게 거르는 길은 이렇다.

1. 목록 '내 것만'이 프리랜서에게 늘 켜진다: `foms/services/common/erp_mine_filter.py:28` — `if force or current_user_is_list_freelancer(): return True`. 옛 보드는 `production_dashboard_filters.py:49` 에서 이것을 읽는다.
2. 그 값이 `build_production_orders_query` 에 들어가 `build_mine_sql_filter(user)` 를 붙인다: `foms/services/production_read_model.py:108-115`.
3. 프리랜서면 `build_mine_sql_filter` 가 연결 표 하나로 바뀐다: `foms/services/erp_permissions.py:317-318` → `foms/services/auth/freelancer_lists.py:61-70`
   > 조건은 하나다: `orders.id IN (SELECT order_id FROM order_freelancer_links WHERE user_id = 나)`.
4. 묘비(취소된 주문)는 파이썬 판정으로 거른다: `production_change_alerts.py:438-441` → `is_order_related_to_user` → 프리랜서 갈래 `erp_permissions.py:169-170` → `freelancer_order_related`(`freelancer_lists.py:97-100`, 같은 연결 표).
5. 주문 하나를 여는 길은 `user_can_read_order` 의 프리랜서 갈래: `order_mutation_policy.py:507-508` → `freelancer_orders.py:132` `freelancer_can_read_order` → `freelancer_can_access_order`(`:79-104`) = **연결 줄 또는 내가 만든 초안**(`:60-76`).
6. 문지기 겹 2: 허용 endpoint 의 URL · query 에 실린 주문 번호가 내 것이 아니면(없는 주문도) 404: `freelancer_scope.py:444-463` `freelancer_order_scope_denial`.

연결 표의 뜻(`freelancer_lists.py:1-17`): "켜진 프리랜서에게 '내 주문'은 `order_freelancer_links` 에 (주문, 나) 줄이 있는 주문**뿐**이다. 직원의 '내 담당' 판정(담당 이름 · 퀘스트 담당 이름 · 시공자 이름 · `sales_assignee_user_ids` · 도면 담당 id)은 프리랜서에게 쓰지 않는다. … 직접 만든 주문(초안 포함)은 연결 표의 `CREATOR` 줄이 덮는다." 담당에서 빠지면 훅이 줄을 지워 다음 요청부터 안 보인다.

**결정 F1** — 새 첫 화면도 이 규칙을 **그대로** 쓴다. 새 판정 함수를 만들지 않는다. 목록 = `build_mine_sql_filter`(연결 표), 주문 하나 = `user_can_read_order`, 주소의 번호 = 문지기 겹 2. 초안은 생산 단계에 없으므로 목록(연결 표만)과 주문 하나(연결 + 내 초안)의 차이는 생산 화면에서 생기지 않는다(추정 — 초안 상태 주문은 `PRODUCTION_HOME_STAGE_CODES` 밖).

### 3-2. 한 곳에서 거르기 — 읽기 모델 들머리

새 함수 하나: `production_home_mine_only(user) -> bool` = `is_list_freelancer(user)`(`foms/services/production_home_read_model.py` 에 둔다, 쿼리 0 — 요청 안에서는 설정을 한 번만 읽는다).

| 자리 | 지금 | 바꿈 |
|---|---|---|
| `build_production_home`(행 · `stats.total` · `past_hidden` 을 모두 여기서) | `build_production_orders_query(db, user, '', '', False, ...)` | `False` → `production_home_mine_only(user)` |
| `home.py:360` 묘비 | `collect_production_tombstones(db, user, False, partner_org)` | 같은 함수 값 |
| 작업 시트 · 인쇄(`home.py:398-454`) | 주문을 번호로 바로 읽음 | 새 도우미 `_home_order_or_404(db, order_id, user)`: 살아 있는 ERP 주문 + `user_can_read_order(user, order)` 아니면 **404** (없는 주문과 같은 답) |
| 도면 카드 작은 그림(`part_thumb.py:99-119`) | 이미 `user_can_read_order` → 403 | 403 → 404 로 맞춘다(존재를 알리지 않음, 다른 길과 같은 답) |

탭 넷 · 날 조각 · 판 조각 · 띠 숫자 · 탭 건수 · 찾기 · '바뀐 것' · PC 받은함은 모두 `build_production_home` 의 행과 묘비에서 파생된다(확인: `home.py:329-392`, `production_home_counts(rows, len(tombstones))`, `production_home_days(rows, ...)`, `production_home_changes_view(db, user, rows, tombstones)`). 그래서 들머리 두 곳만 바꾸면 숫자도 내 주문만 센다.

### 3-3. 읽기 길 전부 — 길마다 거르는 곳과 남의 주문 답

| # | 길 | 프리랜서 문지기 | 거르는 곳 | 남의 주문 번호를 넣으면 |
|---|---|---|---|---|
| 1 | `GET /erp/production/home` 날짜 탭(온전한 페이지) | 허용 추가 | 읽기 모델 들머리(§3-2) | — (번호 없음) |
| 2 | 같은 주소 `?tab=steps` 남은 공정 | 허용 | 들머리 | — |
| 3 | `?tab=changes`(+`done=all`) 바뀐 것 · 묘비 | 허용 | 들머리 + 묘비 | — |
| 4 | `?tab=all` 찾기(글자 찾기는 화면 안, 받아 온 줄만) | 허용 | 들머리 | — |
| 5 | `?tab=parts` 도면 카드 | 허용(탭은 날짜로 돌아감) | `part_view_mode` = `none`(§3-5) | — |
| 6 | 셸 조각 `view=fragment`(레일 · 아래 메뉴 · 하트비트) | 같은 endpoint | 같은 함수 | — |
| 7 | 날 조각 `?view=day&day=` | 같은 endpoint | 같은 행 | — |
| 8 | 판 조각 `?view=panel&step=&order=` | 같은 endpoint + query 검사 | 같은 행(`step_panel_for`) | 문지기 **404** |
| 9 | 주문 고르기 `?order=` · 옛 `?focus_order=` | query 검사 추가 | 같은 행 | 문지기 **404** |
| 10 | `GET /erp/production/sheet/<id>` 작업 시트 | 허용 추가 · URL 검사 | `_home_order_or_404` | 문지기 **404**(핸들러도 404) |
| 11 | `GET /erp/production/print/<id>` 인쇄 | 허용 추가 · URL 검사 | `_home_order_or_404` | **404** |
| 12 | `GET /erp/production/parts/thumb/<id>` 도면 카드 그림 | 허용하지 않음 | — | 문지기 403(허용 목록 밖, 화면 아님) |
| 13 | `GET /api/production/part-marks` 30초 받아 오기 | 허용하지 않음 | 핸들러도 `user_can_read_order(user, None)` 거짓 → 403(확인 `part_marks_read.py:149-150`) | 403 |
| 14 | `GET /api/production/part-sheet` PC 도면 창 | 허용하지 않음 | 핸들러 403(`part_sheet.py:86-87`) | 403 |
| 15 | `GET /api/production/part-history` 바뀐 기록 | 허용하지 않음 | 핸들러 403(`part_history.py:160-161`) | 403 |
| 16 | `GET /api/orders/<id>/production/steps` 공정 읽기 | 지운다(§6-3) | — | 404(길 없음) |
| 17 | `GET /api/files/view|thumb|download|presigned-urls/<key>` 도면 그림 | 지금 그대로 허용 | 핸들러 `_deny_file_access` → `user_can_read_order`(`files/routes.py:96`) | 지금 그대로 403/404 |
| 18 | 알림 종(`notifications.*`) | 지금 그대로 | 내 알림만 | — |
| 19 | `GET /erp/production/dashboard` | 허용 유지(넘겨주기, §5-2) | query `focus_order` 검사 그대로 | 문지기 404 |
| 20 | `GET /erp/production/tablet-sheet/<id>` | 허용 유지(넘겨주기) | URL 검사 그대로 | 문지기 404 |
| 21 | 숫자: 탭 건수 · 띠 숫자 · '전체 N건' · 지난 주문 숨김 수 · 공장 칩 · 아침 칩 | — | 1~4 의 행에서(아침 칩은 파트 계정만 — 프리랜서는 없음) | — |
| 22 | 메뉴 숫자(아래 메뉴 배지) | — | 이미 프리랜서 거름(`foms/services/dashboard_counts.py:70-74`) | — |

모두 22줄. 문지기 표 바꿈(`freelancer_screens/production.py`):
- `ALLOWED_ENDPOINTS` = `erp_production_home` · `erp_production_sheet_page` · `erp_production_print_sheet` · `erp_production_dashboard`(넘겨주기) · `erp_production_tablet_sheet`(넘겨주기). 뺌 = `api_production_steps_get`(길 지움) · `api_get_order_detail_payload` · `erp_order_label` · `orders.api_order_qr_svg`(옛 PC 상세 · 폰 QR 라벨만 쓰던 것 — 세 가지는 "내 주문 일 API" 목록 `freelancer_order_rights.py:42-44` 에도 있어 다른 화면의 내 주문에서는 그대로 열린다).
- `ORDER_VIEW_ARGS` = sheet · print · tablet_sheet → `order_id`.
- `ORDER_QUERY_ARGS` = home → `("order", "focus_order")`, dashboard → `("focus_order",)`.
- `METHOD_LIMITS` 는 화면 묶음 규칙대로 GET 만(없으면 더한다).

### 3-4. 쓰기 길 — 프리랜서에게 전부 거절

| 쓰기 | 지금 프리랜서 | 바꿈 |
|---|---|---|
| 생산 쓰기 여덟(start · complete · rework · cancel · uncomplete · steps POST · defect · hold) | 내 주문이면 문지기 통과 → API 쓰기 판정 403 | **"내 주문 일 API" 목록에서 뺀다** → 문지기에서 403(남의 주문은 404 그대로) |
| change-ack [확인했어요] | 내 주문이면 **통과(200)** | 목록에서 빼고 + `can_ack_production_change` 에 "켜진 프리랜서면 거짓" 한 줄(화면 단추 · 문지기 정책 `PRODUCTION_ACK` · 라우트가 같이 본다) |
| `api_set_logistics_status`(`/logistics`) | 내 주문 통과 → API 판정 | 생산 화면 밖이라 **그대로**(이 설계 범위 밖) |
| 공장 완료 `factory-done` · 도면 수정 요청 `drawing-request(/photo)` · 도면 표시 `part-marks` POST · `part-marks/basic` | 허용 목록 · 내 주문 목록 어디에도 없음 → 문지기 403 | 그대로 |

뺄 줄은 `freelancer_order_rights.py:78-87` 의 `erp_orders_production.api_production_*` 열 줄(steps_get 포함). 두 겹으로 막는다: ① 문지기 ② API 판정(쓰기는 이미 403, ack 는 새 한 줄). D27(프리랜서는 내 주문에서 회사 영업과 같게, 2026-11-07)과 부딪히는 곳이 change-ack 하나다 — §11 여쭐 것 1.

### 3-5. 프리랜서 화면 꼴 — 지금 "보기만 하는 팀" 꼴을 다시 쓴다

- 새 꼴을 만들지 않는다. `production_screen_flags`(`pc_view.py:61-96`)가 쓰기 팀이 아니면 이미 단추 없는 꼴을 낸다: PC(`foms_ptr=fine`)는 PC 보기 화면, 터치(폰 · 태블릿)는 `can_act=False` 읽기 꼴 — CS · 영업이 지금 보는 것과 같다.
- 더하는 것 셋:
  1. `can_ack` = 거짓(§3-4) → [확인했어요] · 바뀐 것 탭 확인 단추 없음.
  2. `part_view_mode(user)` 에 "켜진 프리랜서면 `none`" 한 줄(관리자 판정 앞) → 태블릿 도면 카드 판 · [도면 카드로 보기] · `?tab=parts` 모두 없음(탭은 날짜로, `home.py` `_resolve_home_tab`).
  3. 작업 시트의 [바뀐 기록 보기 ›](`sheet.html:113`, 도면 카드를 쓴 주문)는 `part-history`(프리랜서 403)를 부르므로 새 플래그 `parts_read`(= `part_view_mode != none`)일 때만 그린다.
- 하트비트(50초 미리 받기)는 쓰기 팀만(`production_work_user`) — 프리랜서는 지금처럼 안 돈다.

### 3-6. 시험 계획 — 새 `tests/security/test_freelancer_production_home.py`

준비(기존 `test_freelancer_screen_production.py` 의 `world` 틀을 옮긴다): 생산 단계 주문 셋 — 프리랜서 A 연결 주문(고객 "가짜고객가"), 프리랜서 B 연결 주문("가짜고객나"), 직원 주문("가짜고객다") + 취소 묘비 하나씩. 계정 = 켜진 프리랜서 A · 켜진 프리랜서 B · 회사 영업 직원(음성 대조군) · 꺼진 프리랜서.

1. **읽기 길 전수(라우트 표 래칫)**: `app.url_map` 에서 규칙이 `/erp/production/` · `/api/production/` 로 시작하거나 endpoint 가 `erp_orders_production.*` 인 GET 규칙을 모두 뽑아, 시험 안 표(§3-3 의 1~20)에 "허용+범위 / 거절 / 넘겨주기" 하나로 적혀 있는지 본다. 표에 없는 새 GET 길이 생기면 빨강 — 길 목록이 늘면 시험이 따라온다(`test_freelancer_order_scope.py:173-200` 분류 래칫과 같은 꼴). 음성 대조: 표에서 한 줄을 빼면 잡힌다.
2. **A 로 모든 허용 길을 돈다**(탭 다섯 × PC · 태블릿 · 폰 쿠키, 조각 셋, 시트 · 인쇄): 응답 글에 B 주문 · 직원 주문의 번호 · 고객 이름 · 전화 끝 네 자리 · 묘비 이름이 **한 글자도** 없다. 탭 건수 · 띠 숫자 · '전체 N건' · 바뀐 것 숫자 = A 주문으로 센 값.
3. **음성 대조군**: 회사 영업 직원은 같은 길에서 셋 다 보인다(거르기가 일을 하는 것을 보인다). 꺼진 프리랜서도 다 보인다.
4. **남의 번호**: A 가 `?order=` · `?focus_order=` · `?view=panel&order=` · `/sheet/<B·직원 id>` · `/print/<…>` · `/tablet-sheet/<…>` · 없는 번호 → 모두 404, 응답에 그 주문 글 없음.
5. **쓰기 전수**: 생산 쓰기 여덟 + change-ack 를 A 주문 · B 주문으로 POST → 403(내 것) · 404(남의 것), 주문 `mutation_version` · 이벤트 수 그대로.
6. **단추 0**: A 응답에 `data-tablet-sheet-action` · `data-foms-home-step-done` · `data-kanban-action="change-ack"` · `data-pp-` 판 표식 0.
7. **넘겨주기**: A 가 `/erp/production/dashboard?focus_order=<A 주문>` → 302 `?order=<A 주문>`.
8. **담당에서 빠지면** 다음 요청부터 그 주문이 첫 화면 · 시트에서 사라진다(연결 줄 지움 훅).
9. 쿼리 수: A 의 날짜 탭이 직원 날짜 탭 쿼리 수 + 1 이하(연결 표 하위 질의 하나, 추정).

## 4. 팀 없는 직원 계정 — 보기만

- 지금: `can_view_production_home` = 관리자이거나 보는 팀(§2-2). 팀 없음 → 거짓 → 첫 화면 403, 메뉴는 옛 보드.
- 바꿈(`home_access.py:34-45`): 협력사가 아니고 **팀 값이 비었으면**(`None` · 빈 글) 참을 더한다. 사장님 답 글자 그대로 "팀 없는" 계정만 — 목록 밖 다른 팀 글자(있다면)는 넓히지 않는다(§10 운영 확인에서 센다).
- 쓰기는 그대로 거절(확인): `can_write_production` 은 관리자 · 생산 능력 팀만(`write_access.py:43-63`) → 팀 없음 거짓. 화면은 `can_act=False`.
- [확인했어요]: `can_ack_production_change` 가 지금 `can_view_production_home` 을 그대로 쓰므로(`:84-86`) 그대로 두면 팀 없는 계정에 단추가 생긴다 → "보는 팀(관리자 · `PRODUCTION_HOME_TEAMS`)일 때만"으로 바꾼다(지금 사람들의 답은 같다). 사장님 "단추 없음".
- 도면 카드 판: `part_view_mode` 가 팀 없는 계정에 `readonly` 를 준다(볼 수 있게 되므로). 읽기 전용 판은 보기라 그대로 둔다 — CS · 영업과 같은 꼴(추정: 사장님 "보기만"에 든다).
- 같이 열리는 것: 도면 카드 읽기 API 셋(`part-marks` · `part-sheet` · `part-history` GET)과 작은 그림이 `can_view_production_home` 을 보므로 팀 없는 계정에 열린다(보기만, 쓰기 POST 는 따로 막힘).
- 메뉴: `production_nav_href` 가 첫 화면을 준다(§5-1) — 폰 셸 `else` 갈래(`erp_mobile_shell.html:60-62`)에 생산이 있고, 레일도 같다.
- 깨지는 시험(고침): `test_production_home.py:134-143`(팀 없음 403 → 200 + 단추 0), `test_production_multi_parts.py:151`(팀 없음 `none` → `readonly`), `test_production_part_board.py:173`(판 None → 읽기 판), `test_production_part_handover.py:338`(바뀐 기록 403 → 200). 그대로 두는 시험: `test_production_change_ack_api.py:115-117`(팀 없음 ack 403 — 새 규칙과 같다).

## 5. 길 바꾸기 · 넘겨주기

### 5-1. 길 (확인한 자리)

| 자리 | 지금 | 바꿈 |
|---|---|---|
| `foms/services/production/nav_target.py:46-72` | 볼 수 있고 프리랜서 아님 → 첫 화면, 아니면 보드 | 늘 첫 화면(`?order=`). 보드 상수 · 갈래 · `production_home_open_for` 지움(부르는 곳 정리) |
| `foms/services/auth/freelancer_menu.py:25` | `erp_production_dashboard` | `erp_production_page.erp_production_home` |
| `foms/services/erp_order_deeplink.py:43, 62-63, 117-121` | 못 보면 보드 | 보드 갈래 지움. 돌아가기 열쇠 `"erp_production_dashboard"` 는 옛 링크용으로 남기고 첫 화면으로 |
| `foms/services/orders/board_state_display.py:85` | `production_order_link` | 바꿀 것 없음(nav_target 을 따라감) |
| PC [보드 →] `templates/production/partials/home_pc_board_link.html` · `home_body.html:24` include · `static/css/contexts/production/pc.css:45-46` | 있음 | 지움(pc.css 핀 · 묶음 핀 함께 올림) |
| `static/js/runtime/erp-shell.js:67` `LEGACY_SWAP_PATHS` | 보드 | 빈 목록(또는 줄 통째 지움 — 쓰는 곳 정리) |
| `foms/services/common/partner_order_filter.py:18` · `static/js/foms/partner-order-filter.js:8` | 보드 주소 포함 | 보드 주소 뺌(둘 같이) |
| `foms/services/foms_split_view.py:188` · `erp_sub_nav.html:40` · `erp_mobile_shell.html:38` | `production_nav_href` | 바꿀 것 없음 |
| 시공팀 화면 이동 제한 `foms/platform/http.py:305-318` | 옛 보드 → 출고 302 | 그대로(옛 주소로 오는 시공팀은 지금처럼 출고로) |

### 5-2. 넘겨주기(302) — 옛 주소는 지우지 않는다

| 옛 주소 | 넘겨줄 곳 | 이어 주는 인자 |
|---|---|---|
| `/erp/production/dashboard` | `/erp/production/home` | `focus_order` → `order`, `partner_org`(있으면). `q` · `stage` · `mine` · `page` · `sort` 는 버린다(첫 화면이 안 읽음) |
| `/erp/production/tablet-sheet/<id>` | `/erp/production/sheet/<id>` | 없음 |

- 둘 다 `@login_required` 뒤 바로 302(읽기 없음). 받는 쪽 문지기가 권한을 본다(협력사는 앞 문지기, 프리랜서는 §3-3).
- 302 는 셸 조각 요청(`view=fragment`)도 같은 302 — `LEGACY_SWAP_PATHS` 에서 빠지므로 셸이 조각으로 부르지 않는다(추정: 옛 링크를 누르면 온전한 페이지 이동).
- 라우트 둘은 새 모듈 `foms/web/production/legacy_redirects.py`(약 40줄)에 둔다. endpoint 이름은 그대로(`erp_production_dashboard` · `erp_production_tablet_sheet`) — 옛 `url_for` · 즐겨찾기 · 알림 글이 안 깨진다.
- 사장님 답 4 "한 번에"는 올리는 때를 말한 것이고, 넘겨주기 라우트를 남기는 것은 설계자 판단이다 — §11 여쭐 것 2.

## 6. 지우는 것 · 옮기는 것

### 6-1. 지움 — 옛 보드 전용 (확인: 새 화면 · 다른 화면이 include · import 하지 않음)

| 파일 | 줄 |
|---|---|
| `templates/production/dashboard.html` | 8 |
| `templates/production/partials/dashboard_fragment.html` | 5 |
| `templates/production/partials/dashboard_body.html` | 171 |
| `templates/production/partials/filters.html` | 64 |
| `templates/production/partials/filters_grid.html` | 245 |
| `templates/production/partials/mobile_filters.html` | 84 |
| `templates/production/partials/mobile_queue.html` | 120 |
| `templates/production/partials/modals.html` | 23 |
| `templates/production/partials/admin_override_sheet.html` | 10 |
| `templates/production/partials/production_steps_sheet.html` | 37 |
| `templates/production/partials/scripts.html` | 1,203 |
| `templates/production/partials/styles.html` | 1,357 |
| `templates/production/partials/tablet_kanban_body.html` | 423 |
| `templates/production/partials/tablet_sheet.html` | 292 |
| **템플릿 14개 소계** | **4,042** |
| `static/js/production/foms-production-steps.js` | 354 |
| `static/js/foms/tablet-production-kanban.js` + `templates/partials/shared/layout_scripts.html:111` 태그 | 199 |
| `static/css/components/foms-production-steps.css` | 310 |
| `foms/services/production_dashboard_filters.py` | 69 |
| `foms/services/production_fragment_version.py`(옛 보드 렌더 전 304 키) | 226 |
| `foms/web/production/dashboard.py`(두 라우트 · `_compute_tablet_prod_kpis` · import 묶음) | 376 → 0(남는 것은 §6-2 로 옮김) |
| `tests/support/production_prerender_board.py` | 299 |

전용 읽기 모델 함수(정의 파일 밖 호출처가 `dashboard.py` · `production_fragment_version.py` 뿐 — 확인): `production_read_model.py` 의 `compute_production_summary_blob` · `paginate_production_rows` · `production_attachment_slice_key` · `production_attachment_slice_value` · `production_summary_slice_key`(+ `PRODUCTION_DASHBOARD_PAGE_SIZE`), `production_dashboard_display.py` 의 `build_production_enriched_rows` · `build_production_process_steps`. 지우기 전 `tests/` 호출처를 한 번 더 grep(시험이 직접 부르면 그 시험도 정리). `build_production_orders_query` 의 `f_stage` · `f_q` 갈래는 옛 보드만 쓰지만 함수가 공용이라 **남긴다**(지우면 서명이 바뀌어 일이 커진다 — 하지 않는 것 §13). `dashboard_cache.py` 의 생산 요약 조각 무효화 줄은 쓰는 곳이 없어지면 함께 정리(추정, 구현 때 확인).

### 6-2. 옮김 — 옛 보드 파일 안에 있는 공용 코드

| 무엇 | 지금 | 새 자리 |
|---|---|---|
| `erp_production_page_bp = Blueprint('erp_production_page', ..., url_prefix='/erp')` | `dashboard.py:87-89` | 새 `foms/web/production/blueprint.py`(약 40줄) |
| 템플릿 전역 `production_nav_href` · `production_work_user` · `PRODUCTION_FINISHED_STAGE` | `dashboard.py:92-108` | 같은 `blueprint.py` |
| `foms/web/production/__init__.py:3` | `from ...dashboard import` | `from ...blueprint import` + `import ...legacy_redirects` |
| `home.py:86` · `part_thumb.py:32` | `from foms.web.production.dashboard import erp_production_page_bp` | `from foms.web.production.blueprint import ...` |

`home.py` 는 454줄이라 500줄 래칫 바로 밑 — 이 설계는 `home.py` 에 `_home_order_or_404` 하나(약 10줄)만 더한다.

### 6-3. `GET /api/orders/<id>/production/steps` 지움

- 부르는 곳(확인): 옛 폰 공정 창 `foms-production-steps.js:181`(지움) · `foms-production-sheet-parts.js:39-49` 의 `load()` — 주석 "옆 시트는 자료가 안 실려 있다 — 칸을 켤 때만 공정 API GET 한 번". 전체 화면 시트 · 남은 공정 판은 `data-foms-sheet-parts` 로 자료를 싣는다(`sheet.html:99`, `home_step_panel.html`). 옆 시트가 없어지면 GET 은 쓰는 화면이 없다.
- 지움: 라우트 `foms/api/production/orders.py:1095-1137`, `sheet-parts.js` 의 GET 갈래(자료 없으면 `null` — 단추 없는 꼴), 프리랜서 허용 목록 · 내 주문 목록 줄. POST(공정 쓰기)는 남는다.
- 확신 낮음: 저장소 밖 호출자(앱 · 스크립트)가 이 GET 을 쓰는지는 모른다 — 운영 접속 기록으로 본다(§10).

### 6-4. 가르는 것 — 공용 파일 안의 옛 부분

| 파일 | 줄 | 지우는 부분 | 남기는 부분 |
|---|---|---|---|
| `static/js/foms/tablet-domain-sheets.js` | 907 | 칸반 필터 · 숫자 타일 · 전체 화면(약 589-721) · 변경 브리핑 창 · 칸반 카드 정리 · 조용한 배지(약 413-536 중 첫 화면이 안 쓰는 것) · 그 click 갈래 | 생산 쓰기 단추 · 보류 · 사유 창 · change-ack(첫 화면 받은함 줄 지우기 포함) · 출고 서랍 저장(`:537`, 출고 `shipment-entry.js:25` 가 실음) — 줄 번호는 추정, 함수 단위로 가른다. 핀은 `home_body.html:53` · `sheet.html:222` · `shipment-entry.js:25` 셋을 같이 올린다 |
| `static/css/foundation/foms-tablet-production-kanban.css` | 1,433 | `.foms-kanban*` · `.tablet-prod-*` · `.foms-production-legacy-queue` · 옆 시트 `.foms-prod-sheet__*`(옆 시트 전용이면) | 창 꼴 `.foms-prod-change-modal*`(26곳 — 새 도면 카드 확인 창이 그대로 씀, `home_parts_overlays.html:3` · `parts.css:5, 257`). 지우기 전에 남길 클래스를 첫 화면 · 시트 · 판 템플릿에서 전수 grep. 묶음 `foms-tablet-bundle.css:11` 의 `@import` 핀과 부모 묶음 `<link>` 핀을 같이 올린다 |
| `static/js/foms/tablet-side-sheet.js` | 479 | 위임 셀렉터의 `.foms-kanban-card[data-order-id]`(`:79`) | 나머지(모든 태블릿 화면) |
| `static/js/production/foms-production-sheet-parts.js` | 266 | GET 갈래(§6-3) | 나머지 |
| `foms/services/production/nav_target.py` | 84 | 보드 갈래 · 상수 | 첫 화면 주소 · `PRODUCTION_CHANGES_HREF` |
| `foms/services/auth/freelancer_screens/production.py` | 49 | §3-3 표대로 다시 씀 | — |

### 6-5. 기준선 · 부하 · 기록

- `tests/harness/file_size_baseline.json:245`(`foms-production-steps.js`) 줄 지움.
- `tests/contracts/runtime/layer_dependency_baseline.json:471`(`dashboard.py` → `erp_mobile_order_display`) 줄 지움.
- 부하 스크립트 `tests/harness/load/foms_150_realistic.js:53` · `foms_200_users.js:15` → `/erp/production/home` 로.
- 기록 json(`final_soak_summary.json` · `last_trace_summary.json`) · `docs/harness/evidence/*` 는 지난 기록이라 손대지 않는다.
- 성능 게이트(`tools/perf/staging_perf_gate.py` · `perf_budgets.json`)는 이미 첫 화면만 잰다 — 바꿀 것 없음(주석 두 곳만 남음).
- 쓰기 길 목록 `docs/harness/foms_order_mutation_policy_manifest.json`: 지우는 쓰기 라우트 없음 — 그대로.
- 구조 인벤토리: 구현 끝에 `python tools/harness/refresh_inventories.py` 를 돌리고 바뀐 것을 같은 커밋에(줄 번호만 밀린 인벤토리가 CI 를 깨는 함정).

## 7. 시험 지도

### 7-1. 지움(옛 보드 자체)
`tests/domains/test_production_dashboard_mobile.py` · `test_production_dashboard_date_column_sort.py` · `test_production_dashboard_query_count.py` · `test_production_kanban_full_window.py` · `test_production_prerender_key_contract.py` · `test_production_prerender_shadow.py` · `test_brain_polish_f_prerender_key.py` · `test_production_old_board_buttons.py` · `tests/postgres/test_production_prerender_key_pg.py` · `tests/support/production_prerender_board.py`.

### 7-2. 고침 — 옛 보드 부분만 빼고 나머지 계약은 남김
- 태블릿 계약: `test_tablet_t2_contract.py` · `test_tablet_shell_t0_contract.py` · `test_tablet_dashboard_sheet_contract.py` · `test_tablet_domain_sheets_contract.py`(공용 단추 · change-ack 계약은 남김) · `test_production_side_sheet_p2.py`(레일 화면 크기 단추 · 실패 문구는 첫 화면으로).
- 화면 조각 계약이 옛 템플릿 글을 읽는 것: `test_confirm_to_production_board.py`(읽기 모델 버킷만 남김) · `test_mobile_production_construction_actions.py`(시공만) · `test_board_grid_empty_row.py`(시공만) · `test_dashboard_cap_disclosure.py` · `test_admin_override_ui.py`(작업 시트 쪽) · `test_production_drawing_revision_badge.py` · `test_production_complete_inspect_screens.py` · `test_completion_confirm_hint_surfaces.py` · `test_production_sheet_app_confirm_1127.py` · `test_production_flow_1126_g3.py` · `test_production_wording_1126.py`(`foms-production-steps.js` · `production_steps_sheet.html` 글 고정 줄) · `test_production_home_fixes.py:318-321` · `test_err_ux.py` · `test_erp_order_shared_form_scripts.py` · `test_order_items_master_detail_contract.py` · `test_list_thumb_screens.py` · `test_list_thumb_more_slots.py` · `test_mid_thumb_screens.py` · `test_attachment_list_include_superseded.py` · `test_attachment_superseded_page_scope.py` · `test_tablet_landscape_surfaces.py` · `test_phone_viewport_surfaces.py` · `test_mobile_width_surfaces.py` · `test_tablet_touch_targets_zoom.py` · `test_production_selfclaim_css.py` · `test_production_change_alerts.py`(서비스 계약은 남김) · `test_production_transition_guard_api.py` · `test_production_part_steps_sync.py` · `test_pc_board_state_grid.py` · `test_mobile_quest_names.py` · `test_notification_badge_dedup.py` · `test_contract_company_label.py` · `test_review_followup_1108.py` · `test_shipment_change_alerts.py` · `test_shell_v3_removed.py` · `test_b7_sync_badge.py` · `test_unified_search_params.py`(`filters.html`).
- 구조 · 성능: `contracts/test_shell_fragment_script_parity.py` · `contracts/runtime/foms_namespace_surface_tests.py:1291, 1649-1717, 1907`(옛 `dashboard` 모듈 재수출 고정 → `blueprint` 모듈 또는 줄 지움) · `test_erp_permissions.py:605, 619-632`(생산 mine 검사 원본을 `production_home_read_model.py` 로) · `performance/test_page_local_defer_contract.py` · `test_entry_chain_parallel_contract.py` · `test_template_warm.py` · `test_staging_perf_gate.py`(주석만) · `visual/test_p1_mockup_structure.py:467, 522-584, 933, 953` · `visual/test_mobile_v2_surface_containment.py` · `visual/test_p1_mobile_ux_smoke.py`.
- 길 · 메뉴(§5): `test_production_view_nav.py:130-146` · `test_production_pc_viewer.py:360` · `test_production_home_day_pick.py:241-259` · `test_erp_shell_fragment_contract.py:196, 224` · `test_tablet_rail_contract.py:203, 257` · `test_freelancer_menus.py:271`(프리랜서 메뉴 생산 = 첫 화면, "다른 사용자 출력 한 글자도 같음" 계약 유지) · `test_search_focus_landing.py` · `test_partner_filter_all_tabs.py` · `test_erp_mine_filter.py:11` · `test_production_home.py:141`(시공팀 옛 주소 302 → 출고 그대로) · `test_production_team_p1.py:105`.
- 팀 없는 계정(§4): `test_production_home.py:142-143` · `test_production_multi_parts.py:151` · `test_production_part_board.py:173` · `test_production_part_handover.py:338`.
- 프리랜서: `tests/security/test_freelancer_screen_production.py` — 옛 보드 시험(`:155-235`, 숫자판 캐시 `:265-300`)을 지우고 새 파일로 옮김. `:245-250`(쓰기가 직원 규칙을 따른다)은 **뜻이 바뀐다** → "문지기 403". `test_freelancer_gate.py`(허용 이름이 진짜 endpoint) · `test_freelancer_order_scope.py`(분류 래칫) · `test_freelancer_own_order_rights.py:123-142`(목록 전수)는 표를 바꾸면 저절로 따라오는지 돌려 본다.

### 7-3. 새 시험
- `tests/security/test_freelancer_production_home.py` — §3-6 아홉 가지.
- `tests/domains/test_production_legacy_redirects.py` — 옛 주소 둘 302 · 인자 이어 주기(`focus_order`→`order`, `partner_org`) · 버리는 인자 · 로그인 없음 → 로그인 화면 · 협력사 → 협력사 첫 화면 · 시공팀 → 출고(그대로).
- `tests/domains/test_production_teamless_view.py` — 팀 없는 직원: 첫 화면 탭 다섯 · 시트 · 인쇄 200, 쓰기 여덟 403, change-ack 403, 응답에 쓰기 · 확인 표식 0, 메뉴 '생산' = 첫 화면. 음성 대조: 협력사 403 · 팀 있는 CS 는 [확인했어요] 있음.
- 지움 확인 한 줄: 옛 템플릿 14개 · JS · CSS 파일이 없고, `templates` · `static` · `foms` 어디에도 그 이름이 없다(되살아남 막기).

## 8. 일 나누기 — 일꾼 넷

| 조각 | 맡을 파일(이 조각만 고친다) | 끝 확인 | 기대는 것 |
|---|---|---|---|
| **① 프리랜서 범위** | `foms/services/production_home_read_model.py` · `foms/web/production/home.py`(묘비 인자 · `_home_order_or_404` · 플래그 전달) · `foms/web/production/part_thumb.py`(403→404) · `foms/services/production/pc_view.py`(`parts_read`) · `foms/services/production/part_access.py`(프리랜서 `none`) · `foms/services/auth/freelancer_screens/production.py` · `foms/services/auth/freelancer_order_rights.py` · `templates/production/sheet.html:113` · 새 `tests/security/test_freelancer_production_home.py` · `tests/security/test_freelancer_screen_production.py` | `python -m pytest tests/security/test_freelancer_production_home.py tests/security/test_freelancer_screen_production.py tests/security/test_freelancer_gate.py tests/security/test_freelancer_order_scope.py tests/security/test_freelancer_own_order_rights.py -q` · `python -c "import app; print('APP_OK')"` | ack 시험 한 줄은 ② 의 `write_access.py` 를 기다린다(그 전엔 xfail 없이 ② 와 같은 가지에서 합침) |
| **② 팀 없는 계정 + 확인 규칙** | `foms/services/production/home_access.py` · `foms/services/production/write_access.py`(팀 없음 · 켜진 프리랜서 ack 거짓) · 새 `tests/domains/test_production_teamless_view.py` · `test_production_home.py` · `test_production_write_access.py` · `test_production_multi_parts.py` · `test_production_part_board.py` · `test_production_part_handover.py` | `python -m pytest tests/domains/test_production_teamless_view.py tests/domains/test_production_home.py tests/domains/test_production_write_access.py tests/domains/test_production_change_ack_api.py tests/domains/test_production_multi_parts.py tests/domains/test_production_part_board.py tests/domains/test_production_part_handover.py -q` | 없음 |
| **③ 길 바꾸기 · 넘겨주기** | `foms/services/production/nav_target.py` · `foms/services/auth/freelancer_menu.py` · `foms/services/erp_order_deeplink.py` · `foms/web/production/dashboard.py`(두 라우트 몸을 302 로 — 옛 몸 지움) · `templates/production/partials/home_body.html` · `home_pc_board_link.html`(지움) · `static/css/contexts/production/pc.css` + 핀 · `static/js/runtime/erp-shell.js` · `foms/services/common/partner_order_filter.py` · `static/js/foms/partner-order-filter.js` · §7-2 "길 · 메뉴" 시험 · 새 `tests/domains/test_production_legacy_redirects.py` | 위 시험 파일들 `-q` · `node --check static/js/runtime/erp-shell.js static/js/foms/partner-order-filter.js` · APP_OK | 프리랜서 메뉴가 허용 목록으로 걸러지므로(`freelancer_menu.py` `freelancer_menu_items`) ① 의 허용 목록이 먼저 있어야 `test_freelancer_menus.py` 가 초록 |
| **④ 지우기 · 옮기기 · 시험 정리** | §6-1 · §6-2 · §6-3 · §6-4 · §6-5 전부 · §7-1 · §7-2 나머지 | 바뀐 파일에 닿는 시험 `-q` · `node --check` 고친 JS 전부 · `python tools/harness/refresh_inventories.py` · APP_OK | ①②③ 이 합쳐진 뒤 시작(`home.py` · `dashboard.py` · `tablet-domain-sheets.js` 가 겹침) |

- ①②③ 은 동시에 한다(파일이 겹치지 않는다 — 단 ① ↔ ② 는 ack 한 줄, ③ → ① 은 메뉴 허용 목록에 순서가 있다). 각 조각은 자기 워크트리(`python tools/harness/session_worktree.py create`)에서, 끝나면 총괄이 한 가지에 차례로(① → ② → ③) 합친다. ④ 는 그 가지 위에서.
- 마지막에 한 번만 `scripts/ops/pre_push_smoke.ps1`(전체 시험 · 성능 가드) → deploy → 스테이징 확인 → production 승격(사장님 답 4 "한 번에").

## 9. 되돌리는 법

- DB 바꿈 없음(마이그레이션 0). 되돌리기 = 합친 커밋 묶음 revert 한 번 — 템플릿 · JS · CSS · 라우트가 함께 돌아온다.
- 반만 되돌리기가 필요하면(예: 프리랜서 거르기에 문제): ①② 의 커밋만 되돌리면 안 된다 — ③ 이 프리랜서 메뉴를 첫 화면으로 옮겼으므로 **묶음 전체**를 되돌린다. 그래서 묶음은 하나의 PR 로 올린다.
- 정적 파일 핀을 올리므로 되돌릴 때도 핀이 옛 값으로 돌아간다(브라우저 캐시 1일 — 되돌린 뒤 하루 안에 옛 JS 가 섞일 수 있다, 추정).

## 10. 운영에 올리기 전 확인 (총괄이 한다 — 운영 읽기 전용, 모음 값만)

1. 켜진 프리랜서 수(판매 수수료 설정 `active`) · 그 사람들의 연결 표 생산 단계 주문 수(합계만).
2. 팀 없는 활성 직원 계정 수(역할별 합계만).
3. 팀 값이 `PRODUCTION_HOME_TEAMS` · 별칭 · 빈 값 어디에도 안 드는 활성 계정 수 — 0 이 아니면 그 사람들은 이 설계 뒤에도 첫 화면 403 · 메뉴 첫 화면(= 403)이 된다 → 올리기 전에 사장님께 따로 여쭌다.
4. 지난 14일 운영 접속 기록의 `/erp/production/dashboard` · `/erp/production/tablet-sheet/` · `GET /api/orders/*/production/steps` 요청 수(계정 종류별 합계) — 넘겨주기 · API 지움의 영향 크기.
5. 스테이징에서 프리랜서 시험 계정 A(가짜 주문 `CLAUDE-TEST-` 둘 연결)로 §3-3 1~11 을 실화면으로 연다 — 남의 주문 0, 숫자 = 내 주문 수. 대조군 `claude_master` 는 전부 보임.

## 11. 사장님께 여쭐 것 (남은 것만)

1. **프리랜서의 [확인했어요]** — 회사 영업 직원은 생산 화면에서 바뀐 것을 보고 [확인했어요]를 누를 수 있어요. 이건 주문을 고치는 게 아니라 "나 봤어요" 표시예요. 지난번(11-07)에 "프리랜서도 자기 주문은 회사 영업과 똑같이"라고 하셨는데, 이번 답은 "보기만, 단추 없음"이에요. 예: 프리랜서 김○○의 주문 시공일이 바뀌면, 김○○ 화면에 [확인했어요] 단추를 **안 보이게** 할까요(이 설계), 아니면 회사 영업처럼 **보이게** 할까요?
2. **옛 주소 넘겨주기** — 누가 예전에 저장해 둔 옛 생산 보드 주소(즐겨찾기 · 옛 알림 · 옛 검색 링크)를 누르면, 지우고 나서는 "없는 화면"이 떠요. 이 설계는 그 주소로 오면 **새 생산 화면으로 바로 보내 주는 길만 남겨요**(화면 코드는 다 지움). 예: 옛 링크 `…/production/dashboard?focus_order=123` → 새 화면에서 123번 주문이 고른 채로 열림. 이 길을 남길까요, 아니면 이것도 지울까요?
3. **팀 없는 계정의 도면 카드 보기** — 팀이 없는 직원이 태블릿으로 새 생산 화면을 열면, CS · 영업처럼 도면 카드 판도 **보기만** 할 수 있게 돼요(누르는 단추는 없어요). 이것도 괜찮을까요?

프리랜서가 보는 '내 주문'의 범위는 **옛 보드 규칙 그대로**(담당으로 연결된 주문 + 자기가 만든 주문 — 담당에서 빠지면 다음 화면부터 안 보임)라 여쭐 것 없음.

## 12. 위험 · 막는 법

| 위험 | 막는 법 |
|---|---|
| 프리랜서에게 남의 주문 · 건수가 샌다 | 들머리 두 곳 한 함수(§3-2) + 문지기 번호 검사 + 주문 하나 404 + 라우트 표 래칫 · 이름 한 글자 시험 · 음성 대조군(§3-6) |
| 새 생산 GET 길이 나중에 생겨 프리랜서 거르기를 건너뛴다 | 프리랜서 문지기는 기본 거부(허용 목록 밖 = 403) + §3-6-1 래칫이 표에 없는 길을 빨강으로 |
| Blueprint 를 옮기다 첫 화면 라우트가 안 붙는다 | `__init__.py` import 순서 · APP_OK · 라우트 수 전 · 후 비교(`app.url_map` 에서 `erp_production_page.*` 6개 — home · sheet · print · thumb · 넘겨주기 둘) |
| 공용 JS · CSS 를 가르다 출고 · 첫 화면 단추가 죽는다 | 함수 단위로 가르고 출고 서랍 저장 · change-ack · 보류 시험 유지, 핀 셋 같이 올림, 스테이징 실화면(출고 태블릿 서랍 · 첫 화면 [확인했어요] · 시트 [보류]) |
| 팀 없는 계정에 [확인했어요]가 생긴다 | `can_ack_production_change` 를 보는 팀 목록으로(§4) + 시험 |
| 지운 이름이 템플릿 · 시험에 남아 CI 만 깨진다 | §7-3 지움 확인 시험 · `refresh_inventories` · 전체 시험은 smoke 한 번 |
| 옛 GET 공정 API 를 저장소 밖에서 쓰고 있었다 | §10-4 접속 기록으로 먼저 본다 — 있으면 지우지 않고 남긴다 |

## 13. 하지 않는 것

- 옛 화면에만 있던 기능 옮기기(QR 라벨 · 경보 숫자 · 연락처/주소/실측일/첨부 칸 · 거르기 줄 · 주문 생성) — 사장님 답 3 "필요없어".
- `build_production_orders_query` 서명 바꾸기(`f_stage` · `f_q` 갈래는 남김) · 읽기 모델 큰 정리.
- 시공팀이 옛 주소로 왔을 때 첫 화면으로 보내기(지금처럼 출고).
- 프리랜서의 다른 화면(출고 · 시공 · 완료 등) 범위 바꾸기 · `api_set_logistics_status` 정리.
- 팀 목록 밖 다른 팀 글자를 가진 계정 넓히기(§10-3 에서 세어 보고 따로).
