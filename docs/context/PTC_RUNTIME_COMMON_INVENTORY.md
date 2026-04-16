# PTC §4.5 — `static/js/runtime` + `foms/services/common` inventory rationale

Controlling sources: `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` §4.5, `tests/contracts/runtime/test_ptc_physical_exactness.py`.

Contract: each listed file is either **keep** in place, **move** (not applied in this tranche — would require import churn), **merge**, or **explicit exception**.

## `static/js/runtime/` (§4.5.1)

| File | Decision | Rationale |
|------|----------|-----------|
| `column-resizer.js` | keep | Shared ERP table column resize behavior used across templates. |
| `common_utils.js` | keep | Cross-page DOM/helpers shared by ERP shell. |
| `erp-mobile-shell.js` | keep | Mobile shell wiring for ERP layout. |
| `script.js` | keep | Legacy shared runtime bootstrap hooks still referenced by templates. |
| `upload-progress.js` | keep | Shared upload progress UI for file flows. |

## `foms/services/common/` (§4.5.2)

| File | Decision | Rationale |
|------|----------|-----------|
| `__init__.py` | keep | Package marker. |
| `address_ai_ops_loader.py` | keep | Address AI ops loading shared by address pipelines. |
| `address_converter.py` | keep | Shared address normalization/conversion. |
| `business_calendar.py` | **explicit exception — keep** | `2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (enumerated item 16): `business_calendar` / `/calendar` 축은 별도 승인 전까지 구조 정리 범위 밖 — **keep in `foms/services/common/`** for this tranche. |
| `geocode_config.py` | keep | Shared geocode configuration. |
| `map_generator.py` | keep | Shared map generation helpers. |
