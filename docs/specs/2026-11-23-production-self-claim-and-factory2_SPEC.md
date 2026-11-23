# 생산 파트 화면 '알아서 맡기' 고침 · 계정 여러 파트 · 2공장 — 설계서 (1판)

> 작성일 2026-11-23 | 상태 **승인대기** | 등급: **코어 변경**(완료 규칙 · 생산 쓰기 권한 · 계정 칸 · 도면 자료 · 마이그레이션 2 — 설계 → 승인 → 구현)
> 계기: 사장님 2026-11-23 — ① "파트별로 알아서 자기 일을 맡는 방식"(일 나누기의 답) ② "2공장도 있어 — 도면팀에서 도면에 따라 2공장 것은 따로 분류해 주는데, 1개 주문에 2공장 · 1공장이 섞여 있을 수 있어" ③ 파트 화면 점검 뒤 질문 창 답 네 묶음(2공장 뼈대 넷 · 2공장 둘째 묶음 · 파트 점검 첫 묶음 · 둘째 묶음) ④ 손으로 켠 공정 칸 답("작업 시트에서 재단 체크가 켜진 집은 도면 카드도 '재단 끝'으로").
> 목업 `docs/design/mockups/production-self-claim-factory2-v2.html`(화면 2판, 이 설계서와 같은 커밋) · 흐름 목업 `docs/design/mockups/production-factory2-process.html`(1판, 답을 초록 번호로 고침). 원장 `docs/plans/2026-11-09-tablet-production-ui-ledger.md`(11-23 줄들 — 세션 가지 `session/tablet-prod-ui` 90e6ada1e 에 있고 deploy 에는 아직 없다). 앞 설계서 `2026-11-09-tablet-production-ui_SPEC.md` §15(파트 카드) · `2026-11-21-production-pc-viewer_SPEC.md` · `2026-11-22-production-drawing-arrival-upgrade_SPEC.md`.
> 점검 증거: 파트 화면 '알아서 맡기' 점검(로컬 가짜 주문 26건 · 계정 11, 결과 `scratchpad/part_audit/result.json` · 그림 12장) — 이 설계서의 B1 · B2 · B3 · W1 ~ W12 번호는 그 점검의 번호다.
> 기준 코드 origin/deploy `1cb1c76f8`. 아래 파일:줄은 모두 이 커밋에서 확인했다. 이름 · 번호 예시는 지어낸 값이다.

## 0. 한 줄

지금 파트 화면(도면 카드 골라 맡기)을 그대로 두고 **막힌 곳 · 헷갈리는 곳만** 고친다 — 파트 일이 남으면 [제작 완료]를 막고 마지막 카드에서 "제작 완료할까요?"를 묻는다, 맡기 풀기 · 넘겨받기, '어제 맡음', 보류 · 도면 고치는 중 막기, 손으로 켠 공정 칸 = 카드 끝, 첫 맡기 = 제작 시작, 날짜 탭 줄에 맡은 사람. 그다음 **계정 하나에 파트 여럿** · 파트 없는 생산팀은 아무 파트나 대신. 마지막으로 **2공장**: 도면 한 장마다 만드는 공장을 도면팀이 정하고(나중에도 바꿈), 두 공장이 같은 화면을 쓰되 남의 공장 카드는 흐리게 보기만, 주문 단위(단계 · 마감 · 공정 4칸 · 제작 완료)는 그대로 하나. 기존 주문 표시 `flags.factory2`("라홈시스템(2공장)")는 계약 회사 표시라 따로 두고 이름에서 '2공장'을 뺀다.

## 1. 누가 · 왜 · 흐름

- **파트 사람**(재단 · 엣지 · 조립 · 검수, 태블릿 가로 1176 × 626 · 화면 크기 80%): 아침에 태블릿을 켜고 그날 도면 카드에서 자기 할 장을 **스스로** 맡는다(반장이 나눠 주지 않는다). 끝나면 [끝]. 잘못 맡았으면 풀고, 쉬는 동료 장은 넘겨받는다.
- **파트 없는 생산팀 계정 · 관리자**: 공장 전체를 본다. 빠진 사람 대신 카드를 누르고, 공정 칸을 손으로 켜기도 한다.
- **도면팀**: 도면 장마다 1공장 · 2공장을 정한다. 1공장이 넘칠 때 몇 장을 2공장으로 돌린다. 생산에 내려간 뒤에도 바꾼다.
- **PC 사람**(관리자 · 다른 부서): 보기만. 누가 무엇을 맡았는지 한눈에.
- 흐름(한 주문): 도면 내려옴(생산 단계) → 파트 사람이 첫 카드를 맡음 = **제작 시작** → 장마다 네 파트가 알아서 맡고 끝냄(순서 안 막음, D46) → 마지막 카드 끝 = "제작 완료할까요?" → 시공 대기. 2공장 장이 섞이면 2공장 사람들이 그 장만 같은 방식으로 하고, 물건은 1공장에 모여 함께 나간다.

### 1-1. 사장님 결정(2026-11-23, 고정 — 다시 묻지 않는다)

| # | 결정 | 출처(원장 11-23 줄) |
|---|---|---|
| A | 일 나누기 = 파트별로 알아서 맡기. 반장이 나눠 주는 화면은 없다 | "사장님 말(11-23) ②" |
| B1 | [제작 완료]는 파트 일이 남으면 막는다. 카드를 쓴 주문은 네 파트 모든 장이 끝나야. 마지막 검수 장을 끝내면 "제작 완료할까요?"를 물어 바로 완료 | 파트 점검 첫 묶음 |
| B2 | 맡은 사람은 [맡기 풀기], 같은 파트를 할 수 있는 사람은 [내가 맡기]로 넘겨받기, 기록을 남긴다 | 파트 점검 첫 묶음 |
| B3 | 밤 넘긴 맡음은 그대로(저절로 안 풀림), 카드에 '어제 맡음', 아침 첫 화면에 보이게 | 파트 점검 첫 묶음 |
| B4 | 보류 · 도면 수정 중 주문은 카드에 표시하고 못 누르게, 누르면 까닭 | 파트 점검 첫 묶음 |
| B5 | 작업 시트에서 공정 칸(예 재단)을 손으로 켠 집은 그 파트 카드가 '재단 끝'(칸은 안 꺼짐). 다시 하려면 작업 시트에서 끄면 카드가 다시 열림 | 손으로 켠 공정 칸 |
| B6 | 첫 카드를 맡으면 저절로 [제작 시작] | 파트 점검 둘째 묶음 |
| B7 | 파트 없는 생산팀 계정은 어느 파트 카드든 대신 누를 수 있다('보기만' 아님) | 파트 점검 둘째 묶음 |
| B8 | 새 화면 없이 날짜 탭 줄의 공정 4칸 아래에 맡은 사람 이름(예 "재단 김재단 · 엣지 아무도"), PC 도 같이 | 파트 점검 둘째 묶음 |
| B9 | 한 사람이 여러 파트 — 관리자가 사람마다 정함(1 · 2공장 같은 방식) | 2공장 뼈대 ④ · 둘째 묶음 |
| B10 | 파트 사이 순서는 막지 않는다(D46 그대로) | 원장 §28 D46 |
| C1 | 2공장 = 1공장이 넘칠 때 나눠 만듦(정해진 품목 없음) | 2공장 뼈대 ① |
| C2 | 나누는 단위 = 도면 한 장. 한 주문에 두 공장 장이 섞일 수 있다 | 2공장 뼈대 ② |
| C3 | 도면팀이 정하고 나중에도 바꾼다 — 생산으로 내려온 뒤에도. 바뀌면 두 공장 화면에 '바뀜' | 2공장 둘째 묶음 ③ |
| C4 | 2공장도 같은 방식(태블릿 · 파트 · 알아서 맡기 · 여러 파트) | 2공장 뼈대 ④ |
| C5 | 2공장 것은 1공장에 모아 함께 출고. 두 공장이 다 끝나야 제작 완료. 시공일 하나 | 2공장 뼈대 ⑤ · ⑨ |
| C6 | 남의 공장 카드는 보이지만 못 누름(흐리게, 누가 맡았는지 · 끝났는지는 읽힘) | 2공장 둘째 묶음 ⑥ |
| C7 | 기존 `flags.factory2` "라홈시스템(2공장)"은 계약 회사 표시라 다른 것 — 따로 두고, 이름에서 '2공장'을 뺀다 | 2공장 둘째 묶음 ⑦ |
| C8 | 도면 마감 · "도면 x/n" 은 주문 하나로(단계 · 마감이 주문에 하나라서) — 사장님께 묻지 않고 총괄이 정함(§16 질문 6 에서 반대하실 수 있게 적음) | 2공장 둘째 묶음 끝 |
| 늘 | 지금 화면 그대로 · 가장 작은 고침 · 시공일 늘 보임 · "내려옴" = 영업 컨펌 뒤 생산 단계 진입 · 쉬운 말 · 같은 말 한 번 · 기계 말 금지 · 태블릿 = 공장, PC = 보기 전용 · 누름 칸 보이는 44px(`calc(44px / var(--foms-ui-zoom, 1))`) · 무채색 상태 배지 금지 · 상태 색 쌍 ΔE2000 ≥ 10(색약 ≥ 6) | DECISIONS 2026-11-22 · 메모리 |

## 2. 지금 코드의 사실 (origin/deploy `1cb1c76f8`)

**카드 · 표시 줄**
- 카드 = 확정 도면 한 장(`foms/services/production/part_board.py:284-306` `build_pane_board`, 항목 = `resolve_final_drawing_files` `foms/services/drawing_confirm_cleanup.py:93-111`). 표시 줄 = 표 `production_part_marks` 한 줄 `(order_id, drawing_key, part)`(`models.py:560-606`, 유일 제약 `:599`), 상태 NONE · NEED(맡음) · BASIC(재단만) · DONE. **`picked_at` 은 이미 있다**(`models.py:589`, 맡을 때 찍고 되돌리기 DONE → NEED 는 그대로 둔다 — `foms/services/production/part_mark_rules.py:216-219`).
- 전이 표에 **맡음 → 안 고름 길이 없다**(`part_mark_rules.py:108-114` — take · basic · done · undo 넷). 남이 맡은 장은 관리자만 덮어쓴다(`:194-198`) — W1. 경합 글 "박재단이 먼저 맡았어요"(`:126-144`).
- 판은 고른 날 장의 생산 주문 표시 줄을 **한 번** 읽는다(`part_board.py:109-122`, `:342`). 칸 숫자 '작업 필요' = 파트 계정에게는 **내가 맡은 장만**(`:246`, `:263-270`) — 안 자른 8장이어도 0(W2).
- 화면 글: 남이 맡은 장 = "박재단 맡음"(`templates/production/partials/home_parts.html:25`), 내 장 · 관리자 보기 = "작업 필요 · 김재단"(`:27`) — 같은 상태 두 이름(W10). [재단 완료] 단추는 '작업 필요' 칸에서만 보인다(`:28` `pp-only-need` + `static/css/contexts/production/parts.css:115-116`) — 첫 칸에서는 3번 눌러야(W3). 409 글은 창을 닫고 맨 위 상태 줄로(`static/js/production/foms-production-parts.js:261-266`) — 화면 밖(W4). 카드에서 작업 시트로 가는 길이 없다(W8, 카드 이름 줄 `home_parts.html:71` 은 글뿐).
- 보류 · 불량 · 도면 수정 중이 카드에 안 보이고 막지도 않는다(`part_board.py:211-250` 은 그 값을 안 읽는다 — B3). 쓰기 API 의 주문 검사는 생산 단계 하나뿐(`foms/api/production/part_marks.py:155-161`).
- 30초 받아 오기 `GET /api/production/part-marks`(`foms/api/production/part_marks_read.py:116-139`) = 쿼리 1, 표시 줄만(주문 JSON 안 읽음).

