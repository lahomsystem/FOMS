# 당일 실측 긴급 추가 알림 — SPEC (승인됨)

> 2026-09-23 · 상태: **승인됨(2026-09-23 사용자 — §8: 본인에게도 보냄, 멘션은 스테이징 실측 뒤 재질의, 기존 결함 2건 함께 수정)** · 조사 근거: `docs/plans/2026-09-23-same-day-measure-urgent-alert-research.md`
> 등급: 코어 변경(알림·전역 flush 훅·외부 발송) → Spec → 승인 → 구현.

## 1. 무엇을
실측 일정이 **오늘(KST)** 로 새로 생기거나 바뀌면, 영업 전원에게 세 길로 동시에 알린다.
| 길 | 받는 곳 | 모양 |
|---|---|---|
| A 채널톡 | 새 **"긴급" 팀챗 방**(사용자가 만들고 영업 초대) | 봇 글: `[긴급 실측] 오늘 {시간} · {고객명} · {지역} · 담당 {담당}` + 주문 링크. 휴대폰 채널톡 앱 푸시·배지 |
| B FOMS 화면 | FOMS 를 열어 둔 영업 | 화면 가운데 확인창(도면팀 interrupt 등급 재사용). **각자 "확인"** 을 눌러야 닫힘 |
| C 웹 푸시 + 앱 배지 | FOMS 를 홈 화면에 설치·알림 허용한 영업 | 잠금화면 알림 + 앱 아이콘 숫자 배지(아이폰 16.4+ 숫자, 안드로이드 대부분 점) |

하지 않는 것: 알림톡, 카카오톡(공식 자동 발송 수단 없음), 문자(SMS), "내일" 추가 알림.

## 2. 감지 (트리거)
- 위치: 전역 before_flush 훅 `foms/services/order_date_sync.py:459-545` 에 실측일 비교를 더한다(시공일 변경 감지와 같은 틀). 모든 ORM 저장 경로 9곳을 한 번에 덮는다.
- 조건: 주문이 드래프트가 아니고, 이번 저장으로 **실측일 집합에 오늘(KST)이 새로 들어왔다**(이전 집합에 오늘 없음 → 이후 집합에 오늘 있음).
  - 신규 주문: 이전 = 빈 집합으로 본다(현재 훅의 신규 제외 :501-506 을 이 판정에 한해 푼다).
  - 드래프트 승격(마법사 제출): 날짜 차이가 안 보이므로 DRAFT → 비DRAFT 전환을 함께 감지.
  - 시간만 바뀐 경우·오늘 외 날짜 변경은 대상 아님.
- 발송은 **커밋 뒤에만**(롤백되면 안 보냄): `foms/services/notifications/shipment_change.py:462-563` 의 before_commit/after_commit/soft_rollback 패턴 재사용.
- 중복 방지: outbox 멱등 키 `meas_same_day:{order_id}:{YYYY-MM-DD}` (부분 고유 인덱스 `models.py:2680-2683`). 같은 날 지웠다 다시 넣어도 1회.
- 실제 외부 발송(채널톡·웹 푸시)은 SIDEFX outbox 핸들러가 한다(`tools/ops/run_domain_side_effect_outbox.py` 에 `MEAS_SAME_DAY_ALERT` 등록 — 알림톡 핸들러 선례). 요청 스레드에서 외부 API 를 부르지 않는다.

## 3. 받는 사람
- `Notification(target_type='TEAM', target_team='SALES')` + `recipients.py` 팬아웃. 이때 `MEASURE` 팀 표기 계정도 SALES 로 정규화(`order_mutation_policy.py:47,241-283` 규칙 재사용) — 지금 `recipients.py:70-76` 은 누락.
- 추가한 본인도 받는다(동료가 넣은 건지 본인이 넣은 건지 영업 입장에서 구분 불필요 — 결정 필요 시 §8).

