# 도면팀 최신본 우선(시트별 교체) + 영업 도면 업로드 확인 — SPEC

- 작성: 2026-10-04 · 상태: **승인됨(2026-10-04 전부 승인) · 구현 deploy**
- 계기: 운영 주문 5407 도면 칸에 3장(같은 도면 9/30판·10/2판 + 영업 수동 업로드 1장)
- 기준 코드: `origin/deploy` d7d6793fc (경로:행은 이 커밋 기준)
- 관련 결정: 2026-09-30 "ERP 는 최종 도면만"(메모리 `project_drawing_final_only_policy`), 09-30 수정 fe52bd8b5(확정 전 재전달 = 전체 교체)

## 1. 원인 (운영 DB 읽기 확인)

5407 `drawing_transfer_history` 순서:

1. 09-30 04:56 UTC 김한비 TRANSFER — 마법사 시트 `s-u95ugwpmp` 1판(첨부 6366)
2. 10-02 03:16 백재현 CONFIRM_RECEIPT → 상태 CONFIRMED
3. 10-02 03:17:57 백재현 주문 화면에서 `김나리.png` 직접 업로드(첨부 6554, category=drawing), 9초 뒤 발주 PUSH
4. 10-02 04:07 김한비 TRANSFER — 같은 시트 2판(첨부 6557), 메모 "김나리 수정", **mode=APPEND**

- **원인 A**: 09-30 수정은 상태가 `TRANSFERRED` 일 때만 미지정 mode 를 `REPLACE_ALL` 로 바꾼다(`foms/api/drawing/erp_orders_drawing.py:170`). 4번은 상태가 CONFIRMED 였다. 작업실 전달 창 기본값도 CONFIRMED 면 APPEND 다(`templates/drawing/partials/workbench_detail_body.html:1745`). 그래서 `drawing_current_files = [1판, 2판]` 이 됐다. 09-30 수정 뒤 운영에서 이 모양은 5407 한 건이다.
- **원인 B**: 3번은 전달을 거치지 않은 업로드다. superseded 규칙(`foms/services/drawing_confirm_cleanup.py:100`)의 대상이 아니라 늘 보인다. 9월 수동 업로드 372건은 대부분 09-28 이전 흐름에서 나왔다. 그때는 도면팀이 채널톡에 올리면 영업이 받아 컨펌한 뒤 ERP 에 올렸다. 09-28 이후 실측 건은 ERP 전달·수령 흐름을 쓴다. 그래서 전달본이 있는 주문에 영업이 다시 올리는 것은 중복 습관일 가능성이 크다(도면팀 전달 뒤 업로드는 한 달에 9건).
- **부수 문제**: 발주 PUSH(`push_kind='drawing'`)는 1판+6554 로 나갔고, 2판이 온 뒤에도 "발주가 옛 도면" 표시가 없다(`channel_integration.py:295-319`, 전달 코드는 이 기록을 읽지 않는다).

## 2. 목표 (사용자 결정 2026-10-04)

1. 도면팀이 마지막으로 저장·전달한 도면이 **시트(제품)별로** 1순위다. 같은 시트의 새 판은 상태(전달됨·확정됨)와 상관없이 옛 판을 바꾼다. 다른 시트는 건드리지 않는다.
2. 영업이 도면팀 전달본이 있는 주문에 '도면' 분류로 파일을 올리면 **확인 창**을 띄운다. 막지 않고 확인만 받는다. 알림은 영업 확인 창만 띄우고 도면팀에는 보내지 않는다. 서버도 확인 없이는 받지 않는다.
3. 도면 칸 순서: 도면팀 최종본이 먼저("최종" 표시), 영업 업로드는 뒤에("직접 업로드" 표시 — 구현 때 바꿈: 올린 사람이 영업이 아닐 수도 있어 사실대로 쓴다).

