# W8-B1 — Bridge taxonomy + retirement queue freeze

| Field | Value |
|-------|-------|
| Batch | `W8-B1` |
| Branch | Branch A |
| Baseline | inherited-red collect-only / fresh green APP_OK+verify_result |

## §2.2 / §2.3 live mapping (authoritative)

| Family | Bridge mechanism | queue class |
|--------|-------------------|-------------|
| service-compat-notifications-files | compat shim (4 files) | mainline-pilot |
| apps-direct-files-address | direct-canonical import bridge | mainline-pilot |
| apps-direct-measurement-production-completion | direct-canonical import bridge | mainline-pilot |
| personal-board-shell | adapter shell | adapter-shell defer |
| orders-shell | adapter shell | adapter-shell defer |
| jobs-legacy-path | runtime-string bridge | runtime-string-coupled defer |
| business-calendar | explicit exception | explicit-exception |
| high-risk-cluster | mixed | high-risk cluster defer |

## Explicit exclusion set (mainline 금지)

- `apps/api/personal_board.py`
- `apps/api/orders/__init__.py`
- `services/jobs/*`
- `services/business_calendar.py`
- `apps/api/notifications.py`
- `apps/api/attachments.py`
- `apps/api/chat/*`
- `services/channel_*`

## Retirement-sentinel 규칙 (BR2)

- 삭제된 bridge 경로: `importlib.util.find_spec(...) is None` 또는 canonical-only import 동치 검증으로 대체.
- parity-from-legacy 모듈 객체 비교는 제거된 shim에 대해 중단하고 동일 batch에서 sentinel로 대체.

## W8-B2/B4 허용 file family (freeze)

- B3: `services/realtime_notifications.py`, `services/file_utils.py`, `foms/services/realtime_notifications.py`, `foms/services/file_utils.py` **삭제** + 허용 caller/test/README만.
- B5: `apps/api/files.py` 등 6 bridge **삭제** + `foms/platform/blueprints.py` import line only + locked caller list.

## Direction Lock

1. 순감: 본 batch 문서만 — count 변화 없음.

## Next legal batch

`W8-B2`

## Verification

- Doc completeness / exclusion set 전부 기재됨.
