# SLG-B6 — `erp_policy_internal` flat leaf closure (run record)

> 배치: `SLG-B6` (`docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md` §6.7)  
> 실행일: 2026-04-15

## 1. Scope / acceptance

- `foms/services/erp_policy_internal/*.py` → `foms/services/orders/erp_policy_{constants,data_access,permissions,quests,tasks}.py`.
- `foms/services/erp_policy.py` public surface 유지; **import 경로만** `foms.services.orders.erp_policy_*` 로 전환.
- `foms/services/erp_policy_internal/` 및 `foms/services/orders/erp_policy_internal/` 없음.
- §4.4 services closed-set: top-level `erp_policy_internal` 디렉터리 없음.

## 2. 증거

| 검증 | 결과 |
|------|------|
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py` | **182 passed** |
| `python -c "import app; print('APP_OK')"` | **APP_OK** |
| `python tools/harness/verify_result.py --json` | **success: true** |

## 3. 변경 요약

- **추가:** `foms/services/orders/erp_policy_constants.py`, `erp_policy_data_access.py`, `erp_policy_permissions.py`, `erp_policy_quests.py`, `erp_policy_tasks.py` (상대 import → `foms.services.orders.*` 절대 import).
- **삭제:** `foms/services/erp_policy_internal/`.
- **갱신:** `foms/services/erp_policy.py` (docstring + import 경로).

## 4. 3축 + GDM 감리 (요약)

| 축 | 결과 |
|----|------|
| A literal | `erp_policy_internal` 트리 제거; flat leaf 5개만 존재 — **High 0** |
| B runtime | `erp_policy` re-export 동일 공개 API — **High 0** |
| C proof | SLG services closed-set 게이트 포함 전 계약 green — **High 0** |
| GDM | §6.7 ledger·public surface 규칙 준수 — **High 0** |

**Medium:** 0.

## 5. 다음

- `SLG-B7` — verification hardening land, `docs/AI_STATUS.md` closeout 문구, clean-room + final run record.
