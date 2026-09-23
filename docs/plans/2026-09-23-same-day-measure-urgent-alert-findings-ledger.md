# 당일 실측 긴급 알림 — 리뷰 findings 원장 (2026-09-23)

> 워크플로 wf_9f2df00c-dc6 리뷰 2명 결과 전량. 상태 칸은 총괄이 직접 확인한 뒤 갱신한다.

## F01 [P2] static/js/foms/foms-drawing-alert.js:207

스펙 §5에 '도면 동작 불변'이라고 돼 있지만 도면 수정 요청 확인창 동작이 세 군데 바뀌었다. (1) 확인창이 떠 있을 때 두 번째 interrupt 가 오면, 예전에는 앞 창을 덮어썼는데 이제는 대기열에 넣는다(207행). (2) 비프음이 보이는 탭에서만 난다(47행). 그래서 도면팀이 작업실 탭 하나만 뒤에 열어 둔 경우 소리가 전혀 안 난다. (3) ack 가 BroadcastChannel 로 다른 탭 창까지 닫는다. 개선에 가깝지만 스펙 문구와 맞지 않는다.

제안: 총괄이 이 변경을 받아들일지 정하고 스펙·브리프에 '도면에도 대기열·보이는 탭만 소리·탭 간 닫기 적용'이라고 적는다. 받아들이지 않으면 measure_same_day 종류에만 적용하도록 가른다. 예: alert_kind===MEASURE_KIND 일 때만 queue.push, 도면은 기존처럼 render 로 덮어쓰기.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F02 [P2] static/js/foms/foms-alert-sync.js:78

page-load·visible·socket-connect 세 계기가 30초 제한(MIN_INTERVAL_MS) 하나를 같이 쓴다. 그래서 재연결 재표시가 빠지는 틈이 있다. 페이지를 열거나 화면으로 돌아온 직후 30초 안에 소켓이 끊겼다 다시 붙으면 socket-connect resync 가 건너뛰어진다. 그 사이에 온 확인창은 다음 visibilitychange 가 올 때까지 뜨지 않는다. 늘 보이는 채로 켜 둔 PC 탭은 그 계기가 사실상 오지 않는다. 확인창이 떠 있는데 ack 없이 30초 안에 다른 페이지로 이동해도 새 페이지에서 다시 뜨지 않는다.

제안: 'socket-connect' 계기는 제한에서 빼고 inFlight 만 막는다. 아니면 제한을 계기별로 따로 두거나 5초 정도로 줄인다. 이 경우를 흉내 내는 계약 테스트 1개를 더한다: resync('page-load') 직후 resync('socket-connect') 가 fetch 를 부르는지.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F03 [P2] tests/domains/test_measure_same_day_trigger.py:195

스펙 §7이 요구한 테스트 일부가 없다. (1) 대표 경로 가운데 '통화 기록'(call_log) 경로에서 오늘로 바꾸면 outbox 1행이 되는 테스트. (2) '추가한 본인도 받는다'(§3·§8-1)를 단언하는 테스트: 변경자 user_id 가 NotificationUserState 수신자에 드는지 확인하는 곳이 없다. (3) 채널톡 벤더 오류가 최대 재시도 뒤 DEAD 로 가는지: 지금은 재시도까지만 본다.

제안: 통화 기록 API로 실측일을 오늘로 바꾸는 트리거 테스트를 더한다. 로그인한 SALES 사용자가 PUT 했을 때 그 사용자 id 가 _state_user_ids 에 드는지 단언한다. worker 를 attempts 한도까지 돌려 status=='DEAD' 가 되는지 확인하는 delivery 테스트를 더한다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F04 [P2] static/js/foms/mobile-push.js:218

아이폰 사파리 탭(홈 화면 앱 아님)에서 같은 설치 안내가 두 번 나온다. 시트의 정적 3단계 목록(applySteps('install'), 432행)과 renderUnsupported 가 펼친 채 붙이는 설치 안내 패널(218행)이 위아래로 겹친다.

제안: 둘 중 하나만 보이게 한다. 예: 정적 3단계 목록이 있으면 renderUnsupported 에서 buildGuidePanel 을 붙이지 않고 문구만 남긴다. 또는 install 단계에서는 정적 목록을 숨긴다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F05 [P2] foms/services/notifications/push_sender.py:266

주석은 '주문별 tag: 같은 주문이 다시 오면 잠금화면에서 1건으로 접힌다'인데, 코드는 tag 를 foms-meas-{notif.id}(알림 id)로 만든다. 같은 주문이라도 날이 다르면 알림 id 가 달라 접히지 않는다. 주석과 동작이 어긋난다.

제안: 의도가 주문 단위로 접기라면 tag 를 f"foms-meas-{int(notif.order_id or notif.id)}" 로 바꾼다. 아니면 주석을 '알림별 tag'로 고친다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F06 [P2] static/css/contexts/measurement/measurement-mobile-glance.css:288

