# Strict Final Canonical Tree 100% Execution Plan
> 작성일: 2026-04-15 | 상태: GDM 총감리 완료 / freeze-ready
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> 직접 선행 closeout: `docs/plans/2026-04-15-post-wave9-program3-overlay-minimization-closeout-run-record.md`, `docs/plans/2026-04-15-post-wave9-program4-final-checklist-closeout-run-record.md`
> 필수 조사 입력: `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/harness/policy/DECISIONS.md`
> live truth anchor: repo root physical tree, `foms/`, `templates/`, `static/`, `apps/`, root `services/`, root standalone helper files

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `§2.2.1 Final canonical tree`를 **문자 그대로 가능한 한 엄격하게** 달성하기 위한 별도 실행 계획서다.

이 계획은 `post-Wave9 endgame`을 부정하지 않는다.

- `post-Wave9 endgame`은 packaging reopen 없이 canonical owner, overlay 최소화, defer 분류를 닫은 구조 closeout이었다.
- 이 계획의 목표는 그보다 더 좁고 더 엄격하다.
- 즉, 이미 닫힌 endgame 위에서 **남아 있는 물리 구조 불일치**만 다시 여는 strict follow-up tranche다.

이 plan이 닫아야 하는 것은 아래 여섯 축이다.

1. `§2.2.1`에 없는 root artifact를 root에서 제거한다.
2. `§2.2.2 Transition overlay` 항목을 closeout 시점에 0으로 만든다.
3. `§2.2.1`에 그려진 canonical directory node를 실제 물리 구조로 만든다.
4. canonical code가 root helper, root template, root namespace debt에 기대지 않도록 만든다.
5. clean-room 기준에서 exact-match를 재현한다.
6. 다음 LLM이 이 문서만 읽고 바로 batch 실행에 들어갈 수 있게 한다.

### 1.2 기능 요구사항
1. 최종 목표는 `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`의 `§2.2.1 Final canonical tree`와 physical tree를 최대한 1:1로 맞추는 것이다.
2. `apps/`, root `services/`, root standalone helper scripts, ambiguous top-level root(`src/`)는 최종 closeout 시 남을 수 없다.
3. 이 plan은 `src/foms`, `pyproject.toml`, packaging reopen을 다시 열지 않는다. Wave 9 `Option A explicit defer`는 유지한다.
4. 각 **code batch**는 반드시 한 risk axis, 한 file family만 다룬다.
5. docs-only freeze batch는 여러 family를 inventory할 수 있지만, 그 결과는 반드시 child batch 단위로 다시 분해되어야 한다.
6. 각 code batch의 기본 순서는 `freeze -> consumer reroute -> canonical owner materialize/extend -> zero-legacy verification -> old path retire`다.
7. root helper 제거를 위해 새 root shim, 새 fail-open import fallback, `try/except import` 우회는 금지한다.
8. canonical code(`foms/*`, canonical `templates/*`, canonical `static/*`)에서 root helper import는 closeout 시 0이어야 한다.
9. root template 직접 렌더는 closeout 시 0이어야 한다.
10. `foms/api/files`, `foms/api/measurement`, `templates/auth`, `static/js/{drawing,production,construction,cs,admin,auth}`, `static/css/{layout,components}`는 실제 directory node로 존재해야 한다.
11. root template cleanup은 예시가 아니라 **현재 root template 전체 ledger**를 기준으로 진행해야 한다.
12. `apps/` overlay 제거 전에는 active `apps/*.py` consumer와 nested `apps/api/**` bridge inventory/reroute batch가 별도로 잠겨 있어야 한다.
13. root residual artifact는 대표 예시가 아니라 **file-by-file disposition ledger**를 기준으로 처리해야 한다.
14. clean-room verification은 dirty worktree나 local cache(`__pycache__`, `.pytest_cache`, `.gstack`)에 의존하지 않아야 한다.
15. `§2.2.1`이 명시하지 않은 root artifact는 기본적으로 debt다. 예외는 reviewer 재량이 아니라 closed allowlist로만 허용한다.
16. git이 빈 디렉터리를 추적하지 못하는 경우, canonical directory materialization sentinel은 `B0`에서 하나로 고정한다.
17. "거의 맞음", "실질적으로 완료" 같은 표현은 금지한다. acceptance는 exact-match gate로만 판정한다.

### 1.2.1 Strictness definition
이 plan은 아래 정의를 authoritative하게 사용한다.

| ID | 이름 | 뜻 |
|------|------|------|
| `SF1` | `root-exact-match` | root에 남는 versioned artifact는 `§2.2.1` root set + 아래 closed repo-control allowlist만 허용한다. 임의 shortlist 확장은 금지다. |
| `SF2` | `directory-node-minimum` | `§2.2.1`에 그려진 directory node는 실제 존재해야 한다. 내부 파일은 더 많아도 되지만, 올바른 subtree 안에 있어야 한다. |
| `SF3` | `transition-overlay-zero` | `apps/`, root `services/`, root standalone helper, root template debt, root code root(`src/`)는 closeout 시 0이다. |
| `SF4` | `canonical-import-zero` | canonical code가 root helper를 import하거나 root template/file path에 runtime 의존하는 행위는 closeout 시 0이다. |
| `SF5` | `clean-room-proof` | 최종 acceptance는 clean worktree / clean-room clone / clean worktree clone에서 재현되어야 한다. |