**권한**
- 파트 계정 = 생산팀 + 계정 파트 **하나**(`models.py:1625` `users.production_part` String(16), CHECK `:1586-1591`, 읽기 `foms/services/production/part_constants.py:106-118`). 보기 모드 넷 — 관리자 · 파트 · 읽기 전용 · 못 봄(`foms/services/production/part_access.py:64-81`). **파트 없는 생산팀은 읽기 전용**(`:79-81`, D55), 쓰기 API 403 `PART_REQUIRED`(`part_marks.py:139-152`).
- 파트 계정은 공정 칸을 직접 못 쓴다(`part_access.py:102-114` → `foms/api/production/orders.py:1476-1478` 403, 작업 시트 읽기 전용 `foms/services/production_sheet_view.py:296`). 파트 없는 생산팀 · 관리자는 칸을 손으로 켠다.
- 생산 쓰기 여덟(start · complete · …)은 관리자 + 생산팀(`foms/services/production/write_access.py`, `orders.py:113-125`) — 파트 계정도 [제작 완료]를 누를 수 있다.

**공정 칸 · 완료 규칙**
- 칸 모양 `{key, label, done, at, by_name}`(`foms/services/production/steps.py:9`, 쓰기 `:119-141`) — **누가 · 어디서 켰는지(손 / 카드) 칸에 없다.** 흔적은 이벤트 payload `via: 'part_marks'` 뿐(`foms/services/production/part_steps_sync.py:35-37`, `:135-136`).
- 카드 동기화: 한 파트의 지금 모든 장이 끝이면 칸을 켜고 **하나라도 아니면 끈다**(`part_steps_sync.py:69-86`, `:109-120`) — 카드를 맡기만 해도 손으로 켠 칸이 꺼진다(B2). 도면 쓰기 셋(전달 · 전달 취소 · 확정 뒤 품목 취소)도 생산 · 시공 단계에서 같이 맞춘다(`:149-175`). 공정 API POST 는 동기화를 부르지 않는다(`orders.py:1487-1505`).
- [제작 완료] 판정 한 곳 `production_steps_missing`(`steps.py:83-93`): **칸을 하나도 안 켠 주문은 막지 않는다**(2026-11-21 결정). 카드로 일하는 동안 칸이 모두 꺼져 있으니 '안 쓴 주문'으로 판정 → 파란 단추(B1, 점검 그림 08). 부르는 곳 넷: 제작 완료 API(`orders.py:978-981`), 일반 단계 쓰기(`foms/services/orders/stage_override.py:223-234`), 공정 API 응답(`orders.py:1452`, `:1513`), 작업 시트 뷰(`production_sheet_view.py:221`).
- 제작 시작 = 생산 단계 + 회차 없음 → 회차 발급(`orders.py:758-918`, 단계 그대로 길 막음 `:811-827` · 쓰기 `:857-890`(`execute_order_mutation` 정책 `PRODUCTION_START`, 단계 이동 없음 — `transition_order` 는 고객컨펌 호환 길만), 곁일 `:604-617`). 막는 것: 회차 이미 있음 · 보류(`HOLD_ACTIVE`) · 도면 수정 중(`revision_in_flight_block`, `foms/services/orders/confirm_drawing_gate.py:108-118`).

**날짜 탭 · PC**
- 만들 것 줄 `fph_row`(`templates/production/partials/home_date_macros.html:16-29`): 공정 4칸(`:24-26`) · 도면 칸 "도면 n장"(`:27`, 값 `foms/services/production_home_read_model.py:443`). PC 줄 공정 칸(`templates/production/partials/home_pc_macros.html:47`).
- 보류 = `production.hold.active`(행 `hold_active`, `foms/services/production_dashboard_display.py:241`), 도면 수정 중 배지 판정 `production_drawing_badge`(`confirm_drawing_gate.py:121-131`) — 둘 다 이미 읽은 행의 JSON 에서 쿼리 0.
- 쿼리 수 계약: 날짜 탭 상한 11 · 파트 화면 +1 · 날 조각 상한 9(`tests/domains/test_production_home_query_count.py:27-29`, `:150`, `:187`), 표시 쓰기 한 번 상한 7(`tests/domains/test_production_part_marks_api.py:378-381`).

**도면 장 · 공장**
- 확정 도면 항목 모양은 허용 목록 `key · filename · view_url · download_url · sheet_id · item_uids`(`drawing_confirm_cleanup.py:70-90`) — 다른 칸은 읽을 때 버려진다. 항목을 새로 쓰는 곳 다섯: 전달(`foms/api/drawing/erp_orders_drawing.py:333`, 같은 시트 자리 바꾸기 `foms/services/orders/drawing_transfer.py:154-213`, 항목 만들기 `:283-318`), 전달 취소 되살리기(`erp_orders_drawing.py:789`), 수령 확정(`drawing_confirm_cleanup.py:338`), 확정 뒤 품목 취소(`foms/services/orders/drawing_confirm_partial.py:288`), 협력사 도면(`foms/services/partners/revision.py`).
- 마법사 시트 `drawing_wizard.sheets[]` 는 **화면이 통째로 가진 값**(`foms/api/drawing/wizard.py:179` `_CLIENT_OWNED_STATE_KEYS = ('v', 'sheets')`, 저장 = 보낸 sheets 로 통째 바꿈 `:851-867`, 열린 마법사는 `base_updated_at` 으로 저장 `static/js/drawing/wizard.js:5571-5576`). 시트 검사는 모르는 칸을 버리지 않는다(`wizard.py:702-751`). 탭 그리기 `renderTabs`(`wizard.js:4496-4534`), 탭 딱지 전례 AS(`static/js/drawing/wizard-as.js:36-60`). 직접 올린 파일은 `sheet_id` 가 없다. 작업실 '현재 버전' 목록 = `templates/drawing/partials/workbench_detail_body.html:1535-1538`(타일 매크로 `:52-98`), 보낼 시트 칸 `:1812-1822`.
- **장 · 계정 단위 공장 구분은 어디에도 없다.** 새 생산 첫 화면 · 파트 화면은 `flags.factory2` 를 읽지 않는다(`foms/services/production*` 검색 0).
- `flags.factory2` 를 읽는 곳(뜻 = 계약 회사): 견적 · 계약 공급자와 계좌(`foms/api/erp_estimates.py:69-93`, `foms/services/estimate_service.py:341-346`, `:442`, `:502`, `foms/services/orders/estimate_defaults.py:78-86`), 고객 공유 견적(`foms/services/order_share.py:106-108`), 실측 글머리 ★★(`foms/services/channel_measure_message.py:268`), 주문 복사(`foms/services/order_copy.py:56`), 초안 정리(`foms/api/erp_order_draft.py:94-235`), 바꿀 권한(`foms/services/orders/order_flag_permissions.py:31-36`, `:58`, `foms/api/erp_orders_structured.py:1038`, `:1287-1324`, `:1435-1441`), 감사 경로(`foms/services/orders/structured_diff.py:90`), 도면팀 바뀜 알림(`foms/services/notifications/drawing_order_change.py:207`, `:903`, `:912`), 옛 생산 칸반 공장 거르개(`templates/production/partials/tablet_kanban_body.html:103-107`, `:177`, `:247-251`, `static/js/foms/tablet-domain-sheets.js:508-544`).
- '바뀜' 길: 생산 변경 감지는 이벤트 종류 목록(`foms/services/production_change_alerts.py:65-71`) 한 번 읽기 + 도면 이력(JSON)에서 만든다(`:189-255`). 같은 목록이 조각 304 지문(`PRODUCTION_CHANGE_EVENT_TYPES`)이다.

**파일 크기 래칫**(`tests/harness/test_file_size_ratchet.py`, 파이썬 500 · JS 300): `part_marks.py` 455 · `production_home_read_model.py` 452 · `foms-production-parts.js` 297 · `foms-production-sheet-page.js` 291 — 새 기능은 새 모듈로. `orders.py`(1,810) · `wizard.js`(7,367) · `foms/web/auth/routes.py`(1,355)는 이미 큰 파일 목록에 있지만 더 키우지 않는다.

## 3. 범위 · 단계

| 단계 | 하는 것 | 마이그레이션 |
|---|---|---|
| **P1 맡기 고침** | B1 완료 막기 + 마지막 카드 물음 · B2 풀기 · 넘겨받기 · B3 어제 맡음 · 아침 글 · B4 보류 · 도면 고치는 중 막기 · B5 손으로 켠 칸 · B6 첫 맡기 = 제작 시작 · B8 맡은 사람 한 줄 · 카드 글 고침(W2 · W3 · W4 · W8 · W10) | 없음 |
| **P2 여러 파트** | B9 계정 여러 파트 · B7 파트 없는 생산팀 대신 하기 · 관리자 사용자 화면 | 1(+ 한 판 뒤 옛 칸 지우기 1) |
| **P3 2공장** | C1 ~ C8: 계정 공장 · 장의 공장 표지 · 도면팀 고르기 · 공장 보기(흐리게) · 섞인 주문 · 바뀜 · `flags.factory2` 이름 바꾸기 | 1 |

단계마다 따로 내보낼 수 있다(P2 는 P1 없이도 돌지만 P1 을 먼저 낸다, P3 은 P2 의 계정 화면 위에 공장 칸을 얹는다). P2 의 B7 은 스키마가 필요 없어 P1 에 옮겨도 된다 — 파트 권한 판정을 한 번에 고치려고 P2 에 둔다(사장님이 빨리 원하시면 P1 로).

범위 밖: §17.

## 4. 자료 규칙

### 4-1. 낱말 뜻

- **지금 장** = 주문의 지금 확정 도면 항목들(`resolve_final_drawing_files`).
- **카드를 썼다**(주문) = 그 주문에 상태가 NONE 이 아닌 표시 줄이 하나라도 있다(옛 key 줄 포함). 맡았다 푼 줄(NONE)만 있으면 안 쓴 것 — 실수로 맡았다 푼 주문이 '칸 안 쓴 주문' 길을 잃지 않게. 판정은 쿼리 1(`order_id IN (…) AND state <> 'NONE'`, 유일 제약 앞머리 `order_id` 를 탄다).
- **파트가 끝났다**(주문 · 파트) = 그 파트 공정 칸이 켜져 있다(손으로든 카드로든). 카드 동기화가 "지금 모든 장 끝"일 때만 카드 칸을 켜므로, 카드로 일한 파트는 칸 = 모든 장 끝이다(§4-4).
- **장이 끝났다**(장 · 파트) = 재단은 DONE 또는 BASIC, 그 밖은 DONE(지금 `_finished` `part_steps_sync.py:53-56` 그대로).

### 4-2. 제작 완료 될 수 있나 (생산 단계 주문) — B1

