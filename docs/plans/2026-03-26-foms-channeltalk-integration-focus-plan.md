# FOMS <> ChannelTalk 연동 집중 계획서

작성일: 2026-03-26
상태: 감리완료 (v3)
감리일: 2026-03-27
관련 문서:
- `docs/plans/2026-03-13-channeltalk-integration-plan.md`
- `docs/evolution/2026-03-16-CHANNELTALK-GOOGLE-SHEET-WEBHOOK-ANALYSIS.md`

## 1. 결정과 범위

### 1.1 이번 결정
- FOMS 자체 채팅은 이번 단계에서 제거하지 않는다.
- 이번 문서의 범위는 `FOMS <> ChannelTalk 연동 강화`에 한정한다.
- 목표는 "메신저 대체 기능 개발"이 아니라 "알림 전달, 빠른 확인, 최소 액션, 선택적 자동화"를 ChannelTalk 중심으로 올리는 것이다.

### 1.2 이번 단계의 비목표
- FOMS 채팅 제거
- chat table 정리 및 migration
- `/chat` UI 퇴역
- 채팅 코드 리팩터

### 1.3 근본 원인
- 현재 문제는 채팅 기능 유무가 아니라, ERP 웹이 모바일 알림과 메신저 UX까지 직접 떠안는 구조다.
- FOMS는 주문/일정/상태 변경의 원본 시스템으로는 적합하지만, 모바일 즉시성과 커뮤니케이션 레이어는 ChannelTalk가 더 적합하다.
- 따라서 근본 해결 방향은 `FOMS = 원본 시스템`, `ChannelTalk = 전달/알림/빠른 액션 표면`이다.

## 2. 현재 상태와 코드 기준 사실

### 2.1 이미 구현된 것

| 영역 | 현재 상태 | 근거 파일 |
|------|-----------|-----------|
| 수동 푸시 | ERP Beta에서 ChannelTalk 수동 전송 가능 | `templates/partials/erp_beta_tab.html`, `templates/partials/erp_beta_js.html`, `apps/api/channel_integration.py` |
| 자동 푸시 | 구조화 저장, 실측 수정, 출고 설정 수정, 결제 확인 변경은 diff payload와 함께 outbox enqueue 수행 | `apps/api/erp_orders_structured.py`, `apps/api/erp_measurement.py`, `apps/api/erp_shipment_settings.py`, `services/jobs/queue.py`, `services/jobs/tasks.py` |
| Channel API 래퍼 | `issueToken`, `writeGroupMessage`, short-link/WAM 보조 로직 존재. 현재 runtime 그룹 라우팅은 대부분 `CHANNEL_GROUP_MEASUREMENT` 중심 | `services/channel_client.py`, `services/channel_policy.py`, `services/channel_security.py` |
| 앱 연결점 | ChannelTalk API용 blueprint 등록 완료 | `app.py`, `apps/api/channel_integration.py` |
| 운영 분석 | Google Sheet/Webhook 충돌 분석 문서 존재 | `docs/evolution/2026-03-16-CHANNELTALK-GOOGLE-SHEET-WEBHOOK-ANALYSIS.md` |

### 2.2 2026-03-26 초안 시점 기준 아직 없던 것
- Command 자동 등록 로직
- Function Endpoint와 `X-Signature` 검증
- WAM 앱 셸
- ChannelTalk manager <> FOMS user 매핑
- inbound webhook endpoint
- durable delivery log
- retry / dedupe / idempotency 정책
- 운영용 resend / requeue / failure triage 화면

### 2.3 현재 구현의 구조적 공백
- `apps/api/erp_orders_structured.py`는 저장 후 `enqueue_channeltalk_push(...)`만 호출한다.
- `services/jobs/queue.py`는 큐 등록 성공 여부만 반환하고, 실패 시 durable fallback이 없다.
- `services/jobs/tasks.py`는 worker 실패 시 로그는 남기지만, 재시도/보류/운영 확인용 상태 저장이 없다.
- `services/channel_client.py`는 현재 `issueToken` 캐시 중심이며, refresh token 기반 안정화가 없다.
- `models.User`에는 ChannelTalk manager 식별자를 저장할 구조가 없다.

이 공백 때문에 지금 연동은 "동작은 가능하지만 운영 보장과 관측성이 약한 상태"다.

### 2.4 2026-03-27 구현 반영 메모
- automatic push는 이제 outbox row 생성 시 `template_key`, `masked_request_payload`에 이벤트별 diff payload를 함께 저장한다.
- worker는 `event_key`를 추측용 fallback으로만 쓰고, 기본적으로 저장된 `template_key`와 payload snapshot을 사용해 본문을 만든다.
- 현재 diff-aware automatic push가 적용된 경로는 다음 4개다.
  - structured 저장
  - 실측 담당/주소/연락처 수정
  - 출고/시공 설정 수정
  - 결제 확인 변경
- 주문 상세 링크 계약은 다음처럼 고정한다.
  - 사용자에게 노출되는 primary: `/w/{token}`
  - 내부 최종 도착지: `/channel/wam/?launch_token=...`
  - 서버 fallback: `/edit/{order_id}?open=erp-beta`
  - legacy compatibility: `/erp/orders/{order_id}`는 Flask redirect로 유지
- `services/channel_dispatch.py`와 `services/channel_policy.py`는 현재 runtime contract 기준으로 위 링크 계약과 change-lines 렌더링을 사용한다.

이 메모는 2026-03-27 기준 구현 상태를 반영하며, 위 범위에 대해서는 기존 2.2~2.3의 미구현 서술보다 우선한다.

### 2.4A 2026-03-27 현재 기준 아직 미구현/부분 구현
- 개인 involved 알림 transport는 아직 미구현이다. 현재 runtime push는 사실상 공통 그룹 중심이다.
- manager-user 매핑은 모델/서비스는 있으나 운영 UI와 파일럿용 완성 절차는 없다.
- Command 자동 등록 bootstrap은 없다.
- WAM은 read-only이며 write action은 없다.
- 운영 지표 중 `parse_success_rate`는 참고용이며, rollout auto gate의 단일 source로 쓰기에는 아직 정합성 보강이 더 필요하다.
- feature flag는 현재 대부분 readiness/운영 계약용이며, route hard-off switch를 완전히 대체하지는 않는다.
- manual push는 여전히 admin/manual 직행 경로이며, automatic outbox/source-of-truth 전환 범위와 동일하게 취급하지 않는다.

### 2.5 2026-03-27 목적 재정의 메모
- ChannelTalk 연동의 1차 목적을 아래 두 가지로 다시 고정한다.
  - `개인 involved 알림`: 각 담당자가 자기와 관련된 task / 일정 / 상태 변경을 모바일 백그라운드 알림으로 빠르게 인지한다.
  - `빠른 주문 접근`: ChannelTalk 메시지 클릭으로 FOMS 주문 상세에 바로 들어간다.
- 따라서 v2 계획의 기본 알림 구조는 `공통 그룹 단일 알림`이 아니라 `개인 알림 + 공통 notice + 필요 시 둘 다 발송`이다.
- 개인 알림은 `담당자`, `drawing manager`, `construction worker`, `task assignee`, `owner team의 실제 수신자`를 우선 대상으로 한다.
- 공통 notice는 `팀 전체가 알아야 하는 변경`, `긴급 이슈`, `일정 확정`, `운영 공지` 중심으로 좁힌다.
- 이 재정의는 모바일 백그라운드 푸시 목적과 직접 연결된다. 그룹 일반 메시지만으로는 팀원 앱 설정에 따라 즉시 인지가 보장되지 않으므로, 개인 involved 메시지 경로를 별도 설계 대상으로 포함한다.

## 3. ChannelTalk 공식 문서 기반 제약

### 3.1 공식적으로 가능한 것
- Custom App은 `Native Function`, `Function Endpoint`, `Commands`, `WAM` 조합으로 설계할 수 있다.
- `issueToken`으로 app-token 또는 channel-token을 발급받아 ChannelTalk 기능을 호출할 수 있다.
- `writeGroupMessage`로 FOMS 이벤트를 그룹 채팅에 푸시할 수 있다.
- Function Endpoint 요청에는 `X-Signature`가 포함되며, Signing Key 기반 HMAC 검증이 필요하다.
- Command는 서버 시작 시 등록하는 흐름이 권장된다.
- WAM은 SPA이며 Desk/Front 안의 격리된 iframe에서 동작한다.
- Webhook 응답에는 quick reply를 포함할 수 있다.

### 3.2 계획에 반영해야 할 제약
- WAM/Command는 Desk/Front 중심으로 설계한다.
- 모바일에서의 리치 액션은 초기 범위에 넣지 않는다.
- `issueToken`/`refreshToken` rate limit를 고려한 토큰 운영이 필요하다.
- Webhook은 v1에서 지정 그룹만 대상으로 좁혀 시작한다.

## 4. 목표 제품 결과

### 4.1 사용자 관점 최종 상태
- ERP 담당자는 중요한 이벤트를 ChannelTalk에서 먼저 본다.
- ChannelTalk 안에서 주문 핵심 정보와 일정, 담당, 첨부를 빠르게 확인할 수 있다.
- 일부 핵심 액션은 ChannelTalk에서 바로 처리할 수 있다.
- 지정 그룹에 올라온 표준 메시지는 FOMS Draft/Task로 연결된다.
- FOMS 채팅은 그대로 남아 있지만, 운영의 중심은 ChannelTalk로 이동한다.

### 4.2 제품 원칙
- FOMS가 권한 판단과 최종 저장을 담당한다.
- ChannelTalk는 전달/확인/빠른 액션 표면을 담당한다.
- 운영자는 실패 건을 재전송하거나 보류 처리할 수 있어야 한다.
- 알림이 많아져도 소음 제어 규칙이 먼저 있어야 한다.

### 4.3 개인 알림 + 공통 알림 목표 모델
- `개인 알림`
  - 목적: "내가 지금 바로 봐야 하는 변경"을 놓치지 않게 한다.
  - 채널: ChannelTalk 개인 DM 또는 개인 전용 chat 경로
  - 예시: 내 task 상태 변경, 내 일정 변경, 내 담당 주문 변경, 내 확인 요청
- `공통 notice`
  - 목적: 팀 전체가 알아야 하는 내용을 공용 채널에서 공유한다.
  - 채널: 기존 공용 그룹
  - 예시: 긴급 건, 일정 확정, 시공 이슈, 운영 공지
- `개인 + 공통 둘 다`
  - 목적: involved person에게는 즉시 인지, 팀에는 맥락 공유를 동시에 보장한다.
  - 예시: 긴급 일정 변경, 고객 클레임 급건, 마감 임박 중요 건
- 사용자 경험 기준 최종 상태:
  - 개인은 자기 일만 바로 받는다.
  - 팀은 공통 이슈만 모아 받는다.
  - 모든 메시지는 FOMS 주문 접근 링크를 포함한다.
- 경계:
  - 이 모델은 `목표 상태`다.
  - 2026-03-27 현재 구현은 아직 `공통 그룹 중심 + 일부 read-only surface` 단계다.

## 5. 구현 방향

### 5.1 수정/추가 대상 파일 방향

| 구분 | 파일 | 방향 |
|------|------|------|
| 기존 유지/확장 | `services/channel_client.py` | 토큰 전략, native function 래퍼, 메시지 포맷, 라우팅 강화 |
| 기존 유지/확장 | `apps/api/channel_integration.py` | 수동 푸시 + resend + health 등 admin/manual 전용 유지 |
| 기존 유지/확장 | `services/jobs/queue.py` | enqueue 정책과 실패 시 계약 명확화 |
| 기존 유지/확장 | `services/jobs/tasks.py` | worker 처리, 재시도 연계, delivery 상태 기록 |
| 기존 유지/확장 | `apps/api/erp_orders_structured.py` | 이벤트 emit 기준과 enqueue 시점 정교화 |
| 신규 권장 | `services/channel_security.py` | `X-Signature` 검증, replay 방지, timestamp 검사 |
| 신규 권장 | `services/channel_delivery.py` | outbox, dedupe key, retry, resend, status 변경 |
| 신규 권장 | `services/channel_identity.py` | ChannelTalk manager <> FOMS user 매핑 로직 |
| 신규 권장 | `apps/api/channel_functions.py` | command/function endpoint 라우팅 |
| 신규 권장 | `apps/api/channel_webhooks.py` | inbound webhook receiver |
| 신규 권장 | `apps/api/channel_wam.py` | WAM shell/bootstrap route |
| 신규 권장 | `templates/channel_wam*.html` 또는 partial | WAM 셸 및 UI |

### 5.2 권장 데이터 저장 구조

현재 구조만으로는 운영 추적이 약하다. 아래 구조는 함께 가야 한다.