**Closed repo-control allowlist**
- `.gitignore`
- `.gitattributes`
- `.dockerignore`
- `.gcloudignore`
- `.python-version`

위 다섯 항목 외의 root artifact는 "승인되면 남길 수 있음"이 아니라, 이동/삭제/별도 spec clarification 중 하나로 처리해야 한다.

### 1.3 Out of scope / freeze
이 plan은 strict physical-tree 정렬만 다룬다. 아래는 본편이 아니다.

- 새 기능 개발, route behavior 변경, JSON shape 변경
- DB schema 변경, Alembic revision 추가
- `src/foms` packaging migration, `pyproject.toml` 도입
- `business_calendar` 같은 explicit exception의 기능 확장
- spec을 느슨하게 바꿔 debt를 숨기는 행위
- local cache 정리만으로 completion을 주장하는 행위

추가 규칙:

- 어떤 batch라도 **strict tree 정렬에 예정된 import/path move를 넘어서는 product behavior 변경**이 필요해지면 해당 batch는 중단하고 별도 RCA/fix batch로 분리한다.
- 어떤 batch라도 root helper를 그대로 canonical subtree로 복사만 하고 caller를 안 바꾸면 실패다.
- 어떤 batch라도 새 wrapper를 남기고 retirement condition을 기록하지 않으면 실패다.

**allowed planned runtime-equivalent changes**
- import source reroute
- template path relocation with 동일 route/response contract 유지
- package directory normalization with public import/export contract 유지
- overlay wrapper retirement after all consumers are canonical owner로 재지정된 경우

### 1.4 Predecessor reconciliation
1. Program 3 closeout은 overlay를 최소화했지, literal zero로 만들지 않았다.
2. Program 4 closeout은 post-Wave9 master order 완료를 선언했지, `§2.2.1` physical tree exact-match를 선언하지는 않았다.
3. 따라서 이 plan은 predecessor를 무효화하지 않고, remaining strict debt register만 별도 tranche로 닫는다.
4. Wave 9의 `Option A explicit defer`는 유지된다. 이 plan은 packaging이 아니라 root/canonical physical alignment를 다룬다.

## 2. Current Strict Gap Truth — 현재 strict gap 근거

### 2.1 Transition overlay가 아직 남아 있음
현재 root에는 아래 overlay가 여전히 존재한다.

| 항목 | 상태 |
|------|------|
| `apps/` | 존재 |
| root `services/` | 존재 |
| `src/` | 존재 |

이는 `§2.2.2 Transition overlay` 상태이며 final tree가 아니다.

### 2.2 필수 canonical directory node 누락
현재 live tree에는 아래 `§2.2.1` directory node가 실제로 없다.

| 경로 | 현재 |
|------|------|
| `foms/api/files` | 없음 (`foms/api/files.py` flat module) |
| `foms/api/measurement` | 없음 (`foms/api/measurement.py` flat module) |
| `templates/auth` | 없음 |
| `static/js/drawing` | 없음 |
| `static/js/production` | 없음 |
| `static/js/construction` | 없음 |
| `static/js/cs` | 없음 |
| `static/js/admin` | 없음 |
| `static/js/auth` | 없음 |
| `static/css/layout` | 없음 |
| `static/css/components` | 없음 |

### 2.3 Root template namespace debt가 아직 live다
현재 root plain template file inventory는 아래 25개다.

- `add_order.html`
- `add_user.html`
- `admin.html`
- `change_logs.html`
- `chat.html`
- `edit_order.html`
- `edit_user.html`
- `error_404.html`
- `error_500.html`
- `index.html`
- `layout.html`
- `login.html`
- `map_view.html`
- `metropolitan_dashboard.html`
- `profile.html`
- `regional_dashboard.html`
- `register.html`
- `security_logs.html`
- `self_measurement_dashboard.html`
- `storage_dashboard.html`
- `trash.html`
- `upload.html`
- `user_list.html`
- `wdplanner_setup.html`
- `wdplanner.html`

현재 확인된 root-template render callsite는 14건이다.

### 2.4 Canonical code -> root helper import debt가 아직 live다
현재 canonical code에는 아래 root helper import가 남아 있다.

| root helper family | 대표 consumer |
|------|------|
| `constants.py` | `foms/platform/app_factory.py`, `foms/services/channel_event_payloads.py`, `foms/api/orders/status.py` 등 |
| `foms_address_converter.py` | `foms/api/measurement.py`, `foms/api/erp_map.py`, `foms/api/orders/nearby.py`, `foms/services/jobs/tasks.py` |
| `foms_map_generator.py` | `foms/api/erp_map.py`, `foms/api/measurement_map.py` |
| `map_config.py` | `foms/api/address.py` |
| `erp_automation.py` | `foms/api/erp_orders_structured.py` |
| `erp_order_text_parser.py` | `foms/api/erp_orders_structured.py` |
| `simple_backup_system.py` | `foms/api/backup.py` |

