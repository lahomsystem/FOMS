# 결제 아이콘 저장 없이 클릭 가능

**날짜**: 2026-03-18  
**트리거**: 사용자 요청 (저장을 안 해도 클릭 및 동작 가능하게)  
**GDM 감리**: code-reviewer 통과

## 목표
ERP Beta 탭(신규 주문)에서 예약금/잔금 아이콘을 저장 버튼을 누르지 않아도 클릭·동작 가능하게 함.

## 변경 사항

### 수정 파일
- `templates/partials/erp_beta_js.html`

### 로직 변경
- **기존**: `targetId <= 0`이면 `alert('주문을 먼저 저장해야 합니다.')` 후 return
- **변경**: draft 모드(`__ERP_BETA_DRAFT_MODE`)에서 `targetId <= 0`이면 `erpRequireOrderIdOrWarn('결제:')`로 draft 자동 생성 후 진행
- `erpSaveStructured`(L777-781)와 동일 패턴 적용

### 동작
1. 신규 주문(add_order)에서 결제 아이콘 클릭
2. ORDER_ID가 0이면 `erpEnsureDraftOrderId()` 호출 → draft 주문 생성
3. 생성된 order_id로 `POST /api/orders/{id}/payment-confirm` 호출
4. 결제 확인 상태 토글 완료

### edit_order 영향
- `__ERP_BETA_DRAFT_MODE === false`이므로 `erpEnsureDraftOrderId()` 미호출
- 기존 edit_order 동작 유지

## 감리 결과 (code-reviewer)
- erpEnsureDraftOrderId() 동기 갱신: ✅
- payment-confirm 빈 structured_data: ✅ API가 payment 없으면 {} 초기화
- draft 자동 생성 부작용: ⚠️ placeholder draft 생성 가능, erpRequireOrderIdOrWarn이 실패 시 erpSetStatus로 안내
- edit_order 엣지 케이스: ✅ draft 모드에만 적용
