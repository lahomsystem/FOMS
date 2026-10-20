# 마법사 "PUSH 했는데 주문 없음" 막기 — 설계서

- 작성: 2026-10-20 · 상태: **승인(2026-10-20) · 구현 완료(세션 브랜치 `session/wizard-push-register`)** — 구현 결과는 맨 아래 §7
- 계기: 박미영(010-4417-9114) 건. 10-20 11:07 실측방 PUSH·알림톡 발송 → 주문 등록은 14:24(주문 5769, 197분 뒤). 그 사이 "채널톡엔 왔는데 ERP 에 주문이 없다" 문의.

## 1. 지금 구조와 실측

- 마법사 4단계의 `실측 PUSH`·`알림톡` 버튼은 **초안(OrderDraft)** 에서 보낸다. 설계 D1 "버튼이 몰래 주문을 만들지 않는다" ([foms/api/erp_order_draft_send.py](../../foms/api/erp_order_draft_send.py)).
- 이미 있는 방어 2개:
  - 발송 후 `다음/등록` 버튼 강조(`markPendingSubmit`, [static/js/foms/wizard-send.js](../../static/js/foms/wizard-send.js)).
  - 마법사 **닫기 버튼**을 누를 때만 뜨는 확인창([static/js/foms/wizard.js](../../static/js/foms/wizard.js) `FomsWizardHasPendingSend`). 브라우저 뒤로가기·탭 닫기·앱 전환·화면 꺼짐은 못 잡는다. 코드 주석에 "초안 푸시 54건 중 3건 유실"이 기록돼 있다.
- 운영 실측(2026-10-20, 읽기 전용):
  - 초안에서 PUSH 한 뒤 등록된 주문 241건(09-03~). 236건은 PUSH 후 수 초 안에 등록 → 현장은 이미 "PUSH→등록"을 한 동작으로 쓴다.
  - 5건은 76~197분 늦게 등록(09-06·08·10·11, 10-20).
  - 끝내 등록 안 된 건은 셀 수 없다: 초안은 7일 뒤 `tools/cron/cleanup_order_drafts.py`·`upload_cleanup._claim_expired_drafts` 가 조용히 지운다. **PUSH 기록이 있는 초안도 같이 지워진다.**

## 2. 목표 / 비목표

- 목표: (A) "PUSH 는 나갔는데 주문이 없다"가 정상 흐름에서 생기지 않게 한다. (B) 그래도 생긴 건은 사람이 반드시 알게 하고, 조용히 지워지지 않게 한다.
- 비목표: PUSH 만 하면 몰래 주문을 만드는 자동 저장(덜 채운 주문 생성·주인 규칙 깨짐 — 기각). 알림톡 단독 발송 흐름 변경. PC 주문 화면 PUSH 경로(`foms/api/channel/channel_integration.py`) 변경.

## 3. 설계

### 3.1 "등록하고 PUSH" 한 번에 (주 방어)

- 4단계 버튼 `실측 PUSH` → `등록하고 PUSH`.
- 순서: 초안 flush → 미리보기 시트(지금과 같음) → 확인 → **`POST /api/erp/order-draft/submit-and-push`** 한 번.
- 서버(새 라우트, `foms/api/erp_order_draft_send.py`):
  1. `api_submit_order_draft` 의 본체를 함수로 뽑아(`_submit_draft(db, uid, draft_key, payload)`) 그대로 재사용 — 필수 4항목·지방주문 검사, `create_order`, 첨부 승격, 발송 이력 승계, 초안 삭제.
  2. 커밋 후 **주문 기준** 실측방 PUSH(PC 경로와 같은 서비스)를 보낸다. 본문은 새 주문 `structured_data` 로 서버가 재조립(D2 유지).
  3. PUSH 실패 시 주문은 남긴다(되돌리지 않는다). 응답 `{success: true, data: {order_id, pushed: false, error}}` → 화면은 "주문은 등록됐고 PUSH 는 실패했어요. 주문 화면에서 다시 보내 주세요" 안내 후 주문 상세로 이동.
  4. 등록 검사 실패(VALIDATION)면 PUSH 를 보내지 않는다 — **이게 핵심: PUSH 가 나갔으면 주문이 반드시 있다.**
- 중복 방지: 같은 draft_key 재요청은 초안이 이미 지워져 `NO_DRAFT` → 화면은 최근 생성 주문으로 이동. PUSH 는 기존 `_is_duplicate_send` 창을 주문 이력에 똑같이 적용.
- 알림톡 버튼은 그대로 둔다(실측 전 고객 안내라 등록 전에 보낼 일이 있다). 단 알림톡도 같은 안전망(3.2) 대상.
- `PUSH 만` 버튼은 없앤다. 재푸시는 등록 후 주문 화면이 맡는다(3.3).

