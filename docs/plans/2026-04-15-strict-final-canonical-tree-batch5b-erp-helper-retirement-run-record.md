# SFC-B5B — ERP helper retirement

> Batch: `SFC-B5B`  
> 실행일: 2026-04-15  
> 성격: **code** (실행 계획 `§6.7`)  
> 선행: `SFC-B5A`  
> 권장 canonical home: `foms/services/orders/erp_automation.py`, `order_text_parser.py`

## 1. 목표

- 루트 `erp_automation.py`, `erp_order_text_parser.py` **제거** (importlib shim 포함).
- `foms/api/erp_orders_structured.py`에서 **루트 모듈명 import 0**.
- 구현 본문은 **`foms/services/orders/`** 단일 정본.

## 2. 수행 요약

| 항목 | 내용 |
|------|------|
| 정본 모듈 | `foms/services/orders/erp_automation.py`, `order_text_parser.py` |
| 루트 제거 | `erp_automation.py`, `erp_order_text_parser.py` |
| `scripts/ops/` | 얇은 재노출 (`foms.services.orders.*`에서 import) |
| 소비자 갱신 | `foms/api/erp_orders_structured.py`, `scripts/ops/erp_build_step_runner.py` |
| 계약 테스트 | `foms_namespace_surface_tests.test_erp_automation_uses_canonical_erp_policy_import` — `foms.services.orders.erp_automation` 기준으로 갱신 |

## 3. 검증 증거

| 검증 | 결과 |
|------|------|
| `rg` 제품 트리 `from erp_automation\|from erp_order_text_parser` (py) | `backups/**` 외 **0건** |
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests` (full) | **574 passed** |

## 4. 다음 배치

- **`SFC-B5C`** — backup/helper retirement (`simple_backup_system` / `foms/api/backup.py` vs `foms/services/admin/backup_service.py`, 계획 §6.8).