현재 확인된 canonical/root import line 수는 28건이다.

### 2.5 Root debt ledger — file-by-file disposition baseline
아래 ledger는 `B1`에서 authoritative하게 재잠그며, closeout 시 row가 남아 있으면 실패다.

| 항목 | provisional target / disposition |
|------|------|
| `.cursorrules` | `.cursor/rules/`로 흡수하거나 dead-proof 후 삭제 |
| `app.yaml` | consumer proof 후 삭제 또는 `docs/context/manual-artifacts/legacy-deploy/` |
| `build_wdplanner.bat` | `scripts/maintenance/build_wdplanner.bat` |
| root `config/` | live consumer 있으면 canonical subtree로 이동, 없으면 삭제 |
| `constants.py` | `B2/B3`에서 분해 후 root 제거 |
| `erp_automation.py` | `foms/services/orders/erp_automation.py` |
| `erp_order_text_parser.py` | `foms/services/orders/order_text_parser.py` |
| `findings.md` | `docs/context/analysis/findings.md` |
| `foms_address_converter.py` | `foms/services/common/address_converter.py` |
| `foms_address_learning_data.json` | `data/address/foms_address_learning_data.json` |
| `foms_address_learning.py` | `scripts/ops/address_learning.py` 또는 dead-proof 후 삭제 |
| `foms_advanced_address_processor.py` | `scripts/ops/advanced_address_processor.py` 또는 dead-proof 후 삭제 |
| `foms_map_generator.py` | `foms/services/common/map_generator.py` |
| `foms.dump` | `data/dumps/foms.dump` |
| `furniture_orders.db` | `data/localdb/furniture_orders.db` |
| `map_config.py` | `foms/services/common/geocode_config.py` |
| `menu_config.json` | `data/admin/menu_config.json` |
| `MIGRATION_GUIDE_RAILWAY.md` | `docs/guides/MIGRATION_GUIDE_RAILWAY.md` |
| `MIGRATION_RAILWAY_R2.md` | `docs/guides/MIGRATION_RAILWAY_R2.md` |
| `migration_ready.db` | `data/localdb/migration_ready.db` |
| `ops_browser_qa.db` | `data/localdb/ops_browser_qa.db` |
| `progress.md` | `docs/context/analysis/progress.md` |
| `pyrightconfig.json` | `tools/harness/pyrightconfig.json` 또는 dead-proof 후 삭제 |
| `railway_bootstrap.py` | `scripts/ops/railway_bootstrap.py` |
| `RAILWAY_ENV_VARS.md` | `docs/guides/RAILWAY_ENV_VARS.md` |
| `runtime.txt` | consumer proof 후 삭제 또는 `docs/context/manual-artifacts/legacy-deploy/` |
| `simple_backup_system.py` | `B5C`에서 runtime 분리 후 root 제거 |
| `start_foms_utf8.bat` | `scripts/maintenance/start_foms_utf8.bat` |
| `task_plan.md` | `docs/context/analysis/task_plan.md` |
| `TEST_GUIDE.md` | `docs/guides/TEST_GUIDE.md` |
| `apps/` | `B11A/B11B`에서 reroute 후 root 제거 |
| root `services/` | `B11C`에서 retire |
| `src/` | `B11D`에서 `Add In Program/WDPlanner/legacy-mobile-prototype/`로 이동 후 root 제거 |

### 2.6 Clean-room 관점과 local noise를 분리해야 함
아래는 repository 구조 debt와 동일하게 취급하면 안 된다.

- `.git/`
- `__pycache__/`
- `.pytest_cache/`
- `.gstack/`

반대로, `SF1` closed allowlist 바깥의 root artifact는 strict debt다.

## 3. Strict Gap Scoreboard — 종료 조건용 계기판

`B0`에서 아래 baseline을 다시 잠근다. provisional baseline은 현재 감사 기준이다.

| Metric | 뜻 | provisional baseline | closeout target |
|------|------|------|------|
| `SG1` | overlay root count (`apps`, root `services`, `src`) | 3 | 0 |
| `SG2` | canonical -> root helper import line count | 28 | 0 |
| `SG3` | missing canonical directory node count | 11 | 0 |
| `SG4` | root template render debt callsite count | 14 | 0 |
| `SG5` | root non-spec tracked artifact count (`SF1` allowlist와 local noise 제외) | 33 | 0 |
| `SG6` | clean-room exact-match diff count | 미측정 | 0 |
| `SG7` | root template file count (`templates/` root plain files) | 25 | 0 |

추가 규칙:

- 각 code batch는 최소 하나 이상의 `SG*`를 순감시켜야 한다.
- 어떤 batch라도 `SG*`를 늘리면 실패다.
- `SG5`는 이동 또는 삭제로만 감소로 인정한다.

## 4. Fixed Execution Pipeline — 고정 실행 순서

### 4.1 Master order
Strict canonical tranche는 아래 순서만 합법이다.