1. `ChannelDeliveryLog`
- 목적: FOMS -> ChannelTalk 전송 상태 영속화
- 타입 결정: `status`는 `String(50)` — ENUM 미사용 (상태 코드 추가 시 migration 불필요, 기존 FOMS 패턴 일관)
- 유효 상태 코드는 `constants.py`의 `CHANNEL_DELIVERY_STATUS` 집합으로 저장 전 검증
- 재시도 전략: **동일 row UPDATE 방식** — 같은 event_key의 재시도는 기존 row의 status/retry_count를 갱신. resend(운영자 재전송)는 새 row를 생성하고 `parent_delivery_id`로 원본 참조.
- 필드:
  - `id` Integer PK
  - `event_key` String(200) NOT NULL — 이벤트 식별자
  - `source_type` String(50) NOT NULL — 'order', 'task' 등
  - `source_id` Integer NOT NULL — 원본 레코드 id
  - `target_type` String(50) NOT NULL — 'group', 'manager' 등
  - `target_id` String(200) NOT NULL — 대상 식별자
  - `status` String(50) NOT NULL DEFAULT 'pending'
  - `retry_count` Integer NOT NULL DEFAULT 0
  - `next_retry_at` DateTime nullable — 지수 백오프 재시도 시각
  - `last_error` Text nullable
  - `message_id` String(200) nullable — ChannelTalk 응답 메시지 id
  - `masked_request_payload` JSONColumn nullable — presigned URL 마스킹 후 저장
  - `masked_response_payload` JSONColumn nullable
  - `rendered_text_snapshot` Text nullable — 원본 snapshot resend용 불변 본문
  - `file_snapshot` JSONColumn nullable — 원본 snapshot resend용 첨부 목록(`snapshot_object_key`, `snapshot_checksum`, `file_name`, `mime`, `channel_file_id`). 원본 주문 첨부 경로를 그대로 재사용하지 않고 write-once snapshot 또는 provider durable file id만 저장한다.
  - `target_group_snapshot` String(200) nullable — 원본 대상 그룹 snapshot
  - `template_key` String(100) nullable
  - `template_version` Integer nullable
  - `source_version` Integer nullable — committed outbox row 시점의 `orders.channel_source_seq`
  - `parent_delivery_id` Integer nullable FK('channel_delivery_logs.id') — resend 원본 참조
  - `correlation_id` String(100) nullable — 요청 추적 id
  - `actor_type` String(30) nullable — 'system', 'user', 'worker'
  - `actor_id` Integer nullable — 트리거한 사용자/시스템 id
  - `order_id` Integer nullable FK('orders.id', ondelete='SET NULL') — 조회 최적화 전용
  - `wave` String(20) nullable — pilot wave 추적
  - `request_id` String(100) nullable — HTTP 요청 추적
  - `created_at` DateTime NOT NULL DEFAULT now()
  - `sent_at` DateTime nullable
  - `updated_at` DateTime nullable — 상태 변경 시각

2. `ChannelManagerLink`
- 목적: ChannelTalk manager와 FOMS user 매핑
- 감사 필드는 매핑 테이블 역할에 맞게 선별 적용 (correlation_id 등 이벤트 감사 필드 미적용)
- 필드:
  - `id` Integer PK
  - `channel_manager_id` String(200) NOT NULL — 1차 식별자
  - `channel_manager_email` String(200) nullable — 참고용, 인증 근거로 미사용
  - `user_id` Integer FK('users.id', ondelete='SET NULL') nullable
  - `is_active` Boolean NOT NULL DEFAULT true
  - `linked_at` DateTime NOT NULL DEFAULT now() — 매핑 생성 시각
  - `last_verified_at` DateTime nullable — 최근 검증 시각
  - `deactivated_at` DateTime nullable — 비활성화 시각
  - `deactivated_by_user_id` Integer nullable FK('users.id') — 비활성화 처리자

3. `ChannelInboundEventLog`
- 목적: inbound webhook 원본과 파싱 결과 추적
- PII 보호: 고객 채팅 본문/발신자명은 저장 전 마스킹. raw payload 전문 저장은 30일 보존 후 자동 삭제.
- 필드:
  - `id` Integer PK
  - `provider_event_id` String(200) nullable — provider가 주는 경우에만 저장
  - `dedupe_key` String(200) NOT NULL UNIQUE — receipt-level 중복 방지 키. 생성 규칙은 CT-00-06 payload fixture로 고정한다. 우선순위는 `provider_event_id` -> provider가 주는 stable message key 조합 -> 마지막 fallback으로 제한된 replay-window hash. 마지막 fallback은 receipt logging/dry-run에만 허용하고 create-enabled idempotency에는 사용하지 않는다.
  - `creation_key` String(200) nullable UNIQUE — Draft/Task 생성용 durable idempotency key. `provider_event_id` 또는 stable provider message key로만 만든다. replay-window hash는 금지한다.
  - `payload_hash` String(64) NOT NULL — SHA-256
  - `raw_payload` JSONColumn nullable — 30일 후 null 처리
  - `chat_type` String(50) nullable
  - `source_chat_id` String(200) nullable
  - `status` String(50) NOT NULL DEFAULT 'received'
  - `parsed_result` JSONColumn nullable — PII 마스킹 후 저장
  - `error_reason` Text nullable
  - `correlation_id` String(100) nullable
  - `wave` String(20) nullable
  - `source_manager_id` String(200) nullable — 발신 manager 식별자
  - `created_order_id` Integer nullable FK('orders.id', ondelete='SET NULL') — 생성된 주문 backlink
  - `created_task_id` Integer nullable FK('order_tasks.id', ondelete='SET NULL') — 생성된 태스크 backlink
  - `created_order_ref` String(100) nullable — 롤백/감사용 immutable 주문 식별자 snapshot
  - `created_task_ref` String(100) nullable — 롤백/감사용 immutable 태스크 식별자 snapshot
  - `received_at` DateTime NOT NULL DEFAULT now()
  - `processed_at` DateTime nullable

4. `Order.channel_source_seq`
- 목적: stale 판정용 단조 증가 버전 제공
- 필드:
  - `channel_source_seq` Integer NOT NULL DEFAULT 0
- migration 전략:
  - expand: 기존 `orders` 테이블에는 temporary `server_default 0`로 컬럼을 추가한다.
  - backfill: 기존 row를 `0`으로 채우고, 배포 중간 버전 코드는 `NULL`을 읽더라도 `0`으로 취급하지 않도록 허용하지 않는다.
  - contract: backfill 검증 후 `NOT NULL`을 확정하고, 필요 시 model/server default를 정리한다.
- 규칙:
  - ChannelTalk 연동에 영향을 주는 주문 변경은 같은 DB 트랜잭션 안에서 `channel_source_seq += 1`과 pending `ChannelDeliveryLog` outbox row INSERT까지 수행한다.
  - Redis enqueue는 commit 이후 `delivery_id` 기준으로만 수행한다. commit 전에 queue push를 호출하지 않는다.
  - commit 이후 enqueue가 실패하면 짧은 후속 트랜잭션에서 해당 delivery row를 `queue_enqueue_failed`로 남기고, sweeper/requeue가 재처리한다.
  - `structured_updated_at`은 표시/이력 용도로 유지하되 stale 판정의 기준값으로 사용하지 않는다.

설계 원칙:
- 단순 JSON 누적보다 전용 테이블로 간다.
- 이유는 resend, dedupe, audit, rollback 판단을 해야 하기 때문이다.
- 감사 필드는 모델 역할에 맞게 선별 적용한다 (3개 모델에 기계적으로 동일 적용하지 않는다).
- JSONColumn 계열 필드 수정 시 `copy.deepcopy` + `flag_modified` 패턴을 적용한다.
- GIN 인덱스는 payload 내부 검색이 불필요하므로 추가하지 않는다.
- 모델 필드 타입은 `models.py`의 호환 레이어인 `JSONColumn`을 사용하고, PostgreSQL 전용 최적화는 Alembic DDL에서만 수행한다.

### 5.3 환경 변수/설정 정리

필수:
- `CHANNEL_APP_ID`
- `CHANNEL_APP_SECRET`
- `CHANNEL_ID`
- `CHANNEL_SIGNING_KEY`
- `CHANNEL_GROUP_MEASUREMENT`
- `CHANNEL_GROUP_CONSTRUCTION`
- `CHANNEL_GROUP_GENERAL`
- `FOMS_BASE_URL`

- `FOMS_BASE_URL`은 환경별 명시값으로만 설정한다. production Railway URL fallback은 금지한다.
- `services/channel_client.py`는 import 시점 고정값이 아니라 runtime/lazy config로 `FOMS_BASE_URL`을 읽어야 한다.

권장 추가:
- `CHANNEL_COMMAND_ENABLED`
- `CHANNEL_WEBHOOK_ENABLED`
- `CHANNEL_PUSH_ENABLED`
- `CHANNEL_PUSH_DRY_RUN`
- `CHANNEL_COMMAND_BOOTSTRAP_ENABLED`
- `CHANNEL_COMMAND_BOOTSTRAP_MODE`
- `CHANNEL_ALLOWED_GROUP_IDS`
- `CHANNEL_REPLAY_WINDOW_SECONDS`
- `CHANNEL_RUNTIME_POLICY_VERSION`

### 5.4 보안 계약
- 모든 function/webhook endpoint는 `X-Signature` 검증 필수
- timestamp 기반 replay 방지
- 허용 그룹/허용 manager 화이트리스트
- 쓰기 액션은 FOMS role 재검증 후 수행
- 실패/권한 거부는 audit log로 남김
- provider-facing endpoint(`functions`, `webhooks`, WAM action API)는 `@login_required`, `@role_required`를 사용하지 않는다.
- provider-facing endpoint의 실패 응답은 redirect/HTML이 아니라 JSON만 사용한다.
- 응답 매트릭스는 아래처럼 고정한다.
  - `401`: signature 불일치, launch/action token 위조, 만료된 token
  - `403`: 서명은 맞지만 허용되지 않은 manager/group/context, 매핑 없는 사용자
  - `409`: 유효한 요청이지만 business conflict(이미 처리된 write action, 잘못된 상태 전이, binding mismatch)
  - `503`: queue unavailable 등 일시 장애
  - webhook duplicate receipt는 기존 receipt가 이미 enqueue 성공 또는 terminal 상태일 때만 provider 재시도 폭증을 막기 위해 `200 no-op`로 응답한다.

### 5.5 엔드포인트 소유권 고정
- `apps/api/channel_integration.py`
  - 수동 푸시
  - resend/requeue
  - health/check
  - admin/manual 운영 경로만 담당
- `apps/api/channel_functions.py`
  - `/api/channel/functions`
  - command/function callback 전담
- `apps/api/channel_webhooks.py`
  - `/api/channel/webhooks`
  - inbound receiver + dedupe 진입점 전담
- `apps/api/channel_wam.py`
  - `/channel/wam`
  - WAM shell/bootstrap 전담

원칙:
- manual/admin 경로와 provider callback 경로를 같은 blueprint에 섞지 않는다.
- 서명 검증은 `channel_security.py` 공용 계층에서만 수행한다.

### 5.6 전송 계약
- 모든 push는 `event_key`를 가진다.
- 동일 `event_key`는 재시도여도 중복 전송으로 집계하지 않는다.
- 큐 등록 실패와 API 전송 실패를 구분한다.
- 최종 실패 건은 운영자가 재전송할 수 있어야 한다.
- "성공 여부를 모르는 상태"를 없애는 것이 목표다.

추가 구현 메모:
- automatic push의 runtime payload는 최소 `event_type`, `event_title`, `change_lines`, `changed_by`, optional `reason`를 가진다.
- worker는 `event_key` 문자열 파싱보다 `template_key`와 `masked_request_payload`를 우선 신뢰한다.
- `rendered_text_snapshot`과 `target_group_snapshot`은 worker 전송 시점에 실제 발송 본문/그룹 기준으로 채운다.
- 주문 상세 링크는 사용자에게는 `/w/{token}` short link를 primary로 보여주고, 내부 최종 도착지는 `WAM launch token URL`을 사용한다. short-link 생성 실패 시 `/edit/{order_id}?open=erp-beta` fallback을 사용한다.
- legacy 링크 호환을 위해 `/erp/orders/{order_id}`는 redirect route로 유지한다.

### 5.6A 개인 알림 / 공통 알림 라우팅 계약
- 전송 대상을 `target_type = group | manager | direct_chat` 관점으로 분리한다.
- `group`
  - 팀 전체가 알아야 하는 notice에만 사용한다.
  - 현재의 `CHANNEL_GROUP_MEASUREMENT` 단일 경로를 임시 기본값으로 두되, 정책상 "기본 수신 채널"이지 "모든 이벤트의 최종 채널"로 설명하지 않는다.
- `manager`
  - ChannelTalk manager id가 FOMS user에 매핑되어 있고, 개인 involved 알림 정책에 포함되는 경우 사용한다.
  - Native Function 기준으로는 `writeDirectChatMessageAsManager` 또는 동등한 개인 발송 경로를 우선 검토한다.
- `direct_chat`
  - 개인 DM과 manager direct chat를 동일 delivery 개념으로 다루기 위해 target_type에 별도 값을 허용한다.
- canonical personal target identity는 기본적으로 `manager`로 고정한다.
  - dedupe, resend, 지표 집계의 기준 키는 manager 단위다.
  - `direct_chat`은 transport 선택 결과로만 사용하며, canonical identity를 대체하지 않는다.
- 라우팅 정책 함수는 아래를 반환해야 한다.
  - `delivery_targets`: 한 이벤트가 최종적으로 가야 할 대상 목록
  - 각 target별 `target_type`, `target_id`, `template_key`, `priority`, `send_mode(personal|notice|both)`
- 개인 알림은 아래 event class에 우선 적용한다.
  - `task_assigned`
  - `task_status_changed`
  - `manager_changed`
  - `owner_team_changed`
  - `schedule_changed`
  - `approval_requested`
- 공통 notice는 아래 event class에 우선 적용한다.
  - `urgent`
  - `major_stage_changed`
  - `construction_issue`
  - `operations_notice`
- `order_updated` 같은 포괄 이벤트는 개인/공통 아무 쪽에도 무차별 발송하지 않는다. 정책 함수가 diff 내용을 보고 개인/공통 대상 여부를 다시 판정해야 한다.
- 하나의 변경이 개인과 공통 둘 다 대상이면 delivery row를 각각 생성한다. "한 row가 여러 채널을 대표"하지 않는다.
- `mapping miss` 기본 정책은 `skip + 운영 로그`다.
  - personal-only 이벤트를 notice로 자동 승격하지 않는다.
  - notice 또는 both로 분류된 이벤트만 공통 그룹 row를 별도로 생성한다.
- manual push는 이 라우팅 계약의 직접 대상이 아니다.
  - manual push는 계속 admin/manual group-only 경로로 유지한다.
- WAM/Command는 전달 transport가 아니라 read-only access surface다.
  - personal routing 확장은 outbound push 경로에만 우선 적용한다.
- webhook/inbound rollout은 이 계약과 분리된 별도 축이다.
  - personal routing 확장이 webhook phase를 자동으로 당기지 않는다.

