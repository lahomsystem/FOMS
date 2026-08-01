# Signature Validation & Security Spec (CT-C-01, 02)

## 1. X-Signature 검증 (CT-C-01)
ChannelTalk의 모든 Webhook 및 Native Function 호출은 요청이 위변조되지 않았고, 신뢰할 수 있는 소스(ChannelTalk)에서 발생했음을 보장하기 위해 `X-Signature` 헤더를 포함한다.

### 검증 방식
1. 수신한 HTTP Request의 원본 Body(Raw bytes)를 확보한다.
2. 환경변수에 저장된 `CHANNEL_SIGNING_KEY`를 Secret Key로 사용하여 `HMAC-SHA256` 해시를 생성한다.
3. 생성된 해시와 `x-signature` 헤더의 값을 `hmac.compare_digest()`로 안전하게 비교한다. (타이밍 공격 방지)
4. 검증 실패 시 `401 Unauthorized` 또는 `403 Forbidden` JSON 응답을 반환한다. (HTML 리다이렉트 금지)

## 1-A. Function 전용 서명 (CHANNEL-FUNCTION-CONTRACT-01)

ChannelTalk **Native Function**(`/api/channel/functions`) 은 위 Webhook 서명 helper
(`require_channel_signature`, `CHANNEL_SIGNING_KEY`, raw UTF-8 key + hex digest)를 **재사용하지
않는다**. Function 은 다음 전용 서명 체계를 소유한다(`foms/api/channel/channel_functions.py`).

### 서명 검증 방식 (`verify_function_signature`)
1. 서명 key = `CHANNEL_FUNCTION_SIGNING_KEY` 를 **hex-decode** 한다. decode 결과가 **32 byte
   미만이면 거부**한다. raw UTF-8 key 사용 금지.
2. 서명 대상 = 수신한 요청의 **원본 body(raw bytes)**. 재직렬화(re-serialize)하지 않는다.
3. digest = 위 key 로 `HMAC-SHA256` → **Base64 인코딩**한다(hex digest 금지).
4. `x-signature` 헤더값과 `hmac.compare_digest()` 로 **constant-time** 비교한다.
5. 미서명/위조/형식오류 → `401 Unauthorized`(JSON). body 파싱 불가(invalid JSON) → `400`.

### enable gate·설정 (provider-first)
- `CHANNEL_FUNCTION_ENABLED` 이 `true` 일 때만 활성화된다. 미설정/`false`(기본) 이면 blueprint 가
  없는 것처럼 **모든 method 를 404** 로 닫고 provider 를 호출하지 않는다(provider-first disable
  gate). 비활성화는 반드시 ChannelTalk 쪽 Function 등록/호출 disable 이 **선행**한다.
- enable 상태에서 `CHANNEL_FUNCTION_SIGNING_KEY`(hex≥32B) 또는 `CHANNEL_FUNCTION_CHANNEL_ID`
  가 없으면 **앱 기동 실패(fail-start)**. 조용한 우회 없이 기동 단계에서 차단한다.

### method·context 계약
- 공식 method 는 **PUT** 만 provider contract 다. `POST`/`GET` → `405`.
- 서명이 덮는 `context.channel.id` 를 `CHANNEL_FUNCTION_CHANNEL_ID` 와 **exact 비교**한다(불일치
  → 401). 인증 주체(caller) 는 서명된 `context.caller`(`type == "manager"`) 에서만 취한다
  (params/미서명 필드에서 추정 금지).
- 등록 method 는 `channel_functions.REGISTERED_FUNCTION_METHODS`(정본) + `tests/fixtures/
  channeltalk/function_method_schema.json`(manifest) 에 exact 스키마로만 존재한다. wildcard·
  accept-all params 금지, stale 항목 금지. 미등록 method 는 deny 와 구분 불가한 generic 오류.
- read-only Function 이므로 **PII/mutation 0**. success/deny/error 모두 HTTP `200` provider 봉투
  (`{result|error}`) 로 답하고, deny 와 nonexistent 는 동일한 generic 결과다(존재 여부 미노출).

## 2. Replay Attack 방어 (CT-C-02)
재전송 공격을 막기 위해 타임스탬프 윈도우 검증을 추가로 수행한다.
- ChannelTalk Webhook Payload 내부에 있는 `entity.createdAt` 등 생성 시간(ms)을 기준으로 현재 서버 시간과 비교한다.
- **기본 윈도우 (Replay Window)**: 300초 (5분)
- 5분을 초과한 과거의 Payload이거나 너무 먼 미래의 Payload일 경우 `403 Forbidden` 처리한다.

## 3. 적용 대상
- `/api/channel/functions` 하위 모든 라우트 → **1-A 의 Function 전용 서명 체계**(`CHANNEL_FUNCTION_SIGNING_KEY`, hex-decode key + Base64 digest). 위 1 장의 Webhook helper 를 재사용하지 않는다.
- `/api/channel/webhooks` 하위 모든 라우트 → 1 장의 Webhook 서명 체계(`CHANNEL_SIGNING_KEY`).
- (참고) WAM 라우트는 이 서명 체계가 아니라 별도의 단기(Launch) Token 체계로 보호된다.