| 카드를 썼나 | 공정 4칸 | 결과 | 막힌 글 |
|---|---|---|---|
| 아니오 | 하나도 안 켬 | **됨**(지금 그대로 — 운영은 아직 칸 · 카드를 안 쓴다) | — |
| 아니오 | 일부만 | 막음 | 지금 글 "검수까지 끝나야 제작 완료할 수 있어요. (남은 공정: 조립 · 검수)" |
| 아니오 | 넷 다 | 됨 | — |
| 예 | 넷 다(손 · 카드 섞여도) | 됨 | — |
| 예 | 하나라도 꺼짐 | **막음** | "파트 일이 남았어요 — 재단 1장 · 검수 3장"(남은 장 수 = 칸이 꺼진 파트의 안 끝난 지금 장) |

- 경우마다: **확정 도면 0장 + 카드 씀**(옛 key 줄만 남음 — 품목 취소로 도면이 다 빠짐): 동기화가 칸을 안 건드리므로(`part_steps_after` 빈 결과 `part_steps_sync.py:79-81`) 칸 넷을 손으로 켜거나 관리자 뚫기. 글 "도면이 없어요 — 공정 칸을 켜거나 관리자에게 말해 주세요". **장이 바뀜**(새 key): 새 장이 안 끝나 카드 칸이 꺼짐 → 막힘(맞다). **섞인 공장**: 공정 칸은 주문에 하나라 두 공장 장이 다 끝나야 켜진다 → C5 와 같다. **한 파트에 장이 0** 인 경우는 없다(모든 장 × 모든 파트).
- 판정은 지금처럼 **한 함수**: `production_complete_block_body(sd, *, cards_used, parts_left=None)`(`steps.py`) — `cards_used` 가 참이면 "하나도 안 켬 = 됨" 예외를 끈다. 부르는 곳 넷(§2)이 모두 `cards_used` 를 넘긴다(새 도우미 `orders_with_cards(db, ids) -> set[int]`, 쿼리 1 · 일괄 쓰기도 1). 관리자 뚫기(`ADMIN_OVERRIDE`) · 단계 강제 변경 비상구는 그대로.
- 2026-11-21 결정("공정 칸을 쓴 주문만 막기")의 고침이다 — 승인되면 DECISIONS 에 "카드를 쓴 주문도 막는다"로 덧붙인다.

### 4-3. 마지막 카드 → "제작 완료할까요?" — B1

| 상황 | 결과 |
|---|---|
| 카드 쓰기(끝 · 기본 · 관리자 대신 끝내기) 뒤 동기화로 공정 4칸이 다 켜짐 + 생산 단계 + 보류 아님 + 누른 사람이 생산 쓰기 가능 | 쓰기 응답에 `order_ready: {order_id}` → 같은 확인 창이 이어서 "제작 완료할까요?" — 본문 "박서연 #4182 · 네 파트가 다 끝났어요. 제작 완료하면 시공 대기로 넘어가요." 단추 [나중에] [제작 완료] |
| [제작 완료] | 지금 API `POST /api/orders/<id>/production/complete`(멱등 열쇠) — 같은 한 함수가 다시 판정 |
| 그사이 남이 완료 | 409 `INVALID_STAGE` + 단계가 시공 → 창 안에 "그사이 다른 사람이 제작 완료했어요." [닫기] |
| 그사이 누가 카드를 되돌림 | 409 `STEPS_INCOMPLETE` → 창 안에 "그사이 바뀌었어요 — 검수 1장 남았어요." [닫기] |
| [나중에] | 창 닫기. 날짜 탭 줄 '검수 끝', 작업 시트 [제작 완료] 파랑 — 누구든 나중에 |
| 되돌리기 | 지금 작업 시트 [완료 취소](`orders.py:1273-1352` uncomplete) 그대로 |

- 사장님 말은 "마지막 **검수** 장"이지만 파트 순서를 막지 않으므로(D46) 마지막에 끝나는 장이 조립일 수 있다 → **어느 파트든 주문의 마지막 남은 장을 끝낸 사람**에게 묻는다(§15 ③).
- 누가 확인하나: 그 카드를 끝낸 사람(생산팀 · 관리자 — 지금도 [제작 완료]를 누를 수 있는 사람들). 따로 정한 '완료 담당'은 없다.
- 섞인 주문에서 마지막 장이 2공장일 때 → §16 질문 7.

### 4-4. 손으로 켠 공정 칸 — B5

- **칸에 표지를 더한다**: `{key, label, done, at, by_name, via}` — `via` = `'sheet'`(공정 API · 작업 시트 · 내 공정 판에서 사람이 켬) · `'part_marks'`(카드 동기화가 켬). 끄면 `via` 도 지운다. `set_production_step(…, via=…)` 한 함수(`steps.py:119-141`)가 쓴다. JSON 칸 하나 더함 — 마이그레이션 없음.
- **옛 칸(`via` 없음)** = 손으로 켠 것으로 본다(안전한 쪽 — 사람이 켰을지 모르는 칸을 카드가 끄지 않는다). 운영은 칸을 거의 안 쓴다(11-12 실측 0, 원장 `:495`) — 내보내기 전에 생산 단계 주문의 켜진 칸 수를 읽기로 센다(§13).

| 칸 상태 | 그 파트 카드 화면 | 그 파트 카드 쓰기 | 카드 동기화 |
|---|---|---|---|
| 꺼짐 | 표시 줄대로(지금) | 됨 | 모든 장 끝이면 켬(`via='part_marks'`) |
| 켜짐 · `via='part_marks'` | 표시 줄대로(모두 끝) | 되돌리기 됨 → 동기화가 끔(지금) | 지금 그대로 |
| 켜짐 · `via='sheet'` 또는 없음 | **모든 장 "재단 끝 · 작업 시트"**, 단추 없음, 누르면 "작업 시트에서 재단을 끝으로 켰어요. 다시 하려면 작업 시트에서 꺼 주세요." | 막음 409 `STEP_SET_BY_HAND`(맡기 풀기만 됨) | **안 건드림**(끄지도 켜지도 않음) |

- 켤 때 그 파트에 맡음 줄이 있으면 **줄은 그대로 둔다**(지우지 않음). 화면은 '끝'만 보이고, 작업 시트에서 칸을 끄면 카드가 그 전 모습("김재단 맡음")으로 돌아온다 — "다시 하려면 끄면 카드가 다시 열림".
- 카드로 켜진 칸(`via='part_marks'`)을 작업 시트에서 끄려 하면 막는다 409 `STEP_SET_BY_CARDS` "카드로 끝낸 공정이에요. 다시 하려면 도면 카드에서 되돌려 주세요." — 끄면 다음 카드 쓰기 때 동기화가 다시 켜 버린다(칸 · 카드가 서로 덮음). 사장님 예는 손으로 켠 칸이라 이 막음과 부딪히지 않는다(§15 ④).
- 섞인 주문: 칸이 주문에 하나라 1공장 관리자가 손으로 켜면 2공장 장도 '끝'으로 보인다(§14).

### 4-5. 맡기 · 풀기 · 넘겨받기 — B2

표시 줄 전이(⊙ = 새로 더함). '할 수 있는 사람' = 그 파트를 할 수 있는 사람(§5).

| 누름 | 지금 → 새 | 누가 | 화면이 보내는 것 | 기록 |
|---|---|---|---|---|
| take 맡기 | 없음 · NONE → NEED(나) | 할 수 있는 사람 | `seen:none` | 지금 |
| basic 기본(재단) | NONE → BASIC | 할 수 있는 사람 | `seen:none` | 지금 |
| done 끝 | NEED(나) → DONE | 맡은 사람 · 관리자/대신(덮어쓰기) | `seen:need` + ⊙`seen_by` | 지금 |
| undo 되돌리기 | DONE → NEED · BASIC → NONE | 끝낸 사람 · 관리자/대신 | `seen:done/basic` | 지금 |
| ⊙ release 맡기 풀기 | NEED(나) → NONE(맡은 사람 · 때 지움) | 맡은 사람 · 관리자/대신 | `seen:need` + `seen_by` | 이벤트 `action:'release'` |
| ⊙ takeover 내가 맡기 | NEED(남) → NEED(나, `picked_at` = 지금) | 할 수 있는 사람(맡은 사람 아님) | `seen:need` + `seen_by=<그 사람 id>` | 이벤트 `action:'takeover'`, payload `from_user_id` · `from_name` + 감사 "재단 넘겨받음 김재단 → 박재단" |

- `seen_by`(화면이 본 맡은 사람 id)를 더하는 까닭: 지금 `seen` 은 상태만 봐서 "김재단 맡음"과 "박재단 맡음"을 못 가린다. 넘겨받기 · 풀기 · 끝은 맡은 사람이 화면과 같을 때만 한다.
- **경합**(주문 행 잠금이 줄 세움 — 지금 그대로): 화면이 본 상태 · 맡은 사람과 서버가 다르면 409 `MARK_CONFLICT` + 지금 모습. 글 = "박재단이 먼저 맡았어요"(take) · "박재단이 넘겨받았어요"(그사이 남이 넘겨받음) · "김재단이 먼저 끝냈어요" · "그사이 맡기를 풀었어요". **글은 확인 창 안**에 보이고 창 아래 카드는 서버 모습으로 바뀐다, 실행 단추는 [닫기](W4).
- 멱등: 같은 사람이 같은 결과를 다시 보내면 200(지금 `_same_result` 규칙에 release = NONE · 마지막으로 바꾼 사람이 나, takeover = NEED · 맡은 사람이 나).
- 넘겨받은 기록은 카드에 따로 그리지 않는다(카드는 지금 맡은 사람만). 기록 = 이벤트 `PRODUCTION_PART_MARKED` payload + 감사 한 줄 — 주문 이력 탭에서 보인다. 새 칸 · 새 표 없음(§6-4).
- 풀기 · 넘겨받기도 30초 받아 오기(`part_marks_read.py`)로 남의 화면에 간다(표시 줄이라 그대로).

### 4-6. 막는 것 — B4 · B5 · C6

| 까닭 | 판정(쿼리 0, 이미 읽은 JSON) | 카드 화면 | 서버(쓰기 API) | 되는 것 |
|---|---|---|---|---|
| 보류 | `production.hold.active`(`production_dashboard_display.py:241` 과 같은 값) | 단추 자리에 "보류 · <까닭>"(호박 바탕), 누르면 "보류 중이라 지금은 못 눌러요. 보류를 풀면 다시 돼요." | 409 `HOLD_ACTIVE` | 내 맡기 풀기 · 되돌리기 |
| 도면 고치는 중 | `drawing_revision_in_progress(sd)`(`confirm_drawing_gate.py:116-118` — 제작 시작 게이트와 같은 술어) | 단추 자리에 "도면 고치는 중"(빨강 바탕), 누르면 "도면을 고치는 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요." | 409 `DRAWING_REVISING` | 내 맡기 풀기 · 되돌리기 |
| 손으로 켠 칸 | §4-4 | "재단 끝 · 작업 시트" | 409 `STEP_SET_BY_HAND` | 내 맡기 풀기 |
| 남의 공장(P3) | 장의 공장 ≠ 내 공장(§4-10) | 흐린 카드 + "2공장 · 보기만", 누르면 "2공장 도면이에요. 보기만 돼요." | 403 `OTHER_FACTORY`(관리자 빼고) | 내 맡기 풀기(장이 옮겨 간 경우) |
| 불량 보고 | `production.defects` 마지막 | 카드 아래 작은 글 "불량 · 파손 11/24"(막지 않음) | — | 모두 — 지금도 불량은 완료 게이트가 아니다(`orders.py:935-936` docstring) |

