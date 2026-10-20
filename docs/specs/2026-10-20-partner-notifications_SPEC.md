# 협력사 알림 — 6단계 SPEC (2026-10-20 · 결정 반영 · 승인 대기)

등급: 코어 변경(알림 · 발송 · 권한) — Spec → 승인 → 구현.
선행: `docs/specs/2026-10-19-partner-foms-mode_SPEC.md` §5-6("협력사 알림 방식은 6단계에서 따로 정한다") · §9(그동안 CS 가 전화로 알린다).

## 0. 사용자 결정 (2026-10-20)

1. **알림 수단 = 웹 푸시.** 문자 · 알림톡은 쓰지 않는다(보내는 번호 · 브랜드 결정은 필요 없어짐).
2. **알릴 일 = 네 가지 모두**: 도면 확인 차례 · 시공일 정해짐/바뀜 · AS 방문일 정해짐 · 시공 끝(완공 사진).
3. **받는 사람 = 그 협력사의 사용 중인 직원 모두.**
4. **밤 시간 = 바로 보낸다.**

## 1. 지금 코드의 사실 (2026-10-20 조사)

1. 협력사 계정은 알림을 하나도 받지 못한다. 이유가 셋이다.
   - 받는 사람 고르기에서 전체 · 역할 · 팀 · 담당 이름 경로는 우리 직원만 고른다(`foms/services/notifications/recipients.py:34-36` `INTERNAL_USERS_ONLY`). 사람 id 로 직접 지정(`target_user_id`)만 협력사에게 닿는다(`:117-124`).
   - 벨 · 웹 푸시 주소가 문지기 허용 목록에 없다(`foms/services/auth/partner_scope.py:26-45`).
   - 실시간 연결이 협력사를 거부한다(`foms/api/channel/socketio_handlers.py:28-31`).
2. 알림톡 · 문자는 한 곳(`foms/services/kakao_alimtalk.py`, Solapi)으로 나간다. 지금 받는 사람은 전부 고객이고, 협력사 주문의 고객 발송은 막혀 있다(`:548-549`, `foms/api/share.py:1209-1210`). 직원 · 협력사 전화로 알림톡 · 문자를 보내는 길은 아직 없다.
3. 알림톡은 템플릿마다 카카오 검수가 필요하다. 기록된 검수 기간은 2 · 3 · 5 영업일이고, 등록한 뒤에는 고칠 수 없다(고치면 새 템플릿 · 새 검수). 문자(LMS)는 검수가 없다(`_solapi_send_text`, 지금은 공유 링크 문자만 쓴다).
4. 값: 알림톡 13원, 문자(SMS) 18원, 장문(LMS) 45원(부가세 별도, 2026-07 확인).
5. 운영에서 알림톡 · 문자는 **웹 요청 안에서 바로** 보낸다. 운영 SIDEFX 워커에는 `SOLAPI_*` 키가 없다(`docs/runbooks/sidefx-worker-ops.md:23-36`). 워커로 보내려면 키 복사 · 재배포가 먼저다.
6. 스테이징도 진짜 문자를 보낸다(테스트 모드 없음). 시험 계정 연락처(`010-0000-0001` 같은 값)로 실제 발송이 나갈 수 있다.
7. 웹 푸시는 사람 id 기준으로 나가지만(`push_sender.py:540-611`), 아이폰은 "홈 화면에 추가"를 해야 받는다. 서비스 워커가 `/erp/` 주소만 열고(`static/sw.js:424-435`) 협력사 화면에는 매니페스트 · 등록 스크립트가 없다.
8. **알릴 시점**:
   - 도면 확인 차례: 우리 CS 의 "도면 받음 확인"(`foms/api/drawing/erp_orders_draftsman.py:293` `api_order_confirm_drawing_receipt`)이 `drawing_status='CONFIRMED'` 와 도면→고객컨펌 이동을 함께 하는 유일한 곳이다. 협력사 수정 요청 뒤 다시 확정될 때도 여기를 지난다. 지금 이 자리에는 알림이 없다.
   - 시공일: 모든 저장 경로가 날짜 동기화 훅(`foms/services/order_date_sync.py:558-604`)에서 `OrderEvent CONSTRUCTION_DATE_CHANGED`(이전 · 이후 날짜, 거래당 1건)를 남긴다. 시공팀 알림(`shipment_change.py`)이 이미 이 훅을 쓴다.
   - AS 방문일: AS 화면은 `update_order_field`(`as_visit_date`, `foms/api/orders/field_update.py:766-788`)로 저장하고, `AS_SCHEDULE` 명령(`as_cycle_service.schedule_as_cycle`)은 화면에서 부르지 않는다. → **지금 협력사 화면의 "방문 예정"은 AS 화면에서 잡은 날짜를 못 본다**(`foms/services/partners/completion.py:55-77` 가 `AS_SCHEDULE` 기록만 읽는다). 이번에 함께 고친다.
   - 단계 이동: 모든 엔진 이동이 `STAGE_NOTIFICATION` outbox 행을 남기지만 아무도 배달하지 않는다(`tools/ops/run_domain_side_effect_outbox.py:321-325`).
