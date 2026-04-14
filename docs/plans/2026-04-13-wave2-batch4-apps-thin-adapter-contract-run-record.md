# Wave 2 Batch W2-B4 — `apps/` thin-adapter contract freeze

> **batch ID:** W2-B4  
> **risk axis:** overlay contract documentation  
> **live truth source:** W2-B1 / W2-B2 + `foms/platform/blueprints.py`  
> **실행일:** 2026-04-13

## 1. 요약

- **Adapter matrix**를 bridge debt **row id**와 연결해 고정했다.
- **alias shim / thin adapter**로 이미 확인된 모듈만 **모듈 최상단 docstring**을 정규화했다 (`route`/import 변경 없음).

## 2. Adapter matrix (contract label freeze)

| Matrix id | W2-B2 debt ref | Module / surface | Contract label | Notes |
|-----------|----------------|------------------|----------------|-------|
| AM-001 | BD-003 | `apps.erp_measurement_dashboard` | **alias shim** | `foms.web.measurement.dashboard` module replacement |
| AM-002 | BD-003 | `apps.api.erp_measurement` | **alias shim** | `foms.api.measurement` module replacement |
| AM-003 | BD-005 | `apps.api.orders` (`orders_bp`) | **thin adapter** | Routes call `foms.api.orders.*_response` helpers |
| AM-004 | BD-001…BD-019 (non-shim/non-BD-005) | 기타 `apps.*` registry surfaces | **legacy owner** 또는 **mixed owner** (BD-009 등) | Wave 3+에서 패턴별 처리; 본 matrix는 라벨만 고정 |

## 3. Docstring 정규화 (허용 범위)

| File | Change |
|------|--------|
| `apps/api/orders/__init__.py` | thin adapter 계약 명시 |
| `apps/api/erp_measurement.py` | Wave 2 shim 표기 보강 |
| `apps/erp_measurement_dashboard.py` | Wave 2 shim 표기 보강 |

## 4. Future rule (freeze)

- 신규 `apps/` route batch는 **예외 사유 + canonical/adapter justification** 없이 진행하지 않는다 (controlling spec §2.4와 정합).

## 5. Verification

| 검사 | 결과 |
|------|------|
| `apps/*` docstring만 변경, route/import 미변경 | ✅ |
| `python -c "import app; print('APP_OK')"` | PASS |

## 6. Direction Lock

1–10: thin adapter **과장 없음**; matrix가 BD id와 연결됨.

## 7. touched files

- `apps/api/orders/__init__.py`
- `apps/api/erp_measurement.py`
- `apps/erp_measurement_dashboard.py`
- 본 run record

---

**verification result:** PASS  
**residual risk:** legacy surface에 thin 라벨 오적용 방지 — Wave 3에서 BD/AM 교차 검증 유지
