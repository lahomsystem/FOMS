# Spec: ERP Beta AS접수 단계에서 일반 저장 허용

**날짜**: 2026-03-24  
**배경**: `erpSaveStructured`가 `workflow.stage === 'AS_RECEIVED'`이면 항상 PUT을 중단해, 이미 AS접수인 주문의 주소·기타 필드 저장이 불가했음.

## 목표

1. **서버에 이미 AS접수로 저장된 주문**(`__erpLastStructuredData.workflow.stage === 'AS_RECEIVED'`)은 **저장 버튼으로 `/structured` PUT 허용**.
2. **다른 단계에서 AS접수로 방금 변경한 경우**만 기존처럼 AS 접수 모달을 띄우고, 등록 API 완료 전까지 일반 PUT으로 스테이지를 확정하지 않음.

## 구현 체크리스트 (소스 1:1)

| # | 요구 | 위치 | 검증 |
|---|------|------|------|
| 1 | `nextStage` = collect된 `workflow.stage` trim | `erpSaveStructured` | 코드 존재 |
| 2 | `prevStage` = `window.__erpLastStructuredData?.workflow?.stage` trim | 동일 | 로드 시 610행 부여 |
| 3 | `transitioningIntoAsReceived` = `next === 'AS_RECEIVED' && prev !== 'AS_RECEIVED'` | 동일 | |
| 4 | 위가 true일 때만 모달 + early return | 동일 | |
| 5 | 모달 롤백용 `__erpAsReceivePreviousStage` = `prevStage` | 동일 | hidden.bs.modal 기존 로직 유지 |
| 6 | 전환 시 모달은 `doRedirect`와 무관하게 표시 | `erpSaveStructured` | 채널톡 `redirect:false` 대응 |
| 7 | 기존 주문(`!draft`·`targetId>0`)은 `erpStructuredLoadSucceeded`가 true일 때만 전환 모달 | `erpLoadStructured` 성공 시 true | 로드 실패 시 오탐 방지 |
| 8 | 신규 초안(`__ERP_BETA_DRAFT_MODE`)은 스냅샷 게이트 생략 | `erpSaveStructured` | 초안 AS접수 플로우 유지 |

## 비범위

- structured PUT 응답 후 `redirect:false`일 때 `__erpLastStructuredData` 갱신(별도 개선).
- `update_order_field` address allowlist(별도 이슈).
