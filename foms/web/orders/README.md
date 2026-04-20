# Orders (bounded context — FR20 page-first)

## 목적

주문 도메인의 **페이지·화면**과 연결된 canonical web surface와, 동일 bounded context 안의 **API·상태 변경** 진입점을 한 README에서 안내한다. API Blueprint의 상세는 `foms/api/orders/` 코드를 따른다.

## 주요 모듈

| 영역 | 위치 | 역할 |
|------|------|------|
| Web / pages | `foms/web/orders/` | 주문 관련 HTML 페이지 Blueprint (해당 시) |
| API | `foms/api/orders/` | 주문 API 응답·상태 변경 canonical owner (`calendar`, `nearby`, `regional`, `field_update`, `mutations`, `status` 등) |
| Services | `foms/services/orders/` | 도메인 정책·오케스트레이션 |

`apps.api.orders`는 re-export-only compatibility wrapper다. legacy `apps.api.erp_orders_*`는 별도 bridge debt로 취급한다.

## 읽기 순서

1. `foms/platform/blueprints.py` — 주문 관련 blueprint 등록
2. `foms/web/orders/` — 페이지 owner
3. `foms/api/orders/__init__.py` — canonical API shell
4. `foms/services/orders/` — 정책·서비스 레이어

## 금지 의존성

- quarantine/non-product 트리로의 runtime import 금지 (`2026-04-13` §2.5).
- API 패키지에 ORM/SQL만 누적해 서비스 우회 금지.
