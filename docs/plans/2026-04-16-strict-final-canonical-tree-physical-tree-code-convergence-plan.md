# Strict Final Canonical Tree — Physical Tree + Code Convergence Plan

> 작성일: 2026-04-16
> 상위 기준: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> 직접 선행 계획: `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md`, `docs/plans/2026-04-16-strict-final-canonical-tree-post-audit-correction-plan.md`
> 작성 근거: 2026-04-16 dual-spec hard audit, PAC full-suite/clean-room 재검증, live repo/workspace physical-tree 점검

## 1. Purpose

이 문서는 FOMS 저장소를 **두 스펙 기준으로 동시에** 닫기 위한 마지막 convergence runbook이다.

이번 tranche의 목표는 단순히 테스트 green이나 canonical subtree green이 아니다.
최종 목표는 아래 다섯 surface를 한꺼번에 닫는 것이다.

1. **spec-text exactness**
   - `2026-04-07`과 `2026-04-13`이 같은 저장소 상태를 가리키도록 문서 기준을 다시 잠근다.
2. **git-tracked tree exactness**
   - committed tree / clean-room clone이 최종 canonical tree와 1:1로 맞아야 한다.
3. **workspace physical-tree exactness**
   - 실제 FOMS 폴더(worktree) 안에도 generated cache, local DB/dump, stray temp tree가 남지 않아야 한다.
4. **code exactness**
   - context README, `static/js/runtime`, `foms/services/common`, `data/` ownership까지 스펙 문장과 코드가 맞아야 한다.
5. **proof exactness**
   - contract test, clean-room, workspace hygiene probe가 같은 최종 상태를 가리켜야 한다.

이 문서는 기존 strict/PAC plan을 부정하지 않는다.
다만 그 plan들이 닫지 못한 마지막 축인 **dual-spec reconciliation + workspace hygiene + code-owner exactness**만 다시 연다.

## 2. Current Findings Register

### 2.1 `PTC-S1` — Dual-spec root/taxonomy ambiguity

현재 `2026-04-07` §2.6의 root allowlist와 `2026-04-13` §2.2.1/§2.5 final-form tree는 완전히 같은 집합이 아니다.

대표 차이:

- `2026-04-07` §2.6은 root 허용 폴더를 `foms/`, `templates/`, `static/`, `migrations/`, `scripts/`, `docs/`, `.cursor/`, `.agents/`, `tools/` 중심으로 좁게 적는다.
- `2026-04-13` §2.2.1/§2.5는 여기에 `tests/`, `data/`, `.claude/`, `.github/`, `.vscode/`, `backups/`, `Add In Program/`, `SCheduler/`까지 final taxonomy로 포함한다.

결론:

- 현재 closeout proof는 `2026-04-13` 해석을 따르지만, 두 스펙을 literal하게 동시에 만족한다고 선언할 수는 없다.
- final closeout 전에는 **기존 controlling spec 두 개를 in-place sync** 해야 한다.

### 2.2 `PTC-R1` — Context-local README contract incomplete

`2026-04-13` FR20은 bounded context가 runtime module 3개 이상이거나 `web/api/services` 두 레이어 이상에 걸치면 **정확히 하나의 local `README.md`**를 두라고 요구한다.

현재 multi-layer context inventory:

- 이미 1개 존재: `orders`, `measurement`, `wdcalculator`
- 0개: `shipment`, `drawing`, `production`, `construction`, `cs`, `admin`, `auth`, `channel`, `files`, `notifications`

추가 문제:

- 기존 README 위치도 표준화되어 있지 않다.
- `orders`는 `foms/api/orders/README.md`, `measurement`는 `foms/web/measurement/README.md`, `wdcalculator`는 `static/js/wdcalculator/README.md`에 흩어져 있다.

결론:

- README 존재 여부만이 아니라 **README authoritative home**도 고정해야 한다.

### 2.3 `PTC-D1` — `data/` physical tree and runtime-output policy drift

현재 스펙은 `data/`를 versioned non-secret config/seed/reference로 제한하고, dump/backup/generated export는 `backups/` 또는 다른 runtime output으로 보내라고 말한다.

그런데 live repo/workspace 및 proof/documentation에는 아래 drift가 남아 있다.

