# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
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
| 2026-04-16 11:19:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -8 --oneline; git status -sb` |
| 2026-04-16 11:20:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git diff --stat` |
| 2026-04-16 11:20:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/runtime/SESSION_LOG.md` |
| 2026-04-16 11:21:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/SESSION_LOG.md; $p = "commit` |
| 2026-04-16 11:21:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:21:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg.txt"; $utf8 = New-Object Sys` |
| 2026-04-16 11:21:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:21:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md | Select-Object -First 30` |
| 2026-04-16 11:21:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg2.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:21:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:22:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg3.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:22:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:22:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 11:22:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q` |
| 2026-04-16 11:22:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q` |
| 2026-04-16 11:24:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:25:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:25:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git diff --stat` |
| 2026-04-16 11:26:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_final_ev.txt"; $utf8 = New-Obje` |
| 2026-04-16 11:26:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git log -3 --oneline` |
| 2026-04-16 11:26:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_tail.txt"; $utf8 = New-Object S` |
| 2026-04-16 11:26:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:26:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_tail2.txt"; $utf8 = New-Object ` |
| 2026-04-16 14:40:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline cc3496be2a229908385b1dac4202de8616bb8da6; git log -1 --oneline eb01c5d768` |
| 2026-04-16 14:40:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat eb01c5d768c5ea6d9a52aafc2b61cf1264f92bc3 cc3496be2a229908385b1dac4202de8616bb8` |
| 2026-04-16 14:40:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff eb01c5d768c5ea6d9a52aafc2b61cf1264f92bc3 cc3496be2a229908385b1dac4202de8616bb8da6 -- ` |
| 2026-04-16 14:43:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff eb01c5d768c5ea6d9a52aafc2b61cf1264f92bc3 cc3496be2a229908385b1dac4202de8616bb8da6 -- ` |
| 2026-04-16 14:48:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js` |
| 2026-04-16 14:48:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-16 14:51:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js; python -c "import a` |
| 2026-04-16 14:53:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log -3 --oneline` |
| 2026-04-16 14:53:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $msg = @" fix: WDCalculator 사이드바 init이 loadSidebarEstimates API를 반환하도록 수정 initWdCalculatorSide` |
| 2026-04-16 14:53:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 14:54:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a; git fetch origin 2>&1; git log origin/deploy -1 --oneline 2>$null; git log orig` |
| 2026-04-16 14:54:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline origin/deploy..origin/feature/modular-monolith-wip | head ` |
| 2026-04-16 15:00:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 15:00:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app from flask import render_template_string with app.app_context(` |
| 2026-04-16 15:00:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_request_context('/'): html = app.jinja_env.get_t` |
| 2026-04-16 15:00:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_request_context('/'): html = app.jinja_env.get_t` |
| 2026-04-16 15:00:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-04-16 15:01:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/admin/layout.html templates/auth/layout.html templates/channel/layout.html t` |
| 2026-04-16 15:01:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 15:17:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js; node tests/support/` |
| 2026-04-16 15:18:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_late_bootstrap_contract_node_checks.js; node tests/support/wdc` |
| 2026-04-16 15:18:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-16 15:18:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/wdcalculator/composition.js templates/wdcalculator/partials/wdcalculator_scr` |
| 2026-04-16 15:25:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-16 15:25:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_url_bootstrap_contract_node_checks.js` |
| 2026-04-16 15:25:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1` |
| 2026-04-16 15:26:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_url_bootstrap_contract_node_checks.js` |
| 2026-04-16 15:26:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/wdcalculator/estimate-lifecycle.js templates/wdcalculator/partials/wdcalcula` |
| 2026-04-16 15:26:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F ".git/COMMITMSG_WDC_SIDEBAR.txt"; Remove-Item ".gi` |
| 2026-04-16 16:21:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-16 16:21:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py -q` |
| 2026-04-16 16:21:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json` |
| 2026-04-16 16:24:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m py_compile foms/web/orders/dashboard.py; python -m pytest tests/domains/test_dashboa` |
| 2026-04-16 16:24:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_p` |
| 2026-04-16 16:29:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 16:29:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_p` |
| 2026-04-16 16:31:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 16:32:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py tests/domains/test_erp_measure` |
| 2026-04-16 16:43:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 16:43:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 16:43:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_p` |
| 2026-04-16 16:44:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py::test_get_or_compute_logs_compute_ms_hi` |
| 2026-04-16 16:45:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 16:45:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 16:54:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git diff --stat` |
| 2026-04-16 16:54:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 16:54:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-16 16:54:45 | allow | `-` | `where.exe railway 2>$null; railway --version 2>&1` |
| 2026-04-16 16:54:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway status 2>&1` |
| 2026-04-16 16:55:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only HEAD -- migrations/ templates/ 2>&1` |
| 2026-04-16 19:35:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log origin/HEAD..HEAD --oneline 2>$null; git log HEAD..origin/HEAD --oneli` |
| 2026-04-16 19:35:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD; git rev-parse origin/feature/modular-monolith-wip 2>&1; git cherry -v orig` |
| 2026-04-16 19:37:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-16 19:37:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git reset HEAD -- _commit_msg_dmc_utf8.txt 2>$null; git status --short` |
