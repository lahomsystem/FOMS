# W8-B2 — Service compat bridge freeze

| Field | Value |
|-------|-------|
| Batch | `W8-B2` |
| Branch | Branch A |

## Exact shim paths (lock)

1. `services/realtime_notifications.py`
2. `services/file_utils.py`
3. `foms/services/realtime_notifications.py`
4. `foms/services/file_utils.py`

## Canonical targets (lock)

- `foms.services.notifications.realtime_notifications.emit_erp_notification_to_users`
- `foms.services.files.file_utils` (`allowed_file`, `allowed_erp_media_file`)

## Caller / test surface (B3 허용)

- Runtime contract: `tests/contracts/runtime/foms_namespace_surface_tests.py`
- Thin aggregator: `tests/test_foms_namespace_imports.py`
- `tests/test_realtime_notifications.py`
- Product: (rg 기준) `apps/`에 `services.realtime_notifications` / `services.file_utils` 직접 import **없음**; notifications API는 이미 `foms.services.notifications.realtime_notifications`.

## Zero-import rule (post-B3)

Product code + non-deferred tests에서 retired dotted path import **0**.

## Retirement sentinel map

- `find_spec("services.realtime_notifications") is None`
- `find_spec("foms.services.realtime_notifications") is None`
- `find_spec("services.file_utils") is None`
- `find_spec("foms.services.file_utils") is None`
- Canonical package import smoke 유지.

## Direction Lock

1. 순감: B3에서 4 bridge 파일 삭제 예정.
6. `blueprints.py`: 본 batch 미변경.

## Verification (executed)

- `APP_OK`, `verify_result --json` — B0와 동일 baseline 전제.

## Next legal batch

`W8-B3`