### 5.6B 개인 알림 capability 계약
- ChannelTalk 공식 Function 문서 기준으로 Native Function에는 `writeGroupMessage`, `writeUserChatMessage`, `writeDirectChatMessageAsManager` 계열이 존재한다.
- v2 설계에서는 `개인 involved 알림`을 위해 group-only 설계에서 DM-capable 설계로 전환한다.
- Phase B 정책 확정 전까지는 아래 capability spike를 선행한다.
  - 어떤 함수가 현재 설치된 앱 권한과 운영 UX에 가장 맞는지
  - manager direct chat와 user chat 중 어느 경로가 FOMS 운영 구조에 맞는지
  - 모바일 푸시 도달률이 실제로 더 좋은 경로가 무엇인지
- spike 결과가 나올 때까지는 `개인 알림 transport`를 추상화된 target_type 계약으로 먼저 설계하고, 구체 Native Function 선택은 실행 계획에서 고정한다.
- P0 산출물은 최소 아래 5개를 포함해야 한다.
  - `transport-decision.md`: 채택 Native Function, required scope/context, 실패 코드, fallback
  - `mapping-readiness.md`: pilot 대상자 목록, active mapping coverage, 누락자, 운영 owner
  - `mobile-push-test-matrix.md`: iOS/Android, foreground/background, 앱 설정 조합, 기대 결과
  - `payload-fixture-proof.md`: 실제 callback/function payload, permission proof, sample response
  - `routing-policy-table.md`: event class -> send_mode -> canonical target rule

### 5.7 WAM 인증/부트스트랩 계약
- 아래는 `목표 계약`이다.
- 2026-03-27 현재 구현은 `signed token 기반 read-only 접근 + launch token TTL 1시간 + single-use 미구현` 상태다.
- 현재 short-link -> launch-token 경로는 manager mapping 선행을 강제하지 않는다. 아래 trust chain은 목표 계약이다.
- short link `/w/{token}`는 사용자 노출 링크이며, bearer-link 성격이 있으므로 외부 공유에 주의해야 한다.
- 현재 만료 기준:
  - short link: 기본 30일
  - WAM launch token: 기본 1시간
  - 첨부 presigned URL: 기본 1시간
- `/channel/wam`은 raw query param의 `channel_manager_id`를 신뢰하지 않는다.
- v1 신뢰 체인:
  1. 검증된 function/command callback이 서버에 도달한다.
  2. 서버가 manager identity를 검증한 뒤 **단기 WAM launch token**을 발급한다.
  3. `/channel/wam?launch_token=...` 요청은 이 launch token만 신뢰해 bootstrap payload를 만든다.
- launch token payload에는 최소 아래가 필요하다.
  - `channel_manager_id`
  - `mapped_foms_user_id`
  - `allowed_actions`
  - `channel_id`
  - `context_type`
  - `issued_at`
  - `expires_at`
  - `nonce`
- launch token은 `TTL 5분 내외 + single-use`를 기본값으로 둔다.
- direct `/channel/wam` 접근 또는 launch token 없는 접근은 privileged bootstrap payload를 주지 않는다. 필요하면 read-only shell만 렌더링한다.
- v1 WAM 범위는 `read-only`다. write action은 launch token, manager mapping, role 검증, action token 계약이 모두 닫히기 전까지 열지 않는다.
- write action이 열리는 v2부터는 bootstrap 응답에 HMAC-SHA256 기반 **단기 action token**(TTL 5~10분)을 포함한다.
- write action 전용 API는 `apps/api/channel_wam.py` 또는 별도 provider API에 두고, `@login_required` 대신 launch/action token 검증 데코레이터를 사용한다.
- Phase C 이전에 이메일 기반 매핑 코드를 작성하는 것은 금지한다. 매핑 전까지 ChannelTalk 발원 요청은 "읽기 전용" 또는 "명시적 거부"만 허용한다.

### 5.8 서비스 계층 파일 책임 고정
- `services/channel_client.py`
  - ChannelTalk API 호출, `issueToken`/token refresh, HTTP 응답 정규화만 담당한다.
  - FOMS 도메인 판단, DB 상태 전이, 라우팅 규칙 판단은 넣지 않는다.
- `services/channel_dispatch.py`
  - 수동 푸시와 자동 푸시의 공통 진입점이다.
  - 메시지 조립, 대상 그룹 결정, dedupe 판단, delivery 상태 전이를 조율한다.
- `services/channel_delivery.py`
  - `ChannelDeliveryLog` 생성, 상태 전이, 재시도 대상 조회, resend/requeue 대상 조회를 담당한다.
  - 외부 API 호출은 하지 않는다.
  - 모든 함수는 `Session`을 인자로 받으며, 내부에서 임의 commit/rollback 하지 않는다.
- `services/channel_identity.py`
  - ChannelTalk manager와 FOMS user 매핑 조회, 권한 해석, allowed action 계산만 담당한다.
- `services/channel_security.py`
  - `X-Signature`, replay window, payload hash 검증만 담당한다.
  - endpoint별 분기 로직은 두지 않는다.
- `services/jobs/tasks.py`
  - queue worker는 직접 메시지를 조립하지 않고 `channel_dispatch.py`를 호출한다.
  - worker는 dispatch 결과를 `delivery` 계층에 반영하는 최소 orchestration만 가진다.
- `apps/api/channel_integration.py`
  - 관리자/운영자용 수동 푸시, health, resend/requeue 진입점만 둔다.
  - ChannelTalk provider callback은 여기로 받지 않는다.
- `apps/api/channel_functions.py`
  - command/function callback만 받는다.
  - 읽기/쓰기 액션 여부와 관계없이 최종 도메인 변경은 서비스 계층 호출로만 처리한다.
- `apps/api/channel_webhooks.py`
  - inbound receipt, 서명 검증, 허용 그룹 필터, parser 진입점만 가진다.
  - Draft/Task 생성은 별도 서비스 호출로 내린다.
- `apps/api/channel_wam.py`
  - WAM HTML 셸과 bootstrap payload만 담당한다.
  - 비즈니스 write action은 별도 API/service로 보낸다.
- `apps/api/erp_orders_structured.py`
  - 주문 저장 후 "무슨 이벤트를 발행할지"까지만 결정한다.
  - ChannelTalk 템플릿 조립과 외부 API 호출은 직접 하지 않는다.

세션/트랜잭션 계약:
- DB를 건드리는 서비스(`channel_dispatch`, `channel_delivery`, `channel_identity`)는 모두 `Session` 주입형으로 설계한다.
- HTTP route는 request session(`get_db()`)을 열고 commit/rollback의 최종 책임을 가진다.
- worker는 `db_session()`으로 세션을 열고 job 단위 commit/rollback의 최종 책임을 가진다.
- 서비스 계층은 result object를 반환하고, commit/rollback을 숨겨서 호출자와 경쟁하지 않는다.

### 5.9 순서 보장과 idempotency 계약
- 같은 주문에서 짧은 시간 안에 연속 저장이 일어나면 queue 처리 순서가 뒤집힐 수 있다는 전제를 기본으로 둔다.
- 따라서 `event_key`만으로는 부족하고, push마다 `source_version` 비교값을 같이 가진다.
- worker는 자신이 처리 중인 이벤트가 최신 버전보다 오래되었으면 전송하지 않고 `ignored_stale` 상태로 종료한다.
- resend는 "원본 snapshot 재전송"인지 "현재 주문 상태로 재조립 전송"인지 명시적으로 나눈다.
- v1 기본값은 `현재 주문 상태로 재조립`이 아니라 `원본 이벤트 기준 재전송`으로 두고, 운영자가 의도적으로 최신 상태 재전송을 선택할 수 있게 한다.

source_version 구체 설계:
- `ChannelDeliveryLog`는 transaction outbox 역할을 겸한다. 주문 저장 트랜잭션 안에서는 `channel_source_seq` 증가와 pending delivery row INSERT까지만 수행한다.
- `ChannelDeliveryLog.source_version`은 **committed delivery row** 기준의 `Order.channel_source_seq` 값을 저장한다.
- enqueue 호출은 commit 이후 `delivery_id` 기준으로만 수행한다. worker는 DB에서 committed delivery row를 읽는다.
- commit 이후 enqueue 실패는 `queue_enqueue_failed`로 영속화하고, sweeper/requeue job이 `pending`/`queue_enqueue_failed` row를 다시 enqueue한다.
- 이 계약으로 "queue push 성공 후 DB rollback", "worker가 commit 전 row 관측" 경로를 원천 차단한다.
- worker stale 판정 알고리즘:
  ```
  current_order = Order.query.get(delivery.source_id)
   if delivery.source_version < current_order.channel_source_seq:
       mark_ignored_stale(delivery)
       return  # 전송하지 않음
  ```
- `channel_source_seq`는 ChannelTalk 연동에 영향을 주는 저장 경로에서 같은 트랜잭션 안에 증가시킨다.
- `source_version IS NULL` row는 cutover 기간 legacy compatibility 전용이다. stale 보장의 대상이 아니며 `snapshot resend` 기준으로도 쓰지 않는다.
- `structured_updated_at`은 stale 판정 기준이 아니라 표시/정렬용 메타데이터로만 유지한다.
- `Order.structured_schema_version`은 스키마 버전이므로 저장 이력 version 용도로 재사용하지 않는다.

재시도 전략:
- **동일 event_key의 자동 재시도**: 기존 delivery row의 `status`, `retry_count`, `next_retry_at`을 UPDATE한다.
- **운영자 resend**: 새 delivery row를 INSERT하고 `parent_delivery_id`로 원본을 참조한다.
- resend API 응답에 `resend_mode: "snapshot" | "latest"`를 명시하여 혼동을 방지한다.
- `snapshot resend`는 `rendered_text_snapshot`, `file_snapshot`, `target_group_snapshot`을 사용한다.
- snapshot 필드가 비어 있는 legacy row는 `snapshot resend`를 허용하지 않고 `latest resend only`로 제한한다.
- 첨부 snapshot resend는 `file_snapshot`이 가리키는 대상이 immutable snapshot object 또는 provider durable file id일 때만 허용한다. 그렇지 않으면 `latest resend only` 또는 정책상 금지로 내린다.

### 5.10 저장 제약, 인덱스, 감사 필드

#### `ChannelDeliveryLog`

유니크 제약:
- `(event_key, target_type, target_id)` 유니크 제약을 둔다.
- 자동 재시도는 동일 row UPDATE이므로 유니크 충돌이 발생하지 않는다.
- 운영자 resend는 새 `event_key`(원본 key + `_resend_{timestamp}`)로 INSERT하므로 유니크를 우회한다.

인덱스:
- `(source_type, source_id, status)` 복합 인덱스 — "특정 주문의 pending/failed delivery 조회"
- `(status, next_retry_at)` partial index `WHERE status IN ('pending', 'api_failed', 'token_issue_failed', 'token_rate_limited')` — "재시도 대상 조회"
- `(order_id, created_at)` — 주문별 delivery 이력 조회
- `event_key` — 유니크 제약이 인덱스 겸용
- `created_at` — 시간 범위 조회

페이로드 마스킹:
- `masked_request_payload`와 `masked_response_payload`에는 presigned URL 원문과 민감정보를 그대로 저장하지 않는다.
- 마스킹은 `services/channel_delivery.py`의 `mask_payload()` 헬퍼에서 수행한다.
- presigned URL은 `{"url": "[MASKED]", "key": "r2:orders/{id}/photo.jpg", "expires_at": "..."}` 형태로 storage key와 만료 시각만 남긴다.
- `rendered_text_snapshot`, `file_snapshot`, `target_group_snapshot`은 resend 기준 스냅샷이므로 row 생성 후 수정하지 않는다.
- `file_snapshot`이 참조하는 첨부는 원본 주문 파일 경로가 아니라 immutable snapshot object key 또는 provider durable file id여야 한다.

#### `ChannelManagerLink`

유니크 제약:
- **Partial unique index**: `CREATE UNIQUE INDEX ... ON channel_manager_links(channel_manager_id) WHERE is_active = true`
- SQLAlchemy UniqueConstraint는 조건부 필터를 지원하지 않으므로, Alembic migration에서 `op.create_index(..., postgresql_where=text("is_active = true"), unique=True)` DDL로 직접 작성한다.
- 한 manager가 여러 FOMS user에 중복 활성 매핑되지 않게 한다.
- 비활성화 후 재활성화 시 새 row INSERT가 가능하다.

인덱스:
- `(user_id, is_active)` — FOMS user별 활성 매핑 조회
- `channel_manager_email` — 참조용 조회 (유니크 아님)

#### `ChannelInboundEventLog`

유니크 제약:
- `dedupe_key` UNIQUE — inbound 중복 방지의 단일 기준
- `creation_key` UNIQUE — create-enabled inbound의 durable idempotency 기준. `NULL`은 허용하되, `NULL` row는 생성 모드로 승격하지 않는다.
- `provider_event_id`는 nullable + 일반 인덱스만 둔다. provider가 안정적으로 주지 않는 경우를 허용한다.

인덱스:
- `(status, received_at)` — 상태별 시간 범위 조회
- `source_chat_id` — 채팅별 이벤트 조회
- `payload_hash` — 중복 payload 감지 보조

### 5.11 런타임 정책 source of truth 계약
- `event-matrix.md`, `group-routing-table.md`, `routing-policy-table.md`, `message-template-catalog.md`는 사람 검토용 문서다.
- 런타임에서 실제로 읽는 canonical policy는 `services/channel_policy.py` 또는 동등한 machine-readable 설정 파일이다.
- Phase B 완료 기준은 "문서 승인"만이 아니라 "runtime policy 파일 반영 + 문서와 동기화"까지 포함한다.
- `routing-policy-table.md`는 기존 `event-matrix.md`를 대체하는 것이 아니라, `personal | notice | both`와 canonical target rule을 덧입힌 확장 표로 관리한다.
- DispatchService는 markdown 문서를 직접 읽지 않고 runtime policy 계층만 참조한다.
- `services/channel_policy.py`는 최소 아래 인터페이스를 명시적으로 제공한다.
  - `get_policy_version()`
  - `resolve_push_policy(event_type, order_snapshot, wave)`
  - `resolve_resend_policy(event_type, actor_role)`
  - `resolve_inbound_policy(group_id, template_key, create_enabled)`
