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