- 화면 단추는 `disabled` 대신 `aria-disabled` + 누르면 까닭(2026-11-22 터치 결정과 같은 꼴). 서버도 같은 판정으로 막는다(화면만 막으면 다른 기기 · 늦은 화면이 뚫는다).
- 맡기 풀기는 늘 된다 — 일을 돌려놓는 것이라 막을 까닭이 없다.

### 4-7. 첫 맡기 = 제작 시작 — B6

- 카드 쓰기(take · basic · takeover · 일괄 기본) 뒤 표시가 NONE 이 아닌데 그 주문에 **지금 회차가 없으면**(제작 대기) 같은 tx 안에서 제작 시작을 한다. 회차 찾기 쿼리 1(`fetch_production_current_run_ids` 꼴).
- 하는 일은 지금 [제작 시작] 단계 그대로 길(a)과 같다 — `execute_order_mutation`(정책 `PRODUCTION_START`, 단계 이동 없음) 안에서 단계 기록 "제작 시작 (도면 카드 첫 맡기)" · 회차 발급 · 감사 · 이벤트 `PRODUCTION_STARTED`(payload `via:'part_marks'`) · 버전 +1. 카드 쓰기가 이미 잡은 주문 행 잠금 안에서 한 tx. **누가** = 카드를 맡은 사람(이벤트 `created_by_user_id` · 단계 기록 이름).
- 코드: 지금 `orders.py:604-617` · `:857-890` 을 새 서비스 `foms/services/production/start_run.py` `start_production_run(db, order, user, *, via)` 로 옮겨 제작 시작 API 와 카드 쓰기가 같이 쓴다(api 가 api 를 부르지 않게, 자리 고정 시험).
- 막는 것은 카드 쓰기 막음(§4-6)과 같다(보류 · 도면 고치는 중 → 맡기 자체가 막힘). 생산 단계가 아니면 카드가 없다(`_check_order`). 이미 회차가 있으면 아무것도 안 함(멱등 — 주문 행 잠금 안에서 본다).
- 첫 맡기를 풀어도 **제작 시작은 그대로**(되돌리지 않음) — 되돌리려면 작업 시트 [제작 취소](지금 그대로). 바뀐 것 감지는 생산 → 생산 이동이라 바닥선을 안 옮긴다(`production_change_alerts.py:61` `_DOWNSTREAM_STAGES`).
- 작업 시트 [제작 시작] 단추는 칸만 쓰는 주문을 위해 그대로 둔다.

### 4-8. 맡은 때 · 어제 맡음 · 아침 글 — B3

- 카드 상태 글: 오늘 맡음 "김재단 맡음" · 어제(KST 날짜) "김재단 맡음 · 어제" · 그 전 "김재단 맡음 · 11/20 (금)". 내 카드는 이름 대신 "내가 맡음". `picked_at`(UTC) → KST 날짜로. 표시 줄 응답 `mark_payload`(`part_mark_rules.py:254-270`)에 `picked_day`(KST `YYYY-MM-DD`)를 더해 30초 받아 오기 뒤에도 글이 맞게.
- '어제' 글 조각은 호박 글자(`#9a3412` 위 `#ffedd5`) — 무채색 아님, 맡음 바탕과 ΔE 20.7 / 29.9(§8-9).
- **아침 글**(파트 계정, 전체 페이지에만): 위 줄 아래 한 줄 "어제부터 맡은 도면 2장 — 11/23 (월) 1장 · 지난 7일 1장", 날마다 그 날 장 링크(`home_href`). 셈 = 내가 맡은 NEED 줄 중 `picked_at` 이 오늘 KST 0시 전. 쿼리 1(`order_id IN (첫 화면 생산 주문) AND picked_by_user_id = 나 AND state = 'NEED'`, 유일 제약 앞머리 `order_id` 를 탄다). 날 조각(`view=day`)에는 없다(조각 쿼리 그대로).
- 저절로 풀지 않는다(지금도 푸는 곳이 없다).

### 4-9. 날짜 탭 줄 '맡은 사람' — B8

- 만들 것 줄의 공정 4칸 **바로 아래, 칸마다** 작은 글: 그 파트를 지금 맡은 사람(NEED 줄의 `picked_by_name`, 맡은 때 순, 첫 이름 + "외 n") · 아무도 없으면 "아무도". 칸이 이미 켜졌으면 비움(칸이 끝을 말한다 — 같은 말 한 번). 칸 이름(재단 …)은 바로 위 칸에 있어 되풀이하지 않는다(사장님 예 "재단 김재단 · 엣지 아무도"를 칸 아래 자리로).
- 어제 전부터 맡은 이름은 호박 글자 + 뒤에 "어제"(아침 반장 화면에도 보이게).
- 확정 도면이 없는 줄(도면 없음)은 그리지 않는다. 손으로 켠 칸은 비움(켜짐).
- 2공장(P3): 이름은 두 공장 사람을 함께(사람 이름으로 공장이 갈린다), 2공장 사람 이름 앞에 작은 "2공장"은 붙이지 않는다(§16 질문 3 과 함께 볼 것).
- 값: 고른 날 장 만들 것 주문의 표시 줄 한 번 읽기(파트 계정은 판이 이미 읽은 줄을 다시 씀 — 0). 새 순수 모듈 `foms/services/production/part_holders.py` `attach_part_holders(rows, marks, today)`(행에 `part_holders` 4칸).
- PC 줄: 같은 값을 공정 칸 아래 작은 글(`fpc-s` 안 둘째 줄). 마우스 글(`data-tip`)에 "재단 · 김재단 맡음 · 어제 9:40"(이미 있는 칸 글 뒤).

### 4-10. 여러 파트 · 파트 없는 생산팀 — B7 · B9 (P2)

- 계정 파트 = 0 ~ 4개(§6-1). 판정 함수는 `account_production_parts(user) -> tuple[str, ...]`(정의 순서, 생산팀 아니면 빈 것).
- 보기 모드: **파트**(파트 1개 이상) · ⊙**대신**(생산팀 · 파트 없음 · VIEWER 아님 — B7, 지금 읽기 전용에서 옮김) · **관리자** · 읽기 전용(그 밖 직원) · 못 봄.
- 판 고르기: 파트 2개 이상이면 판 머리에 파트 고르기(지금 관리자의 `pp-parts` 를 그 사람 파트만), 처음 = 주소 `?part=`(내 파트 안일 때) 아니면 정의 순서 첫 파트. 파트 계정은 지금처럼 날짜 탭에 바로 카드(D50 내 공정 탭 숨김 그대로).
- 대신 모드 = 지금 관리자와 같은 카드 권한(네 파트 · 남의 장 대신 끝내기 · 되돌리기 · 풀기, 확인 창에 "김재단이 맡은 도면이에요" 한 줄 — D55 그대로) + 공정 칸 손으로 켜기(지금처럼). 칸 숫자는 그 파트 전체(관리자와 같음). 날짜 탭은 지금처럼 장 + [도면 카드로 보기].
- 공정 칸 직접 쓰기 잠금(`steps_locked_for`) = 파트 1개 이상인 계정(관리자 빼고) — 대신 모드는 잠그지 않는다(손으로 켜는 사람이 이들이다).

### 4-11. 2공장 (P3)

**계정 공장**: 생산팀 계정마다 1공장 또는 2공장(§6-2, 비면 1공장). 관리자는 판 머리 공장 고르기 [1공장 | 2공장](처음 = 계정 값 또는 1). 한 사람이 두 공장 → §16 질문 2.

**장의 공장**(§6-3): `structured_data.drawing_factory` — 시트 신원(`sheet_id`)마다, 직접 올린 파일은 저장 key 마다 1 · 2. 없으면 1공장. 읽기 함수 하나 `sheet_factory(sd, entry) -> int`(순수, 쿼리 0): `sheet_id` 가 있고 표에 있으면 그 값 → key 가 표에 있으면 그 값 → 1.

| 일 | 장의 공장 |
|---|---|
| 같은 시트 다시 보내기(새 판) · 한 장만 바꾸기 | 같은 `sheet_id` → 그대로(새 key 여도) |
| 수령 확정 · 전달 취소 되살리기 · 품목 취소로 장 빠짐 | 표가 따로라 그대로(빠진 장의 표 줄은 다음 쓰기 때 정리) |
| 직접 올린 파일(시트 신원 없음) | key 로 — 같은 파일을 새로 올리면 새 key 라 **1공장으로 돌아간다**(§14, 작업실 목록에 공장이 보여 놓치기 어렵게) |
| 마법사 시트 복제 | 새 시트 신원 → 1공장 |
| AS 도면 | 생산 카드가 없어 공장을 두지 않는다(§17) |

**바꾸기**: 도면 담당 · 도면팀 · 관리자(지금 전달 권한 `DRAWING_ASSIGNED` 과 같음). 새 API `POST /api/orders/<id>/drawing/sheet-factory`(§7). 마법사 탭 · 작업실 '현재 버전' · 보낼 시트 칸 어디서 바꿔도 같은 API · 같은 표. 주문이 생산 단계 이상이면 확인 창 "생산에 이미 내려간 도면이에요. 2공장으로 옮기면 두 공장 화면에 '바뀜'이 떠요."

**옮긴 장의 표시 줄**(§16 질문 1 — 추천값): **그대로 둔다**. 끝낸 파트는 끝(한 일은 한 일), 맡음은 맡은 사람 이름 그대로 — 새 공장 사람이 [내가 맡기]로 넘겨받거나 맡은 사람이 푼다. 저절로 지우거나 풀지 않는다(숨은 쓰기 없음).

**공장 보기**(파트 판):
- 내 공장 장 = 지금 카드. 남의 공장 장 = **같은 판 맨 뒤** "2공장 카드 4장 · 보기만" 머리 아래 흐린 카드(연한 청록 바탕 · 점선 테두리 · 그림 흐림, 글은 그대로 읽힘 — 누가 맡음 · 끝). 섞인 주문은 내 장 카드에 "2공장 2장 따로" 작은 글.
- 칸 숫자(전체 도면 · 맡은 것 · 끝)는 내 공장 장만.
- 남의 공장만 있는 주문도 같은 뒤 묶음에 흐리게(보이지만 못 누름).

**날짜 탭 · PC**(주문 단위 그대로 — C8):
- 띠 '만들 것 / 전체' · "도면 x/n" · 마감 · 장 순서 · 공정 4칸 · 단계 · 보류는 주문에 하나 — 두 공장 같은 숫자.
- 만들 것 줄 도면 칸: 섞인 주문은 두 줄 "우리 3장" / "2공장 2장"(1공장 보기) · "우리 2장" / "1공장 3장"(2공장 보기) · "1공장 3장" / "2공장 2장"(관리자 · PC). 남의 공장 장만 있는 줄은 흐리게 + 그 공장 이름 칩, 만들 것 묶음 안 맨 뒤로(안정 정렬).
- 위 줄 날짜 글 "11월 24일 (화) · 2공장 · 전체 39건"(공장이 정해진 계정만).
- 작업 시트 도면 목록: 2공장 장이 하나라도 있는 주문만 장마다 "1공장" / "2공장" 칩.

**섞인 주문 제작 완료**: 공정 칸이 주문에 하나라 **두 공장 모든 장이 끝나야** 칸 넷이 켜짐 → §4-2 그대로 C5 를 만족. 마지막 장을 끝낸 사람이 2공장이면 → §16 질문 7.

## 5. 권한 표 (서버가 막는다)

