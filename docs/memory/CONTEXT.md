# AS대시보드 데이터 이관 컨텍스트

- **배경**: Staging 환경과 Production 환경이 분리되어 운영되던 중, Staging에만 등록된 'AS 관련 주문'을 Production으로 이관해야 하는 요구사항 발생.
- **주요 제약사항**:
  1. Staging과 Production 간 `orders.id` 가 다를 수 있거나 충돌할 수 있음 (Id 덮어쓰기 금지).
  2. 공통 주문은 제외해야 하므로 `(customer_name, phone)` 등 비즈니스 식별자를 기준으로 중복을 판단해야 함.
  3. `orders` 테이블의 컬럼뿐 아니라 `structured_data` 및 연관 `order_attachments` 등의 데이터도 최대한 보존해야 "완벽한 이관"이 됨.
- **해결 방향**: Python을 이용한 마이그레이션 스크립트로 양쪽 DB를 연결해 메모리 상에서 비교(Set Diff) 후, 신규 Insert 수행 (새로운 PK 할당).

---

# 원격 업로드 개선 컨텍스트 (2026-02-23)

- **배경**: 원격(production)에서 파일 업로드가 느리다는 사용자 피드백. 이미 Phase D Direct Upload(브라우저 → R2 직접 PUT)를 사용 중이라 지연 구간은 사용자 네트워크 ↔ R2.
- **결정**: 서버/API 변경 없이 **프론트만** 개선. Phase 1으로 **병렬 업로드**(파일 2~3개씩 동시 전송) 적용하여 체감 시간 단축. Phase 2(진행률 표시)는 선택.
- **참조**: `docs/memory/PLAN_UPLOAD_IMPROVEMENT.md`

---

# 실측 대시보드 담당자 직접 입력 (2026-02-23)

- **배경**: 실측 대시보드에서 담당자 셀을 클릭해 직접 입력하고, 저장 시 주문 상세(Order.manager_name 및 ERP Beta 시 structured_data.parties.manager.name)에 반영되도록 요청.
- **원인**: 템플릿은 `data-is-erp`만 넘기는데 JS는 `dataset.isErpBeta`를 참조해 편집 분기가 항상 비활성화됨. API는 이미 ERP Beta용 `/api/erp/measurement/update`, 비-ERP용 `/api/orders/update_order_field`(manager_name) 지원.
- **결정**: measurement.js에서 (1) `tr.dataset.isErp === 'true'` 로 수정해 ERP Beta에서 인라인 편집 동작하도록 함. (2) 비-ERP 주문은 담당자만 `update_order_field`로 저장하도록 분기 추가.
- **참조**: `docs/memory/PLAN_MEASUREMENT_MANAGER.md`