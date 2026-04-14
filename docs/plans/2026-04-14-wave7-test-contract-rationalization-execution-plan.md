# Wave 7 Test / Contract Rationalization Execution Plan
> 작성일: 2026-04-14 | 상태: 초안 (감리 전)
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `tests/`, `tests/support/`, `tests/harness/`, `tests/test_foms_namespace_imports.py`, `tests/test_app_bootstrap_contract.py`
> 선행 wave: `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md`
> 핵심 선례: `docs/plans/2026-04-10-step4-batch55-bootstrap-contract-freeze-run-record.md`, `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`, `tests/harness/test_hooks_smoke.py`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 7 — Test / contract rationalization**을 실제로 집행할 수 있는 LLM용 runbook이다.

헤더의 `상태`는 plan maturity를 뜻한다. live execution phase(`W7-B0` gating 중, partial closeout, full closeout)는 헤더가 아니라 해당 run record와 closeout 문서가 authoritative truth다.

Wave 7의 목적은 "테스트도 나중에 정리하자" 수준의 선언이 아니라, 아래 일곱 가지를 기계적으로 닫는 것이다.

1. live `tests/` tree를 다시 읽고 **runtime anchor / chunk contract / domain contract / harness contract** 네 레벨로 authoritative queue를 잠근다.
2. `tests/README.md`를 test taxonomy entrypoint로 만들고, `tests/contracts`, `tests/domains`, `tests/harness`, `tests/fixtures`, `tests/support`의 목표 역할을 고정한다.
3. `tests/test_foms_namespace_imports.py`와 `tests/test_app_bootstrap_contract.py`를 **runtime anchor family**로 재정렬하되, Wave 8 bridge retirement를 조기 실행하지 않고 legacy-vs-canonical parity coverage를 보존한다.
4. WDCalculator의 `tests/support/*` + `test_*_contract_node.py` micro pair 증식을 그대로 두지 않고, **`composition` + `primary-form`** canonical chunk 기준으로 chunk-level contract surface를 만든다.
5. `estimate-lifecycle`, `pricing-core`, measurement/domain suite, bridge-coupled domain tests는 mainline에서 억지로 다 건드리지 않고 **status register / defer register**로 잠근다.
6. structure-only batch에서도 `product / wrapper / test delta`를 남기고, 새 support/test file이 늘면 반드시 same-batch 제거 대상과 증가 이유를 같이 기록한다.
7. 문서 최종 감리 루프 자체도 무한 반복으로 흐르지 않게, **parallel audit hard-stop policy**를 문서 안에 명시한다.

### 1.2 기능 요구사항
1. Wave 7의 authoritative truth는 항상 live `tests/` tree, accepted predecessor evidence, `tests/test_foms_namespace_imports.py`, `tests/test_app_bootstrap_contract.py`, `tests/harness/*`, WDCalculator canonical chunk 상태다.
2. Wave 7는 **test / contract rationalization**이다. product canonicalization(Wave 3~6)이나 bridge retirement(Wave 8)를 본편으로 포함하면 안 된다.
3. 한 batch는 반드시 **한 contract tier / 한 pilot family / 한 support-layout axis**만 다룬다.
4. `tests/README.md`는 Wave 7의 local entrypoint다. taxonomy, 금지 규칙, pilot family, defer family를 같은 entrypoint에서 찾아야 한다.
5. contract tier는 `runtime anchor`, `chunk contract`, `domain contract`, `harness contract` 네 개만 허용한다.
6. `runtime anchor`는 `tests/test_foms_namespace_imports.py`, `tests/test_app_bootstrap_contract.py`, 그리고 이 둘의 직접적인 import-surface smoke만 뜻한다. domain regression, bridge retirement, product behavior regression을 여기에 섞지 않는다.
7. `chunk contract` mainline pilot은 **WDCalculator `composition` + `primary-form`**만 허용한다. `estimate-lifecycle`, `pricing-core`는 별도 승격 전까지 defer다.
8. 새 `tests/support/*` + `test_*_contract_node.py` pair는 기본적으로 금지다. Wave 7에서 새 pair를 만들려면 기존 chunk contract로 흡수할 수 없는 이유를 same-batch run record에 남겨야 한다.
9. 새 chunk contract를 만들 때 기본 판단 순서는 `reuse -> merge -> parameterize -> add`다. 새로운 파일을 가장 마지막 선택지로 둔다.
10. structure-only batch라도 **test file count가 순감 또는 최소 동결**되는 방향을 기본값으로 삼는다. 순증가가 필요하면 same-batch 제거 대상, 제거 wave, 증가 이유를 반드시 남긴다.
11. WDCalculator Node contract rationalization은 동일한 subprocess wrapper를 복제하는 대신 shared runner 또는 parametrized entrypoint를 우선 검토한다.
12. Wave 7는 legacy import path assertion을 함부로 버리지 않는다. root `services/` 또는 `apps/` bridge가 살아 있는 동안 해당 parity assertion은 coverage surface로 남는다.
13. `tests/test_foms_namespace_imports.py`를 잘게 나누더라도 **legacy-vs-canonical import parity**와 `db/models/app bootstrap` public contract smoke는 coverage에서 빠지면 안 된다.
14. `tests/harness/*`는 Wave 7의 mainline pilot이 아니라 **already aligned precedent**다. harness infra까지 넓히는 순간 scope bleed로 본다.
15. Wave 7 code batch는 기본적으로 `tests/`와 `docs/`만 수정한다. `services/`, `apps/`, `foms/`, `static/`, `templates/`, `tools/harness/`는 freeze다.
16. WDCalculator code pilot은 `node`가 PATH에 있어야 한다. `skipif` 때문에 green으로 보이는 상태를 mainline success로 간주하지 않는다.
17. `W7-B0`는 actual execution 시작 전에 Wave 5 current state를 다시 읽고 `composition` + `primary-form`이 둘 다 pilot-ready인지 재잠가야 한다.
18. `tests/contracts`, `tests/domains`, `tests/harness`, `tests/fixtures`, `tests/support`는 target taxonomy다. live tree는 same-batch import/update evidence 없이 big-bang move하지 않는다.
19. predecessor closeout file이 없다고 해서 self-waive하지 않는다. `W7-B0` run record에 `equivalent evidence accepted/rejected`를 명시해야 한다.
20. final plan audit loop는 `§11` hard-stop policy를 따른다. `HIGH = 0`만으로 round 1에서 즉시 종료하지 않으며, 실제 종료 기준은 `§11.5`~`§11.9`를 우선한다.