하지 않는 것: 확정 뒤 재전달을 막기, 주문 전체를 무조건 교체하기(다른 제품 도면이 사라진다), 옛 파일 삭제.

## 3. 설계

### 3.1 시트 신원을 끝까지 싣는다

지금은 마법사가 시트를 알고 있지만 전달 직전에 버린다. 시트 저장 때마다 key 가 새로 생기므로(`wizard.py:1053`) key 로는 시트를 알 수 없다.

- `foms/api/drawing/wizard.py:1479`(transfer-pending)와 `erp_orders_drawing.py:454-458`(transfer-drawing 의 pending 병합)에서 `{key, filename, sheet_id}` 로 넘긴다.
- `materialize_transfer_attachments`(`foms/services/orders/drawing_transfer.py:99`): 입력에 안전한 `sheet_id`(문자열, 64자 이하, `[A-Za-z0-9_-]`)가 있으면 엔트리에 보존한다. 없으면 지금과 같다.
- `_normalize_file_entry`(`drawing_confirm_cleanup.py:67`): `sheet_id` 를 보존한다. 지금은 수령 확정 때 4필드로 다시 만들어 시트 정보가 사라진다.
- 읽는 쪽은 모두 `.get('key')` 만 쓰므로 필드 추가로 깨지지 않는다(전수 확인, 정확한 dict 비교 테스트 없음).

### 3.2 전달 때 같은 시트는 교체

`perform_drawing_transfer` 의 mode 분기(`erp_orders_drawing.py:205-237`) 앞에 한 단계를 넣는다.

- 새 파일 중 `sheet_id` 가 있는 것마다, 옛 목록에서 같은 `sheet_id` 엔트리를 찾아 **그 자리에서** 바꾼다. 번호(순서)가 유지된다.
- 바뀐 옛 엔트리는 `replaced_target_numbers` 와 이력의 `previous_current_files` 에 그대로 남는다. 그래서 superseded 규칙이 화면·공유 링크·발주 PUSH·도면방 PUSH 에서 자동으로 숨긴다. 전달 취소 복원도 지금 방식 그대로 된다.
- 남은 새 파일(시트 없음, 또는 같은 시트가 옛 목록에 없음)은 지금 mode 규칙대로 처리한다. `REPLACE_ALL` 이면 전부 교체한다(지금과 같음).
- 상태 조건은 없다. TRANSFERRED·CONFIRMED·RETURNED 모두 같다. 상태 전이(CONFIRMED → TRANSFERRED, 영업 재확인)는 바꾸지 않는다.
- **옛 엔트리에 `sheet_id` 가 없을 때(기존 주문)**: 마법사 시트가 정확히 1개이고, 옛 엔트리 key 가 `drawing_wizard/exports/` 아래이며, 새 파일이 그 시트이면 같은 시트로 본다. 시트가 2개 이상이면 추정하지 않고 지금 규칙을 따른다.
- 작업실 전달 창 안내 문구를 바꾼다: "같은 시트의 새 판은 옛 판을 바꿉니다. 다른 시트 도면은 그대로 남습니다." 기본 mode 는 그대로 둔다.

### 3.3 확정 뒤 재전달이면 발주 PUSH 를 "옛 도면" 으로 표시

- 전달 때 `channeltalk_push_drawing.pushed` 가 참이고 교체된 key 가 그 PUSH 의 `attachment_ids` 에 있었으면 `channeltalk_push_drawing.stale_drawing_at = <전달 시각>` 을 쓴다. 다음 발주 PUSH 가 성공하면 지운다.
- 주문 화면 발주 PUSH 흔적 칩(`static/js/orders/erp-send-trace.js`)에 "도면 바뀜 — 다시 보내기" 를 띄운다.
- 이 항목은 목표 밖의 추가 제안이다. 승인 때 빼도 된다.

### 3.4 영업 '도면' 업로드 확인

**언제 뜨나**: category=drawing 업로드이고, 주문 `drawing_current_files` 가 비어 있지 않고(도면팀 전달본 있음), 올리는 사람이 DRAWING 팀이 아닐 때.

