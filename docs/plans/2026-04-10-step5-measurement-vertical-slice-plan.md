# Step 5 Measurement Vertical Slice Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Step 5 pilot로 `measurement` vertical slice를 구조-only 방식으로 `foms/{web,api,services}` canonical source로 이관하고, legacy `apps/*` 진입 경로와 화면 동작을 유지한다.

**Architecture:** `apps/erp_measurement_dashboard.py`와 `apps/api/erp_measurement.py`는 legacy alias shim으로 축소하고, 실제 source of truth는 `foms.web.measurement.dashboard`와 `foms.api.measurement`로 이동한다. 페이지/API가 공유하는 실측 날짜 helper는 `foms.services.measurement_dates`로 올리고, `apps/api/erp_map.py`의 measurement 전용 분기는 `foms.api.measurement_map` helper로 위임해 map flow까지 같은 slice 안에서 닫는다.

**Tech Stack:** Flask Blueprint, Jinja2 templates, Vanilla JS, SQLAlchemy ORM, existing `foms.services.*` namespace, pytest.

**Execution mode:** 사용자 지시에 따라 이 세션에서 같은 프로세스(RPI + 전/후감리 + 배치 실행)로 끝까지 수행한다.

---

## Scope

- 포함: `measurement` ERP page/API, measurement 날짜 helper, measurement map mode helper, measurement dashboard template/mobile partial, measurement dashboard JS asset 경로.
- 제외: `business_calendar` module/page, self-measurement page, shipment settings page 자체, schema/Alembic 변경.
- Gate: 비즈니스 로직 diff 없이 구조/경로/source-of-truth만 변경한다.
- Stop 조건: `models.py`/migration/schema 변경 필요, JSONB update contract 변경 필요, shared map shell 전체 이관 필요가 드러나면 즉시 중단 후 별도 ADR.

## Batch 61: Contract Freeze

**Files**
- Add: `tests/test_measurement_slice_contract.py`
- Verify existing: `tests/test_measurement_js_contract.py`, `tests/test_map_view_manager_contract.py`, `tests/test_foms_namespace_imports.py`, `tests/test_erp_measurement_mobile_render.py`

**Work**
- Legacy import path(`apps.erp_measurement_dashboard`, `apps.api.erp_measurement`)와 canonical path(`foms.web.measurement.dashboard`, `foms.api.measurement`)가 같은 runtime contract를 유지해야 함을 테스트로 고정한다.
- Measurement dashboard template/JS canonical path를 고정하는 focused contract를 추가한다.

**Verification**
- `python -m pytest tests/test_measurement_slice_contract.py -q`
- `python -m pytest tests/test_measurement_js_contract.py tests/test_map_view_manager_contract.py -q`

## Batch 62: Shared Measurement Helper Extraction

**Files**
- Add: `foms/services/measurement_dates.py`
- Modify: `apps/erp_measurement_dashboard.py`, `apps/api/erp_measurement.py`

**Work**
- `extract_all_measurement_dates()`와 내부 정규화 helper를 page module에서 service layer로 승격한다.
- page/API 모두 canonical service import로 정렬한다.

**Verification**
- `python -m pytest tests/test_foms_namespace_imports.py -q`
- `python -m pytest tests/test_erp_measurement_manager_sync.py -q`

## Batch 63: Canonical Measurement Page/API Modules

**Files**
- Add: `foms/web/measurement/__init__.py`
- Add: `foms/web/measurement/dashboard.py`
- Add: `foms/api/measurement.py`
- Modify: `apps/erp_measurement_dashboard.py`
- Modify: `apps/api/erp_measurement.py`

**Work**
- Page/API source of truth를 `foms.web.measurement.dashboard`, `foms.api.measurement`로 이동한다.
- Legacy `apps/*` modules는 `sys.modules` alias shim으로 바꿔 기존 import/monkeypatch contract를 유지한다.

**Verification**
- `python -m pytest tests/test_measurement_slice_contract.py tests/test_erp_measurement_mobile_render.py -q`
- `python -m pytest tests/test_foms_namespace_imports.py -q`

## Batch 64: Measurement Map Mode Delegation

**Files**
- Add: `foms/api/measurement_map.py`
- Modify: `apps/api/erp_map.py`

**Work**
- `erp_map.py`의 `dashboard=measurement` 전용 JSON/HTML response branch를 slice helper로 위임한다.
- Shared `map_view.html` shell은 유지하되, measurement 전용 backend branch는 slice 내부로 묶는다.

**Verification**
- `python -m pytest tests/test_map_snapshot.py tests/test_foms_map_generator.py tests/test_map_view_manager_contract.py -q`
- `python -m pytest tests/test_foms_namespace_imports.py -q`

## Batch 65: Template and JS Namespace Move

**Files**
- Add: `templates/measurement/dashboard.html`
- Add: `templates/measurement/partials/mobile_filters.html`
- Add: `templates/measurement/partials/mobile_dates.html`
- Add: `templates/measurement/partials/mobile_list.html`
- Add: `static/js/measurement/dashboard.js`
- Add: `static/js/measurement/mobile.js`
- Add: `static/js/measurement/dashboard-columns.js`
- Add: `static/js/measurement/manual-rows.js`
- Add: `static/js/measurement/image-export.js`
- Modify: `templates/erp_measurement_dashboard.html`
- Modify: `templates/partials/erp_measurement_mobile_filters.html`
- Modify: `templates/partials/erp_measurement_mobile_dates.html`
- Modify: `templates/partials/erp_measurement_mobile_list.html`
- Modify: `tests/test_measurement_js_contract.py`

**Work**
- Canonical measurement dashboard template/partial/JS 경로를 new namespace로 옮긴다.
- Legacy template paths는 thin wrapper로 남겨 missed caller를 흡수한다.
- Dashboard template script refs는 new JS path를 가리키도록 바꾼다.

**Verification**
- `python -m pytest tests/test_measurement_js_contract.py tests/test_erp_measurement_mobile_render.py -q`
- `python -m pytest tests/test_measurement_slice_contract.py -q`

## Batch 66: Post-Audit and Closeout

**Files**
- Add: `docs/plans/2026-04-10-step5-batch61-contract-freeze-run-record.md`
- Add: `docs/plans/2026-04-10-step5-batch62-helper-extraction-run-record.md`
- Add: `docs/plans/2026-04-10-step5-batch63-canonical-modules-run-record.md`
- Add: `docs/plans/2026-04-10-step5-batch64-map-delegation-run-record.md`
- Add: `docs/plans/2026-04-10-step5-batch65-template-js-move-run-record.md`
- Add: `docs/plans/2026-04-10-step5-batch66-closeout-run-record.md`
- Modify: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- Modify: `docs/AI_STATUS.md`
- Modify: `docs/ARCHIVE_INDEX.md`
- Modify: `docs/context/COMPACT_CHECKPOINT.md`

**Work**
- 후감리 결과를 반영해 measurement slice verdict를 기록한다.
- Step 5 완료 상태와 다음 자동 단계(Step 6 inventory)를 문서에 동기화한다.

**Verification**
- `python -m pytest -q`
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `ReadLints` on touched paths