- live local artifacts:
  - `data/dumps/foms.dump`
  - `data/localdb/furniture_orders.db`
  - `data/localdb/migration_ready.db`
  - `data/localdb/ops_browser_qa.db`
  - `data/ops_browser_qa.db`
- current scripts/docs:
  - `scripts/ops/sync_local_to_railway.ps1` → `data/dumps/foms.dump`
  - `scripts/migrations/migrate_local_to_remote.py` → `data/localdb/furniture_orders.db`
  - multiple migration/railway guides still describe repo-local dump/SQLite paths
- current proof:
  - `tests/contracts/runtime/foms_namespace_surface_tests.py` still materializes `data/dumps/` and `data/localdb/` as accepted canonical directories

결론:

- `data/`는 tracked reference/config zone으로 다시 좁혀야 한다.
- local dump/SQLite/browser QA DB는 repo tree 밖 또는 explicitly quarantined non-product runtime output으로 reroute해야 한다.

### 2.4 `PTC-W1` — Workspace physical-tree exactness not currently enforced

현재 repo workspace에는 아래 generated/runtime residue가 실제로 존재한다.

- root `.gstack/`
- root `.pytest_cache/`
- root `__pycache__/`
- recursive `__pycache__/` across `foms/`, `scripts/`, `tests/`, `tools/`, `migrations/`, `.cursor/`, `.claude/`
- temporary clean-room path `.tmp_strict_tree_verify` (verification-time residue 가능)

current proof gap:

- clean-room은 committed snapshot만 보므로 local ignored residue를 닫지 못한다.
- namespace tests와 clean-room helper는 `__pycache__`/hidden dirs를 대부분 무시한다.

결론:

- "committed tree는 맞음"과 "실제 FOMS 폴더가 깨끗함"을 분리해서 증명해야 한다.
- final closeout은 **workspace cleanup -> post-cleanup physical-tree audit**까지 포함해야 한다.

### 2.5 `PTC-P1` — Proof layer does not yet encode physical/code exactness

현재 proof는 아래를 충분히 잠그지 않는다.

- dual-spec root/taxonomy precedence
- FR20 local README exactness
- `data/`에 runtime output 금지
- workspace residue 금지
- `static/js/runtime/`와 `foms/services/common/`의 file-by-file owner justification

결론:

- proof gate를 먼저 강화하지 않으면 "green이지만 아직 exact하지 않은 상태"가 다시 반복된다.

### 2.6 `PTC-C1` — Code exactness for `runtime/common` families is not frozen

현재 `static/js/runtime/`와 `foms/services/common/`는 존재하지만, "각 파일이 정말 cross-context / domain-neutral 인가"를 증명하는 exact contract는 없다.

현재 inventory:

- `static/js/runtime/`
  - `column-resizer.js`
  - `common_utils.js`
  - `erp-mobile-shell.js`
  - `script.js`
  - `upload-progress.js`
- `foms/services/common/`
  - `address_ai_ops_loader.py`
  - `address_converter.py`
  - `business_calendar.py`
  - `geocode_config.py`
  - `map_generator.py`

결론:

- keep/move decision을 file-by-file로 freeze하고, domain-specific residue가 있으면 context owner로 내려야 한다.
- `business_calendar`은 기존 explicit out-of-scope exception으로 존중하되, 예외 항목임을 proof에 명시해야 한다.

## 3. Decision Lock

### 3.1 Spec sync rule

이번 tranche는 **새 sibling spec을 만들지 않는다**.

허용:

- `2026-04-07-repo-structure-governance_SPEC.md`
- `2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`

위 두 controlling spec을 **in-place** 갱신해서 같은 저장소 상태를 가리키게 만든다.

금지:

- 동일 범위의 새 상위 spec 추가
- "둘 다 맞다"는 식의 모호한 해석 메모만 남기고 실제 spec text를 그대로 두는 행위

두 controlling spec이 최종적으로 가리켜야 하는 root allowlist는 아래 exact set이다.

- top-level directories:
  - `.agents`
  - `.claude`
  - `.cursor`
  - `.github`
  - `.vscode`
  - `Add In Program`
  - `backups`
  - `data`
  - `docs`
  - `foms`
  - `migrations`
  - `SCheduler`
  - `scripts`
  - `static`
  - `templates`
  - `tests`
  - `tools`
