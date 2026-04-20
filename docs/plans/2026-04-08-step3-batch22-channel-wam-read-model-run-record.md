# Step 3 Batch 22 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch21-file-utils-run-record.md`

- 일시: 2026-04-08 14:40:25
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `channel_wam_read_model`을 스무 번째 실제 `foms/services` source of truth로 이동하고 WAM service가 canonical read model import를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 22 executed, `channel_wam_read_model` canonical migration completed without intended WAM behavior changes**

이유:
- `foms/services/channel_wam_read_model.py`를 새 canonical source로 추가하고, 기존 `services/channel_wam_read_model.py`는 공개 API 전체를 재수출하는 thin shim으로 전환했다.
- canonical 파일 내부의 `erp_display` 의존은 `from foms.services.erp_display import ...`로 정리해 Step 3 runtime namespace 방향과 일치시켰다.
- `services/channel_wam_service.py`가 `load_wam_order_read_model`을 canonical path에서 직접 import하도록 정리해 hot path도 shim 경유 없이 canonical namespace를 사용하게 만들었다.
- `tests/test_foms_namespace_imports.py`에 read model shim 계약 테스트와 `channel_wam_service`의 canonical import 바인딩 테스트를 추가해 공개 API 동일성뿐 아니라 실제 production import 방향까지 고정했다.
- WAM focused tests/namespace smoke/`APP_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
Batch 21 완료 직후 자동 전감리 결과:
1. `channel_wam_read_model`
2. `channel_wam_attachments`
3. `order_storage_cleanup`

선정 이유:
- `channel_wam_read_model`은 Batch 20의 `channel_wam_view_models`, Batch 22 직전 상태의 `channel_wam_service`와 같은 WAM 축이라 구조 연속성이 높았다.
- production Python caller가 사실상 `services/channel_wam_service.py` 한 곳으로 좁아 import blast radius가 작았다.
- DB/read model 성격이라 구현 리팩터를 섞으면 위험하지만, 이번 배치는 “이동 + import 정리 + shim + 계약 테스트”로만 제한하면 충분히 통제 가능하다고 전감리에서 판정됐다.
- `channel_wam_attachments`는 storage 축이 섞여 있어 다음 자동 후보로 남겼고, `order_storage_cleanup`는 영구 삭제/스토리지 정합 리스크 때문에 계속 제외했다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/channel_wam_read_model.py`
  - 기존 구현을 그대로 canonical 위치로 이동
  - 모듈 docstring 추가
  - 공개 API `__all__` 명시:
    - `STATUS_LABELS`
    - `WamTimelineEntry`
    - `WamOrderReadModel`
    - `get_order_for_wam`
    - `load_wam_order_read_model`
    - `build_order_read_model`
    - `get_recent_events_for_wam`
  - 내부 service import를 `from foms.services.erp_display import ...`로 canonical 정렬

### 3.2 legacy shim 전환
- `services/channel_wam_read_model.py`
  - 위 공개 API 전체를 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `services/channel_wam_service.py`
  - `from services.channel_wam_read_model import load_wam_order_read_model`
  - →
  - `from foms.services.channel_wam_read_model import load_wam_order_read_model`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_channel_wam_read_model` / `namespaced_channel_wam_read_model` import 추가
  - `test_legacy_channel_wam_read_model_shim_preserves_canonical_contract()` 추가
    - `__all__` 일치
    - 공개 심볼 객체 동일성(`is`) 검증
  - `test_channel_wam_service_uses_canonical_read_model_import()` 추가
    - hot path인 `services.channel_wam_service.load_wam_order_read_model`이 canonical helper 객체와 동일한지 검증

## 4. 감리 결과 요약
### 4.1 사전 감리
- medium 메모: canonical 파일에서는 `foms.services.erp_display`를 사용해야 행동 동일성과 namespace 일관성이 유지된다.
- medium 메모: DB/read model 성격이므로 로직 변경을 섞지 말고 이동/경로 정리만 해야 구조-only 배치로 안전하다.
- low 메모: direct unit test는 없으나 WAM bootstrap 통합 테스트가 간접 커버를 제공한다.

### 4.2 사후 감리
- high/medium 회귀·shim drift·행동 변화 finding은 없었다.
- low 수준으로 대형 함수(`load_wam_order_read_model`) 길이, `channel_wam_service`의 read_model 타입 힌트 부족, canonical import 고정 테스트 부재가 식별됐다.
- 이 중 즉시 반영 가능한 항목인 canonical import 고정 테스트는 같은 배치 안에서 바로 추가했다.

## 5. 의도적으로 건드리지 않은 것
- `services/channel_wam_attachments.py`
- `services/channel_wam_telemetry.py`
- `services/channel_quick_actions.py`
- `apps/api/channel_wam.py`
- `services/order_storage_cleanup.py`
- `services/app_init.py`
- `apps/api/erp_orders_structured.py`
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `channel_wam_read_model` 내부 비즈니스 로직 분해/상수화

## 6. 검증 결과
### 6.1 focused tests
- 실행: `python -m pytest tests/test_foms_namespace_imports.py tests/test_channel_wam_backend.py tests/test_channel_wam_routes.py`
- 결과:
  - 최초 구현 후 `48 passed`
  - canonical import 고정 테스트 추가 후 `49 passed`

### 6.2 namespace smoke
- 실행: `python -c "import services.channel_wam_read_model as legacy; import foms.services.channel_wam_read_model as ns; assert legacy.load_wam_order_read_model is ns.load_wam_order_read_model; assert legacy.build_order_read_model is ns.build_order_read_model; assert legacy.get_recent_events_for_wam is ns.get_recent_events_for_wam; print('CHANNEL_WAM_READ_MODEL_NS_OK')"`
- 결과: `CHANNEL_WAM_READ_MODEL_NS_OK`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행:
  - 초기: `python -m pytest`
  - 최종: `python -m pytest`
- 결과:
  - 초기 `267 passed, 3 warnings`
  - 최종 `268 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `channel_wam_read_model`은 스무 번째 실제 `foms/services` source of truth가 되었고, WAM view model에 이어 WAM read model 축도 canonical namespace로 한 단계 더 전진했다.
- 이번 배치는 DB read model 성격을 가진 모듈이었지만, 구현 리팩터를 섞지 않고 파일 위치/경로/shim/계약 테스트만 다뤄 구조-only 원칙을 유지했다.
- `channel_wam_service` hot path까지 canonical import로 고정했기 때문에, 다음 자동 단계는 WAM 축을 이어 `channel_wam_attachments`를 다루는 것이 가장 자연스럽다.

## 8. 다음 단계
1. 자동 다음 구조 후보는 `channel_wam_attachments`로 잡고, storage/job 연계 범위를 전감리해 Batch 23 적합성을 판단한다
2. `channel_wam_service` 자체 canonicalization은 `channel_wam_attachments`/`channel_wam_telemetry` 정리가 더 진행된 뒤 묶는 편이 안전한지 비교한다
3. `order_storage_cleanup`는 여전히 영구 삭제/스토리지 정합 리스크 때문에 별도 검증 전략 없이는 뒤로 유지한다
