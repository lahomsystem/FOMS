판정: 승인 · 구현 중 (사용자 11-11 "승인, 서버부터" — 1차 서버 끝, §11 구현 기록)

# 완료 주문 AS 도면 (2026-11-11)

목업: https://claude.ai/artifact/7VgKWzntepN56pn8eyzsnE (흐름 1 · 흐름 2 · 함께 가는 단계)

## 1. 왜

- 운영 주문(이영광, 냉장고장 리폼)은 시공까지 끝나 '완료' 단계다. AS 로 정확한 도면이 필요한데, 도면팀이 마법사로 AS 도면을 그려 보낼 길이 없다.
- 보통은 AS 담당이 약식 AS 도면을 직접 만든다. 정확한 도면이 필요할 때만 도면팀이 그린다(사용자 11-11).
- 코드로 확인한 막힘 4가지:
  1. **목록에 안 뜬다.** 도면 작업실 모집단(`foms/services/drawing_workbench_read_model.py` `build_drawing_queue_filter`)은 도면 단계 ∪ RETURNED ∪ (CONFIRM·PRODUCTION 의 TRANSFERRED)다. CS·완료 단계 주문은 '누적 완료' 칸에서만 보인다. 검색도 이 모집단 안에서만 찾는다.
  2. **보내면 원래 최종 도면이 바뀐다.** 마법사 전달은 `drawing_current_files` 에 들어간다. 원래 시트를 고쳐 보내면 `replace_same_sheet_files`(`foms/services/orders/drawing_transfer.py`)가 원래 최종 도면을 그 자리에서 바꾼다. 지운 시트 빼기 규칙(PR #783)도 같은 목록에 걸린다.
  3. **보낸 뒤 확인할 곳이 없다.** 바로 반영 단계는 PRODUCTION·CONSTRUCTION 뿐(`DRAWING_HOTFIX_STAGES`)이라 CS·완료 단계 전달은 TRANSFERRED 가 된다. 그런데 이 단계의 TRANSFERRED 는 목록 모집단 밖이라 영업이 확정할 곳을 못 찾는다(10-22 주문 5625 와 같은 모양).
  4. **AS 와 도면이 이어져 있지 않다.** AS 화면 'AS도면' 칸(`shipment.as_blueprint`)은 표시일 뿐이고, 도면팀은 AS 접수 권한도 없다(`api_as_register` 는 `erp_construction_edit_required` — 관리자·라홈팀·영업팀·시공팀).
- 마법사 페이지 자체(`foms/web/drawing/wizard.py`)는 단계로 막혀 있지 않다. 문제는 그 앞(시작)과 뒤(전달·확인)다.
- '채널톡 접수'는 지금의 AS PUSH 다: `POST /api/channel/push-manual` `push_kind='as'` → AS 그룹방(`CHANNEL_GROUP_AS`). 본문은 서버가 `build_as_push_text`(`foms/services/channel_as_message.py`)로 만들고, 첨부는 `select_as_push_attachments` 가 이번 회차 AS 첨부를 고른다. AS 접수 내용이 없으면 400 이다.

## 2. 사용자 결정 (11-11)

| 번호 | 질문 | 결정 |
|---|---|---|
| D1 | 누가 시작하나 | **두 길 다.** AS 담당이 AS 접수한 주문에서 도면을 부탁할 수 있고(흐름 1), 도면팀이 먼저 시작할 수도 있다(흐름 2). |
| D2 | 누가 확인하나 | **AS 담당과 영업 담당. 둘 중 한 명이 누르면 끝난다.** |
| D3 | 'AS도면' 체크 칸 | 뜻을 바꾸지 않는다. AS 담당이 약식 도면을 만든 표시로 그대로 둔다. |
| D4 | 채널톡 도면방 | AS 도면 전달 때 지금 도면방 PUSH 를 그대로 쓰고 글 앞에 `[AS]` 를 붙인다. |
| D5 | 도면팀이 먼저 시작하면 | **AS 접수와 채널톡 접수(AS PUSH)까지 이어서 한다.** |

## 3. 원칙

1. **원래 최종 도면은 절대 바뀌지 않는다.** `drawing_current_files`·`drawing_status`·`drawing_transfer_history`·`last_drawing_transfer`·`drawing_excluded_files` 를 AS 경로가 쓰지 않는다.
2. **AS 도면은 따로 쌓는다.** 새 최상위 키 `as_drawing` 아래에 차수(1차, 2차…)별로 쌓는다. 차수 안에서는 최종본만 남긴다(같은 시트 새 판이 옛 판을 바꾼다, 2026-09-30 정책과 같은 뜻).
3. **원래 시트는 잠근다.** CS·완료 단계에서 AS 차수 표시가 없는 시트(=원래 시트)와 이전 차수 시트는 서버가 **저장된 그대로 지킨다**(보낸 값은 버리고 응답 `sheet_lock` 으로 알린다). 거절(409)로 하면 자동 저장이 실패를 되풀이해 도면팀 화면이 멈춘다.
4. **새 칸·새 메뉴를 만들지 않는다.** AS 접수 창에 체크 한 줄, 도면 작업실 기존 칸(상태 칸 5개, 다음 액션, 시공일)과 기존 단추 자리에 글자만 바꿔 넣는다.
5. **있는 접수·PUSH 를 다시 쓴다.** AS 접수는 지금 접수 서비스, 채널톡 접수는 지금 AS PUSH 를 그대로 부른다. 문구·원장·회차 규칙이 화면마다 달라지지 않게 한다.

## 4. 흐름

```
흐름 1  AS 담당: AS 접수 창 [✓ 도면팀에 정확한 도면 부탁] ─▶ 대기중(WAITING) ─▶ 도면팀이 AS 시트 만듦 ─▶ 작업중
흐름 2  도면팀: [AS 도면 시작] (AS 접수 없으면 접수 + 채널톡 접수까지) ─────────────────────────────▶ 작업중
함께    작업중(IN_PROGRESS) ─▶ [저장하고 보내기] ─▶ 확정 대기(TRANSFERRED) ─▶ [확인했어요] ─▶ 누적 완료(CONFIRMED)
                    ▲                                         │
                    └──────── 수정 요청됨(RETURNED) ◀── [고쳐 주세요]
        한 번도 안 보냈으면 [AS 도면 그만두기] ─▶ CANCELLED (목록에서 빠짐)
```

### 4.1 흐름 1 — AS 접수한 주문에서 도면 부탁 (AS 담당)

1. 주문 화면 AS 접수 창(`static/js/orders/erp-order-shared.js` 접수 모달, 세 모드 new·edit·reintake 모두) 맨 아래에 체크 한 줄 **"도면팀에 정확한 도면 부탁"** 을 둔다. 체크하면 "무엇을 그려야 하나요" 칸이 열린다(비우면 AS 내용을 쓴다).
2. [AS 접수 확인] 한 번에 접수와 부탁을 같이 저장한다. 접수 API 요청에 `drawing_request: {memo}` 를 싣고, 서버는 접수 mutation 안에서 차수를 `WAITING` 으로 연다(접수 cycle 에 묶임).
3. 이미 열린 차수가 있으면 체크 줄 대신 "도면팀이 그리고 있어요 · 1차 작업중" 글만 보인다(중복 부탁 없음).
4. 알림은 원래 도면 담당(`DRAWING_DOMAIN` 배정)에게, 없으면 도면팀 전체에. 도면 작업실 '대기중' 칸, 다음 액션 "AS 도면 그리기", 시공일 칸 "AS 방문 11-20".
5. 채널톡 AS PUSH 는 지금처럼 AS 담당이 따로 누른다(흐름 1 은 PUSH 를 바꾸지 않는다).
6. 접수 창 초안 보관(`static/js/orders/as-receive-draft.js`)이 체크와 메모도 함께 보관한다.

### 4.2 흐름 2 — 도면팀이 먼저 시작 (AS 접수 · 채널톡 접수까지)

1. 도면팀 직원이 도면 작업실 검색칸에 고객 이름·전화·주문 번호를 친다. **검색할 때만** CS·완료 단계 주문도 결과에 나온다. 다음 액션 "AS 도면 시작할 수 있어요".
2. 실행판 맨 위 [도면 마법사] 단추 자리에 **[AS 도면 시작]**.
3. 열린 AS 접수가 **있으면**: 창은 "무엇을 그리나요" 한 줄과 "AS 접수 11-11 · 냉장고장 문 처짐에 묶기"만 보여 준다. 시작하면 그 접수에 묶여 `IN_PROGRESS`. 채널톡은 건드리지 않는다.
4. 열린 AS 접수가 **없으면**(첫 AS · 지난 AS 가 끝남): 창 제목이 **"AS 접수하고 도면 시작"**. 칸은 AS 내용(필수) · 사진(선택) · **채널톡 AS방에 접수 올리기**(기본 켜짐). 지난 AS 가 끝난 주문이면 "2번째 AS 접수"라고 보여 준다(접수 창 reintake 와 같은 말).
5. [접수하고 시작]은 화면이 차례로 부른다:
   1. `POST /api/orders/<id>/drawing/as/start` `{memo, as_register: {content}}` — 서버 한 mutation 안에서 AS 접수(지금 접수 서비스, 원장·회차 기록 포함) + 차수 `IN_PROGRESS` 를 함께 만든다. 응답에 업로드용 `as_log_id`.
   2. 사진이 있으면 지금 AS 첨부 업로드(category `as`, 그 `as_log_id`)로 올린다.
   3. 체크가 켜져 있으면 `POST /api/channel/push-manual` `{order_id, push_kind: 'as'}` — 지금 AS PUSH 그대로. 본문·첨부는 서버가 고른다.
6. 2·3 이 실패해도 1 은 되돌리지 않는다. 실행판 AS 카드에 [사진 다시 올리기]·**[채널톡 다시 보내기]** 를 보여 준다(채널톡 이력 `channeltalk_push_as` 가 비어 있을 때만).
7. CS 팀에 "도면팀이 AS 를 접수했어요" 알림. AS 화면 '미완료'에 바로 올라오고 접수한 사람에 도면팀 이름이 보인다. 방문 날짜·유상/무상은 AS 담당이 이어서 정한다.

### 4.3 함께 — 그리기부터 확인까지

1. 실행판 단추 글자는 **[AS 도면 그리기]**. 기록 맨 위 AS 카드: 부탁 메모(흐름 1) 또는 접수 내용(흐름 2), AS 사진, AS 담당 약식 도면, 원래 최종 도면.
2. 마법사가 열리면 원래 시트들이 잠금 표시로 보인다. "AS 시트 만들기" 창: **원래 도면 복사해서 시작**(기본) / 빈 시트로 시작. 복사는 화면이 한다(객체 id 새로 발급). 열린 차수가 있으면 서버가 새 시트에 차수 표시를 저절로 붙인다. 원래 시트가 없는 옛 주문(09-28 이전 수동 업로드 도면)은 빈 시트만 고를 수 있고, 원래 도면 그림은 실행판에서 크게 본다. 흐름 1 차수는 첫 AS 시트를 만들 때 `WAITING` → `IN_PROGRESS`.
3. AS 시트 탭에 빨간 `AS 1`. 도면 양식 오른쪽 위에 `AS 1차` 도장, AS 접수일(없으면 시작일), 원래 시공일.
4. [저장] 창은 지금 창 그대로, 보낼 시트는 이번 차수 시트만. 받는 사람: 영업 담당 · AS 담당. 창 아래 "원래 최종 도면 N장은 그대로 있어요". 채널톡 도면방 PUSH 는 `[AS]` 머리말. 생산팀 바로 반영 알림은 가지 않는다.
5. 영업 담당 또는 AS 담당 중 한 명이 주문 화면 도면 칸의 'AS 도면 1차' 묶음에서 [확인했어요] / [고쳐 주세요]. AS 화면 'AS도면' 칸 옆에는 상태 글(대기중 · 작업중 · 왔어요 · 확인함)과 주문 화면 링크만 더한다.
6. AS 가 또 오면 2차. 1차 시트도 잠긴다.

### 4.4 AS 화면에서 부탁 (2026-11-12 사용자 승인 · 시안 https://claude.ai/artifact/EN7RBhevjniJMnQmqKRzD9)

1. AS 화면(PC 표) 'AS도면' 칸 체크 아래 **[도면팀 부탁]**. 보이는 줄 = 시공이 끝난 주문 · 열린 AS 접수(미완료 · 영업/배송 탭) · 열린 AS 도면 없음 · 협력사 주문 아님 · 영업 · CS 권한(`as_drawing_views.can_request`). 완료 탭에는 없다(AS 가 닫혀 있어 [재접수]가 먼저).
2. 누르면 작은 창(방문 가능시간 창과 같은 모양): "AS 접수 <날짜>에 묶어요" · 받는 사람 · "무엇을 그려야 하나요 (비우면 AS 내용)" · [닫기] [부탁하기]. 아래 자리가 모자라면 위로 연다.
3. `POST /api/orders/<id>/drawing/as/request {memo}` — 권한 `ERP_EDIT`(확인 단추와 같음). 열린 AS 접수에 차수 `AS_REQUEST` · `WAITING` 만 붙인다. **AS 접수는 다시 저장하지 않는다**(접수 기록 · AS 내용 · 접수일 · 사진 그대로). 알림 · 폰 알림은 흐름 1 과 같다(도면 담당, 없으면 도면팀 전체). 감사 `AS_DRAWING_REQUESTED`("AS 도면 부탁").
4. 응답 `data.state`(`{title, words}`)로 칸 글자를 새로고침 없이 "1차 대기중"으로 바꾸고, 같은 화면 저장 알림(#saveToast)에 "도면팀에 부탁했어요" 를 띄운다.
5. 막는 경우(409): 시공 전 `NOT_AS_STAGE` · 열린 AS 접수 없음 `AS_NOT_OPEN` · 이미 열린 차수 `AS_DRAWING_OPEN`(응답에 지금 `state` 를 실어 칸 글자를 맞춘다) · 협력사 `PARTNER_ORDER`.
6. 폰 AS 카드(모바일 v2)에는 넣지 않는다 — 카드에 'AS도면' 칸이 없어 줄을 새로 더해야 한다(사용자 11-12 "PC 표만"). 폰에서는 주문 화면 [AS 접수 수정] 창 체크를 쓴다.

#### 4.4.1 2판 — 여러 줄 · 사진 · 동영상 (2026-11-12 운영 첫 사용 의견, 사용자 승인 · 시안 같은 캔버스 '2판' 장)

의견: "텍스트가 1줄로만 써져 매우 불편 · 그림, 동영상 첨부가 안 됨". 지금 AS 첨부 방식과 완전히 맞춘다.

1. 작은 창(폭 400px): "무엇을 그려야 하나요"는 여러 줄 칸(2,000자, Enter 줄바꿈 · Ctrl/⌘+Enter 보내기 · 한글 조합 중 Enter 무시). [사진 · 동영상] 단추 · Ctrl+V 캡처 · 끌어다 놓기로 담고, 미리보기에서 빼기 · 순서 바꾸기 — AS 화면 '기록 추가' 칸과 같은 부품(`as-attachment-order.js`)과 같은 규칙(클립보드는 사진만, 받는 파일 image/* · video/*).
2. [부탁하기] → 서버가 한 저장 안에서 차수 + **AS 기록 한 줄**(`memo` 유형, "도면팀에 도면 부탁 (AS 도면 N차)" + 부탁 글)을 만들고 그 id 를 차수 `request_log_id` 와 응답에 준다. 화면은 파일을 지금 AS 기록 첨부와 같은 길(`fomsUploadOrderAttachmentsBatch`, `category='as'` + `as_log_id`)로 그 줄에 묶는다. 업로드만 실패해도 부탁은 되돌리지 않는다(다시 올리기 = AS 기록 클립 단추, 기록 추가 칸과 같은 규칙). 창을 닫아도 글 · 파일은 주문마다 남는다(AS 접수 창 11-09 규칙).
3. 보이는 곳: AS 화면 회차 기록 · AS 사진 보기 · 주문 화면 AS 기록 · 채널톡 AS방 PUSH 확인 창 후보(고른 것만 나감) · **도면 작업실 AS 카드(새로)**: 지금 차수 부탁 기록 + 지금 AS 접수 기록에 묶인 AS 첨부를 "도면 부탁 때 / AS 접수 때"로 보여 준다(`build_as_media`, 조회 1). 사진은 실행판 이미지 보기, 동영상은 새 탭. 고객 공유 링크에는 안 나간다(AS 분류는 원래 빠짐).
4. 여러 줄 글은 작업실 카드 · 주문 화면 AS 도면 칸에서 줄바꿈 그대로(`.dw-as-memo` pre-line). 종 · 폰 알림 글은 " / " 로 한 줄.
5. 주문 화면 AS 접수 창의 같은 칸("무엇을 그려야 하나요")도 여러 줄(2,000자)로(사용자 11-12 "같이 여러 줄로"). 그 창은 원래 사진 · 동영상을 받는다(접수 사진 → 작업실 카드 'AS 접수 때').

## 5. 데이터

`structured_data['as_drawing']` (서버 소유, 폼은 보내지도 렌더하지도 않는다):

```json
{
  "current_round_id": "asd_3f9c1a2b",
  "rounds": [
    {
      "round_id": "asd_3f9c1a2b",
      "no": 1,
      "source": "AS_REQUEST | DRAWING_FIRST",
      "cycle_id": "<as_lifecycle cycle id 또는 null>",
      "status": "WAITING | IN_PROGRESS | TRANSFERRED | RETURNED | CONFIRMED | CANCELLED",
      "memo": "오른쪽 문짝 1짝 · 원래 크기 그대로",
      "opened_at": "2026-11-11T14:20:00", "opened_by": 61,
      "registered_as": true,
      "files": [{"key": "orders/5712/drawing_wizard/exports/...png", "name": "AS1 냉장고장 문짝", "sheet_id": "s_ab12", "sig": "v2:..."}],
      "history": [{"action": "REQUEST|START|TRANSFER|REQUEST_REVISION|CONFIRM|CANCEL|CHANNEL_PUSH_FAILED", "at": "...", "by": 61, "note": "", "files": []}]
    }
  ]
}
```

- `registered_as`: 흐름 2 에서 도면팀이 AS 접수까지 했는지(AS 화면 "접수: 도면팀" 표시와 감사 근거).
- 목록 SQL 이 쓰도록 평평한 키 `as_drawing_status`(현재 차수 상태)를 함께 둔다. `drawing_status` 와 같은 모양의 단순 같음 비교만 쓴다(부분 색인 술어와 어긋나지 않게).
- 마법사 시트: `drawing_wizard.sheets[i].as_round_id` 를 더한다. 없으면 원래 시트다.
- 새 DB 컬럼·마이그레이션은 없다.

## 6. 바꾸는 곳

### 6.1 목록 · 실행판

- `foms/services/drawing_workbench_read_model.py` — 모집단에 `as_drawing_status IN (WAITING, IN_PROGRESS, TRANSFERRED, RETURNED)`(+ include_confirmed 면 CONFIRMED)를 더한다. 검색어가 있을 때만 CS·완료 단계 주문을 더하는 갈래를 둔다(검색 없는 기본 목록은 지금 크기 그대로). 스테이징에서 EXPLAIN 으로 Seq Scan 여부를 잰다(성능 가드).
- `foms/services/drawing_workbench_display.py` — AS 차수 행: 상태 칸은 차수 상태로 센다(WAITING=대기중), 다음 액션 "AS 도면 그리기"·"AS 확인 기다림"·"AS 고쳐 달라고 함", 시공일 칸 = 묶인 AS 방문일이 있으면 "AS 방문 11-20". 검색으로 나온 완료 주문 행: "AS 도면 시작할 수 있어요".
- `templates/drawing/partials/workbench_detail_body.html` — 단추 자리 하나: CS·완료 단계면 [AS 도면 시작] / 차수가 열렸으면 [AS 도면 그리기]. 기록 맨 위 AS 카드(§4.3-1), 흐름 2 실패 때 [사진 다시 올리기]·[채널톡 다시 보내기].

### 6.2 AS 접수 쪽 (흐름 1 · 흐름 2 공용)

- `foms/api/cs/as_orders.py` — 접수 본체(새 cycle `register_as_cycle` · 재접수 `_apply_reregistration` · 원장 `_register_with_ledger` · 접수일·상차일·시공자 반영)를 서비스 함수로 옮겨 접수 API 와 도면팀 시작 API 가 같은 함수를 부른다. 라우트 뒤에 남은 감사(`_audit_as`)·캐시 무효화(`_invalidate_shipment_asrec_caches`)도 같이 옮긴다.
- 접수 API 는 선택 필드 `drawing_request: {memo}` 를 받는다. 있으면 같은 mutation 안에서 차수를 `WAITING` 으로 연다(열린 차수가 있으면 무시하고 응답에 `drawing_request: 'already_open'`).
- 화면: 접수 모달에 체크 줄, `as-receive-draft.js` 초안 보관에 두 값 추가.

### 6.3 도면 쪽 서버 API (새 Blueprint 없음, `foms/api/drawing/` 아래 새 모듈 `as_drawing.py`)

| 경로 | 누가 | 하는 일 |
|---|---|---|
| `GET /api/orders/<id>/drawing/as` | 로그인 직원(협력사 제외) | 지금 차수·지난 차수·시작할 수 있는지·열린 AS 접수 요약. |
| `POST /api/orders/<id>/drawing/as/start` | 정책 `DRAWING_TEAM`(도면팀·관리자·매니저) | CS·완료 단계만. 열린 차수가 있으면 409 `AS_DRAWING_OPEN`. 열린 AS 가 있으면 묶어 `IN_PROGRESS`. 없으면 `as_register.content` 필수 → 접수 서비스로 AS 접수 + 차수를 한 mutation 에. |
| `POST /api/orders/<id>/drawing/as/transfer` | 정책 `DRAWING_TEAM` | 이번 차수 시트의 대기함 파일만 차수 `files` 로. 같은 시트는 바꾸고 나머지는 둔다. 알림·도면방 PUSH(`[AS]`). |
| `POST /api/orders/<id>/drawing/as/confirm` | 정책 `ERP_EDIT`(CS·영업 팀 전체·관리자·매니저) | TRANSFERRED → CONFIRMED. 한 명이면 끝. |
| `POST /api/orders/<id>/drawing/as/request-revision` | 같음 | 사유 필수. → RETURNED, 도면팀 알림. |
| `POST /api/orders/<id>/drawing/as/cancel` | 정책 `DRAWING_TEAM` | 한 번도 안 보냈을 때만. → CANCELLED. 흐름 2 에서 만든 AS 접수는 지우지 않는다(AS 담당이 정리). |

- 채널톡 접수는 새 API 를 만들지 않는다. 화면이 지금 `POST /api/channel/push-manual` `push_kind='as'` 를 부른다(`role_required(['ADMIN','MANAGER','STAFF'])` 라 도면팀 STAFF 도 이미 부를 수 있다). 실패하면 차수 history 에 `CHANNEL_PUSH_FAILED` 를 남기는 작은 기록 API 하나만 둔다(또는 실행판이 `channeltalk_push_as` 이력 유무로 판정 — 구현 때 둘 중 단순한 쪽).
- 새 Blueprint `erp_orders_as_drawing`(`foms/api/drawing/as_drawing.py`, 등록 `foms/platform/blueprints.py`). 모든 쓰기는 `execute_order_mutation`(If-Match · 멱등 키) 위에서 한다(receipt 정책 id `AS_DRAWING`). 권한은 기존 정책 `DRAWING_TEAM`·`ERP_EDIT` 를 쓰고 매니페스트 `docs/harness/foms_order_mutation_policy_manifest.json` 에 5개를 등재했다. 핸들러도 같은 정책을 다시 판정한다(테스트·가드 꺼짐 대비).
- 기존 전달 API(`foms/api/drawing/erp_orders_drawing.py` `perform_drawing_transfer`)는 CS·완료 단계에서 마법사 시트 파일(`sheet_id` 있음)이 하나라도 있으면 400 `USE_AS_TRANSFER` 로 거절한다 — 원래 시트 그림도 원래 최종 도면으로 못 간다. 직접 올린 파일(시트 없음) 전달은 그대로다.
- 알림은 벨 알림만(`notification_type='AS_DRAWING'`, `foms/services/orders/as_drawing_notify.py`). 폰 push 는 1차 밖이다.

### 6.4 마법사

- `foms/api/drawing/wizard.py` PUT — `apply_sheet_lock`(`foms/services/orders/as_drawing.py`): CS·완료 단계면 잠긴 시트(원래·지난 차수)를 저장된 사본으로 되돌리고 빠졌으면 되살린다. 순서는 잠긴 시트 다음 AS 시트. 열린 차수가 없으면 새 시트는 버린다. 응답 `data.sheet_lock = {kept, dropped, tagged}`. AS 단계가 아니면 화면이 보낸 차수 표시를 저장값으로 되돌린다(표시는 서버만 붙인다). 페이지 설정(`foms/web/drawing/wizard.py` `wizard_config`)에 `as_round: {round_id, no, opened_at, as_received_date, original_construction_date}` 를 넣는다.
- JS 는 새 파일 `static/js/drawing/wizard-as.js` 로 뗀다(마법사 JS 300줄 래칫이 꽉 차 있다). 시트 탭 잠금 표시·`AS N` 표시·"AS 시트 만들기" 창·양식 도장.
- 저장 창(`static/js/drawing/save-send.js`): AS 모드면 보낼 시트 = 이번 차수 시트 전부(빈 시트만 뺀다, 11-06 규칙과 같다), 전달 경로 = `as/transfer`. `tests/domains/save_send_runner.js` 로 node 가짜 화면 시험을 더한다.

### 6.5 지켜야 할 함정 (이미 있는 코드)

- **키 정리:** `foms/services/orders/drawing_key_safety.py` `drawing_keys_in_use` 에 `as_drawing.rounds[*].files`·`history[*].files` 의 key 를 더한다. 빠지면 마법사 다시 저장 때 AS 도면 그림이 R2 에서 지워진다.
- **폼 저장:** `foms/api/erp_orders_structured.py` `_OPERATIONAL_TOP_LEVEL_KEYS` 와 `lock_server_owned_keys`(`foms/services/orders/structured_form_projection.py`)에 `as_drawing`·`as_drawing_status` 를 더한다. 빠지면 주문 폼 저장 한 번에 차수가 사라진다(09-10 주문 5177 과 같은 사고).
- **고객 공유 링크:** `foms/api/share.py` 는 도면 첨부 + `drawing_current_files` 를 합친다. AS 도면은 두 곳 어디에도 넣지 않으므로 빠진다. 시험으로 못 박는다.
- **확정 정리:** `finalize_drawing_files_on_confirm`(`foms/services/drawing_confirm_cleanup.py`)을 AS 확인에서 부르지 않는다. AS 사진·약식 도면을 지우지 않는다.
- **시트 복사 그림 원본:** 복사한 AS 시트를 지워도 원래 시트가 쓰는 그림 원본 key 를 지우면 안 된다(`_deletable_after` 경로 확인).
- **AS 분류 깃발과 묶지 않는다:** 차수 시작·확인이 `as_blueprint`·`sales_delivery`·AS cycle 상태를 바꾸지 않는다. 분류 깃발과 배정을 묶었다가 되돌린 10-29 주문 5432(PR #657)와 같은 이유다.
- **접수 복제 금지:** 흐름 2 접수를 새로 짜지 말고 §6.2 서비스를 부른다. 원장(`_record_as_ledger`)·회차 비용 잠금·접수일 컬럼이 한 군데라도 빠지면 AS 화면·정산 알림이 어긋난다.
- **채널톡 재전송 규칙:** AS PUSH 는 이력이 있으면 재전송 메모(`change_note`)가 필수다. [채널톡 다시 보내기]는 첫 전송 실패 때만 보이므로 메모 없이 보낸다. 이미 한 번 간 뒤라면 단추를 숨긴다.

## 7. 권한

- **흐름 1 부탁:** AS 접수 창을 저장할 수 있는 사람(지금 `erp_construction_edit_required` — 관리자·라홈팀·영업팀·시공팀). 권한을 바꾸지 않는다.
- **흐름 2 시작 + AS 접수:** 도면팀 소속, 지정 도면 담당, 관리자. 도면팀의 AS 접수는 **이 경로에서만** 열린다(일반 접수 API 권한은 그대로).
- **흐름 2 사진 업로드:** 도면팀이 category `as` 첨부를 올릴 수 있는지 구현 첫날 확인한다. 막혀 있으면 이 차수에 묶인 `as_log_id` 업로드만 도면팀에 연다.
- **AS 시트·보내기:** 도면팀 소속, 지정 도면 담당, 관리자. 생산·시공·협력사는 403.
- **확인·고쳐 주세요:** 주문 영업 담당(배정), 묶인 AS cycle 을 연 사람, CS 팀, 관리자. 한 명이면 끝. AS 접수가 없는 차수는 없다(흐름 2 가 접수까지 하므로).
- 협력사 주문(`partner_org_id`)은 1차에서 막는다(409 `PARTNER_ORDER`) — 협력사 담당·명세서 흐름이 따로 있어 범위를 넘는다.

## 8. 바꾸지 않는 것

- 원래 도면 흐름(전달·수령 확정·바로 반영·제품 취소)과 그 데이터.
- AS 화면 'AS도면' 체크 칸의 뜻과 저장 방식. 옛 체크는 그대로 둔다.
- AS 접수 API 권한, AS 방문·완료 흐름, AS PUSH 본문 모양.
- 고객 공유 링크, 생산팀 화면, 출고 화면.

## 9. 남은 질문 (옛 번호 유지)

- 없음. 11-11 결정 D1~D5 반영.

## 10. 순서와 시험 (완료 기준)

1. 서버: 접수 서비스 옮기기 → `as_drawing` 데이터·API·잠금·키 안전·폼 보존. 시험 `tests/domains/test_as_drawing_round.py`(새):
   - 흐름 1: 접수 API 에 `drawing_request` → 차수 WAITING, cycle 묶임, 도면팀 알림. 열린 차수 있으면 `already_open`.
   - 흐름 2: 도면팀이 AS 없는 완료 주문에서 시작 → AS cycle RECEIVED + 차수 IN_PROGRESS 가 한 번에. `as_received_date`·원장 행이 일반 접수와 같다. 열린 AS 있으면 묶이고 새 접수 없음. 도면 단계 주문 409, 생산팀 403, 일반 접수 API 는 도면팀에 여전히 403.
   - AS 전달 뒤 `drawing_current_files`·`drawing_status`·`drawing_transfer_history` 가 바이트까지 같다.
   - 원래 시트 저장 409 `SHEET_LOCKED`, AS 시트 저장 200.
   - 같은 차수 같은 시트 재전달은 바꾸고, 다른 시트는 남는다.
   - 확인: 영업 담당·AS cycle 연 사람·CS 팀 200(한 명이면 CONFIRMED), 도면팀 403. 고쳐 주세요 → RETURNED.
   - `drawing_keys_in_use` 에 AS key 포함. 주문 폼 저장 뒤 `as_drawing` 그대로. 공유 링크에 AS 파일 없음.
   - 흐름 2 뒤 `push-manual` `push_kind='as'` 가 접수 내용으로 본문을 만든다(채널톡 전송은 가짜로 막고 본문만 견준다).
2. 기존 AS 접수 시험이 그대로 통과(`tests/domains/` AS 접수·재접수·원장 시험 — 서비스 옮기기 회귀 확인).
3. 목록·실행판: 도면 작업실 시험(`tests/domains/test_drawing_workbench_pipeline_buckets.py` 등)에 AS 행 칸 수·검색 갈래 시험.
4. 마법사·저장 창·접수 창: `save_send_runner.js` AS 모드 시험, `node --check` 로 새 JS 문법 확인.
5. 검증 명령: `python -m pytest tests/domains/test_as_drawing_round.py tests/domains/test_drawing_workbench*.py -q` 와 AS 접수 시험 → push 직전 `scripts/ops/pre_push_smoke.ps1` → CI green.
6. 스테이징 실화면(채널톡 AS 그룹이 실제 방인지 먼저 확인 — 스테이징 영발방이 운영 실제 방이었던 전례): 완료 주문 복제 → 흐름 1(영업 계정 접수 창 부탁 → 도면팀 그리기 → 영업 확인), 흐름 2(도면팀 계정 접수하고 시작 → 사진 → 채널톡 접수 → 그리기 → AS 담당 확인). 원래 최종 도면 key 목록이 처음과 같은지 견준다. 운영은 사용자 요청 때만.

## 11. 구현 기록

### 1차 서버 (2026-11-11, `session/as-drawing`)

- 새 파일: `foms/services/orders/as_drawing.py`(차수 규칙·시트 잠금·전달·확인·고쳐 달라기·그만두기), `foms/services/orders/as_drawing_notify.py`(벨 알림), `foms/api/drawing/as_drawing.py`(API 6개), `tests/domains/test_as_drawing_round.py`(17개).
- 고친 파일: `foms/api/cs/as_orders.py`(접수 본체를 `register_as_from_payload` 로 떼어 냄 + `drawing_request`), `foms/api/drawing/wizard.py`(PUT 잠금), `foms/api/drawing/erp_orders_drawing.py`(`USE_AS_TRANSFER`), `foms/services/orders/drawing_key_safety.py`(`as_drawing_keys`), `foms/api/erp_orders_structured.py`·`foms/services/orders/structured_form_projection.py`(서버 소유 키), 블루프린트·매니페스트.
- 검증: 새 시험 17 + 관련 기존 시험 889(AS·마법사·도면 전달·권한 목록·폼 저장·파일 보호) 통과, 층 의존·파일 크기·이름공간 래칫 통과, `APP_OK`.

### 2차 화면 (2026-11-11, 같은 브랜치)

- 도면 작업실 목록: 열린 차수를 모집단에 더함(AS 축 부분 색인 + `as_drawing_status`), 검색어가 있으면 시공이 끝난 주문을 검색 SQL 술어로 찾음. 상태·다음 액션·시공일 칸 글자만 바꿈(`foms/services/drawing_workbench_as_rows.py`).
- 실행판: 맨 위 단추 [AS 도면 시작]/[AS 도면 그리기], AS 카드(`templates/drawing/partials/workbench_as_card.html`, `static/js/drawing/workbench-as.js`, `static/css/contexts/drawing/workbench-as.css`) — 시작(접수·채널톡 AS방 접수 포함), 보내기, 확인/고쳐 주세요, 그만두기, 채널톡 다시 올리기. 영업·CS 확인은 이 카드에서 한다(주문 화면 묶음은 다음).
- AS 접수 창(PC·모바일) '도면팀에 정확한 도면 부탁' 한 줄과 `drawing_request`.
- 마법사: `sheet-png` 가 원래 시트 그림을 대기함에 안 넣음(409 `SHEET_LOCKED`), 저장 응답 `sheet_lock` 이면 알리고 다시 읽음. 원래 도면 옮기기는 지금 있는 복사(Ctrl+C)·붙여넣기로 한다.
- 행위 감사 `AS_DRAWING_*` 5종, 하네스 인벤토리 갱신.

### 3차 마법사 (2026-11-11, 같은 브랜치)

- `static/js/drawing/wizard-as.js`·`static/css/contexts/drawing/wizard-as.css`(완료 주문에서만 실림): 탭 '잠금'·'AS N' 표시, 처음 열 때 "AS 시트 만들기" 창(원래 도면 복사 = 탭 ⧉ 복제 / 빈 시트), 종이 오른쪽 위 'AS N차' 도장(PNG 에도 찍힘), AS 단계 도면방 PUSH 막기.
- 페이지 설정 `wizard_config.as_drawing`(`as_drawing.wizard_config_view`), 엔진 창구에 시트 복제·추가·전환·탭 다시 그리기.
- `transfer-pending`: 시공이 끝난 주문이면 AS 도면 보내기로 잇는다 — [저장] 창 "저장하고 보내기"가 그대로 AS 도면을 보낸다.
- AS 행위 감사는 `SecurityLog` 직접(API 층은 웹 층 `log_access` 를 부르지 않는다).
- 도장 자리·창 모양은 8차 스테이징 실화면에서 확인하고 고쳤다.

### 4차 주문 화면 (2026-11-11, 같은 브랜치)

- PC·모바일 주문 화면 첨부 갤러리 위 'AS 도면 N차' 묶음(`static/js/orders/erp-as-drawing-panel.js`) — 영업·CS 가 [확인했어요]/[고쳐 주세요]. 원래 도면 갤러리와 따로, AS 도면 없으면 숨김.

### 5차 도면방 [AS] (2026-11-11, D4)

- 같은 도면방 길(`push-manual` `push_kind='drawing_room'`)에 `as_drawing: true` — 본문 `[AS] 고객 · AS 도면 N차` + 메모, 첨부 = AS 차수 파일(열린 차수, 없으면 마지막 확인 차수), 이력 `channeltalk_push_as_drawing_room`(원래 도면방 이력과 따로, 폼 저장 보존). 담당 영업 개인방도 같은 규칙.
- `static/js/drawing/as-room-push.js`(공용): 개인방 못 찾음(409) → 공용방만 보낼지 묻기, 재전송 → 까닭 묻기. 마법사 [저장] 창 "도면방에도 보내기"와 실행판 AS 카드 [채널톡 도면방에 [AS] 보내기]가 같이 쓴다.

### 6차 AS 화면 상태 글 (2026-11-11)

- AS 화면 'AS도면' 칸 옆에 `AS 도면 N차 · 도면팀 대기중/작업중/왔어요/고쳐 달라고 함/확인함` 한 줄 + 주문 화면 링크. 체크 칸 뜻은 그대로.
- 화면 값 함수는 `foms/services/orders/as_drawing_views.py` 로 뗐다(파일 500줄 래칫).

### 7차 시작 창 사진 (2026-11-11, 사용자 결정 "AS 도면 시작 창에서만")

- 실행판 시작 창(AS 접수 없음)에 사진 칸. 시작 → 그 접수 기록(`reception_log_id`)에 사진 업로드 → 채널톡 AS방 접수 순서라 사진도 AS PUSH 에 실린다.
- 권한: 첨부 업로드(`POST /api/orders/<id>/attachments`)가 AS 사진을 막을 때, 도면팀이 **본인이 접수까지 하고 연 작업중 차수**에 **그 접수 기록으로** 올리는 경우만 통과(`as_drawing.drawing_starter_may_upload_as_photo`). 그 밖의 AS 사진 권한(`CONSTRUCTION_EDIT`)·presigned 경로는 그대로.

### 8차 스테이징 실화면 고침 (2026-11-12)

스테이징(60711132a)에서 완료 주문 복제본 2건(`CLAUDE-TEST-AS도면-흐름1/2`, 전화 02-0000-0000)과 도면팀 시험 계정으로 두 흐름을 화면으로 밟았다. 채널톡 주소는 브라우저에서 막았다(실제 방 보호).

- **마법사 [저장] 창 '도면 발송'이 거절됐다.** 저장 창(`save-send.js`)은 `transfer-pending` 이 아니라 `POST /transfer-drawing`(`pending_sheet_ids`)을 부른다. 서버가 그 길을 `USE_AS_TRANSFER` 로 막고 있었다. 이제 완료 주문에서 `pending_sheet_ids` 가 오면 `transfer_pending_as` 로 잇는다(작업실 일괄 전달과 같은 AS 도면 보내기). 시험은 두 길을 같이 돈다.
- 저장 창이 '고친 다른 시트'를 다시 그릴 때 잠긴 원래 시트는 뺀다(`locked_sheet_ids`). 원래 시트 그림은 서버가 막아서, 다시 그리면 전달 전체가 실패한다.
- 탭에 'AS 1 AS1 …' 처럼 같은 말이 두 번 나왔다. 이름이 'AS N' 으로 시작하면 빨간 표를 안 붙이고 탭 글을 빨갛게만 한다. 복제 이름 끝 ' 복사' 는 뺀다.
- 도장이 오른쪽 위 '발주 리스트' 칸과 양식 모서리 칸을 가렸다. 왼쪽 위 여백에 한 줄로 옮겼다. 저장 그림(PNG)에도 테두리 밖에 찍히는 것을 확인했다.
- V2 화면: 탭을 다시 그리지 않고 부르면 '잠금' 이 두 번 붙었다(한 번만 붙게 고침). `display:flex` 가 `[hidden]` 을 이겨서, 원래 시트에서 빈 빨간 상자가 남았다(고침).
- 시작 창 사진이 실패하면 그 안내가 다음 안내에 덮였다. 이제 끝에 붙인다.
- (배포 뒤 확인) 마법사 '도면 발송' → TRANSFERRED, 주문 화면 [고쳐 주세요] → 다시 발송 → [확인했어요] 모두 됐다. 두 건 다 `drawing_current_files` 가 원본 주문과 같다.
- AS 화면 'AS도면' 칸(폭 54px)에서 'AS 도면 1차 · 확인함' 이 `text-nowrap` 이라 옆 칸 글과 겹쳤다. 칸 제목과 겹치는 말을 뺀 짧은 글(`1차 대기중`·`작업중`·`왔어요`·`고치는 중`·`확인함`)을 낱말마다 줄바꿈 없이 쓰고, 긴 글은 마우스 글(title)로 둔다(`as_drawing_views.status_view`).
- 그대로 맞았던 것: 흐름 1 접수 창 체크 줄·주문 화면 'AS 도면 1차 · 도면팀 대기중', 작업실 목록 'AS 방문 미정 · AS 도면 그리기 · 1차', 흐름 2 검색 → 시작 창 → 접수 + 사진(접수 기록에 묶임) + 작업중 카드, 채널톡 실패 안내.

### 운영 반영 (2026-11-12, 사용자 요청)

- PR #817(`019c366d8`) — 이 세션 커밋 19개 cherry-pick(AI_STATUS 만 바꾼 커밋 2개 제외). 완전성 검사 '빠진 의존 331개'는 인벤토리·문서·핀 계보 때문이었다: 파일 내용 대조로 바탕이 다른 파일은 인벤토리 4개·`wizard.html`(핀만)·AI_STATUS 뿐, 내 커밋 사이 남의 커밋 0. 승격 트리에서 APP_OK·인벤토리 재생성(변화 없음)·pre_push_smoke 통과, PR 검사 4개 통과.
- 운영 배포 SUCCESS, 운영이 새 자산(wizard-as.js·save-send.js·wizard-as.css)을 내보내는 것 확인. 스테이징 시험 주문 #4894·#4895 휴지통, 시험 계정 104 탈퇴.

### 9차 남은 일 (2026-11-12, 사용자 "남은 일 하기")

- **고객 공유 링크 제외 시험**: 고객 링크는 `OrderAttachment(category='drawing')` + `drawing_current_files` 만 모은다(`share._collect_drawing_files`). AS 차수 파일은 첨부 행을 만들지 않고 현재본에도 안 들어가서 원래 섞이지 않는다 — 수집 함수와 실제 `/s/<token>` 화면으로 못 박았다(원래 도면은 보이고 AS 그림은 없음).
- **폰 알림**: 원래 도면 규칙과 같게 부탁 · 도착 · 수정 요청만 폰에도 간다. 알림 유형을 나눴다 — `AS_DRAWING_REQUEST`(도면 담당) · `AS_DRAWING_TRANSFERRED`(영업 · CS) · `AS_DRAWING_REVISION`(차수 연 사람 · 도면 담당), 접수(CS 팀 전체) · 확인은 그대로 `AS_DRAWING` 벨만. `push_sender` P1 · 높은 긴급도 · 배너 글(`AS 도면 도착 · 고객명` 등) · 바로가기(도면팀 = 작업실 실행판, 영업 = 주문 화면)에 등록, 벨 바로가기도 같은 곳. 줄 세우기는 커밋 뒤(`enqueue_as_drawing_push`).

- 운영 반영: PR #818(`b1787ec80`) — 위 두 가지, 운영 배포 SUCCESS.

### 10차 AS 화면 [도면팀 부탁] (2026-11-12, §4.4)

- 서버 `api_as_drawing_request`(`foms/api/drawing/as_drawing.py`) · 칸 조건 `can_request` · `as-dashboard-drawing-request.js`(작은 창) · CSS 는 `as-dashboard-body.css`(핀 `20261112a`). 매니페스트 2곳(정책 · 쓰기 보호) 등재.
- 시험 `tests/domains/test_as_drawing_dashboard_request.py` 6개: 성공(차수 · 접수 기록 불변 · 알림 · 폰 알림 · 감사) · 도면팀 전체 · 막는 경우 4가지 · 도면팀 계정 403 · 칸 단추 조건(대기중 · 시공 중 · 도면팀 시작 줄에는 없음) · 스크립트 계약.
- 로컬 실화면(파일 SQLite + Playwright, 스테이징은 폰 알림이 실제 직원에게 갈 수 있어 피함): 단추 → 창 → 부탁하기 → 칸 "1차 대기중" · 알림 "도면팀에 부탁했어요", 동시 부탁은 빨간 알림 "도면팀이 이미 그리고 있어요." + 칸 글자 맞춤, 새로고침 뒤에도 그대로. 고친 것 2개: 칸 안 빨간 글이 54px 칸에서 한 글자씩 끊김 → 화면 저장 알림으로, 단추가 칸 안쪽 폭보다 넓어 오른쪽으로 밀림 → 가운데 맞춤.

- 운영 반영(사용자 "운영 올려"): PR #826(`14043d6b8`) — deploy 커밋 `38999cac9` 하나만 cherry-pick. 코드 파일 바탕은 운영과 같았고 충돌은 AI_STATUS · 설계서 문서뿐이라 운영 쪽을 두었다. 승격 트리 APP_OK · 인벤토리 변화 없음 · 시험 47개 · pre_push_smoke 통과, PR 검사 4개 통과, 운영 배포 SUCCESS, 운영 · 스테이징이 새 스크립트를 내보내는 것 확인.

### 11차 2판 여러 줄 · 사진 · 동영상 (2026-11-12, §4.4.1)

- 서버: `api_as_drawing_request` 가 AS 기록 한 줄 + `request_log_id`, 부탁 글 2,000자(`_MAX_MEMO`, 흐름 1 도 2,000). `as_log` 쓰기 호출부 목록(`test_as_timeline_contract`)에 등재 — 본문은 `append_client_log` 가 sanitize. 작업실 카드 사진 `build_as_media`(조회 1, 카드가 보일 때만). 알림 글 한 줄(`_one_line`).
- 화면: `as-dashboard-drawing-request.js` 2판(296줄) · `as-dashboard-body.css` · 미리보기 칸 정렬은 공용 `foms-as-attachment-order.css` 에 이 창을 더함 · 작업실 카드 사진 묶음 + 이미지 보기 연결(`workbench-as.js`) · 접수 창 칸 textarea(PC · 폰 템플릿).
- 시험 8개(`test_as_drawing_dashboard_request.py`): 여러 줄 · 기록 한 줄 · 앞 기록 불변 · 알림 한 줄 · 2,000자 · 접수 창 여러 줄 · 업로드가 부탁 줄에 묶임 · 작업실 카드 묶음 순서 · 스크립트 계약.
- 로컬 실화면(파일 SQLite · 로컬 저장소 · Playwright): 여러 줄 입력(Enter 는 안 보냄) · 사진 2 + 동영상 1(파일 단추 · Ctrl+V) · 닫았다 다시 열기(글 · 파일 그대로) · Ctrl+Enter → "사진 · 동영상 3개도 함께 보냈어요" · 세 파일 모두 부탁 줄에 묶임 · 작업실 카드 '도면 부탁 때 3 / AS 접수 때 1' · 사진 누르면 이미지 보기 1/3. 고친 것: 미리보기가 세로로 한 줄씩 쌓임 → 공용 미리보기 정렬에 이 창 추가, [사진 · 동영상]이 글자처럼 보임 → 기록 추가 칸 [파일] 단추와 같은 모양. 로컬 400 `/api/upload/session` 은 로컬 저장소라 바로 올리기 대신 폼 업로드로 넘어간 것(기록 추가 칸과 같음).

### 아직 안 한 것 (다음 순서)

1. 도면방 [AS] 단추는 화면에서 누르지 않았다(스테이징 방이 실제 방 — 서버 시험만). 운영 첫 실제 사용 때 확인.
