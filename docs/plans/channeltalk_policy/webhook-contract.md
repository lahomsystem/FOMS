# Webhook Contract (CT-E)

## 1. 개요
ChannelTalk Webhook의 수신, 중복 방지(Deduplication), 비동기 처리 경계(Ack)에 대한 명세를 정의한다.

## 2. 식별자 생성 규칙

### 2.1 `dedupe_key` (Receipt-level 중복 방지)
모든 webhook 수신 건에 대해 반드시 생성해야 하며, 다음 우선순위로 결정한다.
1. `provider_event_id` (채널톡이 제공하는 Webhook 고유 ID가 있을 경우)
2. Provider가 주는 Stable Message Key 조합 (예: `chat_id` + `message_id`)
3. 마지막 Fallback: 제한된 replay-window hash (이 경우 Receipt 로깅 및 Dry-run에만 허용, 생성(Create) 기능 불가)

### 2.2 `creation_key` (Create-level 멱등성)
실제 FOMS의 Draft Order나 Task를 생성하기 위한 멱등성(Idempotency) 보장 키다.
- `provider_event_id` 또는 Stable Provider Message Key로만 만든다.
- Replay-window hash는 절대 사용하지 않는다. (생성 안전성 확보)
- `creation_key`가 없는 페이로드는 `create-enabled` 모드로 승격되지 않고 Dry-run 처리 또는 무시된다.

## 3. Webhook 응답(Ack) 경계 계약
Webhook 수신 엔드포인트(`/api/channel/webhooks`)는 아래 조건을 만족할 때만 HTTP 2xx(200) 응답을 반환한다.
1. `ChannelInboundEventLog` (Receipt Log) DB 저장 완료 (`commit`)
2. 비동기 후속 처리(Worker)를 위한 RQ `enqueue` 성공

**예외 및 실패 시 응답:**
- **Queue Unavailable / Enqueue Failed:** 큐가 연결되지 않거나 enqueue가 실패하면 DB에 `queue_enqueue_failed` 상태로 남기고, ChannelTalk 측에는 HTTP 503을 반환하여 Provider 차원의 Retry를 유도한다. (단, Provider 정책에 따라 달라질 수 있으므로 내부적으로 Inbound Sweeper가 재큐잉하도록 설계한다.)
- **Duplicate Receipt (중복 수신):**
  - 기존 Receipt가 이미 `worker_processing`, `created`, `parse_failed`, `rejected_*`, `ignored_*` 등 Terminal 상태이거나, Enqueue에 성공한 상태일 때만 HTTP `200 no-op` (ex: `{"status": "duplicate_ignored"}`)로 응답하여 Provider의 재시도 폭증을 막는다.
  - 기존 Receipt가 `received` 또는 `queue_enqueue_failed` 상태인 경우, 단순히 `200`으로 무시하지 않고 재enqueue를 시도한다. (실패 시 503 반환)

## 4. 모드 분리
- **Dry-run 모드:** 수신된 Webhook을 파싱하고 유효성 검사까지만 수행하며, 실제 데이터(주문, 태스크)는 생성하지 않는다. (`status: dry_run_completed`)
- **Create-enabled 모드:** 파싱 후 실제 FOMS 시스템에 데이터를 생성한다. (`status: created`, `created_order_id` 등에 레퍼런스 기록)
