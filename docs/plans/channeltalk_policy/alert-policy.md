# Alert & Deduplication Policy (CT-B-03)

## 1. Deduplication (중복 제거)
네트워크 지연이나 연속된 버튼 클릭으로 인해 동일한 알림이 중복 발송되는 것을 방지.

### 1.1. Dedupe Window 설정
- **기본 Window**: 60초 (1분)
- **긴급/수동 푸시**: 0초 (즉시 발송 허용)
- **구현 방식**: 동일한 `event_key` (예: `order_123_update`)로 Redis 큐 또는 `ChannelDeliveryLog`의 최근 발송 이력을 검사하여, Window 이내면 `ignored_duplicate` 처리.

## 2. Rate Limiting (발송 빈도 제어)
채널톡 API의 Rate Limit (429 Too Many Requests) 대응.
- API 레벨의 Rate Limit 발생 시 `token_rate_limited` 상태로 로깅.
- Worker는 Exponential Backoff (예: 5s, 15s, 30s) 전략으로 재시도 (최대 3회).
- 최대 재시도 초과 시 `api_failed` 처리 후 관리자에게 Alert.

## 3. 수동 푸시 승인 및 운영 정책
- **대상**: ERP의 "채널톡으로 주문 정보 수동 전송" 버튼 사용 시.
- **제한**: 권한이 있는 사용자(ADMIN, MANAGER, STAFF)만 가능.
- **재전송 표시**: 이미 전송된 이력이 있는 상태에서 다시 전송하면 `[수정]` Prefix가 자동으로 추가됨.
- **Payload**: 수동 푸시는 사용자가 입력한 텍스트를 그대로 전송하며, 첨부파일 정책에 따라 파일이 함께 전송됨.
