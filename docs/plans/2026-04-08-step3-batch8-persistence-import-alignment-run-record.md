# Step 3 Batch 8 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-07-step3-batch7-erp-display-run-record.md`

- 일시: 2026-04-08
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `foms/services/*` 내부에 남아 있던 root `db`/`models` 직접 import를 `foms.persistence.main.*` 경로로 정렬해 runtime namespace 내부 의존 방향을 한 단계 더 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서 의도적으로 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 8 executed, persistence import alignment completed inside `foms/services/*`**

이유:
- `foms/services/map_snapshot.py`, `foms/services/erp_shipment_settings.py`, `foms/services/erp_display.py`가 root `db`/`models` 대신 `foms.persistence.main.*`를 사용하도록 정렬됐다.
- `foms/services/*` 아래에서 `from db ...`, `from models ...` 직접 참조가 0건임을 확인했다.
- 동작은 기존 thin persistence shim(`foms.persistence.main.db`, `foms.persistence.main.models`)을 그대로 경유하므로 비즈니스 로직 변경 없이 구조만 정리한 배치다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `foms/services/*` 내부 `db`/`models` → `foms.persistence.main.*` 정렬
2. `services/erp_policy.py` staged migration
3. 남아 있는 `services.erp_display` 호출부 전면 canonical import 정리

선정 이유:
- `erp_policy`는 `__file__` 기준 `data/` 경로 계산과 `business_calendar` 의존을 갖고 있어, 이번처럼 “가장 안전한 다음 배치” 기준에서는 리스크가 컸다.
- `erp_display` 호출부 전면 canonical import 정리는 파일 수가 너무 많아 staged 원칙에 비해 PR 표면적이 컸다.
- `foms/services/*` 내부 persistence import 정렬은 영향 파일이 3개뿐이고, 이미 존재하는 persistence shim을 활용하므로 구조 이득 대비 위험이 가장 낮았다.

## 3. 실제 변경 범위
### 3.1 persistence import 정렬
- `foms/services/map_snapshot.py`
  - `Order`, `OrderScheduleDate` import를 `foms.persistence.main.models`로 전환
- `foms/services/erp_shipment_settings.py`
  - `db_session` import를 `foms.persistence.main.db`로 전환
  - `SystemSetting` import를 `foms.persistence.main.models`로 전환
- `foms/services/erp_display.py`
  - 지연 import `db_session`, `User`를 `foms.persistence.main.*`로 전환

### 3.2 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `OrderScheduleDate`, `SystemSetting`이 `foms.persistence.main.models`와 root `models`에서 동일 객체임을 추가 검증

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar`는 사용자 요청대로 제외했다.
- `erp_policy`는 `data/` 경로 계산 이슈와 `business_calendar` 연동 때문에 이번 배치 후보에서 제외되었다.
- 이번 배치는 `foms/services/*` 내부 의존 방향 정렬에만 집중하는 것으로 결정했다.

### 4.2 사후 감리
- `foms/services/*` 아래에서 root `db`/`models` 직접 import는 더 이상 남아 있지 않음을 확인했다.
- persistence shim이 `db`/`models`를 그대로 재수출하는 구조라 런타임 객체 단일성이 유지됨을 smoke/test로 확인했다.
- low 수준 residual risk로는 `erp_shipment_settings`의 `print()` 기반 오류 노출과, `business_calendar`를 제외한 상태에서 앞으로 `erp_policy` / `services/*` / `apps/*` 전반을 어떤 순서로 계속 정리할지 남아 있다.

## 5. 의도적으로 건드리지 않은 것
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `services/erp_policy.py`
- `services/erp_display.py`
- `services/erp_shipment_settings.py`
- root `db.py`
- root `models.py`
- `apps/*`, `services/*`, `app.py`, `run.py`, `scripts/*`의 legacy persistence import 전반

## 6. 검증 결과
### 6.1 구조 확인
- 실행: `rg` (`foms/services` 범위)
- 패턴: `^from models import|^import models|^from db import|^import db`
- 결과: `No matches found`

### 6.2 namespace smoke
- 실행: `python -c "import foms.services.map_snapshot as ms; import foms.services.erp_shipment_settings as ess; import foms.persistence.main.models as m; assert ms.Order is m.Order; assert ess.SystemSetting is m.SystemSetting; print('PERSISTENCE_NS_OK')"`
- 결과: `PERSISTENCE_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_foms_namespace_imports.py tests/test_map_snapshot.py tests/test_erp_shipment_settings.py tests/test_erp_display.py -q`
- 결과: `17 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `206 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 단순한 `foms/services` source 이동뿐 아니라, 그 내부에서 persistence 경로도 `foms.persistence.main.*`로 정렬되기 시작한 상태다.
- 사용자 요청대로 `business_calendar`는 이번 구조 정리의 기준축에서 제외했다.
- 따라서 다음 남은 구조 축은 크게 두 갈래다.
  1. `services/erp_policy.py`와 그 의존 축을 staged 방식으로 설계할지
  2. `foms/services` 밖(`apps/*`, root `services/*`, `app.py`, `scripts/*`)의 legacy persistence import를 어떤 단위로 끊어갈지

## 8. 다음 단계
1. `business_calendar`를 계속 제외한 상태에서 `erp_policy` staged migration 가능성만 별도 설계/감리
2. 또는 더 안전하게 `apps/*`/root `services/*` 중 한 도메인 단위로 `foms.persistence.main.*` 경로 정렬 배치 시작
3. 품질 배치 후보(`manager_filter` 이중 적용, `lat/lng` 안전 파싱, `erp_shipment_settings` 예외 처리, 긴 함수 분해)와 구조 배치의 우선순위 재비교
