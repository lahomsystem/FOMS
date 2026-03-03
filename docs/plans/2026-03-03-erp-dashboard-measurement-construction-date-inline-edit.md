# 실측일·시공일 대시보드 직접 입력 (달력) 계획서

> **목표**: **메인 ERP 대시보드** 작업 큐 그리드에서만 실측일/시공일을 달력으로 직접 입력 가능하게 하고, 변경 시 ERP Beta 탭에 반영. 변경 권한: 영업, 라홈, 하우드, CS팀. (시공/생산 대시보드는 수정 없이 읽기 전용 유지.)

---

## 1. 관련 코드 리뷰 요약

### 1.1 표시 위치 및 데이터 소스

| 위치 | 파일 | 컬럼 | 데이터 소스 |
|------|------|------|-------------|
| **작업 큐 (시공 대시보드)** | `templates/partials/erp_construction_filters_grid.html` | 실측일 L252~253, 시공일 L254~255 | `o.measurement_date`, `o.construction_date` (enriched from `structured_data.schedule`) |
| **작업 큐 (메인 ERP 대시보드)** | `templates/partials/erp_dashboard_grid.html` | 실측일 L307~308, 시공일 L309~310 | 동일 |
| **생산 대시보드** | `templates/partials/erp_production_filters_grid.html` | 실측일 L168~169, 시공일 L170~171 | 동일 |

- 시공/메인/생산 페이지 모두 `apply_erp_beta_display_fields()`로 `order.measurement_date` / `order.scheduled_date`가 `structured_data.schedule.measurement.date` / `schedule.construction.date`에서 채워짐 (`services/erp_display.py`). **직접 입력(달력) 편집은 메인 ERP 대시보드만 적용**하며, 시공/생산 대시보드는 기존처럼 읽기 전용 표시만 유지.

### 1.2 저장 경로 (ERP Beta)

- **실측일**: `structured_data.schedule.measurement.date` (+ 레거시 `orders.measurement_date` 정규화용)
- **시공일**: `structured_data.schedule.construction.date` (+ `orders.scheduled_date` 동기화)
- 주문 편집 폼(`order_edit.py`)에서 실측일/시공일 변경 시 위 경로에 이미 반영됨 (L190~198).  
- **API**: `POST /api/update_order_field` 에서 `field` = `measurement_date` / `scheduled_date` 로 PATCH 가능 (`apps/api/orders.py` L525, L585~593).  
  - Beta 주문이면 `structured_data.schedule.measurement.date` / `schedule.construction.date` 갱신 후 `flag_modified(order, 'structured_data')`.  
  - `order.measurement_date` / `order.scheduled_date` 는 현재 API에서 설정하지 않음. 표시는 `erp_display`에서 structured_data 기준으로 덮어쓰므로 동작에는 문제 없음. (선택) 일관성 위해 DB 컬럼도 동기화할 수 있음.

### 1.3 권한

- **현재**  
  - `update_order_field`: `@role_required(['ADMIN', 'MANAGER', 'STAFF'])` 만 허용.  
  - ERP 수정 권한: `services/erp_permissions.py` → `can_edit_erp(user)` = ADMIN 또는 팀이 `CS`(라홈/하우드), `SALES`(영업) 인 경우.
- **요구사항**: “변경 권한 : 영업, 라홈, 하우드, CS팀” → 기존 ERP 수정 권한과 동일하게 `can_edit_erp` 로 제한하면 됨.

### 1.4 기존 패턴 (참고)

- 지방/수도권 대시보드: `<input type="date" class="editable-date">` + `data-order-id`, `data-field` → `change` 시 `POST /api/update_order_field` (예: `regional_dashboard.html`, `erp_as_dashboard.html`).
- ERP Beta 탭: `erp_beta_tab.html` L164~166 (실측일), L195~196 (시공일) 에서 `#erp-measurement-date`, `#erp-construction-date` 로 편집. 저장은 주문 저장 시 `structured_data` 에 반영.

---

## 2. 요구사항 정리

1. **대상 화면**:  
   - **메인 ERP 대시보드** 작업 큐 그리드만 (실측일/시공일 셀).  
   - `templates/partials/erp_dashboard_grid.html`. 시공/생산 대시보드는 수정하지 않음(읽기 전용 유지).
2. **동작**:  
   - 실측일/시공일 셀을 **달력(type="date")으로 직접 입력** 가능.  
   - 변경 시 **저장 API 호출** → **ERP Beta 탭의 실측일/시공일**에 반영 (동일 `structured_data` 사용).
3. **권한**:  
   - **영업, 라홈, 하우드, CS팀** 만 편집 가능 → `can_edit_erp(user)` True 인 경우에만 인라인 날짜 입력 UI 노출 및 API 호출 허용.

