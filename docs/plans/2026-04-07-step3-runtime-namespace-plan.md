# Step 3 Runtime Namespace Entry Plan
> 작성일: 2026-04-07
> 상태: Batch 1 실행 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 조건: `Step 2` closeout 완료

## 1. 목적
`Step 3`의 목적은 `foms/` runtime namespace를 **가장 작은 안전 단위**로 도입하고, 이후 vertical slice 이행 전에 import/shim 전략을 고정하는 것이다.

이번 계획의 핵심은 다음이다.
- `app.py`, `db.py`, `models.py` 같은 기존 root 계약은 유지한다.
- `foms/`는 먼저 namespace와 shim만 도입한다.
- 비즈니스 로직 변경이나 대규모 물리 이동은 이번 배치에 포함하지 않는다.

## 2. 이번 배치의 원칙
1. **단일 source of truth 유지**: 실제 구현은 기존 root 모듈에 남기고, 새 경로는 shim/re-export만 허용한다.
2. **부팅 순서 불변**: `app.py`의 gevent/Flask/bootstrap 순서는 건드리지 않는다.
3. **배포 계약 불변**: `app:app`, `start.sh`, `Procfile`, `railway.toml`, `migrations/env.py`는 이번 배치에서 수정하지 않는다.
4. **비즈니스 로직 무변경**: import 경로와 namespace만 준비하고 정책/기능 동작은 바꾸지 않는다.

## 3. Batch 1 제안 범위
### 3.1 추가
- `foms/__init__.py`
- `foms/platform/__init__.py`
- `foms/web/__init__.py`
- `foms/api/__init__.py`
- `foms/services/__init__.py`
- `foms/persistence/__init__.py`
- `foms/persistence/main/__init__.py`
- `foms/persistence/main/db.py`
- `foms/persistence/main/models.py`

### 3.2 구현 방식
- `foms/` 하위는 우선 package skeleton만 만든다.
- `foms/persistence/main/db.py`는 root `db.py`의 공개 contract를 thin re-export로 노출한다.
- `foms/persistence/main/models.py`는 root `models.py`의 공개 contract를 thin re-export로 노출한다.
- root `db.py`, `models.py`는 이번 배치에서 그대로 유지한다.

### 3.3 이번 배치에서 하지 않는 것
- `app.py` slim화
- `apps/` 또는 `services/` 실구현 이동
- `templates/`, `static/`, `migrations/` 이동
- Alembic revision 생성
- worker/job 로직 변경

## 4. 동결 대상
다음 항목은 이번 배치에서 수정 금지:
- `app.py`
- `run.py`
- `start.sh`
- `Procfile`
- `railway.toml`
- `Dockerfile`
- `alembic.ini`
- `migrations/env.py`
- `db.py`
- `models.py`
- `wdcalculator_db.py`
- `wdcalculator_models.py`
- `templates/`
- `static/`
- `.cursor/hooks.json`
- `tools/harness/*`

## 5. 예상 리스크
1. `foms/`와 root 경로가 동시에 실구현처럼 보이면 source of truth가 흐려질 수 있다.
2. re-export 누락 시 `Base`, `db_session`, model symbol 등 일부 import contract가 깨질 수 있다.
3. Alembic, pytest fixture, worker import 경로가 root 모듈에 의존하고 있어 얕은 shim이라도 공개 symbol 정합성이 필요하다.

## 6. 검증 게이트
이번 배치 구현 시 최소 검증:
1. `python -c "import app; print('APP_OK')"`
2. `python tools/harness/verify_result.py --json`
3. `python -m pytest -q`
4. `python -c "from foms.persistence.main import db, models; print('FOMS_NS_OK')"`
5. 필요 시 `gunicorn app:app` import smoke 또는 동등 검증
6. `git status` 기준 root local/log/generated 파일 신규 추적 없음 확인

## 7. Batch 1 완료 기준
- `foms/` namespace가 repo에 생성되어 있다.
- 새 namespace import가 동작한다.
- 기존 root import 계약은 그대로 유지된다.
- app boot / migration / worker 계약 파일은 untouched 상태다.

## 8. Batch 1 다음 단계
Batch 1이 안정화되면 다음 순서로 진행한다.
1. `foms/platform` 또는 `foms/services` 쪽에 첫 실제 vertical slice 후보를 선정
2. legacy 경로는 shim, 새 경로만 실구현으로 유지
3. 그 후에만 `Step 4`/`Step 5` 수준 작업 검토

## 9. Batch 1 실행 결과
- 실행 기록: `docs/plans/2026-04-07-step3-batch1-run-record.md`
- 구현 결과: `foms/` package skeleton + `foms/persistence/main/{db,models}.py` thin re-export shim 추가
- 검증 결과: `FOMS_NS_OK`, `APP_OK`, `verify_result.py --json`, `pytest -q` 재통과
