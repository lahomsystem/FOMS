# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-30 15:28:10 | allow | `-` | `python -m pytest tests\domains\test_erp_order_shared_form_scripts.py -q` |
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
| 2026-04-19 16:12:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-04-19 16:13:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/EDIT_LO` |
| 2026-04-20 13:36:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status --short` |
| 2026-04-20 13:36:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout origin/deploy -- templates/cs/partials/as_dashboard_body.html` |
| 2026-04-20 13:36:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git rm -f apps/api/erp_orders_as.py apps/api/orders.py 2>&1` |
| 2026-04-20 13:36:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status --short | Select-Object -First 40` |
| 2026-04-20 13:36:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --name-only --diff-filter=U` |
| 2026-04-20 13:36:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add foms/api/erp_orders_structured.py tests/domains/test_erp_as_dashboard_tabs.py tests/` |
| 2026-04-20 13:37:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status -sb | Select-Object -First 5` |
| 2026-04-20 13:37:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git commit --trailer "Made-with: Cursor" -m "merge: deploy into production (WD calculator + ` |
| 2026-04-20 13:37:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin production` |
| 2026-04-20 13:37:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout feature/modular-monolith-wip && git log -1 --oneline origin/deploy && git log -` |
| 2026-04-20 13:41:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && copy /Y "static\js\erp\order-detail-fragment.js" "static\js\orders\order-detail-fragment.js"` |
| 2026-04-20 13:41:13 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Copy-Item -Force "static\js\erp\order-detail-fragment.js" "static\js\orders\order-de` |
| 2026-04-20 13:41:47 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --exit-code -- docs/harness/bundles/HARNESS_BUNDLE_*.md; echo "exit=$LASTEX` |
| 2026-04-20 13:41:48 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py::` |
| 2026-04-20 13:42:28 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/build_context_bundle.py --all; git diff --exit-code -- docs/har` |
| 2026-04-20 13:42:47 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/wdcalculator/test_estimate_lifecycle_contracts.py t` |
| 2026-04-20 13:44:21 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git branch -a` |
| 2026-04-20 13:44:41 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/build_context_bundle.py --all 2>$null; git add docs/harness/bun` |
| 2026-04-20 13:44:47 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-20 13:44:57 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -m "fix(ci): harness bundles, WD calculator` |
| 2026-04-20 13:45:03 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy 2>&1; git checkout deploy 2>&1; git pull --ff-only origin de` |
| 2026-04-20 13:45:09 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge feature/modular-monolith-wip -m "Merge branch 'feature/modular-monolith-wi` |
| 2026-04-20 13:45:15 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-04-20 13:45:23 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout feature/modular-monolith-wip` |
| 2026-04-20 13:48:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import os; os.environ.pop('DATABASE_URL', None); os.environ['PGHOST']='x.railway.` |
| 2026-04-20 13:48:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c " import os, sys # fresh subprocess - clear relevant for k in list(os.environ): if` |
| 2026-04-20 13:48:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && pytest -q tests/domains/test_db_url_resolver.py tests/contracts/runtime/foms_namespace_surfa` |
| 2026-04-20 13:48:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && pytest -q tests/domains/test_db_url_resolver.py tests/contracts/runtime/foms_namespace_surfa` |
| 2026-04-20 13:52:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && pytest -q tests/domains/test_db_url_resolver.py --tb=short` |
| 2026-04-20 13:54:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status -sb && git branch -a` |
| 2026-04-20 13:54:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git fetch origin && git log --oneline -1 origin/deploy && git log --oneline -1 origin/produc` |
| 2026-04-20 13:54:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline origin/production..origin/deploy` |
| 2026-04-20 13:54:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline origin/deploy..HEAD -5` |
| 2026-04-20 13:54:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline origin/feature/modular-monolith-wip..HEAD -5` |
| 2026-04-20 13:54:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add db.py foms/services/db_url_resolver.py tests/domains/test_db_url_resolver.py && git ` |
| 2026-04-20 13:54:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout deploy && git pull origin deploy && git merge feature/modular-monolith-wip -m "` |
| 2026-04-20 13:55:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git pull origin production && git merge origin/deploy -m "merge: ` |
| 2026-04-20 13:55:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout feature/modular-monolith-wip` |
| 2026-04-20 13:59:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && pytest -q tests/domains/test_db_url_resolver.py tests/contracts/runtime/foms_namespace_surfa` |
| 2026-04-20 14:00:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && pytest -q tests/domains/test_user_delete.py --maxfail=1 --tb=line 2>&1 | Select-Object -Firs` |
| 2026-04-20 14:07:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_db_url_resolver.py tests/domains/conftest.py tests/domai` |
| 2026-04-20 14:07:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_db_url_resolver.py tests/domains/test_wdcalculator_produ` |
| 2026-04-20 14:07:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git branch -a` |
| 2026-04-20 14:07:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log -5 --oneline` |
| 2026-04-20 14:07:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add db.py foms/services/db_url_resolver.py tests/domains/test_db_url_resolver.py tests/c` |
| 2026-04-20 14:08:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git fetch origin && git checkout deploy && git pull origin deploy && git merge feature/modul` |
| 2026-04-20 14:08:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin deploy && git checkout production && git pull origin production && git merge` |
| 2026-04-20 14:08:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin feature/modular-monolith-wip` |
| 2026-04-20 16:22:58 | allow | `-` | `wc -l "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\orders\partials\dashboard_scripts_core.html" "c:\Users\USER\OneDrive\Desktop\SY\pro` |
| 2026-04-20 16:24:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c " import re, pathlib root = pathlib.Path('templates/orders/partials') out = pathli` |
| 2026-04-20 16:27:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_db_url_resolver.py tests/contracts/runtime/foms_namespac` |
| 2026-04-20 16:27:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_db_url_resolver.py tests/contracts/runtime/foms_namespac` |
| 2026-04-20 16:27:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_or` |
| 2026-04-20 16:43:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git branch -vv && git remote -v` |
| 2026-04-20 16:43:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/web/orders/dashboard.py static/js/orders/erp-dashboard-entry.js static/js/orders/` |
| 2026-04-20 16:43:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -m "feat(erp): external dashboard bundle + entry load` |
| 2026-04-20 16:43:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-20 22:08:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git branch -vv; git log -1 --oneline` |
| 2026-04-20 22:08:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git merge feature/modular-monolith-wip -m "Merge feature/modular-monolith` |
| 2026-04-20 22:08:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-04-20 22:08:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy -m "Merge deploy: ERP dashboard external bundle and ` |
| 2026-04-20 22:08:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git checkout feature/modular-monolith-wip; git log -2 --oneline pr` |
| 2026-04-20 22:16:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_notification_badge_dedup.py::test_erp_pages_use_single_not` |
| 2026-04-20 22:16:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_notification_badge_dedup.py::test_erp_pages_use_single_not` |
| 2026-04-20 22:18:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-04-20 22:18:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/domains/test_notification_badge_dedup.py; git commit --trailer "Made-with: Curso` |
| 2026-04-20 22:18:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-20 22:18:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git merge feature/modular-monolith-wip -m "Merge feature/modular-monolith` |
| 2026-04-20 22:18:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy; git checkout production; git merge deploy -m "Merge deploy: notificati` |
| 2026-04-20 22:18:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git checkout feature/modular-monolith-wip; git log -1 --oneline de` |
| 2026-04-21 09:02:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-04-21 09:02:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/orders/partials/estimate_pane.html; git commit --trailer "Made-with: Cursor"` |
| 2026-04-21 09:02:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip; git checkout deploy; git merge feature/modular-m` |
| 2026-04-21 09:02:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy; git checkout production; git merge deploy -m "Merge deploy: estimate p` |
| 2026-04-21 09:02:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git checkout feature/modular-monolith-wip` |
| 2026-04-22 10:59:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from foms.services.erp_policy import is_drawing_workbench_participant, has_pendin` |
| 2026-04-22 10:59:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from foms.services.orders.erp_policy_permissions import is_drawing_workbench_part` |
| 2026-04-22 10:59:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_erp_shell_fragment_contract.py::test_ept_b5_drawing_work` |
| 2026-04-22 11:00:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_erp_shell_fragment_contract.py -k "drawing_workbench" -q` |
| 2026-04-22 11:04:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status -sb && git remote -v && git branch --show-current` |
| 2026-04-22 11:04:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add \ foms/api/drawing/erp_orders_drawing.py \ foms/api/drawing/erp_orders_revision.py \` |
| 2026-04-22 11:04:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/drawing/erp_orders_drawing.py foms/api/drawing/erp_orders_revision.py foms/se` |
| 2026-04-22 11:18:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git fetch origin deploy 2>&1; git log --oneline -3 origin/deploy 2>&1; git log --oneline -3 ` |
| 2026-04-22 11:18:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin feature/modular-monolith-wip:deploy` |
| 2026-04-23 08:32:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_channel_push_messages.py -q --tb=short` |
| 2026-04-23 08:33:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git branch -vv && git log origin/main..HEAD --oneline 2>nul; git log origin/ma` |
| 2026-04-23 08:34:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git fetch origin 2>&1 && git log production..HEAD --oneline | head -20 && echo "---" && git ` |
| 2026-04-23 08:34:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log production..HEAD --oneline | Select-Object -First 25; Write-Host "--` |
| 2026-04-23 08:34:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base production HEAD; git rev-parse origin/production 2>$null; git branch -r | Selec` |
| 2026-04-23 08:34:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log 9358ca6b..873a5c67 --oneline | Measure-Object -Line; git log 9358ca6b..873a5c67 --onel` |
| 2026-04-23 08:34:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log 9358ca6b..873a5c67 --oneline` |
| 2026-04-23 08:34:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add .claude/commands/gdm.md AGENTS.md app.py docs/AI_CHANGELOG.md docs/AI_STATUS.md docs/c` |
| 2026-04-23 08:34:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only; git diff --cached --name-only` |
| 2026-04-23 08:34:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-23 08:35:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; git commit --trailer "Made-with: Cursor" -m "fea` |
| 2026-04-23 08:50:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout feature/modular-monolith-wip` |
| 2026-04-23 08:51:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git checkout deploy; git pull origin deploy; git status -sb` |
| 2026-04-23 08:54:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && set DATABASE_URL=sqlite:///:memory:&& set SECRET_KEY=ci-secret-key&& set FLASK_ENV=testing&&` |
| 2026-04-23 08:55:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && $env:DATABASE_URL="sqlite:///:memory:"; $env:SECRET_KEY="ci-secret-key"; $env:FLASK_ENV="tes` |
| 2026-04-23 08:55:07 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL="sqlite:///:memory:"; $env:SECRET_KEY="ci-secret-key"; $env:FLASK_` |
| 2026-04-23 08:55:15 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git status -sb` |
| 2026-04-23 08:55:20 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/test_as_received_date_kst.py; git commit --trailer "Made-with: Cursor"` |
| 2026-04-23 08:55:25 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-04-23 08:59:43 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL="sqlite:///:memory:"; $env:SECRET_KEY="ci-secret-key"; $env:FLASK_` |
| 2026-04-23 08:59:52 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git add tests/test_as_received_date_kst.py; git status -s` |
| 2026-04-23 08:59:56 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -m "fix(ci): remove duplicate AS KST test f` |
| 2026-04-23 09:00:00 | allow | `-` | `Set-Location "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-04-23 09:47:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_channel_push_messages.py tests/domains/test_channel_inte` |
| 2026-04-23 09:50:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git branch -vv && git log -3 --oneline` |
| 2026-04-23 09:50:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git fetch origin deploy production 2>&1 && git log --oneline origin/deploy -2 && echo "---" ` |
| 2026-04-23 09:50:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git merge-base origin/deploy origin/production | ForEach-Object { git log -1 --oneline $_ };` |
| 2026-04-23 09:50:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git rev-parse deploy production origin/production && git log -1 --oneline production && git ` |
| 2026-04-23 09:50:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add foms/api/erp_orders_structured.py foms/services/channel_event_payloads.py tests/cont` |
| 2026-04-23 09:51:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin deploy` |
| 2026-04-23 09:51:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git pull origin production --ff-only && git merge deploy -m "Merg` |
| 2026-04-23 09:51:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout deploy && git log -1 --oneline && git status -s` |
| 2026-04-23 10:32:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_channel_push_messages.py tests/domains/test_erp_orders_s` |
| 2026-04-23 11:14:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git branch --show-current && git log -1 --oneline` |
| 2026-04-23 11:14:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add foms/api/erp_orders_structured.py tests/domains/test_channel_push_messages.py tests/` |
| 2026-04-23 11:14:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin deploy && git checkout production && git pull origin production --ff-only &&` |
| 2026-04-28 14:04:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1; python -m pytest tests/domains/test_erp_as_` |
| 2026-04-28 14:05:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -a; git diff --stat` |
| 2026-04-28 14:05:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat HEAD; git diff foms/services/channel_event_payloads.py 2>&1 | Select-Object -F` |
| 2026-04-28 14:05:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/contexts/cs/as-dashboard-body.css templates/cs/partials/as_dashboard_body.h` |
| 2026-04-28 14:49:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production` |
| 2026-04-28 14:49:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline origin/deploy..origin/production -5; git log --oneline ori` |
| 2026-04-28 14:49:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy:production` |
| 2026-04-28 14:49:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin production; git branch -f production origin/production; git checkout deploy; ` |
| 2026-04-28 15:03:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-28 15:03:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git branch --show-current` |
| 2026-04-28 15:03:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_as_dashboard_tabs.py -q --tb=short 2>&1` |
| 2026-04-28 15:03:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1` |
| 2026-04-28 15:04:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "open('commit_msg_tmp.txt','w',encoding='utf-8').write('feat: AS ??쒕낫??怨좉컼??諛쒖＜???쒖` |
| 2026-04-28 15:04:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "open('commit_msg_tmp.txt','w',encoding='utf-8').write('feat: AS ??쒕낫??怨좉컼??諛쒖＜???쒖` |
| 2026-04-28 15:04:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/cs/partials/as_dashboard_body.html static/css/contexts/cs/as-dashboard-body.` |
| 2026-04-28 15:16:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log -1 --oneline deploy; git log -1 --oneline origin/production 2>$null;` |
| 2026-04-30 14:06:03 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\terminals" | Select-Object Name,Length,LastWriteTime; g` |
| 2026-04-30 14:08:12 | allow | `-` | `python -m pytest tests\domains\test_erp_order_shared_form_scripts.py tests\domains\test_erp_orders_structured_put.py -q` |
| 2026-04-30 14:08:30 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-30 14:08:42 | allow | `-` | `python tools\harness\verify_result.py --json` |
| 2026-04-30 14:39:37 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\terminals" | Select-Object Name,Length,LastWriteTime` |
| 2026-04-30 14:39:42 | allow | `-` | `python -m py_compile "tools\harness\task_classifier.py" "tools\harness\prompt_router.py"` |
| 2026-04-30 14:39:42 | allow | `-` | `python -m pytest "tests\harness\test_task_classifier.py" -q` |
| 2026-04-30 14:39:53 | allow | `-` | `powershell -NoProfile -File "tools\harness\run_codex.ps1" -Profile review -Target "tools\harness\build_context_bundle.py" -DryRun` |
| 2026-04-30 14:39:53 | allow | `-` | `powershell -NoProfile -File "tools\harness\run_codex.ps1" -Profile review -Target "docs\AI_STATUS.md" -AdditionalPrompt "[level=top]" -DryRun` |
| 2026-04-30 14:41:13 | allow | `-` | `python "tools\harness\build_context_bundle.py" --all` |
| 2026-04-30 14:41:22 | allow | `-` | `python -m pytest "tests\harness\test_task_classifier.py" "tests\harness\test_hooks_smoke.py" "tests\harness\test_run_codex_levels.py" -q` |
| 2026-04-30 14:41:56 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-30 14:42:15 | allow | `-` | `python "tools\harness\verify_result.py" --json` |
| 2026-04-30 15:01:41 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-30 15:17:31 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-30 15:17:31 | allow | `-` | `python -m pytest tests\domains\test_erp_order_shared_form_scripts.py -q` |
| 2026-04-30 15:23:43 | allow | `-` | `python -m pytest tests\domains\test_erp_order_shared_form_scripts.py -q` |
| 2026-04-30 15:28:10 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-05-05 10:49:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-05-05 11:16:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "import app; print('APP_OK')" ; pytest tests/domains/test_orders_boundary_contract.` |
| 2026-05-05 11:18:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; pytest tests/domains/test_orders_boundary_contract.py tests/domains/test_erp_mobile_layout_an` |
| 2026-05-05 11:18:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --timeout=120` |
| 2026-05-05 11:18:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q` |
| 2026-05-05 11:49:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_shipment_as_recom` |
| 2026-05-05 11:50:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_shipment_as_recommendations.py -v` |
| 2026-05-05 11:51:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-05-05 12:03:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_shipment_as_recom` |
| 2026-05-05 12:04:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_orders_boundary_contract.py tests/domains/test_erp_mobile_` |
| 2026-05-05 12:06:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_namespaced_geoc` |
| 2026-05-05 16:17:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-05-05 16:18:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat static/js/runtime/erp-shell.js` |
| 2026-05-05 16:18:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F .git_com` |
| 2026-05-05 16:18:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-files .git_commit_msg_deploy.txt; if (Test-Path .git_commit_msg_deploy.txt) { Get-Item ` |
| 2026-05-05 16:18:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rm -f .git_commit_msg_deploy.txt; git commit --trailer "Co-authored-by: Cursor <cursoragen` |
| 2026-05-05 16:19:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-05-05 19:01:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_shipment_as_recommendations.py -q; python -m pytest tests/` |
| 2026-05-05 19:01:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_shipment_as_recommendations.py -q` |
| 2026-05-05 19:33:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json; python -c "import app; print('APP_OK')"; python ` |
| 2026-05-05 19:34:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/cs/as_orders.py foms/api/orders/field_update.py foms/api/shipment/recommendat` |
| 2026-05-05 19:34:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F .git_commit_msg_depl` |
| 2026-05-05 19:34:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-05-06 08:21:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-05-06 08:35:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_display.py tests/domains/test_erp_sync_columns.py -q` |
| 2026-05-06 08:36:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_display.py tests/domains/test_erp_sync_columns.py -q; ` |
| 2026-05-06 08:42:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-05-06 08:43:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-05-06 08:43:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -u; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F commit_m` |
