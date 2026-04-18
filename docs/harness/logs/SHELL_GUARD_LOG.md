# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-18 10:27:02 | allow | `-` | `if (Get-Command railway -ErrorAction SilentlyContinue) { railway status }` |
| 2026-04-18 10:27:26 | allow | `-` | `alembic heads` |
| 2026-04-18 10:28:05 | allow | `-` | `railway variables --help` |
| 2026-04-18 10:28:29 | allow | `-` | `railway variable list --json | python -c "import sys, json; data=json.load(sys.stdin); keys=set(); if isinstance(data, dict): items = data.items() if all(isinst` |
| 2026-04-18 10:28:45 | allow | `-` | `railway ssh --help` |
| 2026-04-18 10:28:45 | allow | `-` | `railway --help` |
| 2026-04-18 10:28:58 | allow | `-` | `railway ssh alembic current` |
| 2026-04-18 10:32:49 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-18 10:32:49 | allow | `-` | `pytest tests/contracts/runtime/foms_namespace_surface_tests.py tests/domains/test_app_init.py tests/domains/test_db_indexes.py tests/domains/test_erp_order_shar` |
| 2026-04-18 11:22:10 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-18 11:23:56 | allow | `-` | `dir static\js\runtime; echo ---; dir foms\services\common` |
| 2026-04-18 11:24:06 | allow | `-` | `if exist "docs\context\PTC_RUNTIME_COMMON_INVENTORY.md" (echo EXISTS) else (echo MISSING)` |
| 2026-04-18 11:25:37 | allow | `-` | `python -m pytest tests/contracts/ -q 2>&1 | Select-Object -Last 30` |
| 2026-04-18 11:25:50 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-18 11:40:23 | allow | `-` | `powershell -NoProfile -Command "Get-ChildItem -Path 'static/css/foundation' -Recurse -File | Select-Object -ExpandProperty FullName"` |
| 2026-04-18 11:43:25 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-18 11:43:41 | allow | `-` | `python -m pytest tests/domains/test_erp_runtime_shell_js_contract.py tests/domains/test_erp_mobile_layout_and_shipment.py -x -q 2>&1 | Select-Object -Last 40` |
| 2026-04-18 11:43:51 | allow | `-` | `python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py -x -q 2>&1 | Select-Object -Last 30` |
| 2026-04-18 11:44:01 | allow | `-` | `python -m pytest tests/domains -k "erp" -x -q 2>&1 | Select-Object -Last 30` |
| 2026-04-18 11:44:37 | allow | `-` | `python -m pytest tests/domains/test_notification_badge_dedup.py::test_erp_pages_use_single_notification_badge_fetch -x -q 2>&1 | Select-Object -Last 15` |
| 2026-04-18 11:44:53 | allow | `-` | `python -m pytest tests/domains -k "erp and not test_erp_pages_use_single_notification_badge_fetch" -q 2>&1 | Select-Object -Last 10` |
| 2026-04-18 11:45:19 | allow | `-` | `python -m pytest tests/domains -k "edit_order or erp_order_bootstrap or structured_bootstrap" -q 2>&1 | Select-Object -Last 15` |