- Phase B와 Phase A를 병렬로 움직일 때도 위 함수 시그니처와 반환 키 스키마는 kickoff에서 먼저 얼린다.

#### 감사 필드 선별 적용 (모델별)

| 감사 필드 | DeliveryLog | ManagerLink | InboundEventLog | 사유 |
|-----------|:-----------:|:-----------:|:---------------:|------|
| `correlation_id` | O | - | O | 요청 추적 |
| `actor_type` | O | - | - | 트리거 주체 식별 |
| `actor_id` | O | - | - | 트리거 주체 식별 |
| `order_id` | O | - | O | 주문 연결 |
| `wave` | O | - | O | pilot wave 추적 |
| `request_id` | O | - | - | HTTP 요청 추적 |
| `source_manager_id` | - | - | O | 발신 manager |
| `linked_at` | - | O | - | 매핑 생성 시각 |
| `deactivated_at` | - | O | - | 비활성화 시각 |
| `deactivated_by_user_id` | - | O | - | 비활성화 처리자 |

### 5.12 토글과 source of truth 계약
- feature flag는 최소 아래 단위로 나눈다.
  - `CHANNEL_PUSH_ENABLED`
  - `CHANNEL_PERSONAL_PUSH_ENABLED`
  - `CHANNEL_NOTICE_PUSH_ENABLED`
  - `CHANNEL_COMMAND_ENABLED`
  - `CHANNEL_WAM_ENABLED`
  - `CHANNEL_WEBHOOK_ENABLED`
  - `CHANNEL_INBOUND_CREATE_ENABLED`
  - `CHANNEL_WRITE_ACTION_ENABLED`
  - `CHANNEL_MAPPING_REQUIRED`
  - `CHANNEL_PERSONAL_FALLBACK_TO_NOTICE_ALLOWED`
- 운영 토글은 "전체 on/off"만 두지 않고 `팀별`, `이벤트 유형별`, `wave별` 확장 포인트를 남긴다.
- 2026-03-27 현재 `CHANNEL_*_ENABLED`는 대부분 readiness/운영 계약용이다.
  - route hard-off switch는 후속 단계 목표로 보고, 현재는 health/rollout gate와 함께 해석한다.
- FOMS 채팅은 유지하지만 이번 범위의 source of truth는 여전히 `FOMS 주문/일정/권한 데이터`다.
- ChannelTalk message, command, webhook payload는 원본 데이터를 대체하지 않으며, 항상 FOMS 도메인 조회 후 최종 판단한다.
- Google Sheet 연계가 남아 있는 동안 inbound 생성의 단일 source를 문서로 고정하고 이중 생성 경로를 허용하지 않는다.

Feature Flag 의존 행렬:
- 서버 시작 시 아래 선행 조건을 검증하고, 위반 시 경고 로그 + health 응답에 `flag_violation` 표시:

| Flag | 선행 조건 | 위반 시 동작 |
|------|-----------|-------------|
| `CHANNEL_INBOUND_CREATE_ENABLED` | `CHANNEL_WEBHOOK_ENABLED=true` 필수 | 수신기 없이 생성 로직만 켜짐 방지 |
| `CHANNEL_WRITE_ACTION_ENABLED` | `CHANNEL_COMMAND_ENABLED=true` 또는 `CHANNEL_WAM_ENABLED=true` 필수 | 쓰기 액션 표면 없이 활성화 방지 |
| `CHANNEL_WAM_ENABLED` | `CHANNEL_COMMAND_ENABLED`와 독립 | 독립 동작 가능 |
| `CHANNEL_COMMAND_ENABLED` | `CHANNEL_PUSH_ENABLED`와 독립 | command 응답은 push가 아닌 조회 |
| `CHANNEL_PERSONAL_PUSH_ENABLED` | `CHANNEL_PUSH_ENABLED=true`, `CHANNEL_MAPPING_REQUIRED=true` 권장 | personal만 안전하게 끄고 notice는 유지 가능 |
| `CHANNEL_NOTICE_PUSH_ENABLED` | `CHANNEL_PUSH_ENABLED=true` | notice만 유지/중단 가능 |
| `CHANNEL_PERSONAL_FALLBACK_TO_NOTICE_ALLOWED` | 기본 `false` | personal-only 이벤트의 자동 group 승격은 기본 금지 |

- `CHANNEL_PUSH_ENABLED=false`인 상태에서 command 응답으로 주문 정보를 반환하는 것은 push 우회가 아니라 조회로 분류한다. 단, command 응답에 알림성 메시지를 포함하면 push 정책 우회가 되므로 금지한다.

### 5.13 보안/개인정보/보존 계약
- presigned URL은 응답 본문 전송에만 사용하고 DB 로그에는 마스킹된 형태로만 남긴다.
- 첨부/본문 로그는 운영 분석에 필요한 최소 필드만 보존하고, 전문(raw body) 저장은 Phase E webhook 원본 로그처럼 꼭 필요한 지점으로 제한한다.
- `ChannelManagerLink`는 이메일만으로 권한을 신뢰하지 않고 `channel_manager_id`를 1차 식별자로 사용한다.
- 퇴사/권한변경/이메일변경 시 manager-user 매핑을 비활성화하는 운영 절차가 필요하다.
- webhook/function 서명 오류, replay 차단, 권한 거부는 보안성 이벤트로 분류해 일반 push 실패와 분리 집계한다.

### 5.14 운영 상태 코드 계약
- delivery 상태는 최소 아래를 구분한다.
  - `pending`: delivery row 생성 완료, 아직 queue/API 미진입
  - `queue_unavailable`: `REDIS_URL` 미설정 또는 queue 기능 비활성
- `queue_enqueue_failed`: Redis reachable 이지만 enqueue 호출 실패
- `worker_processing`: worker가 실제 처리 시작
- `ignored_duplicate`: 같은 `event_key` 중복 시도
- `ignored_stale`: 최신 버전보다 오래된 이벤트라 전송 생략
- `token_issue_failed`: `issueToken` 또는 동등한 토큰 발급 단계 실패 (secret 오설정, 인증 오류)
- `token_rate_limited`: ChannelTalk 토큰 발급 rate limit 초과 (429 응답). `token_issue_failed`와 분리하여 rate limit 문제를 별도 추적한다.
- `api_failed`: 네트워크 예외(Timeout, ConnectionError) 또는 5xx 서버 오류 — 재시도 가능
- `api_rejected`: ChannelTalk가 명시적으로 거부한 요청 (4xx) — 재시도 불가
- `sent`: 최종 전송 성공
- inbound 상태는 최소 아래를 구분한다.
  - `received`
  - `queue_enqueue_failed`
  - `worker_processing`
  - `rejected_signature`
  - `rejected_replay`
  - `rejected_group`
  - `ignored_duplicate`
  - `parse_failed`
  - `dry_run_completed`
  - `created`
- `queue_unavailable`, `queue_enqueue_failed`, `worker_processing`은 모두 운영 의미가 다르므로 하나의 `queue_failed`로 합치지 않는다.
- `token_issue_failed`는 일반 `api_failed`와 분리해 secret 오설정, ChannelTalk 인증 문제를 추적 가능하게 만든다.
- `token_rate_limited`는 `token_issue_failed`와 추가 분리해 rate limit 문제를 별도 대응할 수 있게 한다. `_issue_token()`에서 HTTP 429 응답 시 별도 에러 타입(`ChannelRateLimitError`)으로 구분한다.
- `api_failed`(재시도 가능)와 `api_rejected`(재시도 불가)는 HTTP 상태 코드 기준으로 분리한다: 5xx/Timeout/ConnectionError → `api_failed`, 4xx → `api_rejected`.
- `partial_sent`는 ChannelTalk가 파일 단위 결과를 공식적으로 제공하는 것이 확인되기 전까지 v1 상태 코드에서 제외한다.

### 5.15 Health/Readiness 계약
- `/api/channel/health` 또는 동등 경로는 최소 아래 필드를 반환한다.
  - ChannelTalk 필수 환경변수 설정 여부
  - `CHANNEL_*` feature flag 상태
  - queue 상태: `disabled`, `unreachable`, `reachable`
  - `rq_worker_count` 또는 동등한 worker registry 결과
  - `last_channel_job_seen_at`
  - 최근 N분 delivery 실패율
  - command desired state / actual state 비교 결과
  - signature 검증 활성 여부
  - `replay_window_seconds` 값
  - inbound create enabled 여부
  - feature flag 의존 행렬 위반 여부 (`flag_violations` 배열)
  - rollback 지표: 일일 push 성공률, duplicate 비율, resend 비율 (자동 감지 가능 항목)
  - `legacy_only_success_after_cutover` 카운트
- 단순 `is_configured()` 통과는 readiness를 의미하지 않는다. signing key, group ids, bootstrap mode, webhook 관련 env까지 별도 검증한다.
- readiness는 "서버가 떴다"가 아니라 "pilot wave를 열어도 된다"의 의미로 정의한다.
- readiness 상태는 `ready`, `degraded`, `fail` 3단계로 고정한다.
  - `ready`: 필수 env 유효, queue reachable, worker 1개 이상, bootstrap drift 없음, signature on
  - `degraded`: 필수 기능은 되지만 경고가 남는 상태(legacy fallback 조회, 최근 실패율 상승, drift audit 경고)
  - `fail`: 필수 env 누락, push/webhook on 상태에서 queue 미가용, worker 0, signature off, bootstrap drift
- `CHANNEL_PUSH_ENABLED=true` 또는 `CHANNEL_WEBHOOK_ENABLED=true`인데 `rq_worker_count < 1`이면 readiness는 무조건 `fail`이다.
- `CHANNEL_PUSH_ENABLED=true` 또는 `CHANNEL_WEBHOOK_ENABLED=true`인데 queue는 reachable이어도 `last_channel_job_seen_at`가 임계치(기본 10분)보다 오래되고 backlog가 남아 있으면 readiness는 `fail`이다.
- Wave 시작 전에는 health 응답으로 아래를 모두 만족해야 한다.
  - 필수 env 유효
  - queue reachable
  - command registration drift 없음
  - 최근 오류율이 허용치 이내
  - signature 검증 on

### 5.16 이행 기간 source of truth 계약
- 전환 기준 시점: **CT-A-01 이후 신규 전송 row부터** delivery 상태의 primary source of truth는 `ChannelDeliveryLog`다.
- `structured_data['channeltalk_push']`는 legacy 수동 푸시 이력에 한해서만 fallback 소스로 남긴다.
- CT-A-06 이전 운영 UI는 `ChannelDeliveryLog 우선 -> legacy structured_data fallback`의 read-through adapter를 사용한다.
- CT-A-06 완료 조건에 "운영 UI가 `structured_data` 기반 조회 경로를 제거했다"를 포함한다.
- `structured_data['channeltalk_push']`는 CT-A-06 이후 과도기 UI 힌트로만 남길 수 있지만, 성공/실패 판정의 근거로 더 이상 사용하지 않는다.
- 새 구현은 delivery 성공 여부를 `structured_data`에만 기록하는 경로를 만들지 않는다.
- 운영 화면과 resend 대상 조회는 `ChannelDeliveryLog` 기준으로만 본다.
- legacy 수동 푸시 row에 대해서는 backfill 대신 adapter를 기본 전략으로 두고, snapshot resend가 불가능한 이력은 `latest resend only`로 제한한다.
- CT-A-01 이후 성공 전송인데 `ChannelDeliveryLog` row 없이 `structured_data['channeltalk_push']`만 갱신된 건은 drift로 간주한다.
- health/admin audit에는 `legacy_only_success_after_cutover`를 노출하고, 값이 0이 아니면 rollout gate를 통과시키지 않는다.
- FOMS 채팅과 `/chat`은 이번 범위에서 유지하며, ChannelTalk 연동 추가가 기존 채팅/알림 경로를 깨지 않는다는 회귀 검증을 필수로 둔다.

### 5.17 데이터 보존 정책

| 모델 | 보존 기간 | 정리 방식 | 사유 |
|------|-----------|-----------|------|
| `ChannelDeliveryLog` | 1년 | `sent`/`ignored_*` 상태 row 중 1년 경과 건 batch 삭제 | 운영 관측성, 감사 추적 |
| `ChannelInboundEventLog` | 90일 (raw payload 30일) | `created`/`ignored_*` 상태: 90일 후 삭제, `parse_failed`/`rejected_*`: 90일 보존 (보안 분석), raw payload 필드: 30일 후 null 처리 | PII 보호, 보안 이벤트 추적 |
| `ChannelManagerLink` | 영구 | 비활성화된 row도 감사 목적으로 영구 보존 | 권한 변경 이력 추적 |

- 보존 기간 초과 데이터 정리는 worker cron job으로 자동 수행한다.
- snapshot 첨부용 immutable object/provider durable file id의 storage lifecycle은 최소 `snapshot resend` 운영 SLA 이상으로 묶고, 원칙적으로 `ChannelDeliveryLog` 참조 기간보다 먼저 삭제하지 않는다.
- Phase F에서 실제 데이터 누적량을 확인한 후 보존 기간을 조정할 수 있다.

### 5.18 리팩터링 범위 명시
- `services/channel_client.py`에서 `format_order_message`, `get_target_group_id`, `get_attachment_category_for_status` 3개 함수를 `services/channel_dispatch.py`로 이전한다. 이전 후 channel_client.py는 순수 HTTP 래퍼로만 유지한다.
- `services/jobs/tasks.py`의 `push_order_to_channeltalk`는 단순 확장이 아니라 상당한 재작성이 필요하다. DB 직접 조회 + 메시지 조립 + API 호출을 모두 `channel_dispatch.py` 호출로 교체한다.
- `apps/api/channel_integration.py`의 수동 push 비즈니스 로직(이전 push 이력 확인, `[수정]` prefix, presigned URL 수집, legacy JSON 기록)을 `channel_dispatch.py`로 위임한다.
- 이 리팩터링은 Phase A CT-A-01에서 수행하며, tasks.py와 channel_integration.py가 동시에 dispatch를 거치도록 변경한다.
- `send_group_message()`의 `except Exception` 패턴을 `requests.Timeout`/`requests.ConnectionError`(→ `api_failed`) + `requests.HTTPError` 4xx(→ `api_rejected`) + 5xx(→ `api_failed`)로 세분화한다.

