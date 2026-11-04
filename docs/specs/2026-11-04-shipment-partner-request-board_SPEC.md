# 출고 화면 협력사 희망 시공일 — 2주 판에서 바로 시공일 정하기 SPEC (2026-11-04 사용자 선택 · 승인)

등급: 코어 변경(주문 일정 쓰기 API · 팀 권한 · 협력사 알림이 따라 나감) — 아래 결정 1~5 를 받은 답을 승인으로 본다.
선행: `docs/specs/2026-10-19-partner-foms-mode_SPEC.md` §18(희망 시공일) · 목업 `docs/design/mockups/shipment-partner-pending-confirm.html#E`(로컬 파일, 커밋 안 함 — 고객 이름은 지어낸 값).

## 0. 사용자 결정 (2026-11-04)

1. **목업 E안(2주 판)으로 간다.** 지금 칸 자리 하나만 바꾸고, 판에서 주문을 누르거나 다른 날로 끌어 놓아 시공일을 정한다.
2. **출고팀도 시공일을 정한다 — 판에서도, 주문 화면(erporder)에서도.** 지금은 CS 가 이 일을 하지만 나중에는 출고팀이 맡는다. 출고팀이 바꿀 수 있는 것은 시공일 · 시공시간뿐이다(다른 칸은 그대로 CS · 영업).
3. **되돌리기를 넣는다.** 확정 뒤 알림에 [되돌리기]를 몇 초 둔다 — 그 사이에는 저장도 협력사 알림도 나가지 않는다.
4. **판 머리를 접을 수 있게 한다.** 접으면 머리 한 줄만 남는다.
5. **누가 언제 무엇을 어떻게 바꿨는지 판에서 보이게 한다.** 판 아래 "최근 정한 기록".
6. **판 · 출고팀 주문 화면을 한 번에 만든다**(나눠 올리지 않는다).
7. **출고팀 주문 화면에서도 금액(견적 · 입금)은 그대로 보인다**(사용자 11-04).
8. **판은 낮은 한 줄(목업 E-2)로 줄인다**(사용자 11-04, 운영 화면을 보고 "자리를 너무 많이 차지"). 14칸을 한 줄에, 칸 안에는 이름만(번호 · 제품 · 자수 · 시간은 마우스를 올리면), 남은 자수는 정수(모자라면 "넘침 N"), 머리 줄 어디를 눌러도 접고 편다, 기록은 마지막 1줄 + [N건 보기]. 자수 0 인 주문(폭 숫자 없음)은 "자수 모름".

## 1. 지금 코드의 사실

- 칸: `templates/shipment/partials/dashboard_main.html:218-233`. 숫자 하나용 타일 틀 `erp-pro-alert`(`static/css/foundation/erp-pro/03-card-pipeline.css:175`, 가로 flex · space-between)에 제목 · 설명 · 버튼 26개를 넣어서, 제목이 "협력사 희 / 망 시공일"처럼 세로로 끊긴다. 버튼마다 "(라운즈)" · "희망"이 되풀이되고, 날짜 없는 건은 협력사가 쓴 시간 칸 글("사공일 미정")이 그대로 나온다.
- 자료: `shipment_pending_requests`(`foms/services/partners/schedule_request.py:177`) — 협력사 주문 중 우리 시공일 없는 시공 전 주문을 최근 200건 훑어 희망일 순으로 30건에서 자른다. 번호 · 고객 · 회사 · 희망일 · 시간 글만 읽는다(자수 · 주소 없음).
- 희망일은 이미 그날 시공 건수 · 자수 · 그날 목록에 들어간다(`foms/web/shipment/dashboard.py:488-503`, 사용자 결정 10-28 · 10-29). 패널 범위는 오늘~14일 뒤(`dashboard.py:445-446`), 날짜별 남은 자수 · 인원은 `remaining_panel_dates`(`dashboard.py:571`).
- 시공일 정본은 `structured_data.schedule.construction.{date, time}`. 주문 화면 시공시간 = 오전 · 오후 · 종일 · 직접 입력(`templates/orders/partials/erp_order_tab.html:371-381`). 평면 `erp_construction_date` 는 `sync_erp_flat_columns`(`foms/services/erp_sync_columns.py:125`)가 맞추고, 확정 대기 판정은 이 평면 칸이 비었는가다(`schedule_request.py` `_unconfirmed_conds`).
- 시공일을 쓰면 전역 before_flush 훅(`foms/services/order_date_sync.py`)이 일정 줄 · `CONSTRUCTION_DATE_CHANGED` 이벤트 · 대시보드 캐시 비우기 · 협력사 직원 "시공일 안내" 푸시(`foms/services/partners/notify_listeners.py`, 처음 정할 때도 보낸다)를 맡는다.
- 쓰는 쪽이 직접 하는 일은 도면팀 알림(`apply_drawing_order_change_alert` → 커밋 뒤 `finalize_drawing_order_change_alert`) · 생산팀 알림(`apply_production_change_alert` → `finalize_production_change_alert`) · 변경 원장(`record_field_changes`) · 감사(`log_access`)다. 지금 대시보드 칸 쓰기(`foms/api/orders/field_update.py:787-1000`, `scheduled_date`)가 이 순서로 한다.
- 시공일을 쓸 수 있는 사람 = `can_edit_erp`(관리자 · CS · 영업, `foms/services/erp_permissions.py:361`). 출고 화면 쓰기(`/api/erp/shipment/update`)도 같은 문(`erp_edit_required`)이다. 출고팀(`SHIPMENT`)은 ERP 주문 화면을 아예 못 연다(`foms/web/orders/edit.py:255` 에서 돌려보낸다).
- 변경 원장 `OrderFieldChange`(`models.py:1026`)에 저장마다 경로 · 이전값 · 새값 · 바꾼 사람 · 시각이 남고, `(path_template, created_at)` 색인이 있다. ERP 폼 저장 · 대시보드 칸 쓰기 모두 여기에 쓴다.
- 변경 사유 창은 빈칸 → 값(처음 입력)이면 묻지 않는다(`foms/services/orders/change_reason.py:217`).
- PC 표면 `.erp-shipment-desktop-shell` 은 모바일 v2 에서 숨는다(`static/css/components/foms-shipment-mobile.css:603`) — 이 칸도 PC 전용이다.