| 누가 | 카드 보기 | 맡기 · 기본 · 끝 · 되돌리기 | 남이 맡은 장 | 내 맡기 풀기 | 남의 맡기 풀기 | 공정 칸 손으로 | 제작 시작 · 완료 | 장 공장 바꾸기 |
|---|---|---|---|---|---|---|---|---|
| 파트 계정(내 파트들 · 내 공장) | 네 파트 · 두 공장(남의 공장 흐림) | 내 파트 · 내 공장 장만 | [내가 맡기] 넘겨받기 | 됨 | 안 됨 | 안 됨(403 지금 그대로) | 됨(지금 그대로) | 안 됨 |
| 여러 파트 계정(P2) | 같음 | 고른 파트들 | 같음 | 됨 | 안 됨 | 안 됨 | 됨 | 안 됨 |
| 파트 없는 생산팀(P2 대신) | 같음 | 네 파트 · 내 공장 | 넘겨받기 · 대신 끝내기 | 됨 | 됨 | 됨 | 됨 | 안 됨 |
| 관리자 | 같음 + 공장 고르기 | 네 파트 · 두 공장 | 넘겨받기 · 대신 끝내기(D55) | 됨 | 됨 | 됨 | 됨 | 됨 |
| 도면 담당 · 도면팀 | 읽기 전용 | 안 됨 | — | — | — | 안 됨 | 안 됨 | **됨** |
| CS · 영업 · 시공 · 출고 | 읽기 전용 | 안 됨(403) | — | — | — | 안 됨 | 안 됨 | 안 됨 |
| VIEWER · 협력사 · 꺼진 계정 | 못 봄 | 안 됨 | — | — | — | 안 됨 | 안 됨 | 안 됨 |
| PC([고치기] 안 켬) | 보기 전용(쓰기 단추 없음) | 화면에 없음 | — | — | — | — | — | — |

- 판정은 한 곳: `part_access.py`(`writable_parts(user)` · `can_override_marks(user)` · ⊙`user_factory(user)` · ⊙`can_write_sheet(user, factory)`). 쓰기 API 의 파트 문(`_gate_part`)과 화면 단추가 같은 함수를 본다. 정책 매니페스트 `PRODUCTION_PART_MARK` 설명(`foms/services/orders/order_mutation_policy.py:201-202`)의 "파트 없는 생산 deny"를 고친다(가드 팀 PRODUCTION 은 그대로).
- 남이 맡은 장 · 대신 끝내기 · 풀기 때 확인 창에 "김재단이 맡은 도면이에요" 한 줄(지금 `ownerNote` `foms-production-parts.js:59-69` — 관리자만 → 대신 모드도).

## 6. 자료 모양 — 고른 것과 까닭

### 6-1. 계정 여러 파트 (P2)

| 안 | 좋은 점 | 나쁜 점 |
|---|---|---|
| ⓐ 같은 칸 `production_part` 를 쉼표 글로 | 칸 그대로 | String(16) 이 짧음(넷 = 25자), CHECK 가 정규식(SQLite 못 함), 읽는 곳마다 쪼개기 |
| ⓑ 숫자 하나(비트 4개) `production_parts_mask` | 쿼리 0, CHECK `BETWEEN 0 AND 15` 이 두 DB 다 됨 | 사람이 DB 로 읽을 수 없음, 감사 글 · 시험이 숫자 풀기 |
| ⓒ 연결 표 `user_production_parts(user_id, part)` | 교과서 꼴, CHECK 두 DB, 공장을 줄마다 둘 수도 | **요청마다 쿼리 +1**(생산 화면 · 표시 쓰기 · 작업 시트) — 날짜 탭이 상한 11 에 닿는다, 관리자 저장이 지우기 + 넣기 |
| **ⓓ JSON 목록 `users.production_parts`**(PG JSONB) | 쿼리 0, 읽기 쉬움(`["cut","edge"]`), 이 저장소의 JSON 칸 꼴(`revoked_session_ids`, `models.py:1631`) | CHECK 는 PG 에만(SQLite 시험은 앱 검사로) |

**추천 ⓓ.** 까닭: 사용자 행은 요청마다 이미 읽는다(`g.current_user`) — 쿼리를 늘리지 않는 안이 ⓑ · ⓓ 뿐이고, 둘 중 사람이 읽을 수 있는 쪽. 값은 앱 한 곳(`normalize_production_parts` — 모르는 값이면 ValueError, 겹침 빼고 정의 순서로, 빈 목록 = NULL)이 맞추고, PG 에는 `CHECK (production_parts IS NULL OR (jsonb_typeof(production_parts) = 'array' AND production_parts <@ '["cut","edge","assemble","inspect"]'::jsonb))`(`ck_users_production_parts`, `ddl_if(dialect='postgresql')` — PG 전용 DDL 전례: `models.py` AccessLog 표현식 색인).

- **마이그레이션 `prodparts_01`**: 칸 더하기(NULL 허용) → 채우기 `production_parts = jsonb_build_array(production_part) WHERE production_part IS NOT NULL` → CHECK. downgrade = `production_part = production_parts->>0` 로 되돌린 뒤 칸 지움. 줄 잠금 짧음(칸 더하기 · 사용자 수백 줄).
- **한 판 동안 둘 다 쓴다**: 관리자 저장이 `production_parts` 와 `production_part = 첫 파트` 를 같이 쓴다 — P2 코드를 되돌려도 옛 코드가 맞는 파트를 읽는다. 다음 판(P2b, 운영 1주 뒤)에 `production_part` · `ck_users_production_part` 를 지우는 마이그레이션.
- **`production_part` 를 읽는 곳 전부**(P2 가 고칠 곳): `models.py:1586-1591`(CHECK) · `:1625`(칸) · `:1646`(`to_dict`) / `part_constants.py:106-118`(`account_production_part` — 칸을 직접 읽는 유일한 함수) / `part_access.py:48-61`(`part_account_part`) → `:64-81` `part_view_mode` · `:84-99` `writable_parts` · `:102-114` `steps_locked_for` / `part_board.py:309-321` `resolve_board_part` · `:336-351` / `part_marks.py:139-152` `_gate_part` / `orders.py:1443`, `:1476`(`steps_locked_for`) / `production_sheet_view.py:296` / `foms/web/production/home.py:84`, `:86`, `:100`, `:105-109`(JS 설정 `part` 하나), `:116-118`, `:198` / `foms/web/auth/routes.py:38-40`, `:202-203`(감사 칸), `:779`, `:790`(화면 목록), `:795-805`(폼 읽기), `:857-859`(목록 글), `:895`, `:909`(추가), `:979`, `:1028`(수정) / `templates/auth/add_user.html:65-73` · `edit_user.html:80-89` · `user_list.html:195` / `static/js/production/foms-production-parts.js:17-24`(`cfg.part` 하나) / 정책 설명 `order_mutation_policy.py:201-202` / 시험 씨앗 `production_part=` 11곳(`tests/domains/test_admin_user_production_part.py` · `test_production_part_marks_model.py` · `test_production_part_board.py` · `test_production_part_marks_api.py` · `test_production_part_marks_sync.py` · `test_production_part_steps_sync.py` · `test_production_parts_screen.py` · `test_production_write_access.py` · `test_production_complete_requires_inspect.py` · `test_production_home_query_count.py` · `tests/support/production_home_step_panel_seed.py`). 옛 마이그레이션 `prodpart_00` 은 그대로.

### 6-2. 계정 공장 (P3)

- **`users.production_factory` SmallInteger NULL, CHECK `production_factory IS NULL OR production_factory IN (1, 2)`**(`ck_users_production_factory`, 두 DB). NULL = 1공장으로 본다(채우기 없음). 생산팀이 아니면 저장 때 비운다(파트와 같은 규칙 `production_part_for_team`).
- 한 사람 = 한 공장(추천, §16 질문 2). 두 공장 다 하면 관리자가 그때그때 바꾼다. "둘 다"가 필요하면 값 `0` 하나를 더하는 작은 고침으로 된다(CHECK · 판정 함수만).
- 감사 칸(`_AUDITED_USER_FIELDS`)에 더한다. 세션은 끊지 않는다(파트와 같음).

### 6-3. 장의 공장 표지 (P3)

| 안 | 문제 |
|---|---|
| ⓐ 마법사 시트 `drawing_wizard.sheets[i].factory` | sheets 는 **화면이 가진 값**이라 저장 때 통째로 바뀐다(`wizard.py:179`, `:851-867`). 작업실에서 바꾼 값을 서버가 sheets 에 써 넣으면, 열려 있던 마법사의 다음 자동 저장이 옛 값으로 덮거나(조용한 되돌림) `base_updated_at` 이 어긋나 저장 충돌이 난다. 직접 올린 파일은 시트가 없어 못 담는다 |
| ⓑ 확정 도면 항목 `drawing_current_files[i].factory` | 항목을 새로 쓰는 곳이 다섯(§2)이고 허용 목록(`drawing_confirm_cleanup.py:70-90`)이 모르는 칸을 버린다 — 다섯 곳 모두 값을 옮겨야 하고 하나라도 빠지면 조용히 1공장으로 돌아간다. 생산 뒤 공장만 바꿀 때 도면 항목을 다시 써야 한다 |
| **ⓒ 주문 JSON 의 서버 소유 칸 `structured_data.drawing_factory`** | `{"sheets": {"<sheet_id>": 2}, "files": {"<저장 key>": 2}, "at": "<UTC iso>", "by_name": "장미래"}` — 이 API 만 쓴다 |

**추천 ⓒ.** 까닭: 시트 신원은 판이 바뀌어도 같아서(`replace_same_sheet_files` 의 축) 다시 보내기 · 한 장 바꾸기 · 확정 · 전달 취소에서 저절로 살아남는다. 마법사 저장 · 도면 전달 · 확정 어느 길도 이 칸을 건드리지 않는다(마법사 저장은 `drawing_wizard` 안 sheets 만, 전달 · 확정은 `drawing_current_files`). 생산 쪽은 행이 이미 들고 있는 JSON 에서 읽는다(쿼리 0).

- 쓰기 규칙(AGENTS.md): 주문 행 잠금 → `sd = copy.deepcopy(order.structured_data)` → `sd['drawing_factory']` 고침 → `order.structured_data = sd` → `flag_modified(order, 'structured_data')` → `execute_order_mutation`(버전 +1 — 편집 화면 · 마법사 전달의 If-Match 가 바뀐 것을 안다) → commit. 같은 tx 에 이벤트 `DRAWING_SHEET_FACTORY_CHANGED` 한 줄(§9).
- 값 = 1 또는 2 만(바꾼 장만 줄이 생김). 1 로 되돌리면 줄을 지운다(없음 = 1). 지금 마법사 시트 · 지금 장 어디에도 없는 열쇠는 쓰기 때 지운다.
- 마법사 화면이 탭 딱지를 그리려면 이 표가 필요하다 → 마법사 GET 응답 `data.factory_by_sheet`(서버가 읽어 줌, 마법사 상태에 넣지 않음).

### 6-4. 넘겨받은 기록

- **표시 줄에 칸을 더하지 않는다** — 지금도 모든 표시 쓰기가 이벤트 `PRODUCTION_PART_MARKED`(payload key · part · from · to · action · override, `part_marks.py:179-190`)와 감사 한 줄(`:209-224`)을 남긴다. 넘겨받기는 payload 에 `from_user_id` · `from_name` 을 더하고 감사 글이 "재단 넘겨받음 (김재단 → 박재단)". 주문 이력에서 읽힌다. 마이그레이션 없음.

### 6-5. 맡은 때

