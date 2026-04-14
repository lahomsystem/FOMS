# Measurement (canonical web slice)

## 목적

실측(Measurement) **페이지** Blueprint의 canonical 구현을 둔다. 레거시 등록 모듈 `apps.erp_measurement_dashboard`는 `foms.web.measurement.dashboard`로 **alias shim** 연결된다 (Wave 2).

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `dashboard.py` | 실측 대시보드 페이지 Blueprint 및 템플릿 조립 |
| `__init__.py` | 패키지 초기화 |

관련 API·지도 동반 surface는 `foms/api/measurement.py`, `foms/api/measurement_map.py` 및 `foms/services/measurement_*.py`와 함께 읽는다.

## 읽기 순서

1. `foms/platform/blueprints.py`에서 `erp_measurement_dashboard_bp` 등록 확인
2. 본 디렉터리 `dashboard.py`
3. API canonical: `foms/api/measurement.py`
4. 레거시 등록 경로: `apps/erp_measurement_dashboard.py` (shim만)

## 금지 의존성 / overlay

- **금지:** quarantine/non-product 트리 import (spec §2.5).
- **overlay:** Flask route는 여전히 `apps.erp_measurement_dashboard` 경로로 등록되며, 제거 조건은 Wave 8 bridge retirement에서 다룬다 (bridge debt `BD-003`).