- top-level files:
  - `.dockerignore`
  - `.gcloudignore`
  - `.gitattributes`
  - `.gitignore`
  - `.python-version`
  - `AGENTS.md`
  - `alembic.ini`
  - `app.py`
  - `CLAUDE.md`
  - `db.py`
  - `Dockerfile`
  - `models.py`
  - `Procfile`
  - `README.md`
  - `railway.toml`
  - `railway-worker.toml`
  - `requirements.txt`
  - `run.py`
  - `start.sh`
  - `wdcalculator_db.py`
  - `wdcalculator_models.py`

위 exact set 바깥의 root entry는 final closeout에서 금지다.

### 3.2 Exactness has two surfaces

이번 문서에서 final closeout은 아래 두 surface를 모두 요구한다.

1. **Committed exactness**
   - `HEAD` clean-room clone 기준 exact-match
2. **Workspace exactness**
   - 현재 작업 폴더 기준 generated/runtime residue가 cleanup 후 0

둘 중 하나만 green이면 closeout 불가다.

### 3.3 Local README authoritative home

FR20 local README는 context마다 **정확히 하나**만 허용한다.

표준 home:

- page-first contexts:
  - `orders`
  - `measurement`
  - `shipment`
  - `drawing`
  - `production`
  - `construction`
  - `cs`
  - `wdcalculator`
  - `admin`
  - `auth`
  - authoritative home = `foms/web/<context>/README.md`

- API-first contexts:
  - `channel`
  - `files`
  - `notifications`
  - authoritative home = `foms/api/<context>/README.md`

금지:

- 한 context 아래 multiple README
- `templates/`/`static/`에 context README를 두고 canonical entrypoint처럼 쓰는 패턴

### 3.4 `data/` policy

`data/`는 tracked versioned reference/config only다.

허용:

- `data/address/*`
- `data/admin/*`
- 기타 versioned non-secret JSON/seed/reference

금지:

- repo 안의 dump/backup/generated export
- repo 안의 SQLite / migration scratch DB
- repo 안의 browser-qa runtime DB
- `data/dumps/`
- `data/localdb/`
- `data/*.db`

local operator/runtime artifact는 아래 둘 중 하나만 허용한다.

1. repo 밖 external output root
2. explicitly quarantined non-product path that is not part of final exact workspace proof

이번 tranche의 기본값은 **repo 밖 external output root**다.

external output root contract:

- authoritative env var: `FOMS_RUNTIME_OUTPUT_ROOT`
- default when unset: `%USERPROFILE%\\FOMS-runtime`
- required child layout:
  - dumps: `%FOMS_RUNTIME_OUTPUT_ROOT%\\dumps\\foms.dump`
  - local sqlite: `%FOMS_RUNTIME_OUTPUT_ROOT%\\localdb\\furniture_orders.db`
  - migration scratch db: `%FOMS_RUNTIME_OUTPUT_ROOT%\\localdb\\migration_ready.db`
  - browser QA db: `%FOMS_RUNTIME_OUTPUT_ROOT%\\localdb\\ops_browser_qa.db`

금지:

- script/doc/test마다 서로 다른 repo-outside path를 따로 하드코딩하는 패턴
- repo 안 다른 하위 폴더로만 이동하고 externalization이라고 주장하는 패턴

### 3.5 Workspace residue policy

final workspace exactness에서 금지:

- `.gstack/`
- `.pytest_cache/`
- `.tmp_strict_tree_verify/`
- repo 어디든 `__pycache__/`

주의:

- 검증 도중 생기는 것은 허용되지만, **final audit 직전 cleanup 후 0**이어야 한다.
- "ignore 되어 있으니 괜찮다"는 closeout 근거가 아니다.

### 3.6 `runtime/common` family policy

`static/js/runtime/`과 `foms/services/common/`은 file-by-file allowlist + reason이 필요하다.

허용 기준:

- `static/js/runtime/*`: cross-context runtime primitive only
- `foms/services/common/*`: cross-context, domain-neutral helper only

금지 기준:

- 특정 단일 context policy
- screen-specific orchestration
- 특정 bounded context 용어가 주 책임으로 드러나는 코드