### 3.3 정보 변경 후 재푸시 (사용자 요청 2026-10-20)

현장 흐름: PUSH → 고객 통화로 날짜·시간·주소·규격이 바뀜 → 고쳐서 다시 PUSH. 경우를 나눠 본다.

1. **등록 후 변경 (합친 버튼 이후 기본 경로)** — 주문 화면 `PUSH → 실측 PUSH` 로 다시 보낸다. 이미 있다: `POST /api/channel/push-manual`(push_kind `measure_room`)가 재전송이면 변경 내용(change_note)을 **필수**로 받고 `channeltalk_push_measure_room.change_log` 에 쌓는다([foms/api/channel/channel_integration.py](../../foms/api/channel/channel_integration.py) `is_resend`). PC(`erp-order-shared.js`)·모바일 주문 탭(`erp_order_tab_mobile.html` 의 PUSH 선택창) 둘 다 된다. 알림톡도 주문 화면에서 다시 보낸다(`erp-alimtalk-send.js`).
   - 할 일: 등록하고 PUSH 성공 후 화면을 **주문 상세(모바일 주문 탭)** 로 보낸다 — 바뀌면 거기서 고치고 바로 재전송하도록. 성공 안내 문구에 "바뀌면 이 화면에서 고치고 PUSH 를 다시 누르세요" 한 줄.
2. **등록 전, 마법사 안에서 변경** — 합친 버튼은 누르는 순간 등록되므로 "등록 전 재푸시"가 생기지 않는다. 마법사에서 고친 내용은 처음 PUSH 에 그대로 실린다.
3. **옛 흐름에서 넘어온 초안**(배포 전에 초안에서 PUSH 해 둔 것) — 이력이 승계되므로 새 주문에선 첫 PUSH 가 **재전송**으로 판정된다. `submit-and-push` 는 승계된 이력에 `pushed` 가 있으면 확인 시트에서 변경 내용 입력을 받는다(마법사에 이미 있는 `change_note` 입력칸 재사용, `wizard-send.js`). 변경 내용이 비면 등록만 하고 PUSH 는 보내지 않는 선택지도 준다("내용이 같으면 PUSH 생략").
4. **본문이 두 경로에서 같아야 한다** — 지금 마법사 PUSH 는 **서버가** 초안으로 본문을 만들고(`build_measure_push_text`), 주문 화면 실측 PUSH 는 **화면의 변환 텍스트**를 보낸다(`erp-order-shared.js` `measure_room` 분기). 첫 PUSH 와 재푸시 모양이 달라 보이면 현장이 헷갈린다. 구현 때 같은 주문으로 두 본문을 나란히 떠서 비교하고, 다르면 주문 화면 쪽도 서버 조립(`build_measure_push_text(order.structured_data)`)으로 맞춘다 — 이번 범위에 포함.
5. **재푸시를 놓친 경우**(정보는 고쳤는데 PUSH 안 함) — 이번 범위 밖. 필요하면 다음 단계로 "실측일·시간·주소가 마지막 PUSH 뒤 바뀌었는데 재전송이 없음" 표시를 검토한다.

결론: 따로 보내는 `PUSH 만` 버튼은 재푸시 때문에 남길 필요가 없다 — 재푸시는 등록 후 주문 화면이 맡는다.

### 3.2 안전망: 놓친 초안 알림 + 지우지 않기

- 대상: `order_id IS NULL` 이고 `send_history` 에 발송 성공(`pushed`/`sent`)이 있는 초안.
- 알림: FOMS-cron 에 10분 간격 작업 추가 — 마지막 발송 30분 경과 + 미등록 초안 → 작성자에게 앱 알림(`Notification` → 기존 웹푸시 전달), 본문 "○○○ 고객 PUSH 는 나갔는데 주문 등록이 안 됐어요", 누르면 그 초안 이어쓰기로. 같은 초안에 1회만(초안 `send_history` 에 `reminded_at` 기록). 2시간 넘으면 관리자(ADMIN)에게도 1회.
- 만료 보호: cleanup 두 곳에서 발송 기록 있는 초안은 삭제 제외. 대신 관리자 화면 목록 "발송했는데 등록 안 된 초안"(작성자·고객명·발송 시각·이어쓰기/버리기). 버리기는 관리자 확인 후 삭제 + 감사 기록.
- 감사 기록 점검: 이번 조사에서 `CHANNEL_PUSH_DRAFT_SENT` 감사 행을 운영 `access_logs` 에서 찾지 못했다. 구현 전 저장 위치를 확인하고, 없으면 원인을 같이 고친다(근본 원인만).

