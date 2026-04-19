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
| 2026-04-18 12:21:37 | allow | `-` | `Get-ChildItem -Path . -Filter "railway*" -File -Force -ErrorAction SilentlyContinue; Get-ChildItem -Path . -Filter "*.toml" -File -Force -ErrorAction SilentlyCo` |
| 2026-04-18 12:23:38 | allow | `-` | `railway status 2>&1 | Select-Object -First 30` |
| 2026-04-18 12:23:44 | allow | `-` | `railway deployment list --json 2>&1 | Select-Object -First 200` |
| 2026-04-18 12:41:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-18 12:44:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-18 12:45:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_sqlite_startup_compat.py tests/domains/test_app_init.py tests/domain` |
| 2026-04-18 12:50:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; pytest tests/domains/test_erp_order_shared_form_scrip` |
| 2026-04-18 12:50:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json` |
| 2026-04-18 12:52:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway --version 2>&1; railway status 2>&1` |
| 2026-04-18 12:52:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables --json 2>&1 | Select-Object -First 5` |
| 2026-04-18 12:52:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables --json 2>&1 | python -c "import sys,json,re; d=json.load(sys.stdin); out={};` |
| 2026-04-18 12:52:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.stdin); keys=sorte` |
| 2026-04-18 12:52:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run -- python -c "import os; print('DATABASE_URL_set', bool(os.environ.get('DATABASE_U` |
| 2026-04-18 12:53:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path .\.venv\Scripts\python.exe) { .\.venv\Scripts\python.exe -c "import sqlalchemy; ` |
| 2026-04-18 12:53:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run -- .\.venv\Scripts\python.exe -c " import os, json from sqlalchemy import create_e` |
| 2026-04-18 12:53:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run -- "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\.venv\Scripts\pyth` |
| 2026-04-18 12:53:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run .\.venv\Scripts\python.exe tools\harness\_tmp_railway_db_gate_snapshot.py` |
| 2026-04-18 12:53:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Test-Path .\.venv\Scripts\python.exe; Get-Command python | Select-Object -ExpandProperty Sourc` |
| 2026-04-18 12:53:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python tools\harness\_tmp_railway_db_gate_snapshot.py` |
| 2026-04-18 12:53:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python -c "import os; k=[x for x in os.environ if 'DATABASE' in x or x.startswith(` |
| 2026-04-18 12:53:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh --help 2>&1 | Select-Object -First 40` |
| 2026-04-18 12:53:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh python -c "import os; print('has_db', 'DATABASE_URL' in os.environ)"` |
| 2026-04-18 12:54:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- python -c "import os; print('DATABASE_URL' in os.environ)"` |
| 2026-04-18 12:54:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc "pwd; ls -la /app 2>/dev/null | head -5"` |
| 2026-04-18 12:54:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc "cd /app && python tools/harness/_tmp_railway_db_gate_snapshot.py"` |
| 2026-04-18 12:54:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc "cd /app && python -c \"import os,json; from sqlalchemy import create_` |
| 2026-04-18 12:54:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway --help 2>&1 | Select-String -Pattern "database|connect|shell"` |
| 2026-04-18 12:54:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway connect --help` |
| 2026-04-18 12:54:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway service list 2>&1; railway status -v 2>&1` |
| 2026-04-18 12:54:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway service --help 2>&1` |
| 2026-04-18 12:54:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway connect 2>&1` |
| 2026-04-18 12:55:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; foreach ($n in @('Postgres','postgres','PostgreSQL','FOMS-Postgres','Database')) { Write-Host ` |
| 2026-04-18 12:55:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway connect Postgres -- -c "SELECT column_name FROM information_schema.columns WHERE table` |
| 2026-04-18 12:55:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @' cd /app && ls tools/harness/railway_db_gate_snapshot.py 2>&1 '@ | railway ssh bash -s` |
| 2026-04-18 12:56:01 | allow | `-` | `Stop-Process -Id 27768 -Force -ErrorAction SilentlyContinue` |
| 2026-04-18 12:56:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables --json 2>&1 | python tools\harness\railway_db_gate_snapshot.py --from-stdin` |
| 2026-04-18 12:56:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc "which psql; which python3; python3 --version"` |
| 2026-04-18 12:56:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc 'if test -n "$DATABASE_URL"; then echo db_env_set; else echo db_env_un` |
| 2026-04-18 12:56:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc '[ -n "$DATABASE_URL" ] && echo db_set || echo db_unset'` |
| 2026-04-18 12:57:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-Content tools\harness\_ssh_env_check.py -Raw | railway ssh -- python3` |
| 2026-04-18 12:57:41 | allow | `-` | `Stop-Process -Id 35632 -Force -ErrorAction SilentlyContinue` |
| 2026-04-18 12:57:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc "env | cut -d= -f1 | sort | grep -E '^DATABASE'"` |
| 2026-04-18 12:57:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import base64, pathlib; p=pathlib.Path('tools/harness/railway_db_gate_snapshot.py')` |
| 2026-04-18 12:58:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (Get-Item tools\harness\_gate_b64.txt).Length` |
| 2026-04-18 12:58:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-Content tools\harness\_gate_b64.txt -Raw | railway ssh -- bash -lc "base64 -d | python3"` |
| 2026-04-18 12:59:49 | allow | `-` | `Stop-Process -Id 44512 -Force -ErrorAction SilentlyContinue` |
| 2026-04-18 13:00:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables --json 2>&1 | python tools\harness\railway_db_gate_snapshot.py --from-stdin` |
| 2026-04-18 13:00:16 | allow | `-` | `wsl --status 2>&1` |
| 2026-04-18 13:00:21 | ask | `pip\s+install\s+(?!-r)` | `python -m pip install "psycopg[binary]" -q; python -c "import psycopg; print('psycopg', psycopg.__version__)"` |
| 2026-04-18 13:00:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables --json 2>&1 | python -c "import json,sys; d=json.load(sys.stdin); import psy` |
| 2026-04-18 13:00:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- python3 -c 'import os, psycopg2; c=psycopg2.connect(os.environ["DATABASE_URL"])` |
| 2026-04-18 13:00:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc 'python3 -c "import os, psycopg2; c=psycopg2.connect(os.environ[\"DATA` |
| 2026-04-18 13:01:31 | allow | `-` | `Stop-Process -Id 1480 -Force -ErrorAction SilentlyContinue` |
| 2026-04-18 13:01:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-Content tools\harness\railway_db_gate_snapshot_ssh.py -Raw -Encoding utf8 | railway ssh --` |
| 2026-04-18 13:03:27 | allow | `-` | `Stop-Process -Id 38120 -Force -ErrorAction SilentlyContinue` |
| 2026-04-18 13:03:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway ssh -- bash -lc "python3 -c \"import os,base64,psycopg2;k=base64.b64decode('REFUQUJBU0` |
| 2026-04-18 13:03:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; cmd /c tools\harness\_run_remote_db_smoke.cmd` |
| 2026-04-18 13:04:18 | allow | `-` | `Stop-Process -Id 43356 -Force -ErrorAction SilentlyContinue` |
| 2026-04-18 13:04:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway logs --help 2>&1 | Select-Object -First 35` |
| 2026-04-18 13:04:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway logs -n 3000 --filter "erp-beta" 2>&1 | Select-Object -First 50` |
| 2026-04-18 13:04:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway logs -n 500 2>&1 | Select-Object -First 15` |
| 2026-04-18 13:04:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway service status 2>&1` |
| 2026-04-18 13:04:59 | allow | `-` | `python -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))"` |
| 2026-04-18 13:06:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables --json 2>&1 | python tools\harness\railway_db_gate_snapshot.py --from-stdin ` |
| 2026-04-18 13:06:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; pytest tests/domains/test_erp_order_shared_form_scrip` |
| 2026-04-18 13:08:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-04-18 13:08:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -u; git add docs\harness\evidence\2026-04-18-erp-beta-retirement-gate-evidence.json do` |
| 2026-04-19 12:56:31 | ask | `git\s+push\s+--force` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push --force-with-lease origin feature/modular-monolith-wip` |
| 2026-04-19 13:02:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD; git branch --show-current; git status -sb` |
| 2026-04-19 13:02:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git rev-parse origin/feature/modular-monolith-wip` |
| 2026-04-19 13:02:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-19 13:03:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git status -sb; git push origin HEAD` |
| 2026-04-19 13:03:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" --allow-empty -F ".git_commit_msg_railway_utf8.txt"; ` |
| 2026-04-19 13:33:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_estimate_service.` |
| 2026-04-19 13:35:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_estimate_service.` |
| 2026-04-19 13:39:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_estimate_service.` |
| 2026-04-19 13:41:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-04-19 13:41:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-04-19 13:41:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/AI_STATUS.md docs/evolution/EVOLUTION_DECISIONS.md docs/harn` |
