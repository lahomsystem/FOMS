# ERP 주문 옛 전화번호(phone 칸) 정리 — SPEC

- 작성: 2026-10-06
- 상태: 승인 대기
- 등급: 코어(운영 DB 쓰기 + 하네스 도구 변경) → Spec → 승인 → 구현

## 1. 증상

ERP 대시보드에서 `6485` 를 검색하면 화면 전화번호가 `010-5100-8886` 인 주문 #4147(박주희)이 나온다.

## 2. 원인 (운영 읽기 전용 실측, 2026-10-06)

- #4147 의 flat `orders.phone` = `010-5210-6485`(옛 번호), 정본 `structured_data.parties.customer.phone` = `010-5100-8886`, `erp_phone_digits` = `01051008886`.
- 대시보드 검색(`foms/services/erp_dashboard_search.py` `_phone_search_clause`)은 `erp_phone_digits` 와 함께 `Order.phone ILIKE` 도 OR 로 본다 → 옛 번호로 걸린다.
- 표시 경로(`apply_erp_display_fields`)는 정본으로 덮어 그리므로 화면은 늘 새 번호다. SQL 만 틀린 무증상 drift.
- 저장 경로가 `phone` 을 갱신하지 않던 결함은 `8654dff78`(2026-09-02)에서 이미 고쳤다. PUT 은 `_sync_identity_flat_columns`, PATCH 는 필드별 `setattr(order, 'phone', ...)` 로 동기한다. **새 코드 결함 없음.**

## 3. 운영 모집단 (is_erp_order, 정본 고객 전화 있음, `digits(phone) <> erp_phone_digits`)

| 분류 | 건수 | 처리 |
|---|---|---|
| 활성 주문, 옛 번호가 정본과 다름 | 46 (최신 생성 2026-08-13) | **정리 대상** |
| 활성 주문, 다전화 — `digits(phone)` 이 `erp_phone_digits` 에 포함 | 7 | 건드리지 않음 |
| DELETED | 112 (2026-09-03 이후 4건은 전부 삭제된 draft, phone=`000-0000-0000`) | 건드리지 않음 |

9월 2일 이후 생성된 활성 주문에서는 새 drift 가 0건이다 → 회귀가 아닌 과거 잔여분이다.

## 4. 변경

### 4.1 도구 (`foms/services/orders/erp_flat_audit.py`, `tools/ops/*_erp_flat_columns.py`)

- 신원 컬럼 `phone` 을 감사·백필 대상에 추가한다. 기대값 = `_sync_identity_flat_columns` 와 같은 규칙(정본 전화가 있고 placeholder 가 아닐 때만 정본 값).
- 분류:
  - `digits(phone) == erp_phone_digits` 또는 포함(다전화) → CLEAN
  - 정본 전화 비었음 / placeholder → CLEAN(덮지 않음)
  - status = DELETED → 제외
  - 그 외 → SAFE
- `TOOL_VERSION` 을 올린다(`column_schema_sha256` 이 바뀌므로 옛 artifact 와 섞이지 않게).
- 규칙은 `_sync_identity_flat_columns` 를 그대로 재사용한다(복사본 금지). 이 함수가 `foms/api` 안에 있으면 서비스 모듈로 옮기고 위치-고정 계약 테스트를 단다.

### 4.2 운영 적용 (기존 승인 경로)

1. `audit_erp_flat_columns.py` → 46건 SAFE 확인, 목록을 사용자에게 제시
2. 대상 행의 옛 `phone` 값을 control root 에 스냅숏 저장(되돌리기 = UPDATE 1회)
3. `ops_scope_for_backfill(scope, "BACKFILL_APPLY")` → `create_ops_approval_request.py`
4. 사용자가 `/admin/ops/approvals/<id>` 에서 재인증 승인
5. `backfill_erp_flat_columns.py --apply --approval-token-file <token> --verify`
6. 검증: 위 §3 쿼리 재실행 시 활성 drift 0건(다전화 7건 제외), 대시보드에서 `6485` 검색 시 #4147 미노출

## 5. 범위 밖

- `customer_name` 도 같은 축이지만 이번 증상과 무관하다. 감사 결과에 함께 보고만 하고 쓰지 않는다.
- 검색 술어(`Order.phone ILIKE`) 제거는 하지 않는다 — 비-ERP 주문 검색이 이 컬럼에 의존한다.

## 6. 테스트

- 단위: 분류 4종(CLEAN 일치·다전화·placeholder, SAFE, DELETED 제외)
- 백필: SAFE 행에 정본 전화가 들어가고 다른 파생 컬럼은 그대로
- `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1` exit 0
