# Wave 9 — W9-B1 Packaging/runtime surface freeze — Run record

**batch id:** W9-B1  
**이름:** Packaging/runtime surface freeze  
**실행일:** 2026-04-14  
**attempt:** 1 — completed  
**진입 branch:** Branch A (W9-B0 통과)

## Batch Start (선언)

- **현재 batch:** W9-B1  
- **현재 branch:** Branch A  
- **allowed files:** 본 파일만  
- **forbidden expansion:** runtime 코드, `pyproject.toml` 생성, spec/archive/AI_STATUS, implementation handoff  

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record | runtime code edit, CI/deploy/test/harness 변경 |

## 2. Inputs consumed

- `docs/plans/2026-04-14-wave9-packaging-reopen-review-execution-plan.md` §4.2
- W9-B0 run record
- Live truth (읽기): `app.py`, `foms/platform/app_factory.py`, `foms/services/jobs/tasks.py`, `migrations/env.py`, `tests/conftest.py`, `tests/test_app_bootstrap_contract.py`, `tools/harness/verify_result.py`, `Dockerfile`, `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml`, `.github/workflows/ci.yml`, `requirements.txt`

## 3. Live truth snapshot — surface freeze table

| Surface | Freeze anchor (current truth) | Repo-root coupling evidence |
|---------|------------------------------|-----------------------------|
| **web boot** | Root `app.py` → `create_app()` from `foms.platform.app_factory`; gunicorn `app:app` (`Procfile`, `start.sh`) | `app` 모듈이 repo root에 고정 |
| **deploy/runtime** | `Dockerfile`: `WORKDIR /app`, `COPY . .`, `CMD ["sh","start.sh"]`; `start.sh`: bash, `alembic upgrade head`, gunicorn `app:app` 또는 RQ worker | 전체 트리가 `/app`에 복사·cwd 의존 |
| **migration runtime** | `migrations/env.py`: `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`; `from db import Base`, `from models import ...` | Alembic이 **root** `db`/`models` 직접 import |
| **worker runtime** | `foms/services/jobs/tasks.py`: `_REPO_ROOT = Path(__file__).resolve().parents[3]`; `sys.path.insert(0, str(_REPO_ROOT))`; `from db import db_session` 등 | **depth arithmetic** (`parents[3]`) + path insert |
| **tests bootstrap** | `tests/conftest.py`: `from app import app`, `from db import ...`, `from models import User` | 테스트가 root `app`/`db`/`models`에 직접 결합 |
| **harness verify** | `tools/harness/verify_result.py`: `repo-root` 기본 `Path(__file__).resolve().parents[2]` | harness가 repo root 기준 스크립트 |
| **CI install** | `.github/workflows/ci.yml`: `pip install -r requirements.txt`, `pytest -v` | `requirements.txt` 단일, editable/`src` 없음 |
| **package boundary inputs** | `requirements.txt` 존재; **루트에 `pyproject.toml` / `setup.py` / `setup.cfg` 없음** (glob 0) | 패키징 메타데이터 없음 = install contract는 pip + requirements 중심 |

## 4. `pyproject.toml` / `setup.py` / `setup.cfg`

| 파일 | 상태 |
|------|------|
| `pyproject.toml` (repo root) | **부재** |
| `setup.py` | **부재** |
| `setup.cfg` | **부재** |

## 5. Option B / Option C 검토 시 추가 evidence gap

| Gap | 설명 |
|-----|------|
| **Option B (minimal hardening)** | 단일 메타데이터 추가만으로는 Step 8 `false-confidence-stop` 위험 — root coupling 제거 증거가 별도 필요 |
| **Option C (full `src/foms`)** | Alembic·worker·tests·Docker·CI 전부 must-update-together 집합이 B2에서 고정 필요; ADR/plan 합의 문서 추가 |

## 6. Stop label

- **없음** (`scope-drift-stop` / `false-confidence-stop` 등 미발생)

## 7. Exact touched files

- `docs/plans/2026-04-14-wave9-batch1-packaging-surface-freeze-run-record.md` (본 파일)

## 8. Verdict column

- **Packaging verdict:** `verdict pending (pre-B3)`

## 9. Why-not-now / next legal step

- **Next legal batch:** `W9-B2` — Option matrix + must-update-together freeze  
- **Run record:** `docs/plans/2026-04-14-wave9-batch2-option-matrix-freeze-run-record.md`

## 10. Verification (docs/evidence)

| 검증 | 결과 |
|------|------|
| Surface table 누락 없음 | 통과 (8 surface) |
| Root coupling evidence 명시 | 통과 (§3) |
| pyproject/setup 부재 기록 | 통과 (§4) |

## 11. Direction Lock (10문항)

| # | Y/N |
|---|-----|
| 1 | Y |
| 2 | Y |
| 3 | Y |
| 4 | Y |
| 5 | Y |
| 6 | Y (must-update-together는 W9-B2에서 고정) |
| 7 | Y |
| 8 | Y |
| 9 | Y |
| 10 | Y |

## 12. Next legal batch

**W9-B2**
