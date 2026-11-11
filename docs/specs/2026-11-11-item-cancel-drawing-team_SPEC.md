판정: 승인 · 구현 (사용자 11-11 "도면팀 전원 · 운영까지")

# 확정 뒤 제품 취소를 도면팀도 할 수 있게 (2026-11-11)

## 왜

- 운영 주문 5608(이순미)은 생산 단계다. 11-11 영업이 도면 4장(이순미1~4.png)을 확정했다.
- 2번 도면(주방수납장)을 생산 도면에서 빼야 한다. 도면은 직접 올린 파일이라 마법사 시트와 묶여 있지 않다.
- 이미 있는 [확정 뒤 제품 취소](2026-10-12-drawing-confirm-partial-cancel_SPEC.md §10)가 바로 이 일을 한다. 제품에 취소 표시를 붙이고, 고른 도면을 `drawing_excluded_files` 로 옮기고, 생산 단계면 CS·영업·생산에 알림을 보낸다.
- 그런데 지금은 정책 `ERP_EDIT`(CS·SALES·관리자)만 쓸 수 있다. 도면팀은 도면 작업실에서 버튼이 안 보이고, 서버도 403 을 준다.
- 사용자 결정(11-11): "확정 뒤 제품 취소를 도면팀도 가능하게".

## 바꾸는 것

1. 새 정책 `ITEM_CANCEL` 을 `foms/services/orders/order_mutation_policy.py` 에 더한다.
   - 팀: CS · SALES · DRAWING. 팀 전체(배정 확인 없음) — CS·SALES 가 지금 팀 전체인 것과 같다.
   - 관리자는 지금처럼 통과, VIEWER·다른 팀·협력사는 막힌다(엔진 기본).
2. `foms/api/drawing/erp_orders_item_cancel.py` 의 `ITEM_CANCEL_POLICY_ID` 를 `ERP_EDIT` → `ITEM_CANCEL` 로 바꾼다. 앞 검사와 `execute_order_mutation` 이 같은 정책을 쓴다.
3. `foms/web/drawing/workbench.py` 의 `can_cancel_items` 를 같은 `ITEM_CANCEL` 정책으로 판정한다(화면 == 서버).
4. 매니페스트 `docs/harness/foms_order_mutation_policy_manifest.json` 의 이 엔드포인트 `policy_id` 를 `ITEM_CANCEL` 로 고친다.

## 바꾸지 않는 것

- 취소 규칙(확정 뒤에만 · 남은 제품 2개 이상 · 사유 필수 · If-Match · 멱등 키)은 그대로다.
- 알림(생산 단계면 CS·영업·생산 팀 row + 폰 push)도 그대로다. 누가 눌렀는지는 이미 알림에 이름이 들어간다.
- 금액은 지금처럼 고치지 않는다. "견적 수정 필요" 표시가 영업에게 남는다.
- 프리랜서 영업 범위 목록(`freelancer_order_rights.py`)은 그대로다.
- 주문 5608 데이터는 건드리지 않는다. 배포 뒤 도면팀(또는 지금도 관리자)이 화면에서 직접 취소한다.

## 시험 (완료 기준)

- `tests/domains/test_drawing_confirm_partial.py` 에 더한다.
  - 도면팀 STAFF 가 확정 뒤 취소 API 를 부르면 200, 제품에 취소 표시·도면 제외가 된다.
  - 도면팀 STAFF 에게 도면 작업실 [이 제품 취소] 버튼이 보인다.
  - 생산팀(또는 시공팀) STAFF 는 여전히 403.
- 검증 명령: `python -m pytest tests/domains/test_drawing_confirm_partial.py tests/domains/test_erp_permissions.py tests/domains/test_auth_enforcement.py -q`, 그 다음 push 직전 `scripts/ops/pre_push_smoke.ps1`.
- 스테이징: 도면팀 계정으로 확정 주문 하나에서 제품 취소 실호출.
