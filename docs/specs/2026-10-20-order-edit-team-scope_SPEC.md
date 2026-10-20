# 주문 금액·담당자·상태 저장을 영업·CS 팀으로 좁히기 — SPEC (2026-10-20)

## 목적
역할표(`docs/plans/2026-07-22-foms-full-system-bug-audit-report.md` §2.1 주체 표)는 도면·생산·시공·출고 팀에게 "일반 structured form·금융·main-stage" 쓰기를 금지한다. 그런데 아래 다섯 경로가 `STAFF_MUTATION`(`teams="*"`, `foms/services/orders/order_mutation_policy.py` POLICY_REGISTRY) 으로 묶여 있어 모든 STAFF 팀이 아무 주문의 구조화 폼(금액 재계산 포함)·담당자·상태를 저장할 수 있다. 표와 코드를 맞춘다.

## 지금 구조
- 정책 가드: `enforce_order_mutation_policy` 가 쓰기 요청 endpoint 를 `docs/harness/foms_order_mutation_policy_manifest.json` 에서 찾아 `evaluate_policy` 를 돈다. 순서는 VIEWER 거부 → ADMIN·MANAGER 통과 → STAFF 팀 검사.
- `ERP_EDIT` 정책은 이미 `teams=("CS","SALES")` 이고 MEASURE→SALES 정규화·회계팀→CS 권한을 함께 받는다.
- `/api/update_order_field`(`foms/api/orders/field_update.py` `update_order_field_response`)는 한 경로로 12개 넘는 칸을 쓴다. 실측일·시공일만 `can_edit_erp` 로 좁히고 나머지는 STAFF 전 팀이다.

### 운영 사용 실측(2026-10-20, 읽기 전용 집계, 개인정보 없음)
- 활성 계정: ADMIN 3 · MANAGER 13(영업 9·CS 2·회계 2) · STAFF 13(시공 10·도면 2·영업 1). 생산·출고 팀 STAFF 는 0명.
- 최근 120일 `order_field_changes` 작성자: MANAGER·ADMIN 만(27,648건). 시공·도면 STAFF 0건.
- 같은 기간 시공·도면 STAFF 의 접근 기록은 파일 열람·내려받기뿐.
→ 아래 변경으로 막히는 실제 업무는 없다.

## 변경
1. 매니페스트에서 다섯 endpoint 의 `policy_id` 를 `STAFF_MUTATION` → `ERP_EDIT` 로 바꾼다.
   - `erp_orders_structured.api_put_order_structured` (PUT 구조화 폼 — 금액 재계산)
   - `erp_orders_structured.api_patch_order_structured_fields` (PATCH 인라인 칸 수정)
   - `order_edit.edit_order` (옛 편집 폼 POST — GET 은 가드 대상이 아님)
   - `orders.update_order_status` · `orders.bulk_update_order_status` (상태 변경)
2. `/api/update_order_field` 는 칸별로 본다(경로 전체를 좁히면 AS·지방 체크리스트 칸까지 바뀐다).
   - `manager_name`(담당자) → `ERP_EDIT`
   - `status` → 물류 보드 목표 상태(`is_logistics_board_status`)면 `SHIPMENT_EDIT`(영업·CS·출고), 그 밖은 `ERP_EDIT`. 역할표가 출고팀에 "출고·물류 일정" 은 허용하고 main-stage 는 금지하기 때문이다.
   - 거부는 403 JSON `{"success": false, "code": "FORBIDDEN", "message": ...}`, 주문은 그대로.
   - 판정은 `user_can(policy_id, user)` 하나로 한다(ADMIN·MANAGER 통과·팀 alias 가 정책 엔진과 같다).
3. `ERP_EDIT` 설명을 "주문 form(구조화 폼·담당자·상태)·CS·SALES command" 로 고친다.

## 건드리지 않는 것
- 새 주문 만들기·초안·복사·첨부·알림톡 발송 경로(`STAFF_MUTATION` 그대로) — 이번 범위는 "있는 주문의 금액·담당자·상태".
- `update_order_field` 의 다른 칸(AS 날짜·지방 체크리스트·출고 예정일 등).
- 화면 버튼 숨기기. 서버가 403 을 주면 기존 오류 안내가 뜬다.

## 테스트
새 파일 `tests/domains/test_order_edit_team_scope.py`(정책 가드 켬):
- 거부: STAFF 시공·도면·생산·출고, VIEWER → 다섯 경로 403 + 주문 값 그대로.
- 허용: ADMIN·MANAGER·STAFF 영업·CS·회계·MEASURE → 가드 통과.
- `update_order_field`: 시공 STAFF 의 `manager_name`·`status`(main-stage) 403, 출고 STAFF 의 물류 상태는 통과, 시공 STAFF 의 AS 칸(`as_visit_date`)은 지금처럼 통과(음성 대조군).
- 매니페스트 단언: 다섯 endpoint 가 `ERP_EDIT`.