**화면** (PC·모바일 주문 화면 `erpUploadCommonAttachmentFiles`(`static/js/orders/erp-order-shared.js:4538`)와 붙여넣기 `:4840`, 태블릿 실측 폼 `static/js/foms/tablet-measure-form.js:1400`):

> 도면팀 최종 도면이 이미 ERP 에 있습니다(N장).
> 고객 컨펌은 '도면 수령 확인'으로 끝나고, 발주 PUSH 에도 자동으로 들어갑니다.
> 도면을 고쳐야 하면 '수정 요청'을 쓰세요.
> [그래도 올리기] [취소]

화면은 주문 사본의 `drawing_current_files`(`erp-order-shared.js:799` 로컬 키)로 판단한다.

**서버** (화면을 거치지 않는 경로까지 막기):

- 행을 만드는 세 곳에서 판정한다: `POST /api/orders/<id>/attachments`(`foms/api/files/order_routes.py:349`), `POST /attachments/complete`(`foms/api/files/direct_upload.py:184`), `upload-tickets/<id>/complete`(`upload_ticket_routes.py:100`).
- 조건이 맞는데 요청에 `ack_drawing_final=1` 이 없으면 `409 {'success': False, 'error': 'DRAWING_FINAL_EXISTS', 'data': {'count': N}}` 를 돌려준다.
- direct upload 는 `/upload/session` 에서도 같은 판정을 해서 R2 에 고아 파일이 생기지 않게 한다.
- 판정 함수는 하나만 둔다(`foms/services/files/` 아래 `drawing_upload_guard.py`).
- 면제: DRAWING 팀 사용자. 관리자는 면제하지 않는다. 대신 도면 전달 창(작업실 `workbench_detail_body.html:2531` 등, ERP 대시보드 `erp-dashboard-drawing.js:104`)은 업로드 요청에 항상 `ack_drawing_final=1` 을 싣는다. 이 업로드는 곧바로 전달되기 때문이다.
- 확인하고 올린 행은 `OrderAttachment` 에 표시하지 않는다(스키마 변경 없음). "영업 업로드" 구분은 "`drawing_current_files` 에 없고 superseded 도 아닌 도면 행" 으로 계산한다.

### 3.5 도면 칸 순서·표시

- 서버 목록(`order_routes.py:330`, created_at DESC)은 그대로 둔다. 화면 `erpLoadAttachments`(`erp-order-shared.js:4255`)에서 도면 분류만 다시 정렬한다. `drawing_current_files` 순서의 행을 먼저 두고, 나머지는 최신순으로 둔다.
- 최종본 카드에 "최종 1"·"최종 2" 배지(제품 1개면 "최종"), 나머지에 "영업 업로드" 배지를 단다. CSS 는 `static/css/foundation/erp-pro.css`(인라인 금지 래칫).
- 대시보드 첨부 창 `orderAttachmentsCurrentFirst`(`erp-dashboard-attachments.js:63`)도 같은 규칙을 따른다.

## 4. 5407 정리 (운영 데이터 — 직접 DB 쓰기 없이)

- 현재 상태는 TRANSFERRED 다(10/2 재전달 때문). 영업이 다시 수령 확인해야 하는 상태다.
- 배포 뒤 도면팀이 마법사에서 그 시트를 다시 저장해 전달하면 3.2 의 단일 시트 추정으로 1판·2판이 새 판 1장으로 바뀐다. 상태가 TRANSFERRED 이므로 지금 코드로도 미지정 mode 는 전체 교체다. 그래서 **배포 전에도 도면팀의 재저장·전달 한 번으로 정리된다.**
- `김나리.png`(6554)는 영업 업로드라 자동으로 숨기지 않는다. 백재현님께 중복인지 물은 뒤, 중복이면 주문 화면 휴지통으로 뺀다.
- 그 뒤 영업이 수령 확인하고 발주 PUSH 를 다시 보낸다. 공장은 지금 1판+6554 를 받은 상태다.