### 1.2.1 FR / shorthand definitions
- `TR1`: `1 chunk = 1 contract surface` 원칙이다. tiny helper마다 별도 pytest/support pair를 만들지 않는다.
- `TR2`: `reuse -> merge -> parameterize -> add`다. 새 test/support file 추가는 마지막 선택지다.
- `TR3`: `anchor-preserve`다. runtime anchor rationalization은 파일을 쪼개더라도 legacy-vs-canonical parity coverage를 줄이면 실패다.
- `TR4`: `micro-pair-budget`다. 새 `tests/support/*` + `test_*_contract_node.py` pair는 기본적으로 금지다.
- `TR5`: `runner-shared-first`다. 동일한 Node subprocess wrapper가 2개 이상 반복되면 shared helper/parametrization을 먼저 검토한다.
- `TR6`: `bridge-aware`다. legacy bridge가 남아 있으면 그에 대응하는 test assertion도 살아 있어야 한다. Wave 7는 이를 없애는 wave가 아니다.
- `TR7`: `tier-lock`다. runtime anchor / chunk contract / domain contract / harness contract는 서로 다른 owner와 목적을 가진다. 한 파일에 여러 tier를 뒤섞지 않는다.
- `TR8`: `pilot-cap`이다. Wave 7 mainline code pilot은 `runtime anchor family`와 `WDCalculator composition + primary-form` 두 축만 허용한다.
- `TR9`: `family-net-zero`다. runtime anchor rationalization은 family-level `tests/*.py` count를 기본적으로 순감 또는 동결해야 한다. 예외적으로 `+1`만 허용되며, 그 경우 giant source file이 thin aggregator(`80` lines 이하 권장)로 줄고 helper/support 순증가가 없어야 한다.

### 1.3 Out of scope / freeze
Wave 7에서는 아래를 건드리지 않는다.

- `services/`, `apps/`, `foms/` product source
- `static/js/`, `templates/`, `foms/platform/blueprints.py`
- route path, blueprint registration, API response shape
- DB schema, Alembic, persistence lifecycle
- worker/bootstrap/chat/socketio/runtime registration
- Wave 5 product canonical chunk merge 자체
- Wave 8 수준의 root shim / `apps/` thin bridge 제거
- `tools/harness/` runtime code 또는 harness policy 문서 개편
- packaging reopen (`src/foms`, `pyproject` hardening)

Wave 7은 **test taxonomy lock + runtime anchor rationalization + WDCalculator selected chunk-contract rationalization + status register + Wave 8 handoff**까지만 담당한다.

추가 규칙:

- 어떤 batch라도 product code 수정이 필요해지는 순간 out-of-scope로 판단하고 즉시 stop/defer한다.
- 어떤 batch라도 legacy import path assertion을 삭제해야만 green이 나온다면 Wave 8 bleed로 보고 stop한다.
- 어떤 batch라도 `estimate-lifecycle` 또는 `pricing-core` product chunk가 필요해지는 순간 mainline WDCalculator pilot에서 제외한다.

### 1.4 Scope reconciliation — Wave 5 / Wave 6 / Wave 8과의 정합
이 계획은 Wave 5 product chunk canonicalization을 다시 열거나, Wave 8 bridge retirement를 조기 실행하는 문서가 아니다. 해석은 아래로 고정한다.

1. Wave 5는 WDCalculator product JS를 `composition`, `primary-form`, `estimate-lifecycle`, `pricing-core` canonical chunk로 수렴시키는 wave다.
2. Wave 7는 그중 **실제로 완료되어 live tree에서 안정화된 canonical chunk**에 대해서만 chunk-level contract를 rationalize한다.
3. 따라서 `estimate-lifecycle`, `pricing-core`가 설계상 target tree에 있더라도, `W7-B0` 시점에 live evidence가 약하거나 active product churn이 있으면 defer row로 남긴다.
4. Wave 6는 test rationalization을 intentionally defer했다. 특히 `tests/test_foms_namespace_imports.py`의 구조적 재설계와 suite-wide rationalization은 Wave 7 소관이다.
5. Wave 8은 bridge retirement wave다. root `services/` 또는 `apps/` thin bridge가 사라질 때까지 Wave 7는 해당 legacy-path coverage를 유지한다.
6. `tests/harness/*`는 이미 harness tier precedent가 있으므로, Wave 7는 taxonomy 정렬과 closeout reference까지만 하고 harness infra를 재설계하지 않는다.
7. predecessor run record에서 Wave 7를 막연히 "test cleanup" 정도로 넓게 부르더라도, 본 계획이 authoritative override다. Wave 7는 product/source change, bridge retirement, harness infra rewrite를 포함하지 않는다.
8. controlling spec의 `Wave 7`과 본 계획의 `Wave 7`은 같은 작업 축이다. predecessor artifact와 충돌이 나면 controlling spec과 본 계획이 우선이고, 그 외 문서는 consume-only evidence다.

## 2. Current Test Truth — 현재 테스트 landscape

### 2.1 선행 handoff gate
Wave 7 actual execution은 아래 산출물을 소비한 뒤에만 시작한다.

1. `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
2. `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md`
3. `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
4. `docs/plans/2026-04-14-wave5-batch2-wdcalculator-composition-run-record.md`
5. `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md`
6. `docs/AI_STATUS.md` 또는 accepted Wave 5 execution-state memo
7. Wave 6 closeout/status evidence (`docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md`, `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md`) 또는 accepted equivalent evidence
8. live `tests/test_foms_namespace_imports.py`, `tests/test_app_bootstrap_contract.py`, `tests/harness/*`
9. live `tests/test_*_contract_node.py`, `tests/support/*contract_node_checks.js`

추가 규칙:

- predecessor closeout file이 실제로 없어도 본 문서는 drafted plan으로 존재할 수 있다.
- actual execution에서 Wave 6 closeout/status file이 없으면 `W7-B0` run record 안에 `equivalent evidence accepted` 또는 `equivalent evidence rejected`를 명시적으로 남긴다.
- Wave 6 dedicated handoff artifact가 없으면 `W7-B0` run record 안에 `Wave 6 -> Wave 7 consumed defer manifest` section을 반드시 만든다. 이후 batch는 이 section 또는 dedicated artifact를 동일 truth source로 사용한다.
- Wave 6 equivalent evidence 최소 계약:
  - `foms/services/README.md`의 최신 status summary
  - latest completed Wave 6 run record 묶음
  - Wave 7로 넘어오는 test debt / Wave 8로 넘어오는 bridge debt 요약
  - 현재 live `tests/test_foms_namespace_imports.py` import surface와의 정합 메모
- Wave 5 equivalent evidence 최소 계약:
  - 작성 시점
  - 완료된 batch 목록
  - 현재/마지막 시도 batch
  - `composition` / `primary-form` actual file 상태
  - verification 상태
  - 다음 batch handoff
- predecessor evidence와 live `tests/` tree가 충돌하면 live tree를 truth로 두고 drift를 `W7-B0` run record에 먼저 기록한다.

### 2.2 Contract tier / queue class 판정 규칙
Wave 7는 test family를 아래 두 축으로만 다룬다.