1. `SFC-B0` Readiness gate + strict interpretation lock
2. `SFC-B1` Exact gap inventory + scoreboard freeze
3. `SFC-B2` Root constants/config family freeze
4. `SFC-B3` Root constants/config retirement
5. `SFC-B4` Root helper family freeze
6. `SFC-B5A` Address/map helper retirement
7. `SFC-B5B` ERP helper retirement
8. `SFC-B5C` Backup/helper retirement
9. `SFC-B6` Template namespace freeze
10. `SFC-B7` Template namespace relocation
11. `SFC-B8` Static namespace materialization
12. `SFC-B9` API package-shape normalization
13. `SFC-B10A` Root manuals/scripts/data artifact liquidation
14. `SFC-B10B` Root deploy/config/tooling artifact liquidation
15. `SFC-B11A` Apps consumer migration freeze + reroute
16. `SFC-B11B` Apps overlay retirement
17. `SFC-B11C` Root `services/` overlay retirement
18. `SFC-B11D` `src/` retirement
19. `SFC-B12` Clean-room exact-match audit + closeout

### 4.2 Branch / stop semantics
- `Branch A full path`: `B0 -> B12` 전체 실행
- `Branch B docs-stop`: `B0`에서 strict interpretation이 모호하거나 `SF1` closed allowlist 밖의 mandatory root artifact가 발견되면 코드 변경 금지, docs-only로 정지
- `Branch C revert-stop`: 어떤 code batch라도 `allowed planned runtime-equivalent changes`를 넘어서는 product behavior 변경이 필요해지면 해당 배치 이전 tree로 되돌리고 docs/status만 남긴다
- `Branch D split-stop`: 한 batch가 두 family를 건드리기 시작하면 즉시 둘로 분리한다

### 4.3 Naming contract
각 배치 run record는 아래 패턴으로 만든다.

- `docs/plans/2026-04-15-strict-final-canonical-tree-batch0-readiness-gate-run-record.md`
- `docs/plans/2026-04-15-strict-final-canonical-tree-batch1-gap-inventory-run-record.md`
- 이후 동일 패턴

## 5. Batch Catalog

| Batch | 성격 | 핵심 산출물 | 선행 조건 |
|------|------|------|------|
| `SFC-B0` | docs / gate | strict interpretation, closed root allowlist, sentinel policy, clean-room verify method | 이 plan 승인 |
| `SFC-B1` | docs | authoritative gap inventory, `SG*` baseline, family queue map, root debt ledger refresh | `B0` |
| `SFC-B2` | docs | `constants.py` symbol family map, target canonical homes, no-go rules | `B1` |
| `SFC-B3` | code | `constants.py` retirement, consumer reroute, root import zero for constants family | `B2` |
| `SFC-B4` | docs | helper family map: address/map, ERP, backup, residual root config/data/docs/scripts | `B3` |
| `SFC-B5A` | code | `foms_address_converter.py`, `foms_map_generator.py`, `map_config.py` retirement | `B4` |
| `SFC-B5B` | code | `erp_automation.py`, `erp_order_text_parser.py` retirement | `B4` |
| `SFC-B5C` | code | `simple_backup_system.py` runtime decoupling + root shim retirement | `B4` |
| `SFC-B6` | docs | exhaustive root template ledger, caller map, target namespace map, partial/shared policy | `B5A~C` |
| `SFC-B7` | code | root template physical relocation, render_template caller update, `templates/auth` materialize, `SG7` 감소 | `B6` |
| `SFC-B8` | code/docs | missing static directory materialization, sentinel policy application, asset relocation if needed | `B7` |
| `SFC-B9` | code | `foms/api/files/`, `foms/api/measurement/` package normalization | `B8` |
| `SFC-B10A` | code/docs | root manuals/scripts/data/db/dump artifact liquidation | `B9` |
| `SFC-B10B` | code/docs | root deploy/config/tooling artifact liquidation | `B10A` |
| `SFC-B11A` | docs/code | `apps/*.py` + `apps/api/**` inventory, target canonical owner freeze, caller reroute | `B10B` |
| `SFC-B11B` | code/docs | `apps/` overlay retirement | `B11A` |
| `SFC-B11C` | code/docs | root `services/` overlay retirement | `B11B` |
| `SFC-B11D` | code/docs | `src/` relocation/retirement | `B11C` |
| `SFC-B12` | docs/verify | clean-room exact-match proof, `SG* == 0`, final closeout memo | `B11D` |

## 6. Batch Runbook — 실제 실행 규칙

### 6.1 `SFC-B0` — Readiness gate + strict interpretation lock
**목표**
- `SF1`~`SF5`를 execution-grade로 잠근다.
- closed root allowlist를 재확인한다.
- empty directory sentinel policy를 확정한다.

**허용 변경**
- `docs/plans/*`, `docs/AI_STATUS.md`(필요 시), `docs/ARCHIVE_INDEX.md`

**금지 변경**
- runtime code
- template/static/file move
- tests 추가/변경

**실행 단계**
1. `§2.2.1`, `§2.2.2`, Program 3 closeout, Program 4 closeout을 다시 연다.
2. root non-spec artifact를 `closed allowlist`, `canonical move`, `quarantine/data/docs/scripts move`, `delete-after-proof`, `requires-spec-clarification` 다섯 bucket으로 분류한다.
3. `SF1` closed allowlist 밖의 artifact가 mandatory라고 주장되면 `Branch B docs-stop`으로 판정한다.
4. empty directory sentinel policy를 `.gitkeep` 또는 local `README.md` 하나로 고정한다.
5. clean-room verification 방식을 `git worktree` 기반으로 고정한다.
6. `Branch A/B/C`를 판정한다.

