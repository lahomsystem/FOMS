# Step 4 Batch 60 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step4-batch59-app-factory-extraction-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Step 4 Batch 55~59의 감리/검증 결과를 문서화하고 거버넌스 상태 문서를 closeout한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 4 closeout completed, `app.py` slim entrypoint migration is closed**

이유:
- Batch 55~59 실행 기록을 `docs/plans/2026-04-10-step4-batch55~59-*.md`로 남겼다.
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`, `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/context/COMPACT_CHECKPOINT.md`를 Step 4 완료 상태로 갱신했다.
- root `app.py` thin adapter, `foms/platform/{blueprints,http,realtime,app_factory}.py` bootstrap source of truth, `app:app` 계약 유지가 문서와 실행 상태 양쪽에서 일치한다.

## 2. 실제 변경 범위
- `docs/plans/2026-04-10-step4-batch55-bootstrap-contract-freeze-run-record.md`
- `docs/plans/2026-04-10-step4-batch56-blueprint-registry-extraction-run-record.md`
- `docs/plans/2026-04-10-step4-batch57-http-bootstrap-extraction-run-record.md`
- `docs/plans/2026-04-10-step4-batch58-realtime-limiter-extraction-run-record.md`
- `docs/plans/2026-04-10-step4-batch59-app-factory-extraction-run-record.md`
- `docs/plans/2026-04-10-step4-batch60-closeout-run-record.md`
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- `docs/AI_STATUS.md`
- `docs/ARCHIVE_INDEX.md`
- `docs/context/COMPACT_CHECKPOINT.md`

## 3. 사후감리 요약
### 3.1 코드 관점
- independent post-audit 결과 high/medium 신규 결함 없음
- low 정리:
  - `BlueprintBindings.can_edit_erp` 미사용 필드 제거
  - `foms/platform/http.py` 내부 handler 타입 힌트 정리
  - gevent fail-open 경로에 warning log 추가

### 3.2 운영 관점 residual risk
- `Procfile`만 직접 사용하는 환경은 `start.sh`의 Alembic 선행 실행이 없으므로 운영 문서에서 시작 커맨드 차이를 계속 명시해야 한다.
- `run_auto_init(app)`는 기존과 동일하게 gunicorn 다중 worker import 시 각 worker에서 실행되는 패턴을 유지한다.

## 4. 최종 검증 결과
### 4.1 전체 테스트
- 실행:
  - `python -m pytest -q`
- 결과:
  - `427 passed, 3 warnings`
- 관찰 사항:
  - 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 4.2 app import smoke
- 실행:
  - `python -c "import app; print('APP_OK')"`
- 결과:
  - `APP_OK`

### 4.3 root public import contract
- 실행:
  - `python -c "import app as m; print(hasattr(m,'app'), hasattr(m,'socketio'), hasattr(m,'run_auto_init'), 'notifications.api_notifications_badge' in m.app.view_functions)"`
- 결과:
  - `True True True True`

### 4.4 shared verification
- 실행:
  - `python tools/harness/verify_result.py --json`
- 결과:
  - `success: true`

### 4.5 lint
- 실행:
  - `ReadLints`
- 결과:
  - 신규 lint 없음

## 5. 해석
- Step 4의 목표였던 root `app.py` slim entrypoint 전환은 완료됐다.
- bootstrap 구현은 `foms/platform`으로 이동했지만 root 공개 계약(`app`, `socketio`, `SOCKETIO_AVAILABLE`, `init_limiter`, `register_context_processors`, `run_auto_init`, `can_edit_erp`, `recommend_owner_team`, `can_modify_domain`, `get_stage`)과 `app:app` 경로는 유지됐다.
- 사용자 제외 범위인 `business_calendar`/`/calendar` 축은 이번 closeout에서도 그대로 제외했다.

## 6. 다음 단계
1. 거버넌스 자동 다음 단계는 Step 5(vertical slice 1개 시범 이관) 전감리다.
2. Step 5에서도 `business_calendar`/`/calendar` 축은 사용자 별도 지시 전까지 계속 제외한다.
