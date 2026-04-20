# Shipment (canonical web slice — FR20)

## 목적

출고(Shipment) **페이지** Blueprint의 canonical 구현을 둔다.

## 주요 모듈

본 디렉터리의 페이지 라우트. 관련 API·설정은 `foms/api/shipment/`, `foms/services/erp_shipment_settings` 등과 함께 읽는다.

## 읽기 순서

1. `foms/platform/blueprints.py`
2. 본 디렉터리
3. `foms/api/shipment/`

## 금지 의존성

- quarantine/non-product 트리 import 금지.