**검증**
- docs-only batch
- 아래 문장을 반드시 포함한다: `closed root allowlist is immutable for the rest of this tranche`

### 6.2 `SFC-B1` — Exact gap inventory + scoreboard freeze
**목표**
- strict gap을 family 단위로 authoritative하게 잠근다.

**실행 단계**
1. root tree, `foms/`, `templates/`, `static/`, `apps/`, root `services/`, `src/`를 재스캔한다.
2. `SG1`~`SG7` baseline을 수치로 적는다.
3. 아래 family register를 만든다.
   - constants/config family
   - address/map helper family
   - ERP helper family
   - backup/helper family
   - template namespace family
   - static namespace family
   - API package-shape family
   - root manuals/scripts/data artifact family
   - root deploy/config/tooling artifact family
   - apps consumer migration family
   - root `services/` retirement family
   - `src/` retirement family
4. `§2.5 root debt ledger`를 actual live tree 기준으로 보정한다.
5. 각 family에 `mainline` / `docs-stop` / `needs-split` 판정을 적는다.

### 6.3 `SFC-B2` — Root constants/config family freeze
**목표**
- `constants.py`를 한 번에 옮기지 말고 symbol family로 쪼개서 canonical home을 고정한다.

**authoritative target map**
- order status / bulk action enum -> `foms/services/orders/status_constants.py`
- file/chat/upload policy -> `foms/services/files/upload_policy.py`
- estimate/legal/payment text -> `foms/services/orders/estimate_defaults.py`
- storage path/runtime upload location -> `foms/services/files/storage_paths.py`

**금지**
- `constants.py`를 그대로 다른 위치로 rename만 하는 것
- consumer reroute 없이 re-export shim 추가

### 6.4 `SFC-B3` — Root constants/config retirement
**목표**
- `constants.py` root import를 0으로 만든다.

**필수 검증**
- `rg` 기준 canonical code의 `from constants import` / `import constants` 0
- `APP_OK`
- touched pytest families

### 6.5 `SFC-B4` — Root helper family freeze
**목표**
- helper/root residual debt를 **child batch용 입력 문서**로 잠근다. `B4`는 multi-family docs batch이지만, 실제 code execution은 `B5A/B5B/B5C/B10A/B10B` child batch로만 한다.

**authoritative family map**
- address/map: `foms_address_converter.py`, `foms_map_generator.py`, `map_config.py`
- ERP parse/automation: `erp_automation.py`, `erp_order_text_parser.py`
- backup runtime helper: `simple_backup_system.py`
- residual research/data/helper: `foms_address_learning.py`, `foms_advanced_address_processor.py`, `foms_address_learning_data.json`, `menu_config.json`, root `config/`
- residual script/manual/deploy/data artifacts: `build_wdplanner.bat`, `start_foms_utf8.bat`, `MIGRATION_GUIDE_RAILWAY.md`, `TEST_GUIDE.md`, `foms.dump`, `app.yaml`, `runtime.txt`, `railway_bootstrap.py`, `pyrightconfig.json` 등

### 6.6 `SFC-B5A` — Address/map helper retirement
**권장 canonical home**
- `foms/services/common/address_converter.py`
- `foms/services/common/map_generator.py`
- `foms/services/common/geocode_config.py`

**검증**
- canonical consumer에서 root import 0
- map/measurement/order nearby 관련 focused pytest
- `APP_OK`

### 6.7 `SFC-B5B` — ERP helper retirement
**권장 canonical home**
- `foms/services/orders/erp_automation.py`
- `foms/services/orders/order_text_parser.py`

**검증**
- `foms/api/erp_orders_structured.py` root import 0
- structured order 관련 focused pytest
- `APP_OK`

### 6.8 `SFC-B5C` — Backup/helper retirement
**권장 canonical home**
- `foms/services/admin/backup_service.py`

**추가 규칙**
- `scripts/ops/simple_backup_system.py`는 operator entrypoint로 남을 수 있으나, product runtime import target이 되어서는 안 된다.
- backup path(`backups/...`)는 operator concern과 runtime concern을 분리한다.

### 6.9 `SFC-B6` — Template namespace freeze
**목표**
- root template를 모두 분류하고 target namespace를 고정한다.

**필수 분류 축**
- context page -> `templates/<context>/`
- shared shell / partial -> `templates/partials/shared/`
- dead legacy page -> `delete-after-proof`

**exhaustive root template ledger baseline**
- orders-owned: `add_order.html`, `edit_order.html`, `index.html`, `trash.html`
- measurement-owned: `regional_dashboard.html`, `metropolitan_dashboard.html`, `self_measurement_dashboard.html`, `map_view.html`
- admin-owned: `admin.html`, `change_logs.html`, `security_logs.html`, `storage_dashboard.html`, `upload.html`, `add_user.html`, `edit_user.html`, `user_list.html`
- auth-owned: `login.html`, `register.html`, `profile.html`
- channel-owned: `chat.html`
- wdcalculator-owned: `wdplanner.html`, `wdplanner_setup.html`
- shared-shell/errors: `layout.html`, `error_404.html`, `error_500.html`