## 2. 동작

### 2.1 화면 (지금 칸 자리 하나만 바꾼다)

- 틀: 왼쪽 "날짜별 시공" 카드와 같은 카드(`card border-0 shadow-sm` · 머리 `card-header bg-white py-1 px-2`). 머리 = "협력사 희망 시공일 · 확정 대기 N" + 오른쪽 안내 한 줄 "주문을 누르거나 다른 날로 끌어 놓으면 시공일을 정해요". 표식 `data-partner-pending-requests` 는 유지한다(기존 시험이 본다).
- 판: 내일부터 14일, 7칸 × 2줄. 칸 머리 = 날짜(요일) · "내일" · "남은 N"(자수, 15 미만이면 빨강) · 막대(쓴 자수 ÷ 전체). 주말 · 휴일 칸은 왼쪽 날짜 목록과 같은 노란 바탕. 숫자는 왼쪽 "날짜별 잔여 시공"과 같은 `remaining_panel_dates` 값이다 — 새 집계를 만들지 않는다.
- 칸 안 = 그날 희망 주문 단추 "#번호 이름 N자 [시간]".
- 판 아래 한 줄 = 판 밖 건(지난 희망일 · 오늘 · 14일 뒤 · 날짜 없음): "MM-DD #번호 이름", 날짜 없음은 날짜 없이. 협력사 시간 칸 글은 단추에 쓰지 않고 정하기 창에만 보인다.
- 협력사가 한 곳이면 회사 이름은 머리 안내에서 한 번만, 여러 곳이면 단추에 "(회사)"를 붙인다.
- 시공일을 쓸 수 없는 사람(시공팀 등)에게는 단추가 주문 화면 링크일 뿐이고 끌기가 없다.
- **접기:** 머리 오른쪽 [접기 ▴] / [펼치기 ▾]. 접으면 머리 한 줄("협력사 희망 시공일 · 확정 대기 N" + "가장 빠른 날 MM-DD(요일) 내일 N건")만 남는다. 접힘 상태는 브라우저에 사람마다 기억한다(`localStorage`, 서버 저장 없음). 새 희망이 들어와도 저절로 펼치지 않는다 — 숫자로 본다.
- **최근 정한 기록:** 판 아래 한 칸. 협력사 주문의 시공일이 처음 정해지거나 바뀐 것을 최근 7일 · 새것 먼저 · 6줄(넘으면 [더 보기]). 한 줄 = "MM-DD HH:MM #번호 이름 희망 MM-DD(요일) → **MM-DD(요일) 시간** [옮김] · 바꾼 사람(팀)". 이미 정해진 날을 다시 바꾼 것은 "MM-DD → MM-DD 바뀜". 판에서 정한 것 · 주문 화면에서 정한 것을 같이 보인다. 이름을 누르면 주문 화면.
- 확정 대기가 0건이면 판은 그리지 않고, 기록이 있으면 접힌 머리 + 기록만 보인다.