예외:

- `business_calendar` / `/calendar` 축은 기존 spec 예외를 유지한다.

## 4. Exact Target Ledgers

### 4.1 Root allowlist ledger

최종 committed tree root entry set은 아래 exact set이어야 한다.

- directories:
  - `.agents`
  - `.claude`
  - `.cursor`
  - `.github`
  - `.vscode`
  - `Add In Program`
  - `backups`
  - `data`
  - `docs`
  - `foms`
  - `migrations`
  - `SCheduler`
  - `scripts`
  - `static`
  - `templates`
  - `tests`
  - `tools`
- files:
  - `.dockerignore`
  - `.gcloudignore`
  - `.gitattributes`
  - `.gitignore`
  - `.python-version`
  - `AGENTS.md`
  - `alembic.ini`
  - `app.py`
  - `CLAUDE.md`
  - `db.py`
  - `Dockerfile`
  - `models.py`
  - `Procfile`
  - `README.md`
  - `railway.toml`
  - `railway-worker.toml`
  - `requirements.txt`
  - `run.py`
  - `start.sh`
  - `wdcalculator_db.py`
  - `wdcalculator_models.py`

명시적 금지 예시:

- `.gstack`
- `.pytest_cache`
- `.tmp_strict_tree_verify`
- root `__pycache__`
- root `*.db`
- root `*.dump`

### 4.2 README target ledger

| Context | Current state | Final target |
|------|------|------|
| `orders` | `foms/api/orders/README.md` only | move/normalize to `foms/web/orders/README.md`; exactly 1 |
| `measurement` | `foms/web/measurement/README.md` only | keep at `foms/web/measurement/README.md`; exactly 1 |
| `shipment` | none | add `foms/web/shipment/README.md` |
| `drawing` | none | add `foms/web/drawing/README.md` |
| `production` | none | add `foms/web/production/README.md` |
| `construction` | none | add `foms/web/construction/README.md` |
| `cs` | none | add `foms/web/cs/README.md` |
| `wdcalculator` | `static/js/wdcalculator/README.md` only | move/normalize to `foms/web/wdcalculator/README.md`; exactly 1 |
| `admin` | none | add `foms/web/admin/README.md` |
| `auth` | none | add `foms/web/auth/README.md` |
| `channel` | none | add `foms/api/channel/README.md` |
| `files` | none | add `foms/api/files/README.md` |
| `notifications` | none | add `foms/api/notifications/README.md` |

### 4.3 `data/` / runtime-output reroute ledger

| Current path / consumer | Final target |
|------|------|
| `scripts/ops/sync_local_to_railway.ps1` dump path | `%FOMS_RUNTIME_OUTPUT_ROOT%\\dumps\\foms.dump` |
| `scripts/migrations/migrate_local_to_remote.py` local sqlite path | `%FOMS_RUNTIME_OUTPUT_ROOT%\\localdb\\furniture_orders.db` |
| railway/migration guides using `data/dumps` or `data/localdb` | `FOMS_RUNTIME_OUTPUT_ROOT` contract docs |
| `tests/contracts/runtime/foms_namespace_surface_tests.py` `data/dumps` / `data/localdb` materialization | retire and replace with `data/` tracked-reference allowlist gate |
| `data/dumps/.gitkeep` | remove |
| `data/localdb/.gitkeep` | remove |
| `data/ops_browser_qa.db` | forbidden in repo |
| ignored local `*.db` / `foms.dump` inside repo | delete from repo tree before final audit |

### 4.4 Workspace hygiene ledger

| Residue | Final rule |
|------|------|
| root `.gstack/` | absent after final audit |
| root `.pytest_cache/` | absent after final audit |
| root `.tmp_strict_tree_verify/` | absent after final audit |
| repo-wide `__pycache__/` | absent after final audit |
| hidden/generated residue under canonical tree | absent after final audit |

### 4.5 `runtime/common` audit ledger

#### 4.5.1 `static/js/runtime/`

- `column-resizer.js`
- `common_utils.js`
- `erp-mobile-shell.js`
- `script.js`
- `upload-progress.js`

각 파일은 아래 셋 중 하나여야 한다.

