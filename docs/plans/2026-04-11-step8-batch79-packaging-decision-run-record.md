# Step 8 Batch 79 Run Record
> 작성일: 2026-04-11
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 문서: `docs/plans/2026-04-11-step8-batch77-preaudit-run-record.md`, `docs/plans/2026-04-11-step8-optional-packaging-reevaluation-plan.md`

- 일시: 2026-04-11
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Step 8의 optional packaging verdict를 확정하고, full `src/foms` migration 또는 minimal hardening을 지금 실행하지 않는 이유를 공식화한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 결정
**Decision: Step 8은 explicit defer로 닫는다. current repo-root `foms/` boundary를 유지하고, full `src/foms` migration과 packaging-only hardening은 둘 다 지금은 실행하지 않는다.**

## 2. 왜 defer가 정답인가

### 2.1 full `src/foms` migration이 optional 범위를 넘는다
- web bootstrap은 root `app.py` + `app:app`에 고정돼 있다.
- Railway/Docker/Procfile/startup은 repo root import root를 전제로 한다.
- Alembic은 root `db` / `models`를 직접 import한다.
- worker task는 `parents[3]` repo-root depth contract에 의존한다.
- tests/harness/shared verification도 `import app`와 repo-root cwd를 가정한다.

즉, `src/foms`는 package location 한 줄 수정이 아니라 boot/worker/migration/test/tooling contract를 동시에 바꾸는 구조 변경이다.

### 2.2 minimal hardening(`pyproject.toml` 등)도 root cause를 해결하지 않는다
- metadata를 추가해도 root `app.py`, `db.py`, `models.py`, `apps/*`, Alembic, worker, tests가 repo-root implicit import에 묶인 상태는 변하지 않는다.
- 이 상태에서 packaging metadata만 도입하면 “패키징이 정리됐다”는 신호를 주지만 실제 운영 계약은 그대로여서 false confidence risk가 생긴다.
- Step 8의 목적은 packaging 자체를 강행하는 것이 아니라, 지금 해야 할지 말아야 할지를 root-cause 기준으로 판정하는 것이다.

## 3. 이번 배치의 실제 구현 범위
- Step 8 preaudit 결과 문서화
- Step 8 plan freeze 문서화
- defer verdict와 reopen 조건 문서화
- 상태/거버넌스/checkpoint/decision 문서 동기화 준비
- verification baseline 재실행 준비

## 4. 이번 배치에서 하지 않는 것
- `pyproject.toml` 신규 추가
- `foms/` → `src/foms/` 물리 이동
- `app.py`, `start.sh`, `railway*.toml`, `migrations/env.py`, `tests/conftest.py`, `foms/services/jobs/tasks.py`의 packaging 대응 수정
- Step 6 future decomposition과 섞인 import unification

## 5. future reopen 조건
- web boot contract가 repo-root cwd 없이도 명시적으로 재현 가능할 것
- worker repo-root detection이 depth arithmetic 대신 single helper/explicit install contract로 바뀔 것
- Alembic이 root `db/models` direct import 대신 agreed canonical persistence path를 쓸 것
- CI/local/Railway가 동일한 install contract(`editable install` 또는 명시적 `PYTHONPATH`)를 공유할 것
- `apps/*`, root `db.py`, root `models.py`, `services/*` shim에 대한 package boundary 전략이 별도 ADR/plan로 합의될 것

## 6. 구현 판정
- Step 8은 “패키징을 하지 않았다”가 아니라, “패키징을 지금 하지 않는 것이 구조적으로 맞다”는 결론을 코드/배포 계약 근거로 확정한 단계다.
- 따라서 본 배치의 deliverable은 no-op이 아니라 **defer verdict를 canonical 문서와 상태 문서에 반영하는 것**이다.