9. 머리 메뉴 "도면 확인 N"(`order_list.partner_turn_count`)은 고객컨펌 단계만 센다. 협력사가 수정 요청을 보내 도면팀 차례(`RETURNED`)여도 협력사 차례로 센다. 도면 상태는 주문 데이터(JSONB) 안에만 있다.

## 2. 설계 원칙

- **받는 사람은 사람 id 로.** 협력사 담당은 SALES 배정(협력사 직원)이다. 이름 문자열(`이름 (회사명)`)로 맞추지 않는다.
- **우리 직원 알림은 그대로.** 넓은 경로의 `INTERNAL_USERS_ONLY` 는 건드리지 않는다.
- **알림 실패가 일을 막지 않는다.** CS 의 "도면 받음 확인" · 시공일 저장은 알림이 실패해도 성공한다.
- **같은 알림은 한 번.** 주문 · 알릴 일 · 값(날짜 · 회차)으로 중복을 막는다.
- **협력사가 고른 기기에만.** 웹 푸시는 협력사 직원이 직접 "알림 받기"를 누른 기기로만 간다(전화번호를 쓰지 않는다).

## 3. 알림 수단 (비교)

- **문자(LMS)** — 검수 없이 바로 쓸 수 있다. 모든 전화가 받는다. 건당 45원(긴 글). 보내는 번호는 회사 대표 번호.
- **알림톡** — 카카오톡으로 온다. 건당 13원, 문자보다 믿음이 간다. 템플릿 검수 2~10 영업일, 검수 전에는 못 쓴다. 실패하면 문자로 대신 보내기(대체발송)는 콘솔에서 템플릿마다 켠다.
- **웹 푸시** — 공짜. 협력사가 알림 허용을 눌러야 하고, 아이폰은 홈 화면 추가가 필요하다. 협력사 화면용 서비스 워커 · 등록 화면을 새로 만들어야 한다.
- **화면 안 알림 목록** — 협력사 화면 머리에 종 · 목록. 들어와야만 보인다(기록 · 다시 보기용).

**결정: 웹 푸시**(§0-1). 협력사 직원이 자기 휴대폰 · PC 에서 "알림 받기"를 한 번 눌러야 받는다. 아이폰은 협력사 화면을 홈 화면에 추가한 뒤 눌러야 한다.

## 4. 알릴 일 (결정 — 네 가지 모두)

| 알릴 일 | 언제 | 문구 예 |
|---|---|---|
| 도면 확인 차례 | CS "도면 받음 확인" 직후(처음 · 수정 뒤 다시 모두) | `[라홈] 홍길동 고객(#1234) 도면이 올라왔습니다. 고객과 확인 후 승인 또는 수정 요청해 주세요. <주문 화면 주소>` |
| 시공일 정해짐 · 바뀜 | `CONSTRUCTION_DATE_CHANGED` 직후(처음 정해질 때 포함) | `… 시공일이 10/24(금)로 정해졌습니다(바뀜: 10/22 → 10/24). 고객에게 알려 주세요.` |
| AS 방문일 정해짐 | AS 방문일 저장 직후 | `… AS 방문이 10/25(토) 14:00 로 잡혔습니다. 고객에게 알려 주세요.` |
| 시공 끝 | 시공 완료(→CS) 직후 | `… 시공이 끝났습니다. 완공 사진을 확인할 수 있습니다.` |

푸시 제목은 "협력사 주문 알림", 본문은 위 문구(앞의 `[라홈]` 없이). 누르면 협력사 주문 화면(`/partner/orders/<id>`, 로그인 필요). 고객 이름은 성+가운데 가림(`홍*동`) — 잠금 화면에 보이는 매체라서.

## 5. 서버 · 화면에서 바뀌는 것

