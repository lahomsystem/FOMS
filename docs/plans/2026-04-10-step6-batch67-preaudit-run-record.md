# Step 6 Batch 67 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 문서: `docs/plans/2026-04-10-step6-large-file-inventory-plan.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Step 6 large-file decomposition inventory 전에 대형 파일 후보, 제외 축, 위험도를 병렬 전감리로 먼저 고정한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 6 Batch 67 executed, pre-audit completed**

이유:
- `explore-codebase`, `code-reviewer`, `frontend-ui`, `python-backend` 병렬 에이전트를 동원해 backend/UI/hotspot/risk를 교차 검토했다.
- exact line count를 다시 확인해 `apps/api/orders.py(911)`, `templates/wdcalculator/partials/wdcalculator_scripts.html(3493)`, `templates/partials/erp_beta_js.html(2516)`, `apps/api/chat/routes.py(889)`, `foms/services/erp_policy.py(764)`, `static/css/erp-pro.css(3595)`를 Tier A anchor candidate로 고정했다.
- generated bundle(`static/wdplanner/assets/index-*.js`), tooling giant file, `models.py`, `business_calendar` / `/calendar` 축은 separate track 또는 explicit exclusion으로 분리했다.

## 2. 실제 변경 범위
- `docs/plans/2026-04-10-step6-batch67-preaudit-run-record.md`

## 3. 핵심 발견 사항

### 3.1 backend
- `apps/api/orders.py`는 nearby geocode/route scoring, calendar projection, `update_order_field`, status/bulk status가 한 모듈에 섞여 있어 Step 6 이후 가장 먼저 contract freeze가 필요한 backend candidate다.
- `apps/api/chat/routes.py`는 upload, room/member, message, page route가 한 파일에 공존해 두 번째 backend split 후보로 적합하다.
- `foms/services/erp_policy.py`는 이미 canonical source이므로 path migration보다 internal package split rule이 별도로 필요하다.

### 3.2 frontend/template
- `templates/wdcalculator/partials/wdcalculator_scripts.html`는 Jinja data injection + DOM render + fetch + local state가 한 파일에 응축된 최대 hotspot이다.
- `templates/partials/erp_beta_js.html`, `templates/layout.html`, `templates/regional_dashboard.html`, `templates/partials/erp_dashboard_styles.html`도 후속 inventory 대상이지만, Step 6 first-wave는 WDCalculator/ERP Beta 쪽이 우선이다.

### 3.3 exclusions
- `business_calendar` / `/calendar`: 사용자 지시대로 계속 제외
- `static/wdplanner/assets/index-*.js`: generated bundle이므로 hand decomposition 대상 아님
- `models.py`: persistence/schema track으로 분리

## 4. 해석
- Step 6는 실제 분해가 아니라 decomposition governance의 입력값을 정리하는 단계이므로, pre-audit에서 candidate tier와 explicit exclusion을 먼저 고정하는 것이 핵심이었다.
- 이후 Batch 68/69는 이 run record를 기준으로 inventory doc과 separate spec을 작성한다.

## 5. 다음 단계
1. Batch 68에서 exact line count 기반 inventory 문서를 작성한다.
2. Batch 69에서 large-file decomposition 전용 governance spec을 별도로 만든다.
3. `business_calendar` / `/calendar` 축은 계속 제외한다.
