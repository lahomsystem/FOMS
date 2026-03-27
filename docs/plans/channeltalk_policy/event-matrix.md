# Event Severity & Routing Matrix (CT-B-01)

## 1. Severity Levels

| Severity | 설명 | 예시 이벤트 | Dedupe Window | Broadcast |
| --- | --- | --- | --- | --- |
| `URGENT` | 즉시 확인이 필요한 건 | `urgent`, `as_urgent` | 0초 | 허용 (`@all`) |
| `NORMAL` | 담당자 대응이 필요한 일반 변경 | `stage_changed`, `manager_changed`, `owner_team_changed`, `schedule_changed`, `shipment_updated`, `payment_confirmation_changed`, `manual` | 60초 | 기본 미사용 |
| `INFO` | 참고성 변경 | `order_updated` | 300초 | 미사용 |

## 2. Event Matrix & Routing

| Event Key | Trigger 시점 | Severity | Target Group | Fallback Group | 비고 |
| --- | --- | --- | --- | --- | --- |
| `stage_changed` | workflow.stage 변경 | `NORMAL` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | 현재 runtime 구현 |
| `manager_changed` | 실측 담당 변경 | `NORMAL` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | 현재 runtime 구현 |
| `owner_team_changed` | owner team 변경 | `NORMAL` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | structured 저장 경로 |
| `schedule_changed` | 실측일/시공일 변경 | `NORMAL` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | structured 저장 경로 |
| `shipment_updated` | 출고/시공 설정 변경 | `NORMAL` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | 현재 runtime 구현 |
| `payment_confirmation_changed` | 계약금/잔금 확인 변경 | `NORMAL` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | 현재 runtime 구현 |
| `order_updated` | 주소/연락처 등 일반 정보 변경 | `INFO` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | 현재 runtime 구현 |
| `urgent` | 긴급 플래그 on 또는 긴급 사유 알림 | `URGENT` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | 필요 시 `@all` |
| `manual` | ERP Beta 수동 푸시 | `NORMAL` | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | 운영자 입력 본문 사용 |

## 3. 2026-03-27 구현 메모
- 현재 runtime은 `template_key` + `masked_request_payload`를 기준으로 이벤트를 렌더링한다.
- `event_key`는 dedupe/stale 판정용 식별자이며, 메시지 의미를 복원하는 1차 source는 아니다.
- 라우팅은 아직 단일 기본 그룹(`CHANNEL_GROUP_MEASUREMENT`) 중심이며, event-specific 분기는 추후 확장 범위다.