---

## 3. 구현 계획

### 3.1 백엔드

| 단계 | 내용 |
|------|------|
| **B1** | `POST /api/update_order_field` 에서 `field in ('measurement_date', 'scheduled_date')` 인 경우, `role_required` 뿐 아니라 **`can_edit_erp(user)` 이면 허용**하도록 조건 추가. (기존 ADMIN/MANAGER/STAFF 유지.) |
| **B2** | (선택) Beta 주문일 때 `measurement_date`/`scheduled_date` 업데이트 시 `order.measurement_date` / `order.scheduled_date` 도 동일 값으로 설정해 DB와 표시 일치. |

### 3.2 프론트엔드 (그리드) — 메인 대시보드만

| 단계 | 내용 |
|------|------|
| **F1** | **메인 ERP 대시보드** (`erp_dashboard_grid.html`):  
  - 실측일/시공일 `<td>` 를 `can_edit_erp` 일 때만 `<input type="date">` 로 렌더링.  
  - `data-order-id="{{ o.id }}"`, `data-field="measurement_date"` / `data-field="scheduled_date"` (시공일은 API가 `scheduled_date` 사용).  
  - 값: `o.measurement_date or ''`, `o.construction_date or ''` (표시용 필드명 그대로 사용). |
| **F2** | **메인 대시보드 스크립트** (`erp_dashboard_scripts.html`):  
  - `input[data-field="measurement_date"]`, `input[data-field="scheduled_date"]` 에 대한 `change` 리스너 추가.  
  - `change` 시 `POST /api/update_order_field` (body: `order_id`, `field`, `value`).  
  - 성공 시 해당 셀 값만 갱신 또는 토스트 메시지; 실패 시 에러 메시지. |
| **F3** | `can_edit_erp` 가 False 인 행은 기존처럼 텍스트만 표시 (`{{ o.measurement_date or '-' }}` 등). |

### 3.3 ERP Beta 탭 반영

- 저장 API가 `structured_data.schedule.measurement.date` / `schedule.construction.date` 를 갱신하므로, 주문 상세(ERP Beta 탭)를 다시 열면 이미 반영됨. **별도 동기화 로직 불필요.**

### 3.4 적용 대시보드·라우트

- **편집 적용**: **메인** `erp_dashboard.py` → `erp_dashboard` → `erp_dashboard_grid.html` + `erp_dashboard_scripts.html` 만 수정.
- 시공/생산 대시보드는 그리드·스크립트 변경 없이 읽기 전용 유지.

---

## 4. 파일 변경 목록 (예상) — 메인만

| 파일 | 변경 내용 |
|------|------------|
| `apps/api/orders.py` | `update_order_field`: measurement_date/scheduled_date 일 때 `can_edit_erp(user)` 허용 로직 추가. (선택) Beta 시 DB 컬럼 동기화. |
| `templates/partials/erp_dashboard_grid.html` | 실측일/시공일 `<td>` 를 `can_edit_erp` 일 때 `<input type="date">` 로 변경. |
| `templates/partials/erp_dashboard_scripts.html` | 실측일/시공일 input change → `POST /api/update_order_field` 바인딩. |

---

## 5. 테스트 시나리오

1. **권한**:  
   - 영업/라홈/하우드/CS 팀(또는 ADMIN): **메인** 대시보드 그리드에서 실측일·시공일 셀에 date input 표시되고, 변경 시 API 성공.  
   - 그 외 팀: 텍스트만 표시, input 없음. (시공/생산 대시보드는 모든 사용자에게 읽기 전용.)
2. **저장·표시**:  
   - 실측일/시공일 변경 후 같은 행에서 값 유지.  
   - 주문 상세 > ERP Beta 탭에서 실측일/시공일이 변경된 값으로 표시.
3. **API**:  
   - `POST /api/update_order_field` 로 `measurement_date` / `scheduled_date` 전송 시 200, `structured_data.schedule` 갱신 확인.
4. **에러 처리**:  
   - 비로그인/권한 없음 시 401/403.  
   - 잘못된 order_id/field 시 400/404.  
   - 프론트: 실패 시 알림, 입력값 복구 가능하면 복구.

---

## 6. 상태

- [x] B1: update_order_field 권한 확장 (can_edit_erp) — 완료
- [x] B2: (선택) DB 컬럼 동기화 — 기존 setattr로 이미 반영됨, 생략
- [x] F1: 메인 그리드(erp_dashboard_grid) 실측일/시공일 input 전환 — 완료
- [x] F2~F3: erp_dashboard_scripts_dom.html에 change 핸들러 및 권한별 표시 — 완료
- [ ] 수동 테스트 (메인 대시보드 권한·저장·ERP Beta 반영)
