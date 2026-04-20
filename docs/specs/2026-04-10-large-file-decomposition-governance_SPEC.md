# Large File Decomposition Governance Spec

> 작성일: 2026-04-10
> 상태: 승인된 Step 6 output
> 상위 거버넌스: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> inventory 입력: `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`

## 1. 목표

이 문서는 Step 6 이후의 **대형 파일 분해 실행 배치**가 따라야 할 별도 거버넌스 spec이다.

핵심 목표는 다음 두 가지다.

1. 저장소 구조 거버넌스와 실제 large-file decomposition execution을 분리한다.
2. future split이 구조-only 원칙, contract freeze, verification baseline을 깨지 않도록 공통 규칙을 고정한다.

## 2. 적용 범위

이 spec은 다음 조건의 runtime/source-adjacent 파일에 적용한다.

- Python: 500줄 초과
- HTML/Jinja template: 800줄 초과
- JS: 300줄 초과
- CSS: 500줄 초과

우선 inventory 기준 주요 대상은 아래와 같다.

- `apps/api/orders.py`
- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `templates/partials/erp_beta_js.html`
- `apps/api/chat/routes.py`
- `foms/services/erp_policy.py`
- `static/css/erp-pro.css`

## 3. Non-goals

이 spec이 자동으로 허용하지 않는 것:

- 실제 코드 분해를 Step 6 문서 배치와 같은 PR/배치에서 수행하는 것
- 새 Alembic revision, schema 변경, `models.py` persistence refactor를 large-file split과 섞는 것
- `templates/` / `static/` 루트 물리 이동을 decomposition 첫 배치에 포함하는 것
- generated bundle(`static/wdplanner/assets/index-*.js`) hand-edit
- 사용자 제외 대상인 `business_calendar` / `/calendar` 축에 손대는 것

## 4. 공통 실행 원칙

### 4.1 Inventory-first

- 모든 decomposition 후보는 먼저 inventory row를 가져야 한다.
- inventory row에는 최소한 다음이 포함되어야 한다.
  - 경로
  - 줄 수
  - artifact type
  - risk summary
  - suggested future target namespace
  - required contract freeze/test/manual check

### 4.2 One boundary per batch

- 하나의 execution batch는 하나의 주요 boundary만 다룬다.
- 예시:
  - `orders.py` split batch
  - `wdcalculator_scripts.html` static extraction batch
  - `erp-pro.css` logical split batch
- API split + template split + CSS split을 같은 batch에 섞지 않는다.

### 4.3 Structure first, behavior later

- 첫 decomposition batch는 파일/경계/namespace만 바꾸고 business logic 변경은 금지한다.
- 중복 제거, naming cleanup, selector rename 같은 quality cleanup은 split batch와 분리한다.

### 4.4 Compatibility by default

- external import path, template include path, static asset path, `window.*` global 같은 public surface는 기본적으로 유지한다.
- 경로가 바뀌어야 할 경우 thin wrapper, alias shim, loader shim 또는 stable bridge를 남긴다.

## 5. Artifact-specific Rules

### 5.1 Flask API module decomposition

적용 대상 예:

- `apps/api/orders.py`
- `apps/api/chat/routes.py`
- `apps/api/attachments.py`
- `apps/api/erp_map.py`

필수 규칙:

- route path, HTTP method, response JSON shape를 먼저 contract test 또는 golden assert로 고정한다.
- queue enqueue, webhook side effect, notification emit은 hidden contract로 간주한다.
- `structured_data` mutation은 반드시 `copy.deepcopy` + `flag_modified` 패턴을 유지한다.
- route layer에 있는 heavy query/geocode/formatting logic은 `foms/services/*`로 먼저 추출하고, route는 thin adapter로 만든다.

### 5.2 Template + inline JS decomposition

적용 대상 예:

- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `templates/partials/erp_beta_js.html`
- `templates/layout.html`

필수 규칙:

- Jinja → JS 직접 주입은 future split에서 config node/`data-*`/safe parse contract로 먼저 치환한다.
- DOM id/class/data attribute, include chain, script load order는 public surface다.
- inline JS를 static JS로 옮길 때는 thin wrapper/template shell을 남겨 caller path를 유지한다.
- automated coverage가 얕은 경우 batch별 manual checklist를 run record에 포함한다.

### 5.3 CSS monolith decomposition

적용 대상 예:

- `static/css/erp-pro.css`
- `static/css/style.css`
- template-embedded style blocks

필수 규칙:

- logical split(토큰/레이아웃/컴포넌트/페이지)과 selector rename을 분리한다.
- 첫 split batch에서는 selector name/semantic change 없이 file organization만 바꾼다.
- style를 template에서 static asset으로 옮길 때는 적용 순서와 specificity drift를 확인한다.

### 5.4 Canonical `foms/services/*` hotspot decomposition

적용 대상 예:

- `foms/services/erp_policy.py`
- `foms/services/storage.py`
- `foms/services/channel_wam_service.py`

필수 규칙:

- canonical path churn보다 **internal package split**을 우선한다.
- external caller import path는 가능하면 유지하고, package `__init__`로 bridge한다.
- canonical service split과 caller cleanup을 같은 배치에 과도하게 섞지 않는다.

## 6. Contract Freeze Baseline

future decomposition batch 시작 전 최소 요구사항:

- `python -m pytest -q` 또는 승인된 subset
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- touched path에 대한 focused contract tests
- template/JS candidate는 필요 시 manual smoke checklist

candidate별 추가 요구:

- `orders.py`: `/api/orders`, `/api/orders/nearby`, `update_order_field`, status/bulk status contract
- `wdcalculator_scripts.html`: config data injection, save/load/estimate sidebar flow
- `erp_beta_js.html`: `ORDER_ID`, `ERP_BETA_ENABLED`, `window.__ERP_*`, attachment/payment UI contract
- `layout.html`: notification badge, socket bootstrap, global panel DOM id contract

## 7. Stop Conditions

다음 중 하나라도 발생하면 decomposition batch를 즉시 중단하고 별도 plan/ADR로 분리한다.

- schema/Alembic 변경이 필요해짐
- persistence contract(`models.py`, DB session lifecycle, WDCalculator DB lifecycle) 변경이 필요해짐
- 하나의 batch 안에서 여러 도메인 split이 섞이기 시작함
- wrapper/shim 없이 기존 public path를 깨야 함
- automated/manual contract evidence 없이 behavior 변경이 불가피함

## 8. Wave Priority

### Wave A

- `apps/api/orders.py`
- `templates/wdcalculator/partials/wdcalculator_scripts.html`
- `templates/partials/erp_beta_js.html`

### Wave B

- `apps/api/chat/routes.py`
- `foms/services/erp_policy.py`
- `apps/api/wdcalculator.py`
- `apps/api/attachments.py`
- `apps/api/erp_map.py`
- `static/css/erp-pro.css`

### Wave C

- `apps/api/events.py`
- `apps/api/notifications.py`
- `templates/layout.html`
- `templates/regional_dashboard.html`
- `templates/partials/erp_dashboard_styles.html`
- `static/js/measurement/dashboard.js`
- `static/js/wam/attachments.js`
- `static/css/style.css`

## 9. Approval Gate

future decomposition은 다음 순서로만 진행한다.

1. inventory row 확정
2. batch-specific execution plan 작성
3. contract freeze/test baseline 확보
4. 구조-only execution
5. post-audit
6. 상태 문서 갱신

## 10. 해석

- Step 6로 large-file decomposition은 이제 “즉흥 리팩터링”이 아니라 별도 spec 기반 작업이 됐다.
- root governance spec은 상위 단계와 자동 next step만 유지하고, large-file execution rule은 이 문서가 담당한다.
- `business_calendar` / `/calendar` 축은 이 spec에서도 계속 제외 대상이다.