1. keep in `runtime/`
2. move to `static/js/<context>/`
3. merge + retire

#### 4.5.2 `foms/services/common/`

- `__init__.py`
- `address_ai_ops_loader.py`
- `address_converter.py`
- `business_calendar.py`
- `geocode_config.py`
- `map_generator.py`

각 파일은 아래 셋 중 하나여야 한다.

1. keep in `common/`
2. move to canonical context package
3. explicit approved exception (only if already frozen by controlling spec)

## 5. Fixed Batch Order

### 5.1 `PTC-B0` — Authoring / truth freeze

docs-only.

필수 산출물:

- 본 계획서
- dual-spec hard audit findings freeze
- exact target ledgers

검증:

- no product code change

### 5.2 `PTC-B1` — Spec sync lock

docs-only.

필수 작업:

- `2026-04-07`과 `2026-04-13`의 root/taxonomy wording reconcile
- root allowlist와 final-form tree 관계를 한 문장으로 잠금
- `data/` policy를 두 spec 모두에서 같은 표현으로 정렬
- FR20 local README rule의 authoritative home rule 반영
- sibling spec 추가 금지

검증:

- docs diff only
- no new sibling spec

### 5.3 `PTC-B2` — Proof hardening for physical/code exactness

tests/tooling/docs. test red 허용.

필수 작업:

- `tests/contracts/runtime/foms_namespace_surface_tests.py`
  - existing PAC/SLG subtree closed-set gate 유지
  - existing forbidden-path gate 유지
  - existing `templates/partials/shared/*.html` exact allowlist gate 유지
  - root allowlist exact gate
  - FR20 local README exactness gate
  - `data/` tracked-reference allowlist gate
  - forbid `data/dumps`, `data/localdb`, `data/*.db`
  - `runtime/common` inventory allowlist gate
- `tools/harness/strict_canonical_b12_clean_room.ps1`
  - dual-spec synced root set 기준 반영
  - existing PAC/SLG subtree closed-set + forbidden-path + shared-partial exact allowlist 유지
  - `HEAD` clean-room exactness 유지
- new workspace hygiene proof helper
  - current repo root + recursive generated-dir probe
  - cleanup-after-verification contract

검증:

- red 허용
- focused pytest

### 5.4 `PTC-B3` — Context README canonicalization

docs/code batch.

필수 작업:

- §4.2 ledger대로 각 context README 배치
- legacy README home 이동
- exactly one README per multi-layer context
- README 내용은 목적, 주요 모듈, 읽기 순서, 금지 의존성을 모두 포함

검증:

- focused README/contract pytest
- `APP_OK`

### 5.5 `PTC-B4` — `data/` runtime-output retirement

code/docs/tests batch.

필수 작업:

- local dump/SQLite/browser QA DB output를 `FOMS_RUNTIME_OUTPUT_ROOT` contract로 reroute
- 관련 script/doc/test path 모두 동시 갱신
- repo tree에서 `data/dumps`, `data/localdb`, `data/*.db` 제거
- `data/`는 tracked reference/config only 상태로 축소

검증:

- focused script/path tests
- `APP_OK`
- `verify_result.py --json`

### 5.6 `PTC-B5` — Workspace artifact generator closure

code/tooling batch.

필수 작업:

- `.gstack/` repo-root 생성원 차단 또는 repo 밖으로 reroute
- verification/temp worktree residue cleanup contract 고정
- repo-wide `__pycache__`/`.pytest_cache` cleanup flow 고정
- final audit용 cleanup sequence 문서화 + 스크립트화

검증:

- generate -> cleanup -> zero-residue proof

### 5.7 `PTC-B6` — `runtime/common` code exactness

code/tests/docs batch.

필수 작업:

- `static/js/runtime/*` file-by-file keep/move/merge 결정
- `foms/services/common/*` file-by-file keep/move/exception 결정
- context-specific residue는 canonical owner로 이동
- `business_calendar` explicit exception을 proof/docs에 명시

검증:

- focused import/template/static tests
- `APP_OK`

### 5.8 `PTC-B7` — Final dual-surface closeout

closeout batch.

필수 작업:

- `HEAD` clean-room exactness
- current workspace cleanup
- post-cleanup workspace physical-tree audit
- final spec/code/proof/run-record sync