### 2.2 정하기 창

- 단추를 누르면 그 아래 작은 창이 뜬다.
  - 제목 "#번호 이름 시공일 정하기", 한 줄 "제품 N자 · 현장 주소 앞부분 · 희망 MM-DD(요일) 시간".
  - 날짜 칸: 희망일이 미리 들어간다. 판 칸으로 끌어 놓아 열었으면 그 칸 날짜.
  - 시간: 오전 · 오후 · 종일 (희망 시간이 그중 하나면 미리 켜짐, 다시 누르면 꺼짐). 직접 입력은 주문 화면에서.
  - 남은 자수 한 줄: "MM-DD 남은 자수 N"(이 주문을 옮겨 넣은 뒤 값). 15 미만이면 "거의 찼어요", 0 미만이면 "자수가 넘쳐요", 주말 · 휴일이면 "토요일이에요"처럼 붙인다.
  - "확정하면 {회사}에 시공일 안내가 가요." · [닫기] [확정].
- 끌어 놓기만으로는 저장하지 않는다 — 항상 이 창의 [확정]으로 저장한다.
- 자수가 넘쳐도 막지 않는다(경고만, 출고 담당 판단).
- 주문에 시공시간이 이미 있으면 시간 칸은 그 값을 보여 주기만 하고 바꾸지 않는다(바꾸면 사유 창 대상이 된다 — 그런 수정은 주문 화면에서).
- **되돌리기 = 늦게 보내기.** [확정]을 누르면 창이 닫히고 알림 "#번호 이름 시공일을 MM-DD(요일) 오전으로 정해요 · 5초 뒤 저장 [되돌리기]"가 뜬다. 단추는 판에서 흐리게 "저장 중"으로 남는다. 5초 동안은 서버에 아무것도 보내지 않는다 — [되돌리기]를 누르면 그대로 끝(저장 · 협력사 알림 없음). 5초가 지나면 저장 API 를 부른다. 그 사이 화면을 떠나면 `fetch(..., {keepalive: true})` 로 바로 보낸다(되돌리기 기회만 없어진다).
  - 이유: 저장 뒤에는 협력사 푸시가 커밋 직후 나가서 거둘 수 없다. 서버에서 알림만 미루면 협력사 알림함 줄이 먼저 생기고 작업자가 하나 더 필요하다.
  - 저장 뒤 잘못 정했음을 알면 주문 화면에서 바꾼다(협력사에 "바뀜" 안내가 간다).

### 2.3 저장 API

- `POST /api/erp/shipment/partner-requests/<order_id>/confirm` `{date, time}` — 새 파일 `foms/api/shipment/partner_request.py`, `erp_shipment_bp` 에 붙이고 `foms/api/shipment/__init__.py` 에서 import(기존 change_ack 와 같은 방식). 응답 `{success, data, error}`.
- 문: `login_required` · 새 술어 `can_edit_construction_schedule(user)` = `can_edit_erp(user)` 또는 팀 `SHIPMENT`(STAFF 이상) — `foms/services/erp_permissions.py` 에 둔다. 판 · 주문 화면 시공일 칸 · 이 API 가 같은 술어를 본다.
- 서비스 `confirm_partner_request(db, user, order_id, date, time)` — `foms/services/partners/schedule_request.py` 에 둔다(확정 대기 판정과 같은 모듈). 순서:
  1. `lock_order_row`(`foms/services/orders/revision.py:241`)로 주문 줄을 잠근다. 없거나 삭제 → 404.
  2. 협력사 주문이 아니면 404. 이미 시공일이 있거나 시공이 시작된 단계(`request_open` 거짓)면 409 "다른 사람이 먼저 시공일을 정했어요."
  3. `date` 는 `clean_date` 를 지나야 하고 비면 400. 오늘보다 앞이면 400 "지난 날짜예요." `time` 은 "" · 오전 · 오후 · 종일만, 아니면 400.
  4. `copy.deepcopy(sd)` → `schedule.construction.date = date`, `time` 은 지금 비어 있을 때만 넣는다 → 재대입 → `flag_modified` → `sync_erp_flat_columns` → `structured_updated_at`.
  5. 도면팀 · 생산팀 알림 apply → `record_field_changes`(change_set) → `log_access`(`ORDER_FIELD_UPDATED`, detail 에 `source: shipment_partner_board`) → 커밋 → 두 알림 finalize. 대시보드 칸 쓰기와 같은 순서 · 같은 함수다.
  6. 응답 `data = {order_id, date, time, moved}`(`moved` = 희망일과 다른 날로 정했는가).
