# Drawing (canonical web slice — FR20)

## 목적

도면(Drawing) 워크벤치·관련 **페이지**의 canonical web owner를 둔다.

## 주요 모듈

본 디렉터리의 Blueprint·페이지 조립. 관련 API는 `foms/api/drawing/` (예: `erp_orders_drawing`, `erp_orders_revision`).

## 읽기 순서

1. `foms/platform/blueprints.py`
2. 본 디렉터리
3. `foms/api/drawing/`

## 금지 의존성

- quarantine/non-product 트리 import 금지.
