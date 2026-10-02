# 긴급 알림 어디서나 띄우기 — SPEC (2026-10-02)

## 문제 (실측: 코드 조사)

1. **standalone 화면 사각지대.** 받는 쪽 전체화면 경고는 `templates/partials/shared/layout_head.html:887`
   `window.triggerUrgentBriefingAlert` 인라인 함수다. `layout_head` 를 쓰지 않는 화면에는 없다.
   - 도면 마법사(`templates/drawing/wizard.html`): `wizard-alert-bridge.js` 가 소켓은 붙였지만
     `FOMSDrawingAlert.handle` 은 `interrupt`/`notice` 만 처리 → `urgent:true` payload 는 버려진다.
   - 실측 지도(`templates/measurement/map_view.html`): 소켓 자체가 없다.
2. **ack 버튼이 안 나온다.** 오버레이는 payload 에 `notification_id` 가 있을 때만 "확인(ack) 처리"를
   보인다. 긴급 멘션(`foms/api/notifications/__init__.py:1082`)·긴급 공지(`:899`) 둘 다 id 를 안 싣는다.
3. **놓친 긴급은 다시 안 뜬다.** 소켓이 끊긴 동안·창이 닫힌 동안 온 긴급은 재표시 경로가 없다.
   (`pending-interrupts` 는 `MEASURE_SAME_DAY_ADDED` 만.)
4. **탭 여러 개.** 한 탭에서 ack 해도 다른 탭 오버레이는 남는다.
5. **PC 팝업(OS 웹푸시)을 누르면 빨간 창이 사라진다.** `static/sw.js` `notificationclick` 이
   열린 창 아무거나 하나를 골라 `client.navigate(deep_link)` 한다 → 그 창이 새로 읽히면서
   메모리에만 있던 오버레이가 지워진다. 도면 마법사에서 누르면 작업 중 화면까지 떠난다.
6. 브라우저 한계: 탭이 다른 탭/창 위로 올라올 수는 없다. 안 보는 창은 OS 웹푸시(`static/sw.js`,
   긴급은 `requireInteraction`)만 가능하다 — 이 SPEC 범위 밖(구독 여부는 별건).

## 설계

### A. 오버레이 모듈 하나로 (`static/js/foms/foms-urgent-alert.js`, 새 파일, 300줄 이하)
- `window.FOMSUrgentAlert = { show(data), handle(data), bindSocket(socket), resync(reason) }`.
- 현재 인라인 오버레이 동작(비프·전체 빨간 화면·닫기 confirm·ack 버튼) 그대로 옮긴다.
  스타일은 `static/css/components/foms-urgent-alert.css`(새 파일)로 — `style.cssText` 제거.
- 여러 건이 오면 마지막 1건만 덮어쓰던 것을 **대기열**로: 확인/닫기 하면 다음 건을 보인다.
- 같은 `notification_id` 중복 표시 방지(소켓 + 재조회 겹침).
- 탭 간: `BroadcastChannel('foms-urgent')` 로 ack 한 id 를 알려 다른 탭에서도 닫는다.
- `layout_head.html` 의 `onErpNotification` 은 `FOMSUrgentAlert.handle` 로 위임,
  `window.triggerUrgentBriefingAlert` 는 호환 별칭으로 남긴다. SSOT 사본
  `static/js/runtime/layout-head-init.js` 도 같이 맞춘다.

### B. standalone 화면 배선
- 도면 마법사: CSS·모듈 로드, `wizard-alert-bridge.js` 에서 `FOMSUrgentAlert.bindSocket(socket)` 추가.
  마법사 단축키가 오버레이 뒤에서 먹지 않게 오버레이가 키 이벤트를 막는다(포커스 가둠).
- 실측 지도: socket.io + 모듈 로드, 짧은 브리지(마법사 브리지와 같은 형태)로 연결.
- WAM·라벨·고객 공유 화면은 대상 아님(직원 작업 화면 아님).

