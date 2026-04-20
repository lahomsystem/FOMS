# Step 8 Batch 77 Run Record
> 작성일: 2026-04-11
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 문서: `docs/plans/2026-04-10-step7-batch76-closeout-run-record.md`

- 일시: 2026-04-11
- 브랜치: `deploy`
- 실행자: AI agent + parallel subagents + MCP
- 목적: Step 8(optional packaging 재평가)의 병렬 전감리로 `src/foms` 같은 physical packaging 이동이 실제로 필요한지, 그리고 지금 실행 가능한지부터 판정한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: current repo-root `foms/` boundary is usable, but full `src/foms` migration is not safe enough for default execution**

이유:
- 현재 web bootstrap은 여전히 root `app.py`와 `app:app` 계약에 묶여 있고, `start.sh` / `railway.toml` / `Procfile` / `Dockerfile`이 repo root import root를 전제로 동작한다.
- `migrations/env.py`는 root `db` / `models` import와 repo-root `sys.path` 삽입에 결합돼 있어 packaging 이동이 Alembic 경로를 직접 흔든다.
- `tests/conftest.py`, `tests/test_app_bootstrap_contract.py`, `tools/harness/verify_result.py`, `tests/harness/*`는 `import app`와 repo-root cwd를 기준으로 bootstrap을 검증한다.
- `foms/services/jobs/tasks.py`는 `_REPO_ROOT = Path(__file__).resolve().parents[3]`에 의존해 worker import path를 보정하므로 `src/foms` 이동 시 즉시 depth mismatch risk가 생긴다.
- repo root에는 아직 `pyproject.toml`, `setup.py`, `setup.cfg`가 없고, installable package contract보다 cwd + `sys.path` patch contract가 더 강하다.
- Context7 `setuptools` 문서 기준으로 `src` layout은 `package-dir = {"" = "src"}` 및 `[tool.setuptools.packages.find] where = ["src"]` 같은 explicit build/install contract를 요구한다. 즉, `src`는 no-op relocation이 아니라 packaging toolchain 전환이다.

## 2. 병렬 팀 전감리 요약

### 2.1 구조/코드베이스 관점
- `foms/`는 이미 새 canonical runtime namespace 역할을 수행하지만, root `apps/`, `db.py`, `models.py`, `services/*` shim과 함께 hybrid 구조를 유지하고 있다.
- `foms`만 `src/`로 이동해도 전체 repo가 installable layout으로 정리되는 것이 아니라 partial move가 되어 coupling이 더 커질 가능성이 높다.

### 2.2 코드리뷰/리스크 관점
- 실제 high-risk touchpoint는 “패키지 위치” 자체가 아니라 `app:app`, Alembic import, RQ worker repo-root detection, pytest bootstrap처럼 repo-root를 묵시적으로 가정한 계약이다.
- 따라서 현재 시점의 full packaging은 구조 정리가 아니라 boot/worker/migration regression 가능성이 큰 배치로 해석된다.

### 2.3 배포/운영 관점
- Railway web은 `sh start.sh` → `gunicorn ... app:app`, worker는 `rq worker default --url $REDIS_URL`를 사용한다.
- CI도 `pip install -r requirements.txt`만 수행하고 editable install이나 `PYTHONPATH=/app/src` 계약이 없다.
- full `src` 이동은 Docker/Railway/CI/local test의 import contract를 한 번에 바꿔야 하므로 Step 8의 optional 범위를 넘는 운영 리스크를 가진다.

### 2.4 히스토리/거버넌스 관점
- root governance spec은 Step 8을 “optional packaging 재평가”로 정의했고, 즉시 `src/` 전환을 non-goal로 둔다.
- stop condition도 “운영 부팅 경로가 조금이라도 불안정하면 패키지화 연기”로 명시돼 있어, 이번 전감리의 기본 판정은 defer 우세다.

### 2.5 Python packaging 관점
- Option A: repo-root `foms/` 유지 + 문서화
- Option B: `pyproject.toml` 등 minimal hardening
- Option C: full `src/foms` migration
- 현 시점에서는 B도 root cause를 제거하지 않는다. metadata만 추가해도 `app.py` / Alembic / worker / tests import contract는 그대로 남으므로 false confidence risk가 있다.

## 3. Option matrix
| 옵션 | 설명 | 기대 이익 | 현재 리스크 | 전감리 판정 |
|------|------|-----------|-------------|-------------|
| A | repo-root `foms/` boundary 유지 + defer 문서화 | 현재 구조와 운영 계약을 깨지 않고 판단을 고정 | 낮음 | 기본 추천 |
| B | `pyproject.toml` 중심 minimal hardening | install metadata, tooling 명시성 확보 | 중간: root coupling 그대로 유지 | 지금은 보류 |
| C | full `src/foms` migration | package isolation, import hygiene 강화 | 높음: boot/worker/alembic/test/CI 동시 변경 필요 | 금지에 가깝게 defer |

## 4. `src/foms`를 시도할 때 must-update-together
- `app.py`
- `start.sh`
- `Procfile`
- `railway.toml`
- `railway-worker.toml`
- `Dockerfile`
- `migrations/env.py`
- `alembic.ini`
- `foms/services/jobs/tasks.py`
- `tests/conftest.py`
- `tests/test_app_bootstrap_contract.py`
- `tests/harness/*`
- `tools/harness/verify_result.py`
- repo-root `db.py` / `models.py` / `apps/*` import surface
- 새 packaging metadata(`pyproject.toml` 등)와 CI install contract

## 5. MCP / 외부 근거
- `user-filesystem:list_allowed_directories`로 workspace 접근 가능 범위를 재확인했다.
- `user-context7:resolve-library-id` + `query-docs`로 `setuptools` 공식 문서를 조회했다.
- 확인된 최신 근거:
  - `src` layout은 `package-dir`와 `find.where=["src"]` 같은 explicit 설정이 필요하다.
  - flat layout은 기본적으로 project root(`"."`)를 scan하며, `src` layout으로 바꾸는 순간 build/install contract도 함께 바뀐다.

## 6. preaudit conclusion
- Batch 78 plan freeze는 docs-first decision gate를 기본 경로로 잡는다.
- Step 8의 기본 실행 경로는 “full packaging 강행”이 아니라 “defer 여부를 구조적으로 판정하고 기록”하는 것이다.
- physical packaging move는 Step 6 future decomposition, root `db/models/apps` 정리, worker repo-root helper 통일과 섞으면 안 된다.
