# Step 3 Batch 49 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch48-erp-policy-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy` (작업 기준)
- 실행자: AI agent
- 목적: `services/jobs` 패키지 본체를 canonical `foms/services/jobs/*`로 이관하고, legacy `services.jobs.tasks.*` enqueue 문자열은 유지해 Redis/RQ backlog 호환을 지키면서 internal canonical caller를 정리한다
- 제외 축: app/API/script 전역 `services.jobs.queue` live caller cleanup은 이번 배치 범위 밖이며 후속 배치 후보로 남긴다

## 1. 전체 판정
**Verdict: Step 3 Batch 49 executed — canonical jobs package + legacy task-path compatibility + internal caller alignment without runtime regression**

이유:
- Source of truth를 `foms/services/jobs/{queue,tasks}.py`와 `foms/services/jobs/__init__.py`로 이동했다.
- `services/jobs/{queue,tasks}.py`는 thin shim으로 유지하고 `services/jobs/__init__.py`는 package-level shim으로 정리해 기존 import 계약을 보존했다.
- `foms/services/jobs/queue.py`의 enqueue 문자열은 의도적으로 `services.jobs.tasks.*`를 유지해 이미 큐에 들어간 legacy job 경로와 worker import 호환을 깨지 않았다.
- `foms/services/jobs/tasks.py`는 repo root 계산을 `Path(__file__).resolve().parents[3]`로 고정해 namespaced 위치에서도 worker 단독 실행 bootstrap을 유지했다.

## 2. 변경 파일 (요약)
- 신규/이동: `foms/services/jobs/__init__.py`, `foms/services/jobs/queue.py`, `foms/services/jobs/tasks.py`
- Shim: `services/jobs/__init__.py`, `services/jobs/queue.py`, `services/jobs/tasks.py`
- Internal caller: `foms/services/channel_inbound.py`, `foms/services/order_attachment_thumbnail.py`
- 테스트: `tests/test_foms_namespace_imports.py`, `tests/test_order_attachment_thumbnail.py`, `tests/test_channel_integration_smoke.py`
- 문서: 본 run record, `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/context/COMPACT_CHECKPOINT.md`, `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`

## 3. 검증
- `python -m pytest tests/test_foms_namespace_imports.py tests/test_order_attachment_thumbnail.py tests/test_channel_integration_smoke.py tests/test_channel_webhooks.py` — 통과 (`130 passed`)
- `python -c "… JOBS_NS_OK …"` (legacy/canonical identity + `_TASK_PATH_PREFIX` + `_REPO_ROOT`) — 통과
- `python -c "import app; print('APP_OK')"` — 통과
- `python tools/harness/verify_result.py --json` — 통과
- `ReadLints` — 신규 lint 없음

## 4. 잔여 리스크 / 후속 후보
- `apps/api/channel_integration.py`, `apps/api/erp_measurement.py`, `apps/api/erp_map.py`, `apps/api/orders.py`, `apps/order_pages.py`, `apps/order_edit.py`, `scripts/geocode_backfill.py` 등 app/API/script live caller는 아직 `services.jobs.queue`를 사용한다. 이는 shim으로 안전하지만 canonical cleanup 배치는 아직 남아 있다.
- `services.jobs.tasks.*` enqueue 문자열은 backlog 호환을 위한 의도적 유지다. 향후 완전 cutover를 하려면 worker/web 동시 배포와 queue drain 전략이 함께 필요하다.
- `business_calendar` 및 `/calendar` 축은 사용자 지시에 따라 계속 migration scope 밖으로 유지한다.
