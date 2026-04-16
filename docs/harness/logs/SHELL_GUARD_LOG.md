# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-15 16:32:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $plain = Get-ChildItem -Path "templates" -File -Filter "*.html" -Name | Sort-Object; $plain.Co` |
| 2026-04-15 16:32:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $nodes = @( "foms\api\files","foms\api\measurement","templates\auth", "static\js\drawing","sta` |
| 2026-04-15 16:33:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $allow = @('.agents','.claude','.cursor','.github','.vscode','.dockerignore','.gcloudignore','` |
| 2026-04-15 16:33:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $allow = @('.agents','.claude','.cursor','.github','.vscode','.dockerignore','.gcloudignore','` |
| 2026-04-15 16:33:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (rg -c "from constants import" foms --glob "*.py" 2>$null | ForEach-Object { ($_ -split ':')[1` |
| 2026-04-15 16:34:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 16:35:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 16:37:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 16:38:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=short -x 2>&1` |
| 2026-04-15 16:38:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line 2>&1 | Select-Object -Last 15` |
| 2026-04-15 16:41:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 16:43:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Force "scripts\ops\foms_address_converter.py" "foms\services\common\address_convert` |
| 2026-04-15 16:44:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 16:44:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line 2>&1 | Select-Object -Last 12` |
| 2026-04-15 16:48:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 16:48:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_orders_structured_put.py tests/contracts/runtime/foms_` |
| 2026-04-15 16:48:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line` |
| 2026-04-15 16:53:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 16:55:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "templates" -File -Filter "*.html" | Sort-Object Name | ForEach-Object { $` |
| 2026-04-15 16:57:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 16:58:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\auth","templates\shared","templates\error` |
| 2026-04-15 16:59:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git mv "templates/regional_dashboard.html" "templates/measurement/regional_dashboard.html"; gi` |
| 2026-04-15 16:59:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git mv "templates/admin.html" "templates/admin/admin.html"; git mv "templates/change_logs.html` |
| 2026-04-15 16:59:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git mv "templates/login.html" "templates/auth/login.html"; git mv "templates/register.html" "t` |
| 2026-04-15 16:59:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git mv "templates/chat.html" "templates/channel/chat.html"; git mv "templates/wdplanner.html" ` |
| 2026-04-15 16:59:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "templates" -File -Filter "*.html" | Measure-Object | Select-Object -Expan` |
| 2026-04-15 16:59:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('templates') for p in root.rglob('*.html'): t` |
| 2026-04-15 16:59:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/_b7_extends_replace.py` |
| 2026-04-15 17:03:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 17:03:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json` |
| 2026-04-15 17:03:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_map_view_manager_contract.py tests/domains/test_foms_names` |
| 2026-04-15 17:04:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line` |
| 2026-04-15 17:06:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path static\js -Directory | ForEach-Object { $_.Name }; Write-Host "---"; Get-C` |
| 2026-04-15 17:07:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json | Select` |
| 2026-04-15 17:12:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Path "foms\api\measurement.py" -Destination "foms\api\measurement\routes.py" -Force` |
| 2026-04-15 17:12:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 17:13:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json; python -m pytest tests -q --tb=short` |
| 2026-04-15 17:15:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_channel_push_mess` |
| 2026-04-15 17:16:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests -q --tb=line` |
| 2026-04-15 17:18:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -File | Select-Object Name | Sort-Object Name` |
| 2026-04-15 17:20:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (-not (Test-Path "data\dumps")) { New-Item -ItemType Directory -Path "data\dumps" -Force | ` |
| 2026-04-15 17:20:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git mv build_wdplanner.bat scripts/maintenance/build_wdplanner.bat; git mv start_foms_utf8.bat` |
| 2026-04-15 17:23:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 17:23:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_strict_canonica` |
| 2026-04-15 17:23:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "foms.dump") { Move-Item -Path "foms.dump" -Destination "data\dumps\foms.dump" -` |
| 2026-04-15 17:27:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_strict_canonica` |
| 2026-04-15 17:27:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "furniture_orders.db") { Move-Item -Path "furniture_orders.db" -Destination "dat` |
| 2026-04-15 17:29:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_strict_canonica` |
| 2026-04-15 17:29:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; foreach ($f in @("migration_ready.db","ops_browser_qa.db")) { if (Test-Path $f) { Move-Item -P` |
| 2026-04-15 17:29:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_strict_canonica` |
| 2026-04-15 17:29:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line 2>&1 | Select-Object -Last 15` |
| 2026-04-15 17:37:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 17:42:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/contracts/runtime/foms_namespa` |
| 2026-04-15 17:42:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "config") { Remove-Item -Recurse -Force "config" }` |
| 2026-04-15 17:42:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_strict_canonica` |
| 2026-04-15 17:45:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem apps -Recurse -File | Where-Object { $_.Extension -eq '.py' -and $_.FullName -no` |
| 2026-04-15 17:46:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem apps -Recurse -File | Where-Object { $_.Extension -eq '.py' -and $_.FullName -no` |
| 2026-04-15 17:49:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-15 17:50:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_foms_namespace_imports.py::test_erp_pages_use_canonical_erp_display_` |
| 2026-04-15 17:51:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests -q --tb=line` |
| 2026-04-15 17:55:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('.').resolve() skip = {'foms/web/auth/__init_` |
| 2026-04-15 17:56:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; pytest tests -q --tb=short` |
| 2026-04-15 17:57:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json` |
| 2026-04-15 18:00:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json | Select` |
| 2026-04-15 18:04:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 18:12:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 18:12:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=short` |
| 2026-04-15 18:22:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 19:00:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 19:04:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 19:07:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 19:08:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=short` |
| 2026-04-15 19:11:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-15 19:14:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-15 19:17:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('.').resolve() apps = root / 'apps' live = fr` |
| 2026-04-15 19:17:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/compare_apps_inventory.py 2>$null; if (-not $?) { python -c "from pathlib` |
| 2026-04-15 19:18:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-15 19:21:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-15 19:24:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_wr_h1_high_risk_cluster_s` |
| 2026-04-15 19:27:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_wr_h1_aux_api_shim_shells` |
| 2026-04-15 19:29:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 19:32:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_wr_h1_erp_order` |
| 2026-04-15 19:32:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 19:35:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_wr_h1_erp_map_a` |
| 2026-04-15 19:38:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_wr_h1_attachmen` |
| 2026-04-15 19:39:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json | python` |
| 2026-04-15 19:41:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools\harness\verify_result.py --json; python ` |
| 2026-04-15 19:42:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q` |
| 2026-04-15 19:46:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools\harness\verify_result.py --json; python ` |
| 2026-04-15 19:49:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests -q --tb=no -q 2>&1 | Select-Ob` |
| 2026-04-15 19:50:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no 2>&1 | Select-String -Pattern "passed|failed|error"` |
| 2026-04-15 19:55:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 19:55:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no 2>&1 | Select-String -Pattern "passed|failed"` |
| 2026-04-15 19:58:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Path "apps\auth.py" -Destination "foms\web\auth\routes.py" -Force` |
| 2026-04-15 19:59:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 19:59:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json; pytest tests -q --tb=no -x 2>&1 | Select-Object ` |
| 2026-04-15 20:01:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Path "apps\dashboards.py" -Destination "foms\web\dashboards\routes.py" -Force` |
| 2026-04-15 20:01:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 20:04:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Path "apps\user_pages.py" -Destination "foms\web\user_pages\routes.py" -Force` |
| 2026-04-15 20:05:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; pytest tests -q --tb=line 2>&1 | Select-Object -Last ` |
| 2026-04-15 20:06:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1 | Select-Object -First 8` |
| 2026-04-15 20:07:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Path "apps\storage_dashboard.py" -Destination "foms\web\storage_dashboard\routes.py` |
| 2026-04-15 20:07:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-15 20:10:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Path "apps\excel_import.py" -Destination "foms\web\excel_import\routes.py" -Force` |
| 2026-04-15 20:10:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-15 20:13:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item "apps\erp_dashboard.py" "foms\web\erp_dashboard\routes.py" -Force; Copy-Item "apps\e` |
| 2026-04-15 20:15:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 20:15:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json; pytest tests -q` |
| 2026-04-15 20:17:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_foms_namespace_imports.py::test_erp_pages_use_canonical_erp_permissi` |
| 2026-04-15 20:23:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "apps\api") { Remove-Item -Recurse -Force "apps\api" }; Get-ChildItem -Path apps` |
| 2026-04-15 20:28:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 20:31:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py tests/domains/test_fo` |
| 2026-04-15 20:32:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line` |
| 2026-04-15 20:35:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_sfc_product_tre` |
| 2026-04-15 20:37:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path apps -Force | Format-Table Name, Mode` |
| 2026-04-15 20:38:23 | ask | `remove-item\s+.+-recurse.+-force` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item -Path "apps" -Recurse -Force -ErrorAction Stop; Test-Path "apps"` |
| 2026-04-15 20:38:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests -q --tb=short` |
| 2026-04-15 20:40:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line; python tools/harness/verify_result.py --json` |
| 2026-04-15 20:43:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path path = Path('tests/contracts/runtime/foms_namespace_surfa` |
| 2026-04-15 20:43:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path path = Path('tests/contracts/runtime/foms_namespace_surfa` |
| 2026-04-15 20:43:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path import re path = Path('tests/contracts/runtime/foms_names` |
| 2026-04-15 20:44:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path import re path = Path('tests/contracts/runtime/foms_names` |
| 2026-04-15 20:44:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path import re path = Path('tests/contracts/runtime/foms_names` |
| 2026-04-15 20:45:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/_tmp_clean_foms_tests.py` |
| 2026-04-15 20:45:33 | ask | `git\s+checkout\s+--` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout -- tests/contracts/runtime/foms_namespace_surface_tests.py` |
| 2026-04-15 20:45:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status tests/contracts/runtime/foms_namespace_surface_tests.py 2>&1; git checkout HEAD -- ` |
| 2026-04-15 20:46:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path lines = Path('tests/contracts/runtime/foms_namespace_surf` |
| 2026-04-15 20:47:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/_tmp_repair_foms_tests.py` |
| 2026-04-15 20:47:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m py_compile tests/contracts/runtime/foms_namespace_surface_tests.py 2>&1` |
| 2026-04-15 20:49:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "services") { Remove-Item -Recurse -Force "services" }; if (Test-Path "services"` |
| 2026-04-15 20:49:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 20:49:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no -q 2>&1` |
| 2026-04-15 20:50:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_wr_b1_business_calendar_ca` |
| 2026-04-15 20:51:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_namespaced_map_snapshot_sh` |
| 2026-04-15 20:51:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_wave8_retired_file_utils_c` |
| 2026-04-15 20:51:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_namespaced_app_init_shim_p` |
| 2026-04-15 20:51:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_namespaced_measurement_man` |
| 2026-04-15 20:53:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 20:55:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Name -Directory | Sort-Object` |
| 2026-04-15 20:56:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git mv src "Add In Program\WDPlanner\legacy-mobile-prototype"` |
| 2026-04-15 20:56:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-15 20:59:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Force -Name | Where-Object { $_ -ne '.git' } | Sort-Object` |
| 2026-04-15 21:00:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-tree --name-only HEAD | Sort-Object` |
| 2026-04-15 21:00:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git diff --stat HEAD | Select-Object -First 30` |
| 2026-04-15 21:00:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @('apps','services','src') | ForEach-Object { "$_`: $(Test-Path $_)" }` |
| 2026-04-15 21:00:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $actualRoot = Get-ChildItem -Force -Name | Where-Object { $_ -ne '.git' -and $_ -ne '__pycache` |
| 2026-04-15 21:01:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Force -Name | Where-Object { $_ -ne '.git' -and $_ -ne '__pycache__' -and $_ -n` |
| 2026-04-15 21:02:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 21:02:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no 2>&1 | Select-Object -Last 25` |
| 2026-04-15 21:03:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $actualRoot = Get-ChildItem -Force -Name | Where-Object { $_ -ne '.git' -and $_ -ne '__pycache` |
| 2026-04-15 21:04:05 | allow | `-` | `Test-Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\apps"` |
| 2026-04-15 21:06:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git diff --stat HEAD 2>&1 | Select-Object -First 15` |
| 2026-04-15 21:06:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/contracts/runtime/foms_namespa` |
| 2026-04-15 21:07:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no 2>&1 | Select-Object -Last 5` |
| 2026-04-15 21:08:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git rev-parse --short HEAD 2>&1` |
| 2026-04-15 21:08:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $actualRoot = Get-ChildItem -Force -Name | Where-Object { $_ -notin '.git','__pycache__','.pyt` |
| 2026-04-15 21:11:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "tools\harness\strict_canonical_b12_clean_room.ps1" -Ref HEAD` |
| 2026-04-15 21:12:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "tools\harness\strict_canonical_b12_clean_room.ps1" -Ref HEAD` |
| 2026-04-15 21:13:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "tools\harness\strict_canonical_b12_clean_room.ps1" -Ref HEAD 2>&1` |
| 2026-04-15 21:13:43 | allow | `-` | `if (Test-Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\.tmp_strict_tree_verify") { "exists" } else { "absent" }` |
| 2026-04-15 21:14:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git rev-parse --short HEAD` |
| 2026-04-15 21:14:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $allowedRoot = @('.agents', '.claude', '.cursor', '.github', '.vscode', '.dockerignore', '.gcl` |
| 2026-04-15 21:15:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $allowedRoot = @('.agents', '.claude', '.cursor', '.github', '.vscode', '.dockerignore', '.gcl` |
| 2026-04-15 21:15:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-15 21:16:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 21:16:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git rev-parse --short HEAD` |
| 2026-04-15 21:16:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no` |
| 2026-04-15 21:17:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status -sb` |
| 2026-04-15 22:51:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 22:52:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "templates" -Directory | ForEach-Object { $_.Name } | Sort-Object` |
| 2026-04-15 22:52:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "foms\web" -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.` |
| 2026-04-15 22:52:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "foms\api" -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.` |
| 2026-04-15 22:52:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "foms\services" -Directory -ErrorAction SilentlyContinue | ForEach-Object ` |
| 2026-04-15 22:57:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "slg_literal_gap" ` |
| 2026-04-15 22:59:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "p=open('templates/shared/layout.html',encoding='utf-8').read().splitlines(); print(` |
| 2026-04-15 22:59:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('templates/shared/layout.html') lines = root.` |
| 2026-04-15 22:59:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path SHELL = '''<!DOCTYPE html> <html lang=\"ko\"> <head> {% i` |
| 2026-04-15 22:59:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/ops/_slg_b2_layout_migrate_once.py` |
| 2026-04-15 23:00:27 | ask | `remove-item\s+.+-recurse.+-force` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "templates\shared") { Remove-Item "templates\shared" -Force -Recurse }; if (Test` |
| 2026-04-15 23:00:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k slg_literal_gap -v` |
| 2026-04-15 23:00:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 23:01:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Path "foms\web\order_pages\routes.py" -Destination "foms\web\orders\listing.py" -Fo` |
| 2026-04-15 23:04:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; foreach ($d in @("foms\web\dashboards","foms\web\order_pages","foms\web\order_edit","foms\web\` |
| 2026-04-15 23:04:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 23:04:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "order_pages_uses_` |
| 2026-04-15 23:04:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "slg_literal_gap" ` |
| 2026-04-15 23:04:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1` |
| 2026-04-15 23:06:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (Get-Content "foms\web\erp_as_page\routes.py").Count; (Get-Content "foms\web\erp_drawing_workb` |
| 2026-04-15 23:06:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item "foms\web\erp_as_page\routes.py" "foms\web\cs\as_dashboard.py" -Force; Copy-Item "fo` |
| 2026-04-15 23:10:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item -Recurse -Force "foms\web\erp","foms\web\erp_as_page","foms\web\erp_drawing_workbe` |
| 2026-04-15 23:10:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 23:10:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "erp_pages_use_can` |
| 2026-04-15 23:10:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k slg_literal_gap -q` |
| 2026-04-15 23:10:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k slg_literal_gap -q` |
| 2026-04-15 23:10:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json` |
| 2026-04-15 23:10:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=line -x` |
| 2026-04-15 23:11:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=line` |
| 2026-04-15 23:11:31 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tools" -Name` |
| 2026-04-15 23:11:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=line` |
| 2026-04-15 23:14:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api"; Copy-Item "attachments_internal\blueprint.py" "files\blueprint.py" -Force; Copy-Item ` |
| 2026-04-15 23:15:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api"; Copy-Item "chat\blueprint.py" "channel\chat_blueprint.py" -Force; Copy-Item "chat\rou` |
| 2026-04-15 23:15:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api\channel"; Move-Item -Force "chat_blueprint.py" "blueprint.py"; Move-Item -Force "chat_f` |
| 2026-04-15 23:17:51 | ask | `remove-item\s+.+-recurse.+-force` | `Remove-Item -Recurse -Force "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api\chat"; Remove-Item -Recurse -Force "c:\Users\USER\OneDrive\Des` |
| 2026-04-15 23:18:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 23:18:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no 2>&1 | Sel` |
| 2026-04-15 23:18:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1 | Select-Object -Last 15` |
| 2026-04-15 23:19:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services"; Copy-Item "erp_policy_internal\constants.py" "orders\erp_policy_constants.py" -F` |
| 2026-04-15 23:20:04 | allow | `-` | `Remove-Item -Recurse -Force "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services\erp_policy_internal"` |
| 2026-04-15 23:20:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no 2>&1 | Sel` |
| 2026-04-15 23:20:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "foms\api" -Directory | ForEach-Object { $_.Name } | Sort-Object` |
| 2026-04-15 23:20:32 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\web" -Directory | ForEach-Object { $_.Name } | Sort-Object` |
| 2026-04-15 23:20:33 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services" -Directory | ForEach-Object { $_.Name } | Sort-Object` |
| 2026-04-15 23:20:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-15 23:22:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-15 23:22:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 23:22:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no 2>&1` |
| 2026-04-15 23:22:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" feat(strict): SLG-B1~B7 literal-gap 트랜치 마감 - templates/shared·errors 제거, partials/shared 레이` |
| 2026-04-15 23:23:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-files _commit_msg_slg.txt; git show HEAD:_commit_msg_slg.txt 2>&1 | Select-Object -Firs` |
| 2026-04-15 23:23:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rm -f _commit_msg_slg.txt; git commit --trailer "Made-with: Cursor" --amend --no-edit` |
| 2026-04-15 23:23:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:23:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" chore: 커밋 메시지 임시 파일 패턴 _commit_msg*.txt gitignore 추가 SLG UTF-8 -F 커밋 시 실수로 스테이징되는 것 방지 "@ |` |
| 2026-04-15 23:24:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:24:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" docs: SLG-B7 run record·AI_STATUS에 CLEAN_ROOM_OK·커밋 SHA 반영 HEAD f4d7410a 기준 clean-room 재증명 ` |
| 2026-04-15 23:24:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:25:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-slgb7-run-record.md docs` |
| 2026-04-15 23:25:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --format=%B` |
| 2026-04-15 23:25:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:26:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" docs: SLG-B7·AI_STATUS 최종 tip SHA 90cf2667로 정합 "@ | Set-Content -Path ".git_commit_msg_tip.` |
| 2026-04-15 23:27:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-slgb7-run-record.md docs` |
| 2026-04-15 23:27:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" docs: SLG-B7·AI_STATUS CLEAN_ROOM 증거 문구 정합 (고정 앵커 92bbb5af) 자기 참조 tip SHA 제거 "@ | Set-Conte` |
| 2026-04-15 23:27:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git push origin feature/modular-monolith-wip` |
| 2026-04-16 09:34:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\orders\partials","templates\construction\` |
| 2026-04-16 09:34:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\shared"; Remove-Item -Force erp_production_*.html,erp_measurement_mobile_*.ht` |
| 2026-04-16 09:35:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 09:36:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "templates\partials\http_errors") { Remove-Item -Recurse -Force "templates\parti` |
| 2026-04-16 09:36:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=line 2>&1 | S` |
| 2026-04-16 09:36:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line 2>&1 | Select-Object -Last 30` |
| 2026-04-16 09:37:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "tools\harness\strict_canonical_b12_clean_room.ps1" -Ref HEAD -Run` |
| 2026-04-16 09:37:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git log -1 --oneline` |
| 2026-04-16 09:38:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-16 09:39:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/platform/http.py templates/ tests/contracts/runtime/foms_namespace_surface_tests.` |
| 2026-04-16 09:39:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F ".git\COMMIT_EDITMSG_PAC.txt"` |
| 2026-04-16 09:39:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 09:40:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "tools\harness\strict_canonical_b12_clean_room.ps1" -Ref HEAD -Run` |
| 2026-04-16 09:42:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "docs/plans/2026-04-16-pac-b2-through-b5-closeout-run-record.md" docs/AI_STATUS.md; $u` |
| 2026-04-16 09:42:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 10:33:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 10:35:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-tree --name-only HEAD | Sort-Object` |
| 2026-04-16 10:36:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ptc_physical_exactness_tests.py -q` |
| 2026-04-16 10:37:47 | ask | `remove-item\s+.+-recurse.+-force` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rm -f "data/dumps/.gitkeep" "data/localdb/.gitkeep" 2>$null; if (Test-Path "data\dumps") {` |
| 2026-04-16 10:37:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ptc_physical_exactness_tests.py -q` |
| 2026-04-16 10:38:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ -q --tb=no -q 2>&1 | Select-Object -Last 25` |
| 2026-04-16 10:38:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ -q` |
| 2026-04-16 10:38:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ptc_physical_exactness_tests.py --collect-only -q` |
| 2026-04-16 10:39:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest "tests/contracts/runtime/" --collect-only 2>&1 | Select-Object -Last 15` |
| 2026-04-16 10:39:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py --collect-only -q 2>&` |
| 2026-04-16 10:39:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts --collect-only -q 2>&1 | Select-Object -Last 5` |
| 2026-04-16 10:39:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime --collect-only` |
| 2026-04-16 10:40:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests --collect-only -q 2>&1 | Select-Object -Last 3` |
| 2026-04-16 10:41:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q; python -m pytest t` |
| 2026-04-16 10:41:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no` |
| 2026-04-16 10:43:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no` |
| 2026-04-16 10:44:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no` |
| 2026-04-16 10:44:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_hygiene_probe.ps1; echo "exit=$LASTEXI` |
| 2026-04-16 10:50:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 10:51:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q; powershell -NoPro` |
| 2026-04-16 10:52:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_hygiene_probe.ps1 -RecursePyCache` |
| 2026-04-16 10:52:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 10:52:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 10:54:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log -1 --oneline` |
| 2026-04-16 10:59:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 10:59:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat tools/harness/run_codex.ps1 tests/harness/test_run_codex_levels.py docs/AI_CHA` |
| 2026-04-16 10:59:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff tools/harness/run_codex.ps1 tests/harness/test_run_codex_levels.py` |
| 2026-04-16 11:00:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -u data/; git add docs/ARCHIVE_INDEX.md docs/guides/MIGRATION_GUIDE_RAILWAY.md docs/gu` |
| 2026-04-16 11:00:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p = "commit_msg_ptc.txt"; $utf8 = New-Object System.Text.UTF8Encoding $false; $t = @" feat: P` |
| 2026-04-16 11:00:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:02:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:02:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 11:09:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git status -u` |
| 2026-04-16 11:10:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff tools/harness/run_codex.ps1 | Select-Object -First 80` |
| 2026-04-16 11:10:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff tests/harness/test_run_codex_levels.py` |
| 2026-04-16 11:10:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/COMPACT` |
| 2026-04-16 11:10:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p = "commit_msg_ptc2.txt"; $utf8 = New-Object System.Text.UTF8Encoding $false; $t = @" chore:` |
| 2026-04-16 11:10:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 ` |
| 2026-04-16 11:12:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md | Select-Object -First 40` |
| 2026-04-16 11:12:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg.txt"; $utf8 = New-Object Sys` |
| 2026-04-16 11:12:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:14:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:14:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat docs/harness/logs/SHELL_GUARD_LOG.md; git add docs/harness/logs/SHELL_GUARD_LO` |
| 2026-04-16 11:14:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:14:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md | Select-Object -First 25` |
| 2026-04-16 11:15:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg3.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:15:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:15:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; git diff --cached --stat` |
| 2026-04-16 11:15:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p = "commit_msg_sg4.txt"; $utf8 = New-Object System.Text.UTF8Encoding $false; $t = "chore: SH` |
| 2026-04-16 11:15:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md` |
| 2026-04-16 11:16:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg5.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:16:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:17:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:17:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg6.txt"; $utf8 = New-Object Sy` |
