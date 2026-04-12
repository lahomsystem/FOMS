# Step 8 Batch 80 Run Record
> 작성일: 2026-04-11
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 문서: `docs/plans/2026-04-11-step8-batch77-preaudit-run-record.md`, `docs/plans/2026-04-11-step8-optional-packaging-reevaluation-plan.md`, `docs/plans/2026-04-11-step8-batch79-packaging-decision-run-record.md`

- 일시: 2026-04-11
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Step 8(optional packaging 재평가)의 최종 verdict를 정리하고, 상태 문서와 거버넌스 기준선을 closeout한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 8 closeout completed, packaging is intentionally deferred**

이유:
- 병렬 전감리와 MCP `setuptools` 최신 문서 확인 결과, full `src/foms` migration은 packaging toolchain, boot path, worker path, Alembic import, test bootstrap을 동시에 바꾸는 고위험 배치로 판정됐다.
- 현재 repo-root `foms/` namespace는 canonical runtime boundary로 기능하고 있으며, Step 8의 목적은 “무조건 이동”이 아니라 “지금 이동해야 하는지”를 마지막 단계에서 재평가하는 것이었다.
- `pyproject.toml` 같은 minimal hardening도 root `app.py`, root `db/models`, `migrations/env.py`, `foms/services/jobs/tasks.py`, `tests/conftest.py`, `tools/harness/verify_result.py`의 repo-root coupling을 제거하지 못하므로 이번 배치에서는 false-confidence risk가 더 컸다.
- 결과적으로 Step 8은 no-op이 아니라 **defer verdict를 canonical 문서와 상태 문서에 고정하고 future reopen gate를 정의한 단계**로 닫혔다.

## 2. 실제 변경 범위
- `docs/plans/2026-04-11-step8-batch77-preaudit-run-record.md`
- `docs/plans/2026-04-11-step8-optional-packaging-reevaluation-plan.md`
- `docs/plans/2026-04-11-step8-batch79-packaging-decision-run-record.md`
- `docs/plans/2026-04-11-step8-batch80-closeout-run-record.md`
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- `docs/harness/policy/DECISIONS.md`
- `docs/AI_STATUS.md`
- `docs/ARCHIVE_INDEX.md`
- `docs/harness/runtime/COMPACT_CHECKPOINT.md`
- `docs/harness/bundles/HARNESS_BUNDLE_*.md` (재생성)

## 3. 사후감리 요약

### 3.1 결과 해석
- Step 8의 핵심 산출물은 full packaging 실행이 아니라, optional packaging에 대한 **명시적 defer decision**이다.
- root `app.py` / `app:app`, Railway startup, worker repo-root detection, Alembic root import, pytest bootstrap이 모두 repo-root layout에 결합돼 있는 동안 `src/foms`는 “정리”보다 “계약 변경”에 가깝다.
- current repo-root `foms/` boundary는 Step 3~5가 만든 canonical namespace로 충분히 작동하므로, 지금 필요한 것은 premature relocation이 아니라 reopen 조건의 정확한 문서화다.

### 3.2 why minimal hardening was also deferred
- `pyproject.toml`만 추가해도 packaging이 정리된 것처럼 보이지만, 실제 운영 계약은 그대로 남는다.
- Step 8은 root-cause aligned verdict를 요구하므로, boot/worker/alembic/tests coupling을 건드리지 않는 metadata-only hardening은 이번 단계의 정답이 아니다.

### 3.3 future reopen gate
- web boot contract가 repo-root cwd 없이도 명시적으로 재현 가능할 것
- worker repo-root resolution이 depth arithmetic 대신 single helper 또는 install contract로 대체될 것
- Alembic이 root `db/models` direct import에서 벗어나 agreed canonical persistence path를 사용할 것
- CI/local/Railway가 같은 install contract를 공유할 것
- `apps/*`, root `db.py`, root `models.py`, `services/*` shim에 대한 package boundary 전략이 별도 ADR/plan로 합의될 것

### 3.4 residual risk
- `docs/harness/policy/DECISIONS.md`는 이미 max-15 guideline을 초과한 historical 상태였고, 이번 Step 8에서도 새 결정 하나가 추가됐다. pruning은 별도 housekeeping batch로 분리한다.
- Step 6 future decomposition inventory에 포함된 일부 파일(`apps/*`, `foms/services/*`)은 future structural churn 가능성이 있으므로 packaging revisit는 해당 배치와 반드시 분리해야 한다.
- `business_calendar` / `/calendar` 축은 끝까지 제외했다.

## 4. 최종 검증 결과

### 4.1 bundle regeneration
- 실행:
  - `python tools/harness/build_context_bundle.py --all`
- 결과:
  - 성공

### 4.2 hook compile smoke
- 실행:
  - `python -m compileall -q ".cursor/hooks"`
- 결과:
  - 성공

### 4.3 harness-focused tests
- 실행:
  - `python -m pytest tests/harness/test_context_bundle.py tests/harness/test_hooks_smoke.py -q`
- 결과:
  - `24 passed`

### 4.4 app import smoke
- 실행:
  - `python -c "import app; print('APP_OK')"`
- 결과:
  - `APP_OK`
- 관찰 사항:
  - 기존 development `SECRET_KEY`/`REDIS_URL` warning 출력은 유지되지만 import smoke는 성공했다.

### 4.5 shared verification
- 실행:
  - `python tools/harness/verify_result.py --json`
- 결과:
  - `success: true`

### 4.6 full regression
- 실행:
  - `python -m pytest -q`
- 결과:
  - `431 passed, 3 warnings`
- 관찰 사항:
  - 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 4.7 lint
- 실행:
  - `ReadLints`
- 결과:
  - 신규 lint 없음

## 5. 해석
- Step 8은 구조 개편 거버넌스의 마지막 재평가 단계로서, full packaging을 실행하지 않는 것이 오히려 정확한 completion이었다.
- 앞으로 packaging을 다시 열 때는 “현재도 된다”는 낙관이 아니라, Step 8에서 정의한 reopen gate를 모두 충족하는 별도 ADR/plan이 필요하다.
- 저장소 구조 거버넌스 spec의 순차 단계는 이번 closeout으로 닫혔고, 이후 packaging은 자동 다음 단계가 아니라 조건부 future batch가 된다.

## 6. 다음 단계
1. 저장소 구조 거버넌스의 Step 1~8 순차 단계는 이번 Step 8 closeout으로 닫힌다.
2. future packaging revisit가 필요하면 `app.py`/worker/Alembic/tests import contract explicit화와 Step 6 future decomposition 정리를 먼저 끝낸 뒤 별도 ADR/plan로 연다.
3. `business_calendar` / `/calendar` 축은 사용자 별도 지시 전까지 계속 제외한다.