**대표 target map**
- `login.html`, `register.html` -> `templates/auth/`
- `admin.html` -> `templates/admin/`
- `wdplanner.html`, `wdplanner_setup.html` -> `templates/wdcalculator/`

**shared-shell/error rule**
- `templates/partials/shared/`는 spec상 cross-context partial 전용이므로, `layout.html`, `error_404.html`, `error_500.html` 같은 full-page/shared-shell template를 그 위치로 그대로 이동하는 것은 금지한다.
- `B6`는 이 셋에 대해 아래 둘 중 하나를 반드시 선택해야 한다.
  1. shared partial + context-owned final template로 분해한다.
  2. spec clarification 없이는 legal home이 없다고 판정하고 `Branch B docs-stop`으로 내린다.

**필수 산출물**
- file-by-file target-home ledger
- current render caller ledger
- dead legacy page 판정 row가 있으면 consumer proof까지 포함

### 6.10 `SFC-B7` — Template namespace relocation
**목표**
- root template file을 실제로 없애고 namespaced path만 남긴다.

**검증**
- root `templates/*.html` debt file 0
- root template render callsite 0
- `templates/auth` 존재
- `SG7 == 0`
- page smoke / focused pytest / `APP_OK`

### 6.11 `SFC-B8` — Static namespace materialization
**목표**
- 누락된 `static/js/*`, `static/css/*` directory node를 materialize한다.

**추가 규칙**
- empty dir tracking은 `B0`에서 고정한 sentinel policy를 따른다.
- 단순 placeholder만 만들 경우에도 왜 비어 있는지 run record에 남긴다.
- 이미 다른 namespace에 있는 JS/CSS가 해당 context 소유라면 same-batch에서 옮긴다.

### 6.12 `SFC-B9` — API package-shape normalization
**목표**
- `foms/api/files.py`, `foms/api/measurement.py`를 `§2.2.1` tree 그대로 package directory로 바꾼다.

**authoritative target shape**
- `foms/api/files/__init__.py`
- `foms/api/files/routes.py` <- current `foms/api/files.py` body
- `foms/api/measurement/__init__.py`
- `foms/api/measurement/routes.py` <- current `foms/api/measurement.py` body
- `foms/api/measurement/map.py` <- current `foms/api/measurement_map.py` body if still measurement-owned after `B6/B7`

**추가 규칙**
- public import contract가 있으면 `__init__.py`에서 canonical export를 유지하되, root/flat fallback은 남기지 않는다.
- package-shape batch와 기능 변경 batch를 섞지 않는다.

### 6.13 `SFC-B10A` — Root manuals/scripts/data artifact liquidation
**목표**
- manual/script/data/db/dump artifact를 root에서 몰아낸다.

**authoritative scope**
- `build_wdplanner.bat`
- `start_foms_utf8.bat`
- `findings.md`
- `progress.md`
- `task_plan.md`
- `MIGRATION_GUIDE_RAILWAY.md`
- `MIGRATION_RAILWAY_R2.md`
- `RAILWAY_ENV_VARS.md`
- `TEST_GUIDE.md`
- `foms.dump`
- `furniture_orders.db`
- `migration_ready.db`
- `ops_browser_qa.db`
- `foms_address_learning_data.json`
- `menu_config.json`

### 6.14 `SFC-B10B` — Root deploy/config/tooling artifact liquidation
**목표**
- deploy/config/tooling root debt를 root에서 몰아낸다.

**authoritative scope**
- `.cursorrules`
- root `config/`
- `app.yaml`
- `runtime.txt`
- `pyrightconfig.json`
- `railway_bootstrap.py`

**추가 규칙**
- consumer proof 없이 삭제 금지
- `SF1` closed allowlist에 새 root tooling file을 추가하는 방식으로 회피 금지

### 6.15 `SFC-B11A` — Apps consumer migration freeze + reroute
**목표**
- `apps/` 제거 전에 live consumer를 정확히 잠그고 canonical target으로 reroute한다.

**authoritative current consumer set**
아래 embedded list는 현재 baseline이며, `B11A` 시작 시 아래 PowerShell inventory와 1:1 일치해야 한다. 일치하지 않으면 reroute 전에 ledger부터 갱신한다.

```powershell
Get-ChildItem apps -Recurse -File |
  Where-Object { $_.Extension -eq '.py' -and $_.FullName -notmatch '__pycache__' } |
  ForEach-Object { $_.FullName.Replace((Get-Location).Path + '\','') }
```

