# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-06-17 15:20:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py -q` |
| 2026-06-17 15:21:01 | allow | `-` | `powershell -NoProfile -Command ". 'c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tools\harness\gstack_qa_skill.ps1'; $r='c:\Users\USER\OneDrive\De` |
| 2026-06-17 15:21:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py -q` |
| 2026-06-17 15:21:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py -q` |
| 2026-06-17 15:21:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tools/harness/gstack_qa_skill.ps1 tools/harness/run_gstack_qa.ps1 tools/harness/run_co` |
| 2026-06-17 15:26:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py::test_ptc_committed_ro` |
| 2026-06-17 15:26:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/contracts/runtime/test_ptc_physical_exactness.py docs/specs/2026-04-07-repo-stru` |
| 2026-06-17 15:38:40 | allow | `-` | `railway --version 2>&1; railway status 2>&1` |
| 2026-06-17 15:38:47 | allow | `-` | `railway service list 2>&1; railway variables 2>&1 | Select-Object -First 40` |
| 2026-06-17 15:39:04 | allow | `-` | `railway logs --help 2>&1 | Select-Object -First 30` |
| 2026-06-17 15:39:09 | allow | `-` | `railway logs -n 80 --filter "@level:info" 2>&1` |
| 2026-06-17 15:39:26 | allow | `-` | `railway logs -n 200 --filter "DashCache" 2>&1 | Select-Object -Last 40` |
| 2026-06-17 15:39:36 | allow | `-` | `railway logs -s WORKER -n 30 2>&1; railway logs -s Postgres -n 20 2>&1` |
| 2026-06-17 15:55:16 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-17 16:04:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff; git log -3 --oneline; git branch --show-current` |
| 2026-06-17 16:05:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/css/components/foms-shipment-mobile.css" "templates/shipment/partials/shipment` |
| 2026-06-17 16:05:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 16:06:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-06-17 16:18:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git status -sb; git log -1 --oneline deploy; git log -1 --oneline o` |
| 2026-06-17 16:18:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline origin/production..deploy -5; git log --oneline deploy..or` |
| 2026-06-17 16:18:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy -m "merge: deploy → prod` |
| 2026-06-17 16:19:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -3 production; git log --oneline -3 origin/production; git log --oneline ori` |
| 2026-06-17 16:19:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base production origin/production; git log --oneline --graph production origin/produ` |
| 2026-06-17 16:19:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse production; git rev-parse origin/production; git merge-base --is-ancestor origin` |
| 2026-06-17 16:19:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 16:20:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-06-18 10:49:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_mobile_order_display.py tests/domains/test_erp_measure` |
| 2026-06-18 10:49:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1` |
| 2026-06-18 10:49:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_mobile_order_display.py tests/domains/test_erp_measure` |
| 2026-06-18 10:53:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_mobile_order_display.py::test_batch_resolve_queue_atta` |
| 2026-06-18 10:53:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git status --short` |
| 2026-06-18 10:53:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-06-18 10:54:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-06-18 10:54:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_mobile_order_display.py foms/web/orders/dashboard.py foms/web/produc` |
| 2026-06-18 10:59:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git status --short; git log -1 --oneline; git status -sb` |
| 2026-06-18 10:59:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy 2>&1; git rev-parse HEAD; git rev-parse origin/deploy` |
| 2026-06-18 11:04:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy production 2>&1; git log -1 --oneline deploy; git log -1 --oneline ori` |
| 2026-06-18 11:04:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy -m "merge: deploy -> pro` |
| 2026-06-18 11:04:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-06-18 11:04:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git log -1 --oneline; git rev-parse origin/production` |
| 2026-06-18 11:26:34 | allow | `-` | `railway --version 2>&1; railway whoami 2>&1; railway status 2>&1` |
| 2026-06-18 11:26:40 | allow | `-` | `railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.stdin); keys=[k for k in d if k.startswith('CHANNEL_') or k=='FOMS_BASE_URL']; print` |
| 2026-06-18 11:26:40 | allow | `-` | `railway environment list 2>&1` |
| 2026-06-18 11:26:40 | allow | `-` | `railway service list 2>&1` |
| 2026-06-18 11:26:46 | allow | `-` | `railway --help 2>&1 | Select-Object -First 40` |
| 2026-06-18 11:26:50 | allow | `-` | `railway service --help 2>&1; railway environment --help 2>&1` |
| 2026-06-18 11:26:51 | allow | `-` | `railway logs -n 100 --filter "채널톡" 2>&1 | Select-Object -Last 30` |
| 2026-06-18 11:26:58 | allow | `-` | `railway environment config --json 2>&1` |
| 2026-06-18 11:26:58 | allow | `-` | `railway service status 2>&1` |
| 2026-06-18 11:27:03 | allow | `-` | `railway list --json 2>&1` |
| 2026-06-18 11:27:08 | allow | `-` | `railway link 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a --environment production 2>&1; railway service link FOMS 2>&1; railway status 2>&1` |
| 2026-06-18 11:27:23 | allow | `-` | `railway link --help 2>&1` |
| 2026-06-18 11:27:27 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s FOMS 2>&1; railway status 2>&1; railway variables --json 2>&1 | python -c "import sys,json` |
| 2026-06-18 11:27:36 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s worker 2>&1; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.s` |
| 2026-06-18 11:27:36 | allow | `-` | `railway logs -n 50 --filter "554075" 2>&1 | Select-Object -Last 15` |
| 2026-06-18 11:29:12 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s web 2>&1; railway variable set "CHANNEL_GROUP_MEASUREMENT=209990" 2>&1; railway variables ` |
| 2026-06-18 11:29:12 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s WORKER 2>&1; railway variable set "CHANNEL_GROUP_MEASUREMENT=209990" 2>&1; railway variabl` |
| 2026-06-18 11:29:13 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s FOMS 2>&1; railway variable set "CHANNEL_GROUP_MEASUREMENT=209990" 2>&1; railway variables` |
| 2026-06-18 11:29:14 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s worker 2>&1; railway variable set "CHANNEL_GROUP_MEASUREMENT=209990" 2>&1; railway variabl` |
| 2026-06-18 11:29:44 | allow | `-` | `railway variable --help 2>&1` |
| 2026-06-18 11:29:44 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s web 2>&1; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.stdi` |
| 2026-06-18 11:29:51 | allow | `-` | `railway variable set --help 2>&1` |
| 2026-06-18 11:29:51 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s FOMS 2>&1; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.std` |
| 2026-06-18 11:29:58 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s web 2>&1; railway restart 2>&1; railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e pr` |
| 2026-06-18 11:29:59 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s FOMS 2>&1; railway restart 2>&1; railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e p` |
| 2026-06-18 11:30:05 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s web 2>&1; railway restart --yes 2>&1; railway link -p cbe0af66-875b-460c-88f6-780dd705f45c` |
| 2026-06-18 11:34:13 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s web 2>&1; railway environment config --json 2>&1 | python -c "import sys,json; c=json.load` |
| 2026-06-18 11:34:14 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s FOMS 2>&1; railway environment config --json 2>&1 | python -c "import sys,json; c=json.loa` |
| 2026-06-18 11:34:15 | allow | `-` | `python -c "import urllib.request, json; r=urllib.request.urlopen('https://lahom-production.up.railway.app/api/channel/health', timeout=20); d=json.loads(r.read(` |
| 2026-06-18 11:34:20 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s web 2>&1; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.stdi` |
| 2026-06-18 11:34:21 | allow | `-` | `railway link -p cbe0af66-875b-460c-88f6-780dd705f45c -e production -s WORKER 2>&1; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.s` |
| 2026-06-18 11:34:22 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s FOMS 2>&1; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.std` |
| 2026-06-18 11:34:22 | allow | `-` | `railway link -p 65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a -e production -s worker 2>&1; railway variables --json 2>&1 | python -c "import sys,json; d=json.load(sys.s` |
| 2026-06-18 11:34:29 | allow | `-` | `railway whoami 2>&1` |
| 2026-06-18 11:34:42 | allow | `-` | `python -c "import urllib.request, json; r=urllib.request.urlopen('https://lahom-dev.up.railway.app/api/channel/health', timeout=20); d=json.loads(r.read()); pri` |
| 2026-06-18 11:34:54 | allow | `-` | `if ($env:RAILWAY_TOKEN) { 'RAILWAY_TOKEN set' } else { 'RAILWAY_TOKEN not set' }; railway whoami 2>&1` |
| 2026-06-18 11:38:52 | allow | `-` | `git rev-parse production deploy origin/production origin/deploy 2>&1` |
| 2026-06-22 08:16:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 08:16:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git rev-parse production; git rev-parse origin/production; git log` |
| 2026-06-22 08:16:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin production; git rev-parse origin/production; git log --oneline origin/product` |
| 2026-06-22 08:16:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-remote origin refs/heads/production; git branch -vv` |
| 2026-06-22 08:16:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git update-ref refs/remotes/origin/production 1cd00528db21a1cc747095044d7c371545c2dd02` |
| 2026-06-22 08:25:07 | allow | `-` | `if (-not (Test-Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\js\drawing")) { New-Item -ItemType Directory -Path "c:\Users\USER\OneDri` |
| 2026-06-22 08:26:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_drawing_workbench` |
| 2026-06-22 08:26:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-22 08:31:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log --oneline -3 deploy; git log --oneline -3 origin/deploy 2>` |
| 2026-06-22 08:31:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff foms/web/drawing/workbench.py templates/drawing/partials/workbench_dashboard_body.htm` |
| 2026-06-22 08:31:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git add foms/web/drawing/workbench.py templates/drawing/partials/workbenc` |
| 2026-06-22 08:32:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F ".git\COMMIT_EDITMSG` |
| 2026-06-22 08:32:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 08:32:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy; git log --oneline -2 deploy; git status -sb` |
| 2026-06-22 08:39:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_mine_filter.p` |
| 2026-06-22 08:40:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_mine_filter.py tests/domains/test_erp_mine_only_js_con` |
| 2026-06-22 08:40:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-22 08:40:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-22 08:40:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_runtime_shell_js_contract.py tests/domains/test_erp_sh` |
| 2026-06-22 08:41:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py::test_construction_mobile` |
| 2026-06-22 08:41:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py tests/domains/test_erp_sh` |
| 2026-06-22 08:41:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest "tests/domains/test_erp_shell_fragment_contract.py::test_canonical_erp_paths_` |
| 2026-06-22 08:42:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_construc` |
| 2026-06-22 08:43:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log --oneline -3 deploy; git log --oneline -3 origin/deploy` |
| 2026-06-22 08:43:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat -- foms/ static/ templates/ tests/` |
| 2026-06-22 08:43:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff foms/web/orders/dashboard.py templates/partials/shared/layout_scripts.html | Select-O` |
| 2026-06-22 08:43:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/common/erp_mine_filter.py foms/api/measurement/routes.py foms/web/constr` |
| 2026-06-22 08:43:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F ".git\COMMIT_EDITMSG` |
| 2026-06-22 08:43:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 08:44:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy; git log --oneline -3 deploy; git status -sb` |
| 2026-06-22 08:48:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py::test_ptc_foms_service` |
| 2026-06-22 09:07:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_channel_push_messages.py -q; python -c "import app; print(` |
| 2026-06-22 09:08:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git log --oneline -5 deploy; git log --oneline -3 origin/deploy; git rev-list --co` |
| 2026-06-22 09:08:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat -- foms/ tests/ docs/plans/channeltalk_policy/; git diff foms/services/channel` |
| 2026-06-22 09:08:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/channel_policy.py tests/domains/test_channel_push_messages.py tests/cont` |
| 2026-06-22 09:08:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F ".git\COMMIT_EDITMSG` |
| 2026-06-22 09:08:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 09:09:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy; git log --oneline -2 deploy` |
| 2026-06-22 09:14:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git status -sb; git log --oneline -3 deploy; git log --oneline -3 production` |
| 2026-06-22 09:14:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy --ff-only` |
| 2026-06-22 09:14:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 09:15:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git ls-remote origin refs/heads/production; git rev-parse producti` |
| 2026-06-22 12:13:57 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-22 12:13:57 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-22 12:36:00 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-22 12:38:28 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 12:45:03 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 12:48:45 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-22 12:51:52 | allow | `-` | `echo "=== origin/production ==="; git log --oneline -5 origin/production; echo "=== origin/deploy ==="; git log --oneline -5 origin/deploy; echo "=== local prod` |
| 2026-06-22 12:52:36 | allow | `-` | `git --no-pager diff -- static/js/measurement/regional-shipping-export.js templates/measurement/regional_dashboard.html` |
| 2026-06-22 14:58:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline HEAD; git log -1 --oneline origin/production; git merge-base HEAD origin/` |
| 2026-06-22 14:58:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge origin/deploy -m "chore: production을 deploy 최신(7a3dd279)과 동기화"` |
| 2026-06-22 14:58:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-22 14:59:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git log -2 --oneline` |
| 2026-06-23 09:38:30 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-23 09:38:45 | allow | `-` | `python -m pytest tests/domains/test_wdc_spec_field_presets.py tests/domains/test_erp_wdc_estimate_sync.py -q 2>&1 | Select-Object -Last 40` |
| 2026-06-23 09:39:06 | allow | `-` | `python -m pytest tests/domains/test_wdcalculator_product_settings.py -q 2>&1 | Select-Object -Last 25` |
| 2026-06-23 09:39:52 | allow | `-` | `python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 30` |
| 2026-06-23 09:43:13 | allow | `-` | `python -m pytest tests/domains/test_wdc_spec_presets_settings_ui.py -q 2>&1 | Select-Object -Last 30` |
| 2026-06-23 09:43:28 | allow | `-` | `python -m pytest tests/domains/test_wdcalculator_product_settings.py -q 2>&1 | Select-Object -Last 8; python tools/perf/perf_scan.py --guard 2>&1 | Select-Objec` |
| 2026-06-23 09:51:34 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-23 09:51:48 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-23 09:51:55 | allow | `-` | `python -m pytest tests/performance/test_page_local_defer_contract.py tests/domains/test_erp_order_shared_form_scripts.py -q 2>&1 | Select-Object -Last 30` |
| 2026-06-23 09:53:37 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py -q 2>&1 | Select-Object -Last 40` |
| 2026-06-23 09:53:50 | allow | `-` | `python -m pytest tests/domains/test_wdc_spec_field_presets.py tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_wdc_spec_presets_settings_ui.py tes` |
| 2026-06-23 09:56:08 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_erp_order_shared_form_scripts.py -q 2>&1 | Select-Object -Last 20; python tools/p` |
| 2026-06-23 10:01:03 | allow | `-` | `python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_erp_order_shared_form_scripts.py -q 2` |
| 2026-06-23 10:01:37 | allow | `-` | `python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 1; python -m pytest tests/domains/test_erp_orders_structured_put.py -q 2>&1 | Select-Object -` |
| 2026-06-23 10:04:03 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/performance/test_page_local_defer_contract.py -q 2>&1 | Select-Object -Last 20; python tools/p` |
| 2026-06-23 10:04:25 | allow | `-` | `python -m pytest tests/domains/test_wdc_spec_field_presets.py tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_wdc_spec_presets_settings_ui.py tes` |
| 2026-06-23 10:11:37 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_p0_01_erp_mobile_v2_cohort.py -q 2>&1 | Select-Object -Last 15` |
| 2026-06-23 10:11:58 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-23 10:53:11 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_erp_spec_calc_followup.py tests/domains/test_wdc_spec_field_presets.py -q 2>&1 | ` |
| 2026-06-23 10:53:12 | allow | `-` | `python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 15` |
| 2026-06-23 10:53:31 | allow | `-` | `python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 30` |
| 2026-06-23 10:53:45 | allow | `-` | `python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_wdc_spec_presets_settings_ui.py tests/performance/test_perf_regression_guard.py ` |
| 2026-06-23 10:56:13 | allow | `-` | `python -m pytest tests/domains/test_wdc_spec_presets_settings_ui.py tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_spec_calc_phase3.py -q 2` |
| 2026-06-23 11:04:38 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 45` |
| 2026-06-23 14:59:59 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_wdc_spec_presets_settings_ui.py -q 2` |
| 2026-06-23 15:00:08 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_wdc_spec_presets_settings_ui.py -q` |
| 2026-06-23 15:00:38 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-23 15:00:39 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-23 15:00:58 | allow | `-` | `python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_mobile_layout_and_shipment.py tests/domains/test_p0_01_erp_mobile_v2` |
| 2026-06-23 15:03:22 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-23 15:19:50 | allow | `-` | `git ls-remote origin refs/heads/deploy refs/heads/production; echo "==== my commit ===="; git rev-parse bafb47d3; echo "==== parent of my commit ===="; git rev-` |
| 2026-06-23 15:20:35 | allow | `-` | `git ls-remote origin refs/heads/deploy refs/heads/production` |
| 2026-06-23 15:28:31 | allow | `-` | `echo "==== bafb47d3 ancestry (top 12) ===="; git log --oneline -12 bafb47d3; echo "==== is 1cd00528 (production hotfix line) ancestor of bafb47d3? (0=yes) ===="` |
| 2026-06-23 15:29:48 | allow | `-` | `echo "==== 5393d94a parents (merge?) ===="; git rev-list --parents -n 1 5393d94a; echo "==== 1cd00528 subject (last prod hotfix) ===="; git log -1 --oneline 1cd` |
| 2026-06-23 15:33:31 | allow | `-` | `echo "==== origin/production reflog (transitions) ===="; git reflog show origin/production 2>&1 | Select-Object -First 12; echo "==== what sits ON TOP of 1cd005` |
| 2026-06-23 15:35:17 | allow | `-` | `echo "==== 78ab25e4 (ERP 즉시견적) parent ===="; git log -1 --oneline 78ab25e4^; echo "==== ERP feature commits to remove (3) ===="; git log --oneline 5393d94a..baf` |
| 2026-06-23 15:39:26 | allow | `-` | `echo "==== remote tips now ===="; git ls-remote origin refs/heads/production refs/heads/deploy; echo "==== ERP 3 commits preserved on deploy? ===="; git merge-b` |
| 2026-06-23 15:41:37 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-06-23 15:42:34 | allow | `-` | `python tools/harness/build_context_bundle.py --all 2>&1 | Select-Object -Last 3; echo "==== changed bundles ===="; git status -sb -- docs/harness/bundles/` |
| 2026-06-23 15:42:57 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 25` |
| 2026-06-23 15:45:59 | allow | `-` | `railway status 2>&1; echo "==== LIST ===="; railway list --json 2>&1 | Select-Object -First 60` |
| 2026-06-23 15:47:31 | allow | `-` | `$urls = @('https://lahom-dev.up.railway.app/static/js/orders/erp-spec-calc.js','https://lahom-dev.up.railway.app/static/js/orders/erp-spec-picker.js','https://l` |
| 2026-06-23 15:51:17 | allow | `-` | `$base='https://lahom-dev.up.railway.app/static/js/orders'; $r=Get-Random; $calc=(Invoke-WebRequest "$base/erp-spec-calc.js?nc=$r" -UseBasicParsing -TimeoutSec 3` |
| 2026-06-23 15:54:25 | allow | `-` | `echo "==== erp_order_js.html version string across ERP commits ===="; foreach ($c in @('78ab25e4','a9c277af','bafb47d3','f85fed2d')) { $line = (git show "${c}:t` |
| 2026-06-23 15:58:35 | allow | `-` | `$base='https://lahom-dev.up.railway.app/static/js/orders'; $r=Get-Random; $resp=Invoke-WebRequest "$base/erp-order-shared.js?nc=$r" -UseBasicParsing -TimeoutSec` |
| 2026-06-23 16:03:22 | allow | `-` | `echo "==== files changed in bafb47d3 (phase3 redesign) ===="; git show --stat --oneline bafb47d3 | Select-String '\.(css|js|html)'; echo "==== was foms-form-fie` |
| 2026-06-23 16:09:04 | allow | `-` | `python -c "import app; print('APP_OK')"; echo "==== targeted tests ===="; python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_s` |
| 2026-06-23 16:09:46 | allow | `-` | `python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 25` |
| 2026-06-23 16:09:59 | allow | `-` | `git --no-pager diff --stat; echo "==== full diff ===="; git --no-pager diff` |
| 2026-06-23 16:10:32 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 45` |
| 2026-06-23 16:12:40 | allow | `-` | `$u='https://lahom-dev.up.railway.app/static/css/foundation/foms-mobile-surfaces.css'; $ok=$false; for($i=1;$i -le 18;$i++){ try{ $c=(Invoke-WebRequest "$u?nc=$(` |
| 2026-06-23 16:19:15 | allow | `-` | `$u='https://lahom-dev.up.railway.app/static/css/foundation/foms-mobile-surfaces.css'; $ok=$false; for($i=1;$i -le 12;$i++){ try{ $c=(Invoke-WebRequest "$u?nc=$(` |
| 2026-06-23 16:23:46 | allow | `-` | `$r=Get-Random; $surf=(Invoke-WebRequest "https://lahom-dev.up.railway.app/static/css/foundation/foms-mobile-surfaces.css?nc=$r" -UseBasicParsing -TimeoutSec 25)` |
| 2026-06-23 16:33:11 | allow | `-` | `node --check static/js/orders/erp-spec-picker.js; if($?){"picker.js: SYNTAX OK"}; node --check static/js/orders/erp-spec-calc.js; if($?){"calc.js: SYNTAX OK"}; ` |
| 2026-06-23 16:37:50 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_spec_calc_phase3.py -q 2>&1 | Select-Object -Last 20` |
| 2026-06-23 16:38:26 | allow | `-` | `python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 6; echo "==== smoke ===="; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | S` |
| 2026-06-23 16:41:51 | allow | `-` | `$u='https://lahom-dev.up.railway.app/static/js/orders/erp-spec-picker.js'; $ok=$false; for($i=1;$i -le 14;$i++){ try{ $c=(Invoke-WebRequest "$u?nc=$(Get-Random)` |
| 2026-06-23 16:46:33 | allow | `-` | `$u='https://lahom-dev.up.railway.app/static/js/orders/erp-spec-picker.js'; $c=(Invoke-WebRequest "$u?nc=$(Get-Random)" -UseBasicParsing -TimeoutSec 25).Content;` |
| 2026-06-23 16:46:44 | allow | `-` | `$u='https://lahom-dev.up.railway.app/static/js/orders/erp-spec-picker.js'; $c=(Invoke-WebRequest "${u}?nc=$(Get-Random)" -UseBasicParsing -TimeoutSec 25).Conten` |
| 2026-06-23 16:49:04 | allow | `-` | `(Get-Content -Raw 'templates/orders/partials/erp_order_js.html') -replace "erp-spec-calc\.js'\) }}\?v=20260623c", "erp-spec-calc.js') }}?v=20260623d" | Set-Cont` |
| 2026-06-23 16:49:34 | allow | `-` | `$files=@('static/css/foundation/foms-mobile-surfaces.css','templates/partials/shared/layout_head.html','templates/orders/wizard/wizard_shell.html','tests/domain` |
| 2026-06-23 16:50:05 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; node --check static/js/orders/erp-spec-picker.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py ` |
| 2026-06-23 16:50:44 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; node --check static/js/orders/erp-spec-picker.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py ` |
| 2026-06-23 16:51:14 | allow | `-` | `python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 8; echo "==== APP_OK ===="; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last` |
| 2026-06-23 16:52:25 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; node --check static/js/orders/erp-spec-picker.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py ` |
| 2026-06-23 16:53:05 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; node --check static/js/orders/erp-spec-picker.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py ` |
| 2026-06-23 16:53:49 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; node --check static/js/orders/erp-spec-picker.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py ` |
| 2026-06-23 16:54:15 | allow | `-` | `python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 8; echo "==== APP_OK ===="; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last` |
| 2026-06-23 16:55:27 | allow | `-` | `git --no-pager diff --stat; git --no-pager diff -- static/js/orders/erp-spec-calc.js static/css/components/foms-form-field.css templates/orders/partials/erp_ord` |
| 2026-06-23 16:55:28 | allow | `-` | `git --no-pager log -5 --oneline` |
| 2026-06-23 16:56:08 | allow | `-` | `$calc='https://lahom-dev.up.railway.app/static/js/orders/erp-spec-calc.js'; $surf='https://lahom-dev.up.railway.app/static/css/foundation/foms-mobile-surfaces.c` |
| 2026-06-23 17:05:43 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; node --check static/js/orders/erp-spec-picker.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py ` |
| 2026-06-23 17:06:33 | allow | `-` | `python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 8; echo "==== APP_OK ===="; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last` |
| 2026-06-23 20:20:25 | allow | `-` | `git --no-pager diff --stat; git --no-pager diff -- static/css/orders/erp-spec-calc.css templates/orders/partials/erp_order_js.html tests/domains/test_erp_spec_c` |
| 2026-06-23 20:20:25 | allow | `-` | `git --no-pager log -5 --oneline` |
| 2026-06-23 20:21:13 | allow | `-` | `$css='https://lahom-dev.up.railway.app/static/css/orders/erp-spec-calc.css'; $ok=$false; for($i=1;$i -le 18;$i++){ $body=''; try{ $body=(Invoke-WebRequest "${cs` |
| 2026-06-24 09:22:39 | allow | `-` | `$files=@('static/css/foundation/foms-mobile-surfaces.css','templates/partials/shared/layout_head.html','templates/orders/wizard/wizard_shell.html','tests/domain` |
| 2026-06-24 09:23:18 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_spec_calc_phase3.py tests/d` |
| 2026-06-24 09:23:45 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-24 09:23:53 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-24 09:25:27 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_order_shared_form_scripts.py tests/visual/test_p1_mockup_structure.py -q` |
| 2026-06-24 09:27:32 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_spec_calc_phase3.py -q` |
| 2026-06-24 09:27:45 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-24 09:29:46 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-24 09:47:14 | allow | `-` | `node --check static/js/orders/erp-spec-calc.js; python -m pytest tests/domains/test_erp_spec_calc_followup.py tests/domains/test_erp_spec_calc_phase3.py -q` |
| 2026-06-24 09:47:27 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-24 09:47:35 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-24 09:56:43 | allow | `-` | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-24 10:23:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node "tests\support\wdcalculator_sidebar_delete_contract_node_checks.js"` |
| 2026-06-24 10:23:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest "tests\contracts\wdcalculator\test_estimate_lifecycle_contracts.py::test_esti` |
| 2026-06-24 10:23:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-06-24 10:24:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-24 10:27:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-06-24 10:27:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff; git diff --cached` |
| 2026-06-24 10:27:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -5 --oneline; git branch --show-current` |
| 2026-06-24 10:27:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/js/wdcalculator/estimate-lifecycle.js" "templates/wdcalculator/partials/wdcalc` |
| 2026-06-24 16:06:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-24 16:06:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git ls-remote origin refs/heads/production refs/heads/deploy; git ` |
| 2026-06-24 18:41:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_spec_calc_phase3.py -q; python tools/perf/perf_scan.py` |
| 2026-06-24 18:44:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_spec_calc_phase3.py -q; python tools/perf/perf_scan.py` |
| 2026-06-24 18:49:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat; git log -3 --oneline` |
| 2026-06-24 18:50:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_wdc_estimate_sync.py::test_unmatch_order_removes_match` |
| 2026-06-24 18:50:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-spec-calc.js tests/domains/test_erp_spec_calc_phase3.py foms/api/` |
| 2026-06-24 18:50:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-24 18:51:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-06-24 18:55:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log origin/production..origin/deploy --oneline; git log origin/deploy..o` |
| 2026-06-24 18:55:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge origin/deploy -m "merge: deploy` |
| 2026-06-24 18:56:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-06-24 19:02:34 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-24 19:02:34 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_erp_order_shared_form_scripts.py -q` |
| 2026-06-24 19:02:35 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-24 19:02:54 | allow | `-` | `python tools/harness/task_classifier.py --profile auto --prompt "erporder 자동 계산기능은 발주사 라홈일 때만 작동" --json` |
| 2026-06-24 19:03:09 | allow | `-` | `python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_estimate_service.py -q` |
| 2026-06-24 19:06:29 | allow | `-` | `python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_estimate_service.py -q` |
| 2026-06-24 19:06:29 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-24 19:06:29 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_erp_order_shared_form_scripts.py -q` |
| 2026-06-24 19:06:29 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-24 19:07:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git log -5 --oneline -- static/js/orders/erp-spec-calc.js; git diff -- sta` |
| 2026-06-24 19:10:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_erp_spec_calc_` |
| 2026-06-24 19:10:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_erp_spec_calc_` |
| 2026-06-24 19:11:57 | allow | `-` | `python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_estimate_service.py -q` |
| 2026-06-24 19:11:57 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-24 19:11:57 | allow | `-` | `python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_erp_order_shared_form_scripts.py -q` |
| 2026-06-24 19:12:21 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-24 19:14:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_wdc_estimate_sync.py tests/domains/test_erp_spec_calc_` |
| 2026-06-24 19:14:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff -- static/js/orders/erp-spec-calc.js foms/api/wdcalculator/blueprint` |
| 2026-06-24 19:16:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- static/js/orders/erp-order-shared.js templates/orders/partials/erp_order_js.html t` |
| 2026-06-24 19:20:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log --oneline -3 deploy; git diff --stat` |
| 2026-06-24 19:20:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff foms/api/wdcalculator/blueprint.py static/js/orders/erp-spec-calc.js static/js/orders` |
| 2026-06-24 19:20:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_spec_calc_phase3.py tests/domains/test_erp_wdc_estimat` |
| 2026-06-24 19:20:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff static/js/orders/erp-spec-calc.js | Select-String "^\+|^\-" | Select-Object -First 60` |
| 2026-06-24 19:21:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status -sb` |
| 2026-06-24 19:26:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-24 19:27:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git ls-remote origin refs/heads/production refs/heads/deploy; git ` |
| 2026-06-25 08:08:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/visual/test_p1_mockup_structure.py::test_p1_dashboard_tower_mobile_widt` |
| 2026-06-25 08:14:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff; git diff --staged` |
| 2026-06-25 08:14:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-06-25 08:14:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -5 --oneline; git branch --show-current` |
| 2026-06-25 08:14:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/contexts/orders/dashboard-control-tower.css tests/visual/test_p1_mockup_str` |
| 2026-06-25 08:14:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-25 08:14:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_shared_erp_order_js` |
| 2026-06-25 08:14:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- static/js/orders/erp-order-shared.js tests/domains/test_erp_order_shared_form_scri` |
| 2026-06-25 08:14:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy; git status -sb` |
| 2026-06-25 08:16:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_shared_erp_order_js` |
| 2026-06-25 08:20:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log --oneline -3 deploy; git log --oneline -3 origin/deploy; git diff --st` |
| 2026-06-25 08:20:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff static/js/orders/erp-order-shared.js tests/domains/test_erp_order_shared_form_scripts` |
| 2026-06-25 08:20:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q -k "conver` |
| 2026-06-25 08:26:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-25 08:27:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git ls-remote origin refs/heads/production refs/heads/deploy; git ` |
| 2026-06-25 09:29:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_dashboard_search_service.py tests/domains/test_unified` |
| 2026-06-25 09:29:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-25 09:29:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-06-25 09:33:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff; git diff --cached` |
| 2026-06-25 09:33:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-06-25 09:33:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -5 --oneline` |
| 2026-06-25 09:33:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-25 09:33:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_dashboard_search.py foms/services/foms_unified_search.py foms/web/or` |
| 2026-06-25 09:33:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy; git status -sb` |
| 2026-06-25 09:38:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_search_overlay.py::test_unified_search_matches_struct` |
| 2026-06-25 09:38:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-25 09:39:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/foms_unified_search.py; git commit --trailer "Co-authored-by: Cursor <cu` |
| 2026-06-25 09:48:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git fetch origin; git log --oneline origin/production..origin/deploy -15; git ` |
| 2026-06-25 09:54:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse origin/production origin/deploy; git merge-base origin/production origin/deploy` |
| 2026-06-25 09:56:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git rev-parse origin/production origin/deploy; git log --oneline origin/prod` |
| 2026-06-25 09:57:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-25 09:58:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy:production; git rev-parse origin/production origin/deploy` |
| 2026-06-25 10:01:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git status -sb; git log --oneline -3 deploy; git log --oneline -3 origin/dep` |
| 2026-06-25 10:01:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline production..deploy; git diff docs/AI_CHANGELOG.md` |
| 2026-06-25 10:01:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/EDIT_LO` |
