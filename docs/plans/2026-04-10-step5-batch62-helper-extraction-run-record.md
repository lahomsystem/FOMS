# Step 5 Batch 62 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step5-batch61-contract-freeze-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: measurement page/API가 공유하던 실측일 추출 helper를 canonical service layer로 승격한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 5 Batch 62 executed, shared measurement helper extraction completed**

이유:
- `foms/services/measurement_dates.py`를 추가해 `extract_all_measurement_dates()`와 내부 중복 제거 helper를 canonical service source of truth로 고정했다.
- measurement page/API가 모두 새 helper를 import하도록 정리해 Step 5 이후에도 date extraction 규칙이 한 곳에만 남도록 만들었다.
- legacy `business_calendar` import는 사용자 제외 범위를 존중해 그대로 유지했다.

## 2. 실제 변경 범위
- `foms/services/measurement_dates.py`
- `apps/erp_measurement_dashboard.py`
- `apps/api/erp_measurement.py`
- `tests/test_foms_namespace_imports.py`

## 3. 의도적으로 건드리지 않은 것
- measurement page/API module source-of-truth 위치 자체
- map shell/template/JS namespace 이동
- `business_calendar` / `/calendar`

## 4. 검증 결과
### 4.1 namespace + helper caller suite
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py tests/test_erp_measurement_manager_sync.py -q`
- 결과:
  - `135 passed in 1.70s`

### 4.2 closeout namespace re-check
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py -q`
- 결과:
  - `132 passed in 0.18s`

## 5. 해석
- Step 5의 shared helper extraction은 구조-only 원칙을 지키면서 source-of-truth를 `foms/services` 아래로 밀어 넣는 가장 작은 단위였다.
- 이후 Batch 63에서 page/API source 자체를 `foms.web.measurement.dashboard`, `foms.api.measurement`로 옮겨도 실측일 계산 규칙은 이 helper 하나만 보면 된다.

## 6. 다음 단계
1. Batch 63에서 measurement page/API source를 canonical module로 이동하고 `apps/*`는 alias shim으로 축소한다.
2. `business_calendar` / `/calendar` 축은 계속 제외한다.