워크트리에 이번 작업과 상관없는 변경이 섞여 있다. 실측 캡처 전화번호 칸 CSS 와 dashboard_main.html 의 ?v=20260923b 핀, test_measurement_mobile_glance.py 핀이 그렇다. layer_dependency_baseline.json 에서도 이번 작업과 상관없는 항목(cs/confirm·orders/status·quest)이 지워졌다. 한꺼번에 커밋하면 다른 작업 몫이 이 커밋에 들어간다.

제안: 총괄은 pathspec 으로 이번 작업(브리프 §3 파일, 새 모듈·테스트, 인벤토리 JSON, test_measurement_visit_api·test_push_sender·test_sidefx_record_only_effects)만 골라 커밋한다. baseline 은 생성 스크립트로 다시 만든 결과인지 확인한 뒤 넣는다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F07 [P1] foms/services/notifications/measure_same_day_delivery.py:189

SIDEFX 핸들러가 153행에서 주문을 읽고, 채널톡 호출(네트워크 왕복)을 한 뒤, 처음 읽은 structured_data 를 deepcopy 해 JSONB 전체를 다시 씁니다(_append_history, 196-202행. stale·no_longer_today·not_configured 경로도 같음). 채널톡 왕복 사이에 영업이 같은 주문을 저장하면 그 저장 내용이 worker 커밋에 덮여 사라집니다. 이 알림은 영업이 방금 실측일을 오늘로 저장한 직후에 돌기 때문에, 같은 주문을 이어서 고치고 있을 가능성이 높습니다. 앞선 사례인 kakao_alimtalk.py:990-993 은 '벤더 왕복 동안 사용자가 저장했을 수 있다'는 이유로 쓰기 직전에 session.refresh(order) 를 합니다.

제안: _append_history 첫 줄에서 session.refresh(order) 를 부르거나 Session.object_session(order).refresh(order, with_for_update=True) 로 행을 잠근 뒤, 새로 읽은 structured_data 에 deepcopy → 수정 → 재대입 → flag_modified 를 합니다. 테스트도 하나 추가합니다: send_group_message 목 안에서 다른 세션으로 주문 structured_data 를 바꿔 커밋하고, 핸들러 커밋 뒤에도 그 값이 남아 있는지 확인합니다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F08 [P1] static/js/foms/foms-drawing-alert.js:42

소리 준비가 pointerdown 에 once:true 로 한 번만 걸려 있습니다. HTML 표준에서 터치의 pointerdown 은 사용자 활성화(user activation)로 치지 않습니다(터치는 pointerup·touchend·click 이 활성화 이벤트, iOS WebKit 도 비슷함). 그래서 휴대폰·태블릿에서는 이때 만든 AudioContext 가 suspended 상태로 남고 resume() 도 거절됩니다. 리스너는 한 번 뒤 제거되고, beep()(45-63행)은 이미 있는 audioCtx 에 resume() 을 다시 부르지 않고 오실레이터만 돌리므로 소리가 영영 나지 않습니다. 예전 코드는 beep 때마다 새 컨텍스트를 만들어, 한 번이라도 탭한 뒤에는 소리가 났습니다. 그래서 도면 확인창 소리도 모바일에서 함께 퇴행합니다.

제안: priming 을 pointerup·touchend·click·keydown 에 걸고 once 는 쓰지 않습니다. audioCtx.state === 'running' 이 된 뒤에만 리스너를 뗍니다. beep() 에서는 ctx.state === 'suspended' 이면 먼저 ctx.resume() 을 부르고, 그 promise 가 풀린 뒤 오실레이터를 시작합니다(실패는 삼킴).

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F09 [P2] foms/services/notifications/measure_same_day.py:338

트랜잭션 경계 문제입니다. 기준 OrderEvent·outbox·Notification 을 업무 트랜잭션 안에서 만들지 않고, after_commit 에서 새 세션을 열어 따로 커밋합니다. 주문 저장은 커밋됐는데 이 두 번째 트랜잭션이 실패하면(DB 순간 끊김, 프로세스 종료, 배포 재시작) 채널톡·화면·푸시가 전부 영구히 빠지고, 다시 시도할 행도 남지 않습니다. 스펙 §2 가 가리킨 앞선 사례 shipment_change._apply_pending_alerts 는 알림 행을 before_commit, 즉 같은 트랜잭션에서 만들어 원자성을 지킵니다. 요청 스레드마다 연결을 하나 더 쓰는 비용도 생깁니다.

제안: _collect_pending(before_commit) 안에서 session.begin_nested() savepoint 로 감싸 OrderEvent·enqueue_side_effect·Notification·fan-out 을 업무 트랜잭션과 함께 커밋합니다. 멱등 IntegrityError 는 savepoint 롤백으로만 흡수합니다(또는 먼저 (effect_type,dedupe_key) 존재를 SELECT). after_commit 에는 푸시 enqueue·배지 무효화·emit 만 남깁니다. 새 세션 설계를 유지한다면 적어도 실패를 되살릴 복구 경로(재예약 스캔)를 둡니다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F10 [P2] foms/services/notifications/notification_push_delivery.py:85

