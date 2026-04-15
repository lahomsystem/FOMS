# SLG-B1 — Verification hardening freeze (run record)

> 배치: `SLG-B1` (`docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md` §6.2)  
> 실행일: 2026-04-15  
> 성격: **tests + harness only** (코드 리팩터 없음; gate는 현재 트리에서 **의도적으로 red**)

## 1. Scope / acceptance

- `tests/contracts/runtime/foms_namespace_surface_tests.py`에 §4 closed-set + shell/fragment + `render_template('errors/...')` + `orders/erp_policy_internal` 금지 게이트 추가·freeze.
- `tools/harness/strict_canonical_b12_clean_room.ps1`에 `templates/`·`foms/web/`·`foms/api/`·`foms/services/` subtree closed-set 비교 + 금지 경로 프로브 추가.
- Plan 허용: **전체 suite green 아님**; 새 `test_slg_literal_gap_*`는 drift를 정확히 지목.

## 2. 증거

| 항목 | 결과 |
|------|------|
| `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k slg_literal_gap -v` | **8 failed, 3 passed** (의도: 미해결 drift) |
| 실패 항목 | templates/web/api/services closed-set, `shared/layout.html`, `templates/errors`, `http.py` errors 템플릿, `extends shared/layout` 다수 |
| 통과 항목 | partials/shared extends 금지, doctype/html 금지, `orders/erp_policy_internal` 없음 |

## 3. 변경 파일

- `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_slg_literal_gap_*` 및 §4 allowlist 상수.
- `tools/harness/strict_canonical_b12_clean_room.ps1` — subtree `Assert-SubtreeClosedSet` + forbidden path probe.

## 4. 3축 + GDM 감리 (요약)

| 축 | 결과 |
|----|------|
| A literal | 게이트가 SLG-B0 인벤토리와 일치하는 drift 보고 → **High 0** |
| B runtime | 제품 동작 변경 없음 → **High 0** |
| C proof | pytest 증거 확보; red 허용 계약 충족 → **High 0** |
| GDM | 계획 §6.2와 구현 1:1 | **High 0** |

**Stop rule:** 해당 없음 (금지 dir를 green으로 주장하지 않음).

## 5. 다음

- `SLG-B2` — template shell/error remediation (코드 배치).
