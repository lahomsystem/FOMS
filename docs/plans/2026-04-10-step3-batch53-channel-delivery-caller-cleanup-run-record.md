# Step 3 Batch 53 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch52-erp-permissions-caller-cleanup-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Batch 39에서 canonical source로 고정된 `channel_delivery`의 남은 live caller를 canonical `foms.services.channel_delivery` 경로로 정리해 production 앱 경로의 legacy lazy import를 제거한다

## 1. 전체 판정
**Verdict: Step 3 Batch 53 executed, `channel_delivery` caller cleanup completed**

이유:
- `channel_delivery` 본체와 thin shim 계약은 이미 Batch 39에서 안정화되어 있었다.
- production 앱 경로 기준 남아 있던 legacy lazy import는 `erp_measurement`, `erp_orders_structured`, `erp_shipment_settings` 3개 파일뿐이었다.
- 이번 배치는 import 경로만 바꾸고 caller source-path 테스트를 보강하는 저위험 cleanup으로 끝났다.

## 2. 사전 감리 요약
- `apps/` 기준 `services.channel_delivery` live import는 3개 lazy caller만 남아 있었다.
- 모두 `mark_order_updated_for_channel` 단일 helper를 지연 import하는 패턴이라 정리 범위가 매우 작았다.
- `business_calendar` 축과 무관하므로 별도 충돌 없이 GO 판정했다.

## 3. 실제 변경 범위
### 3.1 caller cleanup
- `apps/api/erp_measurement.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/erp_shipment_settings.py`

### 3.2 테스트 보강
- `tests/test_foms_namespace_imports.py`

## 4. 변경 상세
- 세 API 모듈의 lazy import를 `from foms.services.channel_delivery import mark_order_updated_for_channel`로 정리했다.
- `tests/test_foms_namespace_imports.py`에 ERP API caller source-path 검증을 추가했다.
- `apps/` 경로에서 `services.channel_delivery` live import가 0건임을 ripgrep로 확인했다.

## 5. 의도적으로 건드리지 않은 것
- `foms/services/channel_delivery.py` 본체 로직
- `services/channel_delivery.py` thin shim 계약
- `business_calendar`/`/calendar` 축
- `as_content_safety` 단일 caller 등 다음 배치 후보

## 6. 검증 결과
### 6.1 live import audit
- 실행: `rg "\bfrom services\.channel_delivery import|\bimport services\.channel_delivery\b" apps`
- 결과: no matches

### 6.2 caller smoke
- 실행: `python -c "... print('CHANNEL_DELIVERY_CALLERS_NS_OK')"`
- 결과: `CHANNEL_DELIVERY_CALLERS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_foms_namespace_imports.py -q`
- 결과: `130 passed`

### 6.4 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `423 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.5 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.6 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Batch 39에서 canonical source로 만든 `channel_delivery`의 app/API caller cleanup이 이번 배치로 닫혔다.
- 구조 정리 관점에서 남아 있는 `services.*` app caller는 사용자 제외 범위인 `business_calendar`와 단일 `as_content_safety` caller뿐이었다.

## 8. 다음 단계
1. 다음 자동 후보인 `services.as_content_safety` 단일 caller cleanup을 바로 수행한다.
2. `business_calendar`/`/calendar` 축은 사용자 지시대로 migration scope 밖에 유지한다.
3. active caller cleanup이 끝나면 Step 4(`app.py` slim entrypoint) 전감리로 넘어간다.
