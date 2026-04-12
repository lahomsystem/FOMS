# Step 3 Batch 46 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch45-order-date-sync-event-run-record.md`

- 일시: 2026-04-10 16:48:00
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `storage`를 마흔네 번째 실제 `foms/services` source of truth로 이동하고 singleton/runtime init 계약을 깨지 않는 thin shim 구조를 고정한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 46 executed, `storage` canonical migration completed with a single shared singleton contract and canonical-facing callers aligned**

이유:
- `foms/services/storage.py`를 새 canonical source로 추가하고, 기존 `services/storage.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- 가장 큰 구조 리스크였던 singleton 분리 가능성을 `legacy_storage.get_storage is namespaced_storage.get_storage` / `StorageAdapter` identity 검증으로 직접 고정했다.
- `foms/services/*` 내부의 storage import 여섯 곳만 canonical path로 정렬하고, fan-in이 넓은 `apps/*`/worker/bootstrap caller는 의도적으로 shim에 남겨 structure-only 범위를 유지했다.

## 2. 선정 근거
Batch 45 완료 후 자동 전감리 결과:
1. `storage`
2. `erp_policy`
3. `business_calendar` (계속 제외)

선정 이유:
- `storage`는 다음 구조 후보 중 유일하게 dedicated batch로 분리 가능한 고위험 slice였다.
- import 시 네트워크 연결은 없고 `get_storage()` 지연 생성만 있어, source-of-truth 이동 자체는 구조-only로 수행 가능했다.
- 다만 singleton/runtime init과 넓은 caller fan-in이 있어, 한 번에 전체 caller를 바꾸지 않고 canonical-facing `foms/services/*` 내부 caller만 우선 정렬하는 방식이 가장 안전했다.
- `erp_policy`는 여전히 `business_calendar` eager import와 광범위 caller 때문에 고위험 유지였다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/storage.py`
  - 기존 `services/storage.py` 구현을 canonical 위치로 이동
  - `__future__` 추가
  - 공개 API `__all__ = ["BOTO3_AVAILABLE", "PILLOW_AVAILABLE", "StorageAdapter", "get_storage"]` 명시
  - 기존 runtime behavior, 환경변수 감지, direct upload helper, thumbnail helper, singleton 패턴은 유지

### 3.2 legacy shim 전환
- `services/storage.py`
  - `BOTO3_AVAILABLE`, `PILLOW_AVAILABLE`, `StorageAdapter`, `get_storage`만 재수출하는 thin shim으로 전환
  - shim이 canonical 함수/클래스 identity를 그대로 공유하도록 정리

### 3.3 canonical-facing caller 정렬
- `foms/services/order_attachment_thumbnail.py`
- `foms/services/channel_wam_attachments.py`
- `foms/services/order_storage_cleanup.py`
- `foms/services/channel_quick_actions.py`
- `foms/services/context_processors.py`
- `foms/services/channel_dispatch.py`

위 여섯 파일의 storage import를 `from foms.services.storage import get_storage`로 정렬했다.

## 4. 테스트 보강
### 4.1 namespace / shim contract
- `tests/test_foms_namespace_imports.py`
  - `legacy_storage`, `namespaced_storage` import 추가
  - `test_legacy_storage_shim_preserves_canonical_contract()` 추가
  - `test_channel_dispatch_canonical_module_uses_canonical_storage_lazy_import()` 추가
  - `test_channel_wam_attachments_uses_canonical_storage_import()` 추가
  - `test_channel_quick_actions_uses_canonical_storage_import()`로 갱신
  - `test_context_processors_uses_canonical_storage_lazy_import()`로 갱신
  - `test_order_attachment_thumbnail_uses_canonical_storage_import()` 추가
  - `test_order_storage_cleanup_uses_canonical_storage_import()` 추가

### 4.2 기존 단위 테스트 영향
- `tests/test_order_storage_cleanup.py`, `tests/test_order_attachment_thumbnail.py`, `tests/test_channel_wam_backend.py`의 monkeypatch target은 유지되어 추가 수정 없이 통과했다.

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 메모:
  - `apps/*`, `services/jobs/tasks.py`, `app.py`는 fan-in과 blast radius를 고려해 이번 배치에서 shim 경로 유지
  - `storage`는 정리됐지만 다음 구조 후보 `erp_policy`는 여전히 separate high-risk batch가 필요

### 5.2 자동 다음 배치 전감리
- Batch 46 완료 후 구조-only 기준 다음 남은 실질 후보는 `erp_policy`
- 단, `business_calendar` eager import와 넓은 caller 때문에 바로 진행 가능한 상태는 아님
- `business_calendar` / `/calendar` 축은 사용자 지시에 따라 계속 제외

## 6. 의도적으로 건드리지 않은 것
- `apps/admin.py`, `apps/api/*`, `services/jobs/tasks.py`, `app.py`의 legacy `services.storage` caller
- `StorageAdapter` 내부 로깅/예외 처리/환경변수 fallback behavior
- `business_calendar` / `/calendar`
- `erp_policy`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_foms_namespace_imports.py tests/test_order_storage_cleanup.py tests/test_order_attachment_thumbnail.py tests/test_channel_wam_backend.py`
- 결과:
  - `122 passed`

### 7.2 namespace smoke
- 실행: `python -c "import services.storage as legacy_storage; import foms.services.storage as namespaced_storage; assert legacy_storage.get_storage is namespaced_storage.get_storage; assert legacy_storage.StorageAdapter is namespaced_storage.StorageAdapter; print('STORAGE_NS_OK')"`
- 결과: `STORAGE_NS_OK`

### 7.3 app import smoke
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 7.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `388 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 7.6 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `storage`는 마흔네 번째 실제 `foms/services` source of truth가 되었고, singleton/runtime init이 중요한 모듈도 runtime namespace 기준으로 정리됐다.
- 이번 배치는 source-of-truth 이동 + canonical-facing caller 정렬까지만 수행했고, fan-in이 넓은 legacy caller는 thin shim으로 안전하게 유지했다.

## 9. 다음 단계
1. 다음 구조 후보는 `erp_policy`지만, `business_calendar` eager import 때문에 별도 승인형 고위험 배치로 다뤄야 한다.
2. `apps/*`와 worker의 `services.storage` caller는 필요 시 후속 저위험 cleanup batch로 분리할 수 있다.
3. `business_calendar` / `/calendar` 축은 계속 제외한다.