| 축 | 값 | 의미 |
|------|------|------|
| `contract tier` | `runtime anchor` | namespace parity, app bootstrap public contract, import-surface smoke |
| `contract tier` | `chunk contract` | canonical chunk 하나에 대응하는 contract surface |
| `contract tier` | `domain contract` | route/page/service/domain behavior regression |
| `contract tier` | `harness contract` | `tests/harness/*`가 `tools/harness` semantics를 lock하는 test family. Wave 7는 `tools/harness/`를 수정하지 않는다. |
| `queue class` | `mainline-pilot` | Wave 7 code batch 대상 |
| `queue class` | `already aligned precedent` | Wave 7에서 reference/status only |
| `queue class` | `active-product-coupled defer` | product canonicalization 완료 전 code batch 금지 |
| `queue class` | `bridge-coupled defer` | Wave 8 bridge retirement와 강하게 엮여 Wave 7 mainline code batch 금지 |
| `queue class` | `high-risk suite defer` | 범위가 넓거나 cross-domain이라 mainline code batch 금지 |
| `execution state` | `completed` | 해당 row가 Wave 7에서 실제로 닫힘 |
| `execution state` | `not started` | touched되지 않음 |
| `execution state` | `partial` | docs freeze 또는 partial code/defer까지만 완료 |

보조 판정 규칙:

1. legacy-vs-canonical import parity를 직접 다루면 `runtime anchor`다.
2. 하나의 canonical product chunk에만 대응하면 `chunk contract`다.
3. `apps.*`, legacy route, page behavior, domain workflow를 주로 다루면 `domain contract`다.
4. `tests/harness/*`가 `tools/harness` semantics를 고정하면 `harness contract`다. Wave 7는 harness test를 읽고 검증할 수는 있지만 `tools/harness/` 코드를 수정하지 않는다.
5. `mainline-pilot`은 product code 수정 없이 **test-side rationalization만으로 순감 또는 명확한 재정렬**이 가능한 family에만 허용한다.
6. `node` availability, live chunk map, predecessor evidence가 없으면 WDCalculator family는 `mainline-pilot`으로 승격하지 않는다.
7. bridge 제거가 없으면 단순히 legacy-path assertion이 지저분하다는 이유만으로 `bridge-coupled defer`를 `mainline-pilot`으로 바꿀 수 없다.

### 2.3 현재 queue snapshot
이 표는 provisional snapshot이다. future LLM은 그대로 복사하지 말고 `W7-B0`에서 live evidence로 다시 잠가야 한다.

| Family | Live truth | Contract tier | Provisional queue class | 비고 |
|------|------|------|------|------|
| runtime-anchor | `tests/test_foms_namespace_imports.py`, `tests/test_app_bootstrap_contract.py` | `runtime anchor` | `mainline-pilot` | 가장 먼저 rationalize |
| wdcalculator-composition-primary-form | 53개 WDCalculator Node micro pair 중 `composition`/`primary-form`에 대응하는 subset | `chunk contract` | `mainline-pilot` | Wave 7 second pilot |
| wdcalculator-estimate-lifecycle-pricing-core | WDCalculator Node micro pair 중 나머지 chunk target | `chunk contract` | `active-product-coupled defer` | Wave 5 후속/추가 prep 필요 |
| harness | `tests/harness/*` | `harness contract` | `already aligned precedent` | mainline pilot 아님 |
| measurement-contract-family | `test_measurement_*`, JS/slice/legacy shim family | `domain contract` | `high-risk suite defer` | scope 큼 |
| orders-api-bridge-family | `test_orders_boundary_contract.py` 및 `apps.api.*` thin bridge 결합 family | `domain contract` | `bridge-coupled defer` | Wave 8 owner 강함 |

### 2.4 Pilot tie-break / lock 규칙
1. first executable pilot은 항상 `runtime-anchor`다.
2. second executable pilot은 항상 `wdcalculator-composition-primary-form`이다.
3. `estimate-lifecycle`, `pricing-core`, measurement, orders-api bridge family는 mainline에서 위 두 pilot을 앞지를 수 없다.
4. `node`가 없거나 `composition`/`primary-form` live chunk evidence가 stale이면 second pilot은 자동 승격되지 않고 defer된다.
5. harness family는 taxonomy precedent로만 소비한다. mainline에서 harness code batch를 새로 열지 않는다.
6. `W7-B0`가 first pilot(runtime-anchor)을 lock하지 못하면 mainline은 즉시 `Branch C` docs-only partial closeout 경로로 내려간다.

## 3. Fixed Execution Pipeline — 고정 배치 순서
Wave 7 mainline은 아래 순서를 기본값으로 한다.

1. `W7-B0` — Readiness gate + authoritative test queue lock
2. `W7-B1` — Test taxonomy + `tests/README.md` freeze
3. `W7-B2` — Runtime anchor contract freeze
4. `W7-B3` — Runtime anchor rationalization
5. `W7-B4` — WDCalculator chunk-contract freeze
6. `W7-B5` — WDCalculator `composition` + `primary-form` contract rationalization
7. `W7-B6` — Test status register
8. `W7-B7` — Closeout + Wave 8 handoff

branch semantics:

- `Branch A` full mainline: `W7-B0 -> W7-B1 -> W7-B2 -> W7-B3 -> W7-B4 -> W7-B5 -> W7-B6 -> W7-B7`
- `Branch B` runtime-only path: `W7-B0 -> W7-B1 -> W7-B2 -> W7-B3 -> W7-B6 -> W7-B7`
- `Branch C` docs-only partial closeout: `W7-B0 -> W7-B1 -> W7-B6 -> W7-B7`
- `runtime-anchor-freeze-stop` post-B2 path: `W7-B0 -> W7-B1 -> W7-B2(partial/failed) -> W7-B6 -> W7-B7`
- `wdcalculator-freeze-stop` post-B4 path: `W7-B0 -> W7-B1 -> W7-B2 -> W7-B3 -> W7-B4(partial/blocked) -> W7-B6 -> W7-B7`
- `wdcalculator-b5-revert-stop` post-B5 path: `W7-B0 -> W7-B1 -> W7-B2 -> W7-B3 -> W7-B4 -> W7-B5(revert-to-pre-B5-tree) -> W7-B6 -> W7-B7`

## 4. Batch Catalog

| Batch | 이름 | 성격 | 핵심 산출물 | 선행 조건 | 대표 run record |
|------|------|------|------|------|------|
| `W7-B0` | Readiness gate + queue lock | docs / gate | accepted predecessor evidence, branch choice, live counts, queue snapshot | 선행 evidence 수집 | `docs/plans/2026-04-14-wave7-batch0-readiness-gate-run-record.md` |
| `W7-B1` | Test taxonomy + entrypoint freeze | docs | `tests/README.md`, tier rules, pair-budget, pilot/defer map | `W7-B0` | `docs/plans/2026-04-14-wave7-batch1-test-taxonomy-run-record.md` |
| `W7-B2` | Runtime anchor contract freeze | docs | runtime anchor split plan, max file budget, parity-preserve rules | `W7-B1` | `docs/plans/2026-04-14-wave7-batch2-runtime-anchor-freeze-run-record.md` |
| `W7-B3` | Runtime anchor rationalization | code / runtime anchor | tiered runtime anchor tests, reduced giant-file burden, preserved old path compatibility if needed | `W7-B2` | `docs/plans/2026-04-14-wave7-batch3-runtime-anchor-rationalization-run-record.md` |
| `W7-B4` | WDCalculator chunk-contract freeze | docs | `composition`/`primary-form` mapping, removal list, file budget | `Branch A` + `W7-B3` | `docs/plans/2026-04-14-wave7-batch4-wdcalculator-chunk-freeze-run-record.md` |
| `W7-B5` | WDCalculator composition + primary-form rationalization | code / chunk contract | chunk-level Node contract files, micro pair reduction, README update | `W7-B4` | `docs/plans/2026-04-14-wave7-batch5-wdcalculator-chunk-contracts-run-record.md` |
| `W7-B6` | Test status register | docs / handoff | pilot/defer register, restart conditions, Wave 8 owner map | Branch A/B/C 공통 | `docs/plans/2026-04-14-wave7-batch6-status-register-run-record.md` |
| `W7-B7` | Closeout + Wave 8 handoff | docs / closeout | full/partial closeout, spec/archive update, next continuation order | `W7-B6` | `docs/plans/2026-04-14-wave7-batch7-closeout-run-record.md` |

