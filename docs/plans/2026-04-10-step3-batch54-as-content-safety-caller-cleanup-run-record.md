# Step 3 Batch 54 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch53-channel-delivery-caller-cleanup-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Batch 15에서 canonical source로 고정된 `as_content_safety`의 마지막 live app caller를 canonical `foms.services.as_content_safety` 경로로 정리한다

## 1. 전체 판정
**Verdict: Step 3 Batch 54 executed, `as_content_safety` caller cleanup completed**

이유:
- production 앱 경로 기준 남아 있던 `services.as_content_safety` caller는 `apps/erp_as_page.py` 1건뿐이었다.
- helper binding만 정리하면 되는 저비용 cleanup이었고, 기존 shim 계약과 테스트가 이미 안정적이었다.
- 이번 배치 완료 후 `apps/` 기준 남은 legacy `services.*` import는 사용자 제외 범위인 `business_calendar`만 남는다.

## 2. 사전 감리 요약
- `rg` 기준 `services.as_content_safety` app caller는 단 1개였다.
- `sanitize_as_content_html`는 top-level binding 패턴이라 caller binding 테스트 추가만으로 충분했다.
- business calendar 삭제 예정 축과 직접 충돌하지 않으므로 GO 판정했다.

## 3. 실제 변경 범위
### 3.1 caller cleanup
- `apps/erp_as_page.py`

### 3.2 테스트 보강
- `tests/test_foms_namespace_imports.py`

## 4. 변경 상세
- `apps/erp_as_page.py`의 import를 `from foms.services.as_content_safety import sanitize_as_content_html`로 전환했다.
- `tests/test_foms_namespace_imports.py`에 `erp_as_page` binding 테스트를 추가했다.
- `apps/` 기준 남은 legacy `services.*` import를 재집계한 결과 사용자 제외 범위인 `business_calendar` 3건만 남음을 확인했다.

## 5. 의도적으로 건드리지 않은 것
- `foms/services/as_content_safety.py` 본체 로직
- `services/as_content_safety.py` thin shim 계약
- `services.business_calendar.py`
- `/calendar` 관련 기능 축

## 6. 검증 결과
### 6.1 live import audit
- 실행: `rg "\bfrom services\.as_content_safety import|\bimport services\.as_content_safety\b" apps`
- 결과: no matches

### 6.2 caller smoke
- 실행: `python -c "... print('AS_CONTENT_SAFETY_CALLERS_NS_OK')"`
- 결과: `AS_CONTENT_SAFETY_CALLERS_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_foms_namespace_imports.py -q`
- 결과: `131 passed`

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
- Batch 15에서 canonical source로 만든 `as_content_safety`의 마지막 production caller가 정리됐다.
- 이제 `apps/` 기준 남은 legacy `services.*` import는 사용자 제외 범위인 `business_calendar`만 남는다.
- 즉, 사용자 지시 범위를 제외한 Step 3 active app/API caller cleanup은 사실상 마감됐다.

## 8. 다음 단계
1. 다음 자동 단계는 Step 4(`app.py` slim entrypoint) 전감리다.
2. `business_calendar`/`/calendar` 축은 삭제 확정 전까지 migration scope 밖에 유지한다.
3. Step 4는 부팅/배포 계약에 닿는 고위험 범위이므로, 기존 소배치 cleanup과 분리된 대형 배치로 다룬다.