- `apps/auth.py`
- `apps/dashboards.py`
- `apps/order_pages.py`
- `apps/order_edit.py`
- `apps/order_trash.py`
- `apps/user_pages.py`
- `apps/storage_dashboard.py`
- `apps/excel_import.py`
- `apps/admin.py`
- `apps/erp_dashboard.py`
- `apps/erp_as_page.py`
- `apps/erp_construction_page.py`
- `apps/erp_drawing_workbench.py`
- `apps/erp_history_page.py`
- `apps/erp_shipment_page.py`
- `apps/erp.py`
- `apps/wdplanner_page.py`
- `apps/api/__init__.py`
- `apps/api/attachments.py`
- `apps/api/backup.py`
- `apps/api/channel_functions.py`
- `apps/api/channel_integration.py`
- `apps/api/channel_wam.py`
- `apps/api/channel_webhooks.py`
- `apps/api/debug.py`
- `apps/api/erp_estimates.py`
- `apps/api/erp_map.py`
- `apps/api/erp_orders_as.py`
- `apps/api/erp_orders_blueprint.py`
- `apps/api/erp_orders_completion.py`
- `apps/api/erp_orders_confirm.py`
- `apps/api/erp_orders_construction.py`
- `apps/api/erp_orders_cs.py`
- `apps/api/erp_orders_draftsman.py`
- `apps/api/erp_orders_drawing.py`
- `apps/api/erp_orders_production.py`
- `apps/api/erp_orders_revision.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/erp_shipment_settings.py`
- `apps/api/events.py`
- `apps/api/notifications.py`
- `apps/api/orders/__init__.py`
- `apps/api/quest.py`
- `apps/api/tasks.py`
- `apps/api/wdcalculator.py`
- `apps/api/attachments_internal/*`
- `apps/api/chat/*`

**추가 규칙**
- `apps/` consumer reroute는 template relocation과 constants/helper retirement 이후에만 시작한다.
- 각 file 또는 subpackage family의 target canonical owner를 row로 잠그고 same-batch 또는 next-batch reroute만 허용한다.
- embedded inventory와 live inventory가 다르면 `B11A`는 먼저 inventory refresh run record를 남기고 나서만 reroute를 시작한다.
- `apps/api/**`는 아래 child family로 다시 나눠 잠근다.
  - `apps/api/attachments_internal/*`
  - `apps/api/chat/*`
  - `apps/api/orders/__init__.py`
  - `apps/api/channel_*`
  - `apps/api/erp_*`
  - `apps/api/{attachments,backup,debug,events,notifications,quest,tasks,wdcalculator}.py`

### 6.16 `SFC-B11B` — Apps overlay retirement
**목표**
- `apps/`를 root에서 제거한다.

**추가 규칙**
- `B11A` reroute ledger가 100% 닫히기 전에는 실행 불가다.
- top-level `apps/*.py`와 nested `apps/api/**` child family가 모두 0이 되기 전에는 `apps/` directory removal을 선언할 수 없다.

### 6.17 `SFC-B11C` — Root `services/` overlay retirement
**목표**
- root `services/`를 root에서 제거한다.

**authoritative input**
- current root `services/` file inventory 전체
- remaining imports / runtime string debt register

**추가 규칙**
- `services/` directory removal은 `rg` 기준 live import 0 이후만 허용한다.
- `business_calendar` 등 prior explicit exception이 남아 있으면 strict closeout은 실패이며 별도 clarification 없이는 `B12`로 갈 수 없다.

### 6.18 `SFC-B11D` — `src/` retirement
**목표**
- `src/`를 root에서 제거한다.

**추가 규칙**
- `src/README.md`의 분류 근거를 이어받아 `Add In Program/` 또는 approved non-product home으로 병합/이동/삭제한다.
- root `src/`를 남긴 채 strict closeout을 선언할 수 없다.

### 6.19 `SFC-B12` — Clean-room exact-match audit + closeout
**목표**
- dirty local cache와 무관하게 strict completion을 증명한다.

**실행 단계**
1. clean-room worktree를 만든다.
2. root tree를 `§2.2.1` + `SF1` closed allowlist와 대조한다.
3. `SG1`~`SG7`를 다시 측정한다.
4. `APP_OK`, `verify_result.py --json`, focused/full pytest policy를 실행한다.
5. spec / archive / AI_STATUS sync 필요 여부를 기록한다.

**PowerShell clean-room recipe**
```powershell
$verify = Join-Path (Get-Location) '.tmp_strict_tree_verify'
git worktree remove --force $verify 2>$null
git worktree prune
if (Test-Path $verify) { Remove-Item -Recurse -Force $verify }
git worktree add $verify HEAD
Set-Location $verify
$actualRoot = Get-ChildItem -Force -Name | Where-Object { $_ -ne '.git' } | Sort-Object
$allowedRoot = @(
  '.agents','.claude','.cursor','.github','.vscode',
  '.dockerignore','.gcloudignore','.gitattributes','.gitignore','.python-version',
  'Add In Program','AGENTS.md','alembic.ini','app.py','backups','CLAUDE.md','data','db.py',
  'Dockerfile','docs','foms','migrations','models.py','Procfile','README.md',
  'railway.toml','railway-worker.toml','requirements.txt','run.py','SCheduler',
  'scripts','start.sh','static','templates','tests','tools','wdcalculator_db.py','wdcalculator_models.py'
) | Sort-Object
$rootDiff = Compare-Object $allowedRoot $actualRoot
if ($rootDiff) {
  $rootDiff | Format-Table -AutoSize
  throw 'STRICT_ROOT_DIFF_DETECTED'
}
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
```

