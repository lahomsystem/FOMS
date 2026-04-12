# Step 8 Optional Packaging Re-evaluation Plan

> 상태: completed
> 범위: Step 8 (`optional packaging` / `src/foms` 여부 재평가)
> 기준 Spec: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`

## 1. 목표
Step 8의 목표는 현재 저장소가 full `src/foms` packaging으로 넘어갈 준비가 됐는지 검증하고, 아니라면 왜 defer해야 하는지와 future re-entry 조건을 명시적으로 고정하는 것이다.

이번 Step 8은 “패키징을 반드시 실행한다”가 아니라 “optional packaging을 마지막 단계에서 재평가한다”는 거버넌스 배치다. 따라서 기본 경로는 docs-first decision gate이며, full packaging은 모든 운영 계약이 동시에 안전하다고 판정될 때만 예외적으로 허용한다.

## 2. 현재 기준선

### 2.1 이미 확보된 packaging boundary
- `foms/`는 Step 3 이후 canonical runtime namespace 역할을 수행한다.
- Step 4 이후 bootstrap 구현은 `foms/platform/*`로 분리됐지만, public boot contract는 여전히 root `app.py`와 `app:app`에 고정돼 있다.
- Step 5/6/7은 모두 shim/compatibility와 runtime contract preservation을 우선했고, full installable-package 전환은 intentionally 뒤로 미뤄졌다.

### 2.2 현재 구조를 묶고 있는 boot-critical contract
- root `app.py`
- `start.sh` / `Procfile` / `railway.toml` / `railway-worker.toml` / `Dockerfile`
- `migrations/env.py` + root `db.py` / `models.py`
- `foms/services/jobs/tasks.py`의 repo-root depth contract
- `tests/conftest.py`, `tests/test_app_bootstrap_contract.py`, `tests/harness/*`, `tools/harness/verify_result.py`

## 3. 범위

### 3.1 포함
- Step 8 병렬 전감리 결과 정리
- Option A/B/C 비교와 decision gate freeze
- packaging defer 또는 execution 여부를 명시한 run record 작성
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- `docs/AI_STATUS.md`
- `docs/ARCHIVE_INDEX.md`
- `docs/harness/runtime/COMPACT_CHECKPOINT.md`
- 필요 시 `docs/harness/policy/DECISIONS.md`
- generated bundle 재생성과 verification baseline 재실행

### 3.2 제외
- `business_calendar` / `/calendar` 축 재도입
- root `app.py`, `start.sh`, `Procfile`, `railway*.toml`, `migrations/*`, `db.py`, `models.py`, `tests/*`의 runtime contract 변경
- Step 6 future decomposition과 packaging을 한 배치에 섞는 작업
- `pyproject.toml` 신규 도입을 위한 speculative hardening

## 4. 핵심 원칙

### 4.1 Re-evaluate, do not force
- Step 8은 optional packaging을 “강행”하는 단계가 아니라, 실행 가능성과 타당성을 판단해 최종 verdict를 남기는 단계다.

### 4.2 Root-cause alignment only
- `pyproject.toml`만 추가하는 minimal hardening도 boot/worker/alembic/tests root coupling을 제거하지 못하면 이번 Step 8에서는 하지 않는다.

### 4.3 Must-update-together or defer
- `src/foms` 같은 physical packaging move가 필요하면 web boot, worker, Alembic, CI, tests, harness verification path를 한 번에 묶어 바꿀 수 있을 때만 허용한다.
- 그렇지 않으면 defer가 정답이다.

### 4.4 Historical steps stay truthful
- Step 3~7 run record는 historical state를 설명하므로 wholesale path/wording rewrite는 하지 않는다.
- Step 8 문서만 현재 verdict와 future reopen 조건을 명시한다.

## 5. 실행 배치

### Batch 77 — parallel pre-audit
- 병렬 agent/team과 MCP 근거로 packaging-sensitive surface를 조사한다.
- 산출물: `docs/plans/2026-04-11-step8-batch77-preaudit-run-record.md`

### Batch 78 — plan freeze
- Option A/B/C, must-update-together 집합, decision gate, stop condition을 문서화한다.
- 산출물: 본 문서

### Batch 79 — packaging decision freeze
- full `src/foms` migration / minimal hardening / explicit defer 중 하나를 최종 선택한다.
- 이번 Step 8의 기본 예상 경로는 docs-only defer verdict다.
- 산출물: `docs/plans/2026-04-11-step8-batch79-packaging-decision-run-record.md`

### Batch 80 — post-audit closeout
- 상태 문서와 거버넌스 spec을 Step 8 결과에 맞게 동기화한다.
- generated bundle / harness tests / shared baseline / APP_OK / full pytest / lint를 재검증한다.
- 산출물: `docs/plans/2026-04-11-step8-batch80-closeout-run-record.md`

## 6. Decision gate

### Gate A — deployment/runtime contract
- `app:app`, Railway web/worker, `start.sh`, Docker, Alembic, worker task repo-root resolution이 동시에 안전해야 한다.
- 하나라도 repo-root import contract에 강하게 묶여 있으면 full packaging 금지.

### Gate B — install contract
- `src` layout을 쓸 경우 `pyproject.toml`/editable install/CI install/Railway runtime path를 한 번에 맞출 수 있어야 한다.
- tooling만 바꾸고 runtime은 그대로 두는 split-brain path는 금지.

### Gate C — benefit over churn
- 이번 배치에서 얻는 이익이 “metadata 정리” 수준이고, 실질 root coupling을 제거하지 못하면 defer가 우선이다.

### Gate D — scope discipline
- Step 6 future decomposition, persistence import unification, `business_calendar` 제외 규칙을 침범하면 Step 8 packaging execution은 중단한다.

## 7. 검증 게이트
- `python tools/harness/build_context_bundle.py --all`
- `python -m pytest tests/harness/test_context_bundle.py tests/harness/test_hooks_smoke.py -q`
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest -q`
- `ReadLints` on touched files

추가 조건:
- 만약 runtime file을 건드리게 되면 `start.sh` web boot contract, worker env parity, Alembic smoke를 추가로 통과해야 한다.
- 이번 Step 8 기본 경로에서는 runtime file을 수정하지 않으므로, 위 추가 조건은 future reopen gate로만 기록한다.

## 8. 중단 조건
- full packaging을 위해 `app.py`, `start.sh`, `railway*.toml`, `migrations/env.py`, `foms/services/jobs/tasks.py`, `tests/conftest.py`를 건드려야 한다는 사실이 드러나면 즉시 defer로 닫는다.
- `pyproject.toml`만 추가해도 구조적 안정성이 좋아진다는 확실한 근거가 없으면 hardening도 defer한다.
- 예상 밖의 boot/runtime regression sign이 보이면 Step 8은 docs-only verdict로 축소한다.
