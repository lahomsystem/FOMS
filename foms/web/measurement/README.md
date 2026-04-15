# Measurement (canonical web slice)

## 목적

실측(Measurement) **페이지** Blueprint의 canonical 구현을 둔다.

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `dashboard.py` | 실측 대시보드 페이지 Blueprint 및 템플릿 조립 |
| `__init__.py` | 패키지 초기화 |

관련 API·지도 동반 surface는 `foms/api/measurement/` (`routes.py`, `map.py`) 및 `foms/services/measurement_*.py`와 함께 읽는다.

## 읽기 순서

1. `foms/platform/blueprints.py`에서 `erp_measurement_dashboard_bp` 등록 확인 (canonical `foms.web.measurement.dashboard` import)
2. 본 디렉터리 `dashboard.py`
3. API canonical: `foms/api/measurement.py`

## 금지 의존성 / overlay

- **금지:** quarantine/non-product 트리 import (modular monolith spec 2.5).
