# Orders Boundary Decomposition Plan
> 작성일: 2026-04-11 | 상태: ✅ 완료 (regional + status + field-update slice)

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
`orders` 대형 분해의 첫 실행 배치를 위한 live boundary 기준 실행 계획을 고정한다. 문서상의 legacy 후보명 `apps/api/orders.py` 대신 실제 runtime 경계인 `apps/api/orders/__init__.py` + `foms/api/orders/{calendar,nearby,mutations}.py`를 source of truth로 사용한다.

### 1.2 기능 요구사항
1. `orders` decomposition 대상의 실제 runtime 경계를 문서에 명시한다.
2. `/api/orders`, `/api/orders/nearby`, `/api/update_regional_status`, `/api/update_regional_memo`, `/api/update_order_field`, `/api/update_order_status`, `/api/bulk_update_order_status`의 HTTP/JSON/side-effect 계약을 contract freeze 대상으로 고정한다.
3. 첫 구조-only 배치는 `foms/api/orders/mutations.py` 내부에서 regional mutation slice만 분리하는 범위로 제한한다.
4. 외부 caller가 보는 import path와 Flask blueprint path는 유지한다.

### 1.3 예외/제약 조건
- 새 Alembic revision, schema 변경, permission 정책 변경, geocode/business logic 변경을 섞지 않는다.
- `business_calendar` / `/calendar` 제외 원칙은 계속 유지한다.
- `apps/api/orders/__init__.py`의 route path, decorator order, exported symbol은 public contract로 간주한다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `apps/api/orders/__init__.py` | Flask wrapper/public export contract freeze 기준 유지 |
| `foms/api/orders/calendar.py` | FullCalendar list-response contract freeze |
| `foms/api/orders/nearby.py` | nearby 검색 응답/지오코드 side-effect contract freeze |
| `foms/api/orders/mutations.py` | 첫 구조-only 분해 대상. regional mutation slice 분리 후보 |
| `tests/test_app_smoke.py` | 기존 `/api/orders` smoke 유지 |
| `tests/test_as_received_date_kst.py` | status/bulk status 날짜 helper contract 유지 |
| `tests/test_erp_as_dashboard_tabs.py` | `update_order_field` 응답 shape 유지 |
| `tests/test_foms_namespace_imports.py` | `apps.api.orders` export/lazy import contract 유지 |

### 2.2 아키텍처 방향
- `apps/api/orders/__init__.py`는 계속 thin Flask adapter로 유지한다.
- canonical execution 대상은 `foms/api/orders/*` 내부로 제한한다.
- 첫 배치는 `mutations.py`에서 regional handlers (`update_regional_status_response`, `update_regional_memo_response`)만 별도 내부 모듈로 분리하고, `update_order_field_response`/status mutation은 같은 배치에 섞지 않는다.
- external import churn 대신 `foms/api/orders/__init__.py` re-export bridge를 유지한다.

### 2.3 의존성 및 영향 범위
- 영향 모듈: `foms/platform/blueprints.py`, `apps/api/orders/__init__.py`, `foms/api/orders/*`, `foms/services/erp_display.py`, `foms/services/erp_permissions.py`, `foms/services/jobs/queue.py`
- DB 영향: 없음
- hidden contract:
  - `enqueue_geocode_order_address()`
  - `sync_erp_flat_columns()`
  - `flag_modified(order, "structured_data")`
  - `OrderEvent` 생성
  - FullCalendar용 raw list 응답 shape

## 3. Steps — 실행 단계
- [x] Step 1: inventory drift를 기록한다. (`apps/api/orders.py`가 아니라 package boundary가 live source임을 고정)
- [x] Step 2: existing orders HTTP/export/side-effect contract를 focused tests로 freeze한다.
- [x] Step 3: `foms/api/orders/mutations.py`에서 regional mutation slice만 구조적으로 분리한다.
- [x] Step 4: post-audit 후 상태 문서와 inventory/reference를 동기화한다.

### 3.1 Batch 1 결과
- `tests/test_orders_boundary_contract.py`로 `/api/orders`, `/api/orders/nearby`, regional invalid-order contract, wrapper export surface를 freeze했다.
- `foms/api/orders/regional.py`를 신설해 `update_regional_status_response`, `update_regional_memo_response`를 `mutations.py`에서 분리했다.
- `foms/api/orders/__init__.py` re-export bridge와 `apps/api/orders/__init__.py` route path/decorator order는 유지했다.
- `get_today_kst`는 wrapper에서 handler로 명시 주입되도록 정리해 `tests/test_as_received_date_kst.py` contract를 안정화했다.
- 감리 결과: No blocking findings. residual risk는 regional success-path focused test 부재뿐이다.

### 3.2 다음 batch 후보
### 3.2 Batch 2 결과
- `foms/api/orders/status.py`를 신설해 `update_order_status_response`, `bulk_update_order_status_response`를 `mutations.py`에서 분리했다.
- `apps/api/orders/__init__.py`의 wrapper call path와 `get_today_kst` 명시 주입 contract는 유지했다.
- 감리 결과: No blocking findings. residual risk는 status route response-shape 전용 contract test가 아직 얇다는 점이다.

### 3.3 Batch 3 결과
- `foms/api/orders/field_update.py`를 신설해 `update_order_field_response`와 관련 helper/constant를 `mutations.py`에서 분리했다.
- `foms/api/orders/mutations.py`는 얇은 compatibility bridge로 축소해 hidden import risk를 낮췄다.
- `tests/test_orders_boundary_contract.py`에 `/api/update_order_field`의 실제 reachable contract를 추가 고정했다.
- 감리 결과: No blocking findings. residual risk는 `field_update.py` 내부 allowlist와 불일치하는 dead branch(`address`, `customer_name`, `phone`, geocode enqueue`)가 남아 있다는 점이다.

### 3.4 Closeout
- `orders` live boundary decomposition pilot은 목표 범위 내에서 완료됐다.
- 최종 구조는 `apps/api/orders/__init__.py` thin wrapper + `foms/api/orders/{calendar,nearby,regional,status,field_update}.py` canonical helpers + compatibility bridge `mutations.py`다.
- 외부 caller import path와 Flask route path/decorator order는 유지됐다.

## 4. 검증 기준
- [x] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python tools/harness/verify_result.py --json` 통과
- [x] `python -m pytest tests/test_app_smoke.py tests/test_as_received_date_kst.py tests/test_erp_as_dashboard_tabs.py tests/test_foms_namespace_imports.py -q` 통과
- [x] 신규 orders contract freeze tests 통과
- [x] `/api/orders` 응답이 raw JSON list contract를 유지함을 확인
- [x] `/api/orders/nearby`의 필수 error/success key shape가 유지됨을 확인
- [x] `/api/update_order_field`의 reachable success/reject contract를 focused tests로 고정함

## 5. 참고 자료
- 관련 spec: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
- 관련 inventory: `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
- 관련 상태 문서: `docs/AI_STATUS.md`
- 관련 아카이브: `docs/ARCHIVE_INDEX.md`
