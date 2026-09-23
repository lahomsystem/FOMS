# 당일 실측 긴급 추가 알림 — 병렬 조사 종합 (2026-09-23)

> 상태: 조사 완료 · 구현 전(코어 변경 — 알림·API → Spec → 승인 필요).
> 사용자 요구: ① 영업 전원 휴대폰에 카톡처럼 알림(**알림톡 제외 — 카톡 또는 채널톡 앱 알림 배지**) ② FOMS 화면에서 종 알람이 아니라 화면 위에 바로 뜨는 알림.

## 1. 휴대폰 알림
- **일반 카카오톡(단톡방·개인 카톡) 자동 발송은 공식 방법이 없다.** 오픈채팅 API 미제공(카카오 데브톡 2026-07-23 답변), "친구에게 보내기"는 기업 자동 알림 용도 불가, 단톡방 비공식 봇은 약관 위반·계정 정지 위험. → 접는다.
- **채널톡 팀챗이 유일한 현실 경로이며 이미 연동돼 있다.**
  - 발송 함수 `foms/services/channel_client.py:262-313` `send_group_message`(Native Functions `writeGroupMessage`), 라우팅 `foms/services/channel_policy.py:125-169`(`measure_room` → `CHANNEL_GROUP_MEASURE_ROOM` 기본 229923 "실측스케줄" 방), 서버 본문 조립 `foms/services/channel_measure_message.py:444` `build_measure_push_text(sd)`.
  - 지금은 **전부 수동 버튼**(`channel_policy.py:205` `"2.0.0-manual-only"`). 자동 발송 경로를 새로 만든다.
  - 휴대폰 푸시·배지 조건(채널톡 도움말): 방 알림이 "모든 알림 받기"여야 일반 메시지에도 푸시. "중요 알림만"은 직접 멘션·팀 멘션·`@all` 만. 방해금지 중엔 없음. **봇 메시지의 `@all`·멘션이 "중요"로 인정되는지 공식 문서 미확인 → 스테이징 실측 필요.** FOMS 에 멘션 전송 코드 없음.
  - 비용: 메시지 건당 0원. 영업이 채널톡 시트가 없으면 1인 월 3,000원.
  - 운영 확인 필요: 영업 전원이 대상 방 멤버인지, WORKER·SIDEFX 에 `CHANNEL_APP_SECRET`/`CHANNEL_ID` 가 있는지(import 시점 상수, `channel_client.py:20-21`).
- 보조: 웹 푸시는 운영에서 켜져 있다(`FOMS_WEB_PUSH_ENABLED=1`). 새 알림 유형은 `push_sender.py:44-70` `_DEFAULT_P1_TYPES` 등록이 없으면 조용히 안 나간다. 아이폰은 홈 화면 설치 필수.

## 2. 화면 알림
- Socket.IO(WebSocket 전용, gevent, Redis message_queue) 실시간 길이 운영 중: `foms/platform/realtime.py:200-236`, `foms/services/notifications/realtime_notifications.py:15-42` `emit_erp_notification_to_users`.
- 도면팀 "가운데 확인창"(interrupt 등급) 재사용: 서버 payload `interrupt: True`(선례 `foms/api/drawing/erp_orders_revision.py:168-182`), 화면 `static/js/foms/foms-drawing-alert.js`(ack+read, 비프음), 분기 `templates/partials/shared/layout_head.html:931` + 사본 `static/js/runtime/layout-head-init.js:152,167`(계약 테스트가 둘을 비교).
- 보강할 약점: 여러 탭에서 창·소리 중복(BroadcastChannel), 클릭 전 탭은 소리 막힘(첫 클릭 때 AudioContext 준비), 끊긴 동안 온 알림은 다시 연결돼도 창이 안 뜸(재연결·visibilitychange 때 미확인 interrupt 재조회), 영업 여러 명 동시 수신 시 "한 명 확인하면 모두 닫기 vs 각자 확인" 결정.
- 먼저 확인: 운영 web 로그에 `Socket.IO initialized in gevent mode with Redis`.

## 3. 트리거(긴급 추가 감지)
- "전날 17시 확정"은 코드에 없다(마감 상수·확정 플래그·스냅샷 없음). `OrderScheduleDate` 에 생성 시각 없음.
- 실측일 쓰기 경로 9곳, 그중 4곳(필드 단건 수정 `field_update.py:727`, 마법사 제출 `erp_order_draft.py:620`, 옛 수정 폼 `web/orders/edit.py:424`, 주문 추가 `web/orders/listing.py:331`)은 실측일 변경 이벤트를 안 남긴다. `MEASUREMENT_SCHEDULED` 는 표시 이름만 있고 만드는 곳 0.
- **추천 지점: 전역 before_flush 날짜 훅 `foms/services/order_date_sync.py:459-545` 확장**(시공일처럼 실측일 이전/이후 집합 비교 → 커밋 뒤 발송; 선례 `foms/services/notifications/shipment_change.py:462-563`). 빈틈: 신규 주문 제외(:501-506) 해제, 드래프트 승격은 날짜 차이가 없어 DRAFT 해제 전환을 따로 감지, 드래프트 자체 제외.
- 멱등 키: `meas_same_day:{order_id}:{YYYY-MM-DD(KST)}` — outbox 부분 고유 인덱스(`models.py:2680-2683`) 재사용.
- 수신자: `Notification(target_type='TEAM', target_team='SALES')` + `recipients.py:43-171`. 단 `MEASURE`→`SALES` 정규화 미반영(`recipients.py:70-76`) 보정 필요.

## 4. 부수 발견 (별건 확인 필요)
- 긴급 멘션(`foms/api/notifications/__init__.py:956-968`)이 outbox `effect_type="NOTIFICATION"` 을 넣지만 SIDEFX 핸들러 등록(`tools/ops/run_domain_side_effect_outbox.py:278-291`)에 없음 → OS 푸시 미발송·outbox DEAD 누적 가능성.

## 5. 사용자 결정 (2026-09-23)
1. 대상: **오늘(KST) 실측이 새로 생기거나 오늘로 바뀐 경우만.** 17시 이후 "내일" 추가는 제외.
2. 채널톡: **새 "긴급" 전용 방**을 만든다(사용자가 채널톡에서 방 생성·영업 초대 → 그룹 id 를 환경변수로). 추가로 **FOMS 를 앱처럼 휴대폰 알림 배지로 받는 방법**을 조사한다(진행 중).
3. 화면 확인창: **각자 확인**(수신자마다 ack).
4. 문자(SMS) 안전망: **보내지 않음.**
