# Phase D (코드 품질 및 리팩토링) GDM 감리 보고서

- **감리일**: 2026-03-15
- **감리자**: Grand Develop Master (GDM)
- **대상**: Phase D 완료 후 검증
- **계획서**: `docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md`

---

## 1. 요약

| 항목 | 결과 | 비고 |
|------|------|------|
| 계획서 Phase D 준수 | ✅ 통과 | D-1~D-8 전 항목 검증 완료 |
| 근본 원인 수정 원칙 | ✅ 준수 | 증상 우회 없음 |
| 프로젝트 규칙(CLAUDE.md, AGENTS.md) | ✅ 준수 | |
| 회귀 위험 | 🟢 낮음 | 앱 기동 정상, deprecated 제거·호환 유지 |
| **종합 판정** | **✅ Phase D 감리 통과** | |

---

## 2. 계획서 Phase D 항목별 검증

### D-1. `query().get()` 제거 → `db.get(Order, order_id)` + soft-delete 검사

**계획서 요구**:
- 6개 파일, 13곳
- `db.get(Order, order_id)` 사용
- `order.status == "DELETED"` 또는 `order.deleted_at is not None` 검사

**검증 결과**: ✅ **준수**

| 파일 | db.get 사용 | soft-delete 검사 |
|------|-------------|------------------|
| `apps/api/erp_orders_as.py` | 4곳 (33, 118, 195, 237) | ✅ |
| `apps/api/erp_orders_confirm.py` | 1곳 (35) | ✅ |
| `apps/api/erp_orders_construction.py` | 3곳 (32, 71, 142) | ✅ |
| `apps/api/erp_orders_cs.py` | 1곳 (35) | ✅ |
| `apps/api/erp_orders_production.py` | 2곳 (32, 77) | ✅ |
| `apps/api/erp_orders_revision.py` | 2곳 (272, 338) | ✅ |

**패턴**: `if not order or order.status == "DELETED" or order.deleted_at is not None:` 일관 적용

**비고**: `backups/tier2_secondary/system_files/app.py`에 `db.query(Order).get()` 1곳 잔존 — 백업 아카이브로 운영 코드 아님.

---

### D-2. `api_put_order_structured` 책임 분리

**계획서 요구**:
- `_handle_stage_transition(...)`
- `_record_structured_events(...)`
- `_apply_structured_side_effects(...)`
- `_finalize_draft_state(...)`

**검증 결과**: ✅ **준수**

| 함수 | 위치 | 역할 |
|------|------|------|
| `_handle_stage_transition` | 90~126행 | 단계 전환 감지, OrderEvent/Quest 생성 |
| `_record_structured_events` | 128~185행 | 긴급/일정/오너팀 변경 이벤트 기록 |
| `_apply_structured_side_effects` | 187~193행 | auto-task 적용 |
| `_finalize_draft_state` | 195~220행 | draft 메타 정리, session 정리 |

`api_put_order_structured` 내 호출 순서: `_handle_stage_transition` → `_record_structured_events` → `_apply_structured_side_effects` → `_finalize_draft_state` (304~310행)

---

### D-3. API 응답 형식 점진 통일 (message 추가, error 호환 유지)

**계획서 요구**:
- 실패 응답에 `message` 추가
- `error` 병행 유지 (소비 코드 이전 전까지)

**검증 결과**: ✅ **준수**

- `erp_orders_structured`, `erp_orders_as`, `erp_orders_confirm`, `erp_orders_construction`, `erp_orders_cs`, `erp_orders_revision`, `erp_orders_drawing`, `erp_orders_blueprint`, `erp_shipment_settings` 등 주요 API에서 `{'success': False, 'message': ...}` 패턴 사용
- `apps/api/orders.py` 143행: `'message': ..., 'error': ...` 병행 (호환 유지)

---

### D-4. 중복 유틸 통합

**계획서 요구**:
- Python: `services/erp_utils.py`에 `ensure_path`
- JS: `static/js/erp/common_utils.js`에 `safeJsonParse`, `safeJsonFetch`

**검증 결과**: ✅ **준수**

| 유틸 | 위치 | 상태 |
|------|------|------|
| `ensure_path` | `services/erp_utils.py` 6~10행 | ✅ 정의됨 |
| `ensure_path` 사용 | `apps/api/erp_orders_as.py` 17, 204행 | ✅ import 후 사용 |
| `safeJsonParse` | `static/js/erp/common_utils.js` 3~13행 | ✅ `window.ERPUtils.safeJsonParse` |
| `safeJsonFetch` | `static/js/erp/common_utils.js` 15~23행 | ✅ `window.ERPUtils.safeJsonFetch` |
| `escapeHtml` | `static/js/erp/common_utils.js` 25~30행 | ✅ 기존 통합 유지 |

---

### D-5. 매직 문자열 상수화 (ERP_DRAFT_PLACEHOLDER_*)

**계획서 요구**:
- `ERP_DRAFT_PLACEHOLDER_CUSTOMER`, `ERP_DRAFT_PLACEHOLDER_PHONE`, `ERP_DRAFT_PLACEHOLDER_PRODUCT`

**검증 결과**: ✅ **준수**

`constants.py` 57~59행:
```python
ERP_DRAFT_PLACEHOLDER_CUSTOMER = "ERP Beta"
ERP_DRAFT_PLACEHOLDER_PHONE = "000-0000-0000"
ERP_DRAFT_PLACEHOLDER_PRODUCT = "ERP Beta"
```