기존 결함 ②를 고친 부분이 실제로 동작하려면 SIDEFX 서비스에 FOMS_WEB_PUSH_ENABLED·VAPID_PRIVATE_KEY(와 VAPID_CLAIMS_SUB) 환경변수가 있어야 합니다. Railway 는 서비스마다 환경변수가 다른데, 없으면 _send_push_impl 이 flag_off 를 돌려주고 핸들러는 error 로그만 남긴 뒤 DONE 처리합니다. 결과적으로 긴급 멘션 OS 푸시는 여전히 안 나가고 겉으로는 해결된 것처럼 보입니다. 재시도 중복도 있습니다. 앞 구독에 webpush 가 성공한 뒤 마지막 db.flush 나 worker 커밋이 실패하면 행이 재시도되는데, PUSH_ATTEMPTED 는 _TERMINAL_STATUSES 에 없어서 같은 수신자 모두에게 다시 발송됩니다.

제안: 배포 체크리스트와 핸들러 시작 부분에서 SIDEFX 에 해당 환경변수가 있는지 확인하고, 없으면 WARNING 을 한 번 크게 남깁니다. 재시도 멱등성은 이렇게 맞춥니다: 핸들러에서 해당 notification 에 PUSH_ATTEMPTED NotificationEvent 가 이미 있는 state 는 건너뛰거나, row.attempts > 1 이면 last_delivery_status == PUSH_ATTEMPTED 인 state 를 제외합니다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F11 [P2] foms/api/notifications/__init__.py:453

pending-interrupts 가 '오늘 만들어짐 + 아직 확인 안 함' 조건만 봅니다. 알림 뒤에 실측일이 오늘에서 빠지거나 주문이 삭제·취소돼도, 페이지를 열 때마다 '오늘 ○시 실측 — 고객명' 확인창을 다시 띄웁니다. 채널톡 핸들러는 _order_has_measurement_on 으로 같은 상황을 걸러내는데, 화면 경로만 이 검사가 없습니다.

제안: 이미 한 번에 불러온 orders_by_id 로 추가 쿼리 없이 거릅니다. 주문이 삭제 상태이거나, collect_order_schedule_date_specs(order) 의 measurement 날짜에 get_today_kst().isoformat() 가 없으면 건너뜁니다(필요하면 그 state 를 자동 ack 처리).

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F12 [P2] static/js/foms/foms-alert-sync.js:114

layout_scripts 로 모든 ERP 페이지에 실리고, 페이지를 열 때와 화면에 돌아올 때마다(탭당 30초 제한) 모든 로그인 사용자에게 /erp/api/notifications/pending-interrupts GET 을 한 번씩 보냅니다. 받을 일이 없는 도면·CS·관리자 계정도 포함입니다. 쿼리가 2개라 N+1 은 아니지만, 전 사용자 페이지 이동마다 조인 쿼리가 하나씩 늘어납니다.

제안: 서버가 템플릿에 data-* 속성(예: 영업/MEASURE 팀 여부)을 내려주고, 대상 팀일 때만 resync 합니다. 또는 배지 count 가 0 이면 건너뛰는 식으로 앞단에서 거릅니다.

상태: 수정 반영 주장(워크플로 2차 판정). 총괄 확인 대기.

## F13 [P3] static/js/foms/foms-drawing-alert.js:167 (스테이징 실화면에서 발견)

담당자가 비어 있는 주문이면 확인창 본문이 "서울특별시 강남구 · 담당" 처럼 이름 없이 "담당" 글자만 남았다. 추가한 사람·시각이 비어도 meta 가 " 추가 · " 로 남는다.

상태: 수정 — 빈 칸은 빼고 " · " 로 잇는다. 핀 20260923a → 20260923b.

## 스테이징 확인 기록 (2026-09-23, deploy `ca687c49`)

- 테스트 주문 4491(가짜 번호 010-0000-0000) 실측일을 오늘로 바꿈(`/api/update_order_field`) → 알림 1645(TEAM/SALES) · 수신 10명(변경자 포함) · outbox `MEAS_SAME_DAY_ALERT` DONE.
- 같은 브라우저 두 탭 모두 확인창이 떴다. 한 탭에서 확인 → 두 탭 모두 닫힘, ack_at·read_at 기록. 새 탭을 열어도 다시 뜨지 않음.
- 스테이징·운영 SIDEFX 에는 CHANNEL_APP_SECRET·CHANNEL_ID·VAPID_* 가 없다 → 채널톡 이력 `error='not_configured'` 로 끝남(설계대로). 채널톡 실제 발송은 SIDEFX 환경변수를 넣어야 동작한다.
- 확인 뒤 실측일을 다시 비웠다.