- `picked_at` 은 이미 있다(`models.py:589`). 넘겨받기 = 새 시각, 풀기 = 지움, 되돌리기(DONE → NEED) = 그대로(지금 규칙).

### 6-6. 공정 칸 `via`

- §4-4. JSON 칸 하나. 이벤트 payload 의 `via` 와 같은 낱말(`'part_marks'`), 사람 쪽은 `'sheet'`.

## 7. API (새 · 바뀜)

| API | 바뀜 |
|---|---|
| `POST /api/production/part-marks` | `action` 에 `release` · `takeover` 더함, 몸에 `seen_by`(정수, need 일 때). 막음 코드 `HOLD_ACTIVE` · `DRAWING_REVISING` · `STEP_SET_BY_HAND` · `OTHER_FACTORY`(P3). 응답에 `order_ready`(§4-3) · `run_started`(첫 맡기) · 바뀐 `mark.picked_day`. 처리 몸통은 새 모듈 `foms/api/production/part_mark_actions.py` 또는 서비스 `foms/services/production/part_mark_write.py` 로(파일 455 → 500 래칫) |
| `POST /api/production/part-marks/basic` | 같은 막음(장마다 `skipped` 로), 첫 기본 = 제작 시작 |
| `GET /api/production/part-marks` | 응답 줄에 `picked_day`. 쿼리 그대로 1 |
| `POST /api/orders/<id>/production/steps` | 칸에 `via:'sheet'`. 끄려는 칸이 `via:'part_marks'` 면 409 `STEP_SET_BY_CARDS`. 응답 `complete_ready` 는 카드 규칙(쿼리 +1) |
| `GET …/production/steps` · `POST …/production/complete` · 일반 단계 쓰기 생산 → 시공 | 카드 규칙(§4-2, 쿼리 +1 · 일괄도 +1). 막힌 글에 남은 장 수(막힐 때만 표시 줄 읽기 +1) |
| ⊙ `POST /api/orders/<id>/drawing/sheet-factory`(P3) | 몸 `{items: [{sheet_id? , key?, factory: 1|2}], idempotency_key}` — 장 하나 또는 여럿. 권한 = 정책 `DRAWING_ASSIGNED`(전달과 같음, 매니페스트 `docs/harness/foms_order_mutation_policy_manifest.json` 에 등재) · 등록은 `foms/platform/blueprints.py`(정본) · CSRF. 응답 `{success, data: {factory_by_sheet, factory_by_key, changed: n}, error}`. 같은 값이면 쓰지 않음(버전 그대로) |

모든 글은 해요체 한 문장, 응답 꼴 `{success, data, error}`(지금 표시 API 와 같음).

## 8. 화면 — 지금 → 바뀜 (가장 작은 고침)

### 8-1. 파트 카드(`home_parts.html` · `parts.css` · 새 JS)

| 곳 | 지금 | 바뀜 |
|---|---|---|
| 아무도 안 맡은 장 | [기본] [내가 자름] / [내가 엣지] | 그대로 |
| 내가 맡은 장 | 첫 칸: "작업 필요 · 김재단"(단추 없음) · '작업 필요' 칸: [재단 완료] | **모든 칸에서** "내가 맡음" + [맡기 풀기] [재단 끝](둘 다 보이는 44px 넘음) |
| 남이 맡은 장 | "박재단 맡음"(파트 계정) / "작업 필요 · 박재단"(관리자) | 모두 "박재단 맡음" + [내가 맡기](할 수 있는 사람만). 대신 · 관리자는 [내가 맡기] [재단 끝] |
| 어제 맡음 | 표시 없음 | "… 맡음 · 어제"(호박 글자) |
| 끝 · 기본 | "재단 끝 · 김재단" · '완료' 칸에서 [되돌리기] | 그대로 |
| 손으로 켠 칸 | 칸이 카드 맡기에 꺼짐 | "재단 끝 · 작업 시트", 단추 없음 |
| 보류 | 보통 카드 · 누르면 됨 | 단추 자리 "보류 · 자재 기다림"(호박), 누르면 까닭 |
| 도면 고치는 중 | 보통 카드 | 단추 자리 "도면 고치는 중"(빨강), 누르면 까닭 |
| 남의 공장(P3) | — | 판 뒤 "2공장 카드 4장 · 보기만" 묶음, 흐린 카드 + 상태 글만 |
| 이름 줄 | 이름 · 번호(글) | 이름 · 번호가 **작업 시트 링크**(줄 높이 보이는 44px) — W8 |
| 칸 단추 | 전체 도면 9 · 작업 필요 2 · 완료 4 | 파트 계정 "전체 도면 9 · **내가 맡은 것** 2 · **내가 끝낸 것** 4", 그 밖 "전체 도면 · 맡은 것 · 끝난 것" — 센 것을 그대로 말함(W2) |
| 확인 창 글 | "안 봄 → 작업 필요 · 김재단" | "아무도 안 맡음 → 김재단 맡음"(재단은 "안 봄 → 김재단 맡음") · 넘겨받기 "박재단 맡음 → 김재단 맡음" · 풀기 "김재단 맡음 → 아무도 안 맡음" |
| 진 경합 글 | 창이 닫히고 맨 위 상태 줄 | **창 안** 빨간 글 + 카드가 서버 모습으로, 단추 [닫기] |
| 마지막 카드 | — | 이어서 "제작 완료할까요?" 창(§4-3) |
| 아침 | — | 위 줄 아래 "어제부터 맡은 도면 2장 — 11/23 (월) 1장 · 지난 7일 1장" |
| 여러 파트(P2) | 파트 계정은 고르기 없음 | 판 머리에 내 파트만 고르기 [재단 · 엣지] |

- 상태 색(같은 자리 actbox, §8-9): 내가 맡음 `--fph-need-50` #c5c9ff · 남이 맡음 `--fph-taken-50` #eecbda · 끝 #a7f3d0 · 기본 #ccedff(모두 지금 값) · ⊙보류 #fed7aa(글자 #9a3412, 대비 5.4) · ⊙도면 고치는 중 #fca5a5(글자 #7f1d1d, 대비 5.28). 남의 공장 카드 바탕 연한 청록 #eefaf7 · 점선 #7fd6c6 · 칩 #cdf3ec/#0f6b63(흐린 것은 그림만, 글은 대비 그대로).
- JS: `foms-production-parts.js` 는 297줄(300 래칫) — 창 글 · 단추 그리기(`plan` · `ownerNote` · `listItem` · `renderAct`)를 새 `foms-production-parts-modal.js` 로 옮기고, 풀기 · 넘겨받기 · "제작 완료할까요?" · 아침 글을 새 `foms-production-parts-claim.js` 로. 둘 다 `defer` · 조각 재실행 한 번만 묶기(`window.__*_BOUND`, G4). `?v=` 핀 올림.

### 8-2. 날짜 탭 줄 · 장

| 곳 | 지금 | 바뀜 |
|---|---|---|
| 만들 것 줄 공정 4칸(`home_date_macros.html:24-26`) | 칸 넷 | 칸마다 아래 작은 글 — 맡은 사람(첫 이름 + 외 n) · "아무도" · 켜진 칸은 비움(§4-9) |
| 도면 칸(`:27`) | "도면 5장" | P3 섞인 주문 "우리 3장 / 2공장 2장"(두 줄), 남의 공장만 = 흐린 줄 + 칩 |
| 위 줄 날짜 글 | "11월 24일 (화) · 전체 39건" | P3 공장 계정 "11월 24일 (화) · 2공장 · 전체 39건" |
| 띠 숫자 | 만들 것 / 전체(주문) | 그대로(§16 질문 4) |
| 기다림 칸 · 제작 완료 칸 | — | 그대로 |

### 8-3. 작업 시트(`templates/production/sheet.html` · `production_sheet_view.py`)

| 곳 | 지금 | 바뀜 |
|---|---|---|
| [제작 완료] 회색 | "— 검수까지 끝나면 눌러요", 누르면 남은 공정 이름 | 카드 쓴 주문: "— 파트 일이 끝나면 눌러요", 누르면 "파트 일이 남았어요 — 재단 1장 · 검수 3장"(서버 글 `data-foms-sheet-complete-why`, JS 는 있으면 그 글 — 2줄 고침, 291 → 293) |
| [제작 완료] 파랑 조건 | 칸 규칙 | §4-2 |
| 공정 칸 | 켬 · 끔 | 카드로 켜진 칸 옆 작은 글 "카드로 끝냄"(누르면 §4-4 막힌 글) |
| 도면 목록 | 장 그림 | P3 2공장 장이 있으면 장마다 공장 칩 |

### 8-4. PC 보기(`home_pc_macros.html` · `pc.css`)

| 곳 | 지금 | 바뀜 |
|---|---|---|
| 공정 칸(`:47`) | 칸 + 아주 넓으면 "김재단 11/20" | 칸 아래 둘째 줄 맡은 사람(§4-9). 마우스 글에 맡은 때 |
| 도면 칸 | "도면 5장" | P3 "1공장 3장 · 2공장 2장"(PC 는 공장 보기 없이 둘 다) |
| 쓰기 단추 | [고치기] 켤 때만 | 그대로 |

### 8-5. 도면팀(P3)

| 곳 | 지금 | 바뀜 |
|---|---|---|
| 마법사 시트 탭(`renderTabs` · 새 `wizard-factory.js`, `wizard-as.js` 꼴) | 이름 · 복제 · 지우기 | 2공장 장만 탭 앞 청록 딱지 "2공장"(1공장은 딱지 없음 = 지금 모습) |
| 마법사 시트 도구 줄 | — | "만드는 곳 [1공장 | 2공장]" 두 칸 단추 — 누르면 API 로 바로 저장(마법사 저장과 따로) |
| 작업실 '현재 버전'(`workbench_detail_body.html:1535-1538`) | 그림 타일 | 목록 머리 "1공장 3장 · 2공장 2장" + 타일마다 [1공장 | 2공장] — 직접 올린 파일도 |
| 보낼 시트 칸(`:1812-1822`) | 시트 이름 · 체크 | 2공장 장 칩, 전달 창 한 줄 "보낼 도면 5장 — 1공장 3장 · 2공장 2장" |
| 생산 뒤 바꿈 | — | 확인 창 "생산에 이미 내려간 도면이에요. 2공장으로 옮기면 두 공장 화면에 '바뀜'이 떠요." [그대로] [옮기기] |

- 작업실 화면은 PC(도면팀). 새 JS 는 `static/js/drawing/workbench-sheet-factory.js`(300줄 안), 인라인 style 0(그 템플릿의 옛 style 은 건드리지 않음).

### 8-6. 관리자 사용자 화면(P2 · P3)

| 곳 | 지금 | 바뀜 |
|---|---|---|
| 추가 · 수정(`add_user.html:65-73` · `edit_user.html:80-89`) | "생산 파트 (선택)" 한 개 고르기 | "생산 파트 (여럿 골라도 돼요)" 체크 넷 [재단][엣지][조립][검수] + P3 "공장" [1공장][2공장] · 도움말 "생산팀일 때만 쓰여요. 다른 팀이면 저장할 때 비워져요."(지금 글) |
| 목록(`user_list.html:195`) | "생산팀 · 재단" | "생산팀 · 재단 · 엣지 · 2공장"(1공장은 안 적음) |
| 감사 | `production_part 미지정→assemble` | `생산 파트 재단 → 재단 · 엣지` · `공장 1공장 → 2공장`(한글 이름) |

### 8-7. 계약 회사 표시 이름(`flags.factory2`, P3 첫 커밋) — C7

