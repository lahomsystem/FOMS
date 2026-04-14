# Orders API (canonical helper cluster)

## 목적

주문 **API 응답·상태 변경**의 canonical helper를 둔다. Flask `Blueprint`와 URL은 `apps.api.orders`에 남아 있으며, 핸들러는 `foms.api.orders`의 `*_response` helper로 위임하는 **thin adapter** 패턴이다 (Wave 2 선례, bridge debt `BD-005`).

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `calendar.py` | 캘린더/FullCalendar용 이벤트 응답 |
| `nearby.py` | 근접 일정 검색 |
| `regional.py` | 지역 상태·메모 등 |
| `field_update.py` | 필드 업데이트 |
| `mutations.py` | 기타 변이 응답 |
| `status.py` | 상태 변경 응답 |

`__init__.py`는 Flask Blueprint shell만 유지한다.

## 읽기 순서

1. `apps/api/orders/__init__.py` — 등록된 route → 어떤 helper를 부르는지
2. 본 패키지의 해당 `foms.api.orders` 모듈
3. 아직 `apps.api.erp_orders_*` 등 **legacy owner** API는 별도 모듈; 동일 도메인이라도 선례(`BD-005`)와 동일하지 않음 (Wave 2).

## 금지 의존성 / overlay

- **금지:** ORM/SQL을 이 패키지에 새로 누적해 “서비스 우회”하는 패턴 (정책은 `foms/services` 쪽).
- **overlay:** 페이지·다른 ERP stage API(`apps.api.erp_orders_*`)는 아직 `apps` live owner — split-brain 주의 (bridge debt `BD-006`, `BD-019`).
