# Notifications (API-first context — FR20)

## 목적

알림·실시간 알림 **API**의 canonical owner를 둔다.

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `__init__.py` | Blueprint |
| `realtime_notifications.py` | ERP 알림 emit 등 public helper |

## 읽기 순서

1. `foms/platform/blueprints.py`
2. `realtime_notifications.py` — public API
3. 구독·배달 서비스는 `foms/services/notifications/`, `foms/services/channel_*`

## 금지 의존성

- quarantine/non-product 트리 import 금지.
