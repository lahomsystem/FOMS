# Write Action Guardrails (CT-D-04)

## 1. 개요
ChannelTalk 환경 내에서 FOMS 데이터의 상태를 변경(Write Action)하는 기능을 도입할 때 적용되는 안전 장치 및 제약 사항.
(현재 1차 구축 Phase D에서는 모든 쓰기 액션이 비활성화됨)

## 2. 보안 가드레일 (Guardrails)

### 2.1 Feature Flag 연동
- `CHANNEL_WRITE_ACTION_ENABLED=false` 일 경우 모든 UI와 API 레벨에서 쓰기 기능이 차단된다.
- 서버단에서 해당 플래그가 false인 경우 API 호출 시 503(Service Unavailable) 또는 403(Forbidden)을 즉시 반환한다.

### 2.2 Action Token 검증 (v2 도입 예정)
- 모든 상태 변경(예: 승인, 보류, 담당자 변경 등) 요청은 단기적으로 발급된 Action Token을 요구한다.
- Action Token은 5~10분 내로 만료되며, 한 번 사용되면 무효화되는 방식(Single-use)을 검토한다.

### 2.3 권한 교차 검증
- ChannelTalk Manager ID에 매핑된 FOMS User 객체를 조회하여, 해당 User가 ERP 시스템 상에서 변경 권한(`role_required`, 부서 일치 여부 등)을 갖고 있는지 검사한다.
- 권한 매핑이 없거나 불일치할 경우 무조건 "읽기 전용" 모드로 강제 강등된다.
