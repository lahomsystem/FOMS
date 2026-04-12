# Step 6 Batch 68 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step6-batch67-preaudit-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Step 6 large-file candidate를 exact line count, tier, future target namespace, contract freeze 관점으로 inventory 문서에 고정한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 6 Batch 68 executed, inventory document completed**

이유:
- `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`를 추가해 Python/HTML/JS/CSS threshold scan 결과와 Tier A/B/C matrix를 문서화했다.
- original Step 6 anchor candidate(`apps/api/orders.py`, `templates/wdcalculator/partials/wdcalculator_scripts.html`)를 유지하면서, `templates/partials/erp_beta_js.html`, `apps/api/chat/routes.py`, `foms/services/erp_policy.py`, `static/css/erp-pro.css`를 Tier A로 확장했다.
- future execution에서 필요한 contract freeze/test gap/manual checklist도 inventory 문서에 함께 포함했다.

## 2. 실제 변경 범위
- `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
- `docs/plans/2026-04-10-step6-batch68-inventory-run-record.md`

## 3. inventory 핵심 결과

### 3.1 Tier A
- `apps/api/orders.py`
- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `templates/partials/erp_beta_js.html`
- `apps/api/chat/routes.py`
- `foms/services/erp_policy.py`
- `static/css/erp-pro.css`

### 3.2 Tier B
- `apps/api/wdcalculator.py`
- `apps/api/attachments.py`
- `apps/api/erp_map.py`
- `apps/api/events.py`
- `apps/api/notifications.py`
- `templates/layout.html`
- `templates/regional_dashboard.html`
- `templates/partials/erp_dashboard_styles.html`
- `static/js/measurement/dashboard.js`
- `static/js/wam/attachments.js`
- `static/css/style.css`
- `apps/erp_dashboard.py`

### 3.3 Tier C / explicit exclusion
- `business_calendar` / `/calendar`
- `models.py`
- `tests/test_foms_namespace_imports.py`
- `tools/research_center/coding_research_center.py`
- `foms_map_generator.py`
- `static/wdplanner/assets/index-*.js`
- `backups/`

## 4. 해석
- inventory 문서는 “무엇을 왜 쪼갤 것인가”를 먼저 고정하는 문서다.
- 이 문서를 기준으로 future decomposition batch는 route/template/CSS/service 각각의 public surface를 별도 contract로 먼저 잠가야 한다.

## 5. 다음 단계
1. Batch 69에서 large-file decomposition 전용 governance spec을 별도 작성한다.
2. root governance spec에는 Step 6 완료와 next step만 남기고, 세부 분해 규칙은 새 spec으로 위임한다.
