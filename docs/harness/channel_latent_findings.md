# 채널톡 표면 잠복 결함 원장 (2026-08-27)

> 조사 계기: 채널톡 401 전송 실패(운영 `dde4ac36` / PR #167) 수정 후 "주변에 같은 종류의
> 조용한 실패가 더 있는가" 전수 점검. 대상 = `foms/api/channel/*` + `foms/services/channel_*`
> + `foms/services/jobs/*` 30개 파일(약 7,400줄).
>
> **판정: 지금 터지고 있는 조용한 실패 0건.** 아래 2건은 잠복이었고, 처음에는 기록만 하기로
> 했다가 같은 날 **둘 다 수정**했다(2026-08-27). 각 항목의 `수정` 절이 최종 상태다.

## CH-LATENT-01 — 푸시 라우트가 전송 결과를 확인하지 않는다

* 위치: `foms/api/channel/channel_integration.py:509`(수동 푸시), `:797`(견적서 푸시)
* 증상(발현 시): 채널톡에 아무것도 안 갔는데 화면에는 성공. 흔적 칩에는 `message_id: None`
  인 가짜 발송 기록이 남는다.
* 원인: 두 라우트 모두 `dispatch_order_event(...)` 결과를 받아두고 `result['success']` 를
  보지 않은 채 `jsonify({'success': True})` 를 반환한다. `raise_on_error=True` 는 **예외만**
  전파하는데, `foms/services/channel_client.py:272` 의 "group_id 없음 → 전송 건너뜀" 은
  예외가 아니라 `{"success": False, "message_id": None}` **리턴**이다.
* 현재 미발현 이유: 그룹 id 는 `foms/services/channel_policy.py:150-157` 이 하드코딩 폴백
  (도면 229625 · 견적 230395 · AS 230351 · 실측 209990)을 주고, 운영에는
  `CHANNEL_GROUP_DRAWING/ESTIMATE/AS` 가 설정돼 있지 않아 폴백이 동작한다.
* 발현 조건: 누군가 `CHANNEL_GROUP_*` 를 **빈 문자열로** 설정하면 열린다
  (`os.environ.get(key, default)` 는 빈 문자열이면 기본값을 주지 않는다).
* **수정 완료(2026-08-27)**: `_ensure_dispatch_sent(result, push_kind)` 신설
  (`channel_integration.py`) — 전송 결과가 성공이 아니면 `RuntimeError` 로 올려 기존 502
  경로를 그대로 태운다. 이력 기록은 건너뛰고, 견적서 라우트는 업로드 정리 try **안에서**
  판정해 고아 파일이 남지 않는다. 성공 경로 무변경.
* 테스트: `tests/domains/test_channel_integration_smoke.py`
  ::`test_push_manual_reports_502_when_dispatch_did_not_send` ·
  ::`test_push_estimate_cleans_up_upload_when_dispatch_did_not_send`
  (판정 호출 2줄을 빼면 둘 다 red 인 것 확인).

## CH-LATENT-02 — 인바운드 파싱 실패가 아무에게도 보이지 않는다

* 위치: `foms/services/channel_inbound.py:241-246`
* 증상(발현 시): 채널톡으로 주문 텍스트를 보낸 사람은 접수된 줄 아는데, 실제로는
  `parse_failed` 행 하나만 남고 끝난다.
* 원인: 실패 시 `log.status = "parse_failed"` 기록 후 `# TODO: 채널톡 API를 통해 실패 안내
  Quick Reply 전송` 인 채로 반환한다. `parse_failed` 문자열은 코드 전체에서 이 파일
  (`:93`, `:241`) 밖에서 **읽히지 않는다** — 관리자 화면·알림·지표 어디에도 없다.
* 현재 미발현 이유: 운영 `channel_inbound_event_logs` **0행**(2026-08-27 읽기전용 조회).
  `CHANNEL_INBOUND_CREATE_ENABLED=true` 이지만 인바운드 트래픽 자체가 없다.
* 발현 조건: 인바운드 수신이 실제로 시작되는 시점. 켜기 전에 되살릴 것.
* **수정 완료(2026-08-27)**: `_notify_parse_failure(log, missing)` 신설
  (`channel_inbound.py`) — ① 항상 `logger.warning` 으로 `parse_failed`·빠진 항목·chat 정보를
  남긴다(운영 로그에서 grep 가능) ② **그룹 채팅에만** 빠진 항목을 적어 회신한다.
  고객 1:1 대화(userChat)에는 자동 안내를 보내지 않는다 — 자동 실패 메시지가 고객에게
  나가면 안 되고, `channel_client` 도 그룹 전송만 지원한다. 환경변수 미설정이면 조용히
  건너뛴다(수신 처리를 깨뜨리지 않는다).
* 테스트: `tests/domains/test_channel_inbound_parse_failure.py` 6개 — 그룹 회신·userChat
  무회신·chat_id 없음·미설정 skip·로그 항상 남김·worker 실제 경로(배선을 빼면 red).

## 깨끗하다고 확인한 것 (재조사 낭비 방지)

* except 무음 삼킴 **0건**. `db.rollback()` 만 있는 것처럼 보이는 8곳
  (`messages.py`·`rooms.py`·`socketio_handlers.py`)은 전부 `log_handled_exception()` 동반 +
  500 반환이다(정적 스캔 오탐이었다).
* 나머지 except 는 int 파싱 폴백이고 400/None/0 으로 정상 처리된다
  (`channel_integration.py:568`, `channel_security.py:145·177`, `channel_policy.py:50`,
  `channel_as_attachments.py:38`).
* 레거시 자동 푸시는 퇴역 상태다. `channel_delivery_logs` 3,963행(`api_failed` 2,544 ·
  `sent` 1,300 · `ignored_stale` 119)은 **2026-06-18 이후 정지** — 옛 흔적이지 현재 실패가 아니다.
* 외부 토큰 규율(expires_in 기반 TTL · 401 재발급 재시도)은
  `tests/contracts/test_external_token_client_discipline.py` 가 강제한다.
