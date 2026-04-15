# Wave 8 Legacy Bridge Retirement Execution Plan
> 작성일: 2026-04-14 | 상태: 최종 하드 감리 완료 / freeze-ready
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `foms/platform/blueprints.py`, `services/**/*.py`, `apps/api/*.py`, `apps/*_page.py`, `tests/contracts/runtime/foms_namespace_surface_tests.py`
> 선행 wave: `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md`
> 핵심 선례: `docs/plans/2026-04-13-wave3-batch2-files-canonicalization-run-record.md`, `docs/plans/2026-04-13-wave3-batch3-address-canonicalization-run-record.md`, `docs/plans/2026-04-13-wave3-batch5-aggregate-read-canonicalization-run-record.md`, `docs/plans/2026-04-13-wave4-batch5-dashboard-page-owner-run-record.md`, `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md`, `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md`, `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 8 — Legacy bridge retirement**를 실제로 집행할 수 있는 LLM용 runbook이다.

헤더의 `상태`는 **plan maturity**를 뜻한다. 실제 execution state(`W8-B0` gating 중, full closeout, partial closeout, revert-stop)는 헤더가 아니라 각 batch run record와 closeout 문서가 authoritative truth다.

Wave 8의 목적은 단순 "shim 몇 개 치우기"가 아니라, 아래 여덟 가지를 **기계적으로** 닫는 것이다.

1. Wave 6에서 package pilot이 끝났지만 남겨둔 **root `services/*.py` + flat `foms/services/*.py` compat shim** 중 `notifications` / `files` 축을 실제로 제거한다.
2. Wave 3 / Wave 4에서 canonical owner를 이미 확보했는데도 남아 있는 **`apps/*` direct-import bridge**를 `blueprints.py`와 caller import 기준으로 제거한다.
3. bridge parity 테스트를 단순 삭제하지 않고, **canonical direct-import smoke + retirement sentinel**로 같은 batch 안에서 대체한다.
4. `foms/platform/blueprints.py`는 **registration order 불변**을 유지한 채 import source만 canonical `foms.*`로 바꾼다.
5. `apps.api.personal_board`, `apps.api.orders.__init__`, `services.jobs.*`, `services.business_calendar` 같은 **adapter shell / runtime-string / explicit exception**은 본편에 끌어오지 않고 status/defer row로 잠근다.
6. high-risk cluster(`apps.api.notifications`, `attachments`, `chat`, `channel_*`, platform-adjacent shims)는 "나중에 보자"가 아니라 **bridge-stuck / continuation required** 상태로 명시한다.
7. 각 code batch는 `bridge count`를 **순감**시키는 방향만 허용한다. 파일 수가 늘거나 bridge가 다른 형태로 되살아나면 실패다.
8. 계획서 감리 루프도 무한 반복에 빠지지 않게, **parallel audit hard-stop policy**를 문서 안에 명시한다.

### 1.2 기능 요구사항
1. Wave 8의 authoritative truth는 항상 live `foms/platform/blueprints.py`, live `services/**/*.py`, live `apps/api/*.py`, live `apps/*_page.py`, accepted Wave 3/4/6/7 evidence, runtime contract tests다.
2. Wave 8는 **legacy bridge retirement**다. canonical product logic 재작성, 새 context package 설계, page/API feature 개선을 본편으로 포함하면 안 된다.
3. 한 batch는 반드시 **한 retirement mechanism / 한 bridge family**만 다룬다.
4. bridge는 `reroute imports -> verify zero legacy usage -> add retirement sentinel -> delete bridge` 순서로만 제거한다.
5. 삭제되는 bridge에 대응하던 test coverage는 same-batch에서 **canonical smoke** 또는 **retirement sentinel**로 대체되어야 한다.
6. `foms/platform/blueprints.py`는 **registration order와 binding 이름**이 runtime contract다. Wave 8에서 허용되는 변화는 import source와 주석 정도뿐이다.
7. Wave 8 mainline service pilot은 `notifications` / `files` compat shim만 허용한다.
8. Wave 8 mainline direct-import pilot은 아래 여섯 경로만 허용한다.
   - `apps/api/files.py`
   - `apps/api/address.py`
   - `apps/api/erp_measurement.py`
   - `apps/erp_measurement_dashboard.py`
   - `apps/erp_production_page.py`
   - `apps/erp_completion_page.py`
9. `apps.api.personal_board`는 canonical helper owner가 이미 `foms.api.personal_board`로 이동했지만, **Blueprint + decorator shell**이 아직 `apps`에 남아 있으므로 mainline pilot에 포함하지 않는다.
10. `apps.api.orders.__init__`는 thin shell에 가깝더라도 route decorator, queue binding, helper injection이 남아 있으므로 mainline pilot에 포함하지 않는다.
11. `services.jobs.*`는 thin shim이지만 `_TASK_PATH_PREFIX == "services.jobs.tasks"` 같은 runtime string contract가 있으므로 mainline pilot에 포함하지 않는다.
12. `services.business_calendar.py`는 shim이 아니라 **explicit exception implementation**이므로 mainline pilot에 포함하지 않는다.
13. `apps.api.notifications`, `apps.api.attachments`, `apps.api.chat`, `services/channel_*`, platform-adjacent shims는 **owner-surface retirement 기준으로** high-risk cluster로만 다룬다.
14. Wave 8는 `src/foms`, `pyproject.toml` hardening, packaging reopen을 다시 열지 않는다.
15. Wave 8는 route path, endpoint name, blueprint name, auth decorator stack, JSON shape를 바꾸지 않는다.
16. Wave 8 code batch에서 caller 파일을 수정할 수는 있지만, 허용되는 수정은 **import source reroute**와 same-batch canonical docstring/README sync뿐이다.
17. high-risk cluster 파일을 caller로 건드리는 경우라도, 이는 **consumer-side import reroute 예외**일 뿐이며 그 cluster가 mainline pilot으로 승격된 것을 뜻하지 않는다.
18. `backups/`, `docs/`, `agent-transcripts/`에 남아 있는 legacy import 문자열은 zero-import gate의 blocker가 아니다. blocker는 **live product code + non-deferred tests**만이다.
19. predecessor closeout이 없다고 해서 self-waive하지 않는다. `W8-B0` run record 안에 `accepted equivalent evidence` 또는 `rejected evidence`를 남겨야 한다.
20. baseline이 green이 아니면 억지 fix-forward로 진행하지 않는다. `fresh green baseline` 또는 `inherited-red baseline`을 명시하고 그 범위를 batch마다 다시 확인한다.
21. final plan audit loop는 `§11` hard-stop policy를 따른다. local wording 수정만으로 round를 추가하지 않는다.

### 1.2.1 BR shorthand definitions
- `BR1`: `delete-after-reroute`다. bridge는 import reroute와 zero-legacy verification 뒤에만 삭제한다.
- `BR2`: `retirement-sentinel`이다. parity test를 지운 자리에 canonical direct-import smoke 또는 retirement absence assertion이 남아야 한다.
- `BR3`: `import-source-only`다. caller 파일에서는 import source line과 same-batch comment/doc sync만 허용한다.
- `BR4`: `pilot-cap`이다. Wave 8 mainline code pilot은 `service compat shim`과 `direct canonical import bridge` 두 축만 허용한다.
- `BR5`: `adapter-shell-fenced`다. `personal_board`, `orders`처럼 wrapper가 아직 runtime shell 역할을 하는 레인은 defer row로만 남긴다.
- `BR6`: `runtime-string-fenced`다. `services.jobs.*`처럼 문자열 경로 계약이 있는 레인은 mainline에서 건드리지 않는다.
- `BR7`: `net-negative-bridge-count`다. 각 code batch 종료 시 bridge file count 또는 live bridge surface count가 순감해야 한다.
- `BR8`: `hard-stop-audit`다. 감리 round는 최대 3번이며, round 2 이후에는 holistic patch 또는 freeze / new-plan decision만 허용한다.

### 1.3 Out of scope / freeze
Wave 8에서는 아래를 건드리지 않는다.

- `services/business_calendar.py` implementation 이동
- `services/jobs/*` runtime string contract 재설계
- `apps.api.personal_board` Blueprint shell collapse
- `apps.api.orders.__init__` route shell collapse
- `apps.api.notifications`, `apps.api.attachments`, `apps.api.chat`, `apps.api.channel_*` canonicalization
- `services/channel_*`, `services/storage.py`, platform-adjacent shim cluster 재편
- 새 canonical package / 새 bounded context / 새 route / 새 template namespace 생성
- `static/js/`, `templates/` 구조 재설계
- `app.py`, worker bootstrap, Alembic, DB schema, persistence lifecycle
- packaging reopen (`src/foms`, `pyproject.toml`)

Wave 8는 **bridge 삭제 + import source retirement + defer/status register + closeout**까지만 담당한다.

추가 규칙:

- 어떤 batch라도 product behavior 수정이 필요해지는 순간 out-of-scope로 판단하고 즉시 stop/defer한다.
- 어떤 batch라도 legacy bridge를 제거하려고 `try/except import` fallback을 새로 넣는 순간 실패다.
- 어떤 batch라도 `personal_board` / `orders` shell을 "이번 기회에 같이 정리"하려는 순간 scope drift다.
- 어떤 batch라도 bridge를 삭제했는데 sentinel test 또는 status register row가 없으면 실패다.

### 1.4 Scope reconciliation — Wave 3 / 4 / 6 / 7 / 9과의 정합
1. Wave 3는 `files`, `address`, `personal_board` canonical API를 만들고 `apps.api.*` thin bridge를 남겼다.
2. Wave 4는 `production`, `completion`, `measurement` page canonical owner를 만들었지만 `apps.*` 등록 bridge를 유지했다.
3. Wave 6는 `notifications` / `files` package pilot을 끝냈지만 root+flat compat shim 제거는 **Wave 8**로 넘겼다.
4. Wave 7는 legacy import parity 테스트를 유지한 채 bridge-coupled debt를 Wave 8 owner로 넘기도록 설계됐다.
5. 따라서 Wave 8의 기본 해석은 `canonical owner는 이미 존재하고, 남은 bridge만 치운다`이다.
6. `apps.api.personal_board`와 `apps.api.orders.__init__`는 canonical helper owner가 생겼더라도 wrapper 자체가 아직 runtime shell 역할을 하므로 Wave 8 mainline이 아니라 defer/status row다.
7. `services.jobs.*`와 `services.business_calendar.py`는 removal이 아니라 별도 승인 / 별도 runtime plan 축이다.
8. Wave 9는 packaging reopen review다. Wave 8 미종결 bridge debt를 Wave 9에 슬쩍 넘기지 않는다. unresolved row는 **bridge-stuck / continuation required**로 남긴다.

## 2. Current Bridge Truth — 현재 bridge landscape

### 2.1 선행 handoff gate
Wave 8 actual execution은 아래 산출물을 소비한 뒤에만 시작한다.

1. `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
2. `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md`
3. `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md`
4. `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md`
5. `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md`
6. `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md`
7. `docs/plans/2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md`
8. `docs/plans/2026-04-13-wave3-batch2-files-canonicalization-run-record.md`
9. `docs/plans/2026-04-13-wave3-batch3-address-canonicalization-run-record.md`
10. `docs/plans/2026-04-13-wave3-batch5-aggregate-read-canonicalization-run-record.md`
11. `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md`
12. `docs/plans/2026-04-13-wave4-batch5-dashboard-page-owner-run-record.md`
13. `foms/web/measurement/README.md`
14. live `foms/platform/blueprints.py`
15. live `services/realtime_notifications.py`, `services/file_utils.py`, `foms/services/realtime_notifications.py`, `foms/services/file_utils.py`
16. live `apps/api/files.py`, `apps/api/address.py`, `apps/api/erp_measurement.py`, `apps/erp_measurement_dashboard.py`, `apps/erp_production_page.py`, `apps/erp_completion_page.py`, `apps/api/personal_board.py`, `apps/api/orders/__init__.py`
17. live `tests/contracts/runtime/foms_namespace_surface_tests.py`, `tests/test_measurement_slice_contract.py`, `tests/test_foms_namespace_imports.py`
18. `docs/AI_STATUS.md` 또는 accepted current-state memo

추가 규칙:

- Wave 7 actual closeout (`W7-B6`, `W7-B7`)가 없어도 본 문서는 drafted plan으로 존재할 수 있다.
- actual execution에서 Wave 7 closeout이 없으면 `W8-B0` run record 안에 `accepted equivalent evidence` 또는 `rejected evidence`를 명시한다.
- Wave 7 equivalent evidence 최소 계약:
  - freeze-ready Wave 7 plan 자체
  - latest runtime contract test landscape snapshot
  - bridge-coupled test family 목록
  - current baseline 상태(green / inherited-red)
- predecessor evidence와 live tree가 충돌하면 live tree를 truth로 두고 drift를 `W8-B0` run record에 먼저 적는다.

### 2.2 Bridge mechanism / queue class 판정 규칙

| 축 | 값 | 의미 |
|------|------|------|
| `bridge mechanism` | `compat shim` | root `services/*.py` 또는 flat `foms/services/*.py`가 canonical package를 재노출만 하는 상태 |
| `bridge mechanism` | `direct-canonical import bridge` | canonical owner가 이미 있고, 남은 `apps.*` 모듈을 caller/registry import source 전환으로 제거할 수 있는 상태 |
| `bridge mechanism` | `adapter shell` | thin해 보여도 Blueprint, decorator, helper injection, route shell이 아직 `apps.*`에 남은 상태 |
| `bridge mechanism` | `runtime-string bridge` | import source 외에 job path, dotted string, registry 문자열 같은 runtime contract가 남은 상태 |
| `bridge mechanism` | `explicit exception implementation` | root 파일이 shim이 아니라 실제 구현체인 상태 |
| `queue class` | `mainline-pilot` | Wave 8 code batch 대상 |
| `queue class` | `adapter-shell defer` | shell collapse가 필요해 mainline code batch 금지 |
| `queue class` | `runtime-string-coupled defer` | string contract 정리가 선행돼야 해 mainline code batch 금지 |
| `queue class` | `explicit-exception` | 승인 게이트 없이는 mainline code batch 금지 |
| `queue class` | `high-risk cluster defer` | 다중 모듈 / multi-side-effect로 mainline code batch 금지 |
| `execution state` | `completed` | Wave 8에서 bridge retirement까지 닫힘 |
| `execution state` | `not started` | touched되지 않음 |
| `execution state` | `partial` | freeze/status only 또는 일부 pilot만 완료 |
| `execution state` | `reverted` | code batch 시도 후 pre-batch tree로 되돌리고 status row만 남김 |

보조 판정 규칙:

1. route path, endpoint name, decorator stack을 유지한 채 import source만 바꾸면 `direct-canonical import bridge`다.
2. bridge 제거를 위해 canonical module이 새로운 Blueprint shell을 가져와야 하면 `adapter shell`이다.
3. legacy dotted path 문자열이 runtime semantics에 쓰이면 `runtime-string bridge`다.
4. root `services/` 파일이 실제 구현이면 `explicit exception implementation`이다.
5. mainline-pilot은 **product behavior 수정 없이** net-negative bridge count가 가능한 family에만 허용한다.
6. `foms/platform/blueprints.py`에서 import source를 바꿀 때 register call 순서가 달라지면 실패다.

### 2.3 현재 queue snapshot
이 표는 provisional snapshot이다. future LLM은 그대로 복사하지 말고 `W8-B0`에서 live evidence로 다시 잠가야 한다.

| Family | Live truth | Bridge mechanism | Provisional queue class | 비고 |
|------|------|------|------|------|
| service-compat-notifications-files | `services/realtime_notifications.py`, `services/file_utils.py`, `foms/services/realtime_notifications.py`, `foms/services/file_utils.py` | `compat shim` | `mainline-pilot` | Wave 6 SR-N1 / SR-F1 removal condition |
| apps-direct-files-address | `apps/api/files.py`, `apps/api/address.py`, known caller imports, `foms/platform/blueprints.py` | `direct-canonical import bridge` | `mainline-pilot` | helper re-export + registry import source 전환 |
| apps-direct-measurement-production-completion | `apps/api/erp_measurement.py`, `apps/erp_measurement_dashboard.py`, `apps/erp_production_page.py`, `apps/erp_completion_page.py`, `foms/platform/blueprints.py` | `direct-canonical import bridge` | `mainline-pilot` | alias/module-replacement bridge 제거 |
| personal-board-shell | `apps/api/personal_board.py`, `foms/api/personal_board.py` | `adapter shell` | `adapter-shell defer` | canonical helper는 있으나 Blueprint shell은 아직 `apps` |
| orders-shell | `apps/api/orders/__init__.py` | `adapter shell` | `adapter-shell defer` | decorators + queue binding + helper injection |
| jobs-legacy-path | `services/jobs/*`, `tests/contracts/runtime/foms_namespace_surface_tests.py` | `runtime-string bridge` | `runtime-string-coupled defer` | `_TASK_PATH_PREFIX == "services.jobs.tasks"` |
| business-calendar | `services/business_calendar.py` | `explicit exception implementation` | `explicit-exception` | spec 승인 게이트 |
| high-risk-cluster | `apps/api/notifications.py`, `apps/api/attachments.py`, `apps/api/chat/*`, `services/channel_*`, platform-adjacent shims | mixed | `high-risk cluster defer` | owner-surface retirement는 Wave 8 본편에 섞지 않음. 단, low-risk bridge 제거를 위해 이들 파일의 **import source line만** consumer-side로 수정하는 것은 허용 가능 |

### 2.4 Pilot tie-break / lock 규칙
1. first executable pilot은 항상 `service-compat-notifications-files`다.
2. second executable pilot은 항상 `apps-direct-files-address` + `apps-direct-measurement-production-completion` direct-import family다.
3. `personal-board-shell`, `orders-shell`, `jobs-legacy-path`, `business-calendar`은 second pilot을 앞지를 수 없다.
4. `service-compat-notifications-files`가 readiness를 통과하지 못하면 mainline은 즉시 `Branch C` docs-only partial closeout으로 내려간다.
5. direct-import family에서 pure bridge 성격이 불분명한 surface가 나오면 해당 surface는 즉시 mainline에서 제외하고 status row로 넘긴다.
6. `personal_board` 또는 `orders`를 second pilot에 끼워 넣는 순간 scope drift다.

## 3. Fixed Execution Pipeline — 고정 배치 순서
Wave 8 mainline은 아래 순서를 기본값으로 한다.

1. `W8-B0` — Readiness gate + authoritative bridge queue lock
2. `W8-B1` — Bridge taxonomy + retirement queue freeze
3. `W8-B2` — Service compat bridge freeze
4. `W8-B3` — Service compat bridge retirement
5. `W8-B4` — Direct-import bridge freeze
6. `W8-B5` — Direct-import bridge retirement
7. `W8-B6` — Bridge status register
8. `W8-B7` — Closeout + continuation handoff

branch semantics:

- `Branch A` full mainline: `W8-B0 -> W8-B1 -> W8-B2 -> W8-B3 -> W8-B4 -> W8-B5 -> W8-B6 -> W8-B7`
- `Branch B` service-only path: `W8-B0 -> W8-B1 -> W8-B2 -> W8-B3 -> W8-B6 -> W8-B7`
- `Branch C` docs-only partial closeout: `W8-B0 -> W8-B1 -> W8-B6 -> W8-B7`
- `service-compat-freeze-stop` post-B2 path: `W8-B0 -> W8-B1 -> W8-B2(partial/blocked) -> W8-B6 -> W8-B7`
- `service-compat-b3-revert-stop` post-B3 path: `W8-B0 -> W8-B1 -> W8-B2 -> W8-B3(revert-to-pre-B3-tree) -> W8-B6 -> W8-B7`
- `direct-import-freeze-stop` post-B4 path: `W8-B0 -> W8-B1 -> W8-B2 -> W8-B3 -> W8-B4(partial/blocked) -> W8-B6 -> W8-B7`
- `direct-import-b5-revert-stop` post-B5 path: `W8-B0 -> W8-B1 -> W8-B2 -> W8-B3 -> W8-B4 -> W8-B5(revert-to-pre-B5-tree) -> W8-B6 -> W8-B7`

## 4. Batch Catalog

| Batch | 이름 | 성격 | 핵심 산출물 | 선행 조건 | 대표 run record |
|------|------|------|------|------|------|
| `W8-B0` | Readiness gate + queue lock | docs / gate | accepted predecessor evidence, live bridge snapshot, branch choice | 선행 evidence 수집 | `docs/plans/2026-04-14-wave8-batch0-readiness-gate-run-record.md` |
| `W8-B1` | Bridge taxonomy + queue freeze | docs | bridge mechanism rules, mainline/defer map, no-go boundary | `W8-B0` | `docs/plans/2026-04-14-wave8-batch1-bridge-taxonomy-run-record.md` |
| `W8-B2` | Service compat bridge freeze | docs | exact shim paths, caller/test surface, zero-import rule, retirement sentinel map | `W8-B1` | `docs/plans/2026-04-14-wave8-batch2-service-compat-freeze-run-record.md` |
| `W8-B3` | Service compat bridge retirement | code / service pilot | package-canonical imports, 4 shim removals, updated runtime tests, README sync | `W8-B2` | `docs/plans/2026-04-14-wave8-batch3-service-compat-retirement-run-record.md` |
| `W8-B4` | Direct-import bridge freeze | docs | direct-import candidate list, caller map, registry import-source lock, explicit exclusion set | `Branch A` + `W8-B3` | `docs/plans/2026-04-14-wave8-batch4-direct-import-freeze-run-record.md` |
| `W8-B5` | Direct-import bridge retirement | code / app bridge pilot | canonical `blueprints.py` imports, retired `apps/*` bridges, updated caller imports/tests, docstring/README sync | `W8-B4` | `docs/plans/2026-04-14-wave8-batch5-direct-import-retirement-run-record.md` |
| `W8-B6` | Bridge status register | docs / truth | completed/defer/stuck rows, continuation owner, bridge count delta | 모든 legal path 공통 | `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md` |
| `W8-B7` | Closeout + continuation handoff | docs / closeout | full/partial closeout, spec/archive sync, unresolved bridge-stuck rows | `W8-B6` | `docs/plans/2026-04-14-wave8-batch7-closeout-run-record.md` |

## 5. Batch Runbook — 배치별 실행 규칙
`§5` 각 batch 검증 블록은 최소 subset만 적는다. 실제 완료 판정은 항상 `§7 Run Record Contract` 전체를 함께 만족해야 한다.

### 5.1 W8-B0 — Readiness gate + authoritative bridge queue lock
**목표**
- predecessor evidence, live bridge surface, baseline 상태를 다시 잠근다.
- `Branch A/B/C`를 명시적으로 판정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave8-batch0-readiness-gate-run-record.md`

**금지 변경**
- runtime code
- test file rename/move
- README/spec/archive update

**실행 단계**
1. `§2.1` 입력 문서를 exact path 기준으로 다시 연다.
2. Wave 7 actual closeout이 없으면 equivalent evidence를 평가하고 `accepted/rejected`를 명시한다.
3. live bridge snapshot을 아래 항목으로 남긴다.
   - pilot 4 shim file 존재 여부
   - direct-import candidate 6 bridge file 존재 여부
   - `foms/platform/blueprints.py`의 current import source lines
   - rg counts: `services.realtime_notifications`, `services.file_utils`, `foms.services.realtime_notifications`, `foms.services.file_utils`
   - rg counts: `apps.api.files`, `apps.api.address`, `apps.api.erp_measurement`, `apps.erp_measurement_dashboard`, `apps.erp_production_page`, `apps.erp_completion_page`
4. baseline policy를 아래 둘 중 하나로 잠근다.
   - `fresh green baseline`
   - `inherited-red baseline` + 실패 test 목록
5. branch를 아래 규칙으로 판정한다.
   - `Branch A`: predecessor accepted + service pilot ready + direct-import pilot ready
   - `Branch B`: predecessor accepted + service pilot ready + direct-import pilot blocked 또는 ambiguous
   - `Branch C`: readiness rejected 또는 service pilot not ready
6. `next legal batch`를 명시한다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- live snapshot completeness 확인
- branch reason one-line summary

### 5.2 W8-B1 — Bridge taxonomy + retirement queue freeze
**목표**
- bridge mechanism, queue class, no-go boundary를 authoritative doc로 잠근다.
- mainline pilot과 defer row를 다시 분리한다.

**허용 변경**
- `docs/plans/2026-04-14-wave8-batch1-bridge-taxonomy-run-record.md`

**금지 변경**
- runtime code
- test edits
- README/spec/archive update

**실행 단계**
1. `§2.2`, `§2.3`, `§2.4`를 live evidence 기준으로 다시 채운다.
2. `service-compat-notifications-files`가 exact 4-file compat shim family인지 확인한다.
3. direct-import candidate 6-file set을 다시 확인한다.
4. 아래 explicit exclusion set을 run record에 적는다.
   - `apps/api/personal_board.py`
   - `apps/api/orders/__init__.py`
   - `services/jobs/*`
   - `services/business_calendar.py`
   - `apps/api/notifications.py`
   - `apps/api/attachments.py`
   - `apps/api/chat/*`
   - `services/channel_*`
5. retirement-sentinel 규칙을 명시한다.
6. `W8-B2`, `W8-B4`에서 허용되는 exact file families를 잠근다.

**검증**
- doc completeness
- pilot/defer split 명시
- exclusion set 누락 없음

### 5.3 W8-B2 — Service compat bridge freeze
**목표**
- `notifications` / `files` compat shim 제거를 위한 exact surface와 zero-import rule을 잠근다.

**허용 변경**
- `docs/plans/2026-04-14-wave8-batch2-service-compat-freeze-run-record.md`

**금지 변경**
- shim 삭제
- direct-import pilot touch
- `foms/platform/blueprints.py` 변경

**실행 단계**
1. 아래 exact shim paths를 lock한다.
   - `services/realtime_notifications.py`
   - `services/file_utils.py`
   - `foms/services/realtime_notifications.py`
   - `foms/services/file_utils.py`
2. current canonical targets를 lock한다.
   - `foms.services.notifications.realtime_notifications`
   - `foms.services.files.file_utils`
3. live product/test import surface를 `rg`로 다시 수집한다.
4. B3 allowed caller/test file set을 잠근다.
   - `tests/contracts/runtime/foms_namespace_surface_tests.py`
   - `tests/test_foms_namespace_imports.py`
   - `tests/test_realtime_notifications.py`
   - caller files found by current `rg`
5. retirement sentinel rule을 잠근다.
   - canonical direct-import smoke 유지
   - retired path import는 explicit absence assertion 또는 equivalent sentinel로 대체
6. hidden runtime dependency가 보이면 `service-compat-freeze-stop`으로 내려간다.

**검증**
- `APP_OK`
- `verify_result`
- `rg` snapshot completeness

### 5.4 W8-B3 — Service compat bridge retirement
**목표**
- root+flat compat shim 4개를 제거하고 package canonical import로 정렬한다.

**허용 변경**
- `services/realtime_notifications.py` **삭제**
- `services/file_utils.py` **삭제**
- `foms/services/realtime_notifications.py` **삭제**
- `foms/services/file_utils.py` **삭제**
- `foms/services/notifications/__init__.py`
- `foms/services/files/__init__.py`
- caller import reroute files
- `tests/contracts/runtime/foms_namespace_surface_tests.py`
- `tests/test_foms_namespace_imports.py`
- `tests/test_realtime_notifications.py`
- `foms/services/README.md`
- `docs/plans/2026-04-14-wave8-batch3-service-compat-retirement-run-record.md`

**금지 변경**
- `services/jobs/*`
- `services/business_calendar.py`
- `foms/platform/blueprints.py`
- `apps/*`
- feature logic changes

**실행 단계**
1. caller imports를 canonical package paths로 바꾼다.
2. `foms/services/notifications/__init__.py`, `foms/services/files/__init__.py`, `foms/services/README.md`에서 "compat shim remains" 문구를 current truth로 갱신한다.
3. runtime contract tests를 parity-from-bridge에서 `canonical import + retirement sentinel`로 바꾼다.
4. product code + non-deferred tests 기준으로 retired path `rg` zero를 확인한다.
5. 4개 compat shim file을 삭제한다.
6. run record에 before/after bridge count delta를 남긴다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py tests/test_realtime_notifications.py tests/test_foms_namespace_imports.py -q`
- retired service path `rg` zero (product + non-deferred tests)

**실패 규칙**
- code batch가 실패하면 **same-batch full revert to pre-B3 tree** 후 `service-compat-b3-revert-stop`으로 내려간다.

### 5.5 W8-B4 — Direct-import bridge freeze
**목표**
- 이미 canonical owner가 있는 `apps/*` bridge 중 direct import retirement 가능한 set만 잠근다.

**허용 변경**
- `docs/plans/2026-04-14-wave8-batch4-direct-import-freeze-run-record.md`

**금지 변경**
- bridge 삭제
- `foms/platform/blueprints.py` code edit
- `personal_board` / `orders` shell touch
- README/spec/archive update

**실행 단계**
1. 아래 direct-import candidate set을 exact path로 다시 잠근다.
   - `apps/api/files.py`
   - `apps/api/address.py`
   - `apps/api/erp_measurement.py`
   - `apps/erp_measurement_dashboard.py`
   - `apps/erp_production_page.py`
   - `apps/erp_completion_page.py`
2. 아래 canonical import targets를 다시 적는다.
   - `foms.api.files`
   - `foms.api.address`
   - `foms.api.measurement`
   - `foms.web.measurement.dashboard`
   - `foms.web.production.dashboard`
   - `foms.web.cs.completion_dashboard`
3. current known caller map을 적는다.
   - `apps/api/chat/utils.py`
   - `apps/api/chat/routes_files.py`
   - `apps/api/attachments.py`
   - `apps/api/attachments_internal/common.py`
   - `apps/api/attachments_internal/direct_upload.py`
   - `apps/api/attachments_internal/search.py`
   - `apps/api/erp_orders_drawing.py`
   - `apps/api/erp_orders_completion.py`
   - `apps/api/erp_orders_blueprint.py`
   - plus current `rg` result
4. `measurement` / `production` / `completion` alias bridge는 current truth 기준 **`foms/platform/blueprints.py` + dedicated tests 외 non-doc product caller 없음**을 먼저 확인한다. 추가 product caller가 발견되면 해당 surface는 `direct-import-freeze-stop`으로 내린다.
5. exact test surface를 잠근다.
   - `tests/contracts/runtime/foms_namespace_surface_tests.py`
   - `tests/test_measurement_slice_contract.py`
   - `tests/test_menu_config.py`
   - `tests/test_foms_namespace_imports.py` (필요 시)
6. 아래 direct exclusions를 다시 적는다.
   - `apps/api/personal_board.py`
   - `apps/api/orders/__init__.py`
   - `apps/api/notifications.py`
7. candidate 중 unique shell semantics가 발견되면 해당 surface를 `direct-import-freeze-stop` row로 밀어낸다.

**검증**
- doc completeness
- caller map exists
- candidate set vs exclusion set overlap 없음

### 5.6 W8-B5 — Direct-import bridge retirement
**목표**
- `apps/*` direct-import bridge 6개를 제거하고 `foms.platform.blueprints.py` 및 caller imports를 canonical source로 정렬한다.

**허용 변경**
- `foms/platform/blueprints.py` (import source line / comment only)
- `apps/api/files.py` **삭제**
- `apps/api/address.py` **삭제**
- `apps/api/erp_measurement.py` **삭제**
- `apps/erp_measurement_dashboard.py` **삭제**
- `apps/erp_production_page.py` **삭제**
- `apps/erp_completion_page.py` **삭제**
- direct-import caller files (B4 locked list)
- `tests/contracts/runtime/foms_namespace_surface_tests.py`
- `tests/test_measurement_slice_contract.py`
- `tests/test_menu_config.py`
- `tests/test_foms_namespace_imports.py` (필요 시)
- `foms/api/files.py`
- `foms/api/address.py`
- `foms/web/measurement/README.md`
- `docs/plans/2026-04-14-wave8-batch5-direct-import-retirement-run-record.md`

**금지 변경**
- `app.py`
- `foms/platform/blueprints.py` register order 변경
- `personal_board` / `orders` shell touch
- 새 canonical module 생성
- route / decorator / response shape 변경

**실행 단계**
1. `files` / `address` direct callers의 import source를 canonical `foms.api.*`로 바꾼다. 이때 `attachments`, `chat`, `erp_orders_*` 파일은 **consumer-side import line**만 수정한다.
2. `measurement` / `production` / `completion` alias bridge는 current truth 기준 `foms/platform/blueprints.py` 외 non-doc product caller가 없음을 다시 확인한다. 하나라도 발견되면 same-batch에 포함하지 말고 `direct-import-freeze-stop` row로 내린다.
3. `foms/platform/blueprints.py`의 import source를 canonical `foms.*`로 바꾸되 register call order와 binding 이름은 그대로 둔다.
4. runtime tests를 legacy alias parity에서 `canonical import + retirement sentinel`로 바꾼다.
5. direct-import bridge 6개를 삭제한다.
6. `foms/api/files.py`, `foms/api/address.py`, `foms/web/measurement/README.md`의 bridge-retirement 문구를 current truth로 갱신한다.
7. run record에 before/after bridge count delta와 retired path list를 남긴다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py tests/test_measurement_slice_contract.py tests/test_menu_config.py tests/test_foms_namespace_imports.py -q`
- retired apps path `rg` zero (product + non-deferred tests)

**실패 규칙**
- code batch가 실패하면 **same-batch full revert to pre-B5 tree** 후 `direct-import-b5-revert-stop`으로 내려간다.

### 5.7 W8-B6 — Bridge status register
**목표**
- completed / defer / bridge-stuck row를 authoritative table로 남긴다.

**허용 변경**
- `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md`
- `foms/services/README.md` status summary (필요 시 docs-only sync)

**금지 변경**
- 신규 code pilot
- spec/archive/AI_STATUS update

**실행 단계**
1. 아래 minimum row set을 채운다.
   - `BR-S1` service compat notifications/files
   - `BR-D1` apps direct files/address
   - `BR-D2` apps direct measurement/production/completion
   - `BR-P1` personal_board shell
   - `BR-O1` orders shell
   - `BR-J1` jobs runtime-string bridge
   - `BR-B1` business_calendar explicit exception
   - `BR-H1` high-risk cluster
2. 각 row에 아래 필드를 남긴다.
   - row type
   - execution state
   - bridge mechanism
   - future canonical target
   - why-not-now / removal condition
   - continuation owner
   - bridge count delta
3. partial path일 경우 completed row와 blocked row를 분리한다.
4. unresolved row는 `bridge-stuck` 또는 `continuation required`로 명시한다.

**검증**
- row 누락 없음
- branch별 execution state 정합

### 5.8 W8-B7 — Closeout + continuation handoff
**목표**
- full 또는 partial closeout을 문서로 고정하고 spec/archive/status를 sync한다.

**허용 변경**
- `docs/plans/2026-04-14-wave8-batch7-closeout-run-record.md`
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
- `docs/ARCHIVE_INDEX.md`
- `docs/AI_STATUS.md`

**금지 변경**
- code touch
- Wave 9 packaging reopen 논의 확장

**실행 단계**
1. closeout 유형을 아래 중 하나로 잠근다.
   - `full closeout`
   - `partial closeout`
2. `W8-B6` status register를 authoritative source로 인용한다.
3. spec reference / archive index / AI status를 current truth에 맞게 갱신한다.
4. unresolved row는 `Wave 9`가 아니라 `continuation required` 또는 `bridge-stuck`로 기록한다.
5. `next legal batch`를 아래 둘 중 하나로 적는다.
   - `없음 — Wave 8 chain 종료`
   - `없음 — dedicated continuation plan required`

**검증**
- docs-only closeout consistency
- status register link correctness
- AI_STATUS 한 줄 요약 반영

## 6. Additional Rules — 추가 실행 규칙
1. `W8-B0` baseline policy는 전체 wave에 적용된다. 이후 code batch는 fresh green baseline 위에서만 성공 주장 가능하다.
2. caller file 수정은 **import source line**과 same-batch docstring/README sync만 허용된다. 함수 본문 로직 수정은 scope drift다.
3. `foms/platform/blueprints.py`는 import source line만 바꾸고, register call과 return bindings는 유지한다.
4. 삭제된 bridge를 대체하는 sentinel test는 `ModuleNotFoundError`, `find_spec` absence, 또는 explicit canonical-only assertion 중 하나로 same-batch에 남겨야 한다.
5. `docs/`, `backups/`, `agent-transcripts/`에 남아 있는 문자열은 zero-import gate를 막지 않는다.
6. canonical docstring/README가 "Wave 8에서 제거"라고 적혀 있었다면, Wave 8에서 실제 제거가 일어나는 batch에서 current truth로 갱신해야 한다.
7. `apps/api/files.py` caller reroute는 helper import source만 바꾸며, `attachments`, `chat`, `erp_orders_*`의 로직 변경은 허용되지 않는다. 이 caller 수정은 **cluster admission이 아니라 consumer cleanup**이다.
8. `personal_board`와 `orders`는 shell collapse가 필요한 순간 즉시 defer row로 내린다. mainline pilot에 억지로 포함하지 않는다.
9. unresolved row를 남길 수는 있지만, 이유 없이 `not started`로만 끝내면 안 된다. `why-not-now`와 `continuation owner`가 반드시 있어야 한다.

## 7. Run Record Contract — 모든 batch 공통 기록 규약
각 batch run record는 아래 항목을 반드시 포함한다.

1. batch id / 이름 / 실행일 / attempt / 진입 branch
2. scope lock (허용 / 금지)
3. inputs consumed
4. live snapshot 또는 caller/test inventory
5. bridge mechanism / queue class
6. baseline policy (`fresh green baseline` 또는 `inherited-red baseline`)
7. exact touched files
8. product / wrapper / test delta
9. canonical target
10. retired bridge path list 또는 deferred row list
11. removal condition / why-not-now
12. verification commands + 결과
13. `rg` before/after snapshot 또는 equivalent evidence
14. Direction Lock 10문항
15. stop / revert / partial 여부
16. bridge count delta
17. next legal batch

### 7.1 Direction Lock (10문항)
1. 이 batch는 bridge count를 순감시키는가?
2. import source만 바꾸고 behavior는 그대로인가?
3. canonical owner는 이미 존재하는가?
4. shell collapse가 필요한 surface를 mainline에 끌어오지 않았는가?
5. runtime string / explicit exception을 건드리지 않았는가?
6. `foms/platform/blueprints.py` registration order를 보존했는가?
7. 삭제된 bridge마다 retirement sentinel 또는 canonical smoke가 남았는가?
8. unresolved row에 why-not-now / continuation owner가 있는가?
9. packaging / DB / worker / template 구조를 건드리지 않았는가?
10. 이 batch는 다음 bridge batch의 전제 조건을 더 명확하게 만들었는가?

## 8. Stop Conditions / Branch Rules

### 8.1 `readiness-gate-rejected`
- trigger:
  - predecessor evidence rejected
  - baseline 상태 불명
  - service pilot exact surface가 lock되지 않음
- allowed path:
  - `Branch C`

### 8.2 `service-compat-freeze-stop`
- trigger:
  - `notifications` / `files` pilot exact path set이 흔들림
  - hidden runtime dependency로 pure compat shim 삭제가 불가능
- allowed path:
  - `service-compat-freeze-stop -> W8-B6 -> W8-B7`

### 8.3 `service-compat-b3-revert-stop`
- trigger:
  - B3 code batch 실패
  - retired path zero-import를 만들지 못함
  - focused pytest / APP_OK / verify_result regression을 same-batch fix하지 못함
- allowed path:
  - pre-B3 tree로 full revert 후 `W8-B6 -> W8-B7`

### 8.4 `direct-import-freeze-stop`
- trigger:
  - candidate surface 중 pure bridge가 아닌 shell semantics가 발견됨
  - exact caller map이 너무 넓어져 import-source-only 규칙을 지킬 수 없음
- allowed path:
  - `Branch B`

### 8.5 `direct-import-b5-revert-stop`
- trigger:
  - B5 code batch 실패
  - deleted bridge 6개 중 일부만 제거된 split state
  - `blueprints.py` registration contract regression
- allowed path:
  - pre-B5 tree로 full revert 후 `W8-B6 -> W8-B7`

### 8.6 `bridge-scope-drift-stop`
- trigger:
  - `personal_board`, `orders`, `jobs`, `business_calendar`, `notifications`, `attachments`, `chat`, `channel`, platform cluster를 mainline에 끌어오려 함
  - import-source reroute를 넘는 feature refactor가 발생
- allowed path:
  - 해당 surface를 `W8-B6` defer row로만 기록

### 8.7 `legacy-import-nonzero-stop`
- trigger:
  - retired path가 product code 또는 non-deferred tests에 남아 있음
- allowed path:
  - same-batch fix-forward
  - 불가 시 revert-stop

### 8.8 `runtime-contract-regression-stop`
- trigger:
  - `APP_OK`, `verify_result`, focused pytest fail
  - failure가 bridge retirement와 직접 연관돼 same-batch fix가 불가능
- allowed path:
  - revert-stop 또는 partial closeout

## 9. Restart Minimum Input Set

### 9.1 공통 restart 입력
- current plan file
- latest completed Wave 8 run record
- `foms/platform/blueprints.py`
- live target bridge files
- latest `rg` snapshot
- current baseline status

### 9.2 Path-specific restart notes
- `Branch B`:
  - service compat pilot까지만 authoritative
  - direct-import family는 `W8-B6` status row를 truth로 삼고 별도 continuation decision 필요
- `Branch C`:
  - docs-only partial closeout
  - no code batch may resume without new approval or revised plan
- `service-compat-b3-revert-stop`:
  - pre-B3 tree 복구 증거와 failure summary가 restart input
- `direct-import-b5-revert-stop`:
  - pre-B5 tree 복구 증거와 candidate exclusion decision이 restart input

## 10. Execution Prompt Contract
Wave 8 실행 프롬프트는 아래를 반드시 강제해야 한다.

1. 현재 batch id와 branch를 먼저 선언한다.
2. 이번 turn의 allowed files / forbidden expansion을 먼저 적는다.
3. edit 전 `Direction Lock` 핵심 답(1, 4, 6, 7)을 짧게 적는다.
4. caller reroute는 import source line만 바꾼다고 명시한다.
5. delete batch는 반드시 `rg zero-import`와 retirement sentinel 계획을 먼저 적는다.
6. batch 종료 시 run record를 same-turn에 쓴다.
7. failure가 나면 silent retry 대신 `stop label` 또는 `revert label`을 선언한다.

## 11. Final Audit Loop Hard-Stop Policy
Wave 8 계획서 감리는 아래 규칙으로만 반복한다.

1. audit round는 최대 **3번**이다.
2. round 1은 **parallel audit**로 한다.
   - `code-reviewer`
   - `evolution-architect`
   - `grand-develop-master`
3. finding은 line-by-line가 아니라 **finding family**로 묶는다.
4. `LOW`는 freeze blocker가 아니다.
5. `MEDIUM`도 local wording, table phrasing, 중복 서술 수준이면 freeze blocker가 아니다.
6. round 1 뒤에는 **holistic patch 1회**만 허용한다. local 미세 패치 반복은 금지다.
7. round 2는 **final hard audit**이다. 아래 조건을 모두 만족하면 즉시 `freeze-ready`로 종료한다.
   - `HIGH = 0`
   - batch legality를 바꾸는 `MEDIUM = 0`
   - 새로운 scope drift 없음
8. round 2에서 남는 것이 wording / formatting / optional note 수준이면 더 이상 round 3를 열지 않고 종료한다.
9. round 3는 **법적 batch order / stop semantics / scope fence**를 깨는 새 `HIGH` 또는 구조적 `MEDIUM`이 있을 때만 연다.
10. round 3 이후에도 blocker가 남으면 `freeze-ready`가 아니라 `needs-new-plan`으로 종료한다. round 4는 없다.

## 12. Completion Criteria

### 12.1 Full closeout
아래를 모두 만족하면 Wave 8 full closeout이다.

- B3에서 service compat shim 4개가 제거됨
- B5에서 direct-import bridge 6개가 제거됨
- `foms/platform/blueprints.py`가 canonical `foms.*` import source를 직접 사용함
- retired path `rg`가 product code + non-deferred tests에서 0
- status register가 completed / defer / bridge-stuck row를 authoritative로 남김
- spec / archive / AI status sync 완료

### 12.2 Partial closeout
아래 중 하나면 partial closeout이다.

- service compat pilot까지만 완료되고 direct-import family는 defer
- freeze-stop 또는 revert-stop 후 status register만 남김
- unresolved row가 많아 dedicated continuation plan이 필요함

### 12.3 Explicit non-goal
아래는 Wave 8 완료 조건이 아니다.

- `personal_board` shell collapse
- `orders` shell collapse
- `jobs` dotted string retirement
- `business_calendar` root implementation 이동
- packaging reopen
