# 당일 실측 긴급 추가 알림 — 작업 브리프 (초안 · 스펙 승인됨)

> 정본 스펙: `docs/specs/2026-09-23-same-day-measure-urgent-alert_SPEC.md` (승인됨). 조사: `docs/plans/2026-09-23-same-day-measure-urgent-alert-research.md`.
> 이 브리프는 초안이다. CEO 는 계약을 보강할 수 있으나 "이름 고정" 표는 바꾸지 않는다.
> 선행 작업(실측 체크리스트, 같은 워크트리)이 커밋된 뒤에 시작한다.

## 1. 이름 고정
| 대상 | 이름 |
|---|---|
| 알림 유형 | `MEASURE_SAME_DAY_ADDED` (Notification.type) |
| outbox effect | `MEAS_SAME_DAY_ALERT`, dedupe_key `meas_same_day:{order_id}:{YYYY-MM-DD}` |
| 감지 함수 | `foms/services/notifications/measure_same_day.py`(신규) — `detect_same_day_additions(session, order, before_dates, after_dates, was_draft, is_draft)` 순수 판정 + 리스너 등록 `register_measure_same_day_listener()` |
| 채널톡 | env `CHANNEL_GROUP_URGENT_MEASURE`(기본 `'209989'`, 빈 문자열이면 끔), 봇 이름 `FOMS긴급`, 이력 키 `structured_data.channeltalk_push_urgent_measure` |
| 화면 payload | `interrupt: True`, `alert_kind: 'measure_same_day'`, `customer_name, area, time, manager, added_by, added_at, order_url` |
| 미확인 재조회 API | `GET /erp/api/notifications/pending-interrupts` (본인 것만, ack 안 된 interrupt 유형) |
| 탭 간 채널 | `BroadcastChannel('foms-alerts')` |
| 웹 푸시 | payload `data.unread_count`(수신자별), sw.js `setAppBadge`, `ttl=86400`, `Urgency` 헤더 |

## 2. 앵커
- 전역 flush 훅: `foms/services/order_date_sync.py:482-545`(`_run_date_sync_flush`, 신규 제외 :501-506, 등록 :525-545). 시공일 이벤트 emit 선례 `:410-479`.
- 커밋 뒤 발송 패턴: `foms/services/notifications/shipment_change.py:462-563`.
- outbox 멱등: `models.py:2680-2683`, 알림톡 예약 선례 `foms/services/kakao_alimtalk.py:1009-1058`, 핸들러 등록 `tools/ops/run_domain_side_effect_outbox.py:275-295`.
- 알림 생성·팬아웃: `foms/services/notifications/recipients.py:43-171`(MEASURE→SALES 정규화 누락 :70-76; 정규화 규칙 `foms/services/orders/order_mutation_policy.py:47,241-283`), 수동 공지 선례 `foms/api/notifications/__init__.py:710-828`.
- 실시간: `foms/services/notifications/realtime_notifications.py:15-42`, interrupt 선례 `foms/api/drawing/erp_orders_revision.py:168-182`.
- 화면: `static/js/foms/foms-drawing-alert.js`(ack 96-127, 탭 내 중복방지 129-132, beep 38-55), 분기 `templates/partials/shared/layout_head.html:931-946` + 사본 `static/js/runtime/layout-head-init.js:152,167`, 재연결 시 배지만 갱신 `layout_head.html:889`.
- 웹 푸시: `foms/services/notifications/push_sender.py`(P1 집합 :43-68, payload :211-235, 발송 :328-333·:544-549, 수신자 루프 :383-402), `static/sw.js:336-385`(push), `:422-450`(click), 배지 페이지 코드 `static/js/foms/mobile-push.js:473-496`, 알림 시트 `templates/partials/shared/erp_mobile_notification_panel.html:41-47`, 시험 발송 API `foms/api/notifications/push.py:292-335`.
- 채널톡: `foms/services/channel_client.py:262-313` `send_group_message`, 라우팅 `foms/services/channel_policy.py:125-169`, 서버 본문 선례 `foms/services/channel_measure_message.py:444`.
- 드래프트 승격: `foms/api/erp_orders_structured.py:983-990`(`_finalize_draft_state`), 마법사 제출 `foms/api/erp_order_draft.py:620-709`.
- 서버 소유 키 보존 목록: `foms/api/erp_orders_structured.py:231` `_OPERATIONAL_TOP_LEVEL_KEYS`.
- 기존 결함 ②: 긴급 멘션 outbox `effect_type="NOTIFICATION"` (`foms/api/notifications/__init__.py:956-968`) — 핸들러 등록 여부를 먼저 grep 으로 확정하고, 미등록이면 실제 소비자(푸시 enqueue)를 등록한다.
- 기존 결함 ①: pywebpush 2.0.0 `webpush()` 의 `ttl` 기본값을 설치 소스(`pip show -f pywebpush` 후 파일 열람)로 확인.

