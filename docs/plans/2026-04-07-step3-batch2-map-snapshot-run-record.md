# Step 3 Batch 2 Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-07-step3-batch1-run-record.md`

- 일시: 2026-04-07
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `map_snapshot`를 Step 3의 첫 실제 vertical slice로 옮기고 legacy `services/` 경로를 호환 shim으로 유지

## 1. 전체 판정
**Verdict: Step 3 Batch 2 executed, first real service slice moved under `foms/`**

이유:
- `foms/services/map_snapshot.py`를 canonical source of truth로 추가했다.
- legacy `services/map_snapshot.py`는 공개 API 두 개만 재수출하는 thin shim으로 전환했다.
- 실제 호출부 `apps/api/erp_map.py`, `tests/test_map_snapshot.py`를 canonical import로 정리했다.
- 사전 감리와 사후 감리를 각각 수행했고, 사후 감리에서 발견된 shim 표면 과노출(`import *`)까지 `__all__`/명시 import로 차단했다.

## 2. 실제 변경 범위
### 2.1 canonical source
- `foms/services/map_snapshot.py`

### 2.2 legacy compatibility shim
- `services/map_snapshot.py`

### 2.3 canonical caller 전환
- `apps/api/erp_map.py`
- `tests/test_map_snapshot.py`

### 2.4 shim 검증 보강
- `tests/test_foms_namespace_imports.py`

## 3. 감리 결과 요약
### 3.1 사전 감리
- `services/map_snapshot.py`는 호출부가 좁고(`apps/api/erp_map.py`, `tests/test_map_snapshot.py`) DB/Alembic 리스크가 없어 첫 실제 slice 후보로 적합하다고 판정했다.
- legacy shim 유지 시 순환 import 위험이 낮고, 구조 변경과 로직 변경을 분리할 수 있다고 확인했다.

### 3.2 사후 감리
- 초안 구현 후 `services/map_snapshot.py`의 `import *`가 과도한 공개 표면을 만든다는 high finding 1건이 나왔다.
- canonical 모듈에 `__all__`을 추가하고, legacy shim을 명시 import + `__all__`로 좁혀 즉시 수정했다.
- `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수/타입 힌트 부족은 이번 배치가 만든 회귀가 아니라 기존 residual risk로 분리했다.

## 4. 의도적으로 건드리지 않은 것
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
- `templates/`
- `static/`
- `services/erp_display.py`
- `services/geocode_helpers.py`
- `services/erp_shipment_settings.py`
- `services/measurement_manager_colors.py`

## 5. 검증 결과
### 5.1 namespace smoke
- 실행: `python -c "from foms.services.map_snapshot import build_measurement_snapshot; from services.map_snapshot import build_measurement_map_query; print('MAP_NS_OK')"`
- 결과: 통과

### 5.2 focused test
- 실행: `python -m pytest tests/test_map_snapshot.py tests/test_foms_namespace_imports.py -q`
- 결과: `5 passed`

### 5.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: 통과

### 5.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 5.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `177 passed, 3 warnings in 23.12s`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 5.6 lint
- 실행: `ReadLints` (`services/map_snapshot.py`, `foms/services/map_snapshot.py`, `apps/api/erp_map.py`, `tests/test_map_snapshot.py`, `tests/test_foms_namespace_imports.py`)
- 결과: 신규 lint 없음

## 6. 해석
- Step 3는 이제 namespace skeleton 단계에서 멈추지 않고, 실제 서비스 구현 하나를 `foms/` 아래 source of truth로 옮긴 상태다.
- legacy 경로는 계속 살아 있으나, 공개 표면을 두 함수로 제한해 “호환 shim” 역할만 수행한다.
- 따라서 다음 Step 3 후속 배치는 두 번째 slice 후보를 고르거나, 이번 배치에서 확인된 기존 residual risk를 별도 감리 단위로 분리하는 문제로 넘어간다.

## 7. 다음 단계
1. `services` 또는 `platform` 계열에서 두 번째 실제 vertical slice 후보를 선정
2. `manager_filter` 이중 적용 / `lat-lng` 안전 파싱 같은 기존 residual risk를 이번 구조 배치와 분리해 별도 감리 대상으로 관리
3. `app.py` slim entrypoint 작업은 여전히 별도 감리 단위로 유지