**'2공장'이 화면에 나오는 곳 전부(바꿈 → "라홈시스템 계약")**

| 곳 | 지금 | 바뀜 |
|---|---|---|
| `templates/production/partials/tablet_kanban_body.html:103-107` 옛 칸반 거르개 | `공장 필터` · 전체 / 1공장 / 2공장 | `계약 회사` · 전체 / 라홈시스템 계약 / 그 밖 계약(값 1 · 2 그대로, `tablet-domain-sheets.js:508-544` 판정 그대로) |
| 같은 파일 `:247-251` 칸반 칩 | "2공장" · title "라홈시스템(2공장) 발주" | "라홈시스템 계약" · title "라홈시스템 계약 주문" |
| `foms/services/notifications/drawing_order_change.py:207` · `:903` 도면팀 바뀜 알림 | "2공장" | "라홈시스템 계약" |
| `foms/services/audit_message_display.py:443` 감사 경로 이름 | "라홈시스템(2공장)" | "라홈시스템 계약"(시험 `tests/domains/test_order_flag_permissions.py:153` 같이) |
| `static/js/foms/tablet-measure-form.js:662` 확인 글 · `:1091` 체크 이름 | "라홈시스템(2공장)" | "라홈시스템 계약" |

**'라홈시스템'만 쓰는 곳(2공장 말 없음 — 그대로, §16 질문 5)**: 주문 화면 체크(`templates/orders/partials/erp_order_tab.html:200-202` · `erp_order_tab_mobile.html:377-379`), 접수 마법사(`templates/orders/wizard/step3_schedule.html:61-65` · `static/js/foms/wizard.js:855`), 주문 대시보드 딱지(`templates/orders/partials/dashboard_grid.html:387-390`), 실측 대시보드(`templates/measurement/partials/dashboard_main.html:914`), 지방 대시보드 · 내보내기(`templates/measurement/regional_dashboard.html:373` · `static/js/measurement/regional-shipping-export.js:313`), 저장 확인 글(`static/js/orders/erp-order-shared.js:3345`), 채널 글머리 ★★(`channel_measure_message.py:268` · `erp-order-shared.js:5497`).

**주석 · 설명 글만(화면 아님 — 같은 커밋에서 "라홈시스템 계약"으로 맞춤)**: `erp_estimates.py:85` · `erp_orders_structured.py:1428` · `estimate_service.py:342` · `estimate_defaults.py:24`, `:79`, `:85` · `order_flag_permissions.py:1`, `:35`, `:59` · `structured_diff.py:88` · `share_estimate_body.html:16`, `:39` · `static/css/foundation/foms-tablet-production-kanban.css:418`, `:515`.

- 칸 이름 `flags.factory2` · 뜻 · 권한 · 견적 동작은 그대로. 장의 공장은 이 값에서 **만들지 않는다**(C7).

### 8-8. 목업 · 그림

목업 2판 `docs/design/mockups/production-self-claim-factory2-v2.html` — 위 표마다 "지금 → 바뀜" 그림과 사장님 결정 한 줄. 그림 `scratchpad/sf2/01_…png`.

### 8-9. 색 잰 값(CIEDE2000 · Machado 2009 적록 색약)

| 쌍(같은 자리 actbox) | ΔE | 색약(1형 / 2형) |
|---|---|---|
| 보류 / 도면 고치는 중 | 23.2 | 14.4 / 9.2 |
| 보류 / 끝 | 29.2 | 7.4 / 11.9 |
| 보류 / 남이 맡음 | 23.9 | 22.3 / 19.5 |
| 도면 고치는 중 / 남이 맡음 | 14.3 | 14.0 / 14.9 |
| 도면 고치는 중 / 끝 | 49.6 | 14.0 / 9.4 |
| 도면 고치는 중 / 흰 바탕 | 27.2 | 19.0 / 18.3 |
| 어제 글 바탕 / 남이 맡음 · 내가 맡음 | 20.7 · 29.9 | 16.8 / 14.0 · 29.6 / 31.4 |

