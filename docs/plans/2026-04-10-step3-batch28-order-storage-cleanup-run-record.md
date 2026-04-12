# Step 3 Batch 28 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch27-channel-security-run-record.md`

- 일시: 2026-04-10 10:28:02
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `order_storage_cleanup`를 스물여섯 번째 실제 `foms/services` source of truth로 이동하고 휴지통 영구 삭제 caller가 canonical path를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 28 executed, `order_storage_cleanup` canonical migration completed without changing permanent-delete storage cleanup semantics**

이유:
- `foms/services/order_storage_cleanup.py`를 새 canonical source로 추가하고, 기존 `services/order_storage_cleanup.py`는 thin shim으로 전환했다.
- `apps/order_trash.py`가 storage cleanup helper를 canonical path에서 직접 import하도록 정리했다.
- 기존에 없던 전용 테스트를 추가해 attachment/blueprint/drawing key 삭제 규칙과 early-return 동작을 고정했다.
- `ORDER_STORAGE_CLEANUP_NS_OK`/`verify_result.py --json`/최종 전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
Batch 27 완료 후 자동 전감리 결과:
1. `order_storage_cleanup`
2. `channel_quick_actions`
3. `user_deletion`

선정 이유:
- `order_storage_cleanup`는 caller가 `apps/order_trash.py` 한 곳뿐인 소형 모듈이라 structure-only 배치로 가장 안전했다.
- storage 삭제라는 부수효과는 있지만 import 그래프 자체는 단순했고, DB/Flask/Redis/HTTP와 얽힌 추가 helper 축이 없었다.
- `channel_quick_actions`는 DB + storage + `erp_display` private helper 결합이 남아 있어 이번 단계의 “가장 작은 안전 단위” 기준에서 후순위로 밀렸다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/order_storage_cleanup.py`
  - 기존 주문 영구 삭제 시 storage key 정리 구현을 canonical 위치로 이동
  - module docstring 추가
  - `__all__` 명시:
    - `delete_storage_files_for_order`
  - `VIEW_URL_PREFIX`는 내부 구현 상수로 유지
  - attachment / blueprint / `drawing_current_files` key 삭제 의미론은 structure-only 원칙에 따라 유지

### 3.2 legacy shim 전환
- `services/order_storage_cleanup.py`
  - `delete_storage_files_for_order`를 canonical에서 재수출하는 thin shim으로 전환
  - 기존 module-level constant 접근 호환성을 위해 `VIEW_URL_PREFIX`도 함께 재노출

### 3.3 caller canonical import 정리
- `apps/order_trash.py`
  - `delete_storage_files_for_order` import를 canonical path로 전환
  - 기존 `order_display_utils` canonical import와 함께 상단 import 정렬만 조정

## 4. 테스트 보강
### 4.1 namespace contract
- `tests/test_foms_namespace_imports.py`
  - `legacy_order_storage_cleanup` / `namespaced_order_storage_cleanup` import 추가
  - `test_legacy_order_storage_cleanup_shim_preserves_canonical_contract()` 추가
  - `test_order_trash_uses_canonical_storage_cleanup_import()` 추가

### 4.2 focused behavior verification
- `tests/test_order_storage_cleanup.py`
  - `test_delete_storage_files_for_order_deletes_valid_attachment_blueprint_and_drawing_keys()` 추가
  - `test_delete_storage_files_for_order_returns_early_when_order_missing()` 추가
  - canonical module의 `get_storage`를 monkeypatch해 실제 storage I/O 없이 삭제 대상 key만 검증

## 5. 감리 결과 요약
### 5.1 사전 감리
- `order_storage_cleanup`는 caller 1곳의 작은 destructive helper로 판정됐고, structure-only namespace 이행에 적합한 가장 작은 slice였다.
- `apps/order_trash.py`만 정리하면 runtime binding이 닫히므로 thin shim 패턴에 잘 맞는 모듈로 평가됐다.

### 5.2 사후 감리
- 신규 high/medium/low 회귀는 식별되지 않았다.
- residual gap으로 `VIEW_URL_PREFIX` object identity 자체를 shim 계약 테스트에서 직접 고정하지는 않았지만, 저장소 내 production import는 존재하지 않아 low risk로 판단했다.
- canonical code 내부의 `except Exception: pass`는 기존 정리 로직을 그대로 이동한 것이며, 이번 배치에서 새로 도입된 의미론은 아니다.

## 6. 의도적으로 건드리지 않은 것
- `order_storage_cleanup` 내부 예외 처리 정책(`except Exception: pass`)
- storage backend 구현(`services.storage`)
- `apps/order_trash.py`의 삭제 UX/권한 의미론
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_order_storage_cleanup.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `40 passed`

### 7.2 namespace smoke
- 실행: `python -c "import foms.services.order_storage_cleanup as m; print('ORDER_STORAGE_CLEANUP_NS_OK')"`
- 결과: `ORDER_STORAGE_CLEANUP_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `288 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `order_storage_cleanup`는 스물여섯 번째 실제 `foms/services` source of truth가 되었고, 휴지통 영구 삭제 축의 storage cleanup import 정리가 완료됐다.
- 다음 자동 전감리 기준 가장 안전한 구조 후보는 `rate_limit`로 재선정됐다. caller가 `app.py` 한 곳뿐이고 cross-service 결합이 거의 없기 때문이다.
- 그 다음 비교 후보는 `realtime_notifications`이며, `channel_quick_actions`는 여전히 결합도가 높아 후순위다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `rate_limit`
2. 그 다음 비교 후보는 `realtime_notifications`
3. 별도 품질 배치에서 `order_storage_cleanup`의 예외 처리 로깅 정책과 `channel_quick_actions`의 private helper 결합을 검토한다