- 협력사 푸시 · 일정 줄 · 이벤트 · 캐시 비우기는 전역 훅이 한다 — 여기서 또 부르지 않는다.
- 새 structured_data 쓰기 자리이므로 쓰기 목록(REV-99 인벤토리)을 커밋 전에 새로 맞춘다.

### 2.3-b 주문 화면 시공일 (출고팀)

- 시공일 쓰기를 판 전용이 아닌 일반 서비스로 둔다: `set_construction_schedule(db, user, order_id, date, time, reason=None)`(`foms/services/orders/construction_schedule.py`). 2.3 의 협력사 확정은 이 함수에 "확정 대기여야 함 · 처음 정함" 조건을 얹은 것이다. 이미 있는 날을 바꾸면 `is_reason_required` 로 사유를 판정해, 필요하면 사유 없이 409 `REASON_REQUIRED` → 화면은 기존 사유 시트(`foms-reason-sheet.js`)를 띄워 다시 보낸다.
- API: `POST /api/orders/<id>/construction-schedule` `{date, time, reason_code?, reason_note?}`(`foms/api/orders/`).
- 출고팀이 ERP 주문 화면을 열 수 있게 한다(`edit.py:255` 문을 `can_edit_construction_schedule` 로). 출고팀에게는 화면 전체가 읽기 모드이고 시공일 · 시공시간 칸만 열린다. 이 두 칸은 출고팀일 때 폼 전체 저장(PUT, CS · 영업 전용 그대로)이 아니라 위 API 로 저장한다(칸 옆 [시공일 저장]).
- 주문 화면에는 읽기 모드가 없다(2026-11-04 확인 — 템플릿 · JS 에 read-only 분기 0). 출고팀용 읽기 모드를 새로 만든다. **사용자 결정(11-04): 판과 한 번에 같이 만들어 올린다.** 읽기 모드 세부(무엇을 잠그고 무엇을 숨기나)는 구현 첫 단계에 화면을 재서 §2.3-c 로 적는다.

### 2.4 확정 뒤 화면

- 저장되면 알림 "#번호 이름 시공일을 MM-DD(요일) 오전으로 정했어요. {회사}에 알림이 갔어요." 뒤 1.5초에 화면을 새로 읽는다 — 왼쪽 목록 · 잔여 표 · 그날 표 · 판 · 기록이 모두 서버 값으로 맞춰진다(구현 2026-11-04: 같은 날 확정도 새로 읽는 쪽이 단순하고 기록 칸이 바로 보인다).
- 409 → "다른 사람이 먼저 시공일을 정했어요." 알림 뒤 새로 읽는다.

### 2.3-c 출고팀 주문 화면 (구현 2026-11-04)

- `foms/web/orders/edit.py` — ERP 주문을 `can_edit_erp` 가 아닌 사람이 열면, `can_edit_construction_schedule` 이고 GET 일 때만 연다(`erp_construction_only`). 폼 POST 는 그대로 돌려보낸다.
- `#erp-order-config[data-erp-construction-only]` → `static/js/orders/erp-construction-only.js` 가 화면 안 입력 · 단추를 모두 잠그고(뒤에 그려지는 품목 칸도 MutationObserver 로) 탭 · 접기만 둔다. [저장] 단추는 숨긴다.
- 시공일 칸 아래 [시공일 저장] + 안내 "출고팀은 시공일 · 시공시간만 바꿀 수 있어요. 다른 칸은 CS · 영업팀이 고쳐요." 하루만(여러 날은 CS 에), 시간은 오전 · 오후 · 종일(직접 입력 옵션은 숨김). 바꿔서 사유가 필요하면 응답의 `change_reason_required` 로 기존 사유 창을 띄운다.
- 서버 쪽 사실(조사 2026-11-04): 첨부 · 퀘스트 · 단계 강제 · 공유 · 알림톡 · 채널 푸시 쓰기는 `STAFF_MUTATION` 이라 출고팀 STAFF 도 원래 지난다(이번에 생긴 구멍 아님). 화면에서는 잠근다.

### 2.5 자료 · 파일

