# Step 5 Batch 65 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step5-batch64-map-delegation-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: measurement dashboard template/partial/JS 자산의 canonical namespace를 `measurement/*`로 옮기고 legacy 경로는 wrapper/shim으로 유지한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 5 Batch 65 executed, template/JS namespace move completed**

이유:
- `templates/measurement/*`, `static/js/measurement/*`를 canonical source of truth로 추가하고 dashboard template script refs를 새 경로로 정렬했다.
- 기존 `templates/erp_measurement_dashboard.html`, `templates/partials/erp_measurement_mobile_*.html`는 thin wrapper/include로 축소해 missed caller를 흡수했다.
- 기존 `static/js/erp/measurement*.js`, `static/js/measurement-image-export.js`는 canonical bundle을 로드하는 compatibility shim으로 유지했다.

## 2. 실제 변경 범위
- `templates/measurement/dashboard.html`
- `templates/measurement/partials/mobile_filters.html`
- `templates/measurement/partials/mobile_dates.html`
- `templates/measurement/partials/mobile_list.html`
- `templates/erp_measurement_dashboard.html`
- `templates/partials/erp_measurement_mobile_filters.html`
- `templates/partials/erp_measurement_mobile_dates.html`
- `templates/partials/erp_measurement_mobile_list.html`
- `static/js/measurement/dashboard.js`
- `static/js/measurement/mobile.js`
- `static/js/measurement/dashboard-columns.js`
- `static/js/measurement/manual-rows.js`
- `static/js/measurement/image-export.js`
- `static/js/erp/measurement.js`
- `static/js/erp/measurement-mobile.js`
- `static/js/erp/measurement-dashboard-columns.js`
- `static/js/erp/measurement-manual-rows.js`
- `static/js/measurement-image-export.js`
- `tests/test_measurement_js_contract.py`

## 3. 의도적으로 건드리지 않은 것
- shared static/template root 위치 자체
- strict CSP 전환
- `business_calendar` / `/calendar`

## 4. 검증 결과
### 4.1 template/JS namespace suite
- 실행:
  - `python -m pytest tests/test_measurement_js_contract.py tests/test_erp_measurement_mobile_render.py tests/test_measurement_slice_contract.py -q`
- 결과:
  - `11 passed in 1.45s`

### 4.2 post-audit shim re-check
- 실행:
  - `python -m pytest tests/test_measurement_js_contract.py tests/test_measurement_slice_contract.py tests/test_map_view_manager_contract.py tests/test_erp_measurement_mobile_render.py -q`
- 결과:
  - `16 passed in 1.38s`

## 5. 해석
- Step 5는 `templates/` / `static/`의 물리 루트 이동이 아니라 namespace 정리여야 하므로, canonical asset은 새 하위 경로로 만들고 legacy path는 wrapper/shim으로 남기는 방식이 가장 안전했다.
- 후감리에서 지적된 silent-failure 가능성을 줄이기 위해 legacy JS shim에는 `document.currentScript` fallback과 `console.warn`를 추가했다. 이 변경은 loader 관측 가능성만 올리고 canonical 로드 경로는 유지한다.

## 6. 다음 단계
1. Batch 66에서 사후감리 verdict와 Step 5 완료 상태를 spec/status/archive/checkpoint에 반영한다.
2. `business_calendar` / `/calendar` 축은 계속 제외한다.