## 5. 테스트

새 테스트:

- 확정 뒤 같은 시트 재전달(mode 미지정·APPEND 둘 다) → 현재 목록은 새 판 1장, 옛 판 superseded.
- 시트 2개 중 1개만 재전달 → 다른 시트 유지, 순서 유지.
- sheet_id 없는 옛 엔트리 + 시트 1개 → 교체 / 시트 2개 → 지금 규칙.
- 수령 확정 뒤 `sheet_id` 보존(`finalize_drawing_files_on_confirm`).
- 전달 취소 → 옛 목록(시트 포함) 복원.
- 업로드 가드: 영업이 전달본 있는 주문에 ack 없이 올리면 409, ack 있으면 200, 전달본 없으면 ack 없이 200, DRAWING 팀은 ack 없이 200. 세 엔드포인트와 session 모두 확인한다.
- 발주 PUSH 옛 도면 표시가 설정되고, 다음 PUSH 에서 지워진다(3.3 승인 시).

바뀌는 기존 테스트:

- `tests/domains/test_drawing_confirm_keeps_files.py:347` `test_confirm_receipt_keeps_attachment_tab_drawing_upload` — 영업 업로드에 `ack_drawing_final=1` 을 싣는다.
- `test_drawing_confirm_keeps_files.py:314` `..._append_transfer_past_earlier_confirm_keeps_both` — sheet_id 없는 key 라 결과는 그대로다. 시트 1개 추정이 이 시드에 걸리는지 확인하고, 걸리면 시드에 시트 2개를 넣어 "다른 도면 APPEND" 의미를 지킨다.

검증 명령:

- `python -m pytest tests/domains -k "drawing or wiz or share" -q`
- `python -c "import app; print('APP_OK')"`
- `scripts/ops/pre_push_smoke.ps1` exit 0
- 스테이징에서 `CLAUDE-TEST-` 주문으로 확인: 전달 → 확정 → 같은 시트 재전달 → 도면 칸 1장, 영업 업로드 확인 창

## 6. 범위·위험

- 바뀌는 파일(예상 10개 안팎): `erp_orders_drawing.py`, `wizard.py`, `drawing_transfer.py`, `drawing_confirm_cleanup.py`, `order_routes.py`, `direct_upload.py`, `upload_ticket_routes.py`, 새 `drawing_upload_guard.py`, `erp-order-shared.js`, `tablet-measure-form.js`, `erp-dashboard-drawing.js`, `workbench_detail_body.html`, `erp-pro.css`, 테스트들. DB 마이그레이션은 없다.
- JS 를 고치면 `?v=` 핀을 올린다. `@import` 자식 CSS 는 부모 번들 핀도 올린다.
- 위험: 시트 1개 추정이 "다른 도면을 일부러 추가한" 옛 주문을 교체할 수 있다. 조건(마법사 시트 1개 + 새 파일이 그 시트)이 맞으면 같은 제품의 새 판이므로 의도와 맞는다고 본다. 마법사 밖에서 올린 파일은 sheet_id 가 없어 이 추정에 들어가지 않는다.
- 위험: 409 를 모르는 옛 클라이언트(캐시된 JS)는 업로드 실패만 보인다. 메시지 문구를 서버 응답에 실어 그대로 띄운다.

## 7. 승인 받을 것

1. 3.2 시트별 교체(상태 무관) — 핵심
2. 3.3 발주 PUSH 옛 도면 표시 — 추가 제안, 뺄 수 있음
3. 3.4 영업 업로드 확인(서버 409 포함, 관리자 비면제)
4. 3.5 도면 칸 순서·배지
5. 4 의 5407 정리 순서(도면팀 재저장·전달 → 영업 중복 확인 → 재확인 → 발주 재전송)
