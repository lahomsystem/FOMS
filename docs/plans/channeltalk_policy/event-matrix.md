# Event Severity & Routing Matrix (CT-B-01)

## 1. Severity Levels (긴급도 분류)
이벤트는 시스템 부하와 수신자의 피로도를 관리하기 위해 3단계로 분류한다.

| 레벨 (Severity) | 의미 | 예시 이벤트 | Dedupe Window | Broadcast 여부 |
| --- | --- | --- | --- | --- |
| **URGENT** (긴급) | 즉각적인 조치가 필요하거나 치명적인 일정 변경 | 긴급 AS 접수, 당일 실측 취소, 결제/계약 오류 | 0초 (즉시 발송) | 허용 (`@all`) |
| **NORMAL** (일반) | 업무 진행을 위한 상태 변경 알림 | 실측 완료, 도면 확정, 시공 배정, 수동 푸시 | 60초 | 기본 미허용 (특정 담당자 멘션만) |
| **INFO** (참고) | 참고용 정보, 당장 조치가 필요 없는 변경 | 고객 정보 수정, 배송 예정일 단순 변경 | 300초 | 미허용 (조용히 전달) |

## 2. Event Matrix & Routing (이벤트별 그룹 매핑)
ChannelTalk 그룹(채널) 라우팅 정책 정의.

| Event Key | Trigger 시점 | Severity | Target Group | Fallback Group | 비고 |
| --- | --- | --- | --- | --- | --- |
| `order.measurement_completed` | 실측 완료/보고서 업로드 시 | NORMAL | `MEASUREMENT_GROUP` | `GENERAL_GROUP` | |
| `order.drawing_approved` | 고객 도면 확정 시 | NORMAL | `DRAWING_GROUP` | `GENERAL_GROUP` | |
| `order.construction_assigned` | 시공 담당자 배정 시 | NORMAL | `CONSTRUCTION_GROUP` | `GENERAL_GROUP` | |
| `order.as_urgent_received` | 긴급 AS 접수 시 | URGENT | `AS_GROUP` | `GENERAL_GROUP` | 전체 멘션 발송 |
| `order.manual_push` | ERP Beta에서 수동 푸시 버튼 클릭 | NORMAL | `MEASUREMENT_GROUP` (임시) | `GENERAL_GROUP` | 사용자가 지정한 그룹으로 라우팅 확장 예정 |
| `order.info_updated` | 주소/연락처 등 기본 정보 변경 시 | INFO | `GENERAL_GROUP` | - | |