`erp_orders_structured.py` 19행에서 import 후 사용.

---

### D-6. `logger.exception` 적용 (erp_shipment_settings)

**계획서 요구**:
- `import traceback` 함수 내부 인라인 제거, `logger.exception` 사용

**검증 결과**: ✅ **준수**

`apps/api/erp_shipment_settings.py` 147행:
```python
logger.exception("[ERP_SHIPMENT] 업데이트 오류: %s", e)
```

---

### D-7. `storage.get_file_type()` public 메서드

**계획서 요구**:
- public `get_file_type(filename: str) -> str` 추가
- 호출부를 `storage.get_file_type(filename)`으로 교체
- `_get_file_type` 직접 참조 제거

**검증 결과**: ✅ **준수**

| 항목 | 상태 |
|------|------|
| `services/storage.py` 497~506행 | `get_file_type()` public 메서드 정의 |
| `_get_file_type` | deprecated 래퍼로 유지 (508~510행) |
| `apps/api/erp_orders_drawing.py` | `storage.get_file_type(filename)` 사용 |
| `apps/api/attachments.py` | `storage.get_file_type(filename)` 사용 |
| `apps/api/chat/routes.py` | `storage.get_file_type(filename)` 사용 |
| `apps/` 내 `_get_file_type` 직접 호출 | **0건** (완전 제거) |

---

### D-8. 인라인 스타일 → CSS 클래스 (erp-toast-container, erp-col-resizer)

**계획서 요구**:
- `.erp-col-resizer`, `.erp-toast-container` CSS 책임 이동

**검증 결과**: ✅ **준수**

| 위치 | 내용 |
|------|------|
| `templates/partials/erp_dashboard_styles.html` | `#erp-toast-container`, `.erp-toast-container` (5~15행), `.erp-col-resizer` (26~35행) 정의 |
| `templates/partials/erp_dashboard_scripts_core.html` | `container.className = 'erp-toast-container'` (15행), `resizer.className = 'erp-col-resizer'` (84행) |

---

## 3. 근본 원인 수정 원칙 준수 여부

**CLAUDE.md / AGENTS.md 요구**:
- 근본 원인 파악 → 근본 수정
- 증상 우회 금지
- 에러 숨기기 금지
- 구시대 방식 적용 금지

**검증 결과**: ✅ **준수**

| Phase D 항목 | 근본 수정 여부 |
|--------------|----------------|
| D-1 | deprecated `query().get()` 제거 → SQLAlchemy 2.0 `Session.get()` 사용. soft-delete 검사로 삭제된 주문 접근 차단 |
| D-2 | 단일 거대 함수 → 책임별 함수 분리 (구조적 개선) |
| D-3 | 응답 계약 점진 통일 (message 추가, error 호환) |
| D-4 | 중복 코드 → 공용 유틸 통합 |
| D-5 | 매직 문자열 → 상수화 |
| D-6 | traceback 인라인 → logger.exception (표준 로깅) |
| D-7 | private 메서드 직접 호출 → public API 도입 |
| D-8 | 인라인 스타일 → CSS 클래스 (관심사 분리) |

**증상 우회·에러 숨기기·미봉책**: 발견되지 않음.

---

## 4. 프로젝트 규칙 준수

| 규칙 | 준수 |
|------|------|
| 함수 50줄 이하 | D-2 분리로 `api_put_order_structured` 책임 축소 |
| API 응답 형식 통일 | D-3 `message` 추가 |
| 인라인 스타일 금지 | D-8 CSS 클래스 사용 |
| data-* + safeJsonParse 패턴 | D-4 common_utils.js 제공 |
| deprecated API 사용 금지 | D-1, D-7 제거 |
| bare except 금지 | D-6 logger.exception 사용 |

---

## 5. 회귀 위험 평가

| 검증 항목 | 결과 |
|-----------|------|
| `python -c "import app; print('APP_OK')"` | ✅ 성공 |
| `db.get(Order, id)` 동작 | SQLAlchemy 2.0 표준 API, 기존 `query().get()`과 동등 |
| soft-delete 검사 | `status == "DELETED"` + `deleted_at is not None` 이중 검사로 Phase C 기준과 일치 |
| `error` 필드 제거 | 미수행 — D-3 계획대로 `message` 추가 + `error` 호환 유지 |
| `_get_file_type` | deprecated 래퍼로 유지, 내부에서 `get_file_type` 호출 |

**회귀 위험**: 🟢 **낮음**. 기존 동작 의미 변경 없음.

---

## 6. 권장 사항 (선택)

1. **D-4 확장**: `apps/orders.py`의 로컬 `ensure_path`(19행)를 `services.erp_utils.ensure_path`로 통합 검토 (시그니처 호환 시).
2. **D-3 후속**: 프론트엔드 소비 코드가 `message`로 완전 이전되면 `error` 필드 제거 검토.
3. **backups/tier2_secondary**: 운영 코드 아님. 필요 시 별도 정리.

---

## 7. 결론

**Phase D (코드 품질 및 리팩토링) GDM 감리 결과: ✅ 통과**

- 계획서 Phase D 전 항목 준수
- 근본 원인 수정 원칙 준수
- 프로젝트 규칙 준수
- 회귀 위험 낮음
- 앱 기동 정상

---

*감리 완료: 2026-03-15*
