# 실측일·시공일 인라인 편집 — 계획서 1:1 소스코드 검증 보고서

> GDM 총괄: 계획서 `2026-03-03-erp-dashboard-measurement-construction-date-inline-edit.md` 대비 구현 코드 전수 대조 및 문법·로직 점검.

---

## 1. 계획서 §3.1 백엔드

### B1: update_order_field 권한 확장

| 계획 요구 | 구현 위치 | 검증 결과 |
|-----------|-----------|-----------|
| `field in ('measurement_date', 'scheduled_date')` 일 때 `can_edit_erp(user)` 이면 허용 | `apps/api/orders.py` L519~525 | ✅ `_date_fields = ('measurement_date', 'scheduled_date')`, `field in _date_fields` 시 `can_edit_erp(user)` 확인 |
| 그 외 필드는 기존 ADMIN/MANAGER/STAFF 유지 | 동일 L524~525 | ✅ `else` 분기에서 `user.role not in ('ADMIN', 'MANAGER', 'STAFF')` 시 403 |
| `@role_required` 제거 후 뷰 내부에서 권한 처리 | L499~501, L515~525 | ✅ 데코레이터는 `@login_required`만 사용, 401/403 JSON 반환 |
| 실측일/시공일 403 메시지 | L522 | ✅ "실측일/시공일 수정 권한이 없습니다. (영업, 라홈, 하우드, CS팀만 가능)" |

**문법/로직**: `get_user_by_id`, `can_edit_erp` import 확인됨. `session.get('user_id')` 없으면 user None → 401. `order_id`/`field`/`value`는 기존과 동일하게 `data.get()` 사용. **오차 없음.**

### B2: (선택) DB 컬럼 동기화

| 계획 | 구현 | 검증 |
|------|------|------|
| Beta 시 `order.measurement_date` / `order.scheduled_date` 동기화 | L550~551 `setattr(order, field, value)` | ✅ `measurement_date`/`scheduled_date` 포함해 모든 일반 필드에 적용되며, 이후 L594~603에서 `structured_data.schedule` 갱신. 별도 동기화 불필요. |

---

## 2. 계획서 §3.2 프론트엔드 (메인 대시보드만)

### F1: erp_dashboard_grid.html

| 계획 요구 | 구현 위치 | 검증 결과 |
|-----------|-----------|-----------|
| 실측일/시공일 `<td>` 를 `can_edit_erp` 일 때만 `<input type="date">` | L307~322 | ✅ `{% if can_edit_erp\|default(false) %}` 내부에만 input |
| `data-order-id="{{ o.id }}"` | L310, L318 | ✅ |
| `data-field="measurement_date"` / `data-field="scheduled_date"` (시공일은 API가 scheduled_date) | L310, L318 | ✅ |
| 값: `o.measurement_date or ''`, `o.construction_date or ''` | L310, L318 `value="{{ o.measurement_date or '' }}"`, `value="{{ o.construction_date or '' }}"` | ✅ |

### F3: can_edit_erp False 시 텍스트만

| 계획 | 구현 | 검증 |
|------|------|------|
| 권한 없으면 기존처럼 텍스트만 | L311~312, L319~320 `{% else %}` 블록 `{{ o.measurement_date or '-' }}`, `{{ o.construction_date or '-' }}` | ✅ |

### F2: change 리스너 및 API 호출

| 계획 요구 | 구현 위치 | 검증 결과 |
|-----------|-----------|-----------|
| `input[data-field="measurement_date"]`, `input[data-field="scheduled_date"]` 에 대한 change | `erp_dashboard_scripts_dom.html` L296~323 | ✅ `.erp-dashboard-date-input` 로 바인딩 (해당 input만 해당 클래스 보유) |
| change 시 `POST /api/update_order_field` (body: order_id, field, value) | L304~306 | ✅ `JSON.stringify({ order_id: parseInt(orderId, 10), field: field, value: value })` |
| 성공 시 해당 셀 값 유지 또는 토스트 | L310~311 | ✅ input 값은 사용자가 이미 선택한 상태이므로 유지, `data-prev-value`만 갱신 |
| 실패 시 에러 메시지 | L313~314 alert | ✅ |
| 실패 시 입력값 복구 | L314, L319 `input.value = prevValue \|\| ''` | ✅ |

**문법**: `document.querySelectorAll`, `addEventListener`, `fetch`, `.then(function...)` 사용. ES5 스타일로 문법 오류 없음. `parseInt(orderId, 10)`으로 order_id 숫자 전달, API의 `data.get('order_id')`와 일치.

---

## 3. 계획서 §2·§4 — 적용 범위

| 항목 | 확인 내용 | 결과 |
|------|-----------|------|
| 메인 대시보드만 편집 적용 | `erp_dashboard_grid.html` 에만 `erp-dashboard-date-input` 및 date input 사용 | ✅ |
| 시공 대시보드 미수정 | `erp_construction_filters_grid.html` L252~255 여전히 `{{ o.measurement_date or '-' }}` 텍스트만 | ✅ |
| 생산 대시보드 미수정 | 동일 그리드 패턴 유지 (계획서상 생산 파일명만 언급, 실측/시공 셀 동일) | ✅ |
| 변경 파일 목록 (§4) | orders.py, erp_dashboard_grid.html, 스크립트(실제: erp_dashboard_scripts_dom.html) | ✅ 계획서 §6에서 dom partial 명시됨 |

---

## 4. 문법·엣지 체크

| 항목 | 결과 |
|------|------|
| Python 문법 (orders.py) | ✅ Lint 0건 |
| Jinja2 문법 (erp_dashboard_grid) | ✅ `\|default(false)`, `{{ }}` 사용 적절 |
| JavaScript 문법 (erp_dashboard_scripts_dom) | ✅ 구문 오류 없음, IE 호환 function 사용 |
| API body 키 일치 | 프론트 `order_id` ↔ 백엔드 `data.get('order_id')` ✅ |
| field 이름 | 실측일 `measurement_date`, 시공일 `scheduled_date` (표시는 construction_date) ✅ |

---

## 5. 권장 사항 (선택)

- **request.get_json() None**: `update_order_field`에서 `data = request.get_json()` 후 `data`가 None이면 `data.get(...)` 시 AttributeError 가능. 동일 파일 내 다른 API(update_order_status 등)도 동일 패턴 사용 중이므로 본 구현만 변경할 필요는 없음. 추후 전역 보강 시 `if not data: return jsonify({...}), 400` 추가 검토 가능.

---

## 6. 종합

- **계획서와 구현 1:1 대조**: B1, B2, F1, F2, F3 모두 계획서 요구사항과 일치.
- **문법 오류**: 없음.
- **적용 범위**: 메인 대시보드만 편집, 시공/생산 읽기 전용 유지 확인됨.
- **에러 처리**: 401/403/404/400 반환 및 프론트 실패 시 alert·입력 복구 구현됨.

**결론: 계획서 대비 오차 없이 구현되었으며, 문법 및 로직 이상 없음.**
