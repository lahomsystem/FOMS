# Step 4 Batch 59 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step4-batch58-realtime-limiter-extraction-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Flask app 생성·설정·middleware orchestration을 `foms/platform/app_factory.py`로 이동하고 root `app.py`를 thin adapter로 축소한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 4 Batch 59 executed, app factory extraction completed and root `app.py` became a thin adapter**

이유:
- `foms/platform/app_factory.py`에 `build_app(socketio_available=...)`를 추가해 Flask app 생성, Compress, WhiteNoise, ProxyFix, session/secret key config, blueprint/http/realtime bootstrap orchestration을 이동했다.
- root `app.py`는 early gevent/Werkzeug patch, canonical 공개 심볼 import, Socket.IO availability detection, `build_app()` 호출, WSGI auto-init/main 분기만 남는 thin adapter 형태로 축소됐다.
- `tests/test_foms_namespace_imports.py`의 canonical storage source-path 검증이 root adapter에서 실패하는 회귀를 사후감리 중 즉시 포착했고, `from foms.services.storage import get_storage` import를 복원해 계약을 유지했다.
- 사후감리 low 항목으로 드러난 `BlueprintBindings.can_edit_erp` 미사용 필드는 제거했고, `foms/platform/http.py` 내부 함수 시그니처를 정리했으며, gevent fail-open은 warning log를 남기도록 보강했다.

## 2. 실제 변경 범위
- `foms/platform/app_factory.py`
- `foms/platform/__init__.py`
- `foms/platform/blueprints.py`
- `foms/platform/http.py`
- `app.py`

## 3. 의도적으로 건드리지 않은 것
- `app:app` 시작 경로
- `run_auto_init()` 내부 business logic
- `start.sh` / `Procfile` / `run.py`
- `business_calendar` / `/calendar`

## 4. 검증 결과
### 4.1 focused Step 4 contract suite
- 실행:
  - `python -m pytest tests/test_app_bootstrap_contract.py tests/test_foms_namespace_imports.py tests/test_rate_limit.py -q`
- 결과:
  - `138 passed in 0.25s`

### 4.2 전체 테스트
- 실행:
  - `python -m pytest -q`
- 결과:
  - `427 passed, 3 warnings`
- 관찰 사항:
  - 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 4.3 app import smoke
- 실행:
  - `python -c "import app; print('APP_OK')"`
- 결과:
  - `APP_OK`

### 4.4 root public import contract
- 실행:
  - `python -c "import app as m; print(hasattr(m,'app'), hasattr(m,'socketio'), hasattr(m,'run_auto_init'), 'notifications.api_notifications_badge' in m.app.view_functions)"`
- 결과:
  - `True True True True`

### 4.5 shared verification
- 실행:
  - `python tools/harness/verify_result.py --json`
- 결과:
  - `success: true`

### 4.6 lint
- 실행:
  - `ReadLints`
- 결과:
  - 신규 lint 없음

## 5. 사후감리 요약
- 코드 관점: high/medium 신규 결함 없음. 미사용 binding field 제거와 타입 힌트 정리로 low 소음 일부 해소.
- 운영 관점 residual risk:
  - `start.sh` 경유가 아닌 Procfile-only 기동 환경은 Alembic 선행 실행이 빠질 수 있으므로 문서화 필요
  - `run_auto_init(app)`는 기존과 동일하게 gunicorn 다중 worker import 시 각 worker에서 실행되는 패턴을 유지한다

## 6. 해석
- Step 4의 핵심 목표였던 `app.py` slim entrypoint는 달성됐고, root bootstrap contract와 `app:app` 경로는 유지됐다.
- 남은 작업은 실행 기록/상태 문서 closeout뿐이다.