1. **협력사 알림 서비스** `foms/services/partners/notify.py` `notify_partner_staff(db, order, event, values)`: 협력사 주문(`partner_org_id`)이면 그 회사의 사용 중인 직원마다 `Notification(target_type="USER", target_user_id=직원)` 한 줄 + `fan_out_new_notification`. 커밋은 호출자. 커밋 뒤 `enqueue_push_for_notification`(기존 RQ 경로). 같은 일 중복은 주문 · 알릴 일 · 값으로 막는다(같은 키의 알림이 이미 있으면 만들지 않음).
2. **알림 종류 4개**: `PARTNER_DRAWING_READY` · `PARTNER_CONSTRUCTION_DATE` · `PARTNER_AS_VISIT` · `PARTNER_CONSTRUCTION_DONE`. 푸시 대상 종류(`push_sender._DEFAULT_P1_TYPES`)에 넣고, 누르면 열 주소는 `/partner/orders/<id>`(`push_sender._deep_link` · `static/sw.js` `sanitizePushDeepLink` 가 `/partner/` 를 허용하게).
3. **알릴 자리 연결**(협력사 주문만, 실패해도 원래 일은 성공):
   - 도면 확인 차례: `api_order_confirm_drawing_receipt` 커밋 뒤(처음 · 수정 뒤 다시).
   - 시공일: 날짜 동기화 훅의 `CONSTRUCTION_DATE_CHANGED`(처음 정해질 때 포함) — 시공팀 알림(`shipment_change.py`)과 같은 커밋 앞뒤 방식.
   - AS 방문일: `field_update` `as_visit_date` 저장 · `schedule_as_cycle` 뒤.
   - 시공 끝: `api_construction_complete` 커밋 뒤.
4. **구독 길 열기**: 우리 푸시 주소 4개를 협력사 문지기 허용 목록에 넣는다 — `notifications_push.vapid_public_key` · `notifications_push.subscribe`(자기 기기만, 남의 기기는 403) · `notifications_push.push_test`(비관리자는 자기에게만) · `notifications_push.push_event`(자기 알림만). 쓰기 정책 엔진에도 `CREATE_OWN_PUSH_SUBSCRIPTION` · `OWN_PUSH_SELF` 를 협력사 허용 정책에 더한다. 넷 다 "자기 것만" 다루는지 시험으로 고정한다(다른 사용자 기기 · 알림 거부).
5. **협력사 화면 "알림 받기"**: 머리줄에 종 버튼 — 서비스 워커(`/static/sw.js`) 등록 → 권한 → 구독 → 시험 알림. 상태 표시(켜짐 · 꺼짐 · 막힘), 아이폰은 "홈 화면에 추가" 안내. 협력사용 매니페스트(`static/manifest-partner.json`, 시작 주소 `/partner`). 새 JS `static/js/partner/partner-push.js`.
6. **우리 쪽에서 보이게**: 관리자 "협력사 관리" 화면에 직원마다 "알림 받는 기기 N대" — CS 가 누구에게 전화해야 하는지 안다.
7. **함께 고칠 것**: 협력사 AS 진행의 "방문 예정"이 `schedule.as_visit` 도 읽게(§1-8). 머리 메뉴 "도면 확인 N"은 도면 상태 `CONFIRMED` 일 때만 센다(§1-9).

## 6. 단계

1. 6-1: 구독 길 · "알림 받기" 화면 · 알림 서비스 · "도면 확인 차례" 알림 · 관리자 화면 기기 수 · 함께 고칠 것 2개.
2. 6-2: 시공일 · AS 방문일 · 시공 끝 알림.

## 7. 바꾸지 않는 것

- 우리 직원 알림 경로 · 벨 · 웹 푸시 · 실시간 연결의 협력사 차단.
- 협력사 주문의 고객 발송 차단(`partner_order` 409).

## 8. 검증

- 시험: 같은 회사 사용 중인 직원 모두에게 한 줄씩(꺼진 직원 · 다른 회사 · 우리 직원 대조군), 같은 일 두 번 → 한 번, 협력사 아닌 주문 → 0건, 알림 실패여도 원래 요청 성공, 푸시 주소 4개가 남의 기기 · 남의 알림을 거부, 문지기 허용 목록 · 쓰기 목록 · 정책 엔진 시험, 누르면 `/partner/orders/<id>` 로 감.
- 스테이징: CLAUDE-TEST 협력사 계정으로 PC 브라우저에서 "알림 받기" → 시험 알림 → CS 계정으로 "도면 받음 확인" → 푸시 1건 · 누르면 그 주문 화면. 끝나면 구독 해제 · 시험 계정 끄기.
- `scripts/ops/pre_push_smoke.ps1` exit 0, CI green.

## 9. 남는 위험