## 4. A 채널톡
- 새 환경변수 `CHANNEL_GROUP_URGENT_MEASURE`(긴급방 그룹 id). **기본값 `209989`**(채널톡 "단체방" — https://channel.works/haud/groups/단체방-209989, 2026-09-23 사용자 지정). 다른 방 라우팅처럼 `channel_policy.py` 에 기본값을 두고 환경변수로 덮는다. 환경변수를 빈 문자열로 두면 채널톡 길만 끄고 B·C 는 보냄(로그 경고 1회).
- 발송: 기존 `send_group_message`(`foms/services/channel_client.py:262-313`), 봇 이름 `FOMS긴급`. 본문은 서버 조립(고객명·지역=주소 앞 2토막·시간 원문·담당·링크). 이력은 `structured_data.channeltalk_push_urgent_measure`(서버 소유 키 — `_OPERATIONAL_TOP_LEVEL_KEYS` 등재).
- 멘션(@all): 공개 문서로 봇 멘션이 "중요 알림"이 되는지 확인 불가 → **1차는 멘션 없이** 보내고 영업 전원이 긴급방 알림을 "모든 알림 받기"로 설정(운영 안내). 스테이징에서 멘션 실측 후 2차 결정.
- 운영 확인: WORKER·SIDEFX 에 `CHANNEL_APP_SECRET`/`CHANNEL_ID` 존재(import 시점 상수).

## 5. B 화면 확인창
- 서버: 새 알림 유형 `MEASURE_SAME_DAY_ADDED`, `emit_erp_notification_to_users` 로 payload `interrupt: True` + `{customer_name, area, time, manager, added_by, added_at, order_url}`.
- 화면: `static/js/foms/foms-drawing-alert.js` 의 `show()` 를 유형별 제목·링크로 일반화(도면 동작 불변). 분기 두 곳(`layout_head.html:931`, `static/js/runtime/layout-head-init.js:152,167`)을 같이 고친다(계약 테스트가 비교).
- 보강 3건: ① 여러 탭 중복 방지(BroadcastChannel `foms-alerts` — 한 탭에서 확인하면 같은 사람의 다른 탭도 닫힘, 소리는 보이는 탭만) ② 소리 준비(첫 클릭 때 AudioContext 하나 만들어 재사용) ③ 끊긴 동안 온 알림 재표시(재연결·화면 복귀 때 "내 미확인 interrupt 알림" 조회 API 신설 → 창 다시 띄움).
- 각자 확인: 기존 ack API(`/erp/api/notifications/<id>/ack`)가 수신자별 기록 — 그대로.
- 적용 범위(2026-09-23 통합 검증 확정): 보강 ①(탭 간 닫기)·보이는 탭만 소리·대기열은 **당일 실측 확인창에만** 적용한다. 도면 수정 요청은 기존대로(새 도면 알림이 도면 창을 덮고, 탭 간 닫기 없음). 당일 실측 창이 떠 있을 때 온 도면 알림만 대기열에 들어간다(덮으면 당일 실측 확인이 사라지므로). 재조회 API 는 대상 팀(영업·MEASURE 표기)에게만 부르고, 삭제됐거나 실측일에서 오늘이 빠진 주문은 돌려주지 않는다.

## 6. C 웹 푸시 + 앱 배지
- `push_sender.py:44-70` `_DEFAULT_P1_TYPES` 에 `MEASURE_SAME_DAY_ADDED` 등록(없으면 조용히 안 나감).
- pywebpush 호출(`push_sender.py:328,544`)에 `ttl=86400` + `headers={"Urgency": "high"}`(긴급 유형) / `"normal"`(그 외). **현재 ttl 미지정 — pywebpush 2.0.0 기본값이 0 이면 기기가 꺼져 있을 때 기존 푸시도 버려진다(기존 결함 가능성, 구현 전 설치 소스로 확인).**
- 배지: payload 에 수신자별 `unread_count` 추가(발송 루프 안에서 수신자마다 계산, badge API 와 같은 조건) → `sw.js` push 핸들러에서 `event.waitUntil(showNotification(...) + navigator.setAppBadge(unread_count))`. 알림 클릭·읽음·앱 복귀 시 `FOMSNotificationBadge.refresh({force:true})` 로 맞춤. `payload.badge` 키는 이미 아이콘 URL 이라 `unread_count` 로 이름을 따로 쓴다.
- 직원 안내: 알림 시트에 3단계 안내(홈 화면에 추가 → 알림 허용 → 시험 알림 받기 — 기존 `push/test` API 에 버튼 연결). 관리자용 영업별 구독 상태 표(설치·허용·마지막 수신 — 기존 모델 `NotificationPushSubscription`).
- 운영 확인(배포 체크리스트): SIDEFX 서비스에 `FOMS_WEB_PUSH_ENABLED`·`VAPID_PRIVATE_KEY`·`VAPID_CLAIMS_SUB` 가 있어야 긴급 멘션(`NOTIFICATION` outbox) OS 푸시가 나간다. 없으면 SIDEFX 로그에 WARNING 1회. 재시도는 이미 `push_attempted` 인 수신자를 건너뛴다.
- 푸시 본문은 기존 규칙대로 고객명 없이 일반 문구: "오늘 실측이 긴급 추가됐어요" + 딥링크(잠금화면 노출 대비). 고객명은 앱을 연 뒤 확인창에서.

## 7. 테스트
- 트리거: 9개 저장 경로 중 대표(ERP PUT·필드 단건·통화 기록·마법사 제출·주문 추가)에서 오늘로 바꾸면 outbox 1행, 내일로 바꾸면 0행, 시간만 바꾸면 0행, 같은 날 두 번 저장해도 1행, 롤백이면 0행, 드래프트는 0행.
- 수신자: SALES + MEASURE 표기 계정 포함, 비활성 제외.
- 채널톡: 그룹 id 없으면 A 만 건너뜀, 벤더 오류 시 재시도·DEAD 처리, 실발송 없음(모킹).
- 화면: interrupt payload 키, 두 분기 파일 동기, BroadcastChannel 가드, 미확인 재조회 API 권한(본인 것만).
- 웹 푸시: ttl·Urgency 인자, 수신자별 unread_count, sw.js 배지 호출 문자열 계약.

## 8. 결정이 필요한 것
1. 긴급 추가를 한 **본인에게도** 알릴지(기본: 보냄).
2. 채널톡 멘션(@all) 실측 결과에 따라 2차 적용 여부(스테이징에서 확인 후 다시 묻기).
3. 기존 결함 두 건을 이번에 같이 고칠지: ① 웹 푸시 ttl 미지정 ② 긴급 멘션의 OS 푸시 미발송 가능성(outbox `NOTIFICATION` 핸들러 미등록).