## 3. 소유권 (겹치지 않게)
| 워커 | 파일 |
|---|---|
| A 감지·outbox·채널톡 | `foms/services/notifications/measure_same_day.py`(신규), `foms/services/order_date_sync.py`(등록 1곳 + 판정 호출), `foms/services/channel_policy.py`(라우트 1개), `foms/api/erp_orders_structured.py`(보존 키 1줄), `tools/ops/run_domain_side_effect_outbox.py`(핸들러 등록 — `MEAS_SAME_DAY_ALERT` 와 결함② `NOTIFICATION`), 신규 핸들러 모듈 `foms/services/notifications/measure_same_day_delivery.py`, `foms/services/notifications/recipients.py`(정규화) + 테스트 `tests/domains/test_measure_same_day_*.py` |
| B 화면 확인창 | `static/js/foms/foms-drawing-alert.js`, `templates/partials/shared/layout_head.html`(931-946 분기만), `static/js/runtime/layout-head-init.js`(같은 분기), `foms/api/notifications/__init__.py`(pending-interrupts API 만) + 테스트 `tests/domains/test_measure_same_day_alert_ui.py` |
| C 웹 푸시·배지·안내 | `foms/services/notifications/push_sender.py`, `static/sw.js`, `static/js/foms/mobile-push.js`, `templates/partials/shared/erp_mobile_notification_panel.html`, (관리자 구독 상태 표) 기존 관리자 템플릿 1곳 + 테스트 `tests/domains/test_push_badge_ttl.py` |

## 4. 규칙·함정
- 요청 스레드에서 외부 API(채널톡·웹푸시) 호출 금지 → outbox/RQ. 롤백되면 아무것도 안 나간다.
- 드래프트 주문은 대상 아님. 오늘 판정은 `foms/services/datetime_kst.py` `get_today_kst()` (CI 는 UTC — `date.today()` 금지).
- 푸시·잠금화면 본문에 고객명 금지(기존 규칙). 채널톡·화면 확인창은 고객명 허용.
- iOS 무음 푸시 3회 해지 규칙: sw.js push 는 반드시 `event.waitUntil(showNotification(...))` 안에서 배지까지 처리.
- 계약 테스트가 `layout_head.html` 과 `layout-head-init.js` 분기를 비교한다 — 둘을 같이 고친다(`layout_head.html` 은 핫파일).
- 캐시 핀: 고친 정적 파일의 `?v=` 핀을 올리고, 핀을 복제해 단언하는 테스트도 같이 올린다(`grep -rn "?v=<옛핀>" tests/`). sw.js 는 캐시 버전 상수도 확인.
- 하네스 인벤토리 JSON(`docs/harness/foms_*_inventory.json` 등)이 새 쓰기 경로·outbox 를 요구하면 생성 스크립트로 갱신(손편집 금지 — 해당 테스트 메시지가 명령을 알려 준다).
- 공통: `cd c:/tmp/foms-s-meas-glance && pwd`, git 금지, LF/UTF-8, 인라인 style 금지, jQuery 금지, `{success,data,error}`.

## 5. 검증
```
cd c:/tmp/foms-s-meas-glance && pwd
python -c "import app; print('APP_OK')"
node --check static/sw.js static/js/foms/foms-drawing-alert.js static/js/foms/mobile-push.js static/js/runtime/layout-head-init.js
PYTHONIOENCODING=utf-8 python -m pytest -q tests/domains -k "measure_same_day or push or notification or drawing_alert or order_date_sync or shipment_change or channel or outbox or layout_head" -p no:cacheprovider
PYTHONIOENCODING=utf-8 python -m pytest -q tests/harness tests/performance -p no:cacheprovider
```
