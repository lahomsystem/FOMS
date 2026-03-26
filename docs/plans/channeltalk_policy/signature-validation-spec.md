# Signature Validation & Security Spec (CT-C-01, 02)

## 1. X-Signature 검증 (CT-C-01)
ChannelTalk의 모든 Webhook 및 Native Function 호출은 요청이 위변조되지 않았고, 신뢰할 수 있는 소스(ChannelTalk)에서 발생했음을 보장하기 위해 `X-Signature` 헤더를 포함한다.

### 검증 방식
1. 수신한 HTTP Request의 원본 Body(Raw bytes)를 확보한다.
2. 환경변수에 저장된 `CHANNEL_SIGNING_KEY`를 Secret Key로 사용하여 `HMAC-SHA256` 해시를 생성한다.
3. 생성된 해시와 `x-signature` 헤더의 값을 `hmac.compare_digest()`로 안전하게 비교한다. (타이밍 공격 방지)
4. 검증 실패 시 `401 Unauthorized` 또는 `403 Forbidden` JSON 응답을 반환한다. (HTML 리다이렉트 금지)

## 2. Replay Attack 방어 (CT-C-02)
재전송 공격을 막기 위해 타임스탬프 윈도우 검증을 추가로 수행한다.
- ChannelTalk Webhook Payload 내부에 있는 `entity.createdAt` 등 생성 시간(ms)을 기준으로 현재 서버 시간과 비교한다.
- **기본 윈도우 (Replay Window)**: 300초 (5분)
- 5분을 초과한 과거의 Payload이거나 너무 먼 미래의 Payload일 경우 `403 Forbidden` 처리한다.

## 3. 적용 대상
- `/api/channel/functions` 하위 모든 라우트
- `/api/channel/webhooks` 하위 모든 라우트
- (참고) WAM 라우트는 이 서명 체계가 아니라 별도의 단기(Launch) Token 체계로 보호된다.
