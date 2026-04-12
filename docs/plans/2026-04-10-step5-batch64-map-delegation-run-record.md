# Step 5 Batch 64 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step5-batch63-canonical-modules-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: shared `erp_map` shell은 유지하되 measurement 전용 backend branch를 slice-local helper로 위임해 Step 5 scope 안에서 map flow를 닫는다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 5 Batch 64 executed, measurement map mode delegation completed**

이유:
- `foms/api/measurement_map.py`를 추가해 `/api/map_data`, `/api/generate_map`의 `dashboard=measurement` 분기를 slice-local helper로 이동했다.
- `apps/api/erp_map.py`는 measurement branch만 새 helper로 위임하고, shared map shell/route 계약은 그대로 유지했다.
- map query/snapshot/geocode enqueue 흐름은 기존 legacy query 규칙을 보존한 채 measurement slice 내부에서 읽을 수 있게 정리했다.

## 2. 실제 변경 범위
- `foms/api/measurement_map.py`
- `apps/api/erp_map.py`
- `tests/test_foms_namespace_imports.py`

## 3. 의도적으로 건드리지 않은 것
- `templates/map_view.html` shared shell
- shared map route 전체 이관
- `business_calendar` / `/calendar`

## 4. 검증 결과
### 4.1 map delegation suite
- 실행:
  - `python -m pytest tests/test_map_snapshot.py tests/test_foms_map_generator.py tests/test_map_view_manager_contract.py -q`
- 결과:
  - `15 passed in 0.15s`

### 4.2 namespace contract gate
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py -q`
- 결과:
  - `132 passed in 0.18s`

## 5. 해석
- measurement slice는 dashboard/page/API만 옮기고 끝내면 map branch가 여전히 shared module에 남아 경계가 흐려진다. 이 배치로 measurement-specific backend branch를 slice 내부로 묶어 vertical slice pilot이라는 목적에 맞는 닫힌 경계를 만들었다.
- shared `map_view.html`은 Step 5 범위 밖에 두되, measurement-specific 응답 조합은 slice 내부에서 해석할 수 있게 됐다.

## 6. 다음 단계
1. Batch 65에서 measurement template/partial/JS canonical namespace 이동과 legacy wrapper를 적용한다.
2. `business_calendar` / `/calendar` 축은 계속 제외한다.
