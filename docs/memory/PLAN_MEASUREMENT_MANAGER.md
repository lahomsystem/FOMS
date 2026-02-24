# 실측 대시보드 담당자 직접 입력 계획

**작성일**: 2026-02-23  
**목표**: 실측 대시보드에서 담당자를 직접 입력 가능하게 하고, 저장 시 주문 상세(Order.manager_name + structured_data)에 반영.

---

## 1. 코드 리뷰 요약

- **실측 대시보드** (`templates/erp_measurement_dashboard.html`): 담당자 컬럼에 이미 `editable-cell` + `data-field="manager"` 적용되어 있으나, **JS에서 `data-is-erp-beta`를 참조**하고 템플릿은 **`data-is-erp`**만 넘기고 있어 **인라인 편집이 동작하지 않음**.
- **API**: `POST /api/erp/measurement/update/<order_id>` 에서 `field === 'manager'` 시 `order.manager_name`과 `structured_data.parties.manager.name` 동기화 완료. 단 **ERP Beta 주문만 허용** (비-ERP 주문은 400).
- **주문 상세**: `order_pages.py`·`order_edit`·다른 대시보드에서 `order.manager_name` 및 `structured_data.parties.manager.name` 표시. 저장 시 둘 다 갱신하면 주문 상세에 그대로 반영됨.
- **표시**: `apply_erp_display_fields_to_orders()`가 `structured_data.parties.manager.name` → `order.manager_name` 으로 채우므로, 실측 대시보드 행의 담당자 표시는 이미 일치.

---

## 2. 변경 사항

| 구분 | 내용 |
|------|------|
| **원인** | `measurement.js`에서 `tr.dataset.isErpBeta === 'true'` 사용. HTML은 `data-is-erp`만 있어 `dataset.isErpBeta`는 항상 undefined → 편집 분기 미동작. |
| **수정 1** | `tr.dataset.isErp === 'true'` 로 비교하도록 수정 → ERP Beta 주문에서 담당자(·주소·전화) 인라인 편집 활성화. |
| **수정 2** | 비-ERP Beta 주문도 담당자만 직접 입력 가능하도록: `field === 'manager'` 이고 `!isErpBeta` 일 때 `POST /api/orders/update_order_field` 호출 (`field: 'manager_name'`, `value`). |

---

## 3. 영향 범위

- **수정 파일**: `static/js/erp/measurement.js` (인라인 편집 로직 1곳).
- **API**: 기존 `/api/erp/measurement/update`, `/api/orders/update_order_field` 활용. 신규 API 없음.
- **주문 상세 반영**: 이미 두 API가 `order.manager_name`(및 Beta 시 `structured_data.parties.manager.name`) 갱신하므로 추가 작업 없음.

---

## 4. 검증

- 실측 대시보드에서 ERP Beta 주문의 담당자 셀 클릭 → 입력 → blur 시 저장되고, 주문 상세(편집 페이지 등)에서 동일 담당자 표시.
- 비-ERP Beta 주문의 담당자 셀 클릭 → 입력 → blur 시 `update_order_field`로 저장되고, 주문 상세에 반영.