### 5.19 Command Bootstrap 실행 범위 계약
- command registration은 `app.py` import 시점 부작용으로 수행하지 않는다.
- command registration은 `web-only` 실행 범위를 가진 명시적 bootstrap runner 또는 deploy hook으로 수행한다.
- `TESTING=true`, CI, worker 프로세스에서는 bootstrap을 절대 실행하지 않는다.
- health는 desired state / actual state drift를 보여주되, import 시점에 외부 등록을 트리거하지 않는다.

### 5.20 Queue Cutover 계약
- 새 worker는 **기존 payload(`order_id`, `event_type`)** 와 **새 payload(`delivery_id`, `source_version`, optional legacy fields`)** 를 모두 처리할 수 있어야 한다.
- 배포 순서는 `backward-compatible worker 먼저 -> old queue drain 확인 -> 새 web enqueue 전환 -> legacy path cleanup`으로 둔다.
- Redis backlog가 남아 있는 동안 구 job이 실패하지 않도록 dual-signature handler를 유지한다.
- "Web/Worker 동시 재시작"은 운영 편의일 뿐 호환성 보장 수단으로 간주하지 않는다.
- legacy payload job에는 `delivery_id`, `source_version`이 없으므로 compatibility worker가 최소 `ChannelDeliveryLog` synthetic row를 만든 뒤 처리한다. 이 synthetic row는 `source_version=NULL`, `compat_mode=legacy_queue` 의미로 취급하고 stale/snapshot 보장의 대상에서 제외한다.
- `CT-A-06` 이전까지는 synthetic legacy row를 허용하되, delivery-log-only 의미는 old queue가 0이 된 뒤에만 강제한다.
- 롤백 계약은 전방향뿐 아니라 역방향도 가진다.
  - 새 format job이 Redis에 들어간 뒤에는 legacy-only worker로 즉시 롤백하지 않는다.
  - 장애 시 먼저 새 enqueue를 feature flag로 끄고, compatibility worker를 유지한 채 old/new payload를 모두 drain한다.
  - queue가 0이 된 뒤에만 worker binary를 legacy-only 버전으로 되돌릴 수 있다.

### 5.21 Webhook Ack/비동기 경계 계약
- webhook은 `receipt log commit`과 `비동기 후속 작업 enqueue 성공`이 모두 끝난 뒤에만 2xx를 반환한다.
- queue가 unavailable이면 2xx로 성공을 가장하지 않는다. v1 기본값은 `503 JSON` 반환으로 고정한다.
- v1 기본값은 `receipt persisted + async enqueued`일 때만 2xx다.
- 무거운 parse/create는 비동기 작업으로 보내되, "수신 사실" 자체는 receipt log로 먼저 남긴다.
- receipt 저장 후 enqueue가 실패한 경우 inbound row를 `queue_enqueue_failed`로 남기고, provider retry 또는 inbound sweeper가 재큐잉을 다시 시도한다.
- duplicate receipt는 **기존 receipt가 이미 enqueue 성공 또는 terminal 상태일 때만** `200 {"status":"duplicate_ignored"}` no-op로 응답한다.
- duplicate receipt인데 기존 row가 `received` 또는 `queue_enqueue_failed`면 duplicate no-op로 끝내지 않고 재enqueue를 다시 시도한다. 재enqueue가 또 실패하면 `503`을 반환한다.
- create-enabled webhook은 `creation_key`가 확보된 payload에서만 열린다. stable identity가 없는 payload는 dry-run/parse-only까지만 허용하고 Draft/Task를 만들지 않는다.

## 6. 단계별 실행 계획

### 6.0 Phase 간 선행관계

```
Phase 0 (스키마/경계/관측성)
    ↓
Phase B (운영 정책 확정) ← 정책이 구현보다 선행
    ↓
Phase A (Push 경로 운영화) ← 정책 기반으로 구현
    ↓
Phase C (App Server 기반)
    ↓
Phase D (Quick Action)
    ↓
Phase E (Inbound 자동화)
    ↓
Phase F (파일럿 운영)
```

- Phase 0은 모든 후속 단계의 선행 토대다.
- **Phase B는 Phase A보다 선행한다.** 이벤트 severity, 그룹 라우팅, 템플릿/첨부 정책이 확정되어야 DispatchService 구현이 가능하다.
- Phase A는 Phase B의 정책을 코드로 구현하는 단계다.
- Phase C는 Command/WAM/Webhook이 올라가는 App Server 기반 단계다.
- Phase D는 조회 중심 quick action 단계다. Phase C의 CT-C-01(X-Signature), CT-C-02(command), CT-C-03(manager mapping)이 선행이다.
- Phase E는 가장 마지막에 여는 선택적 자동화 단계다. Phase C의 CT-C-01(X-Signature)과 Phase A의 CT-A-02(queue 영속화)가 선행이다.
- Phase F는 wave별 운영 전환과 감리 단계다.

### 6.0A 2026-03-27 재정렬된 실행 우선순위
- 기존 `group 중심 push 운영화` 단계를 그대로 확장하지 않고, 아래 순서로 재정렬한다.
1. 개인 알림 capability spike
2. involved person 결정 규칙 고정
3. 개인 알림 + 공통 notice 정책표 확정
4. outbox를 multi-target delivery로 확장
5. 관리자/팀 파일럿
- 이유:
  - 이번 목적은 단순 "채널톡에 메시지가 가는가"가 아니라 "각 개인이 자기 건을 모바일에서 즉시 인지하는가"이기 때문이다.
  - 따라서 group-only 안정화만으로는 목표를 달성하지 못한다.

### 6.1 구현 티켓 묶음

아래 티켓은 "바로 작업에 넣을 수 있는 최소 구현 단위" 기준이다. 한 티켓 안에 schema, API, UI, 운영 규칙을 섞어 넣지 않는다.

#### Phase 0 티켓

| 티켓 | 선행 | 작업 | 주요 파일 | 완료 조건 |
|------|------|------|-----------|-----------|
| `CT-00-01` | - | `ChannelDeliveryLog`, `ChannelManagerLink`, `ChannelInboundEventLog`와 `Order.channel_source_seq` 모델/migration 추가 (`creation_key`, immutable ref, partial unique index 포함). `channel_source_seq`는 expand/backfill/contract 순서로 live migration 한다. | `models.py`, `migrations/versions/*` | migration 적용 후 새 모델과 `channel_source_seq`가 조회 가능하고, populated `orders` 테이블에도 무중단 적용 경로가 문서화된다. |
| `CT-00-02` | - | ChannelTalk 관련 blueprint 등록 지점과 URL ownership 고정 | `app.py`, `apps/api/channel_functions.py`, `apps/api/channel_webhooks.py`, `apps/api/channel_wam.py` | manual/admin 경로와 provider callback 경로가 분리된다. |
| `CT-00-03` | CT-00-01 | 운영 조회용 최소 observability spec과 admin 조회 API + 최소 health endpoint 정의. `legacy_only_success_after_cutover`, outbox backlog, queue drain 상태를 포함한다. | `apps/api/channel_integration.py`, `services/channel_delivery.py` | 실패 건, backlog 조회 가능. health에서 env/queue/worker registry/source-of-truth drift 상태 확인 가능. |
| `CT-00-04` | CT-00-01 | `channel_source_seq` 증가 규칙을 채널 영향 쓰기 경로 전체에 적용하고, 어떤 write path가 실제 ChannelTalk 영향 경로인지 명시 목록을 확정한다. `erp_orders_structured.py`의 추가 write path(결제 확인, draft 생성 등)도 포함 여부를 결정한다. | `apps/api/erp_orders_structured.py`, `apps/api/erp_measurement.py`, `apps/api/erp_shipment_settings.py`, 관련 저장 경로 | stale 판정 기준값이 wall-clock이 아니라 단조 증가 정수로 통일되고, 누락된 write path가 없다. |
| `CT-00-05` | CT-00-02 | bootstrap 실행 범위, transaction outbox/post-commit enqueue, queue cutover rollback, session ownership 계약을 코드/문서에 고정 | `app.py`, `services/jobs/*`, 운영 문서 | web-only bootstrap, post-commit enqueue, dual-signature queue cutover, 역방향 rollback 규칙, Session 주입 계약이 명시된다. |
| `CT-00-06` | CT-00-02 | ChannelTalk function/webhook/WAM launch payload 샘플 확보 및 fixture 저장. stable provider identity 유무에 따라 `dedupe_key`/`creation_key` 생성 규칙을 고정한다. | `tests/fixtures/` 또는 동등 경로, 운영 문서 | event id 유무, stable message key 유무, launch context, webhook 필드가 실제 payload 기준으로 검증되고 create-enabled 허용 조건이 확정된다. |
| `CT-00-ENV` | - | Railway deploy/staging 환경에 ChannelTalk 필수 환경변수와 bootstrap/readiness용 변수 설정 및 서비스별 필요 변수 분류. `FOMS_BASE_URL`은 환경별 명시값만 허용하고 production fallback을 제거한다. | Railway 설정, 운영 문서, `services/channel_client.py` | readiness helper 기준으로 Web/Worker 필수 env가 모두 충족되고 staging/test가 production deep link를 만들지 않는다. |
| `CT-00-CI` | CT-00-01, CT-00-02 | 새 blueprint/모델 추가 후 CI 호환성 확인, app smoke test 확장, Postgres 대상 Alembic up/down smoke 추가. admin fixture 권한 값 대소문자 불일치도 정리한다. | `.github/workflows/ci.yml`, `tests/` | SQLite smoke와 별도로 Postgres migration smoke가 통과하고, ChannelTalk admin/manual 테스트가 auth에 막히지 않는다. |

#### Phase B 티켓 (정책 확정 — Phase A 선행)

| 티켓 | 선행 | 작업 | 주요 파일 | 완료 조건 |
|------|------|------|-----------|-----------|
| `CT-B-01` | CT-00-01 | 이벤트 severity와 그룹 라우팅 표 확정 + runtime policy 초안 작성 | 정책 문서, `services/channel_policy.py` | 팀별 기본 그룹과 긴급/일반 분기가 문서와 runtime 설정에 같이 고정된다. |
| `CT-B-02` | CT-B-01 | 템플릿, 첨부, mention/broadcast 정책 정리 | 정책 문서 `message-template-catalog.md`, `attachment-policy.md`, `services/channel_policy.py` | 본문 길이, 첨부 수, 알림 prefix 규칙이 문서와 runtime 설정에 같이 반영된다. |
| `CT-B-03` | CT-B-01 | 수동 push/resend 승인 규칙과 dedupe window 확정 | 정책 문서, `apps/api/channel_integration.py` | 운영자 재전송 권한과 이벤트별 dedupe window가 문서화된다. |

#### Phase A 티켓 (Push 경로 운영화 — Phase B 정책 기반 구현)

| 티켓 | 선행 | 작업 | 주요 파일 | 완료 조건 |
|------|------|------|-----------|-----------|
| `CT-A-01` | CT-00-01, CT-00-05, CT-B-01, CT-B-02 | `ChannelTalkDispatchService` 추가 및 공통 push 진입점 통합. `channel_client.py`에서 메시지 조립 함수를 이전하고, Session 주입 계약을 적용한다. | `services/channel_dispatch.py`, `services/channel_client.py`, `services/channel_delivery.py` | 수동/자동 push가 같은 dispatch 진입점을 사용하고 서비스가 암묵 commit하지 않는다. |
| `CT-A-02` | CT-A-01, CT-00-04, CT-00-05 | post-commit enqueue 실패, queue 미구성, worker 처리 실패를 delivery 상태로 영속화하고 dual-signature worker + outbox sweeper로 cutover 한다. legacy payload는 synthetic delivery row로 수용한다. `send_group_message()` 예외 세분화 포함. | `services/jobs/queue.py`, `services/jobs/tasks.py`, `services/channel_delivery.py` | `queue_unavailable`, `queue_enqueue_failed`, `api_failed`, `token_rate_limited`, `sent`가 구분 저장되고, 구 payload도 synthetic row를 통해 관측 가능하게 처리된다. |
| `CT-A-03` | CT-A-01, CT-B-03 | 수동 push, resend, health 경로를 운영형으로 정리하고 legacy read-through adapter를 넣는다 | `apps/api/channel_integration.py`, `templates/partials/erp_beta_js.html`, `templates/partials/erp_beta_tab.html` | 운영자가 delivery 상태를 보고 수동 재전송할 수 있고 legacy 수동 이력도 조회된다. |
| `CT-A-04` | CT-A-01, CT-B-03 | dedupe key, retry 정책, presigned URL 재발급 정책 확정 | `services/channel_dispatch.py`, `services/channel_delivery.py`, `services/channel_client.py` | 동일 `event_key` 중복 전송과 만료 링크 재전송이 제어된다. |
| `CT-A-05` | CT-A-01, CT-00-04 | 연속 저장 시 stale 이벤트 차단(source_version 비교)과 resend 의미 분리(snapshot vs latest) | `services/channel_dispatch.py`, `services/channel_delivery.py`, `apps/api/erp_orders_structured.py`, 관련 저장 경로 | 오래된 worker 이벤트가 최신 상태를 덮어쓰지 않고 `ignored_stale`로 종료된다. |
| `CT-A-06` | CT-A-01~05 | `structured_data['channeltalk_push']`에서 delivery log 중심 조회로 전환. 운영 UI의 structured_data 기반 조회 경로 제거와 `legacy_only_success_after_cutover` drift 검출을 함께 넣는다. | `apps/api/channel_integration.py`, `services/channel_delivery.py`, 관련 UI | 운영 화면과 resend 기준이 `ChannelDeliveryLog`로 일원화되고, post-cutover legacy-only 성공 기록이 감지된다. |
| `CT-A-TEST` | CT-A-01~06 | delivery 상태 전이 단위 테스트, dedupe/stale 판정 테스트, presigned URL 마스킹 테스트 | `tests/test_channel_delivery.py` | 모든 상태 전이 경로와 edge case가 자동 검증된다. |

#### Phase C 티켓

| 티켓 | 선행 | 작업 | 주요 파일 | 완료 조건 |
|------|------|------|-----------|-----------|
| `CT-C-01` | CT-00-02, CT-00-ENV | `X-Signature` 및 replay 검증 공용 계층 추가. `CHANNEL_REPLAY_WINDOW_SECONDS` 기본값 300초, 0값 금지. Provider endpoint JSON 응답 매트릭스(`401/403/409/503`, 이미 enqueue/terminal인 duplicate만 `200 no-op`)를 고정한다. | `services/channel_security.py`, `apps/api/channel_functions.py`, `apps/api/channel_webhooks.py` | raw body 기준 검증과 replay 차단이 동작하고 redirect 응답이 제거되며, endpoint별 실패 코드가 일관된다. |
| `CT-C-02` | CT-00-02, CT-00-05 | command registration bootstrap runner와 feature flag 연결. import 시 자동 실행 금지, web-only 실행. | `app.py`, `apps/api/channel_functions.py`, `scripts/channel_command_bootstrap.py` 또는 동등 경로 | 테스트/worker에서 외부 등록 호출 없이 command 상태를 안전하게 맞출 수 있다. |
| `CT-C-03` | CT-00-01 | manager-user 매핑 조회 API/permission 계산 추가 | `services/channel_identity.py` | manager 매핑 없는 사용자를 일관되게 차단 또는 읽기 전용 처리한다. |
| `CT-C-04` | CT-C-01, CT-C-02 | `/api/channel/functions` 라우트와 health/readiness 지표 정리 (`rq_worker_count`, `last_channel_job_seen_at`, backlog, flag violation, replay window 포함). `push/webhook on + worker 0`과 stale consumer 조건은 fail-closed로 고정한다. | `apps/api/channel_functions.py`, `apps/api/channel_integration.py` | callback 요청과 운영 health 점검 경로가 분리되고 pilot gate를 코드로 확인할 수 있다. |
| `CT-C-05` | CT-C-01, CT-C-03, CT-00-06 | WAM launch token 계약과 read-only bootstrap 규칙 고정. launch token은 short-lived single-use로 두고, write action token은 후속 단계에서만 개방. | `apps/api/channel_wam.py`, `services/channel_identity.py` | launch token 없는 WAM은 권한 있는 bootstrap을 받지 못하고, read-only WAM만 열린다. |
| `CT-C-06` | CT-C-02 | 멀티 인스턴스 환경에서 command 등록 중복/경합 방지 | `app.py`, `apps/api/channel_functions.py` | 두 개 이상의 앱 인스턴스가 떠도 command 등록이 중복 생성되거나 흔들리지 않는다. |
| `CT-C-07` | CT-C-03 | manager-user 매핑 lifecycle 규칙 정리 (이메일 변경/비활성화 절차) | `services/channel_identity.py`, 운영 문서 | 퇴사/권한변경/이메일변경 시 매핑 비활성화 절차가 정의된다. |
| `CT-C-TEST` | CT-C-01~07 | X-Signature HMAC 검증 단위 테스트, replay 방지 테스트, launch token 검증 테스트 | `tests/test_channel_security.py` | 보안 경로의 모든 edge case가 자동 검증된다. |

#### Phase D 티켓

| 티켓 | 선행 | 작업 | 주요 파일 | 완료 조건 |
|------|------|------|-----------|-----------|
| `CT-D-01` | CT-C-02, CT-C-03 | `/foms 주문`, `/foms 일정`, `/foms 담당` 응답 스키마 고정 | `apps/api/channel_functions.py`, 관련 서비스 계층 | 조회 성공/없음/권한 없음 응답이 분리된다. command 응답 시간 3초 이내. |
| `CT-D-02` | CT-D-01 | 주문 요약 조회 서비스와 첨부 조회 서비스 분리 | 신규/기존 서비스 파일 | command와 WAM이 같은 조회 서비스를 재사용한다. |
| `CT-D-03` | CT-C-05, CT-D-02 | WAM 셸 및 read-only UI 1차 구축 | `apps/api/channel_wam.py`, `templates/channel_wam*.html` | 파일럿 사용자가 Desk에서 조회 전용 흐름을 수행할 수 있다. WAM 초기 로드 5초 이내. |
| `CT-D-04` | CT-D-03 | write action guardrail과 feature flag 추가 | `services/channel_identity.py`, 관련 API | write action은 숨김 + 서버 차단이 동시에 적용된다. |

#### Phase E 티켓

| 티켓 | 선행 | 작업 | 주요 파일 | 완료 조건 |
|------|------|------|-----------|-----------|
| `CT-E-01` | CT-C-01, CT-00-01, CT-00-06 | `/api/channel/webhooks` 수신기, 허용 그룹 필터, receipt log 추가. `dedupe_key`와 `creation_key` 생성 규칙을 분리한다. | `apps/api/channel_webhooks.py`, `services/channel_security.py` | 허용 그룹 외 메시지가 저장 없이 차단되고, receipt-level dedupe와 create-level idempotency 규칙이 고정된다. |
| `CT-E-02` | CT-E-01 | payload parser와 quick reply 실패 응답 구현 | `apps/api/channel_webhooks.py`, parser 서비스 | 표준 템플릿 기준 parse 성공/실패가 분리 저장된다. |
| `CT-E-03` | CT-E-02, CT-00-01 | Draft/Task 생성 서비스 연결과 dry-run/create-enabled 토글 분리, 생성 backlink/immutable ref 저장. `creation_key` 없는 payload는 create-enabled를 금지한다. | 도메인 서비스 파일, webhook 경로 | pilot 동안 저장 없는 검증과 실제 생성 모드를 나눠 운영할 수 있고 rollback 대상이 durable ref로 역추적된다. |
| `CT-E-04` | CT-E-03, CT-B-01 | Google Sheet 연계 중복 처리 분리와 golden payload fixture 작성 | 관련 연계 코드, 테스트 fixture | inbound 중복 생성과 회귀 검증이 가능해진다. |
| `CT-E-05` | CT-E-01, CT-A-02 | webhook ack 경계와 비동기 처리 계약 고정. duplicate는 이미 enqueue/terminal인 receipt만 `200 no-op`, `queue_enqueue_failed` receipt는 provider retry 또는 inbound sweeper로 재enqueue하고 실패 시 `503`으로 고정한다. | `apps/api/channel_webhooks.py`, queue/worker 계층 | receipt persisted + async enqueued 이후에만 2xx를 반환하고, duplicate/temporary failure 응답이 유실 없이 일관된다. |
| `CT-E-TEST` | CT-E-01~05 | golden payload fixture 기반 parser 단위 테스트, webhook 응답 시간 테스트 | `tests/test_channel_webhooks.py` | 파싱 성공/실패 경로와 dedupe가 자동 검증된다. |

#### Phase F 티켓

| 티켓 | 선행 | 작업 | 주요 파일 | 완료 조건 |
|------|------|------|-----------|-----------|
| `CT-F-01` | Phase A~E 완료 | pilot wave별 feature flag/대상 그룹 설정 정리 | 설정 파일, 운영 문서 | wave 단위 on/off가 가능하다. |
| `CT-F-02` | CT-F-01 | 운영자용 실패 대응 가이드와 1장짜리 사용자 가이드 작성 (역할별 분리) | 운영 문서 | push 실패, parse 실패, resend 절차가 문서화된다. |
| `CT-F-03` | CT-F-01 | 성공률, duplicate, resend, parse 성공률 집계와 회고 루틴 고정 | 운영 문서, admin 조회 API | wave 종료 판단을 수치로 할 수 있다. |
| `CT-F-04` | CT-F-01 | rollback 토글과 중단 기준 실제 점검 | 설정 경로, 운영 문서 | 특정 phase/wave 기능을 즉시 닫을 수 있다. |

### Phase 0. 선행 스키마/경계/관측성 단계
목표:
- 이후 단계가 설계로 되돌아가지 않도록 저장 구조, 엔드포인트 경계, 관측성 최소 장치를 먼저 고정한다.

핵심 작업:
1. `ChannelDeliveryLog`, `ChannelManagerLink`, `ChannelInboundEventLog`, `Order.channel_source_seq` 정의
2. Alembic migration 작성
3. 보존 정책과 payload masking 규칙 결정
4. blueprint ownership 확정
5. bootstrap 실행 범위, queue cutover, session ownership 계약 고정
6. admin 조회 API 또는 최소 ops 조회 경로 정의
7. pilot 지표 계산에 필요한 쿼리/집계 기준 정의
8. ChannelTalk callback/WAM launch payload fixture 확보
9. Postgres 대상 migration smoke 경로 정의

산출물:
- `channel-schema-spec.md`
- migration 1~3건
- `endpoint-ownership.md`
- `ops-observability-spec.md`

완료 기준:
- 이후 Phase A/C/E가 "이미 있는 모델"을 가정하지 않아도 된다.
- 운영자가 실패/중복/queue backlog를 볼 최소 조회 경로가 있다.
- source_version, webhook dedupe, bootstrap 실행 범위가 문서상 모호하지 않다.

### Phase B. 운영 정책 확정 (Phase A 선행)
목표:
- 알림이 실제 운영 규칙에 맞게 흘러가도록 제품 정책을 **구현 전에** 고정한다.
- Phase A의 DispatchService가 이 정책을 기반으로 구현되므로 반드시 선행한다.

입력 문서:
- Phase 0 산출물 (`channel-schema-spec.md`, `endpoint-ownership.md`)

핵심 작업:
1. 긴급/일반/참고 이벤트 수준 정의
2. 팀/그룹 ownership 정의
3. 첨부 전송 기준 정의
4. mention/broadcast 사용 규칙 정의
5. 시간대/빈도 제한 규칙 정의

산출물:
- `event-matrix.md` — Phase A CT-A-01의 입력
- `group-routing-table.md` — Phase A CT-A-01의 입력
- `message-template-catalog.md` — Phase A CT-A-01, Phase E CT-E-02의 입력
- `alert-policy.md`
- `severity-matrix.md`
- `attachment-policy.md`

완료 기준:
- "무엇을 누구에게 언제 얼마나 보낼지"가 구현 전에 문서로 고정된다.

실구현 단계:
1. 이벤트를 `긴급`, `일반`, `참고`, `묶음 가능`으로 분류한다.
2. 팀별 기본 그룹과 예외 그룹을 표로 확정한다.
3. `broadcast` 사용 가능 이벤트를 따로 표기한다.
4. 첨부 상한, 본문 길이, 링크 형식, 제목 prefix 규칙을 문서화한다.
5. dedupe window 기본값을 이벤트별로 정한다.
6. 운영자가 직접 전송할 수 있는 수동 푸시 범위와 승인 규칙을 정한다.
7. markdown 문서와 별도로 `services/channel_policy.py` 같은 runtime policy 파일 초안을 만든다.

테스트/검증:
- 샘플 주문 5건 기준으로 이벤트별 최종 메시지 예시를 리뷰한다. 주문 선정 기준: 실측(2건), 도면(1건), 시공(1건), 긴급(1건).
- 실측/도면/시공 책임자가 각자 자기 그룹 라우팅이 맞는지 승인한다.
- 긴급 알림과 일반 알림이 같은 템플릿/같은 그룹으로 섞이지 않는지 확인한다.
- 리뷰 체크리스트: ① 그룹 라우팅 정확성 ② 템플릿 가독성 ③ 첨부 상한 적절성 ④ dedupe window 합리성 ⑤ broadcast 남용 위험

### Phase A. Push 경로 운영화 (Phase B 정책 기반 구현)
목표:
- Phase B에서 확정된 정책을 바탕으로 현재 push 경로를 운영 가능한 수준으로 만든다.

입력 문서:
- Phase 0 산출물 (스키마, 관측성)
- Phase B 산출물 (`event-matrix.md`, `group-routing-table.md`, `message-template-catalog.md`, runtime policy)

핵심 작업:
1. durable delivery log 설계
2. retry / dedupe / resend 정책 구현
3. 토큰 운영 전략 재설계
4. `structured_data['channeltalk_push']`에서 delivery log 중심으로 넘어가는 전환 규칙 고정
5. presigned URL 재전송 시 재생성 규칙 결정
6. 연속 저장 시 stale 이벤트 차단 기준 결정
7. `channel_client.py` → `channel_dispatch.py` 리팩터링
8. queue payload cutover와 legacy adapter 적용

산출물:
- `delivery-state-model.md`

관련 파일:
- `services/channel_client.py`
- `services/channel_dispatch.py` (신규)
- `services/channel_delivery.py` (신규)
- `services/jobs/queue.py`
- `services/jobs/tasks.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/channel_integration.py`

완료 기준:
- 전송 시도, 성공, 실패, 재시도 상태가 영속적으로 추적된다.
- 운영자가 "왜 안 갔는지"를 로그만 보지 않고 식별할 수 있다.

실구현 단계:
1. `services/channel_delivery.py`에 상태 전이 API를 만든다.
   - `create_pending_delivery`
   - `mark_enqueued`
   - `mark_sent`
   - `mark_api_failed`
   - `mark_api_rejected`
   - `mark_queue_unavailable`
   - `mark_queue_enqueue_failed`
   - `mark_token_issue_failed`
   - `mark_token_rate_limited`
   - `mark_ignored_stale`
   - `mask_payload()` — presigned URL 마스킹 헬퍼
2. `services/channel_client.py`를 "단순 API 래퍼"로 좁히고, `format_order_message`, `get_target_group_id`, `get_attachment_category_for_status`를 `channel_dispatch.py`로 이전한다.
3. `services/channel_dispatch.py`를 만들어 수동 푸시와 worker 푸시가 같은 진입점을 타게 한다. Phase B의 runtime policy를 참조한다.
4. `apps/api/channel_integration.py`의 수동 푸시가 delivery log를 남기도록 바꾼다.
5. `services/jobs/tasks.py`는 worker 시작/성공/실패를 delivery log에 반영한다. dispatch 호출로 교체하되, 구 payload와 신 payload를 모두 받는 compatibility handler를 먼저 둔다.
6. `services/jobs/queue.py`의 `REDIS_URL` 미설정, Redis 연결 실패, enqueue 실패를 다른 상태로 남기게 한다.
7. `apps/api/erp_orders_structured.py`와 ChannelTalk 영향 쓰기 경로는 같은 트랜잭션 안에서 `channel_source_seq += 1` 후 pending delivery row를 만들고, enqueue는 commit 이후 `delivery_id` 기준으로 수행한다.
8. queue 계열 실패에 대한 auto requeue와 수동 resend의 경계를 문서와 코드에 같이 넣는다.
9. worker는 `channel_source_seq` 기반 `source_version` 비교 후 stale 이벤트를 `ignored_stale`로 종료한다.
10. resend API는 `원본 snapshot 재전송`(parent_delivery_id 참조)과 `최신 상태 재전송`을 명시적으로 구분한다.
11. `rendered_text_snapshot`, `file_snapshot`, `target_group_snapshot`이 없는 legacy row는 snapshot resend를 금지한다.
12. 운영 UI는 CT-A-06 전까지 `ChannelDeliveryLog 우선 + structured_data fallback` read-through adapter를 사용한다.
13. `send_group_message()` 예외를 세분화: `Timeout`/`ConnectionError` → `api_failed`, 4xx → `api_rejected`, 5xx → `api_failed`, 429 → `token_rate_limited`.
14. 배포 순서는 `backward-compatible worker 먼저 -> old queue drain 확인 -> 새 web enqueue 전환 -> legacy cleanup`으로 고정한다.

테스트/검증:
- 수동 푸시 1건 성공 시 `pending -> sent` 상태 전이가 기록된다.
- `REDIS_URL` 미설정 시 `queue_unavailable`이 기록되고 silent success가 나오지 않는다.
- Redis 연결 불가 또는 enqueue 예외 시 `queue_enqueue_failed`가 기록된다.
- 같은 `event_key`로 중복 호출 시 dedupe가 동작한다.
- worker 예외 시 `last_error`가 저장되고 운영자가 재시도 대상을 조회할 수 있다.
- presigned URL 만료 후 재전송 시 새 URL로 정상 전송된다.
- 주문 저장 2건이 역순 처리되어도 오래된 이벤트는 `ignored_stale`로 끝난다.
- 운영자가 snapshot resend와 latest resend를 혼동하지 않도록 API/문서가 분리된다.
- `issueToken` 실패는 `token_issue_failed`, rate limit은 `token_rate_limited`로 구분 저장된다.
- `structured_data['channeltalk_push']`와 delivery log가 서로 다른 성공 판정을 내리지 않도록 전환 규칙이 검증된다.
- `masked_request_payload`에 presigned URL이 마스킹된 형태로만 저장되는지 확인한다.
- Redis에 남아 있는 구 payload job이 새 worker에서도 처리되는지 확인한다.

### Phase C. App Server 기반 구축
목표:
- Command, Function Endpoint, WAM의 서버 기반을 만든다.

핵심 작업:
1. command registration bootstrap 추가
2. `X-Signature` 검증 서비스 추가
3. function routing 설계
4. manager-user 매핑 방식 결정
5. app bootstrap과 feature flag 정의
6. manual/admin 경로와 callback 경로 blueprint 분리
7. WAM bootstrap payload 계약 고정
8. 멀티 인스턴스 command registration 경합 방지

산출물:
- `command-registry-spec.md`
- `signature-validation-spec.md`
- `identity-mapping-spec.md`

관련 파일:
- `app.py`
- `apps/api/channel_integration.py`
- `services/channel_security.py`
- `services/channel_identity.py`
- `services/channel_client.py`

완료 기준:
- 앱 재시작 후 command 등록과 endpoint 검증이 일관되게 동작한다.

실구현 단계:
1. `services/channel_security.py`에 raw body 기준 HMAC 검증기를 만든다.
2. replay window와 payload hash 정책을 정하고 공용 helper로 캡슐화한다.
3. `apps/api/channel_functions.py` 또는 동등한 callback blueprint에 `/api/channel/functions` 라우트를 만든다.
4. command 등록은 import 시점이 아니라 명시적 bootstrap runner 또는 deploy hook에서만 수행한다.
5. feature flag로 command 등록을 끄고 켤 수 있게 만든다.
6. `ChannelManagerLink` 모델 또는 동등 구조를 만들고, manager-user binding 조회 API를 구현한다.
7. `health` endpoint에서 환경변수, feature flag, command 등록 상태, queue 연결 상태, `rq_worker_count`, `last_channel_job_seen_at`, signature 검증 상태를 보여준다.
8. `/channel/wam`은 launch token 검증 전에는 권한 있는 bootstrap을 만들지 않는다.
9. command 등록은 원하는 상태(desired state) 비교 후 upsert 형태로 처리하고, 앱 인스턴스 수와 무관하게 idempotent 하게 만든다.
10. manager-user 매핑은 `channel_manager_id` 기준으로 조회하고, 이메일 변경/비활성화 lifecycle 절차를 같이 문서화한다.
11. readiness 판단 기준을 문서와 endpoint 응답 필드에 같이 고정한다.
12. provider-facing endpoint는 `login_required`/`role_required`를 쓰지 않고 JSON 응답 매트릭스(`401/403/409/503`, 이미 enqueue/terminal인 duplicate만 `200 no-op`)만 반환한다.

테스트/검증:
- 잘못된 서명 요청은 401/403으로 차단된다.
- 서명은 맞지만 매핑 없는 manager는 읽기 전용 또는 거부 정책대로 처리된다.
- 서버 재시작 후 command 재등록이 중복 없이 수행된다.
- feature flag off 상태에서 command/webhook이 닫히는지 확인한다.
- launch token 없는 WAM은 권한 있는 bootstrap을 받지 못한다.
- 앱 인스턴스 2개가 같은 시점에 올라와도 command 상태가 중복 생성되거나 불안정해지지 않는다.
- manager 이메일이 바뀌거나 비활성화되어도 기존 권한이 남아 있지 않다.
- health 응답만 보고도 pilot 시작 가능 여부를 판단할 수 있다.
- provider callback 실패 시 redirect HTML이 아니라 JSON 오류가 반환된다.

### Phase D. Quick Action 1차 구축
목표:
- 읽기 중심 quick action을 먼저 올리고, 쓰기 액션은 좁게 시작한다.

1차 범위:
1. `/foms 주문 {번호}`
2. `/foms 일정 {번호}`
3. `/foms 담당 {번호}`
4. WAM 주문 요약
5. WAM 첨부 보기

2차에서 검토:
- 상태 변경
- 담당 변경
- 승인/보류

산출물:
- `wam-information-architecture.md`
- `command-response-contract.md`
- `write-action-guardrails.md`

완료 기준:
- pilot 사용자가 데스크에서 읽기 액션을 빠르게 수행할 수 있다.
- 쓰기 액션은 후속 단계에서만 검토하며, 이번 단계의 WAM은 read-only가 기본이다.

실구현 단계:
1. `/foms 주문`, `/foms 일정`, `/foms 담당`의 응답 스키마를 먼저 고정한다.
2. 읽기 액션에 필요한 order summary service를 별도 서비스 함수로 분리한다.
3. `templates/channel_wam*.html`에 WAM 셸과 기본 레이아웃을 만든다.
4. WAM은 1차에 `조회 전용`으로 시작하고, launch token이 없는 접근에는 read-only shell 또는 거부 응답만 준다.
5. 첨부 보기에서는 원본 다운로드 링크와 썸네일/미리보기 정책을 구분한다.
6. 2차에서만 상태 변경, 승인/보류를 검토하고, 이때 action token + server-side revalidation을 강제한다.

테스트/검증:
- Command 응답이 주문 없음/권한 없음/정상 조회를 구분해 보여준다.
- WAM 로드 후 주문 조회가 느리거나 실패해도 사용자에게 원인 메시지가 나온다.
- 쓰기 액션 flag가 꺼져 있으면 UI와 서버 모두 막혀 있다.
- manager-user 매핑 없음, 팀 불일치, 비활성 사용자, 권한 변경 직후 케이스가 조회 정책대로 일관되게 처리된다.

### Phase E. Inbound 자동화
목표:
- ChannelTalk의 표준 입력을 FOMS Draft/Task로 연결한다.

v1 범위:
- 지정 그룹
- 지정 템플릿
- quick reply 응답
- Draft Order 또는 Task 생성

핵심 작업:
1. webhook endpoint 생성
2. payload validation / replay 방지
3. 템플릿 기반 파서 설계
4. parse 실패 사유 저장
5. 기존 Google Sheet 연계와 충돌 지점 정리
6. golden payload fixture 세트 작성
7. dry-run 모드와 create-enabled 모드 분리
8. webhook 응답 시간과 비동기 처리 경계 정의

산출물:
- `webhook-contract.md`
- `parser-rulebook.md`
- `inbound-failure-playbook.md`

완료 기준:
- pilot 그룹에서 inbound 자동화 성공/실패가 추적 가능하다.
- parse 실패가 조용히 버려지지 않는다.

실구현 단계:
1. `/api/channel/webhooks`를 만들고 허용 그룹 화이트리스트부터 적용한다.
2. `ChannelInboundEventLog`에 `provider_event_id`, `dedupe_key`, `creation_key`, `raw_payload`, `payload_hash`, 처리 상태, immutable 생성 ref를 저장한다.
3. parser는 자유 텍스트 추론보다 "표준 템플릿 우선"으로 설계한다.
4. 필수 필드가 빠지면 Draft 생성 대신 실패 상태 + quick reply를 보낸다.
5. quick reply 문구는 운영자가 바로 이해할 수 있게 고정 문안으로 만든다.
6. Google Sheet 연계가 살아 있다면 중복 처리 또는 순서 충돌을 먼저 분리한다.
7. 입력 계약 승인은 운영 책임자 + 제품 책임자가 같이 하도록 문서화한다.
8. webhook 수신기는 receipt log commit과 async enqueue 성공 이후에만 2xx를 반환한다.
9. provider 재전송이 와도 receipt-level 중복은 `dedupe_key`, create-level 중복은 `creation_key` 기준으로 막는다.
10. Draft/Task 생성 시 `created_order_id`, `created_task_id` backlink와 immutable ref(`created_order_ref`, `created_task_ref`)를 inbound log에 남긴다.

테스트/검증:
- 동일 webhook 재수신 시 중복 생성이 일어나지 않는다.
- 첫 수신에서 receipt 저장 후 enqueue 실패가 났다가 retry가 오면 duplicate no-op로 먹지 않고 재enqueue가 다시 시도된다.
- 필수 필드 누락 메시지는 실패 사유가 로그에 남는다.
- 잘못된 그룹에서 온 메시지는 저장 없이 거부된다.
- 표준 템플릿 10건 기준으로 파싱 성공률을 측정한다.
- golden payload fixture 변경 시 회귀 테스트가 깨지지 않는지 확인한다.
- webhook 처리 중 내부 작업이 느려도 provider retry를 유발하지 않는 응답 시간이 유지된다.
- 서명 실패, replay 차단, 허용 그룹 아님, 중복 webhook, parse 실패가 서로 다른 상태로 집계된다.
- queue unavailable 상태에서 2xx를 잘못 반환하지 않는지 확인한다.

### Phase F. 파일럿 운영과 확장
목표:
- 운영 지표를 보고 범위를 넓힌다.

pilot 순서:
1. Wave 0: 관리자/개발자 전용 그룹
2. Wave 1: 실측 팀 push only
3. Wave 2: 도면/시공 팀 push only
4. Wave 3: 실측 팀 read-only quick action
5. Wave 3.5: 도면/시공 팀 read-only quick action
6. Wave 4: 선택 그룹 inbound 자동화
7. Wave 5: 쓰기 액션 제한 공개

완료 기준:
- 각 wave 종료 시 성공 지표와 rollback 기준을 통과해야 다음 wave로 간다.

실구현 단계:
1. Wave 0에서 관리자와 개발자가 push 로그, resend, health만 본다.
2. Wave 1~2에서는 push only로 운영하며 소음과 실패율을 측정한다.
3. Wave 3에서 read-only quick action을 실측팀에 연다.
4. Wave 3.5에서 도면/시공 팀에 read-only quick action을 확대한다.
5. Wave 4에서 inbound 자동화를 소수 그룹으로만 연다.
6. Wave 5에서 권한 매핑이 끝난 그룹에 한해 쓰기 액션을 연다.
7. 각 wave 종료 시 15분짜리 운영 회고를 열고 확대/보류/축소를 결정한다.

테스트/검증:
- 각 wave마다 성공률, duplicate 비율, resend 비율, 사용자 피드백을 기록한다.
- rollback 토글이 실제로 동작하는지 wave 시작 전에 먼저 확인한다.
- 운영 가이드 없이도 핵심 담당자가 read-only quick action을 수행할 수 있는지 확인한다.

## 7. 운영/제품 강화 항목

### 7.1 Pilot 운영 순서
- 한 번에 전체 공개하지 않는다.
- `push -> read-only quick action -> inbound -> write action` 순서로 넓힌다.
- 팀은 `실측 -> 도면 -> 시공 -> AS` 순으로 확대하는 것이 안전하다.
- 이유는 실측 팀이 일정 이벤트와 모바일 즉시성 요구가 가장 직접적이기 때문이다.

### 7.2 사용자 교육/전환
- 파일럿 시작 전 1장짜리 운영 가이드를 만든다.
- 반드시 포함할 항목:
  - 어떤 메시지가 오는지
  - 어디를 눌러 확인하는지
  - 알림이 잘못 왔을 때 어떻게 신고하는지
  - FOMS에서 계속 해야 하는 일과 ChannelTalk에서 해도 되는 일을 구분
- 역할별 가이드 분리:
  - 관리자
  - 실측
  - 도면/시공
- 전환 기간에는 FOMS 기존 흐름을 유지하고, ChannelTalk는 병행 채널로 올린다.

### 7.3 알림 소음 제어
- 긴급 알림은 `flags.urgent` 또는 명시적 긴급 이벤트만 허용한다.
- 동일 주문의 짧은 시간 내 연속 저장은 묶거나 dedupe 한다.
- 첨부는 기본적으로 상한을 둔다.
- 그룹을 팀 단위로 쪼개고, 전사 그룹 남용을 금지한다.
- 초기에는 broadcast/mention 사용을 최소화한다.

권장 제어 규칙:
1. 동일 주문 동일 이벤트 5분 dedupe
2. 긴급 알림은 별도 템플릿
3. 첨부는 기본 3~5개 제한
4. 대량 변경은 요약 메시지 우선

### 7.4 성공 지표

초기 제안값:
- push 성공률: 재시도 포함 99% 이상
- duplicate push 비율: 1% 미만
- manual resend 비율: 전체 push의 10% 미만
- command 호출 성공률: 95% 이상
- inbound parse 성공률: pilot 기준 95% 이상
- 잘못된 권한으로 쓰기 액션 수행된 건수: 0
- pilot 팀 응답 시간: 기존 대비 개선 또는 최소 유지

### 7.5 Rollback 기준

다음 중 하나라도 만족하면 해당 wave를 중단하고 이전 범위로 되돌린다.

| # | 기준 | 감지 방식 | 자동화 가능성 |
|---|------|-----------|-------------|
| 1 | 일일 push 성공률이 95% 미만 | health API `delivery_success_rate` 필드 | **자동** — health 응답에서 계산 |
| 2 | duplicate push 비율이 2% 초과 | health API `duplicate_rate` 필드 | **자동** — delivery log 집계 |
| 3 | 긴급 알림 오발송이 하루 3건 초과 | 운영자 신고 + 수동 집계 | **수동** — 오발송 판정이 도메인 지식 필요 |
| 4 | inbound parse 실패가 10% 초과 | health API `parse_success_rate` 필드 + 운영 샘플 확인 | **수동 보조** — 현재는 참고 지표, 단독 auto gate로 사용 금지 |
| 5 | 권한 검증 누락 또는 무단 쓰기 액션 1건 이상 | 보안 로그 + audit 집계 | **부분 자동** — audit log 기반 알림 가능 |
| 6 | 운영자가 수동 재전송으로만 버티는 상태가 2일 이상 지속 | 수동 resend 비율 추이 관찰 | **수동** — 운영 판단 필요 |

- 자동 감지 가능 항목은 현재 1, 2 중심으로 본다. 4는 health에 노출하되, metric 정합성 보강 전까지는 운영 샘플 확인을 함께 거친다.
- 수동 판단 항목(3, 6)은 wave 회고 시 운영자가 확인한다.

### 7.6 운영자 실패 처리 절차
- `queue_unavailable`
  - `REDIS_URL` 미설정 또는 queue 기능 off 상태인지 먼저 확인한다.
  - 시스템 설정 문제를 먼저 해결하고 backlog를 일괄 재처리한다.
- `queue_enqueue_failed`
  - Redis 연결과 enqueue 예외를 확인한다.
  - queue 복구 후 auto requeue 가능 여부를 먼저 본다.
- `api_failed`
  - retry 정책 횟수 내 자동 재시도
  - 초과 시 운영자 resend 대상
- `token_issue_failed`
  - secret, channel id, ChannelTalk 인증 오류를 먼저 본다.
  - 일반 전송 실패와 같은 큐에서 처리하지 않고 인증 장애로 분리 대응한다.
- `token_rate_limited`
  - ChannelTalk 토큰 발급 rate limit 초과 상태다.
  - 일정 시간(기본 60초) 대기 후 자동 재시도한다.
  - 멀티 인스턴스 환경에서 동시 토큰 발급이 원인이면 인스턴스 수 또는 토큰 캐시 전략을 재검토한다.
- `api_rejected`
  - ChannelTalk가 4xx로 명시 거부한 요청이다.
  - 재시도해도 같은 결과이므로 자동 재시도하지 않는다.
  - 요청 payload를 확인하고 원인(잘못된 그룹 id, 메시지 형식 오류 등)을 해소한 후 운영자 resend한다.
- `ignored_duplicate`
  - 사용자 액션 불필요
  - 로그만 남긴다.
- `ignored_stale`
  - 최신 이벤트가 이미 별도로 존재하는지 확인한다.
  - 오래된 이벤트를 되살려 재전송하지 않는다.
- `parse_failed`
  - quick reply 실패 안내
  - 운영자가 원문 payload와 실패 사유를 조회 가능해야 한다.
- `rejected_signature` / `rejected_replay` / `rejected_group`
  - 보안 또는 허용 범위 문제로 분류한다.
  - 업무 입력 실패와 섞지 않고 별도 집계한다.
- `bootstrap_drift`
  - command desired state와 actual state 불일치다.
  - health 경고로 표시하고, web-only bootstrap runner를 다시 수행한다.

### 7.7 책임자와 의사결정 포인트

역할 기준으로 분리한다.

1. 제품 책임
- 어떤 이벤트를 보낼지
- 어떤 그룹을 pilot로 쓸지
- 어떤 quick action까지 공개할지 결정

2. 기술 책임
- endpoint/security/retry/outbox 구현
- 장애 대응과 배포 기준 수립

3. 운영 책임
- 그룹별 룰 배포
- 사용자 교육
- pilot 피드백 수집

4. 승인 포인트 (Phase 실행 순서)
- Phase 0 종료 승인: 스키마/관측성/ownership 확정 여부
- Phase B 종료 승인: 이벤트 정책/라우팅 표/템플릿 확정 여부
- Phase A 종료 승인: delivery 추적 가능 여부, source of truth 전환 완료
- Phase C 종료 승인: command/function 보안 검증 여부
- Phase D 종료 승인: read-only quick action 공개 여부
- Phase E 종료 승인: inbound 자동화 pilot 시작 여부
- Phase F 각 wave 종료 승인: 다음 wave 확대 여부

## 8. 검증 기준

- [ ] 현재 수동 푸시 경로와 자동 푸시 경로의 상태가 구분되어 추적된다.
- [ ] `REDIS_URL` 미설정, Redis 연결 불가, enqueue 실패가 서로 다른 상태로 기록된다.
- [ ] queue 등록 실패와 API 전송 실패가 다른 상태로 기록된다.
- [ ] 주문 저장 트랜잭션 안에서는 pending delivery row까지만 만들고, enqueue는 commit 이후에만 호출된다.
- [ ] 토큰 발급 실패가 일반 API 실패와 구분 기록된다.
- [ ] 역순 처리된 오래된 push 이벤트가 최신 상태를 덮어쓰지 않는다.
- [ ] `X-Signature` 검증 실패 요청은 거부된다.
- [ ] replay 공격 방지 로직이 있다.
- [ ] manager-user 매핑 없는 사용자는 쓰기 액션을 수행할 수 없다.
- [ ] manager-user 매핑 없음, 팀 불일치, 비활성 사용자, 권한 변경 직후 조회 정책이 검증된다.
- [ ] 멀티 인스턴스에서도 command registration이 중복/경합 없이 유지된다.
- [ ] health/readiness 응답만으로 pilot 시작 가능 여부를 판단할 수 있다.
- [ ] `CHANNEL_PUSH_ENABLED=true` 또는 `CHANNEL_WEBHOOK_ENABLED=true` 상태에서 `rq_worker_count=0`이면 readiness가 fail-closed 된다.
- [ ] `FOMS_BASE_URL` 누락 시 readiness가 fail로 내려가고 production fallback deep link가 생성되지 않는다.
- [ ] presigned URL과 민감정보가 delivery/audit 로그에 원문으로 남지 않는다.
- [ ] `structured_data['channeltalk_push']`와 `ChannelDeliveryLog`의 source of truth가 혼재되지 않는다.
- [ ] `legacy_only_success_after_cutover`가 0이 아니면 rollout gate가 열리지 않는다.
- [ ] inbound는 `queue_enqueue_failed`, `worker_processing`, `rejected_signature`, `rejected_group`, `ignored_duplicate`, `parse_failed`, `created`를 구분 집계한다.
- [ ] pilot wave별 성공/rollback 판정 기준이 문서화되어 있다.
- [ ] 교육 자료 없이도 pilot 사용자가 주요 흐름을 따라갈 수 있는 최소 가이드가 있다.
- [ ] 이번 단계에서 FOMS 채팅은 기존 상태 그대로 유지된다.
- [ ] ChannelTalk 연동 추가 후에도 `/chat` 접근과 기존 채팅/알림 흐름에 회귀가 없다.
- [ ] `token_rate_limited`와 `token_issue_failed`가 구분 저장되고 운영 절차가 다르다.
- [ ] `api_failed`(재시도 가능)와 `api_rejected`(재시도 불가)가 HTTP 상태 코드 기준으로 분리된다.
- [ ] `snapshot resend`는 immutable snapshot 필드가 있는 row에서만 허용된다.
- [ ] launch token 없는 `/channel/wam` 접근은 권한 있는 bootstrap을 받지 못한다.
- [ ] feature flag 의존 행렬 위반 시 health 응답에 경고가 표시된다.
- [ ] `masked_request_payload`에 presigned URL이 마스킹된 형태로만 저장된다.
- [ ] `ChannelDeliveryLog.source_version`은 wall-clock이 아니라 `orders.channel_source_seq`를 사용한다.
- [ ] webhook dedupe는 `provider_event_id` optional + `dedupe_key` unique + `creation_key` unique 계약으로 일관된다.
- [ ] stable identity 없는 webhook payload는 create-enabled로 승격되지 않는다.
- [ ] provider-facing endpoint는 redirect HTML 대신 JSON 응답 매트릭스(`401/403/409/503`, 이미 enqueue/terminal인 duplicate만 `200 no-op`)를 반환한다.
- [ ] queue cutover 기간에 구 payload와 신 payload가 모두 처리된다.
- [ ] queue cutover rollback 시 compatibility worker를 유지한 채 old/new payload를 모두 drain하는 절차가 있다.
- [ ] command bootstrap은 web-only로 실행되고 TESTING/CI/worker에서는 비활성이다.
- [ ] CI에서 새 모델/blueprint import 및 app 초기화 테스트가 통과하고, Postgres 대상 Alembic smoke가 별도로 통과한다.
- [ ] admin/manual ChannelTalk 테스트 fixture는 실제 auth role 규약과 일치한다.

## 9. 다음 구현 우선순위

1. `ChannelDeliveryLog` + `ChannelInboundEventLog` + `Order.channel_source_seq` 스키마 확정 (Phase 0)
2. bootstrap 실행 범위 / queue cutover / Session 계약 확정 (Phase 0)
3. **이벤트 정책/라우팅 표/템플릿 + runtime policy 확정 (Phase B)** ← 구현보다 정책이 선행
4. **personal routing P0 gate**: transport spike, mapping-readiness, mapping miss 정책, canonical target 규칙, task source-of-truth 범위 결정
5. DispatchService + multi-target delivery + 최소 observability/requeue 운영화
6. `X-Signature` 검증기와 provider JSON 오류 계약 확정 (Phase C)
7. manager-user 매핑 구현 고도화와 WAM launch token 목표 계약 보강 (Phase C)
8. read-only quick action (Phase D)
9. inbound pilot (Phase E)

이 순서가 맞는 이유:
- 스키마와 기반 인프라(Phase 0)가 모든 후속 작업의 전제다.
- bootstrap/cutover/session 계약이 없으면 병렬 구현 중 배포 순간에 바로 깨질 수 있다.
- **정책 확정(Phase B)이 구현(Phase A)보다 선행해야 한다.** 그룹 라우팅, 템플릿, dedupe window가 없으면 DispatchService를 올바르게 구현할 수 없다.
- personal routing은 group-only 안정화의 단순 연장이 아니라 `개인 transport와 매핑`이 먼저 닫혀야 하는 별도 gate가 있다.
- `mapping miss`, `direct send fail`, `fallback used` 같은 개인 알림 관측성은 첫 실발송 전에 최소 수준이 먼저 있어야 한다.
- task 이벤트는 `Order.channel_source_seq` 바깥의 별도 전송축이므로, source-of-truth 계약이 닫히기 전까지 초기 personal rollout 범위에 포함하지 않는다.
- delivery 상태 저장과 보안 검증이 없으면 나머지 기능은 운영 위험만 키운다.
- 읽기 액션이 쓰기 액션보다 먼저다.
- inbound 자동화는 가장 마지막에 pilot로 연다.

## 10. 참고 자료

### 10.1 ChannelTalk 공식 문서
- Authentication: https://developers.channel.io/en/articles/Authentication-e7c2fb6f
- Function: https://developers.channel.io/docs/app-function
- Command: https://developers.channel.io/ko/articles/Command-b3d200dc
- WAM: https://developers.channel.io/docs/app-wam
- Getting Started Tutorial: https://developers.channel.io/en/articles/Getting-Started-Tutorial-516161ed
- Quick-reply for a Webhook: https://developers.channel.io/en/articles/Quick-reply-for-a-Webhook-063baa27
- Send a message to a Group: https://developers.channel.io/docs/send-a-message-to-a-group-1

### 10.2 FOMS 내부 근거 파일
- `app.py`
- `models.py`
- `services/channel_client.py`
- `services/jobs/queue.py`
- `services/jobs/tasks.py`
- `apps/api/channel_integration.py`
- `apps/api/erp_orders_structured.py`
- `templates/partials/erp_beta_js.html`
- `templates/partials/erp_beta_tab.html`
- `docs/evolution/2026-03-16-CHANNELTALK-GOOGLE-SHEET-WEBHOOK-ANALYSIS.md`
