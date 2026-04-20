# Wave 1 Root / Folder Hygiene Execution Plan
> 작성일: 2026-04-13 | 상태: 실행 준비 완료 (LLM batch-ready)
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> 보조 기준선: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 inventory: `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`
> 선행 closeout: `docs/plans/2026-04-07-step2-closeout-run-record.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 1 — Root / folder hygiene**를 바로 실행할 수 있는 LLM용 실행 계획서다.

이 계획의 목적은 추상적인 구조 방향을 반복 설명하는 것이 아니라, 다음 LLM batch가 더 이상 구조를 재해석하지 않고 바로 집행할 수 있게 아래 다섯 가지를 고정하는 것이다.

1. 루트의 **허용 taxonomy**를 다시 명확히 고정한다.
2. 현재 root debt를 **실행 가능한 batch 단위**로 분해한다.
3. 각 batch의 **risk axis / freeze / verification / stop condition**을 문서 안에서 닫는다.
4. `apps/`, root `services/`, quarantine, root standalone helper의 처리 기준을 **일관된 runbook**으로 만든다.
5. 다음 LLM이 첫 배치부터 바로 실행할 수 있도록 **scope lock + prompt contract**까지 제공한다.

### 1.2 기능 요구사항
1. 이 plan은 `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`의 Step 1과 Wave 1을 실제 배치로 번역한 **집행 문서**여야 한다.
2. 각 LLM turn은 반드시 **한 risk axis만** 다뤄야 한다.
3. 각 batch의 기본 의사결정 순서는 항상 **delete -> merge -> extend existing chunk -> add new file** 이어야 한다.
4. 새 root standalone script, 새 top-level code directory, 새 shim/wrapper는 **분류/retirement condition 없이** 추가할 수 없다.
5. 현재 `Step 2` inventory는 historical baseline로 재사용하고, 같은 범위의 sibling inventory 문서를 새로 늘리기보다 **delta/run record**로 이어가야 한다.
6. `backups/`, `Add In Program/`, `SCheduler/`는 끝까지 non-product / quarantine 축으로만 다뤄야 한다.
7. `src/`처럼 역할이 모호한 top-level code directory는 growth 금지 상태로 두지 말고, 반드시 **product / tooling / non-product track / quarantine** 중 하나로 고정해야 한다.
8. root standalone helper 정리는 "한 번에 다 옮기기"가 아니라 **family 단위**로 나누어 실행해야 한다.
9. 각 batch는 future LLM이 읽어도 재해석이 필요 없도록 **입력 문서, 수정 허용 범위, 금지 범위, 검증, 산출물**을 같이 남겨야 한다.
10. 이 문서만 읽어도 "다음으로 무엇을 해야 하는가"가 바로 결정되어야 한다.

### 1.3 Out of scope / freeze
Wave 1에서는 아래 항목을 건드리지 않는다.

- `app.py`, `run.py`, `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml`, `Dockerfile`, `alembic.ini`
- `db.py`, `models.py`, `wdcalculator_db.py`, `wdcalculator_models.py`
- `migrations/`의 Alembic revision source of truth
- `templates/` / `static/`의 root path relocation
- `task_plan.md`, `findings.md`, `progress.md`
- `business_calendar` / `/calendar`
- `src/foms`, packaging-only hardening, `pyproject.toml` reopen
- DB schema 변경, Alembic revision 추가, persistence lifecycle 재설계
- WDCalculator chunk merge 자체 실행

이 plan은 Wave 1 전용이다. `foms/web`, `foms/api`, `foms/services` 내부 context migration은 Wave 2 이후에 다룬다.

## 2. Current Root Debt — 현재 루트 부채 묶음

### 2.1 Root 분류 원칙
현재 루트 항목은 아래 일곱 범주 중 하나로만 읽는다.

1. runtime contract
2. canonical product tree
3. transition overlay
4. verification / tooling / ops
5. docs / governance
6. IDE / agent supply chain
7. quarantine / non-product

이 일곱 범주는 상위 spec Step 1의 다섯 축을 Wave 1 운영용으로 더 세분화한 것이다.

| Step 1 다섯 축 | Wave 1 운영 축 |
|------|------|
| runtime | runtime contract |
| product | canonical product tree + transition overlay |
| tooling | verification / tooling / ops + IDE / agent supply chain |
| docs | docs / governance |
| quarantine | quarantine / non-product |

### 2.1.1 Wave 1 operational root allowlist
Wave 1에서 허용되는 루트 항목은 아래 allowlist 또는 이들의 명시적 하위 분류뿐이다.

| 범주 | 허용 항목 |
|------|-----------|
| runtime contract | `app.py`, `run.py`, `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml`, `Dockerfile`, `alembic.ini`, `requirements*.txt`, `db.py`, `models.py`, `wdcalculator_db.py`, `wdcalculator_models.py` |
| canonical product tree | `foms/`, `templates/`, `static/`, `migrations/` |
| transition overlay | `apps/`, `services/`, `src/`(분류 전까지 growth 금지), root standalone helper scripts(temporary debt only) |
| verification / tooling / ops | `tests/`, `scripts/`, `tools/`, `data/` |
| docs / governance | `docs/`, `README.md`, `AGENTS.md`, `CLAUDE.md` |
| IDE / agent supply chain | `.cursor/`, `.claude/`, `.agents/`, `.github/`, `.vscode/` |
| quarantine / non-product | `backups/`, `Add In Program/`, `SCheduler/` |

allowlist에 없는데 현재 루트에 존재하는 항목은 **즉시 debt로 분류**하고, Batch 1 delta table에 올린다.
이 allowlist는 `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` §2.6의 **Wave 1 working copy**다. 둘이 어긋나면 `2026-04-07` spec이 우선하며, Batch 1에서 먼저 reconcile한 뒤 다음 batch로 간다.

### 2.1.2 `scripts/` bucket 사용 규칙
Wave 1에서 `scripts/` 하위는 아래처럼 고정한다.

- `scripts/migrations/`: one-off migration, import-path relocation, backfill helper
- `scripts/ops/`: operator entrypoint, automation runner, deploy/maintenance utility
- `scripts/maintenance/`: 반복 실행 가능한 수동 maintenance helper

이 셋 외의 새 `scripts/*` bucket은 Wave 1에서 만들지 않는다.

### 2.2 이번 Wave 1에서 실제로 다룰 root debt group
아래 표는 `Step 2` inventory와 현재 저장소 상태를 합쳐, Wave 1에서 다뤄야 할 실제 debt group을 batch-ready 관점으로 다시 묶은 것이다.

| 그룹 | 현재 예시 | 기본 target | 비고 |
|------|-----------|-------------|------|
| ambiguous top-level code root | `src/` | 역할 고정 후 `tooling` 또는 `non-product track` 또는 `quarantine` | Batch 2에서 먼저 분류 |
| root migration helpers | `migrate_as_orders.py`, `migrate_attachment_user.py`, `migrate_blueprint_field.py`, `migrate_local_attachment_user.py`, `migrate_local_to_remote.py`, `migrate_local_uploads_to_r2.py`, `railway_migrate_team.py`, `safe_schema_migration.py`, `web_migration.py` | `scripts/migrations/` 또는 `scripts/ops/` | 한 번에 전부가 아니라 family 단위 |
| root ops / utility Python | `erp_automation.py`, `erp_build_step_runner.py`, `erp_order_text_parser.py`, `init_wdcalculator_db.py`, `simple_backup_system.py`, post-Step-2 additions like `foms_map_generator.py`, `foms_address_converter.py` | `scripts/ops/`, `tools/`, 또는 명시적 non-product track | runtime import 여부 확인 후 이동 |
| root manual / office artifacts | `Cloudflair R2 API.docx`, `Furniture Process.md`, `가구 주문 프로세스.docx`, `개발자 구인 공고 내용.docx`, `🚨_간단_백업.bat`, post-Step-2 additions like `SYSTEM_DOCUMENTATION.md`, `DEPLOYMENT_GUIDE.md`, `WDPLANNER_INTEGRATION.md` | `docs/`, `scripts/maintenance/`, 또는 external/quarantine | 자동 삭제 금지 |
| ambiguous root text / deploy-looking artifact | `runtime.txt` 같은 소비자 미확인 text artifact | Batch 2에서 먼저 소비자 확인 후 freeze 또는 이동 | contract 여부 확인 전 이동 금지 |
| harness-looking root files | `task_plan.md`, `findings.md`, `progress.md` | root 유지 | Wave 1에서 이동 금지 |
| quarantine zones | `backups/`, `Add In Program/`, `SCheduler/` | quarantine 유지 | 새 product source 금지 |

### 2.3 Wave 1에서 먼저 다시 스캔해야 하는 것
`Step 2` inventory는 2026-04-07 기준이므로, 첫 batch에서 아래 항목을 다시 확인한다.

- `Step 2` 이후 새로 생긴 root standalone script
- `Step 2` 이후 새로 생긴 root office/manual artifact
- 현재 root top-level directory 전체
- 현재 root에서 runtime contract가 아닌 `.py`, `.ps1`, `.bat`, `.md`, `.docx`, `.txt`

이 재스캔은 **새 sibling inventory 문서 생성**이 아니라, Batch 1 run record 안의 delta table로 남긴다.

## 3. Fixed Execution Pipeline — 고정 실행 순서

각 LLM batch는 아래 순서를 바꾸지 않는다.

1. classify
2. delete / merge candidate 확인
3. existing canonical target 확장 가능성 확인
4. 정말 필요할 때만 add new file
5. shim이 필요하면 canonical target / retirement wave / removal condition을 같은 기록 안에 남김
6. verification
7. run record 작성

추가 규칙:

- spec과 plan이 충돌하면 **구현을 멈추고 controlling spec부터 갱신**한다.
- batch가 두 개 이상의 risk axis를 건드리기 시작하면 **즉시 분리**한다.
- 한 batch가 file move와 behavior change를 동시에 요구하면, 먼저 behavior-free structure batch를 만든다.
- delete/merge 검토 기록 없이 새 파일을 추가하지 않는다.
- B3 계열에서 말하는 "family"는 아래 셋 중 하나로만 정의한다.
  - 같은 filename prefix를 공유하는 집합(예: `migrate_*`)
  - 같은 inventory row에서 같은 owner로 묶인 집합
  - 같은 문서/운영 흐름에서 항상 같이 갱신되는 집합
- 한 batch는 위 family 정의 중 **하나만** 선택할 수 있다.

## 4. Wave 1 Batch Catalog — LLM 실행 순서

### 4.1 Batch table
| Batch ID | 이름 | Risk axis | 주 결과물 | 선행 조건 |
|------|------|------|------|------|
| W1-B0 | Spec adoption | governance | final-form spec 승인 상태 반영 | 완료 |
| W1-B1 | Allowlist + refreshed root inventory + quarantine contract | docs / taxonomy | root allowlist 재확인, root delta inventory, quarantine contract 고정 | W1-B0 |
| W1-B2 | Ambiguous top-level root classification | filesystem taxonomy | `src/` 등 모호한 top-level root의 역할 고정 | W1-B1 |
| W1-B3A | Root migration helper convergence | standalone script relocation | migration family를 `scripts/migrations/` 또는 `scripts/ops/`로 수렴 | W1-B2 |
| W1-B3B | Root ops / utility Python convergence | standalone script relocation | ops/util family를 `scripts/ops/` 또는 `tools/`로 수렴 | W1-B3A |
| W1-B4 | Root manual / office artifact convergence | non-code root cleanup | loose docs/manual artifacts를 `docs/` 또는 `scripts/maintenance/` 등으로 수렴 | W1-B3B |
| W1-B5 | Wave 1 closeout | verification / governance | delta 요약, 잔여 debt, 다음 wave handoff 고정 | W1-B4 |

### 4.2 Batch별 기본 원칙
- `W1-B0`는 이미 완료된 gate다. spec 상태가 다시 바뀌지 않는 한 반복 실행하지 않는다.
- `W1-B1`, `W1-B2`는 **docs-first / classification-first**다.
- `W1-B3A`, `W1-B3B`는 한 번에 모든 root script를 옮기지 말고 **같은 owner/family만** 다룬다.
- `W1-B4`는 삭제보다 **적절한 home으로 수렴**이 기본값이다.
- `W1-B5`는 새 이동을 하지 않고, Wave 1 결과를 정리하는 closeout이다.

## 5. Batch Runbooks — 각 배치의 실제 실행법

### 5.1 W1-B1 — Allowlist + refreshed root inventory + quarantine contract
**목표**
- final-form spec을 기준으로 root taxonomy를 실행 문서 수준으로 고정한다.
- 현재 root delta를 다시 스캔해 다음 batch 대상군을 확정한다.
- quarantine zones에 대한 해석을 문서상에서 재고정한다.

**허용 변경**
- `docs/specs/*`, `docs/plans/*`, `docs/ARCHIVE_INDEX.md`, `README.md` 수준의 docs 변경

**금지 변경**
- root `.py` / `.ps1` / `.bat` / `.docx` 실이동
- runtime contract file 수정
- `apps/`, root `services/`, `foms/` 내부 구현 이동

**실행 단계**
1. 현재 root top-level entry 전체를 다시 분류한다.
2. `2026-04-07-step2-root-hygiene-inventory.md` 기준 Category D와 현재 root delta를 비교한다.
3. root allowlist를 이 plan 또는 연결된 run record에서 다시 적는다.
4. `backups/`, `Add In Program/`, `SCheduler/`를 quarantine로 재명시한다.
5. `product tree -> quarantine import 금지`를 future batch gate로 고정한다.
6. `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.3의 bounded context ↔ canonical/bridge 표를 Wave 1의 owner map source로 다시 링크하고, 이번 Wave 1에서 그 표는 변경하지 않음을 명시한다.
7. `W1-B2`~`W1-B4` 대상 파일군을 확정한다.

**산출물**
- `W1-B1` run record 1개
- root delta table
- batch 대상군 확정 표

**검증**
- docs-only batch인지 확인
- runtime path 미변경 확인
- touched doc lint / markdown sanity
- 이번 batch는 `tools/` executable code 추가를 허용하지 않는다

### 5.2 W1-B2 — Ambiguous top-level root classification
**목표**
- `src/` 같은 ambiguous top-level root와 `runtime.txt` 같은 deploy-looking text artifact의 역할을 먼저 고정한다.

**허용 변경**
- classification 문서, local `README.md`, ownership note

**금지 변경**
- `src/` 내부 대규모 코드 이동
- `src/`를 product tree로 승격시키는 구조 변경

**실행 단계**
1. `src/`를 product / tooling / non-product track / quarantine 중 하나로 판정한다.
2. 판정 근거를 문서에 남긴다.
3. future growth rule을 적는다.
4. 필요하면 `src/README.md` 같은 최소 entrypoint를 추가한다.

**산출물**
- `W1-B2` run record 1개
- `src/` 역할 고정 문장 또는 local `README.md`

**검증**
- root taxonomy 문서와 모순이 없는지 확인
- product tree 확장으로 읽히지 않는지 확인

### 5.3 W1-B3A — Root migration helper convergence
**목표**
- migration 성격의 root helper를 `scripts/migrations/` 또는 `scripts/ops/`로 수렴시킨다.

**기본 후보**
- `migrate_*.py`
- `safe_schema_migration.py`
- `web_migration.py`
- `railway_migrate_team.py`

**허용 변경**
- file move
- import / docs reference update
- minimal compatibility shim

**금지 변경**
- DB schema 변경
- Alembic revision 추가
- script behavior 변경

**실행 단계**
1. 후보 중 같은 owner/family만 선택한다.
2. old root path가 실제로 runtime contract인지 확인한다.
3. new home을 `scripts/migrations/` 또는 `scripts/ops/`로 정한다.
4. docs / tooling references를 같은 batch에서 갱신한다.
5. unavoidable할 때만 root shim을 두고 retirement wave를 적는다.

**산출물**
- moved script set
- reference update
- `W1-B3A` run record

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- impacted script smoke 또는 import smoke
- `git status`에 새 root standalone script가 남지 않았는지 확인

### 5.4 W1-B3B — Root ops / utility Python convergence
**목표**
- root utility/ops Python debt를 `scripts/ops/` 또는 `tools/`로 수렴시킨다.

**기본 후보**
- `erp_automation.py`
- `erp_build_step_runner.py`
- `erp_order_text_parser.py`
- `init_wdcalculator_db.py`
- `simple_backup_system.py`
- post-Step-2 additions like `foms_map_generator.py`, `foms_address_converter.py`

**핵심 원칙**
- runtime import를 받는 utility는 먼저 caller map을 확인한다.
- runtime-facing이면 shim이 아니라 canonical owner 재판정이 먼저다.
- pure operator utility면 `scripts/ops/` 또는 `tools/`로 보낸다.

**검증**
- `APP_OK`
- focused pytest 또는 해당 utility smoke
- reference update 확인

### 5.5 W1-B4 — Root manual / office artifact convergence
**목표**
- loose business/manual artifacts를 적절한 home으로 옮기되, 가치가 있는 자료를 삭제하지 않는다.

**기본 후보**
- `Cloudflair R2 API.docx`
- `Furniture Process.md`
- `가구 주문 프로세스.docx`
- `개발자 구인 공고 내용.docx`
- `🚨_간단_백업.bat`
- post-Step-2 additions like `SYSTEM_DOCUMENTATION.md`, `DEPLOYMENT_GUIDE.md`, `WDPLANNER_INTEGRATION.md`

**기본 target**
- office/reference docs -> `docs/`
- manual batch file -> `scripts/maintenance/`
- deployment/runtime notes -> `docs/guides/` 또는 explicit ops doc home

**금지**
- 가치 확인 없는 일괄 삭제
- product source와 같은 축에 재배치

### 5.6 W1-B5 — Wave 1 closeout
**목표**
- Wave 1 결과를 요약하고 잔여 debt를 명확히 남긴다.

**산출물**
- closeout run record 1개
- 남은 root debt 목록
- Wave 2 handoff note

**검증**
- `APP_OK`
- `verify_result.py --json`
- 필요한 경우 `pytest -q`
- root clutter 신규 생성 없음
- 새 top-level code dir 없음
- `rg -n "Add In Program|SCheduler|backups" "foms" "apps" "services" "templates" "static" "tests" "tools" "scripts"` 또는 동등한 search 기준 새 runtime dependency 흔적 없음

## 6. Verification Matrix — 검증 기준

### 6.1 공통
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `git status`

### 6.2 docs-only batch
아래 조건을 모두 만족하면 runtime smoke를 생략할 수 있다.

1. 수정 파일이 `docs/*`, `README.md`류에 한정됨
2. `tools/`에도 executable code를 추가하지 않음
3. import path / script path / runtime contract path를 바꾸지 않음

위 셋 중 하나라도 깨지면 `APP_OK`와 최소 smoke를 다시 돌린다.

### 6.3 move batch
아래를 기본으로 한다.

- `APP_OK`
- `verify_result.py --json`
- moved file reference smoke
- 필요 시 `pytest -q` 또는 focused pytest

## 7. Run Record Contract — 각 실행 기록에 반드시 남길 것

### 7.1 Run record file path convention
Wave 1 run record는 아래 패턴으로 `docs/plans/` 아래에 둔다.

- `2026-04-13-wave1-batch1-root-allowlist-run-record.md`
- `2026-04-13-wave1-batch2-src-classification-run-record.md`
- `2026-04-13-wave1-batch3a-root-migration-helpers-run-record.md`
- `2026-04-13-wave1-batch3b-root-ops-utilities-run-record.md`
- `2026-04-13-wave1-batch4-root-manual-artifacts-run-record.md`
- `2026-04-13-wave1-batch5-closeout-run-record.md`

### 7.2 Direction Lock 질문 (plan 내장본)
각 run record는 아래 질문에 짧게 답한다.

1. 이번 batch는 single source of truth를 더 선명하게 만드는가
2. split-brain을 줄이는가, 아니면 임시로 늘린다면 언제 다시 줄일 것인가
3. 새 파일 추가 전에 delete/merge/extend를 실제로 검토했는가
4. 새 파일이 있다면 그것이 가장 큰 유지보수 가능 chunk인가
5. product/wrapper/test file 수는 순감 또는 최소 동결인가
6. 순증가라면 어떤 파일을 언제 없앨지 이미 적혀 있는가
7. local `README.md` 또는 동등한 AI entrypoint가 이번 변경 범위를 반영하는가
8. 이 패턴이 10번 반복돼도 FOMS 폴더가 더 깔끔해질 것 같은가
9. product / bridge / tooling / docs / quarantine 경계가 더 선명해졌는가
10. 지금 이 batch가 구조 작업인지, 아니면 슬쩍 기능 변경을 섞고 있는지 명확한가

### 7.3 Run record content
각 batch run record는 최소 아래를 포함해야 한다.

- batch ID
- risk axis
- touched files
- product file delta
- wrapper file delta
- test file delta
- canonical target
- removal / merge target
- new shim retirement wave
- local `README.md` update 여부
- delete / merge / extend / add 검토 결과
- Direction Lock 10문항에 대한 짧은 답
- verification command와 결과 요약
- stop condition 여부

## 8. Stop Conditions — 즉시 중단 조건

다음 중 하나라도 발생하면 구현을 멈추고 controlling spec/plan을 먼저 갱신한다.

- packaging 또는 `src/foms` 전환이 batch에 섞이기 시작할 때
- DB schema / Alembic revision / persistence lifecycle 변경이 섞일 때
- `task_plan.md`, `findings.md`, `progress.md` 이동 요구가 생길 때
- runtime contract file 경로 이동이 필요해질 때
- 새 shim이 canonical target / retirement wave 없이 생기려 할 때
- quarantine에서 product source를 읽어오려 할 때
- batch가 한 risk axis를 넘기기 시작할 때

## 9. First LLM Turn — 바로 실행할 다음 배치

다음 LLM turn은 **반드시 `W1-B1`만** 실행한다.

### 9.1 Scope lock
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
- `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`
- `docs/plans/2026-04-07-step2-closeout-run-record.md`
- 이 plan 문서

### 9.2 Allowed edits
- `docs/plans/*`
- `docs/specs/*`
- `README.md` 류 문서
- 필요 시 `docs/ARCHIVE_INDEX.md`

### 9.3 Forbidden edits
- root code file move
- `apps/`, `services/`, `foms/` 구현 이동
- `templates/`, `static/`, `migrations/` 실이동

### 9.4 Prompt-ready contract
다음 프롬프트를 그대로 사용해도 된다.

```text
Execute only Wave 1 Batch W1-B1 from `docs/plans/2026-04-13-wave1-root-folder-hygiene-execution-plan.md`.

Read first:
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
- `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`
- `docs/plans/2026-04-07-step2-closeout-run-record.md`
- `docs/plans/2026-04-13-wave1-root-folder-hygiene-execution-plan.md`

Goal:
- refresh root delta inventory after Step 2
- restate root allowlist / taxonomy for Wave 1 execution
- lock quarantine interpretation for `backups/`, `Add In Program/`, `SCheduler/`
- restate that `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.3 remains the context owner map source for Wave 1
- decide exact candidate file groups for W1-B2, W1-B3A, W1-B3B, W1-B4

Do not:
- move code files
- change runtime behavior
- touch `apps/`, root `services/`, `foms/`, `templates/`, `static/`, `migrations/`

Required output:
- one W1-B1 run record
- updated plan/spec docs only if needed
- explicit next-batch candidate list

Before editing, answer briefly:
1. delete/merge/extend/add check result
2. touched files
3. why this is still a single risk axis

After editing, report:
- product/wrapper/test delta
- canonical target
- removal/merge target
- verification performed
- whether any stop condition was hit
```

## 10. Definition of Done — Wave 1 완료 판정

Wave 1은 아래 조건을 만족하면 closeout 가능하다.

1. root allowlist와 top-level taxonomy가 문서상에서 다시 고정되었다.
2. `src/` 같은 ambiguous root의 역할이 고정되었다.
3. root standalone Python debt가 family 단위로 `scripts/` / `tools/`로 수렴하기 시작했고, 남은 debt도 owner별로 분류되었다.
4. loose manual / office artifact가 적절한 home 또는 explicit defer 상태로 정리되었다.
5. quarantine가 product source of truth가 아님이 실행 기록과 검증 기준에 반영되었다.
6. 다음 LLM이 Wave 2를 시작할 때 root/folder taxonomy를 다시 해석할 필요가 없다.
