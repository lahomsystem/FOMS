# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-03-24 16:03:29 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -10 -- templates/erp_as_dashboard.html` |
| 2026-03-24 16:03:33 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 9df3a376 -- templates/erp_as_dashboard.html | grep "^[+-]" | grep -v "^---\|^+++" |` |
| 2026-03-24 16:03:39 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff e6799042~1 e6799042 -- templates/erp_as_dashboard.html | grep "^[+-]" | grep -v "^-` |
| 2026-03-24 16:03:45 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 3c80c0cb -- apps/api/orders.py | grep "^[+-]" | grep -v "^---\|^+++" | grep -i "sco` |
| 2026-03-24 16:03:50 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show cc47e315 -- apps/api/orders.py | grep "score_text\|duration\|distance_km\|route_ite` |
| 2026-03-24 16:04:16 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 6fedefe3 --stat` |
| 2026-03-24 16:04:26 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 6fedefe3 -- apps/api/erp_map.py | grep "^[+-]" | grep -v "^---\|^+++" | grep -i "ca` |
| 2026-03-24 16:04:32 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline --all -- foms_address_converter.py && echo "---" && git log --oneline --al` |
| 2026-03-24 16:05:18 | allow | `-` | `grep -n "reset_order_geocode\|geocode_status\|lat.*=.*None\|lng.*=.*None" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/api/erp_orders_struc` |
| 2026-03-24 16:05:19 | allow | `-` | `grep -n "def reset_order_geocode\|reset_order_geocode" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/services/order_geocode.py" | head -20` |
| 2026-03-24 16:06:39 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 6fedefe3 -- apps/api/erp_orders_structured.py | grep "^[+-]" | grep -v "^---\|^+++"` |
| 2026-03-24 16:17:16 | allow | `-` | `grep -n "lat\|lng\|geocode" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/models.py" | grep -i "lat\|lng\|geocode" | head -20` |
| 2026-03-24 16:17:49 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show e6799042 -- templates/erp_as_dashboard.html | grep "^[+-]" | grep -v "^---\|^+++" |` |
| 2026-03-24 16:17:56 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 36570950 -- apps/api/orders.py | grep "^[+-]" | grep -v "^---\|^+++" | head -60` |
| 2026-03-24 16:18:27 | allow | `-` | `grep -n "def.*as.*page\|address\|structured_data\|r\.address" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/erp_as_page.py" | head -30` |
| 2026-03-24 16:18:37 | allow | `-` | `grep -n "\.address\b\|address.*label\|display.*address\|r\.address" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/erp_as_page.py" | tail -20` |
| 2026-03-24 16:18:41 | allow | `-` | `grep -n "address\s*=\|\.address\s*=\|'address'" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/erp_as_page.py" | grep -v "def \|_display\|add` |
| 2026-03-24 16:18:48 | allow | `-` | `grep -n "def apply_erp_display_fields\|address" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/services/erp_order_detail.py" | head -20` |
| 2026-03-24 16:18:49 | allow | `-` | `grep -rn "def apply_erp_display_fields" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/" 2>/dev/null | head -5` |
| 2026-03-24 16:20:52 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && grep -rn "def apply_erp_display_fields" . 2>/dev/null | head -5` |
| 2026-03-24 16:23:35 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -5` |
| 2026-03-24 16:24:31 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git push origin deploy` |
| 2026-03-24 16:25:47 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git stash && git checkout production && git merge deploy --no-edit && git push origin produc` |
| 2026-03-24 16:37:49 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c " from app import app with app.app_context(): from foms_address_converter import F` |
| 2026-03-24 16:39:29 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-24 16:41:22 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git push origin deploy && git stash && git checkout production && git merge deploy --no-edit` |
| 2026-03-24 16:56:38 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-24 17:00:20 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git push origin deploy && git stash && git checkout production && git merge deploy --no-edit` |
| 2026-03-24 17:14:04 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git add services/erp_order_detail.py templates/partials/erp_dashboard_scripts_detail_dom.htm` |
| 2026-03-24 22:07:52 | allow | `-` | `rm "c:/tmp/commit_msg.txt"` |
| 2026-03-24 22:19:26 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git add templates/erp_as_dashboard.html && git commit -F "c:/tmp/commit_msg.txt" && rm "c:/t` |
| 2026-03-24 22:32:06 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git status && git diff --stat` |
| 2026-03-24 22:32:30 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -5` |
| 2026-03-24 22:32:43 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff services/order_geocode.py` |
| 2026-03-24 22:33:04 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git push origin deploy` |
| 2026-03-24 22:33:17 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git checkout production && git merge deploy --no-edit && git push origin production && git c` |
| 2026-03-24 23:03:05 | allow | `-` | `powershell -NoProfile -Command "(Get-Content -Path 'c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py' | Measure-Object -Line).Lines"` |
| 2026-03-24 23:05:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-24 23:05:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add ".cursor/agents/grand-develop-master.md" ".cursor/agents/GDM_EXECUTION_PLAN.md" ".curs` |
| 2026-03-24 23:06:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -f ".cursor/rules/14-incident-rca.mdc"; git status` |
| 2026-03-24 23:06:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt; if (Test-Path commit_msg.txt) { Re` |
| 2026-03-24 23:16:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK'); from services.order_geocode import apply_erp_beta_site` |
| 2026-03-24 23:18:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import copy from types import SimpleNamespace from services.order_geocode import r` |
| 2026-03-24 23:18:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-24 23:18:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git status -sb` |
| 2026-03-24 23:18:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "apps/order_edit.py" "services/order_geocode.py"; git commit --trailer "Made-with: Cur` |
| 2026-03-24 23:28:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; from services.order_geocode import reset_order_geocode_on_address_chang` |
| 2026-03-24 23:28:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "apps/order_edit.py" "services/order_geocode.py"; git commit --trailer "Made-with: Cur` |
| 2026-03-24 23:36:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-24 23:36:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "templates/partials/erp_beta_js.html" "docs/evolution/ERP_BETA_AS_RECEIVED_SAVE_TRANSI` |
| 2026-03-25 08:14:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git branch -a; git log -1 --oneline deploy; git log -1 --oneline origin/prod` |
| 2026-03-25 08:14:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline origin/production; git merge-base deploy origin/production; git rev-list ` |
| 2026-03-25 08:14:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production` |
| 2026-03-25 08:15:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base --is-ancestor production deploy; echo "exit=$LASTEXITCODE"` |
| 2026-03-25 08:15:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge deploy --ff-only; git push origin production; if (Test-Path commit_msg.txt) { Remove` |
| 2026-03-25 08:26:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git branch --show-current` |
| 2026-03-25 08:49:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 08:50:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "templates/partials/erp_beta_js.html"; git commit --trailer "Made-with: Cursor" -F "_c` |
| 2026-03-25 08:50:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-25 09:10:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git branch -a; git status -sb` |
| 2026-03-25 09:10:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production` |
| 2026-03-25 09:10:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge origin/deploy -m "merge: deploy -> production (ERP Beta shipment preserve 등)"` |
| 2026-03-25 09:10:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-25 09:10:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git log -1 --oneline production` |
| 2026-03-25 09:39:05 | allow | `-` | `ls "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/docs/plans/"` |
| 2026-03-25 10:21:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 10:21:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "apps/api/orders.py" "static/css/erp-pro.css" "templates/erp_as_dashboard.html"; git c` |
| 2026-03-25 10:30:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 10:31:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/css/erp-pro.css" "templates/erp_as_dashboard.html" "templates/layout.html"; gi` |
| 2026-03-25 10:36:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git checkout production; git pull origin production; git merge origin/deploy` |
| 2026-03-25 11:33:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 11:33:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/js/measurement-image-export.js" "templates/erp_measurement_dashboard.html"; gi` |
| 2026-03-25 11:45:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 11:47:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from PIL import Image; import os; p='static/images/pay-coin.png'; im=Image.open(p);` |
| 2026-03-25 11:54:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-03-25 11:54:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/erp_template_filters.py static/js/erp-table-image-export-helpers.js static/js` |
| 2026-03-25 11:54:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg_deploy.txt; Remove-Item commit_msg_depl` |
| 2026-03-25 12:31:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from PIL import Image import os for base in ('pay-coin', 'pay-bill'): p = os.path.` |
| 2026-03-25 12:32:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 12:33:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-03-25 12:34:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff static/css/erp-pro.css static/js/erp-table-image-export-helpers.js templates/erp_meas` |
| 2026-03-25 12:34:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 12:36:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-25 12:36:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/erp_template_filters.py static/css/erp-pro.css static/js/erp-table-image-expo` |
| 2026-03-25 12:41:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git branch -a; git log -1 --oneline deploy; git log -1 --oneline origin/prod` |
| 2026-03-25 12:42:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy -m "merge: deploy into p` |
| 2026-03-25 12:51:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 12:59:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 13:01:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 13:04:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -a` |
| 2026-03-25 13:05:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/js/erp/measurement.js" "static/js/erp/measurement-manual-rows.js" "templates/e` |
| 2026-03-25 13:05:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg_foms.txt` |
| 2026-03-25 13:05:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git merge production -m "merge: production into deploy (실측 수동 행)"; git pu` |
| 2026-03-25 13:27:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 13:29:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 13:30:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-25 13:31:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-03-25 13:31:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/js/erp-table-image-export-helpers.js" "static/js/erp/measurement-manual-rows.j` |
| 2026-03-25 13:31:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git merge production; git push origin deploy; git checkout production; gi` |
| 2026-03-25 14:05:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-03-25 14:05:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "templates/erp_measurement_dashboard.html" "docs/plans/2026-03-25-measurement-save-pro` |
| 2026-03-25 14:05:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git merge production; git push origin deploy; git checkout production; gi` |
| 2026-03-25 14:19:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD~1..HEAD static/js/measurement-image-export.js static/js/erp-table-image-export-h` |
| 2026-03-25 14:19:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -3 --oneline` |
| 2026-03-25 14:19:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 72bd2c75 --stat` |
| 2026-03-25 14:22:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; grep -rn "erp-table-image-export-helpers.js" templates/` |
| 2026-03-25 14:23:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-25 14:23:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rm static/js/erp-table-image-export-helpers.js; git add static/css/erp-pro.css static/js/m` |
| 2026-03-25 14:24:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git checkout deploy; git merge production; git push origin deploy;` |
| 2026-03-25 14:25:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-26 08:52:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-26 09:37:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current; git remote -v` |
| 2026-03-26 09:38:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-26 09:38:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/erp_template_filters.py static/js/erp/common_utils.js templates/erp_drawing_w` |
| 2026-03-26 09:39:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-26 09:39:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy -m "merge: deploy -> pro` |
| 2026-03-26 11:07:25 | allow | `-` | `wc -l c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/script.js c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/css/erp` |
| 2026-03-26 11:07:31 | allow | `-` | `find c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates -name "*.html" | xargs wc -l 2>/dev/null | sort -rn | head -20` |
| 2026-03-26 11:07:41 | allow | `-` | `wc -l c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/erp/*.js 2>/dev/null; echo "---"; wc -l c:/Users/USER/OneDrive/Desktop/SY/program/la` |
| 2026-03-26 12:40:11 | allow | `-` | `flask db revision --autogenerate -m "Add ChannelTalk Phase 0 models"` |
| 2026-03-26 12:40:35 | allow | `-` | `$env:FLASK_APP="app.py"; flask db revision --autogenerate -m "Add ChannelTalk Phase 0 models"` |
| 2026-03-26 12:40:50 | allow | `-` | `alembic revision -m "Add ChannelTalk Phase 0 models"` |
| 2026-03-26 12:41:47 | allow | `-` | `alembic upgrade head` |
| 2026-03-26 12:42:32 | allow | `-` | `$env:FLASK_APP="app.py"; python -c "import app; print('APP_OK')"` |
| 2026-03-26 12:44:32 | allow | `-` | `ls services/channel_delivery.py` |
| 2026-03-26 12:49:24 | allow | `-` | `ls tests` |
| 2026-03-26 12:49:38 | allow | `-` | `mkdir -p tests/fixtures/channeltalk` |
| 2026-03-26 12:50:01 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-26 12:51:15 | allow | `-` | `python scripts\test_migration.py` |
| 2026-03-26 12:51:48 | allow | `-` | `pytest tests/test_channel_integration_smoke.py` |
| 2026-03-26 12:54:31 | allow | `-` | `mkdir -p docs/plans/channeltalk_policy` |
| 2026-03-26 12:59:10 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-26 12:59:25 | allow | `-` | `pytest tests/test_channel_integration_smoke.py` |
| 2026-03-26 13:03:50 | allow | `-` | `pytest tests/test_channel_security.py -v` |
| 2026-03-26 13:04:27 | allow | `-` | `pytest tests/test_channel_security.py -v` |
| 2026-03-26 13:04:42 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-26 13:10:15 | allow | `-` | `pytest tests/test_channel_quick_actions.py -v` |
| 2026-03-26 13:10:59 | allow | `-` | `pytest tests/test_channel_quick_actions.py -v` |
| 2026-03-26 13:11:24 | allow | `-` | `pytest tests/test_channel_quick_actions.py -v` |
| 2026-03-26 13:12:23 | allow | `-` | `pytest tests/test_channel_quick_actions.py -v` |
| 2026-03-26 13:13:12 | allow | `-` | `pytest tests/test_channel_quick_actions.py -v` |
| 2026-03-26 13:28:47 | allow | `-` | `pytest tests/test_channel_webhooks.py -v` |
| 2026-03-26 13:29:22 | allow | `-` | `pytest tests/test_channel_webhooks.py -v` |
| 2026-03-26 13:47:35 | allow | `-` | `pytest tests/test_channel_quick_actions.py` |
| 2026-03-26 13:48:00 | allow | `-` | `pytest tests/test_channel_webhooks.py tests/test_channel_inbound.py` |
| 2026-03-26 13:48:13 | allow | `-` | `pytest tests/test_channel_webhooks.py` |
| 2026-03-26 13:48:27 | allow | `-` | `pytest tests/test_erp_orders_structured.py` |
| 2026-03-26 13:50:12 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-26 13:50:48 | allow | `-` | `railway logs` |
| 2026-03-26 13:51:04 | allow | `-` | `railway logs -n 50` |
| 2026-03-26 13:51:17 | allow | `-` | `railway status` |
| 2026-03-26 13:51:31 | allow | `-` | `railway environment` |
| 2026-03-26 13:51:56 | allow | `-` | `railway environment list` |
| 2026-03-26 13:52:12 | allow | `-` | `curl -I https://lahom-dev.up.railway.app/erp/dashboard` |
| 2026-03-26 13:52:55 | allow | `-` | `alembic history` |
| 2026-03-26 13:53:13 | allow | `-` | `railway -h` |
| 2026-03-26 13:53:24 | allow | `-` | `railway env --help` |
| 2026-03-26 13:53:41 | allow | `-` | `python -c "import urllib.request; print(urllib.request.urlopen('https://lahom-dev.up.railway.app/erp/dashboard').getcode())"` |
| 2026-03-26 13:53:53 | allow | `-` | `curl -I https://lahom-dev.up.railway.app/erp/dashboard` |
| 2026-03-26 13:55:52 | allow | `-` | `ls -la migrations/versions` |
| 2026-03-26 13:56:02 | allow | `-` | `alembic upgrade head` |
| 2026-03-26 13:56:23 | allow | `-` | `cat Procfile` |
| 2026-03-26 13:57:19 | allow | `-` | `python -c "from db import get_engine; print(get_engine().url)"` |
| 2026-03-26 13:57:30 | allow | `-` | `python -c "from db import engine; print(engine.url)"` |
| 2026-03-26 13:57:40 | allow | `-` | `python -c "from db import engine; engine.connect()"` |
| 2026-03-26 13:58:27 | allow | `-` | `alembic upgrade head` |
| 2026-03-26 13:59:06 | allow | `-` | `alembic upgrade head` |
| 2026-03-26 14:00:55 | allow | `-` | `alembic upgrade head` |
| 2026-03-26 14:01:15 | allow | `-` | `alembic upgrade head` |
| 2026-03-26 14:01:56 | allow | `-` | `alembic upgrade head` |
| 2026-03-26 14:02:41 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-26 14:03:36 | allow | `-` | `railway logs -n 50` |
| 2026-03-26 14:03:48 | allow | `-` | `railway status` |
| 2026-03-26 14:04:00 | allow | `-` | `python -c "import urllib.request, urllib.error; try: print(urllib.request.urlopen('https://lahom-dev.up.railway.app/api/channel/health').getcode()) except urlli` |
| 2026-03-26 14:04:10 | allow | `-` | `railway logs -n 50` |
| 2026-03-26 14:04:22 | allow | `-` | `railway status` |
| 2026-03-26 14:04:42 | allow | `-` | `python -c "import urllib.request, urllib.error; try: print(urllib.request.urlopen('https://lahom-dev.up.railway.app/erp/dashboard').getcode()) except urllib.err` |
| 2026-03-26 14:27:11 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-26 14:27:24 | allow | `-` | `python -m pytest tests/test_channel_integration_smoke.py -v` |
| 2026-03-26 14:28:11 | allow | `-` | `python -m pytest tests/test_channel_integration_smoke.py -v` |
| 2026-03-26 14:40:49 | allow | `-` | `python -m pytest tests/test_channel_security.py -v` |
| 2026-03-26 22:24:24 | allow | `-` | `curl -s -X GET "http://localhost:8080/api/channel/health"` |
| 2026-03-26 22:24:32 | allow | `-` | `python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/api/channel/health').read().decode())"` |
| 2026-03-26 22:24:43 | allow | `-` | `python -c "import urllib.request; from urllib.error import HTTPError; try: print(urllib.request.urlopen('http://localhost:5000/api/channel/health').read().decod` |
| 2026-03-26 22:24:54 | allow | `-` | `python -c "import urllib.request, json; from urllib.error import HTTPError; try: resp = urllib.request.urlopen('http://localhost:5000/api/channel/health') print` |
| 2026-03-26 22:27:50 | allow | `-` | `python -m pytest tests/test_channel_quick_actions.py -v` |
| 2026-03-26 22:42:58 | allow | `-` | `python -c "import os; os.environ['FOMS_BASE_URL'] = 'https://test'; os.environ['CHANNEL_PUSH_ENABLED'] = 'true'; os.environ['REDIS_URL'] = 'redis://'; import ap` |
| 2026-03-26 22:43:19 | allow | `-` | `python -c "import os; os.environ['FOMS_BASE_URL'] = 'https://test'; os.environ['CHANNEL_PUSH_ENABLED'] = 'true'; os.environ['CHANNEL_COMMAND_ENABLED'] = 'true';` |
| 2026-03-26 22:47:41 | allow | `-` | `python -c "import os; os.environ['FOMS_BASE_URL'] = 'https://test'; os.environ['CHANNEL_PUSH_ENABLED'] = 'true'; os.environ['REDIS_URL'] = 'redis://'; import ap` |
| 2026-03-26 22:47:57 | allow | `-` | `python -c "import os; os.environ['FOMS_BASE_URL'] = 'https://test'; os.environ['CHANNEL_PUSH_ENABLED'] = 'true'; os.environ['CHANNEL_COMMAND_ENABLED'] = 'true';` |
| 2026-03-26 22:55:34 | allow | `-` | `curl -s https://lahom-dev.up.railway.app/api/channel/health` |
| 2026-03-26 22:56:27 | allow | `-` | `curl -m 10 -s https://lahom-dev.up.railway.app/api/channel/health` |
| 2026-03-26 22:56:56 | allow | `-` | `curl.exe -m 10 -s https://lahom-dev.up.railway.app/api/channel/health` |
| 2026-03-26 22:57:21 | allow | `-` | `curl.exe -m 10 -s https://lahom-dev.up.railway.app/api/channel/health | ConvertFrom-Json | ConvertTo-Json -Depth 5` |
| 2026-03-28 10:43:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-03-28 10:43:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" feat: 색상 필드 (SK) 기본값 자동 표시 비활성화 - erp_beta_js: 빈 색상 시 (SK) 대입 로직 주석 처리, 복구 가능 - add_order: ` |
| 2026-03-30 09:07:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from models import OrderEstimate; print('OrderEstimate loaded:', OrderEstimate.__ta` |
| 2026-03-30 09:07:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-30 09:07:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m alembic revision --autogenerate -m "add order_estimates table for estimate/contract"` |
| 2026-03-30 09:08:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from db import get_db, engine; from sqlalchemy import inspect; insp = inspect(engin` |
| 2026-03-30 09:08:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m alembic stamp 2fa571e611d9` |
| 2026-03-30 09:08:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-30 09:17:45 | allow | `-` | `dir "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\images" 2>$null; if (-not $?) { echo "Directory not found" }` |
| 2026-03-30 09:24:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-30 09:29:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-30 09:36:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-30 09:36:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5` |
| 2026-03-30 09:36:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A` |
| 2026-03-30 09:36:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-30 09:36:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-30 10:58:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/erp/estimate-preview.js; [System.IO.File]::WriteAllText("commit_msg.txt", "f` |
| 2026-03-30 11:12:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/erp/estimate-preview.js; [System.IO.File]::WriteAllText("commit_msg.txt", "f` |
| 2026-03-30 11:23:39 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static" -Recurse -Name | Select-String -Pattern "logo|haud|lahom" -SimpleMatch` |
| 2026-03-30 11:23:45 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static" -Directory -Name` |
| 2026-03-30 11:23:49 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\images" -Name` |
| 2026-03-30 11:24:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-03-30 11:24:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_estimate_pane.html templates/partials/erp_dashboard_styles.html` |
| 2026-03-30 11:24:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-30 11:24:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-30 11:28:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_estimate_pane.html static/js/erp/estimate-preview.js apps/api/e` |
| 2026-03-30 11:29:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt; git push origin deploy` |
| 2026-03-30 11:39:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_estimate_pane.html` |
| 2026-03-30 11:39:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt; git push origin deploy` |
| 2026-03-30 11:50:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "import app; print('APP_OK')"` |
| 2026-03-30 11:51:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git status` |
| 2026-03-30 11:51:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git diff --stat` |
| 2026-03-30 11:51:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git log --oneline -5` |
| 2026-03-30 11:51:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; [System.IO.File]::WriteAllText("commit_msg.txt", "fix: 퀘스트 승인 후 대시보드 파이프라인 타일 미이동 버그 수정`n`n근본` |
| 2026-03-30 11:52:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git add apps/api/erp_orders_as.py apps/api/erp_orders_construction.py apps/api/erp_orders_cs.` |
| 2026-03-30 11:52:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-30 11:52:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; Remove-Item commit_msg.txt ; git push origin deploy` |
| 2026-03-30 11:53:14 | allow | `-` | `ls "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\images\" 2>$null; if (-not $?) { echo "Directory not found" }` |
| 2026-03-30 11:56:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-03-30 11:56:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff templates/partials/erp_estimate_pane.html` |
| 2026-03-30 11:56:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_estimate_pane.html` |
| 2026-03-30 11:57:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt; Remove-Item commit_msg.txt` |
| 2026-03-30 11:57:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-30 12:40:38 | allow | `-` | `Copy-Item "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets\sign-e07d98d4-1326-409d-b2ee-3ceade236fe1.png" "c:\U` |
| 2026-03-30 12:40:45 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" -Recurse -Filter "sign-e07d98d4*.png" -ErrorAction SilentlyContinue | Select-O` |
| 2026-03-30 12:40:53 | allow | `-` | `Test-Path "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets"; if (Test-Path "C:\Users\USER\.cursor\projects\c-Us` |
| 2026-03-30 12:41:02 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets" -Filter "*sign*" -ErrorAction SilentlyContinue ` |
| 2026-03-30 12:41:06 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS" -Name | Select-Object -First 30` |
| 2026-03-30 12:41:09 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets" -Filter "*.png" | Select-Object Name` |
| 2026-03-30 12:41:14 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets" -Recurse -Include "*.png" -ErrorAction Silently` |
| 2026-03-30 12:41:34 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets\" -Recurse 2>$null | Select-Object Name, FullNam` |
| 2026-03-30 12:41:45 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\" -Recurse -Filter "*.png" 2>$null | Select-Object Name` |
| 2026-03-30 12:41:54 | allow | `-` | `Get-ChildItem "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\" -Recurse -Filter "sign*.png" 2>$null | Select-Object ` |
| 2026-03-30 12:42:00 | allow | `-` | `Get-ChildItem "C:\Users\USER\AppData\Roaming\Cursor\User\workspaceStorage\" -Recurse -Filter "sign*.png" -ErrorAction SilentlyContinue | Select-Object -First 5 ` |
| 2026-03-30 12:42:14 | allow | `-` | `Get-ChildItem "C:\Users\USER\AppData\Roaming\Cursor\User\workspaceStorage\533155fc540ce8fdfccbd97527acfc34\images\" -ErrorAction SilentlyContinue | Select-Objec` |
| 2026-03-30 12:42:22 | allow | `-` | `Get-ChildItem "C:\Users\USER\AppData\Roaming\Cursor\User\" -Recurse -Filter "*sign*" -ErrorAction SilentlyContinue | Select-Object -First 10 Name, FullName` |
| 2026-03-30 12:42:29 | allow | `-` | `Get-ChildItem "C:\Users\USER\AppData\Roaming\Cursor\User\" -Recurse -Filter "*e07d98d4*" -ErrorAction SilentlyContinue | Select-Object -First 10 Name, FullName` |
| 2026-03-30 12:43:43 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\" -Recurse -Filter "*.png" | Select-Object Name, FullName; echo "---"; Get-Chi` |
| 2026-03-30 12:43:50 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\" -Recurse -Include "*.png","*.jpg","*.svg","*.gif" -ErrorAction SilentlyContinue | S` |
| 2026-03-30 12:45:36 | allow | `-` | `$path = "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets\c__Users_USER_AppData_Roaming_Cursor_User_workspaceSto` |
| 2026-03-30 12:45:46 | allow | `-` | `Copy-Item "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\assets\c__Users_USER_AppData_Roaming_Cursor_User_workspaceS` |
| 2026-03-30 12:45:51 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\images\"` |
| 2026-03-30 12:48:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/images/company-stamp.png services/estimate_service.py templates/partials/erp_es` |
| 2026-03-30 12:49:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $msg = @" feat: 견적서 4가지 기능 추가 1. 인감 도장: company-stamp.png를 대표자 옆에 오버레이 표시 2. 조건부 로고: 발주사가 라홈이면` |
| 2026-03-30 12:49:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-30 12:51:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" # 하우드 로고 복사 Copy-Item "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-` |
| 2026-03-30 12:51:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "static\images\"` |
| 2026-03-30 12:51:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/images/haud-logo.png static/images/company-stamp.png; $msg = "chore: 하우드 로고(hau` |
| 2026-03-30 13:10:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" # 하우드 로고 최신 버전으로 교체 Copy-Item "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-` |
| 2026-03-30 13:12:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" fix: 계약서 UI 4항목 수정 - 하우드 로고 최신 이미지로 교체 - 인감 도장 위치/크기 수정 (td→info-left 기준 absolute, 50` |
| 2026-03-30 13:52:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" fix: 계약서 UI 세부 조정 - 세로 bar 컬러 #5d4037 -> #ede8de (계약내용 헤더 라이트브라운 동일 적용) - 세로 bar 두께 3` |
| 2026-03-30 13:54:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" fix: 하우드 로고 max-width 제한 해제로 라홈 로고와 동일 높이 표시 - HAUD 로고 전환 시 max-width: none 적용 (가로 비율` |
| 2026-03-30 13:56:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" fix: 계약 내용 테이블 내부 테두리 PDF와 동일하게 수정 - 테두리 색상 회색(#aaa/#bbb) -> 따뜻한 베이지(#c5b9a6/#d4cbbe)` |
| 2026-03-30 13:58:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git log --oneline -5` |
| 2026-03-30 13:58:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" docs: AI 세션 로그 및 체크포인트 갱신 "@ $msg | Out-File -FilePath commit_msg.txt -Encoding utf8 ` |
| 2026-03-30 14:01:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" fix: 계약 내용 테이블 테두리 전체 제거 + PDF 색상 일치 - contract-title, tbl 외곽 border 전부 제거 - th: bord` |
| 2026-03-30 14:08:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" fix: 계약 내용 thead 배경색 연하게 변경 - 헤더와 확연히 구별 - th background: #f0ebe0 -> #faf8f4 (계약내용 #e` |
| 2026-03-30 14:11:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" fix: 갈색 세로 bar 높이를 content 영역(padding 제외)에 맞게 조정 - border-left 방식 -> ::before 가상요소 방식` |
| 2026-03-30 15:02:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -8; git status` |
| 2026-03-30 15:02:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" # 1. docs 변경사항 커밋 $msg = @" docs: AI 세션 로그 갱신 "@ $msg | Out-File -FilePath commit_msg.txt -Enco` |
| 2026-03-30 15:03:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; grep -n "저장\|save\|btn.*save\|savePdf\|print\|download" templates/erp_measurement_dashboard.ht` |
| 2026-03-30 15:05:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" feat: 계약서 탭 이미지 저장 버튼 추가 (실측 대시보드와 동일 방식) - erp_estimate_pane.html: 툴바 + 이미지저장 버튼(btn` |
| 2026-03-30 15:25:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git log --oneline -3` |
| 2026-03-30 15:26:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" # docs 커밋 $msg = @" docs: AI 세션 로그 갱신 "@ $msg | Out-File -FilePath commit_msg.txt -Encoding utf` |
| 2026-03-30 15:28:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_estimate_pane.html static/js/erp/estimate-preview.js` |
| 2026-03-30 15:29:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $msg = "feat: 견적서 계산에 예약금 행 추가 - 예약금 있을 때만 조건 표시, 잔금 = 합계 - 예약금 반영"; [System.IO.File]::WriteAl` |
| 2026-03-30 15:29:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-30 15:29:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/erp/estimate-preview.js; $msg = "fix: 계약번호 형식 변경 - 미리보기 대신 고객 전화번호 사용 (YYYYM` |
| 2026-03-30 15:55:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/erp/estimate-preview.js; $msg = "fix: 계약서 탭 진입 시 2중 로딩 제거 - click 리스너 중복 제거 ` |
| 2026-03-30 15:55:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy --no-edit; git push origin production; git checkout ` |
| 2026-03-30 16:00:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/estimate_service.py; $msg = "fix: 견적서 예약금 추출 버그 수정 - ERP Beta가 저장하는 flat 숫자 구` |
| 2026-03-30 16:08:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/estimate_service.py apps/api/erp_estimates.py static/js/erp/estimate-preview.` |
| 2026-03-30 16:09:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git log --oneline -3` |
| 2026-03-30 16:09:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/context/COMPACT_CHECKPOINT.md docs/context/EDIT_LOG.md docs/` |
| 2026-03-30 16:18:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/estimate_service.py; $msg = "fix: 견적서 예약금 미반영 근본 수정 - ERP Beta는 payment(단수)로 ` |
| 2026-03-30 16:26:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy; git push origin production; git checkout deploy` |
| 2026-03-30 16:26:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash; git checkout production; git merge deploy; git push origin production; git checkout` |
| 2026-03-30 16:34:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-03-30 16:35:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; $msg = "docs: 세션 로그 및 자동 생성 문서 갱신"; [System.IO.File]::WriteAllText("commit_msg.txt` |
| 2026-03-30 16:51:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_beta_js.html services/estimate_service.py; $msg = "feat: 제품 색상 ` |
| 2026-03-30 17:00:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/erp/estimate-preview.js; $msg = "perf: 계약서 탭 로딩 최적화 - dirty 플래그 도입으로 불필요한 저장` |
| 2026-03-30 22:15:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git log origin/deploy..HEAD --oneline` |
| 2026-03-30 22:15:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; $msg = "docs: 세션 로그 갱신"; [System.IO.File]::WriteAllText("commit_msg.txt", $msg, [S` |
| 2026-03-30 22:22:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/api/orders.py services/channel_delivery.py templates/partials/erp_beta_js.html; $` |
| 2026-03-30 22:23:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git log origin/deploy..HEAD --oneline` |
| 2026-03-30 22:23:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; $msg = "docs: 세션 로그 갱신"; [System.IO.File]::WriteAllText("commit_msg.txt", $msg, [S` |
