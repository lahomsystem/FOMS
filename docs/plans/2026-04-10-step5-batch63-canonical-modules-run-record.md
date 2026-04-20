# Step 5 Batch 63 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step5-batch62-helper-extraction-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: measurement page/API source of truth를 `foms.web.measurement.dashboard`, `foms.api.measurement`로 이동하고 legacy `apps/*` 진입점을 alias shim으로 축소한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 5 Batch 63 executed, canonical measurement page/API modules completed**

이유:
- `foms/web/measurement/dashboard.py`, `foms/api/measurement.py`, `foms/web/measurement/__init__.py`를 추가해 measurement slice의 page/API source of truth를 `foms/` namespace 아래로 이동했다.
- 기존 `apps/erp_measurement_dashboard.py`, `apps/api/erp_measurement.py`는 `sys.modules[__name__] = _mod` alias shim으로 축소해 기존 import/monkeypatch contract를 유지했다.
- shared helper import는 Batch 62에서 분리한 `foms.services.measurement_dates`를 기준으로 정렬했다.

## 2. 실제 변경 범위
- `foms/web/measurement/__init__.py`
- `foms/web/measurement/dashboard.py`
- `foms/api/measurement.py`
- `apps/erp_measurement_dashboard.py`
- `apps/api/erp_measurement.py`
- `tests/test_measurement_slice_contract.py`
- `tests/test_foms_namespace_imports.py`

## 3. 의도적으로 건드리지 않은 것
- measurement map branch delegation
- measurement template/JS canonical namespace 이동
- `business_calendar` / `/calendar`

## 4. 검증 결과
### 4.1 canonical module + mobile render suite
- 실행:
  - `python -m pytest tests/test_measurement_slice_contract.py tests/test_erp_measurement_mobile_render.py -q`
- 결과:
  - `6 passed in 1.43s`

### 4.2 namespace contract gate
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py -q`
- 결과:
  - `132 passed in 0.18s`

## 5. 해석
- Step 5의 핵심 구조 전환은 이 배치에서 닫혔다. 이후부터 `apps/*`는 source of truth가 아니라 호환성 shim이며, 실제 page/API 구현은 `foms/` 아래만 보면 된다.
- alias shim 패턴은 Step 3에서 사용한 thin shim과 달리 module identity를 유지하는 방식이라 monkeypatch/legacy import 의존을 그대로 흡수한다.

## 6. 다음 단계
1. Batch 64에서 `apps/api/erp_map.py`의 measurement 전용 branch를 slice-local helper로 위임한다.
2. `business_calendar` / `/calendar` 축은 계속 제외한다.
