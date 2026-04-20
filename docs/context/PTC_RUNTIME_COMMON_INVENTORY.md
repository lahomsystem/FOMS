# PTC §4.5 — `static/js/runtime` + `foms/services/common` inventory rationale

Controlling sources: `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` §4.5, `tests/contracts/runtime/test_ptc_physical_exactness.py`.

Contract: each listed file is either **keep** in place, **move** (not applied in this tranche — would require import churn), **merge**, or **explicit exception**.

## `static/js/runtime/` (§4.5.1)

| File | Decision | Rationale |
|------|----------|-----------|
| `column-resizer.js` | keep | Shared ERP table column resize behavior used across templates. |
| `common_utils.js` | keep | Cross-page DOM/helpers shared by ERP shell. |
| `erp-mobile-shell.js` | keep | Mobile shell wiring for ERP layout. |
| `erp-shell.js` | keep | Canonical ERP shell fragment navigation/cache/prefetch runtime. Relocated from legacy `static/js/erp/runtime-shell.js` by the 2026-04-17 ERP Order cleanup/rename landing (commit `eaf5a444`). Referenced by `templates/partials/shared/layout_scripts.html` whenever `request.path` starts with `/erp/`. |
| `script.js` | keep | Legacy shared runtime bootstrap hooks still referenced by templates. |
| `upload-progress.js` | keep | Shared upload progress UI for file flows. |

## `foms/services/common/` (§4.5.2)

| File | Decision | Rationale |
|------|----------|-----------|
| `__init__.py` | keep | Package marker. |
| `address_ai_ops_loader.py` | keep | Address AI ops loading shared by address pipelines. |
| `address_converter.py` | keep | Shared address normalization/conversion. |
| `business_calendar.py` | **explicit exception — keep** | `2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (enumerated item 16): `business_calendar` / `/calendar` 축은 별도 승인 전까지 구조 정리 범위 밖 — **keep in `foms/services/common/`** for this tranche. |
| `dashboard_cache.py` | keep | Dashboard micro-cache (Redis DTO slice) shared by orders/measurement/shipment/drawing/production/construction/CS dashboards. Landed in commit `bf70243d` ("feat: Dashboard micro-cache(Redis DTO slice) 및 DMC 문서·검증"). Cross-domain dashboard helper — correctly lives in `foms/services/common/`. |
| `ept_b7_profile.py` | keep | EPT B7 latency profile contract shared by ERP shell HTTP (`erp_shell_http.py`) and its domain test (`tests/domains/test_ept_b7_profile.py`). Landed with the ERP fast-page EPT shell/fragment/prefetch tranche (commit `9541bfd5`). |
| `erp_navigation_contract.py` | keep | Canonical ERP navigation contract (route → tab/fragment mapping) consumed by dashboards across orders/measurement/shipment/drawing/production/construction/CS. Cross-domain contract helper — belongs in `foms/services/common/`. Landed in commit `9541bfd5`. |
| `erp_shell_http.py` | keep | ERP shell fragment HTTP helper (ETag/cache/prefetch headers) shared by all ERP fragment endpoints. Paired with `ept_b7_profile.py`. Landed in commit `9541bfd5`. |
| `geocode_config.py` | keep | Shared geocode configuration. |
| `map_generator.py` | keep | Shared map generation helpers. |