- 기록 자료: `OrderFieldChange` 에서 `path_template = 'schedule.construction.date'` · 최근 7일(색인 그대로) → 협력사 주문(`partner_org_id` 있음)만 → 바꾼 사람 이름 · 팀. 희망일은 `partner_intake.requested_construction.date`(확정 뒤에도 남아 있다). 새 표 · 새 칸 없음.

- `shipment_pending_requests` 를 판에 맞게 넓힌다: 자르기 30 → 200(훑는 수와 같게). 각 건에 자수 · 첫 제품 이름 · 현장 주소를 붙인다. 판 안 건은 라우트가 이미 읽은 `partner_pending` 주문(`dashboard.py:488`)의 자수를 쓰고, 거기 없는 건(판 밖 · 담당 거르기로 빠진 건)만 structured_data 를 따로 읽는다 — 지금 운영 26건 중 판 밖은 10건(14일 뒤 7 · 날짜 없음 3)이다.
- 템플릿: 지금 칸을 새 파샬 `templates/shipment/partials/partner_request_board.html` 로 옮긴다. 값은 `data-*` 로 넘기고 JS 가 `safeJsonParse` 로 읽는다. 인라인 스타일 금지 — 막대 길이는 `data-*` 값을 JS 가 CSS 변수로 넣는다(템플릿에 `style=` 0개).
- JS 새 파일 `static/js/shipment/partner-request-board.js`(300줄 안 · jQuery 없음 · `fetch` 는 try/catch + `data.success`). CSS 는 `static/css/contexts/shipment/` 아래 새 파일.

## 3. 검증 (완료 기준)

- 서비스 · API 시험: 출고팀 판 확정 200 · 출고팀 주문 화면 시공일 200 · 출고팀이 다른 칸(PUT) 403 그대로 · 희망일로 확정 200 · 평면 칸 채워짐 · 확정 대기에서 빠짐 · 협력사 알림 줄 생김 / 다른 날 200(`moved`) / 이미 정해짐 409 / 시공 시작 단계 409 / 시공팀 · 도면팀 403 · 관리자 · CS · 영업 · 출고 200 / 확정 뒤 날 바꾸기는 사유 판정(확정 단계면 `REASON_REQUIRED`) / 협력사 주문 아님 404 / 지난 날짜 · 빈 날짜 · 목록 밖 시간 400 / 이미 있던 시공시간 그대로 / 도면팀 알림이 대시보드 칸 쓰기와 같은 조건에서만 뜬다(대조군: 도면 착수 전 주문은 안 뜬다) / 원장 행 · 감사 행.
- 화면 시험: 판 14칸 · 판 밖 줄 · 권한 없으면 끌기 없음 · 접기 기억 · 기록 칸(판에서 정한 것 · 주문 화면에서 정한 것 둘 다 · 7일 밖은 안 보임 · 협력사 아닌 주문은 안 보임) · 되돌리기 누르면 요청 0번(대조군: 5초 뒤 1번) · 기존 `tests/security/test_partner_request_display.py` 초록.
- 하네스: JS 300줄 래칫 · `node --check` · 인라인 스타일 래칫 · `scripts/ops/pre_push_smoke.ps1` · 출고 화면 perf-gate(판 밖 건 structured_data 읽기가 예산 안인지).
- 스테이징 실화면 PC 1440 · 1920: 가상 협력사 주문(`CLAUDE-TEST-`, 더미 연락처) 3건으로 희망일 확정 · 다른 날 끌어 놓기 · 두 창 동시 확정(409). 끝나면 가상 주문 정리.

## 4. 바꾸지 않는 것

- 희망일을 그날 건수 · 자수 · 목록에 넣는 규칙(10-28 · 10-29).
- 주문 화면 시공일 칸 · 협력사 화면 · 협력사 알림 문구.
- 대시보드 칸 쓰기 경로(`field_update.py`) — 같은 함수를 부를 뿐 손대지 않는다.
- 휴대폰 · 태블릿 출고 화면.

## 5. 남는 위험

- 자수가 넘쳐도 확정된다 — 경고만 한다(사용자 판단 영역).
- 되돌리기 5초 동안 다른 사람이 같은 주문을 정하면 내 저장이 409 로 끝난다(알림으로 알려 준다).
- 출고팀이 주문 화면을 열게 되면 지금까지 못 보던 금액 · 고객 정보를 보게 된다 — 출고 화면에서 이미 보는 범위인지 구현 첫 단계에서 확인한다.
- 판은 14일까지만 칸이 있다. 그 뒤 희망일은 판 아래 줄에서 날짜 칸으로 정한다.
