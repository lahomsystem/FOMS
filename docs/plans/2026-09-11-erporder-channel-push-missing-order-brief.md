# 조사 브리프 — ERP 주문 화면에서 채널톡 푸시 후 주문이 FOMS에 저장되지 않은 건 (2026-09-11)

> 초안이다. CEO 에이전트는 이 브리프를 고쳐서 워커 브리프를 확정한다.
> **읽기 전용 조사다. 코드 편집·DB 쓰기·git 조작·배포 금지.**

## 1. 사건

사용자가 FOMS ERP 주문 화면(erporder)에서 아래 실측 건의 채널톡 푸시를 보냈는데,
FOMS에 주문이 저장되어 있지 않다. 푸시 후 저장을 안 한 것인지, 버그로 누락된 것인지
로그·DB 증거로 판정한다.

푸시 본문(사용자 제공, 채널톡 "FOMS안중훈" 봇, 10:40 AM):

- 실측일 2026-09-10 / 시간 조율 / 시공일 상담
- 고객명: 이광일
- 발주사: 안중훈
- 주소: 서울 중구 동호로14길 35
- 연락처: 010-6210-8486
- 담당자: 한용희
- 품목 1: 부엌가구 3320, 항목 견적 2,415,000원 (국산MMA 인조대리석 포함, 기본수전·후드·싱크볼 포함)
- 품목 2: 아일랜드 1600, 항목 견적 820,000원 (국산 MMA 인조대리석 포함, 측·후 EP 포함)
- 출고가 3,235,000원 / 잔금 3,235,000원

## 2. 확정된 앵커 (총괄이 직접 확인함)

- `foms/api/erp_order_draft_send.py:1-20` — 모듈 docstring. 마법사 **초안(등록 전)** 발송 API.
  설계 D1: 대상은 `Order` 가 아니라 `OrderDraft(draft_key)` — "버튼이 몰래 주문을 만들지 않는다".
  즉 **초안 단계 채널톡 푸시는 설계상 주문 행을 만들지 않는다.** 이 사건의 1순위 가설.
- 초안 발송 라우트 4개: `foms/api/erp_order_draft_send.py:217,249,310,414`
  (`/api/erp/order-draft/alimtalk/preview|send`, `/channel-push/preview|send`).
- 초안 CRUD·등록: `foms/api/erp_order_draft.py:263(GET) 287(PUT) 418(DELETE) 448(attachments) 547(submit)`.
  `submit` 이 실제 주문을 만드는 지점이다.
- `models.py:1758` `class OrderDraft` — `order_drafts` 테이블. `user_id`,`order_id`(nullable),
  `draft_key`, `payload`, `send_history`(서버만 씀), `expires_at`(**TTL 7일**), unique(`user_id`,`draft_key`).
- `models.py:1794` `class ChannelDeliveryLog` — `channel_delivery_logs`. 푸시 1건마다 행이 남는다:
  `event_key`,`source_type`,`source_id`,`target_type`,`target_id`,`status`,`last_error`,
  `rendered_text_snapshot`,`actor_type`,`actor_id`,`order_id`(nullable),`request_id`,`created_at`,`sent_at`.
  **이 표가 "푸시가 실제로 나갔는가 / 그때 주문에 묶여 있었는가" 의 1차 증거다.**
- 서비스: `foms/services/channel_draft_push.py`, `foms/services/channel_dispatch.py`,
  `foms/services/channel_delivery.py`, `foms/services/channel_measure_message.py`.

## 3. 운영 데이터 접근 (검증된 레시피)

- `railway` CLI 는 `/c/nvm4w/nodejs/railway`, v4.27.5. python `subprocess` 에서는 shim 때문에
  `FileNotFoundError` — **bash 로 파일에 덤프한 뒤 읽어라.**
- 저장소 디렉토리에서 `railway link` 금지(링크 오염). 각자 자기 스크래치패드 하위 디렉토리에서 한다.
- `railway link --project FOMS-PRODUCTION` → `railway variables --service Postgres --json > pgvars.json`
  → psycopg2 로 `DATABASE_PUBLIC_URL` 접속, **`conn.set_session(readonly=True)` 필수**.
- 쓰기 쿼리·스키마 변경·`claude_master` 로그인 전부 금지. 이번 건은 읽기 조회만이다.

## 4. 함정

- `Order.active_filter()` 는 `is_erp_order AND (status='DRAFT' OR meta.draft=true)` 를 **화면에서 숨긴다**.
  DB에 행이 있어도 목록에 안 보인다 — "저장 안 됨" 의 가짜 원인이 될 수 있으니 raw 조회로 확인하라.
- 대시보드 검색 오탐: 검색어가 input `value=` 에 에코된다. HTML 안에 이름이 있다고 0건이 아니다.
- 시각은 KST/UTC 를 반드시 구분해 적어라. 푸시는 KST 2026-09-10 10:40 근처, DB `created_at` 은 naive UTC 가능.
- 소프트 삭제(`soft_delete_order`)·휴지통으로 갔을 가능성도 0건 판정 전에 배제하라.
- 초안 TTL 7일이라 2026-09-10 초안은 아직 살아 있어야 한다. 없다면 그 자체가 증거다.

## 5. 판정해야 할 질문

1. 푸시는 실제로 나갔는가? 언제, 누구(actor)가, 어느 라우트로, `source_type/source_id` 는 무엇인가?
2. 그 시점에 주문 행이 있었는가? (`channel_delivery_logs.order_id` 가 NULL 이면 초안 발송)
3. 지금 orders 에 이 고객 행이 있는가? (있는데 안 보이면 필터/삭제 문제, 없으면 미등록 또는 등록 실패)
4. 초안 행(`order_drafts`)이 남아 있는가? `send_history` 는? `order_id` 는 NULL 인가?
5. 등록(`/order-draft/submit`) 요청이 로그에 있는가? 있었다면 응답 코드는? 5xx·예외가 있었는가?
6. 결론: (a) 사용자가 등록을 안 눌렀다 (b) 등록을 눌렀는데 실패했다 (c) 저장됐는데 화면에서 사라졌다.
   각 결론은 **증거 인용(표·행·로그 줄)** 으로 뒷받침해야 한다. 증거 없으면 "판정 불가" 라고 써라.