## 5. Batch Runbook — 배치별 실행 규칙
`§5`의 각 검증 블록은 최소 subset만 적는다. 실제 배치 완료 판정은 항상 `§7 Run Record Contract` 전체(특히 Direction Lock 10문항 포함)를 함께 만족해야 한다.

### 5.1 W7-B0 — Readiness gate + authoritative test queue lock
**목표**
- predecessor evidence, live `tests/` tree, WDCalculator chunk readiness를 다시 잠근다.
- `Branch A/B/C`를 명시적으로 판정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave7-batch0-readiness-gate-run-record.md`

**금지 변경**
- runtime code
- test file rename/move
- README/spec/archive update

**실행 단계**
1. `§2.1`의 predecessor evidence를 exact path 기준으로 다시 연다.
2. Wave 6 closeout/status file이 없으면 equivalent evidence를 평가하고 `accepted/rejected`를 명시한다.
3. live `tests/` tree snapshot을 아래 항목으로 남긴다.
   - `test_*_contract_node.py` file count
   - `tests/support/*contract_node_checks.js` file count
   - `tests/test_foms_namespace_imports.py` line count 또는 section count
   - `tests/harness/*` representative file list
4. live runtime-anchor readiness를 아래 checklist로 잠근다.
   - `tests/test_foms_namespace_imports.py`와 `tests/test_app_bootstrap_contract.py`가 current tree에 존재
   - same-session fresh baseline 또는 documented current failure 상태가 있음
   - current tree가 runtime-anchor file rename/move 중간 상태가 아님
5. live WDCalculator chunk readiness를 아래 checklist로 잠근다.
   - `static/js/wdcalculator/composition.js` 존재 + accepted Wave 5 B2 evidence
   - `static/js/wdcalculator/primary-form.js` 존재 + accepted Wave 5 B3 evidence
   - accepted Wave 5 state memo에 두 chunk가 active in-progress로 표시되지 않음
   - `node` on PATH
6. provisional queue snapshot을 `contract tier`, `queue class`, `execution state = not started` 기준으로 적는다.
7. branch를 아래 규칙으로 판정한다.
   - `Branch A`: predecessor accepted + runtime anchor stable + `composition`/`primary-form` stable + `node` available
   - `Branch B`: predecessor accepted + runtime anchor stable + `§8.3`의 early WDCalculator gate-block 조건 충족
   - `Branch C`: `§8.1`의 readiness-gate-rejected 조건 충족
8. `next legal batch`를 명시한다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- live count snapshot completeness 확인
- branch reason one-line summary

### 5.2 W7-B1 — Test taxonomy + entrypoint freeze
**목표**
- `tests/README.md`를 Wave 7 local entrypoint로 만든다.
- contract tier, queue class, pair-budget, no-go boundary를 고정한다.

**허용 변경**
- `tests/README.md`
- `docs/plans/2026-04-14-wave7-batch1-test-taxonomy-run-record.md`

**금지 변경**
- actual test code movement
- product source

**실행 단계**
1. `tests/README.md`가 없으면 새로 만들고, 있으면 append가 아니라 authoritative rewrite로 정리한다.
2. 아래 항목을 entrypoint에 고정한다.
   - contract tier definitions
   - queue class definitions
   - mainline pilot family
   - defer family
   - `TR1`~`TR9` shorthand
   - 새 micro pair 금지 규칙
3. target taxonomy를 `tests/contracts`, `tests/domains`, `tests/harness`, `tests/fixtures`, `tests/support`로 적되, live move는 same-batch evidence 없이는 하지 않는다고 명시한다.
   - README에는 `target taxonomy`와 `currently applied in live tree`를 구분해서 적는다. Branch B/C 또는 defer 상태에서 target shape를 곧바로 live tree truth처럼 쓰면 안 된다.
4. `Branch B/C`에서도 `tests/README.md`는 최소한 유지한다.

**검증**
- `tests/README.md`에 runtime anchor / chunk / domain / harness 구분이 있는지 확인
- `tests/README.md`에 `composition` + `primary-form` pilot 제한이 적혀 있는지 확인
- Direction Lock 10문항 yes/no + 한 줄 근거

### 5.3 W7-B2 — Runtime anchor contract freeze
**목표**
- giant `tests/test_foms_namespace_imports.py`를 어떤 shape로 rationalize할지 먼저 docs로 잠근다.
- parity-preserve boundary를 명시한다.

**허용 변경**
- `tests/README.md` (runtime anchor section 보강)
- `docs/plans/2026-04-14-wave7-batch2-runtime-anchor-freeze-run-record.md`

**금지 변경**
- actual runtime anchor test code
- new domain/harness pilot 시작

**실행 단계**
1. current `tests/test_foms_namespace_imports.py`를 아래 surface로 분류한다.
   - service namespace parity
   - persistence parity (`db`, `models`)
   - packaged precedent/import-surface smoke (`jobs`, `erp_policy` 등)
2. `tests/test_app_bootstrap_contract.py`는 runtime anchor family 안에서 keep/separate/merge 방향을 docs로 잠근다.
3. target shape를 아래 제한으로 잠근다.
   - 최대 2개의 substantive runtime-anchor target file
   - 최대 1개의 shared matrix/fixture helper
   - `tests/test_foms_namespace_imports.py`와 `tests/test_app_bootstrap_contract.py`는 delete보다 thin aggregator/collector 우선 검토
4. runtime-anchor family-level file count rule을 잠근다.
   - preferred: `tests/*.py` family net count `<= 0`
   - exceptional allowance: net `+1`까지만 허용
   - exceptional allowance를 쓰면 `TR9` 조건(thin aggregator, no helper/support net growth)을 run record에 같이 남긴다
   - `family net count`는 runtime-anchor family가 소유하는 substantive file, thin collector/aggregator, shared matrix/helper를 모두 포함해 계산한다.
5. old giant file을 없애더라도 parity coverage가 줄지 않는다는 증거 전략을 적는다.
6. 아래 stop rule을 함께 잠근다.
   - legacy-vs-canonical parity assertion 축소 필요
   - `services/`/`apps/`/`foms/` source 수정 필요
   - bridge retirement 가정 필요

**검증**
- target file budget 명시 여부
- keep/remove/aggregator decision 명시 여부
- parity-preserve rule 명시 여부

### 5.4 W7-B3 — Runtime anchor rationalization
**목표**
- giant runtime anchor test surface를 더 읽기 쉬운 구조로 옮기되, old command compatibility와 parity coverage를 함께 보존한다.

**허용 변경**
- `tests/test_foms_namespace_imports.py`
- `tests/test_app_bootstrap_contract.py`
- `tests/contracts/runtime/*` 또는 `W7-B2`에서 freeze한 exact target files
- `tests/fixtures/*` 중 runtime anchor shared matrix/helper 1개 이하
- `tests/README.md`
- `docs/plans/2026-04-14-wave7-batch3-runtime-anchor-rationalization-run-record.md`

**금지 변경**
- product source
- legacy import assertion 삭제
- bridge retirement 성격의 coverage 제거

**실행 단계**
1. `W7-B2`에서 잠근 target shape 외의 새 runtime test file을 만들지 않는다.
2. repeated import/assert table이 있으면 shared matrix/helper로 올리되, 그 helper는 runtime anchor family 전용이어야 한다.
3. `tests/test_foms_namespace_imports.py`를 아래 둘 중 하나로 수렴시킨다.
   - thin compatibility aggregator
   - reduced top-level collector with imported tiered tests
4. `tests/test_app_bootstrap_contract.py`는 same-batch에서 thin collector 또는 target substantive file로 정리한다.
5. `tests/README.md` runtime anchor section을 실제 파일 구조로 갱신한다.
6. run record에 old/new file delta와 reduced giant-file burden 근거를 남긴다.
7. `TR9` exceptional allowance를 썼다면 old giant file의 thin-aggregator line count와 helper/support 순증가 없음 여부를 수치로 남긴다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/test_foms_namespace_imports.py tests/test_app_bootstrap_contract.py -q`
- `python -m pytest tests --collect-only -q`
- touched file diagnostics/lint (`ReadLints` 또는 동등 진단)

### 5.5 W7-B4 — WDCalculator chunk-contract freeze
**목표**
- WDCalculator micro pair를 어떤 기준으로 `composition` / `primary-form` chunk contract에 접을지 먼저 docs로 잠근다.

**허용 변경**
- `tests/README.md` (WDCalculator section 보강)
- `docs/plans/2026-04-14-wave7-batch4-wdcalculator-chunk-freeze-run-record.md`

**금지 변경**
- actual WDCalculator Node test code
- `estimate-lifecycle` / `pricing-core` 승격
- product JS 수정

**실행 단계**
1. `W5-B2`, `W5-B3` run record와 live `composition.js`, `primary-form.js`, `wdcalculator_scripts_config.html`를 다시 연다.
2. current WDCalculator micro pair를 아래 분류로 잠근다.
   - merge-into-composition
   - merge-into-primary-form
   - defer-estimate-lifecycle
   - defer-pricing-core
   - defer-legacy-unmapped
3. code batch file budget을 아래 제한으로 잠근다.
   - `tests/contracts/wdcalculator/test_composition_contracts.py`
   - `tests/contracts/wdcalculator/test_primary_form_contracts.py`
   - `tests/contracts/wdcalculator/_node_runner.py` (optional, 1개 이하)
   - `tests/support/wdcalculator/composition_contract_checks.js`
   - `tests/support/wdcalculator/primary_form_contract_checks.js`
4. default representative page smoke는 `tests/test_wdcalculator_product_settings.py`로 잠근다. 이 경로가 live tree에 없거나 역할이 더 넓다면, exact replacement path를 same run record에 고정한다.
5. same-batch removal list를 exact path 기준으로 잠근다.
6. B0에서 잠근 early gate와 B4에서 새로 확인한 late freeze blocker를 구분한다.
   - `node` 부재 또는 `composition`/`primary-form` readiness drift가 B4 시점에 다시 발견되면 `W7-B5`는 열지 않고 `W7-B4`를 partial/blocked로 닫은 뒤 `wdcalculator-freeze-stop` 경로로 내려간다. `Branch B`는 B0 early gate 전용이다.
   - actual removal list가 `estimate-lifecycle` 또는 `pricing-core` family를 요구하거나 product JS touch 없이는 닫히지 않으면 `W7-B5`를 열지 않고 `wdcalculator-freeze-stop` 경로로 내려간다.

**검증**
- file budget 명시 여부
- exact removal list 명시 여부
- defer row 명시 여부
- `node` availability snapshot 기록 여부

### 5.6 W7-B5 — WDCalculator composition + primary-form contract rationalization
**목표**
- `composition` + `primary-form`에 대응하는 WDCalculator micro pair를 chunk-level contract surface로 접는다.
- 1:1 pytest wrapper + JS support proliferation을 줄인다.

**허용 변경**
- `tests/contracts/wdcalculator/test_composition_contracts.py`
- `tests/contracts/wdcalculator/test_primary_form_contracts.py`
- `tests/contracts/wdcalculator/_node_runner.py` (optional, 1개 이하)
- `tests/support/wdcalculator/composition_contract_checks.js`
- `tests/support/wdcalculator/primary_form_contract_checks.js`
- `tests/README.md`
- `docs/plans/2026-04-14-wave7-batch5-wdcalculator-chunk-contracts-run-record.md`
- `W7-B4` removal list에 들어간 old WDCalculator micro pair files

**금지 변경**
- `estimate-lifecycle` / `pricing-core` family
- product JS
- 새 1:1 micro pair 추가

**실행 단계**
1. `tests/contracts/wdcalculator/`와 `tests/support/wdcalculator/` target path를 same-batch에서 실제로 만든다. 경로가 없던 pre-B5 상태는 실패가 아니라 미시작 상태다.
2. repeated Node subprocess wrapper는 shared helper 또는 parametrized runner로 수렴시킨다.
3. `composition` target JS support script는 startup/bootstrap/order/load-order band만 다룬다.
4. `primary-form` target JS support script는 base-components/notes/coupon/additional-options/catalog band만 다룬다.
5. `tests/test_wdcalculator_product_settings.py`가 live tree에 없거나 더 넓은 unfinished chunk까지 묶고 있으면, `W7-B4`에서 잠근 replacement smoke path를 사용한다. replacement smoke path를 잠그지 못했으면 B5 substantive edit를 시작하지 말고 `W7-B4` freeze failure로 간주해 `wdcalculator-freeze-stop` 경로로 내려간다. 만약 substantive edit를 이미 시작한 뒤 이 문제가 드러나면 `§5.6.9` / `§8.5`에 따라 same-batch full revert 후 `wdcalculator-b5-revert-stop`으로 닫는다.
6. old micro pair handling은 `W7-B4` exact removal list 기준으로 binary다.
   - exact removal list에 포함된 old micro pair path는 same-batch에서 삭제가 필수다.
   - exact removal list path를 삭제할 수 없으면 `exact why-not-now + next batch`로 carry-forward하지 말고 `§5.6.9` / `§8.5`에 따라 same-batch full revert to pre-B5 tree로 내려간다.
   - exact removal list 밖의 old micro pair path는 B5에서 건드리지 않고 defer register로만 넘긴다.
7. `estimate-lifecycle`, `pricing-core`, unmapped legacy pair는 건드리지 않고 defer register로 넘긴다.
8. README에 chunk-contract map과 removed micro pair summary를 적는다.
9. partial/failed 상태로 내려갈 때는 new `tests/contracts/wdcalculator/` 또는 `tests/support/wdcalculator/` subtree를 old micro pair removal 대상과 함께 반쯤 남기지 않는다. complete removal map을 닫지 못하면 same-batch full revert to pre-B5 tree가 필수다.
   - B5가 만든/수정한 new WDCalculator contract/support subtree를 되돌리거나 제거한다.
   - B5에서 삭제한 old micro pair file이 있으면 same-batch에서 복구한다.
   - 실제 restoration 없이 `explicit revert-incomplete` 문구만 남기는 것은 invalid다.
   - revert 후 closeout으로 내려갈 때 branch label은 `wdcalculator-b5-revert-stop`으로 고정한다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/contracts/wdcalculator/test_composition_contracts.py tests/contracts/wdcalculator/test_primary_form_contracts.py -q`
- `python -m pytest tests/test_wdcalculator_product_settings.py -q`  # if W7-B4 froze a replacement smoke path, substitute that exact path in the run record
- `python -m pytest tests --collect-only -q`
- `node --version`
- touched file diagnostics/lint (`ReadLints` 또는 동등 진단)

추가 규칙:

- `skipif(not shutil.which("node"))`로 green처럼 보이는 상태는 completion 증거가 아니다. B5 시작 후 `node --version`이 실패하면 same-batch full revert to pre-B5 tree를 수행한 뒤 `wdcalculator-b5-revert-stop`으로 `W7-B6/W7-B7` partial closeout 경로로 내려간다.
- same-batch 제거 수보다 새 substantive file 수가 많아지면 실패다. shared helper 1개 추가는 예외로 허용하지만, 그 경우에도 total micro pair count는 순감이어야 한다.

### 5.7 W7-B6 — Test status register
**목표**
- Wave 7에서 다룬 family와 다루지 않은 family를 authoritative status register로 잠근다.
- Wave 8이 받아야 할 bridge-coupled debt와 Wave 7 후속 continuation을 분리한다.

**허용 변경**
- `tests/README.md`
- `docs/plans/2026-04-14-wave7-batch6-status-register-run-record.md`

**금지 변경**
- runtime code
- new pilot 시작

**실행 단계**
1. `W7-B0` queue snapshot과 latest completed batch run record를 모두 입력으로 소비한다.
2. status register를 아래 세 축으로 잠근다.
   - `contract tier`
   - `queue class`
   - `execution state`
3. 최소 아래 row를 모두 남긴다.
   - runtime-anchor
   - wdcalculator-composition-primary-form
   - wdcalculator-estimate-lifecycle-pricing-core
   - harness
   - measurement-contract-family
   - orders-api-bridge-family
4. 각 row에 `why not now`, `required prep`, `suggested restart batch`, `bridge-coupled yes/no`, `Wave 8 owner`, `micro-pair delta`를 남긴다.
5. `bridge-coupled yes`인 row는 `Wave 8 owner`를 기본값으로 두고, Wave 7이 bridge removal owner가 아님을 명시한다.
6. path별 default execution-state rule을 적용한다.
   - `Branch C`: `runtime-anchor = not started`, `wdcalculator-composition-primary-form = not started`
   - `runtime-anchor-freeze-stop`: `runtime-anchor = partial`, `wdcalculator-composition-primary-form = not started`
   - `Branch B`: `runtime-anchor = completed`, `wdcalculator-composition-primary-form = not started`
   - `wdcalculator-freeze-stop`: `runtime-anchor = completed`, `wdcalculator-composition-primary-form = partial`
   - `wdcalculator-b5-revert-stop`: `runtime-anchor = completed`, `wdcalculator-composition-primary-form = partial`
7. `tests/README.md`에 status summary를 반영한다.

**검증**
- docs-only closeout
- status register completeness
- `tests/README.md` status summary 반영 여부
- Direction Lock 10문항 yes/no + 한 줄 근거

### 5.8 W7-B7 — Closeout + Wave 8 handoff
**목표**
- Wave 7 완료 범위와 미완 범위를 명확히 고정한다.
- Wave 8(bridge retirement)와 후속 test rationalization continuation을 분리해 넘긴다.

**허용 변경**
- `docs/plans/2026-04-14-wave7-batch7-closeout-run-record.md`
- `tests/README.md`
- controlling spec의 참고 자료 섹션 보강
- `docs/ARCHIVE_INDEX.md`
- `docs/AI_STATUS.md`

**금지 변경**
- runtime code
- 새 code pilot

**실행 단계**
1. full closeout인지 partial closeout인지 먼저 선언한다.
2. completed row와 deferred row를 구분한다.
3. Wave 8로 넘길 항목은 오직 `bridge-coupled` row만 적는다.
4. `active-product-coupled defer` row는 Wave 8이 아니라 **후속 Wave 7 continuation (required Wave 5 product prerequisite 충족 후 재시작)**로 적는다.
5. controlling spec Wave 7 bullet 아래에 본 plan file을 authoritative execution runbook으로 연결한다.
6. `docs/ARCHIVE_INDEX.md`에 Wave 7 plan entry를 추가한다.
7. `docs/AI_STATUS.md`에 Wave 7 현재 상태 또는 closeout 결과를 반영한다. 세션 훅이 대신 갱신한다면 run record에 그 사실을 명시한다.
8. next continuation order를 아래 둘 중 하나로 고정한다.
   - full closeout: `Wave 8 bridge retirement planning`
   - partial closeout: blocked family의 `suggested restart batch`

**검증**
- closeout 문서에 `completed / deferred / blocked / next continuation`이 모두 있는지 확인
- spec reference 추가 여부
- archive index entry 추가 여부
- `docs/AI_STATUS.md` 반영 또는 세션 훅 위임 기록 여부

## 6. Verification Matrix — 배치별 검증 규칙
모든 검증 명령은 저장소 루트에서, 동일한 venv/PATH/PowerShell 환경 기준으로 실행한다.

| Batch | `APP_OK` | `verify_result` | focused pytest / node | README / docs check | diagnostics |
|------|------|------|------|------|------|
| `W7-B0` | 필수 | 필수 | live count snapshot + `node` availability check | run record completeness | 선택 |
| `W7-B1` | B0 baseline 재사용 또는 rerun | B0 baseline 재사용 또는 rerun | 없음 | `tests/README.md` completeness | 선택 |
| `W7-B2` | B0 baseline 재사용 또는 rerun | B0 baseline 재사용 또는 rerun | 없음 | runtime anchor freeze completeness | 선택 |
| `W7-B3` | 필수 | 필수 | `tests/test_foms_namespace_imports.py`, `tests/test_app_bootstrap_contract.py`, `tests/harness/test_hooks_smoke.py::test_verify_result_app_ok_contract`, `tests --collect-only` | README update | 필수 |
| `W7-B4` | B3 baseline 재사용 또는 rerun | B3 baseline 재사용 또는 rerun | `node` availability snapshot | freeze completeness | 선택 |
| `W7-B5` | 필수 | 필수 | `test_composition_contracts.py`, `test_primary_form_contracts.py`, representative WDCalculator page smoke, `node --version`, `tests --collect-only` | README update | 필수 |
| `W7-B6` | latest same-path fresh baseline 재사용 또는 rerun | latest same-path fresh baseline 재사용 또는 rerun | 없음 | status register completeness | 선택 |
| `W7-B7` | latest same-path fresh baseline 재사용 또는 rerun | latest same-path fresh baseline 재사용 또는 rerun | 없음 | closeout/spec/archive completeness | 선택 |

추가 규칙:

- docs-only batch는 직전 fresh baseline을 같은 execution path에서 재사용할 수 있다.
- `W7-B3`의 `tests/harness/*` smoke는 cross-tier safety check일 뿐이며, harness code/infrastructure 편집 scope 승격 근거가 아니다.
- `W7-B5`는 `node --version` 성공 없이 completion claim 금지다.
- revert/defer로 끝난 code batch는 closeout 전에 fresh baseline 또는 불가 사유를 같은 run record에 남겨야 한다.

## 7. Run Record Contract — 배치 기록 최소 계약
각 batch run record에는 최소 아래를 남긴다.

1. exact file path delta
2. `product / wrapper / test delta` 요약
3. `canonical target` 또는 `contract target`
4. `removal / merge target`
5. `queue class`, `contract tier`, `execution state`
6. verification command와 결과
7. `why not now`, `required prep`, `suggested restart batch` (defer/partial이면 필수)
8. `next legal batch`
9. branch label (`Branch A/B/C`, `runtime-anchor-freeze-stop`, `wdcalculator-freeze-stop`, `wdcalculator-b5-revert-stop` 등)
10. Direction Lock 10문항 yes/no + 한 줄 근거

### 7.1 Direction Lock 10문항
1. tests/docs 밖의 product source를 수정하지 않았는가?
2. Wave 8 bridge retirement를 조기 실행하지 않았는가?
3. legacy-vs-canonical parity coverage를 줄이지 않았는가?
4. 새 micro pair를 기본값처럼 추가하지 않았는가?
5. same-batch 제거 대상과 증가 이유를 명시했는가?
6. `runtime anchor`와 `chunk contract` tier를 섞지 않았는가?
7. WDCalculator pilot이 `composition` + `primary-form`만 다뤘는가?
8. `node` availability를 필요한 batch에서 실제로 기록했는가?
9. `tests/README.md`를 최신 상태로 반영했는가?
10. 다음 restart batch와 why-not-now가 남아 있는가?

## 8. Stop Conditions / Branch Rules — 중단 조건과 분기

### 8.1 `readiness-gate-rejected`
아래 중 하나면 `Branch C`다.

- Wave 6 closeout/status evidence를 accepted equivalent로도 잠글 수 없음
- Wave 5 `composition`/`primary-form` state가 stale 또는 contradictory
- live `tests/` tree와 predecessor evidence가 크게 충돌하고 truth를 잠글 수 없음
- B0 runtime-anchor readiness checklist를 충족하지 못해 first pilot truth를 잠글 수 없음

허용 경로:

- `W7-B0 -> W7-B1 -> W7-B6 -> W7-B7`

### 8.2 `runtime-anchor-freeze-stop`
아래 중 하나면 `W7-B2` partial/failed를 남기고 post-B2 partial closeout path로 내려간다.

- runtime anchor rationalization이 bridge removal 없이는 불가능
- `services/`/`apps/`/`foms/` source 수정이 필요함
- giant file를 줄이려면 legacy parity assertion을 삭제해야 함

허용 경로:

- `W7-B0 -> W7-B1 -> W7-B2(partial/failed) -> W7-B6 -> W7-B7`

### 8.3 `wdcalculator-pilot-blocked`
아래 중 하나면 `Branch B`다. 이 절은 **B0 early gate** 전용이다.

- `node` 없음
- `composition`/`primary-form` readiness 불충분

허용 경로:

- `W7-B0 -> W7-B1 -> W7-B2 -> W7-B3 -> W7-B6 -> W7-B7`

### 8.4 `wdcalculator-freeze-stop`
아래 중 하나면 `W7-B4` partial/blocked를 남기고 `W7-B5`를 열지 않는다.

- B4 시점에 `node` 부재 또는 `composition`/`primary-form` readiness drift가 다시 확인됨
- actual removal list가 `estimate-lifecycle` 또는 `pricing-core` family를 요구함
- product JS touch 없이는 contract rationalization이 닫히지 않음

허용 경로:

- `W7-B0 -> W7-B1 -> W7-B2 -> W7-B3 -> W7-B4(partial/blocked) -> W7-B6 -> W7-B7`

### 8.5 `wdcalculator-b5-revert-stop`
아래 중 하나면 `W7-B5`를 same-batch full revert to pre-B5 tree로 닫고 partial closeout으로 내려간다.

- B5 실행 중 `node --version` 실패 또는 runtime drift로 Node verification이 무효화됨
- complete removal map을 same-batch에서 닫지 못함
- `coverage-shrink-stop` 또는 `micro-pair-growth-stop`을 same-batch 수정으로 해소하지 못함

허용 경로:

- `W7-B0 -> W7-B1 -> W7-B2 -> W7-B3 -> W7-B4 -> W7-B5(revert-to-pre-B5-tree) -> W7-B6 -> W7-B7`

### 8.6 `coverage-shrink-stop`
아래 중 하나면 즉시 stop 후 same-batch revert 또는 partial closeout이다.

- parity coverage 축소
- old path compatibility를 잃고도 replacement evidence가 없음
- deleted micro pair보다 replacement chunk contract coverage가 좁음

### 8.7 `micro-pair-growth-stop`
아래 중 하나면 즉시 stop이다.

- substantive 새 test/support file 수가 제거 수보다 많음
- shared helper 추가 외에 순증가를 합리화하지 못함
- pair-budget을 어기고 새 1:1 pair를 추가함

### 8.8 `scope-drift-stop`
아래 중 하나면 즉시 stop이다.

- `services/`, `apps/`, `foms/`, `static/`, `templates/` 수정 필요
- harness infra rewrite 시작
- packaging reopen 필요
- Wave 8 bridge retirement를 same-batch에서 시도

## 9. Batch Restart Minimum Input Set — 재시작 최소 입력

### 9.1 공통 규칙
- resume 세션이면 항상 live `tests/` tree snapshot을 다시 수집한다.
- 가능하면 current git revision marker도 함께 남긴다.
- snapshot 후 현재 상태가 기존 branch/pilot 결론과 모순되면 `W7-B0`로 올라가 다시 판정한다.

### 9.2 Batch별 최소 입력

| Batch | 최소 입력 |
|------|------|
| `W7-B0` | controlling spec, Wave 6 plan, Wave 5 plan, Wave 5 B2/B3 run records, `docs/AI_STATUS.md`, live runtime anchor files, live WDCalculator micro pair/support counts |
| `W7-B1` | `W7-B0` run record, latest accepted baseline |
| `W7-B2` | `W7-B0`, `W7-B1`, live `tests/test_foms_namespace_imports.py`, `tests/test_app_bootstrap_contract.py` |
| `W7-B3` | `W7-B2` freeze run record, target file budget, latest baseline |
| `W7-B4` | `W7-B0`, `W7-B1`, Wave 5 B2/B3 run records, live `composition.js`, `primary-form.js`, live WDCalculator micro pair list, `node` availability snapshot |
| `W7-B5` | `W7-B4` freeze run record, exact removal list, latest baseline, `node --version` success evidence |
| `W7-B6` | `W7-B0`, `W7-B1`, latest same-path completed/partial batch run records |
| `W7-B7` | `W7-B6`, same-path completed run records, closeout target paths(spec/archive) |

### 9.3 Path-specific restart notes
- `Branch C` (`readiness-gate-rejected`) path는 `W7-B2` run record가 없을 수 있다. 이 경우 `W7-B6`의 runtime-anchor row는 기본값 `execution state = not started`, reason = `readiness-gate-rejected`로 적는다.
- `runtime-anchor-freeze-stop` path는 `W7-B2` partial/failed run record가 반드시 있어야 한다. 이 경우 `W7-B6`의 runtime-anchor row는 기본값 `execution state = partial`, reason = `runtime-anchor-freeze-stop`로 적는다.
- `Branch B` path는 `W7-B4/W7-B5` run record가 없을 수 있다. 이 경우 `W7-B6`의 `wdcalculator-composition-primary-form` row는 기본값 `execution state = not started`, reason = `wdcalculator-pilot-blocked`로 적는다.
- `wdcalculator-freeze-stop` path는 `W7-B4` partial/blocked run record가 반드시 있어야 한다. 이 경우 `W7-B6`의 `wdcalculator-composition-primary-form` row는 기본값 `execution state = partial`, reason = `wdcalculator-freeze-stop`로 적는다.
- `wdcalculator-b5-revert-stop` path는 `W7-B5` revert run record가 반드시 있어야 한다. 이 경우 `W7-B6`의 `wdcalculator-composition-primary-form` row는 기본값 `execution state = partial`, reason = `wdcalculator-b5-revert-stop`로 적는다.

## 10. Execution Prompt Contract — 실제 실행 프롬프트에 들어가야 하는 규칙
future LLM execution prompt는 최소 아래를 포함해야 한다.

1. plan 전체 완독
2. `§2.1` 입력 문서 전부 확인
3. `W7-B0` 전에는 어떤 수정도 시작하지 않음
4. batch 시작 직전 해당 `§5.x`, `§6`, `§8`, `§9` 재확인
5. `runtime-anchor`와 `wdcalculator-composition-primary-form` 외 새 pilot 금지
6. product source 수정 금지
7. legacy parity assertion 축소 금지
8. `W7-B5`에서 `node --version` 성공 없이 completion claim 금지
9. 저장소 루트에서, 동일한 venv/PATH/PowerShell 환경 기준으로 명령 실행
10. partial closeout도 `W7-B6/W7-B7`까지 반드시 닫기
11. future run record 미리 scaffold 금지

## 11. Final Audit Loop Hard-Stop Policy — 최종 감리 루프 무한 반복 방지 규칙
이 절은 **문서 자체를 다듬는 최종 감리 루프**를 위한 hard-stop policy다. plan drafting/review는 아래 규칙을 벗어나지 않는다.

1. parallel audit round는 최대 3회다.
2. severity rubric을 아래로 고정한다.
   - `HIGH`: batch order/branch/stop/restart/verification semantics가 모순되거나 빠져서 다른 LLM이 잘못 실행할 위험이 있는 경우
   - `MEDIUM`: handoff/path/file-budget/ownership/assumption이 불명확하지만 즉시 unsafe execution까지는 아닌 경우
   - `LOW`: wording/style/taste 수준이며 plan freeze를 막지 않는 경우
3. `finding family`는 reviewer wording이 아니라 root cause slug로 묶는다. 예: `branch-c-timing`, `runtime-file-budget`, `node-path-precondition`.
4. 한 round는 동일 역할 3축을 기본값으로 한다.
   - `code-reviewer`
   - `evolution-architect`
   - `grand-develop-master`
5. round 1 이후 즉시 종료 가능한 조건은 `HIGH = 0` 그리고 `MEDIUM = 0` 둘 다 만족할 때뿐이다.
6. round 2 이후 조기 종료 가능한 조건은 `HIGH = 0`이고, 남은 `MEDIUM`이 모두 2연속 round에서 반복된 wording/traceability class일 때뿐이다. 이 경우 residual을 기록하고 freeze한다.
7. reviewer가 scope 확장 제안을 하지만 current Wave 7 boundary를 넓혀야만 반영 가능한 경우, 그 제안은 follow-up note로 내리고 same-loop patch 대상으로 승격하지 않는다.
8. round 3 종료 시점에 `HIGH`가 남아 있으면 루프를 더 돌리지 말고 user escalation이다.
9. round 3 종료 시점에 `HIGH`는 없고 `MEDIUM`만 남아 있으면, residual을 문서/closeout note에 남기고 freeze한다.
10. round 3 종료 시점에 `HIGH = 0`이고 `MEDIUM = 0`이면 즉시 freeze한다.
11. "새 reviewer를 추가하면 해결될 것 같다"는 이유로 round cap을 늘리지 않는다.
12. 문서를 다시 열 수 있는 조건은 `HIGH` 재발 또는 새 live evidence 충돌뿐이다. 동일 wording churn만으로 재오픈하지 않는다.

## 12. Completion Criteria — 완료 판정
Wave 7 plan은 아래를 만족하면 executable plan으로 본다.

- `W7-B0` branch/queue lock이 정의돼 있다.
- `W7-B1`에서 `tests/README.md` entrypoint가 정의돼 있다.
- `W7-B3`가 runtime anchor rationalization을 구체적으로 설명한다.
- `W7-B5`가 WDCalculator `composition` + `primary-form`에 한정된 chunk-contract rationalization으로 잠겨 있다.
- `W7-B6`가 pilot/defer register를 남긴다.
- `W7-B7`가 spec/archive wiring과 Wave 8 handoff를 닫는다.
- `§11` hard-stop policy가 있어 최종 감리 루프가 무한 반복으로 흐르지 않는다.
