# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-07-02 09:04:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff 3dc6c058..HEAD -- "migrations/versions/phase_f_trgm_search_indexes.py" "templates/ord` |
| 2026-07-02 09:04:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff 3dc6c058 HEAD -- "templates/partials/shared/layout_head.html" "templates/partials/sha` |
| 2026-07-02 09:04:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff 3dc6c058..HEAD -- "foms/services/erp_permissions.py" "foms/services/drawing_workbench` |
| 2026-07-02 09:04:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 7abe2753 --stat` |
| 2026-07-02 09:05:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; $env:SECRET_KEY='ci-secret-key'; $` |
| 2026-07-02 09:09:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; $env:SECRET_KEY='ci-secret-key'; $` |
| 2026-07-02 09:09:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; powershell -NoProfile -File script` |
| 2026-07-02 09:10:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff static/js/measurement/image-export.js` |
| 2026-07-02 09:10:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; python -m pytest tests/domains/tes` |
| 2026-07-02 09:11:17 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tests\domains\test_*.py" | Measure-Object | Select-Object -ExpandProperty Count` |
| 2026-07-02 09:11:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; $env:SECRET_KEY="ci-secret-key"; $` |
| 2026-07-02 09:12:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; python -m pytest --ignore=tests/vi` |
| 2026-07-02 09:15:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue; python tools/perf/perf_scan.py --g` |
| 2026-07-02 09:15:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_design_ssot_lint.py tests/harness/test_hooks_smoke.py -q -` |
| 2026-07-02 09:16:12 | allow | `-` | `Start-Sleep -Seconds 2` |
| 2026-07-02 09:16:31 | allow | `-` | `Start-Sleep -Seconds 2` |
| 2026-07-02 09:16:40 | allow | `-` | `Start-Sleep -Seconds 2` |
| 2026-07-02 09:16:48 | allow | `-` | `Start-Sleep -Seconds 2` |
| 2026-07-02 09:32:42 | ask | `git\s+reset\s+--hard` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git fetch origin; git reset --hard eef8e96d; git merge origin/deploy ` |
| 2026-07-02 09:42:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5 origin/deploy 2>&1; Write-Host "---"; git log --oneline -5 origin/product` |
| 2026-07-02 09:42:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff origin/production..origin/deploy --stat -- templates/ partials/ shared/ layout_head.h` |
| 2026-07-02 09:42:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show-ref | Select-String "production|deploy"` |
| 2026-07-02 09:42:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff refs/remotes/origin/production..origin/deploy -- templates/partials/shared/layout_hea` |
| 2026-07-02 09:42:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff refs/remotes/origin/production..origin/deploy --stat -- static/js/runtime/ static/sw.` |
| 2026-07-02 09:42:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline refs/remotes/origin/production..origin/deploy 2>&1` |
| 2026-07-02 09:42:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff refs/remotes/origin/production..origin/deploy -- templates/partials/shared/layout_hea` |
| 2026-07-02 09:42:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 797c52da --stat; Write-Host "==="; git show 8f66ca1c --stat` |
| 2026-07-02 09:42:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/deploy:templates/partials/shared/layout_head.html 2>&1 | Select-Object -First ` |
| 2026-07-02 09:42:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show refs/remotes/origin/production:templates/partials/shared/layout_head.html 2>&1 | Sele` |
| 2026-07-02 09:43:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da --stat 2>&1 | Select-Object -Last 5; Write-Host "TOTAL:"; git dif` |
| 2026-07-02 09:43:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- Procfile railway.toml railway.json nixpacks.toml .env.example ` |
| 2026-07-02 09:43:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da --name-only -- foms/ services/ apps/ 2>&1` |
| 2026-07-02 09:43:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5 refs/remotes/origin/production; Write-Host "---"; git log --oneline -5 or` |
| 2026-07-02 09:43:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- static/js/runtime/erp-mobile-shell.js 2>&1` |
| 2026-07-02 09:43:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da --stat -- templates/orders/partials/ templates/partials/shared/ s` |
| 2026-07-02 09:43:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- templates/partials/shared/foms_p2_surface_bundle.html template` |
| 2026-07-02 09:43:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- foms/services/erp_dashboard_search.py foms/services/foms_unifi` |
| 2026-07-02 09:43:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da --name-only -- migrations/ alembic/ 2>&1` |
| 2026-07-02 09:43:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- templates/partials/shared/layout_head.html templates/partials/` |
| 2026-07-02 09:43:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da --stat -- templates/drawing/ templates/construction/ templates/pr` |
| 2026-07-02 09:43:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f7d43ce5..797c52da --stat -- templates/ static/js/runtime/ static/sw.js Procfile 2>&1` |
| 2026-07-02 09:43:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline f3ad6d1fa..797c52da -- templates/drawing/ templates/construction/ templates/` |
| 2026-07-02 09:43:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -3 refs/heads/production; git merge-base refs/heads/production origin/deploy` |
| 2026-07-02 09:43:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- static/js/foms/search.js 2>&1 | Select-Object -First 80` |
| 2026-07-02 09:43:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa 797c52da -- templates/partials/shared/layout_head.html templates/partials/s` |
| 2026-07-02 09:43:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- templates/measurement/partials/dashboard_scripts.html static/j` |
| 2026-07-02 09:44:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show f3ad6d1fa:templates/measurement/partials/dashboard_scripts.html | Select-String "html` |
| 2026-07-02 09:44:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (git show f3ad6d1fa:templates/partials/shared/layout_head.html | Measure-Object -Character).Ch` |
| 2026-07-02 09:44:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da --stat -- foms/services/orders/dashboard_read_model.py foms/api/n` |
| 2026-07-02 09:44:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f7d43ce5..797c52da -- templates/partials/shared/layout_head.html templates/partials/s` |
| 2026-07-02 09:44:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-tree f3ad6d1fa static/js/runtime/; Write-Host "---"; git ls-tree 797c52da static/js/run` |
| 2026-07-02 09:44:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- static/js/foms/alpine-store.js static/js/foms/sync.js static/j` |
| 2026-07-02 09:44:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff f3ad6d1fa..797c52da -- templates/partials/shared/alpine_layout.html templates/orders/` |
| 2026-07-02 09:44:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python tools` |
| 2026-07-02 09:46:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 09:49:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff refs/remotes/origin/production..origin/deploy -- templates/measurement/partials/dashb` |
| 2026-07-02 09:50:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 09:51:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 09:53:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff refs/remotes/origin/production..origin/deploy -- static/js/runtime/erp-shell.js 2>&1 ` |
| 2026-07-02 10:06:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 10:11:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python tools` |
| 2026-07-02 10:16:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if ($env:FOMS_STAGING_USERNAME) { Write-Output "USERNAME=set" } else { Write-Output "USERNAME=` |
| 2026-07-02 10:16:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "scripts/ops/compare_deploy_production_stress.ps1" 2>&1` |
| 2026-07-02 10:21:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --radar --json 2>&1 | Select-Object -Last 30; python tools/perf` |
| 2026-07-02 10:23:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (-not $env:FOMS_STAGING_USERNAME) { Write-Error "credentials missing" }; python -c " import` |
| 2026-07-02 10:23:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 10:28:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python tools` |
| 2026-07-02 10:31:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --radar --json 2>&1 | Out-File -Encoding utf8 "docs/harness/evi` |
| 2026-07-02 11:02:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 11:09:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; $env:FOMS_ST` |
| 2026-07-02 11:09:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 11:27:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python tools` |
| 2026-07-02 11:39:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import json, statistics from datetime import datetime, timezone, timedelta from pa` |
| 2026-07-02 11:40:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/_write_real_chrome_l3_evidence.py; $env:FOMS_STAGING_USERNAME="upperkill"; $` |
| 2026-07-02 11:57:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python tools` |
| 2026-07-02 12:01:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; python -c " ` |
| 2026-07-02 12:18:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy production 2>&1; git log -1 --oneline origin/production; git log -1 --` |
| 2026-07-02 12:18:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff origin/production..origin/deploy --stat 2>&1 | Select-Object -First 25; git diff orig` |
| 2026-07-02 12:18:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff origin/production..origin/deploy --name-only 2>&1 | Select-String -Pattern "erp-shell` |
| 2026-07-02 12:27:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_construction_dash` |
| 2026-07-02 12:28:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py tests/domains/test_constr` |
| 2026-07-02 12:28:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py tests/domains/test_constr` |
| 2026-07-02 12:28:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1; python -m pytest tests/domains/test_erp_per` |
| 2026-07-02 12:44:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1` |
| 2026-07-02 12:44:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py tests/domains/test_dashbo` |
| 2026-07-02 12:44:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-07-02 12:44:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-02 12:44:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-07-02 12:45:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_erp_pages_use_canonical_er` |
| 2026-07-02 12:45:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-07-02 12:45:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -3 --oneline` |
| 2026-07-02 12:46:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/construction_read_model.py foms/web/construction/dashboard.py foms/web/o` |
| 2026-07-02 12:46:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy 2>&1` |
| 2026-07-02 12:46:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Start-Sleep -Seconds 75; $r = Invoke-WebRequest -Uri "https://lahom-dev.up.railway.app/login" ` |
| 2026-07-02 12:47:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; $env:FRAGMEN` |
| 2026-07-02 12:54:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard 2>&1; python -` |
| 2026-07-02 12:54:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- foms/services/history_read_model.py foms/web/orders/history.py foms/services/` |
| 2026-07-02 12:56:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-07-02 12:56:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/history_read_model.py foms/web/orders/history.py foms/services/common/da` |
| 2026-07-02 12:57:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Start-Sleep -Seconds 80; Write-Output "deploy_wait_done"` |
| 2026-07-02 12:58:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; $env:FOMS_ST` |
| 2026-07-02 13:09:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard 2>&1; python -` |
| 2026-07-02 13:09:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- foms/services/measurement_read_model.py foms/web/measurement/dashboard.py foms/ser` |
| 2026-07-02 13:10:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline -- foms/services/drawing_workbench_read_model.py; git show HEAD:foms/web/` |
| 2026-07-02 13:11:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-07-02 13:11:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/measurement_read_model.py foms/web/measurement/dashboard.py foms/service` |
| 2026-07-02 13:11:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Start-Sleep -Seconds 85; Write-Output "ready"` |
| 2026-07-02 13:13:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:FOMS_STAGING_USERNAME="upperkill"; $env:FOMS_STAGING_PASSWORD="anfant8273!"; $env:FOMS_ST` |
| 2026-07-02 13:17:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_focus_o` |
| 2026-07-02 13:17:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py tests/domains/test_measur` |
| 2026-07-02 13:17:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/measurement_read_model.py foms/web/measurement/dashboard.py; git commit ` |
| 2026-07-02 14:08:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_estimate_service.` |
| 2026-07-02 14:08:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-02 14:08:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/orders/estimate_defaults.py foms/api/erp_estimates.py static/js/orders/e` |
| 2026-07-02 14:11:36 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\images" -Filter "*logo*" | Select-Object Name, Length` |
| 2026-07-02 14:11:42 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static" -Recurse -Filter "*lahom*" -ErrorAction SilentlyContinue | Select-Object Full` |
| 2026-07-02 14:11:47 | allow | `-` | `Test-Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\images\lahom-logo.png"; Test-Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahom` |
| 2026-07-02 14:12:05 | allow | `-` | `Copy-Item "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets\c__Users_USER_AppData_Roaming_Cursor_User_workspaceS` |
| 2026-07-02 14:12:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_estimate_table_colu` |
| 2026-07-02 14:12:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-02 14:13:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/images/lahom-logo-en.png static/js/orders/estimate-preview.js templates/orders/` |
| 2026-07-02 14:20:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py::test_ptc_committed_ro` |
| 2026-07-02 14:20:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/contracts/runtime/test_ptc_physical_exactness.py docs/specs/2026-04-07-repo-stru` |
| 2026-07-02 14:26:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_estimate_service.py::test_estimate_company_info_factory2_f` |
| 2026-07-02 14:28:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_estimate_service.py::test_estimate_company_info_factory2_f` |
| 2026-07-02 14:29:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/orders/estimate_defaults.py tests/domains/test_estimate_service.py; git ` |
| 2026-07-02 14:33:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log -5 --oneline origin/deploy; git log -3 --oneline refs/remotes/origin` |
| 2026-07-02 14:33:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show c40e2ad1 --no-stat; git merge-base refs/remotes/origin/production c40e2ad1; git log -` |
| 2026-07-02 14:33:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show refs/remotes/origin/production:foms/services/orders/estimate_defaults.py | Select-Str` |
| 2026-07-02 14:33:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show c40e2ad1 -p` |
| 2026-07-02 14:33:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show refs/remotes/origin/production:foms/services/orders/estimate_defaults.py` |
| 2026-07-02 14:33:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base --is-ancestor 635141b9 refs/remotes/origin/production; echo "635141b9 ancestor ` |
| 2026-07-02 14:34:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git cherry-pick c40e2ad1` |
| 2026-07-02 14:34:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_estimate_service.py::test_estimate_company_info_factory2_f` |
| 2026-07-02 14:34:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git checkout deploy` |
| 2026-07-02 14:35:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -8 --oneline origin/deploy` |
| 2026-07-02 14:35:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline refs/remotes/origin/production..origin/deploy -- foms/serv` |
| 2026-07-02 14:35:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show refs/remotes/origin/production:templates/orders/partials/erp_order_tab.html | Select-` |
| 2026-07-02 14:35:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline refs/remotes/origin/production | Select-String "2공장|factory2|6bc3c5f6|635141` |
| 2026-07-02 14:35:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git cherry-pick 77996b0a` |
| 2026-07-02 14:36:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/orders/estimate_defaults.py tests/domains/test_estimate_service.py; git ` |
| 2026-07-02 14:36:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git cherry-pick a1e507b6` |
| 2026-07-02 14:36:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_estimate_service.py tests/domains/test_erp_order_shared_fo` |
| 2026-07-02 14:36:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5; git push origin production` |
| 2026-07-02 14:38:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git log --oneline -3 production; git log --oneline -3 deploy` |
| 2026-07-02 14:38:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show deploy:migrations/versions/phase_f_trgm_search_indexes.py 2>&1 | Select-Object -First` |
| 2026-07-02 14:38:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline deploy -- migrations/versions/phase_f_trgm_search_indexes.py 2>&1; git log -` |
| 2026-07-02 14:38:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-tree -r production --name-only migrations/versions/ | Sort-Object; Write-Host "=== DEPL` |
| 2026-07-02 14:38:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline production -- migrations/versions/phase_e_trgm_perm_indexes.py | Select-Obje` |
| 2026-07-02 14:39:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show cb0bf873 --stat` |
| 2026-07-02 14:39:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline production..deploy -- migrations/ | Select-Object -First 15` |
| 2026-07-02 14:39:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git checkout deploy -- migrations/versions/phase_f_trgm_search_indexe` |
| 2026-07-02 14:39:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Test-Path migrations/versions/phase_f_trgm_search_indexes.py; python -m alembic heads 2>&1` |
| 2026-07-02 14:39:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F commit_msg.txt; Remo` |
| 2026-07-02 16:20:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-02 16:20:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_dashboa` |
| 2026-07-02 16:20:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-07-02 16:21:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py tests/domains/test_measur` |
| 2026-07-02 16:21:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- foms/services/measurement_read_model.py foms/web/measurement/dashboard.py foms/api` |
| 2026-07-02 16:22:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat; git log -3 --oneline` |
| 2026-07-02 16:22:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-02 16:23:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a; git rev-parse --abbrev-ref HEAD` |
| 2026-07-02 16:23:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/erp_map.py foms/api/measurement/routes.py foms/services/map_snapshot.py foms/` |
| 2026-07-02 16:23:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash push -m "regional-measurement-fix" --staged; git checkout deploy; git stash pop` |
| 2026-07-02 16:23:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git pull origin deploy` |
| 2026-07-02 16:24:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/measurement_read_model.py; git pull origin deploy` |
| 2026-07-02 16:24:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_dashboa` |
| 2026-07-02 16:24:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/erp_map.py foms/api/measurement/routes.py foms/services/map_snapshot.py foms/` |
| 2026-07-02 16:24:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-07-02 16:24:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash list` |
| 2026-07-02 16:24:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash drop stash@{0}` |
| 2026-07-02 16:24:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash drop "stash@{0}"` |
| 2026-07-02 16:30:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log --oneline -5 deploy; git log --oneline -5 production; git ` |
| 2026-07-02 16:30:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline -3 origin/production; git log --oneline -3 origin/deploy; ` |
| 2026-07-02 16:31:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse remotes/origin/production; git rev-parse remotes/origin/deploy; git merge-base r` |
| 2026-07-02 16:31:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production` |
| 2026-07-02 16:31:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge deploy -m "merge: deploy production 승격 — 지방주문 실측 대시보드 포함"` |
| 2026-07-02 16:31:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-02 16:32:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-07-02 22:22:57 | allow | `-` | `Copy-Item "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets\c__Users_USER_AppData_Roaming_Cursor_User_workspaceS` |
| 2026-07-02 22:23:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current` |
| 2026-07-02 22:23:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-07-02 22:23:15 | allow | `-` | `Test-Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\images\lahom-company-stamp.png"` |
| 2026-07-02 22:23:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_estima` |
| 2026-07-02 22:27:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=line 2>&1` |
| 2026-07-02 22:28:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/images/lahom-company-stamp.png templates/orders/partials/estimate_pane.html sta` |
| 2026-07-02 22:28:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F commit_msg.txt; Remo` |
| 2026-07-02 22:32:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_dashboa` |
| 2026-07-02 22:33:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_dashboa` |
| 2026-07-02 22:33:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_dashboa` |
| 2026-07-02 22:34:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-02 22:34:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git add foms/api/measurement/routes.py foms/services/measurement_re` |
| 2026-07-02 22:34:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline origin/production..origin/deploy | Select-Object -First 15` |
| 2026-07-02 22:35:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a | Select-String "production"; git rev-parse production; git rev-parse refs/remot` |
| 2026-07-02 22:35:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline refs/remotes/origin/production -8; Write-Host "---"; git log --oneline produ` |
| 2026-07-02 22:35:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show-ref production` |
| 2026-07-02 22:35:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base f3ad6d1f 3471502a; git log --oneline f3ad6d1f..3471502a | Measure-Object -Line;` |
| 2026-07-02 22:35:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base --is-ancestor a24dff5c production; echo "stamp on prod: $LASTEXITCODE"; git mer` |
| 2026-07-02 22:35:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline refs/remotes/origin/production..production | Measure-Object -Line; git log -` |
| 2026-07-02 22:35:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline f3ad6d1f..3471502a | Select-Object -First 25` |
| 2026-07-02 22:35:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin production; git rev-parse refs/remotes/origin/production; git log --oneline -` |
| 2026-07-02 22:35:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git cherry-pick a24dff5c` |
| 2026-07-02 22:35:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=line 2>&1; python` |
| 2026-07-02 22:36:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-07-02 22:44:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git log -1 --oneline; git show HEAD:templates/measurement/partials/` |
| 2026-07-02 22:44:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5 deploy; git show deploy:templates/measurement/partials/dashboard_main.htm` |
| 2026-07-02 22:44:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git pull origin deploy` |
| 2026-07-02 22:45:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show production:templates/measurement/partials/dashboard_main.html 2>$null | Select-String` |
| 2026-07-02 22:45:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base --is-ancestor ff9e0294 production; echo exit:$LASTEXITCODE; git log production ` |
| 2026-07-02 22:46:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_dashboa` |
| 2026-07-02 22:46:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-02 22:47:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/measurement/partials/dashboard_main.html static/css/contexts/orders/erp-orde` |
| 2026-07-02 22:51:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git branch --show-current; git log --oneline -3 origin/deploy; git log --one` |
| 2026-07-02 22:51:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse remotes/origin/production remotes/origin/deploy; git log --oneline remotes/origi` |
| 2026-07-02 22:52:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production` |
| 2026-07-02 22:52:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD remotes/origin/production; git log --oneline -2 HEAD` |
| 2026-07-02 22:52:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline remotes/origin/production..HEAD; git log --oneline HEAD..remotes/origin/depl` |
| 2026-07-02 22:52:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge deploy -m "merge: deploy production 승격 — 실측 패널 3색 뱃지 및 CSS cascade fix"` |
| 2026-07-02 22:52:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-02 22:53:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git log -1 --oneline` |
| 2026-07-03 10:18:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log eef8e96dc86917673e2efa83a6c943d3b2d760e6..HEAD --oneline --no-walk=sorted 2>$null; git` |
| 2026-07-03 10:18:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard --base eef8e96dc86917673e2efa83a6c943d3b2d760e6 --json` |
| 2026-07-03 10:18:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --radar --json` |
| 2026-07-03 10:18:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --audit --json` |
| 2026-07-03 10:18:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff eef8e96dc86917673e2efa83a6c943d3b2d760e6..HEAD --stat` |
| 2026-07-03 10:18:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log eef8e96dc86917673e2efa83a6c943d3b2d760e6..HEAD --format="%h|%s|%an|%ad" --date=short` |
| 2026-07-03 10:18:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log eef8e96dc86917673e2efa83a6c943d3b2d760e6..HEAD --oneline --no-merges 2>&1` |
| 2026-07-03 10:18:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log eef8e96dc86917673e2efa83a6c943d3b2d760e6..HEAD --oneline --no-merges --format="%H %s" ` |
| 2026-07-03 10:18:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat b47399a2de60083de85cab30449f98d0a4f4e790 2>&1 | head -40` |
| 2026-07-03 10:18:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat b22d948d7da62101b954bfe09c5a9a9d1ff45e4b 2>&1 | head -50` |
| 2026-07-03 10:18:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 8ffc9c4ab6a33e9fcc03afd3f63fe530220dde6e 2>&1 | head -40` |
| 2026-07-03 10:18:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log eef8e96..HEAD --oneline` |
| 2026-07-03 10:19:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat b47399a2de60083de85cab30449f98d0a4f4e790 2>&1 | Select-Object -First 40` |
| 2026-07-03 10:19:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat b22d948d7da62101b954bfe09c5a9a9d1ff45e4b 2>&1 | Select-Object -First 50` |
| 2026-07-03 10:19:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 8ffc9c4ab6a33e9fcc03afd3f63fe530220dde6e 2>&1 | Select-Object -First 40` |
| 2026-07-03 10:19:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 3dc6c0582b22052e0ae4417c39f36c7af2bd7ea5 2>&1 | Select-Object -First 30` |
| 2026-07-03 10:19:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 797c52dab28c51e7c25d4b9e1a135f13df348bdf 2>&1 | Select-Object -First 30` |
| 2026-07-03 10:19:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 5bd179c1fa4c3085a008597c19ec024bed8dac6d 2>&1 | Select-Object -First 30; git s` |
| 2026-07-03 10:19:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 4df6c74a32740b8b349fb275f4a5722023523e27 2>&1 | Select-Object -First 30` |
| 2026-07-03 10:19:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 8f66ca1c742fb53ee80956a01d9d7f479cbbba87 2>&1 | Select-Object -First 30; git s` |
| 2026-07-03 10:19:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 9c52ecdde327d5a838b98d2a6ee19902711c031f 2>&1 | Select-Object -First 25; git s` |
| 2026-07-03 10:19:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 0fa05f76ce52b40ff7bf47f0c6b9f955f693f94b 2>&1 | Select-Object -First 20; git s` |
| 2026-07-03 10:19:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 294635d8b12c96c4da93195c255a7e3e77807b38 2>&1 | Select-Object -First 20; git s` |
| 2026-07-03 10:19:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff eef8e96dc86917673e2efa83a6c943d3b2d760e6..HEAD -- foms/services/common/dashboard_cach` |
| 2026-07-03 10:20:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat 0fa05f76ce52b40ff7bf47f0c6b9f955f693f94b 2>&1 | Select-Object -First 25` |
| 2026-07-03 10:20:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log eef8e96dc86917673e2efa83a6c943d3b2d760e6..HEAD --oneline --no-merges --format="%ad %h ` |
| 2026-07-03 10:22:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard --base eef8e96dc86917673e2efa83a6c943d3b2d760e6; python` |
| 2026-07-03 10:22:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show eef8e96dc86917673e2efa83a6c943d3b2d760e6 --format="%h %s%n%b" --no-patch` |
| 2026-07-03 15:02:49 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-07-03 15:03:07 | allow | `-` | `python -m pytest tests/domains/test_channel_integration_smoke.py tests/domains/test_channel_push_messages.py tests/domains/test_erp_order_shared_form_scripts.py` |
| 2026-07-03 15:03:20 | allow | `-` | `python -m pytest tests/domains/test_channel_integration_smoke.py tests/domains/test_channel_push_messages.py tests/domains/test_erp_order_shared_form_scripts.py` |
| 2026-07-03 15:03:49 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-07-03 15:04:06 | allow | `-` | `git --no-pager diff --stat; echo "----- STATUS -----"; git --no-pager status --short` |
| 2026-07-03 15:07:23 | allow | `-` | `python -m pytest tests/domains/test_channel_integration_smoke.py tests/domains/test_channel_push_messages.py tests/domains/test_erp_order_shared_form_scripts.py` |
| 2026-07-03 15:08:11 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-07-03 15:08:22 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-03 15:14:06 | allow | `-` | `python -m pytest tests/domains/test_channel_integration_smoke.py tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_orders_structured_pu` |
| 2026-07-03 15:14:42 | allow | `-` | `python tools/perf/perf_scan.py --guard; echo "PERF_EXIT=$LASTEXITCODE"` |
| 2026-07-03 15:14:54 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1; echo "SMOKE_EXIT=$LASTEXITCODE"` |
| 2026-07-03 15:17:16 | allow | `-` | `Get-Content *.txt | Select-Object -First 60` |
| 2026-07-03 15:21:00 | allow | `-` | `git --no-pager diff -- templates/measurement/map_view.html` |
| 2026-07-03 15:21:25 | allow | `-` | `python tools/perf/perf_scan.py --guard; echo "---APP---"; python -c "import app; print('APP_OK')"` |
| 2026-07-03 15:21:27 | allow | `-` | `python -m pytest tests/domains/test_map_view_manager_contract.py tests/performance/test_page_local_defer_contract.py tests/domains/test_format_datetime_kst.py t` |
| 2026-07-03 15:21:56 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 45` |
| 2026-07-03 15:32:10 | allow | `-` | `echo "=====ALL refs named production====="; git for-each-ref | Select-String "production"; echo "=====EXPLICIT remote HEAD====="; git rev-parse refs/remotes/ori` |
| 2026-07-03 15:32:41 | allow | `-` | `$prod="refs/remotes/origin/production"; $dep="refs/remotes/origin/deploy"; echo "=====TRUE COMMITS prod..deploy====="; git log "$prod..$dep" --oneline; echo "==` |
| 2026-07-03 15:38:09 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-03 15:46:50 | allow | `-` | `python tools/perf/perf_scan.py --guard; echo "PERF_GUARD_EXIT=$LASTEXITCODE"` |
| 2026-07-03 15:49:04 | allow | `-` | `$prod="5684b4ec149ad54f8b8f403425c2530802683bcb"; $dep="21e38f32f5889b49f406a8eb3edbb5dfc70d2ddc"; $mb=git merge-base $prod $dep; echo "=====MERGE-BASE====="; g` |
| 2026-07-03 15:49:41 | allow | `-` | `$prod="5684b4ec149ad54f8b8f403425c2530802683bcb"; $dep="21e38f32f5889b49f406a8eb3edbb5dfc70d2ddc"; echo "=====is deploy's 인감 commit a24dff5c an ancestor of BOTH` |
| 2026-07-03 15:50:41 | allow | `-` | `echo "=====merged tree (from dry-run)====="; echo "1b12e50a0a7c4130ac8fa3b9ec6890bd61c3be06"; echo "=====deploy 21e38f32 tree====="; git rev-parse "21e38f32^{tr` |
| 2026-07-03 15:51:58 | allow | `-` | `$m = git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>"-tree 1b12e50a0a7c4130ac8fa3b9ec6890bd61c3be06 -p 5684b4ec149ad54f8b8f403425c25308026` |
| 2026-07-03 15:52:46 | allow | `-` | `echo "=====git aliases====="; git config --get-regexp "^alias\." 2>&1; echo "=====core.hooksPath====="; git config --get core.hooksPath 2>&1; echo "=====.git/ho` |
| 2026-07-03 15:53:41 | allow | `-` | `echo "=====which git====="; (Get-Command git -All | Select-Object -First 5 | Format-List Name,CommandType,Source | Out-String); echo "=====git version====="; gi` |
| 2026-07-03 15:54:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log --oneline deploy -10; git log --oneline production -10 2>$` |
| 2026-07-03 15:54:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy production; git rev-parse origin/deploy origin/production; git log --o` |
| 2026-07-03 15:55:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show-ref production; git branch -a | Select-String production; git log -1 --oneline refs/r` |
| 2026-07-03 15:55:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline production..origin/deploy; git rev-list --count production..origin/deploy; g` |
| 2026-07-03 15:55:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-03 15:55:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-07-03 15:55:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-03 15:55:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge origin/deploy --no-edit -m "merge: deploy production 승격 — E` |
| 2026-07-03 15:56:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline; git rev-list --count refs/remotes/origin/production..HEAD; git push orig` |
| 2026-07-03 15:56:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin production deploy; git log -1 --oneline origin/production; git log -1 --oneli` |
| 2026-07-03 15:56:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline refs/remotes/origin/production; git log -1 --oneline HEAD; git merge-base` |
| 2026-07-03 15:56:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin refs/heads/production:refs/remotes/origin/production; git log -1 --oneline re` |
| 2026-07-03 15:56:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-07-03 15:58:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy production; git log -1 --oneline refs/remotes/origin/deploy; git log -` |
| 2026-07-03 16:22:13 | allow | `-` | `git -C "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" log --oneline -20 --all -S "Advisor" -- "*.md" "*.mdc"` |
| 2026-07-03 16:22:26 | allow | `-` | `git -C "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" show ad7ce1dc --stat` |
| 2026-07-03 16:22:32 | allow | `-` | `Get-ChildItem -Path "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\agent-transcripts" -Recurse -Filter "*.jsonl" | S` |
| 2026-07-03 16:22:39 | allow | `-` | `Get-ChildItem -Path "C:\Users\USER\AppData\Roaming\Cursor\User" -Recurse -Include "*.md","*.json","*.mdc" -ErrorAction SilentlyContinue | Select-String -Pattern` |
| 2026-07-03 16:22:59 | allow | `-` | `Get-ChildItem -Path "C:\Users\USER\.cursor\projects" -Recurse -Filter "*.jsonl" -ErrorAction SilentlyContinue | Select-String -Pattern "모델 역할 분담" -List -ErrorAc` |
| 2026-07-03 19:33:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; gh auth status 2>&1; gh pr view --json baseRefName -q .baseRefName 2>&1` |
| 2026-07-03 19:33:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git remote get-url origin 2>$null; git status; git log --oneline -5` |
| 2026-07-03 19:33:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff static/css/contexts/orders/dashboard-control-tower.css templates/par` |
| 2026-07-03 19:33:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1` |
| 2026-07-03 19:33:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-03 19:33:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/css/contexts/orders/dashboard-control-tower.css" "templates/partials/shared/er` |
| 2026-07-03 19:33:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "docs/AI_CHANGELOG.md" "docs/AI_STATUS.md" "docs/context/SHELL_GUARD_LOG.md" "docs/gui` |
