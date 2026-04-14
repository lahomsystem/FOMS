# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-13 16:51:15 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-13 19:11:31 | allow | `-` | `where.exe cursor` |
| 2026-04-13 22:26:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Name | Sort-Object` |
| 2026-04-13 22:27:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-13 22:29:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (-not (Test-Path "scripts\migrations")) { New-Item -ItemType Directory -Path "scripts\migra` |
| 2026-04-13 22:30:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -c "from safe_schema_migration import SafeSche` |
| 2026-04-13 22:33:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -File | Select-Object Name | Sort-Object Name` |
| 2026-04-13 22:35:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (-not (Test-Path "scripts\ops")) { New-Item -ItemType Directory -Path "scripts\ops" -Force ` |
| 2026-04-13 22:36:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -c "import erp_automation; import erp_order_te` |
| 2026-04-13 22:37:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Path "docs\manual-artifacts" -Force | Out-Null; New-Item -ItemTy` |
| 2026-04-13 22:38:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git mv "docs/plans/2026-04-13-wave1-batch3a-migrations-run-record.md" "docs/plans/2026-04-13-w` |
| 2026-04-13 22:38:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-13 22:38:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; rg -n "Add In Program|SCheduler|backups" foms apps services templates static tests tools scrip` |
| 2026-04-13 22:39:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest -q` |
| 2026-04-13 22:40:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-13 22:57:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -c "from foms.platform.blueprints import regis` |
| 2026-04-13 22:57:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-13 22:59:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-13 23:03:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only HEAD 2>$null; if (-not $?) { git status -s --short }` |
| 2026-04-13 23:14:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-13 23:15:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-13 23:16:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_foms_namespace_imports.py::test_personal_board_uses_canonical_erp_` |
| 2026-04-13 23:17:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-13 23:22:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-13 23:24:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-14 09:04:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (Get-Content "apps\erp_production_page.py" | Measure-Object -Line).Lines; (Get-Content "apps\e` |
| 2026-04-14 09:07:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-14 09:07:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_foms_namespace_imports.py::test_erp_completion_page_shim_reexports` |
| 2026-04-14 09:08:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem templates\partials\erp_production*.html | ForEach-Object { "$($_.Name) $((Get-Co` |
| 2026-04-14 09:08:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\production\partials" | Out-Null; Copy-Ite` |
| 2026-04-14 09:11:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-14 09:11:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_foms_namespace_imports.py -q --tb=short` |
| 2026-04-14 09:11:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_menu_config.py -q --tb=line 2>$null; if (-not $?) { echo "test_men` |
| 2026-04-14 09:12:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only HEAD 2>$null; git status -s --short` |
| 2026-04-14 09:20:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-14 09:22:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from db import get_db from models import Order from sqlalchemy import func db = ge` |
| 2026-04-14 09:22:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import app as app_module from db import get_db from models import Order from sqlal` |
| 2026-04-14 09:23:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import app as app_module from db import get_db from models import Order from sqlal` |
| 2026-04-14 09:23:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import app as app_module from db import get_db from models import Order from sqlal` |
| 2026-04-14 09:23:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import app as app_module from db import get_db from models import Order from app i` |
| 2026-04-14 09:23:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-14 09:24:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- "foms/web/production/dashboard.py"; git log -1 --oneline -- "foms/web/product` |
| 2026-04-14 09:24:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -- "foms/web/production/dashboard.py"; git diff --cached -- "foms/web/production/da` |
| 2026-04-14 09:24:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/main:apps/erp_production_page.py 2>$null | Select-Object -First 120` |
| 2026-04-14 09:27:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-14 09:28:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; pytest tests/test_foms_namespace_imports.py tests/tes` |
| 2026-04-14 09:30:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-14 09:40:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "templates\wdcalculator\partials\wdcalculator_scripts.html","templates\par` |
| 2026-04-14 09:44:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "static\js\wdcalculator\*.js" | Sort-Object Name | ForEach-Object { $_.Name }` |
| 2026-04-14 09:47:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-14 09:47:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node "tests\support\wdcalculator_layout_sync_wiring_contract_node_checks.js"; node "tests\supp` |
| 2026-04-14 09:51:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "static\js\wdcalculator\early-bootstrap.js","static\js\wdcalculator\startup-init` |
| 2026-04-14 09:51:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $files = @('early-bootstrap.js','late-bootstrap.js','startup-init.js','terminal-init.js','side` |
| 2026-04-14 09:53:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $order = @( 'early-bootstrap.js','sidebar-bootstrap.js','primary-ui-bootstrap.js', 'catalog-bu` |
| 2026-04-14 09:59:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-14 09:59:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_wdcalculator_product_settings.py::test_wdcalculator_page_renders_i` |
| 2026-04-14 10:02:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_wdcalculator_early_bootstrap_contract_node.py tests/test_wdcalcula` |
| 2026-04-14 10:02:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_wdcalculator_product_settings.py -q --tb=no -q 2>&1 | Select-Objec` |
| 2026-04-14 10:04:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only HEAD 2>$null; git status -sb` |
| 2026-04-14 10:04:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (Get-Content "static\js\wdcalculator\composition.js" | Measure-Object -Line).Lines` |
| 2026-04-14 10:04:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff foms/platform/blueprints.py 2>$null | Select-Object -First 40` |
| 2026-04-14 10:08:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-14 10:08:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/ -k "bootstrap_contract_node" -q --tb=no 2>&1 | Select-Object -Last 25` |
| 2026-04-14 10:09:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short -- "foms/platform/blueprints.py" "apps/api" "foms/api" 2>$null` |
| 2026-04-14 10:09:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short -- "*.py" 2>$null | Select-String -Pattern "models|alembic|migration|schema` |
| 2026-04-14 10:10:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only foms/platform/blueprints.py 2>&1; git status -s foms/platform/blueprints.` |
| 2026-04-14 10:12:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('static/js/wdcalculator') files = [ 'notes-ui` |
| 2026-04-14 10:21:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-14 10:21:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/test_wdcalculator_product_settings.py tests/test_wdcalculator_calculate` |
| 2026-04-14 10:36:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git branch -a` |
| 2026-04-14 10:37:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -File -Name | Where-Object { $_ -match '^(erp_|foms_|init_wdcalculator|safe_sche` |
| 2026-04-14 10:37:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status --short | Measure-Object -Line` |
