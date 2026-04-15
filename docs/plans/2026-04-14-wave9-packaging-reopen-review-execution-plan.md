# Wave 9 Packaging Reopen Review Execution Plan
> 작성일: 2026-04-14 | 상태: 최종 하드 감리 완료 / freeze-ready
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `app.py`, `foms/platform/app_factory.py`, `foms/services/jobs/tasks.py`, `migrations/env.py`, `tests/conftest.py`, `tests/test_app_bootstrap_contract.py`, `tools/harness/verify_result.py`, `Dockerfile`, `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml`, `.github/workflows/ci.yml`, `requirements.txt`
> 선행 wave: `docs/plans/2026-04-14-wave8-legacy-bridge-retirement-execution-plan.md`
> 핵심 선례: `docs/plans/2026-04-11-step8-optional-packaging-reevaluation-plan.md`, `docs/plans/2026-04-11-step8-batch77-preaudit-run-record.md`, `docs/plans/2026-04-11-step8-batch79-packaging-decision-run-record.md`, `docs/plans/2026-04-11-step8-batch80-closeout-run-record.md`, `docs/plans/2026-04-11-final-stabilization-reopen-plan.md`, `docs/harness/policy/DECISIONS.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 9 — Packaging reopen review**를 실제로 집행할 수 있는 LLM용 runbook이다.

헤더의 `상태`는 **plan maturity**를 뜻한다. 실제 execution state(`W9-B0` gating 중, readiness-gate-rejected closeout, explicit defer closeout, reopen-approved handoff)는 헤더가 아니라 각 batch run record와 closeout 문서가 authoritative truth다. `needs-new-plan`은 packaging verdict가 아니라 `§10` plan-audit termination state다.

Wave 9의 목적은 `src/foms`를 곧바로 실행하는 것이 아니라, 아래 아홉 가지를 **기계적으로** 닫는 것이다.

1. Step 8에서 defer한 packaging revisit가 **지금 legal하게 다시 열릴 수 있는지**부터 판정한다.
2. `app.py`, worker, Alembic, tests, harness, CI, Railway가 현재도 repo-root layout에 어떻게 결합돼 있는지 **live truth**로 다시 잠근다.
3. Wave 8 미종결 bridge debt를 Wave 9로 슬쩍 넘기지 못하게 **scope fence**를 문서로 고정한다.
4. Wave 9 본편은 **review / decision / handoff wave**로 유지하고, runtime path migration이나 metadata hardening을 같은 wave에서 바로 섞지 않는다.
5. Step 8 precedent 그대로 legal outcome을 **Option A / B / C** 세 갈래로만 고정한다.
6. `pyproject.toml`만 추가하는 false-confidence 경로를 명시적으로 차단한다.
7. `src/foms` 같은 physical move가 필요하다면 `must-update-together` 집합 전체를 한 번에 다룰 수 있는지부터 판정한다.
8. reopen이 승인되더라도 Wave 9 본편은 implementation을 수행하지 않고, **dedicated implementation handoff**만 남긴다.
9. 계획서 감리 루프도 무한 반복에 빠지지 않게, **parallel audit hard-stop policy**를 문서 안에 명시한다.

### 1.2 기능 요구사항
1. Wave 9의 authoritative truth는 항상 live `app.py`, live `foms/platform/app_factory.py`, live `foms/services/jobs/tasks.py`, live `migrations/env.py`, live deploy files, live test/harness files, accepted Step 8 evidence, accepted Wave 8 evidence다.
2. Wave 9는 **packaging reopen review**다. bridge retirement, canonicalization, page/API 리팩터, template/static root 이동을 본편으로 포함하면 안 된다.
3. 한 batch는 반드시 **한 decision family / 한 contract family**만 다룬다.
4. Wave 9 mainline은 원칙적으로 **docs-only**다. runtime code edit가 필요해지는 순간 본편 implementation이 아니라 handoff/stop 판단으로 내려간다.
5. legal **packaging verdict**는 아래 셋뿐이다.
   - `Option A`: explicit defer / no reopen
   - `Option B`: minimal packaging hardening approved
   - `Option C`: full `src/foms` reopen approved
   `readiness-gate-rejected`와 `needs-new-plan`은 packaging verdict가 아니라 meta termination state다.
6. `Option B`는 metadata-only hardening이 더 이상 false confidence가 아니고, runtime path migration과 혼합되지 않을 때만 허용한다.
7. `Option C`는 `must-update-together` 집합 전체가 하나의 coordinated implementation track에서 legal하게 묶일 때만 허용한다.
8. Wave 9는 runtime path migration implementation을 직접 하지 않는다. `Option B` 또는 `Option C`가 승인돼도 **dedicated implementation handoff**만 남긴다.
9. `app.py`, `start.sh`, `Procfile`, `railway*.toml`, `Dockerfile`, `migrations/env.py`, `tests/conftest.py`, `tools/harness/verify_result.py`, `foms/services/jobs/tasks.py`는 review truth source이지 Wave 9 본편의 기본 edit 대상이 아니다.
10. `apps/*`, root `db.py`, root `models.py`, root `services/*` shim, high-risk cluster는 package boundary 전략의 입력일 뿐, Wave 9 본편 cleanup 대상으로 끌어오지 않는다.
11. Wave 8 unresolved row는 `bridge-stuck` 또는 `continuation required`로 유지한다. Wave 9에서 “겸사겸사 같이 정리”하면 실패다.
12. Step 8 reopen gate 다섯 항목은 **hard prerequisite**다. 일부만 충족된 상태에서 optimistic reopen verdict를 내리면 실패다.
13. `foms/services/jobs/tasks.py`의 `_REPO_ROOT = Path(__file__).resolve().parents[3]` 같은 depth arithmetic contract는 packaging sensitivity evidence로 취급한다.
14. `migrations/env.py`의 root `db` / `models` direct import는 packaging sensitivity evidence로 취급한다.
15. `.github/workflows/ci.yml`, `Dockerfile`, `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml`은 **shared install/runtime contract** evidence로 취급한다.
16. Wave 9는 reopen 승인 여부와 무관하게 `APP_OK` / `verify_result` / namespace regression 기준을 final closeout에 명시해야 한다.
17. reopen 승인 시 handoff는 implementation 범위, must-update-together 집합, forbidden mixing rules, verification set, revert semantics를 포함해야 한다.
18. final plan audit loop는 `§10` hard-stop policy를 따른다. local wording 수정만으로 round를 추가하지 않는다.

### 1.2.1 PR shorthand definitions
- `PR1`: `gate-first`다. reopen 여부보다 먼저 Step 8 defer 조건 충족 여부를 판정한다.
- `PR2`: `docs-only-mainline`이다. Wave 9 본편은 decision/handoff wave이며 implementation wave가 아니다.
- `PR3`: `three-outcome-only`다. verdict는 `Option A/B/C` 셋 외에 허용하지 않는다.
- `PR4`: `false-confidence-fenced`다. `pyproject.toml` 단독 추가처럼 coupling을 해소하지 못하는 minimal hardening은 승인할 수 없다.
- `PR5`: `must-update-together-or-defer`다. `src/foms` physical move는 boot/worker/Alembic/test/harness/CI/deploy contract를 함께 다룰 수 있을 때만 reopen 가능하다.
- `PR6`: `bridge-debt-not-wave9`다. Wave 8 unresolved bridge debt를 Wave 9로 이관하지 않는다.
- `PR7`: `implementation-handoff-only`다. reopen 승인 시에도 Wave 9 본편은 dedicated implementation handoff만 남긴다.
- `PR8`: `hard-stop-audit`다. 감리 round는 최대 3번이며, round 2 이후에는 holistic patch 또는 freeze / new-plan decision만 허용한다.

### 1.3 Out of scope / freeze
Wave 9에서는 아래를 건드리지 않는다.

- `apps/`와 root `services/`의 미종결 bridge cleanup
- `apps.api.personal_board`, `apps.api.orders.__init__` shell collapse
- `services.jobs/*` runtime string contract 자체의 구현 변경
- `services.business_calendar.py` 이동
- `templates/`, `static/`, global layout shell 재구성
- 새 bounded context 생성
- route / endpoint / Blueprint / auth decorator stack 변경
- DB schema / persistence logic 변경
- packaging implementation 자체 (`src/foms` 이동, `pyproject.toml` 추가, CI install contract 변경)를 Wave 9 본편에서 바로 수행하는 것

Wave 9는 **reopen gate 판정 + option freeze + decision record + implementation handoff + closeout**까지만 담당한다.

추가 규칙:

- 어떤 batch라도 “이건 결국 코드도 같이 바꿔야 한다”가 드러나면 본편 implementation이 아니라 stop/handoff 판단으로 내려야 한다.
- 어떤 batch라도 Wave 8 unresolved item을 “Wave 9에서 같이 닫자”로 바꾸는 순간 scope drift다.
- 어떤 batch라도 `pyproject.toml`만 추가하면 충분하다고 가정하는 순간 실패다.
- 어떤 batch라도 global layout/template/static reopen을 packaging과 묶는 순간 실패다.

### 1.4 Scope reconciliation — Step 8 / Wave 8 / final stabilization과의 정합
1. Step 8은 optional packaging을 강행하는 단계가 아니라 `Option A/B/C` decision gate를 고정하는 단계였다.
2. Step 8 verdict는 explicit defer였고, `src/foms` full migration과 packaging-only hardening 모두 지금은 실행하지 않는다고 고정했다.
3. Step 8 closeout은 future reopen gate 다섯 항목을 정의했고, 이는 Wave 9의 hard prerequisite가 된다.
4. final stabilization reopen plan은 packaging revisit와 global layout/template reopen을 별도 track으로 분리했다.
5. Wave 8은 bridge debt를 닫는 wave이며, 미종결 bridge debt를 Wave 9로 넘기지 않는다고 명시했다.
6. 따라서 Wave 9의 기본 해석은 **“지금 packaging을 실행할지”가 아니라 “지금 packaging을 다시 열 수 있는지”를 판정하는 것**이다.

## 2. Current Packaging Truth — 현재 packaging/runtime landscape

### 2.1 선행 handoff gate
Wave 9 actual execution은 아래 산출물을 소비한 뒤에만 시작한다.

1. `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
2. `docs/harness/policy/DECISIONS.md`
3. `docs/plans/2026-04-11-step8-optional-packaging-reevaluation-plan.md`
4. `docs/plans/2026-04-11-step8-batch77-preaudit-run-record.md`
5. `docs/plans/2026-04-11-step8-batch79-packaging-decision-run-record.md`
6. `docs/plans/2026-04-11-step8-batch80-closeout-run-record.md`
7. `docs/plans/2026-04-11-final-stabilization-reopen-plan.md`
8. `docs/plans/2026-04-14-wave8-legacy-bridge-retirement-execution-plan.md`
9. actual Wave 8 closeout evidence 또는 accepted equivalent evidence
10. live `app.py`, `foms/platform/app_factory.py`, `foms/services/jobs/tasks.py`, `migrations/env.py`
11. live `tests/conftest.py`, `tests/test_app_bootstrap_contract.py`, `tools/harness/verify_result.py`
12. live `Dockerfile`, `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml`, `.github/workflows/ci.yml`, `requirements.txt`
13. `docs/AI_STATUS.md`

추가 규칙:

- Wave 8 actual closeout이 없어도 본 문서는 drafted plan으로 존재할 수 있다.
- actual execution에서 Wave 8 closeout이 없으면 `W9-B0` run record 안에 `accepted equivalent evidence` 또는 `rejected evidence`를 명시한다.
- predecessor evidence와 live tree가 충돌하면 live tree를 truth로 두고 drift를 `W9-B0` run record에 먼저 적는다.

### 2.2 Packaging-sensitive truth map

| Family | Live truth | Current contract | Packaging sensitivity |
|------|------|------|------|
| web-boot | `app.py`, `foms/platform/app_factory.py` | public boot contract는 여전히 root `app.py` + `app:app`; `WhiteNoise(root=\"static/\")`는 repo-root/static cwd 가정 | `src/foms` move나 package install contract 변경 시 boot path 재검토 필요 |
| deploy-runtime | `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml`, `Dockerfile` | Railway/web/worker 모두 repo-root checkout + `app:app` + `sh start.sh` + `pip install -r requirements.txt` 기준 | packaging-only change라도 deploy/runtime path와 분리 불가 |
| migration-runtime | `alembic.ini`, `migrations/env.py` | `prepend_sys_path = .`, root `db`/`models` direct import | package boundary 미정 상태에서 `src` 이동 시 즉시 coupling 발생 |
| worker-runtime | `foms/services/jobs/tasks.py` | `_REPO_ROOT = Path(__file__).resolve().parents[3]` + `sys.path.insert` | physical move 시 depth mismatch risk |
| tests-bootstrap | `tests/conftest.py`, `tests/test_app_bootstrap_contract.py` | root `app`, root `db`, root `models` import 전제 | install contract 변경과 동시 검토 필요 |
| harness-verify | `tools/harness/verify_result.py` | `import app; print(\"APP_OK\")`를 shared bootstrap contract로 사용 | packaging reopen 후에도 유지/대체 계약 합의 필요 |
| ci-install | `.github/workflows/ci.yml`, `requirements.txt` | `pip install -r requirements.txt` 후 `python -m pytest -v` | editable install / `pyproject.toml` / `src` layout 도입 시 계약 재정의 필요 |
| package-boundary-input | root `db.py`, root `models.py`, `apps/*`, root `services/*` shim | 아직 repo-root import surface가 남아 있음 | package boundary ADR 없이 reopen 불가 |

### 2.3 Current legal outcomes

| Option | 의미 | 기본 해석 | 현재 기본값 |
|------|------|------|------|
| `Option A` | explicit defer / no reopen | Step 8 defer 유지, gates 미충족 또는 false-confidence risk 존재 | **default** |
| `Option B` | minimal packaging hardening approved | metadata/install contract 일부를 분리해서 열 수 있으나 runtime path migration과 섞지 않음 | exceptional |
| `Option C` | full `src/foms` reopen approved | `must-update-together` 집합 전체를 coordinated implementation track으로 열 수 있음 | exceptional |

추가 규칙:

- `Option A/B/C`는 packaging verdict다.
- `readiness-gate-rejected`는 `W9-B0`에서 종료되는 meta closeout state다.
- `needs-new-plan`은 `§10` audit hard-stop에서만 쓰는 plan-maturity termination state다. Wave 9 execution verdict로 쓰지 않는다.

### 2.3.1 `Option B` minimal touch set
`Option B`는 `Option C`의 축소판이 아니다. future implementation handoff에서 최소 아래 범위 안에 머물러야 한다.

**허용 가능한 최소 범위**
1. packaging metadata (`pyproject.toml` 등)
2. CI install contract (`.github/workflows/ci.yml`)
3. install contract 정합을 위한 최소 dependency/runtime metadata 동기화 (`requirements.txt` 포함 가능)
4. 필요 시 동일 install contract를 반영하는 deploy/install surface (`Dockerfile`, `start.sh`, `Procfile`, `railway*.toml`) 단, physical path move 없이 가능한 범위

**`Option C` 전용 또는 defer 대상**
1. `foms/` → `src/foms/` physical move
2. `migrations/env.py`, `alembic.ini`
3. `foms/services/jobs/tasks.py`
4. `tests/conftest.py`, `tests/test_app_bootstrap_contract.py`, `tests/harness/*`, `tools/harness/verify_result.py`
5. repo-root `db.py` / `models.py` / `apps/*` import surface relocation

### 2.4 `src/foms` must-update-together 집합
Step 8 preaudit precedent 기준으로, `src/foms` physical move는 아래를 하나의 coordinated track으로 다룰 수 있을 때만 reopen 가능하다.

1. `app.py`
2. `start.sh`
3. `Procfile`
4. `railway.toml`
5. `railway-worker.toml`
6. `Dockerfile`
7. `migrations/env.py`
8. `alembic.ini`
9. `foms/services/jobs/tasks.py`
10. `tests/conftest.py`
11. `tests/test_app_bootstrap_contract.py`
12. `tests/harness/*`
13. `tools/harness/verify_result.py`
14. repo-root `db.py` / `models.py` / `apps/*` import surface
15. 새 packaging metadata(`pyproject.toml` 등)와 CI install contract

### 2.5 Pilot tie-break / lock 규칙
1. first executable path는 항상 `Option A explicit defer 검토`다.
2. `Option B`는 `Option A`를 기각할 만큼 강한 evidence가 있을 때만 검토한다.
3. `Option C`는 `must-update-together` 집합 전체가 legal하게 묶인다는 evidence가 있을 때만 검토한다.
4. `Option B`와 `Option C`는 동시에 승인할 수 없다.
5. bridge cleanup, layout reopen, persistence refactor가 조건부로 필요해지면 packaging reopen이 아니라 `scope-drift-stop`이다.

## 3. Fixed Execution Pipeline — 고정 배치 순서
Wave 9 mainline은 아래 순서를 기본값으로 한다.

1. `W9-B0` — Readiness gate + predecessor acceptance
2. `W9-B1` — Packaging/runtime surface freeze
3. `W9-B2` — Option matrix + must-update-together freeze
4. `W9-B3` — Decision freeze (`Option A/B/C`)
5. `W9-B4` — Closeout + dedicated implementation handoff

branch semantics:

- `Branch A` explicit defer closeout: `W9-B0 -> W9-B1 -> W9-B2 -> W9-B3 -> W9-B4`
- `Branch B` minimal hardening approved handoff: `W9-B0 -> W9-B1 -> W9-B2 -> W9-B3 -> W9-B4`
- `Branch C` full `src/foms` reopen approved handoff: `W9-B0 -> W9-B1 -> W9-B2 -> W9-B3 -> W9-B4`
- `Branch D` readiness rejected / docs-only abort: `W9-B0 -> W9-B4`

## 4. Batch runbook — 배치별 실행 규칙

### 4.1 W9-B0 — Readiness gate + predecessor acceptance
**목표**
- Wave 9가 실제로 시작 가능한지, 그리고 현재 evidence가 Step 8 / Wave 8 precedent와 legal하게 연결되는지 잠근다.

**허용 변경**
- `docs/plans/2026-04-14-wave9-batch0-readiness-gate-run-record.md`

**금지 변경**
- runtime code edit
- 새 packaging file 생성
- spec/archive/AI_STATUS update

**실행 단계**
1. Wave 8 actual closeout evidence 또는 accepted equivalent evidence 존재 여부를 적는다.
2. Step 8 reopen gate 다섯 항목의 current evidence availability를 적는다.
3. baseline을 아래 둘 중 하나로 잠근다.
   - `decision-ready baseline`
   - `insufficient-evidence baseline`
4. evidence가 부족하거나 Wave 8 미종결 debt가 섞이면 `readiness-gate-rejected`로 내린다.

**검증**
- predecessor list completeness
- accepted/rejected evidence 명시

### 4.2 W9-B1 — Packaging/runtime surface freeze
**목표**
- packaging-sensitive runtime contract를 live truth 기준으로 잠근다.

**허용 변경**
- `docs/plans/2026-04-14-wave9-batch1-packaging-surface-freeze-run-record.md`

**금지 변경**
- runtime code edit
- package move
- new metadata file creation

**실행 단계**
1. 아래 surface를 current truth로 잠근다.
   - web boot
   - deploy/runtime
   - migration runtime
   - worker runtime
   - tests bootstrap
   - harness verify
   - CI install
   - package boundary inputs
2. repo-root coupling evidence를 파일/문자열 기준으로 적는다.
3. `pyproject.toml`, `setup.py`, `setup.cfg` 부재/존재 상태를 적는다.
4. `Option B`와 `Option C` 검토 시 필요한 추가 evidence gap을 적는다.

**검증**
- surface table 누락 없음
- root coupling evidence 명시

### 4.3 W9-B2 — Option matrix + must-update-together freeze
**목표**
- legal outcome 셋과 `src/foms` must-update-together 집합을 고정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave9-batch2-option-matrix-freeze-run-record.md`

**금지 변경**
- runtime code edit
- new packaging metadata
- implementation handoff 작성 시작

**실행 단계**
1. `Option A/B/C` 정의를 current truth에 맞게 다시 적는다.
2. `Option B` 승인 조건과 false-confidence 금지 조건을 적는다.
3. `Option C` 승인 조건과 must-update-together 집합을 다시 적는다.
4. 아래 direct exclusions를 다시 적는다.
   - Wave 8 unresolved bridge debt
   - global template/layout reopen
   - persistence refactor
   - `business_calendar`
5. `W9-B3`에서 하나의 option을 선택할 때 다른 둘은 왜 아닌지 판단할 기준을 같이 남긴다.

**검증**
- option overlap 없음
- must-update-together 누락 없음

### 4.4 W9-B3 — Decision freeze
**목표**
- `Option A`, `Option B`, `Option C` 중 하나만 legal verdict로 고정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave9-batch3-packaging-decision-run-record.md`

**금지 변경**
- runtime code edit
- package move
- `pyproject.toml` 생성
- CI/deploy file edit

**실행 단계**
1. `Option A/B/C` 중 하나를 선택한다.
2. 선택 근거를 Step 8 gate와 live truth 기준으로 적는다.
3. 미선택 option 둘은 왜 지금 legal하지 않은지 적는다.
4. `Option B` 또는 `Option C`가 선택돼도 implementation은 여기서 하지 않는다고 다시 명시한다.

**검증**
- single verdict only
- gate-to-verdict traceability

### 4.5 W9-B4 — Closeout + dedicated implementation handoff
**목표**
- Wave 9를 readiness-gate-rejected closeout, explicit defer closeout, 또는 reopen-approved handoff 상태로 닫는다.

**허용 변경**
- `docs/plans/2026-04-14-wave9-batch4-closeout-run-record.md`
- `docs/plans/2026-04-14-wave9-packaging-reopen-implementation-handoff.md` (`Option B` 또는 `Option C` 승인 시에만)
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (`Wave 9` subsection + authoritative runbook reference + status wording만)
- `docs/ARCHIVE_INDEX.md`
- `docs/AI_STATUS.md`

**금지 변경**
- runtime code edit
- package move execution
- `pyproject.toml` 생성

**실행 단계**
1. closeout 유형을 아래 중 하나로 잠근다.
   - `readiness-gate-rejected closeout`
   - `explicit defer closeout`
   - `minimal-hardening-approved handoff`
   - `full-src-reopen-approved handoff`
2. `readiness-gate-rejected`면 missing evidence list, skipped batch(`W9-B1~B3 = N/A`), next legal step을 적는다.
3. `Option A`면 defer 이유와 next legal step을 적는다.
4. `Option B` 또는 `Option C`면 dedicated implementation handoff를 작성한다.
5. implementation handoff에는 아래를 반드시 포함한다.
   - exact implementation scope
   - must-update-together 집합
   - forbidden mixing rules
   - verification set
   - revert semantics
6. spec / archive / AI status를 current truth에 맞게 sync한다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py tests/test_foms_namespace_imports.py -q`
- closeout type single-source
- handoff file 존재 여부와 verdict 정합
- docs link correctness

## 5. Additional Rules — 추가 실행 규칙
1. `W9-B0` readiness가 rejected면 본편은 `Branch D`로 내려가고, Wave 9는 implementation 논의를 확장하지 않는다.
2. `Option A`는 실패가 아니라 legal packaging verdict다. 단, gate 미충족 상태에서 `W9-B0`에서 바로 끝나는 경우는 `Option A`가 아니라 `readiness-gate-rejected closeout`이다.
3. `Option B`는 `pyproject.toml` 하나 추가 같은 metadata-only fantasy를 의미하지 않는다. false-confidence risk가 남으면 `Option A`가 정답이다.
4. `Option C`는 `src/foms`를 바로 실행하는 verdict가 아니다. dedicated implementation handoff까지가 Wave 9의 끝이다.
5. dedicated implementation handoff가 없다면 `Option B` 또는 `Option C` 승인을 주장할 수 없다.
6. `app.py`, `start.sh`, `Procfile`, `railway*.toml`, `Dockerfile`, `migrations/env.py`, `tests/conftest.py`, `tools/harness/verify_result.py`, `foms/services/jobs/tasks.py`는 Wave 9 본편에서 변경 금지다.
7. `docs/`, `backups/`, `agent-transcripts/` 문자열은 coupling 참고 자료일 뿐, live truth는 아니다.
8. unresolved row를 남길 수는 있지만, 이유 없이 `maybe later`로 끝내면 안 된다. `why-not-now`와 `next legal step`이 반드시 있어야 한다.
9. `W9-B0`~`W9-B3`는 docs-only batch다. 이 배치들의 최소 검증은 evidence completeness, link/path correctness, 표/목록 무결성이다. `APP_OK` / `verify_result`는 `W9-B4` closeout에서 반드시 다시 실행한다.
10. `W9-B1` 또는 `W9-B2`에서 stop label이 확정되면 current batch run record를 stop label로 닫고, next legal batch는 `W9-B3`다. `W9-B3`는 그 stop context를 `Option A` verdict로 수렴한 뒤 `W9-B4` closeout으로 내려간다.

## 6. Run Record Contract — 모든 batch 공통 기록 규약
각 batch run record는 아래 항목을 반드시 포함한다.

1. batch id / 이름 / 실행일 / attempt / 진입 branch
2. scope lock (허용 / 금지)
3. inputs consumed
4. live truth snapshot
5. current gate state
6. baseline policy (`decision-ready baseline` 또는 `insufficient-evidence baseline`)
7. exact touched files
8. option table delta 또는 evidence delta
9. selected packaging verdict(`Option A/B/C`), meta termination state(`readiness-gate-rejected`), 또는 `verdict pending (pre-B3)`
10. why-not-now / next legal step
11. verification commands + 결과
12. Direction Lock 10문항
13. stop / handoff / explicit defer / readiness-rejected 여부
14. next legal batch

### 6.1 Direction Lock (10문항)
1. 이 batch는 packaging reopen 여부를 더 명확하게 만드는가?
2. Wave 9가 bridge debt를 떠안지 않게 울타리를 유지하는가?
3. docs-only mainline 원칙을 깨지 않았는가?
4. `Option A/B/C` 외의 새로운 packaging verdict를 만들지 않았는가?
5. `pyproject.toml` false-confidence 경로를 허용하지 않았는가?
6. `src/foms` 검토 시 must-update-together 집합을 누락하지 않았는가?
7. Step 8 reopen gate 다섯 항목과 verdict가 연결되는가?
8. global template/layout reopen을 packaging과 섞지 않았는가?
9. implementation 승인 시 dedicated handoff만 남기고 본편 code edit를 하지 않았는가?
10. 이 batch는 다음 batch의 legal branch를 더 좁혀 주는가?

## 7. Stop Conditions / Branch Rules

### 7.1 `readiness-gate-rejected`
- trigger:
  - Wave 8 closeout evidence도 없고 accepted equivalent evidence도 성립하지 않음
  - Step 8 reopen gate evidence 부족
  - live truth snapshot 미완성
- allowed path:
  - `Branch D`

### 7.2 `scope-drift-stop`
- trigger:
  - Wave 8 unresolved bridge debt를 Wave 9에서 같이 정리하려 함
  - template/static/global layout reopen이 packaging과 섞이기 시작함
  - persistence refactor를 packaging revisit에 끌어옴
- allowed path:
  - `W9-B3 -> Option A -> W9-B4`

### 7.3 `false-confidence-stop`
- trigger:
  - `pyproject.toml`만 추가하면 충분하다는 식의 verdict가 등장
  - metadata hardening이 root coupling을 제거하지 못함
- allowed path:
  - `W9-B3 -> Option A -> W9-B4`

### 7.4 `must-update-together-incomplete-stop`
- trigger:
  - `Option C`를 주장하면서 must-update-together 집합 일부가 누락됨
  - coordinated implementation track이 정의되지 않음
- allowed path:
  - `W9-B3 -> Option A -> W9-B4`

### 7.5 `implementation-mixing-stop`
- trigger:
  - Wave 9 본편에서 runtime/deploy/test/harness code edit가 시작됨
  - implementation handoff 없이 implementation scope가 섞임
- allowed path:
  - `W9-B3 -> Option A -> W9-B4`

## 8. Restart Minimum Input Set

### 8.1 공통 restart 입력
- current plan file
- latest completed Wave 9 run record
- latest actual Wave 8 status / closeout evidence
- latest Step 8 closeout and decision records
- live runtime truth files
- current baseline status

### 8.2 Path-specific restart notes
- `Branch A`:
  - explicit defer verdict와 why-not-now가 authoritative truth
- `Branch B`:
  - implementation handoff file이 next action truth
- `Branch C`:
  - must-update-together 집합과 implementation handoff file이 next action truth
- `Branch D`:
  - readiness failure summary와 missing evidence list가 restart input

## 9. Execution Prompt Contract
Wave 9 실행 프롬프트는 아래를 반드시 강제해야 한다.

1. 현재 batch id와 branch를 먼저 선언한다.
2. 이번 turn의 allowed files / forbidden expansion을 먼저 적는다.
3. edit 전 `Direction Lock` 핵심 답(1, 2, 3, 7)을 짧게 적는다.
4. Wave 9 본편은 docs-only mainline이라고 먼저 적는다.
5. `Option B` 또는 `Option C`가 나오면 implementation을 하지 않고 handoff만 남긴다고 먼저 적는다.
6. batch 종료 시 run record를 same-turn에 쓴다.
7. failure가 나면 silent retry 대신 `stop label`을 선언한다.

## 10. Final Audit Loop Hard-Stop Policy
Wave 9 계획서 감리는 아래 규칙으로만 반복한다.

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
9. round 2에서 구조적 blocker가 남아 round 3를 열 때는 **targeted patch 1회**만 허용한다. 두 번째 holistic pass는 금지다.
10. round 3는 **법적 batch order / option legality / scope fence**를 깨는 새 `HIGH` 또는 구조적 `MEDIUM`이 있을 때만 연다.
11. round 3 이후에도 blocker가 남으면 `freeze-ready`가 아니라 `needs-new-plan`으로 종료한다. round 4는 없다.

## 11. Completion Criteria

### 11.1 Explicit defer closeout
아래를 모두 만족하면 Wave 9 explicit defer closeout이다.

- Step 8 reopen gate 평가 완료
- current runtime truth freeze 완료
- `Option A`가 legal verdict로 고정됨
- why-not-now / next legal step 명시
- final closeout verification set(`APP_OK` / `verify_result` / namespace regression) 완료
- spec / archive / AI status sync 완료

### 11.2 Readiness-gate-rejected closeout
아래를 모두 만족하면 Wave 9 readiness-gate-rejected closeout이다.

- `W9-B0`에서 predecessor 또는 gate evidence 부족이 기록됨
- missing evidence list가 명시됨
- `W9-B1~B3 = N/A`가 closeout에 기록됨
- next legal step이 명시됨
- final closeout verification set(`APP_OK` / `verify_result` / namespace regression) 완료
- spec / archive / AI status sync 완료

### 11.3 Reopen-approved handoff
아래를 모두 만족하면 Wave 9 reopen-approved handoff다.

- Step 8 reopen gate 평가 완료
- current runtime truth freeze 완료
- `Option B` 또는 `Option C` 중 하나가 legal verdict로 고정됨
- dedicated implementation handoff 작성 완료
- must-update-together / forbidden mixing / verification / revert semantics 명시
- final closeout verification set(`APP_OK` / `verify_result` / namespace regression) 완료
- spec / archive / AI status sync 완료

### 11.4 Explicit non-goal
아래는 Wave 9 완료 조건이 아니다.

- `src/foms` physical move 실제 실행
- `pyproject.toml` 실제 생성
- CI/deploy/runtime/test/harness contract 실제 변경
- Wave 8 unresolved bridge debt cleanup
- template/static/global layout reopen