처음 고른 '도면 고치는 중' 올리브(#eeebb2, 지금 기다림 색)는 보류 호박과 색약 1.9 로 떨어져 버렸다. 지금 쌍(맡음 · 끝 · 기본)은 D51 · D52 값 그대로.

## 9. 알림 · 바뀜

- **새 알림 없음.** 장의 공장이 바뀌면 이벤트 `DRAWING_SHEET_FACTORY_CHANGED`(payload `key` · `sheet_id` · `sheet_no` · `from` · `to`, `created_by_user_id`)를 남기고, 생산 변경 감지 목록(`production_change_alerts.py:65-71`)에 이 종류를 더한다 → 주문 '바뀜' 테두리 · 바뀐 것 탭 장 · 줄 '바뀜' 글 "공장 바뀜 도면 2/5 1공장 → 2공장 · 도면 장미래 · 2시간 전" · [확인했어요]가 지금 길 그대로 두 공장 모두에 뜬다. 같은 목록이 조각 304 지문이라 받아 오기도 바로 안다. 이미 읽는 이벤트 쿼리에 종류만 더함 — 쿼리 0.
- 생산 진입 전(도면 · 컨펌 단계) 바꾼 것은 D22 바닥선으로 안 뜬다(내려오기 전이라 맞다).
- 넘겨받기 · 풀기 알림(다음 사람에게)은 없다 — 30초 받아 오기가 카드를 바꾼다(§17).

## 10. 쿼리 예산 · 성능

| 응답 | 지금(계약) | 바뀐 뒤 | 어떻게 |
|---|---|---|---|
| 날짜 탭(파트 없는 계정) | 9 실측 · 상한 11 | **10** · 11 | 맡은 사람 한 줄 = 고른 날 장 주문 표시 줄 읽기 1(좁은 칸 `order_id, part, state, picked_by_name, picked_at`) |
| 날짜 탭(파트 계정 · 태블릿) | 10 · 12 | **11** · 12 | 판이 이미 읽은 줄을 한 줄에 다시 씀(0) + 아침 글 1 |
| 날 조각(파트 없는 / 파트) | 6 / 7 · 9 | 7 / 7 · 9 | 위와 같음, 아침 글은 조각에 없음 |
| PC 날짜 탭 | ≤ 11 | +1 | **구현 첫 일: 지금 수를 잰다.** 11 을 넘기면 멈추고 묻는다(상한을 그냥 올리지 않음) |
| 파트 판 · 30초 받아 오기 | +1 · 1 | 같음 | 보류 · 도면 고치는 중 · 공장 · 손 칸 = 이미 읽은 JSON |
| 표시 쓰기 한 장 | 상한 7 | 맡기 +1(회차 찾기) | 첫 맡기(제작 시작이 같이 되는 한 번)만 +3(회차 쓰기 · 이벤트 · 감사) — 따로 상한(실측 + 30%) |
| 제작 완료 · 공정 API · 일반 단계 쓰기 | 지금 | +1 | 카드 썼나 1(일괄도 `IN` 1) |
| 작업 시트 | 지금 | +1 | 그 주문 표시 줄(카드 썼나 · 남은 장 수) |
| 장 공장 API(P3) | — | 잠금 1 · 쓰기 · 이벤트 1 | — |
| 여러 파트 · 계정 공장(P2 · P3) | — | 0 | 사용자 행 칸 |

- N+1 없음: 맡은 사람은 장 하나의 주문 id 들로 한 번(`in_`), 주문 · 카드 수와 무관. `test_production_home_query_count.py` 씨앗에 맡음 줄 · 2공장 장을 더해 4 → 12건에도 그대로임을 단언.
- 표시 줄 읽기는 모두 유일 제약 앞머리 `order_id` 를 탄다 — 운영 EXPLAIN(읽기만)으로 Seq Scan 없음 확인. 아침 글의 `picked_by_user_id` 는 `order_id IN` 뒤 거르기라 새 색인이 필요 없다.
- 행 JSON 을 늘리지 않는다(30초 받아 오기는 주문 JSON 을 안 읽는다 — JSONB TOAST 함정).

## 11. 단계별 일 (파일 · 크기)

**P1 맡기 고침(마이그레이션 없음, 큼: 파일 약 22)**
1. `steps.py`(칸 `via` · `production_complete_block_body(sd, *, cards_used, parts_left)`) · 새 `foms/services/production/part_cards.py`(`orders_with_cards` · `parts_left`) · 네 부르는 곳(`orders.py` · `stage_override.py` · `production_sheet_view.py`) + 시험.
2. `part_mark_rules.py`(release · takeover · `seen_by` · 글) · `part_steps_sync.py`(손 칸 안 건드림) · 쓰기 몸통 새 모듈(막음 넷 · 첫 맡기 시작 · `order_ready`) · 새 `start_run.py`(제작 시작 옮김, 자리 고정 시험) · 정책 설명.
3. `part_board.py`(카드 상태 · 막음 · 어제 · 칸 이름 · 링크) · 새 `part_holders.py` · `production_home_read_model.py` 한 줄 연결 · `home.py`(아침 글 쿼리 · 파트 없는 날짜 탭 표시 줄 읽기).
4. 템플릿 `home_parts.html` · `home_parts_overlays.html` · `home_date_macros.html` · `home_pc_macros.html` · `sheet.html` · CSS `parts.css` · `home.css` · `pc.css` · `sheet.css` 핀 · JS 새 둘 + `foms-production-parts.js` 줄이기 + `foms-production-sheet-page.js` 2줄.
5. 쿼리 시험 · 바뀐 파일 시험 → smoke → deploy → 스테이징(claude_master, `CLAUDE-TEST-` 주문) → 사장님 확인 → 승격.

**P2 여러 파트(마이그레이션 1 + 한 판 뒤 1, 중간: 파일 약 14)**: `models.py` · `migrations/versions/prodparts_01_*.py` · `part_constants.py` · `part_access.py`(대신 모드) · `part_board.py`(고르기) · `part_marks.py` 문 · `home.py` · `foms/web/auth/routes.py` · 템플릿 셋 · 정책 설명 · 시험 씨앗 11곳 → 운영 1주 뒤 `prodparts_02_drop_production_part`.

**P3 2공장(마이그레이션 1, 큼: 파일 약 24)**: ① 이름 바꾸기 커밋(§8-7, 혼자 내보내도 됨) ② `users.production_factory` 마이그레이션 · 관리자 화면 ③ `sd.drawing_factory` 서비스 `foms/services/orders/drawing_factory.py` + API `foms/api/drawing/erp_orders_sheet_factory.py` + 등록 · 매니페스트 · 마법사 GET 응답 ④ `wizard-factory.js` · 작업실 타일 · 전달 창 한 줄 ⑤ 생산 쪽: `part_access`(공장 문) · `part_board`(뒤 묶음 · 숫자) · `production_home_read_model`(도면 칸 · 정렬) · 날짜 글 · 작업 시트 칩 · PC ⑥ 변경 감지 종류 · 바뀐 것 글.

## 12. 시험

- **P1**: 완료 규칙 표 §4-2 전부(카드 안 씀 3줄 · 카드 씀 2줄 · 도면 0장 · 새 장 · 맡았다 푼 줄만) — 네 부르는 곳이 같은 답(제작 완료 API 409 · 일반 단계 쓰기 409 · 공정 응답 · 시트 단추). 점검 B1 재현(재단 1장 끝 · 엣지 1 · 조립 2 맡음 → 완료 409). 마지막 카드 `order_ready`(어느 파트든 · 보류면 없음 · 관리자 대신 끝내기). 전이 표 §4-5 전부 + 경합(같은 장 두 사람 넘겨받기 · 넘겨받는 사이 끝냄 · 풀기와 넘겨받기) + 멱등. 막음 넷 × 쓰기 다섯(풀기만 됨). 손 칸 §4-4 세 줄 + 옛 칸(`via` 없음) + 카드 칸 끄기 409 + 도면 전달 동기화가 손 칸을 안 끔. 첫 맡기 = 회차 1개(두 사람 동시 첫 맡기 → 회차 1, PG 레인) · 풀어도 회차 그대로 · `PRODUCTION_STARTED.via`. 어제 글 KST 경계(시험이 시계를 쥠 — CI 는 UTC). 아침 글 셈. 맡은 사람 한 줄(외 n · 아무도 · 켜진 칸 비움 · 도면 없음 줄 없음). 쿼리 §10. 템플릿 꼴(`test_p1_mockup_*` 구조 시험 꼴) · 인라인 style 래칫 · CSS 핀 · 새 글자 `calc` · JS 300 래칫 · G4.
- **P2**: 정규화(겹침 · 순서 · 모르는 값 · 빈 목록 = NULL) · 마이그레이션 왕복(PG CHECK · downgrade 가 첫 파트로) · 두 칸 같이 쓰기 · 모드 다섯 · 권한 표 §5 전부(서버) · 여러 파트 판 고르기(주소 `part` 가 내 것 아니면 첫 파트) · 감사 글.
- **P3**: `sheet_factory` 표 §4-11(다시 보내기 · 한 장 바꾸기 · 확정 · 전달 취소 · 품목 취소 · 직접 올림 · 복제) · API 권한 · 멱등 · 버전 +1 · 이벤트 · 열린 마법사 자동 저장 뒤에도 값 유지(회귀) · 공장 문(남의 공장 403, 관리자 됨, 옮긴 장 맡은 사람 풀기 됨) · 판 뒤 묶음 · 숫자 · 섞인 주문 완료 · 바뀜 감지 · 이름 바꾸기 글 시험.

## 13. 내보내기 · 확인 · 되돌리기

- **내보내기 전 읽기(운영, 사용자 요청 1회 · 읽기만)**: 생산 단계 주문 중 켜진 공정 칸 수(`via` 없는 옛 칸 — §4-4 가 '손'으로 볼 칸) · 표시 줄 NEED 수 · 파트 계정 수. 0 에 가까우면 그대로.
- P1 · P2 · P3 마다: 로컬 준비물 서버(가짜 이름, 26건 꼴) + Playwright 태블릿 1176 × 626 80% · PC 1440 → 스테이징 claude_master(쓰기는 `CLAUDE-TEST-` 주문만) → 사장님 확인 → 자기 커밋 승격.
- 되돌리기: P1 = 커밋 revert(JSON 칸 `via` 는 남아도 옛 코드가 무시). P2 = revert → 옛 코드는 `production_part`(첫 파트)를 읽음, 마이그레이션 downgrade 는 P2b 전까지만. P3 = revert → `drawing_factory` 칸 · `production_factory` 칸은 남아도 무시됨(지우지 않음).

## 14. 위험 · 막는 법

| 위험 | 막는 법 |
|---|---|
| 카드를 실수로 맡았다 둔 주문이 '칸 안 쓴 주문' 길을 잃음 | 맡았다 푼 줄(NONE)은 '카드 씀'이 아님(§4-1). 남으면 관리자 뚫기 |
| 옛 칸(`via` 없음)을 손 칸으로 봐 카드가 잠김 | 운영 수를 먼저 셈(§13). 작업 시트에서 끄면 풀림 |
| 1공장 관리자가 손으로 켠 칸이 2공장 장까지 '끝'으로 | 칸은 주문에 하나(C8 과 같은 까닭) — 화면 글 "작업 시트"로 어디서 켰는지 보임. 필요하면 다음 판에서 공장마다 칸 |
| 첫 맡기 = 제작 시작이 실수 맡기에도 걸림 | 풀어도 시작은 남음 — [제작 취소] 길 그대로. 시작은 화면에 '재단 중'으로 바로 보임 |
| 직접 올린 2공장 파일을 새로 올리면 1공장으로 | 작업실 목록 · 전달 창에 공장이 보임, 바뀐 것 글. 시트 없는 파일만의 일 |
| 2공장 화면에 1공장 줄이 대부분(흐림) | 남의 공장 줄은 만들 것 묶음 맨 뒤 · 흐림. 띠 숫자는 §16 질문 4 |
| 열린 마법사가 공장 값을 덮음 | 공장은 마법사 상태 밖(§6-3) — 회귀 시험 |
| 파일 래칫(parts.js 297 · part_marks.py 455) | 새 모듈로 나눔(§8-1 · §7) |
| 날짜 탭 쿼리 상한에 닿음(파트 계정 11 / 12) | 아침 글 · 맡은 사람 외에 더하지 않음, 4 → 12건 시험 |
| 넘겨받기를 몰래 쓰는 사람 | 이력 · 감사에 "넘겨받음 (김재단 → 박재단)" |

## 15. 사장님 결정과 지금 코드 · 옛 결정이 부딪히는 곳

1. **B5 ↔ 카드 동기화(§15.5 "카드로 일한 파트는 카드가 칸을 정한다")**: 지금은 맡기만 해도 손 칸을 끈다(`part_steps_sync.py:69-86`). → 칸에 `via` 를 더해 손 칸은 동기화가 안 건드린다(§4-4). 옛 칸은 손으로 본다.
2. **B1 ↔ 2026-11-21 "공정 칸을 쓴 주문만 막기"**: 카드를 쓴 주문은 칸을 안 켜도 막는다(§4-2). 카드를 안 쓴 주문의 예외는 그대로 — 운영 습관(칸 · 카드 안 씀)을 막지 않는다.
3. **B1 "마지막 검수 장" ↔ D46(순서 안 막음)**: 마지막에 끝나는 장이 검수가 아닐 수 있다 → 마지막 남은 장(어느 파트든)에 묻는다(§4-3). **사장님 확인 바람**(다르면 "검수 장일 때만 묻기"로 한 줄 고침).
4. **B5 "다시 하려면 끄면 열림" ↔ 카드로 켠 칸**: 카드로 끝낸 칸을 작업 시트에서 끄면 다음 쓰기 때 다시 켜진다 → 그 칸은 끄기를 막고 카드에서 되돌리게(§4-4). 사장님 예(손 칸)와는 안 부딪힘.
5. **B2 · B6 ↔ D55 ~ D57 설계서 승인 때 추천안("넘겨받기 없음, 제작 시작 자동 안 함", 원장 §28 `:521`)**: 이번 답이 옛 추천안을 바꾼다 — 승인되면 DECISIONS 에 바뀜으로 적는다.
6. **B7 ↔ D55("나머지 직원은 읽기 전용")**: 파트 없는 생산팀만 읽기 전용에서 '대신'으로. CS · 영업 · 도면 등은 그대로 읽기 전용.
7. **B9 ↔ D47("계정 하나에 파트 하나")**: 여러 파트로 바꾼다(§6-1).
8. **C6 "남의 공장은 못 누름" ↔ B7 "어느 파트든 대신"**: 대신은 파트를 넘는 것, 공장은 넘지 않는 것으로 읽었다(관리자만 두 공장). **사장님 확인 바람**(§16 질문 2).
9. **C3 "생산 뒤에도 바꿈" ↔ D56("도면 바뀜 = 새 판 안 봄부터")**: 공장만 바꾸는 것은 새 판이 아니다 — 도면 key 를 안 바꾸고 표시 줄을 지키도록 따로 API(§6-3). 다시 보내기와 섞지 않는다.
10. **C2 장 단위 ↔ 주문 단위로 남는 것(공정 4칸 · 단계 · 보류 · 불량 · 제작 시작/완료 · 마감)**: 섞인 주문의 '재단 중'은 두 공장 합친 모습이다. C5 · C8 과 맞는다.

## 16. 사장님께 여쭐 것 (추천값으로 먼저 시작)

1. **도면 장을 다른 공장으로 옮겼는데 이미 맡거나 끝낸 표시가 있으면?** → 추천: **그대로 둔다**(끝낸 파트는 끝, 맡음은 새 공장 사람이 넘겨받거나 맡은 사람이 풂). 다른 안: 옮길 때 맡음만 저절로 풀기 / 모두 처음부터.
2. **한 사람이 두 공장에서 일하나요? 파트 없는 생산팀(반장 등)은 두 공장 카드를 다 누르나요?** → 추천: **계정마다 한 공장**, 옮기면 관리자가 바꿈. 두 공장을 다 누르는 사람은 관리자뿐.
3. **관리자는 두 공장 카드를 한 화면에 같이 보나요?** → 추천: 판은 **공장을 골라 하나씩**(위 [1공장 | 2공장]), 날짜 탭 · PC 줄은 두 공장 합쳐 "1공장 3장 · 2공장 2장".
4. **파트 계정 날짜 띠 숫자 '만들 것 / 전체'를 '내 파트 남은 장'으로 바꿀까요?** → 추천: **지금 그대로**(주문 수, 반장과 같은 띠). 아침 글 · 카드 칸 숫자가 내 일을 말한다.
5. **'라홈시스템' 이름만 쓰는 곳(주문 화면 체크 · 대시보드 딱지 등)도 '라홈시스템 계약'으로 맞출까요?** → 추천: **'2공장'이 보이는 다섯 곳만** 바꾼다(§8-7). 딱지가 길어지면 표 칸이 밀린다(지방 내보내기 딱지 사고 2026-08-07).
6. **도면 마감과 '도면 x/n'은 주문 하나로 셉니다(총괄이 정함).** 공장마다 따로 보고 싶으시면 말씀해 주세요. → 추천: **주문 하나로**(단계 · 마감이 주문에 하나).
7. **섞인 주문에서 마지막 장을 2공장이 끝내면, "제작 완료할까요?"를 2공장 사람에게 묻나요?** → 추천: **끝낸 사람에게 그대로 묻는다**(1공장으로 보냈는지는 그 사람이 앎). 다른 안: 1공장 사람에게만 묻고 2공장은 "1공장으로 보내 주세요" 한 줄.

## 17. 하지 않는 것

- 반장이 나눠 주는 화면 · 새 '누가 무엇을' 화면(B8 은 날짜 탭 한 줄).
- 밤 넘긴 맡음 저절로 풀기 · 파트 순서 막기(D46).
- 넘겨받기 · 풀기 · 제작 완료 알림(벨 · 폰 · 채널톡) — 30초 받아 오기로 충분.
- 공장마다 공정 칸 · 단계 · 마감 · 도면 x/n · 보류 · 불량(C8 — 주문 하나).
- `flags.factory2` 에서 장의 공장 만들기 · 그 값 지우기 · 견적 동작 바꾸기(C7).
- 2공장 전용 다른 공정 · 다른 화면(C4 — 같은 방식).
- AS 도면의 공장(생산 카드 없음) · 협력사 포털 화면의 공장 표시.
- 띠 숫자 바꾸기(§16 질문 4 답 전까지) · PC 판 꼴 바꾸기(사장님 "추후 통보").
- 공정 칸 기록을 실제 시각과 어긋나게 하는 "남은 공정 한 번에 끝내기"(2026-11-22 결정 그대로).
- 금액(D7) · 새 패키지 · 새 서비스(Railway) · 새 백그라운드 일.