## 4. 바뀌는 파일 (예상)

- `foms/api/erp_order_draft.py` — submit 본체 함수 추출(동작 불변).
- `foms/api/erp_order_draft_send.py` — `submit-and-push` 라우트, write guard manifest 등재.
- `foms/services/channel_draft_push.py` 또는 주문 PUSH 서비스 재사용.
- `templates/orders/wizard/step4_confirm.html`, `static/js/foms/wizard-send.js`, `wizard.js` — 버튼·흐름, 자산 핀 갱신.
- `tools/cron/` 새 리마인더 작업, `tools/cron/cleanup_order_drafts.py`, `foms/services/upload_cleanup.py` — 삭제 제외.
- 관리자 목록 화면(`foms/web/admin/`) + 템플릿.
- 마이그레이션 없음(기존 JSONB `send_history` 에 키 추가).

## 5. 검증 (완료 기준)

- 단위: submit-and-push — 검사 실패 시 PUSH 0회, 성공 시 주문 1 + PUSH 1, PUSH 실패 시 주문 유지, 재요청 시 주문 1 유지, 승계 이력에 pushed 가 있으면 change_note 없이는 PUSH 안 함.
- 재푸시: 등록 후 주문 화면 실측 PUSH 가 재전송으로 판정되고 change_log 1줄 추가. 마법사 첫 PUSH 본문과 주문 화면 재푸시 본문이 같은 주문에서 동일.
- cron: 30분 경과 미등록 초안만 알림, 1회만, 등록된 초안 제외. cleanup: 발송 기록 초안 보존.
- 로컬 PG 레인 + 실제 dev 서버에서 마법사 끝까지 수동 QA(모바일·PC), 스테이징 E2E(`claude_master`).
- `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1` exit 0, CI green.

## 6. 되돌리기

- 기능 플래그 `wizard_submit_and_push`(기본 꺼짐 → 스테이징 확인 후 켬). 끄면 옛 `PUSH` 버튼 흐름 그대로.
- 리마인더 cron 은 별도 플래그. 삭제 제외는 되돌려도 데이터 손실 없음.

## 7. 구현 결과 (2026-10-20, 설계와 달라진 점)

- **새 등록 API 를 만들지 않았다.** 마법사가 기존 `POST /api/erp/order-draft/submit` 을 먼저 부르고, 성공해야만 주문 기준 `POST /api/channel/push-manual`(push_kind `measure_room`)을 **text 없이** 부른다. 등록 검사가 실패하면 PUSH 요청 자체가 나가지 않는다. 주문 PUSH 정본 경로(receipt·OrderEvent·이력·감사)를 그대로 탄다.
- `push-manual` 의 `measure_room` 은 text 가 비면 서버가 `build_measure_push_text(order.structured_data)` 로 본문을 만든다(`_SERVER_COMPOSED_WHEN_EMPTY_KINDS`). PC 폼은 저장 전 화면 값을 text 로 보내므로 동작 불변. 두 본문은 원래 같은 규칙의 미러라(§3.3-4) 따로 바꿀 것이 없었다.
- 승계 이력에 이미 PUSH 가 있으면(옛 흐름 초안) 시트의 변경 사유 칸이 필수다. "내용이 같으면 PUSH 생략"은 별도 버튼 대신 기존 [주문 등록] 버튼이 맡는다.
- 알림 스윕은 새 루프 없이 WORKER 의 기존 1분 루프(`run_notification_escalation.py`, 운영 `FOMS_ESCALATION_LOOP_ENABLED=1` 확인)에 얹었다. 알림 종류 `DRAFT_SENT_NOT_REGISTERED` 는 기본 P1(폰 푸시) 목록에 넣었다. 누르면 모바일 홈(작성 중 줄)으로 간다.
- 기능 플래그는 두지 않았다 — 되돌리기는 커밋 revert 로 한다(마이그레이션 없음).
- 관리자 화면 `/admin/sent-unregistered-drafts`(관리자 메뉴 "발송 후 미등록 초안"): 목록 + 버리기(첨부 임시 파일 삭제 예약·감사 `ORDER_DRAFT_DISCARDED`).
- 발송 기록이 있는 초안은 만료돼도 정리 cron 이 지우지 않고, 작성자의 "작성 중" 줄에도 계속 보인다.
- 감사 기록 점검(§3.2 마지막 줄)은 이번에 못 했다 — 운영 `access_logs` 에서 `CHANNEL_PUSH_DRAFT_SENT` 행을 찾지 못한 원인은 별도 확인 과제로 남긴다.