필수 green:

1. `python -c "import app; print('APP_OK')"`
2. `python tools/harness/verify_result.py --json`
3. `pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q`
4. `pytest tests -q`
5. `tools/harness/strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest`
6. workspace hygiene probe green
7. dual-spec 1:1 GDM audit green

## 6. GDM Ultra-Review Loop

각 batch는 아래 감리 loop를 통과해야만 다음 batch로 간다.

### 6.1 Reviewer roles

- `R1 Spec reviewer`
  - 두 controlling spec과 runbook acceptance 비교
- `R2 Physical-tree reviewer`
  - committed tree + workspace tree + cleanup residue 비교
- `R3 Code-owner reviewer`
  - README, `runtime/common`, path ownership, wrapper retirement condition 비교
- `R4 Proof reviewer`
  - tests/clean-room/workspace-hygiene false-green 여부 비교
- `GDM synthesis`
  - 위 4개 리뷰를 모아 stop/go 판정

### 6.2 Exit condition per batch

아래를 모두 만족해야 한다.

- High = 0
- Medium = 0
- batch acceptance 전부 충족
- run record와 실제 evidence 일치
- same-batch fix-forward 없이 다음 batch로 넘긴 TODO = 0

### 6.3 Hard stop

아래 중 하나라도 발생하면 즉시 중단한다.

- spec wording이 아직 충돌하는데 code closeout을 주장함
- committed tree는 green인데 workspace hygiene가 red
- workspace cleanup만으로 code/spec drift를 덮으려 함
- README exactness를 count-only로 green 처리함
- `data/` runtime output를 repo 안 다른 폴더로만 옮기고 해결이라고 주장함
- `runtime/common` file inventory를 rationale 없이 keep 처리함

## 7. Final 1:1 Acceptance Matrix

### 7.1 Spec-text exactness

- `2026-04-07`과 `2026-04-13`이 같은 root/taxonomy/data/README rule을 가리킨다.

### 7.2 Committed tree exactness

- `HEAD` clean-room green
- root allowlist exact match with §4.1
- `templates/`, `foms/web`, `foms/api`, `foms/services` subtree closed-set exact match
- no `apps/`, root `services/`, `src/`
- no forbidden `data/` runtime outputs
- README target homes exact

### 7.3 Workspace exactness

- root `.gstack/` 없음
- root `.pytest_cache/` 없음
- root `.tmp_strict_tree_verify/` 없음
- repo-wide `__pycache__/` 없음
- repo 안 local dump/SQLite/browser QA DB 없음

### 7.4 Code exactness

- README content/placement exact
- `static/js/runtime/*` file-by-file rationale complete
- `foms/services/common/*` file-by-file rationale complete
- explicit exceptions documented

### 7.5 Proof exactness

- `APP_OK`
- `verify_result.py --json`
- strict contract pytest
- full `pytest tests -q`
- clean-room `HEAD`
- workspace hygiene probe
- 기존 PAC/SLG closed-set/forbidden-path/shared-allowlist gate 유지 상태에서 green

## 8. First-Turn Operator Prompt

다음 LLM은 아래 순서로 착수한다.

1. `AGENTS.md`
2. `docs/ARCHIVE_INDEX.md`
3. `docs/harness/policy/DECISIONS.md`
4. `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
5. `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
6. `docs/plans/2026-04-16-strict-final-canonical-tree-post-audit-correction-plan.md`
7. `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md`

첫 응답에서 반드시 아래를 수행한다.

- 현재 상태를 `spec-text / committed-tree / workspace-tree / code / proof` 다섯 축으로 10줄 이내 요약
- `PTC-B1` scope / acceptance / stop rule 재진술
- 사용할 검증 명령과 cleanup 명령을 먼저 고정
- 바로 `PTC-B1` 착수

진행 규칙:

- blocker가 없으면 `PTC-B1 -> B2 -> B3 -> B4 -> B5 -> B6 -> B7` 자동 진행
- batch마다 GDM ultra-review loop 수행
- High/Medium이 남아 있으면 같은 batch에서 fix + 재감리
- 최종 closeout 전에는 반드시 `HEAD` clean-room과 current workspace physical-tree 둘 다 감사