**closeout 조건**
- `SG1 == 0`
- `SG2 == 0`
- `SG3 == 0`
- `SG4 == 0`
- `SG5 == 0`
- `SG6 == 0`
- `SG7 == 0`

## 7. Verification Matrix

| 축 | 최소 검증 |
|------|------|
| 공통 | `python -c "import app; print('APP_OK')"` |
| 공통 | `python tools/harness/verify_result.py --json` |
| import debt | 해당 family `rg` zero-result |
| templates | page smoke + template path grep zero-result |
| static | `Test-Path` + asset load smoke 또는 contract test |
| package shape | `Test-Path <dir> -PathType Container` + import smoke |
| root exactness | `Compare-Object $allowedRoot $actualRoot` zero diff |
| final | focused pytest + 필요 시 full `pytest tests` |

## 8. Run Record Contract
각 batch run record는 아래를 반드시 포함한다.

1. 사용한 입력 문서 exact path
2. 이번 batch가 다룬 family / risk axis
3. 변경 파일 목록
4. 금지 범위를 넘지 않았다는 증거
5. `SG*` before/after
6. `rg` / `Test-Path` / pytest / `APP_OK` 결과
7. 다음 legal batch
8. 남은 blocker와 defer 없음 여부

## 9. Clean-Room Acceptance Rules
1. final acceptance는 현재 dirty worktree가 아니라 clean-room에서 해야 한다.
2. `.git/`, cache dir, local editor/runtime generated dir는 clean-room baseline에 포함하지 않는다.
3. versioned root file이 `§2.2.1` 또는 `SF1` closed allowlist에 없으면 failure다.
4. subtree 내부 파일 증가는 허용하되, 올바른 canonical subtree 안에 있어야 한다.
5. final closeout 문서는 `strict physical-tree achieved` 또는 `failed with explicit blockers` 둘 중 하나만 말할 수 있다.

## 10. GDM / Autoplan Review Loop
이 plan 자체와 각 execution tranche는 아래 review loop를 따라야 한다.

### 10.1 Review dimensions
- CEO / scope review: 목표가 spec 회피가 아니라 literal exactness를 향하는지
- Eng review: batch order, import-reroute-first, test gate가 충분한지
- Design review: template/static namespace 이동이 사용자-facing regression 없이 설명되는지
- DevEx review: 다음 LLM이 질문 없이 실행할 수 있을 정도로 path, gate, stop condition이 닫혀 있는지
- GDM synthesis: root-cause only, simplification-first, hard-stop policy가 살아 있는지

### 10.2 Hard-stop policy
1. 감리 round는 최대 3번이다.
2. round 1은 신규 발견 자유.
3. round 2는 substantive gap patch만 허용한다.
4. round 3은 holistic accept/reject만 허용한다.
5. wording polish만으로 round를 추가하지 않는다.

### 10.3 Acceptance question set
각 round에서 아래 질문에 모두 yes여야 한다.

1. 이 plan만 읽고 다음 batch를 바로 실행할 수 있는가
2. batch 순서가 import debt -> namespace debt -> residual artifact -> apps/root-services/src eradication 순으로 잠겨 있는가
3. clean-room exact-match gate가 정의되어 있는가
4. `apps/`, root `services/`, `src/`, root helper, root template debt가 closeout target 0으로 고정되어 있는가
5. `apps/api/**`와 shared-shell/error template 처리까지 실행 경로가 닫혀 있는가
6. spec을 느슨하게 해 debt를 숨길 구멍이 없는가

## 11. LLM Operator Prompt Contract
다음 LLM이 첫 턴에 바로 사용할 수 있는 operator prompt는 아래와 같다.

```text
목표는 `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md`를 authoritative runbook으로 사용해 `§2.2.1 Final canonical tree`를 literal하게 맞추는 것이다.

반드시 먼저 읽을 것:
1. docs/AI_STATUS.md
2. docs/ARCHIVE_INDEX.md
3. docs/harness/policy/DECISIONS.md
4. docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md
5. docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md
6. 가장 최근 strict batch run record (없으면 `SFC-B0`부터 시작)

규칙:
- 한 턴에 한 batch, 한 risk axis, 한 family만 다룬다.
- root-cause only. 새 shim/fallback 금지.
- 먼저 consumer reroute, 마지막에 old root path retire.
- 각 배치 끝에 run record를 남기고 `SG*` before/after를 적는다.
- prior strict run record가 없으면 반드시 `SFC-B0` run record를 먼저 작성한다.
- final acceptance는 clean-room exact-match로만 판정한다.
```

## 12. Completion Signal
아래가 모두 충족되면 이 strict tranche는 완료다.

1. `§2.2.1` directory node 누락 0
2. `§2.2.2` overlay 잔존 0
3. canonical code의 root helper import 0
4. root template render debt 0
5. root non-spec tracked artifact 0 (`SF1` closed allowlist와 local noise 제외)
6. clean-room exact-match diff 0
7. root plain template file 0
8. final closeout run record가 `strict physical-tree achieved`를 선언