### C. 서버
- 긴급 멘션 emit payload 에 `notification_id: notif.id` 추가.
- 긴급 공지: 수신자별 notification row 가 다르므로 수신자마다 자기 id 를 실어 emit.
- 에스컬레이션(`escalation.py`)은 단일 id 가 없으므로 지금처럼 id 없음(ack 버튼 숨김) 유지.
- 새 GET `/erp/api/notifications/pending-urgent`: 본인 state, `is_urgent=True`,
  `ack_at IS NULL`, `archived_at IS NULL`, 최근 24시간, 오래된 것부터 최대 5건.
  응답 `{'success','data':{'items':[{notification_id,title,message,order_id,created_by_name}]},'error'}`.
- 클라 `resync`: 소켓 연결(재연결 포함) 때 + 화면 복귀(visibilitychange) 때, 30초 간격 제한.

### D. PC 팝업 클릭 → 빨간 창으로 (사용자 요청 2026-10-02)
- push payload `data` 에 `urgent: true` 를 싣는다(`push_sender._build_payload`).
- `sw.js notificationclick`: 긴급이면 **navigate 하지 않는다.** 열린 창이 있으면 보이는 창
  (`focused`/`visibilityState=visible` 우선, 없으면 첫 창)을 `focus()` 하고 모든 창에
  `postMessage({type:'foms-urgent-open', notification_id})`. 열린 창이 없을 때만 `openWindow`
  (대시보드) — 새 창은 로드 때 `pending-urgent` 재조회로 빨간 창을 띄운다. 긴급이 아니면 현행 유지.
- 페이지는 메시지를 받으면 해당 긴급을 빨간 창에 띄운다(이미 떠 있으면 그대로, 없으면
  `pending-urgent` 에서 찾아 띄움 — 이미 ack 된 건이면 안 띄움).
- 빨간 창 닫기 규칙: **"확인" 버튼 하나로만 닫힌다.** 현재의 confirm 닫기("알림 확인완료")와
  별도 ack 버튼을 하나로 합친다 → 확인 = ack 기록 + 닫기 + 다른 탭 닫기. 배경 클릭·Esc 로는
  안 닫힌다. id 없는 에스컬레이션 경고는 확인 = 닫기만.
- SW 캐시 버전 상수 올림(새 sw 가 깔리게).

## 변경 파일
- 새: `static/js/foms/foms-urgent-alert.js`, `static/css/components/foms-urgent-alert.css`,
  `static/js/measurement/map-urgent-bridge.js`, `tests/domains/test_urgent_alert_everywhere.py`
- 수정: `templates/partials/shared/layout_head.html`, `static/js/runtime/layout-head-init.js`,
  `templates/drawing/wizard.html`(다른 세션 미커밋 변경 있음 — hunk 단위로만),
  `static/js/drawing/wizard-alert-bridge.js`, `templates/measurement/map_view.html`,
  `foms/api/notifications/__init__.py`, `static/sw.js`, `foms/services/notifications/push_sender.py`

## 완료 기준
- `python -m pytest tests/domains/test_urgent_alert_everywhere.py tests/domains/test_urgent_call.py tests/domains/test_drawing_revision_interrupt_alert.py tests/domains/test_measure_same_day_alert_ui.py tests/performance/test_shared_layout_defer_contract.py -q` 통과
- `node --check` 새/수정 JS, `python -c "import app; print('APP_OK')"`
- 로컬 dev 실화면: 도면 마법사·실측 지도·주문 화면을 탭 3개로 열고 긴급 멘션 1건 →
  세 탭 모두 오버레이, 한 탭 ack → 나머지 닫힘. 마법사 새로고침 전 미확인 긴급 → 재표시.
- PC 팝업 클릭 → 창이 새로 읽히지 않고(마법사 작업 유지) 빨간 창이 그대로/다시 보이며,
  "확인" 을 눌러야만 닫힌다.
- `scripts/ops/pre_push_smoke.ps1` exit 0
