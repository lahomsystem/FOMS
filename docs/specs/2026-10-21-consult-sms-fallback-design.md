# '상담 먼저' 알림톡 — 카톡 실패 고객에게 링크 문자 자동 발송 · 옛 서식 정리

- 날짜: 2026-10-21
- 상태: 설계(사용자 확인 전)
- 앞선 설계: `docs/specs/2026-10-20-alimtalk-consult-first-design.md`

## 1. 왜

- '상담 먼저' 알림톡은 링크가 없고, 솔라피 문자 대체발송을 끄고 보낸다(`disable_sms=True`). 대체 문자는 알림톡 본문 그대로라 링크가 없어 쓸모가 없기 때문이다.
- 그래서 지금은 카톡을 못 받는 고객(카톡 미사용·채널 차단·번호 불일치)에게 **아무것도 가지 않는다**.
- 사용자 결정(2026-10-21): "카톡 실패한 고객은 문자로 보내야지."
- 솔라피 공개 문서에서는 대체 문자 문구를 메시지마다 바꾸는 방법을 확인하지 못했다. 그래서 대체발송은 우리 서버가 맡는다.

## 2. 무엇을 하나

### 2-1. 카톡 실패 → 링크 문자 자동 발송

1. **발송 때 메시지 번호를 남긴다.** `api_share_send_alimtalk` 는 지금 `ka._solapi_send` 가 돌려준 벤더 message id 를 버린다. '상담 먼저' 발송이면 `SHARE_ALIMTALK.payload.consult.message_id` 에 남긴다.
2. **워커가 1분마다 결과를 묻는다.** 새 루프 `share_consult_sms_fallback` 를 `tools/ops/worker_supervisor.py` 에 단다(다른 루프와 같은 `--loop --interval 60` 모양, env `FOMS_SHARE_CONSULT_SMS_FALLBACK_ENABLED=1` 일 때만 켬).
   - 대상은 '상담 먼저'로 보낸 `SHARE_ALIMTALK` 가운데 다음을 모두 만족하는 것이다.
     - `status=sent`
     - `message_id` 가 있다.
     - 보낸 지 90초 이상 30분 이하다.
     - 아직 판정하지 않았다(`consult.kakao_result` 없음).
   - 솔라피에 그 message id 의 상태를 묻는다(측정 알림톡 `_solapi_lookup_channel` 와 같은 `get_messages` 경로).
3. **판정**
   - `4000`(수신 완료) → `kakao_result=delivered`. 끝.
   - `2000`·`3000`(접수·전송 중) → 다음 바퀴에 다시 묻는다. 30분이 지나도 그대로면 `kakao_result=unknown` 으로 닫고 문자는 보내지 않는다(이중 발송보다 안전).
   - 그 밖의 코드(카톡 실패) → `kakao_result=failed` 로 표시하고 문자를 보낸다.
4. **문자 내용과 보내는 방법**
   - 도면 보내기 창의 [회사 문자]와 같다.
     - 링크를 새로 발급한다. 종류는 알림톡 때와 같아서 도면·계약서·묶음 중 하나다.
     - 본문은 `share_link_message(order, kind, url, brand)` 로 만든다.
     - `ka._solapi_send_text` 로 LMS 를 보낸다. 발신 번호는 [회사 문자]와 같은 `_resolve_sender` 를 쓴다. 담당자의 등록 발신번호(`users.sender_phone`)가 있으면 그 번호로, 없으면 브랜드 대표번호로 보낸다(사용자 결정 2026-10-21: "ERP 등록 담당자 번호로"). 2026-10-21 운영 기준으로 발신번호가 등록된 직원은 이시영 1명이다.
   - 이력에는 기존 회사 문자와 같은 `SHARE_SMS` 이벤트를 남기고, `payload.source='consult_fallback'` 로 구분한다.
   - 도면 탭 발송 상태 줄에는 "카톡 실패 → 문자로 보냄"으로 보인다(기존 상태 줄이 `SHARE_SMS` 를 이미 읽는다).
5. **겹침 막기**
   - 판정과 발송은 `SHARE_ALIMTALK` 행을 잠그고(`with_for_update`) 한다.
   - `kakao_result` 를 먼저 쓰고 커밋한 뒤에 문자를 보낸다. 워커가 둘이어도 한 번만 나간다.
   - 문자가 실패하면 `consult.sms_fallback={status: failed, error}` 를 남긴다. 다시 보내지 않고, 도면 탭 상태 줄에 실패로 보인다. 영업이 [회사 문자]·[내 폰 문자]로 직접 보낸다.