- 협력사 직원이 "알림 받기"를 누르지 않으면 아무것도 못 받는다 → 관리자 화면의 기기 수로 CS 가 확인하고, 0대인 회사는 지금처럼 전화.
- 아이폰은 홈 화면 추가가 필요하다(iOS 16.4 이상) → 화면 안내.
- 브라우저가 구독을 버리면(기기 교체 · 데이터 삭제) 조용히 끊긴다 → 기기 수가 줄어드는 것으로 보인다.
- 운영 웹 푸시 키 · 스위치(`FOMS_WEB_PUSH_ENABLED` · `VAPID_*`)는 이미 켜져 있다(우리 직원이 쓰는 중).

## 10. 6-1 구현 기록 (2026-10-20)

- 승인: 2026-10-20 사용자 "이대로 6-1 시작".
- 알림 종류 · 문구 · 열 주소 `foms/services/notifications/partner_push.py`(종류 4개, 고객 이름 가림 `mask_customer_name`, `/partner/orders/<id>`). `push_sender`: 협력사 종류는 env(`FOMS_PUSH_P1_TYPES`)로 P1 집합을 덮어써도 늘 보내고(`_should_push`), 누르면 협력사 주문 화면(`_deep_link`), 푸시 문구는 협력사 알림 서비스가 만든 문장(`_build_payload` — 주소 · 메모 없음).
- 알림 서비스 `foms/services/partners/notify.py`: `create_partner_notifications`(그 회사 사용 중인 직원마다 `target_type=USER` 한 줄 + `fan_out`, 같은 주문 · 종류 · 문장이 10분 안에 있으면 건너뜀), `notify_partner_staff`(커밋 → 푸시 예약, 실패는 기록만), `notify_partner_drawing_ready`(고객컨펌 단계일 때만), `partner_push_device_counts`.
- 연결: `api_order_confirm_drawing_receipt` 커밋 직후 한 줄(`erp_orders_draftsman.py` — 파일 500줄 상한 때문에 판정은 서비스 안에).
- 구독 길: 문지기 허용 목록에 `notifications_push.vapid_public_key` · `subscribe` · `push_test` · `push_event`, 정책 엔진 협력사 허용에 `CREATE_OWN_PUSH_SUBSCRIPTION` · `OWN_PUSH_SELF`. 벨 목록 · 푸시 관리 주소는 그대로 막힘(시험 대조군). `static/sw.js` 가 `/partner/` 주소를 연다.
- 화면: 협력사 머리줄 "알림 받기"(`static/js/partner/partner-push.js` — 서비스 워커 등록 · 권한 · 구독 · 시험 알림 · 끄기, 아이폰 홈 화면 안내, 막힘 안내), 협력사 매니페스트 `static/manifest-partner.json`(시작 `/partner`). 관리자 "협력사 관리"에 직원별 "알림 받는 기기 N대 / 없음".
- 함께 고침: 협력사 AS 진행 "방문 예정"이 진행 중 AS 건이면 `schedule.as_visit` 도 읽는다(`completion._visit`). 쉬운 단계 · 내 차례 · 머리 메뉴 수는 고객컨펌이라도 도면 확정(`CONFIRMED`) 전이면 "도면 작업 중"(`partner_stage_label(drawing_confirmed=...)`, 목록은 고객컨펌 주문만 JSONB 를 읽음).
- 시험 `tests/security/test_partner_push.py` 10건 + `test_partner_gate` 정책 집합 갱신.

## 11. 6-2 구현 기록 (2026-10-20)

- 시공일: `foms/services/partners/notify_listeners.py` — 날짜 동기화 훅이 남긴 시공일 변경(`pending_construction_date_changes`)을 `before_commit` 에서 읽어 같은 트랜잭션에 협력사 알림 줄을 만들고, `after_commit` 에서 푸시를 예약한다(시공팀 출고 알림과 같은 방식, 협력사 주문만, 처음 정해질 때도). 등록은 `order_date_sync` 의 소비자 배선 끝. 문장: "시공일이 ○로 정해졌습니다(바뀜: ○ → ○)".
- AS 방문일: `field_update` 의 `as_visit_date` 저장 커밋 뒤 `notify_partner_as_visit`(`schedule.as_visit` 날짜 · 시간).
- 시공 끝: `api_construction_complete` 커밋 직후 `notify_partner_construction_done`.
- 세 알림 모두 `notify._after_commit` 공통 입구 — 판정이 실패해도 끝난 일을 500 으로 바꾸지 않는다. 같은 문장 10분 안 중복은 건너뜀.
- 시험 `tests/security/test_partner_push_events.py` 4건(시공일 처음 · 바뀜과 협력사 아닌 주문 대조군, AS 화면 방문일 저장 경로, 시공 끝과 라우트 연결).