6. **하지 않는 것**
   - 카톡은 받았는데 [문서 받기]를 안 누른 고객에게 문자를 보내지 않는다. 카톡을 받은 고객은 상담으로 이어 가는 것이 이 기능의 목적이다.
   - 협력사 주문(`is_partner_order`)은 지금처럼 대상이 아니다.

### 2-2. ERP 주문 화면 [공유] 창도 '상담 먼저'로

- `static/js/orders/erp-share.js` 의 두 곳(빠른 알림톡 `_quickAlimtalk`, 창 안 `_sendAlimtalk`)에서 `consult: false` 를 뺀다. 그러면 서버가 도면 탭과 같은 '상담 먼저'로 보낸다.
- 확인 문구를 고친다. 예: "고객에게 도면 알림톡을 보낼까요? 고객이 [문서 받기]를 누르면 상담으로 링크가 갑니다."
- 알림톡 버튼 툴팁 "(실패 시 문자 대체발송)"은 그대로 둔다. 2-1 이 켜지면 사실이 된다.

### 2-3. 옛 서식 정리 (2-1·2-2 가 운영에서 확인된 뒤)

- 솔라피에서 옛 서식 5개를 지운다.
  - 고객 문서 공유 링크 (하우드)(사본)
  - 고객 문서 공유 링크 (라홈)(사본)
  - 고객 문서 공유 링크 통합 (하우드)
  - 고객 문서 공유 링크 통합 (라홈)
  - 고객 문서 공유 링크 통합 (하우드)(사본)
- "상담 먼저 (하우드·라홈)"(`KA01TP261020024519461bWqdjUHSkFA`)은 지우지 않는다. 사용자 결정(2026-10-21)으로 **하우드 '상담 먼저' 서식을 이것으로 바꿨다**(운영·스테이징 web env `SOLAPI_TEMPLATE_SHARE_CONSULT_ID_HAUD`, 같은 날 재배포). 대신 "상담 먼저 (하우드)"(`KA01TP261020024519280XniXkJcLYr4`)는 이제 쓰지 않으니 지울 대상에 넣는다.
- 운영·스테이징 web env 에서 `SOLAPI_TEMPLATE_SHARE_ID_{HAUD,LAHOM}`·`SOLAPI_TEMPLATE_SHARE_BOTH_ID_{HAUD,LAHOM}` 를 뺀다.
- 코드의 옛 경로(`consult: false`·`SHARE_ID`·`SHARE_BOTH_ID`)는 이번에는 남긴다. env 가 없으면 '알림톡 미설정'으로 막히므로 조용히 옛 서식으로 새는 일은 없다. 코드 정리는 다음 묶음이다.

## 3. 바뀌는 파일

| 파일 | 내용 |
|---|---|
| `foms/api/share.py` | '상담 먼저' 발송 때 `consult.message_id` 저장 |
| `foms/services/share_consult_fallback.py`(새) | 대상 찾기 · 솔라피 상태 판정 · 링크 발급 · 문자 발송 · 기록 |
| `scripts/maintenance/run_share_consult_fallback.py`(새) | `--loop --interval` 실행기(escalation 실행기와 같은 모양) |
| `tools/ops/worker_supervisor.py` | env 켜짐 조건으로 루프 등록 |
| `foms/services/orders/drawing_customer_send_view.py` | 상태 줄에 "카톡 실패 → 문자로 보냄" |
| `static/js/orders/erp-share.js` | `consult: false` 제거 · 확인 문구 |
| 시험 | 판정 3갈래(성공·실패·대기 30분), 이중 발송 막기, 문자 실패 기록, 공유 창 요청 본문 |

## 4. 켜는 순서

1. deploy 에 올리고 CI 를 확인한다. 스테이징 WORKER 에 `FOMS_SHARE_CONSULT_SMS_FALLBACK_ENABLED=1` 을 넣는다.
2. 스테이징 시험: 카톡이 없는 번호로 '상담 먼저'를 보내 1~2분 안에 링크 문자가 오는지 본다. 카톡 미사용 번호를 사용자에게 받아야 한다.
3. 운영 승격 PR → 운영 WORKER env 를 켠다 → 운영 시험 1회.
4. [공유] 창이 '상담 먼저'로 나가는 것을 확인한 뒤 2-3 정리를 한다.

## 5. 정한 것 (사용자 2026-10-21)

- 문자 발신 번호: 담당자 등록 발신번호 우선, 없으면 브랜드 대표번호. 담당자 번호로 보내려면 그 번호를 솔라피 발신번호로 등록하고, ERP 사용자 정보의 발신번호 칸에 넣어야 한다.
- 문자 비용: 카톡 실패 건에만 LMS 1통.
- 하우드 '상담 먼저' 서식 = "상담 먼저 (하우드·라홈)".
