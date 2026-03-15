# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-03-09 08:34:44 | allow | `-` | `wc -l c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/api/erp_measurement.py c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/a` |
| 2026-03-09 08:57:55 | allow | `-` | `wc -l c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/partials/erp_beta_js.html c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOM` |
| 2026-03-10 16:37:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from services.order_date_sync import collect_order_schedule_date_specs; print('OK')` |
| 2026-03-10 16:38:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff services/order_date_sync.py` |
| 2026-03-10 16:38:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/order_date_sync.py; git commit --trailer "Made-with: Cursor" -F commit_msg.tx` |
| 2026-03-10 16:38:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-10 21:55:11 | allow | `-` | `python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-10 22:35:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-10 22:35:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-10 22:35:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5` |
| 2026-03-10 22:35:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-03-10 22:35:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff app.py | head -30` |
| 2026-03-10 22:35:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff app.py 2>$null | Select-Object -First 40` |
| 2026-03-10 22:36:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only` |
| 2026-03-10 22:36:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add app.py apps/api/erp_shipment_settings.py docs/AI_CHANGELOG.md docs/AI_STATUS.md docs/c` |
| 2026-03-10 22:36:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/shipment-dashboard-columns.css static/js/shipment-dashboard-columns.js docs` |
| 2026-03-10 22:36:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-10 22:36:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/ docs/context/SHELL_GUARD_LOG.md` |
| 2026-03-10 22:36:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --cached app.py 2>$null` |
| 2026-03-10 22:36:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-03-10 22:36:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/context/EDIT_LOG.md docs/context/SHELL_GUARD_LOG.md; git commit --trailer "Made-w` |
| 2026-03-10 22:42:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-10 22:42:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-10 22:49:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5 origin/production` |
| 2026-03-10 22:49:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show HEAD:services/order_date_sync.py 2>$null | Select-String "fallback|beta_schedule_fall` |
| 2026-03-10 22:49:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show HEAD:services/order_date_sync.py | Select-String "fallback|timedelta|days=5"` |
| 2026-03-10 22:54:53 | allow | `-` | `railway --version 2>$null; if ($LASTEXITCODE -ne 0) { echo "NOT_INSTALLED" }` |
| 2026-03-10 22:55:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway status 2>&1` |
| 2026-03-10 22:55:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway logs --limit 50 2>&1 | Select-Object -Last 30` |
| 2026-03-10 22:55:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway service 2>&1` |
| 2026-03-10 22:55:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway logs 2>&1 | Select-Object -Last 40` |
| 2026-03-10 22:55:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway service foms-production 2>&1; railway logs 2>&1 | Select-Object -Last 20` |
| 2026-03-10 22:56:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway environment 2>&1` |
| 2026-03-10 22:56:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline origin/production -3` |
| 2026-03-10 22:57:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway service FOMS 2>&1; railway logs 2>&1 | Select-Object -Last 5` |
| 2026-03-10 23:07:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline origin/production -5` |
| 2026-03-10 23:08:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production` |
| 2026-03-10 23:08:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import hashlib, time; print(hashlib.md5(str(time.time()).encode()).hexdigest()[:8])` |
| 2026-03-10 23:08:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" --allow-empty -F commit_msg.txt` |
| 2026-03-10 23:08:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-10 23:09:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-10 23:27:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables 2>&1 | Select-String "DATABASE|POSTGRES|DATABASE_URL" | Select-Object -First` |
| 2026-03-10 23:27:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import psycopg2, json conn = psycopg2.connect('postgresql://postgres:XMuhzNDZDeBlQ` |
| 2026-03-10 23:28:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import psycopg2 conn = psycopg2.connect('postgresql://postgres:XMuhzNDZDeBlQStbmUQ` |
| 2026-03-10 23:28:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python scripts/check_prod_fallback.py` |
| 2026-03-10 23:28:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python scripts/delete_prod_fallback.py` |
| 2026-03-10 23:30:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline services/order_date_sync.py | Select-Object -First 15` |
| 2026-03-10 23:30:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 9e95da3 --stat; git show 9e95da3 -- services/order_date_sync.py | Select-String "fall` |
| 2026-03-11 08:38:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-11 08:52:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python scripts/db_admin.py reset-admin --password admin1234` |
| 2026-03-11 08:56:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_client() as c: with c.session_transaction() as s` |
| 2026-03-11 08:56:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_client() as c: # Login first rv = c.post('/login` |
| 2026-03-11 08:56:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_client() as c: rv = c.post('/login', data={'user` |
| 2026-03-11 08:57:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_client() as c: rv = c.post('/login', data={'user` |
| 2026-03-11 09:07:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-11 09:07:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/order_pages.py static/css/erp-pro.css templates/index.html; git status` |
| 2026-03-11 09:07:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-11 09:08:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-11 09:08:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy; git push origin production; git checkout deploy` |
| 2026-03-11 12:49:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-11 13:08:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-11 13:09:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -a` |
| 2026-03-11 13:09:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_dashboard_grid.html; git commit --trailer "Made-with: Cursor" -` |
| 2026-03-11 13:09:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-11 13:10:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy -m "Merge deploy: ERP 대시보드 실측일/시공일 복합 표기"` |
| 2026-03-11 13:10:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-11 13:10:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-11 16:44:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp, _haversine_km, _get_order_schedule_date, a` |
| 2026-03-11 16:47:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp, _haversine_km, _get_order_schedule_date, _` |
| 2026-03-11 16:50:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add -A && git status` |
| 2026-03-12 00:16:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp; print('APP_OK')" 2>&1` |
| 2026-03-12 00:16:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py && git commit -F commit_msg.txt && rm commit_msg.txt && git push ` |
| 2026-03-12 00:28:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp, _get_order_schedule_date, _build_candidate` |
| 2026-03-12 00:28:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py && git commit -F commit_msg.txt && rm commit_msg.txt && git push ` |
| 2026-03-12 00:31:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c " import os, sys sys.path.insert(0, '.') from app import app with app.app_context(` |
| 2026-03-12 00:31:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c " import os, sys sys.path.insert(0, '.') from app import app with app.app_context(` |
| 2026-03-12 00:38:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp; print('APP_OK')" 2>&1 | tail -1` |
| 2026-03-12 00:38:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py && git commit -F commit_msg.txt && rm commit_msg.txt && git push ` |
| 2026-03-12 00:48:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp, _SEARCH_RADII_KM; print('OK', _SEARCH_RADI` |
| 2026-03-12 00:49:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py && git commit -F commit_msg.txt && rm commit_msg.txt && git push ` |
| 2026-03-12 01:01:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp; print('OK')" 2>&1 | tail -1` |
| 2026-03-12 01:01:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py && git commit -F commit_msg.txt && rm commit_msg.txt && git push ` |
| 2026-03-12 08:08:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp, _SEARCH_RADII_KM; print('OK', _SEARCH_RADI` |
| 2026-03-12 08:15:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py && git commit -F commit_msg.txt && rm commit_msg.txt && git push ` |
| 2026-03-12 08:27:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.api.orders import orders_bp; print('OK')" 2>&1 | tail -1` |
| 2026-03-12 08:27:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py && git commit -F commit_msg.txt && rm commit_msg.txt && git push ` |
| 2026-03-12 08:47:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c " import sys; sys.path.insert(0, '.') from app import app with app.app_context(): ` |
| 2026-03-12 08:48:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.erp_dashboard import erp_dashboard_bp; print('OK')" 2>&1 | tail -1` |
| 2026-03-12 08:48:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/erp_dashboard.py && git commit -F commit_msg.txt && rm commit_msg.txt && git pu` |
| 2026-03-12 08:50:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "from apps.erp_dashboard import erp_dashboard_bp; print('OK')" 2>&1 | tail -1` |
| 2026-03-12 08:50:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/erp_dashboard.py && git commit -F commit_msg.txt && rm commit_msg.txt && git pu` |
| 2026-03-12 09:13:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-12 09:14:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c " from apps.api.orders import _SEARCH_RADII_KM, _MAX_RESULTS, _haversine_km print(` |
| 2026-03-12 09:22:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-12 09:22:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c " from apps.api.orders import _SEARCH_RADII_KM print('諛섍꼍:', _SEARCH_RADII_KM) # f` |
| 2026-03-12 09:24:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status --short` |
| 2026-03-12 09:24:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/orders.py templates/erp_as_dashboard.html && git status --short` |
| 2026-03-12 09:29:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin deploy && git log --oneline -3` |
| 2026-03-12 09:29:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git merge deploy --no-ff -m "Merge branch 'deploy' into productio` |
| 2026-03-12 09:29:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout deploy && git log --oneline -3` |
| 2026-03-12 09:39:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && grep -r "bootstrap.*5\|cdn.*bootstrap" templates/base.html 2>/dev/null | head -3` |
| 2026-03-12 09:40:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git merge deploy --no-ff -m "Merge branch 'deploy' into productio` |
| 2026-03-12 09:56:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -1` |
| 2026-03-12 09:58:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git merge deploy --no-ff -m "Merge branch 'deploy' into productio` |
| 2026-03-12 10:02:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git merge deploy --no-ff -m "Merge branch 'deploy' into productio` |
| 2026-03-12 10:14:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -1` |
| 2026-03-12 10:16:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git merge deploy --no-ff -m "Merge branch 'deploy' into productio` |
| 2026-03-12 10:23:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -1` |
| 2026-03-12 10:23:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git merge deploy --no-ff -m "Merge branch 'deploy' into productio` |
| 2026-03-12 13:29:42 | allow | `-` | `python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-12 13:32:23 | allow | `-` | `python -c "import app; print('APP_OK')" 2>&1 | tail -1` |
| 2026-03-12 13:49:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; from apps.erp_shipment_page import erp_shipment_dashboard; print('OK')"` |
| 2026-03-12 13:58:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-12 13:58:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-12 13:59:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/erp_shipment_page.py; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-12 13:59:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-13 09:54:32 | allow | `-` | `find . -name "*.py" | xargs grep -l "channel" 2>/dev/null | head -20` |
| 2026-03-13 09:56:40 | allow | `-` | `curl -s "https://developers.channel.io/docs/native-functions" -H "Accept: text/html" --max-time 15 2>&1 | head -200` |
| 2026-03-13 09:56:43 | allow | `-` | `curl -s "https://developers.channel.io/reference/introduction" -H "Accept: text/html" --max-time 15 2>&1 | head -100` |
| 2026-03-13 09:56:49 | allow | `-` | `curl -s "https://api.channel.io/doc/app-store" --max-time 15 -H "Accept: application/json" 2>&1 | head -50` |
| 2026-03-13 09:56:51 | allow | `-` | `curl -s "https://app-store-api.channel.io/openapi/v3/native-functions" --max-time 15 -H "Accept: application/json" 2>&1 | head -50` |
| 2026-03-13 09:56:58 | allow | `-` | `curl -s -L "https://app-store-api.channel.io/openapi/v3/native-functions/issueToken" --max-time 15 2>&1 | head -100 && echo "---" && curl -s -L "https://app-sto` |
| 2026-03-13 09:56:59 | allow | `-` | `curl -s "https://developers.channel.io/docs/openapi/app-store" -A "Mozilla/5.0" --max-time 15 2>&1 | python3 -c "import sys,re; html=sys.stdin.read(); texts=re.` |
| 2026-03-13 09:57:07 | allow | `-` | `curl -s "https://developers.channel.io/docs/openapi/app-store" -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0` |
| 2026-03-13 09:57:08 | allow | `-` | `curl -s "https://developers.channel.io/reference/native-function-issue-token" -A "Mozilla/5.0" --max-time 15 2>&1 | head -50 && echo "====" && curl -s "https://` |
| 2026-03-13 09:57:16 | allow | `-` | `curl -s "https://developers.channel.io/_next/data/EpIouXxZwB9d6xwJaA7wQ/docs/native-functions.json" --max-time 15 2>&1 | head -100` |
| 2026-03-13 09:57:19 | allow | `-` | `curl -s "https://app-store-api.channel.io/general/v1/search?q=issueToken" --max-time 15 -H "Accept: application/json" 2>&1 | head -50 && echo "===" && curl -s "` |
| 2026-03-13 09:57:28 | allow | `-` | `curl -s "https://web.archive.org/web/2024/https://developers.channel.io/docs/native-functions" --max-time 20 -A "Mozilla/5.0" 2>&1 | python3 -c " import sys, re` |
| 2026-03-13 09:57:36 | allow | `-` | `curl -s "https://api.channel.io/app-store/v1/functions" --max-time 10 -H "Content-Type: application/json" 2>&1 | head -20` |
| 2026-03-13 09:57:42 | allow | `-` | `curl -s "https://api.channel.io/app-store/v1/native-functions/issueToken" --max-time 10 -X POST -H "Content-Type: application/json" -d '{"method":"issueToken","` |
| 2026-03-13 09:57:45 | allow | `-` | `pip show channeltalk 2>&1; pip show channel-io 2>&1; pip index versions channel-io 2>&1 | head -5` |
| 2026-03-13 09:57:55 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/channel-talk-example/main/README.md" --max-time 10 2>&1 | head -100 && echo "===" && curl -s "https://raw.` |
| 2026-03-13 09:57:58 | allow | `-` | `curl -s "https://api.github.com/search/repositories?q=channel.io+native+function&sort=stars" --max-time 10 -H "Accept: application/vnd.github.v3+json" 2>&1 | py` |
| 2026-03-13 09:58:03 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/bezier-react/main/README.md" --max-time 10 2>&1 | head -30` |
| 2026-03-13 09:58:21 | allow | `-` | `curl -s "https://api.github.com/orgs/channel-io/repos?per_page=50&sort=updated" --max-time 15 -H "Accept: application/vnd.github.v3+json" 2>&1 | python3 -c " im` |
| 2026-03-13 09:58:27 | allow | `-` | `curl -s "https://api.github.com/orgs/channel-io/repos?per_page=50&sort=updated" --max-time 15 2>&1 | python3 -c " import sys,json,re raw = sys.stdin.read() # ex` |
| 2026-03-13 09:58:36 | allow | `-` | `curl -s "https://api.github.com/orgs/channel-io/repos?per_page=50&sort=updated" --max-time 20 -o /tmp/channeltalk_repos.json && python3 /tmp/channeltalk_repos.j` |
| 2026-03-13 09:58:42 | allow | `-` | `curl -s "https://api.github.com/orgs/channel-io/repos?per_page=50&sort=updated" --max-time 20 > /tmp/channeltalk_repos.json && echo "Downloaded" && wc -c /tmp/c` |
| 2026-03-13 09:58:48 | allow | `-` | `python3 -c " import json with open('/tmp/channeltalk_repos.json') as f: data = json.load(f) for r in data: print(r['full_name'], '-', r.get('description','')) "` |
| 2026-03-13 09:58:55 | allow | `-` | `curl -s "https://api.github.com/orgs/channel-io/repos?per_page=50&sort=updated" --max-time 20 > "C:/Users/USER/AppData/Local/Temp/channeltalk_repos.json" && ech` |
| 2026-03-13 09:59:03 | allow | `-` | `python3 -c " import json with open('C:/Users/USER/AppData/Local/Temp/channeltalk_repos.json') as f: data = json.load(f) for r in data: name = r.get('full_name',` |
| 2026-03-13 09:59:08 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && python3 -c " import json with open('channeltalk_repos.json') as f: data = json.load(f) for r in data: name = r.get('ful` |
| 2026-03-13 09:59:15 | allow | `-` | `cd /c/Users/USER/AppData/Local/Temp && ls channeltalk_repos.json && python3 -c " import json with open('channeltalk_repos.json') as f: data = json.load(f) for r` |
| 2026-03-13 09:59:26 | allow | `-` | `curl -s "https://api.github.com/search/repositories?q=org:channel-io+native+function&sort=stars" --max-time 15 > "C:/Users/USER/AppData/Local/Temp/channeltalk_s` |
| 2026-03-13 09:59:30 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/channel-web-sdk-loader/main/README.md" --max-time 10 2>&1 | head -80 && echo "===" && curl -s "https://raw` |
| 2026-03-13 09:59:37 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-sdk/contents/" --max-time 10 2>&1 | head -50 && echo "===" && curl -s "https://api.github.com/search/reposi` |
| 2026-03-13 09:59:44 | allow | `-` | `curl -s "https://api.github.com/search/code?q=issueToken+org:channel-io" --max-time 15 -H "Accept: application/vnd.github.v3+json" 2>&1 | head -80` |
| 2026-03-13 10:00:04 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/README.md" --max-time 10 && echo "===" && curl -s "https://raw.githubusercontent.com/cha` |
| 2026-03-13 10:00:11 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/contents/" --max-time 10 -H "Accept: application/vnd.github.v3+json" 2>&1 | grep '"name"' | head -` |
| 2026-03-13 10:00:13 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/git/trees/main?recursive=1" --max-time 10 -H "Accept: application/vnd.github.v3+json" 2>&1 | grep ` |
| 2026-03-13 10:00:19 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/appstore/infra/app_store_client.go" --max-time 10 2>&1` |
| 2026-03-13 10:00:22 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/appstore/infra/dto/write_message_dto.go" --max-time 10 2>&1 && echo "===" && cu` |
| 2026-03-13 10:00:29 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/git/trees/main?recursive=1" --max-time 10 -H "Accept: application/vnd.github.v3+json" 2>&1 | grep ` |
| 2026-03-13 10:00:31 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/appstore/svc/app_store_svc.go" --max-time 10 2>&1 && echo "===" && curl -s "htt` |
| 2026-03-13 10:00:39 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/auth/infra/auth_client.go" --max-time 10 2>&1 && echo "===" && curl -s "https:/` |
| 2026-03-13 10:00:40 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/auth/svc/auth_svc.go" --max-time 10 2>&1 && echo "===" && curl -s "https://raw.` |
| 2026-03-13 10:00:48 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/native/dto/native_function_dto.go" --max-time 10 2>&1 && echo "===" && curl -s ` |
| 2026-03-13 10:00:49 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/auth/repo/auth_repo.go" --max-time 10 2>&1 && echo "===" && curl -s "https://ra` |
| 2026-03-13 10:00:57 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/git/trees/main?recursive=1" --max-time 10 -H "Accept: application/vnd.github.v3+json" 2>&1 | grep ` |
| 2026-03-13 10:00:59 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/native/dto/native_function_dto.go" --max-time 10 2>&1` |
| 2026-03-13 10:01:03 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/http/server.go" --max-time 10 2>&1 && echo "===" && curl -s "https://raw.github` |
| 2026-03-13 10:01:04 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/git/trees/main?recursive=1" --max-time 10 2>&1 | grep '"path"' | head -60` |
| 2026-03-13 10:01:11 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/api/public/route/function/dto/function_dto.go" --max-time 10 2>&1 && echo "===" && curl ` |
| 2026-03-13 10:01:13 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/git/trees/main?recursive=1" --max-time 10 2>&1 | grep '"path"' | tail -30` |
| 2026-03-13 10:01:21 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/config/config.go" --max-time 10 2>&1` |
| 2026-03-13 10:01:23 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/wam/src/utils/wam.ts" --max-time 10 2>&1 && echo "===" && curl -s "https://raw.githubuse` |
| 2026-03-13 10:01:33 | allow | `-` | `curl -s "https://developers.channel.io/docs/app-store-verification" -A "Mozilla/5.0" --max-time 15 2>&1 | grep -oP '"text":"[^"]{10,}"' | head -50` |
| 2026-03-13 10:01:35 | allow | `-` | `curl -s "https://developers.channel.io/docs/app-store-authentication" -A "Mozilla/5.0" --max-time 15 2>&1 | grep -oP '"content":"[^"]{20,}"' | head -50` |
| 2026-03-13 10:01:40 | allow | `-` | `curl -s "https://developers.channel.io/docs/app-store-verification" -A "Mozilla/5.0" --max-time 15 > "C:/Users/USER/AppData/Local/Temp/channeltalk_verification.` |
| 2026-03-13 10:01:49 | allow | `-` | `curl -s "https://registry.npmjs.org/@channel.io/app-store-api" --max-time 10 2>&1 | head -100` |
| 2026-03-13 10:01:57 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-store-webhook-python/contents/" --max-time 10 2>&1 | grep '"name"' && echo "===" && curl -s "https://api.gi` |
| 2026-03-13 10:02:02 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/git/trees/main?recursive=1" --max-time 10 2>&1 | grep -E '"path"' | grep -v ".gz"` |
| 2026-03-13 10:02:10 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/config/root/root.go" --max-time 10 2>&1 && echo "===" && curl -s "https://raw.g` |
| 2026-03-13 10:02:14 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/api/public/fx.go" --max-time 10 2>&1` |
| 2026-03-13 10:02:25 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/go.mod" --max-time 10 2>&1` |
| 2026-03-13 10:02:27 | allow | `-` | `curl -s "https://api.github.com/search/repositories?q=channel-io+app+webhook+signature&sort=updated" --max-time 15 2>&1 | grep -E '"full_name"|"description"' | ` |
| 2026-03-13 10:02:41 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/app-tutorial/issues?state=all&per_page=10" --max-time 10 2>&1 | grep -E '"title"|"body"' | head -20` |
| 2026-03-13 10:02:44 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/api/public/route/function/dto/function_dto.go" --max-time 10 2>&1 | grep -i "sign\|heade` |
| 2026-03-13 10:02:48 | allow | `-` | `curl -s "https://raw.githubusercontent.com/channel-io/app-tutorial/main/internal/config/viper.go" --max-time 10 2>&1` |
| 2026-03-13 10:08:53 | allow | `-` | `python -c "from services.channel_client import is_configured, send_group_message, format_order_message; print('channel_client OK')"` |
| 2026-03-13 10:09:15 | allow | `-` | `python -c "from services.jobs.queue import enqueue_channeltalk_push; print('queue OK')"` |
| 2026-03-13 10:09:19 | allow | `-` | `python -c "from apps.api.erp_orders_structured import erp_orders_structured_bp; print('blueprint OK')"` |
| 2026-03-13 10:09:24 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 10:12:52 | allow | `-` | `python -c "from services.channel_client import is_configured, format_order_message, get_target_group_id; print('channel_client OK')" && python -c "import app; p` |
| 2026-03-13 10:13:53 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 11:24:41 | allow | `-` | `ls /c/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/api/` |
| 2026-03-13 11:25:14 | allow | `-` | `python -c "from apps.api.channel_integration import channel_integration_bp; print('channel_integration OK')"` |
| 2026-03-13 11:25:24 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 11:25:31 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 11:25:56 | allow | `-` | `python -c "from apps.api.channel_integration import channel_integration_bp; print('channel_integration OK')" && python -c "import app; print('APP_OK')"` |
| 2026-03-13 11:29:04 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 11:31:57 | allow | `-` | `curl -s "https://developers.channel.io/docs/native-functions" -L --max-time 15 -A "Mozilla/5.0" 2>&1| head -200` |
| 2026-03-13 11:32:35 | allow | `-` | `curl -s "https://api.github.com/search/repositories?q=channel-io+native+functions&sort=stars" --max-time 15 2>&1| python -c "import sys,json; data=json.load(sys` |
| 2026-03-13 11:32:43 | allow | `-` | `curl -s "https://developers.channel.io/reference/native-functions-overview" -L --max-time 15 -A "Mozilla/5.0" 2>&1 | python -c " import sys content = sys.stdin.` |
| 2026-03-13 11:32:46 | allow | `-` | `curl -s "https://developers.channel.io/reference/write-group-message" -L --max-time 15 -A "Mozilla/5.0" 2>&1 | python -c " import sys, re content = sys.stdin.re` |
| 2026-03-13 11:32:50 | allow | `-` | `curl -s "https://developers.channel.io/reference/app-store-api-v1-native-functions" -L --max-time 20 -A "Mozilla/5.0" -H "Accept: application/json" 2>&1 | head ` |
| 2026-03-13 11:32:52 | allow | `-` | `curl -s "https://api.github.com/repos/channel-io/channel-native-functions-sdk/contents" --max-time 15 2>&1 curl -s "https://api.github.com/search/code?q=deleteM` |
| 2026-03-13 11:33:07 | allow | `-` | `curl -sL "https://api.github.com/orgs/channel-io/repos?per_page=50&type=public" --max-time 20 2>&1 | python3 -c "import sys, json; data=json.loads(sys.stdin.rea` |
| 2026-03-13 11:33:43 | allow | `-` | `curl -sL "https://developers.channel.io/en/articles/Function-77250b17" --max-time 20 -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" 2>&1 | py` |
| 2026-03-13 11:33:50 | allow | `-` | `curl -sL "https://developers.channel.io/en/articles/Function-77250b17" --max-time 30 -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, li` |
| 2026-03-13 11:34:09 | allow | `-` | `curl -sL "https://developers.channel.io/en/articles/Function-77250b17" --max-time 30 -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, li` |
| 2026-03-13 11:34:24 | allow | `-` | `python3 << 'PYEOF' import re with open('C:/Users/USER/AppData/Local/Temp/channeltalk_article.html', 'r', encoding='utf-8', errors='ignore') as f: content = f.re` |
| 2026-03-13 11:34:36 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && python3 -c " import re with open('channeltalk_article.html', 'r', encoding='utf-8', errors='ignore') as f: content = f.` |
| 2026-03-13 11:34:48 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && dir channeltalk_article.html 2>&1` |
| 2026-03-13 11:34:58 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o "deleteMessage[^\"<]*" channeltalk_article.html | head -20 2>&1` |
| 2026-03-13 11:35:00 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o "writeGroupMessage[^<\"]*" channeltalk_article.html | head -20 2>&1` |
| 2026-03-13 11:35:05 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -c "deleteMessage" channeltalk_article.html 2>&1 grep -c "deleteGroupMessage" channeltalk_article.html 2>&1 grep -` |
| 2026-03-13 11:35:10 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -oi "method.*[A-Z][a-z]\{3,\}" channeltalk_article.html | head -30 2>&1` |
| 2026-03-13 11:35:22 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o ">[^<]*Message[^<]*<" channeltalk_article.html | grep -v "class\|style\|script\|href" | sort -u | head -60 2>&1` |
| 2026-03-13 11:35:29 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o '"method": "[^"]*"' channeltalk_article.html | sort -u 2>&1` |
| 2026-03-13 11:35:31 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -oi "update[A-Za-z]*Message\|delete[A-Za-z]*Message\|edit[A-Za-z]*Message" channeltalk_article.html | sort -u 2>&1` |
| 2026-03-13 11:35:35 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -oi 'method.*[A-Za-z]\{4,\}' channeltalk_article.html | grep -iv "class\|style\|charset\|content\|http\|get\|post\` |
| 2026-03-13 11:35:48 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o '"method":[^,}]*' channeltalk_article.html | sort -u 2>&1` |
| 2026-03-13 11:35:55 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o '"method": \\\\\"[^\\]*\\\\\"' channeltalk_article.html | sort -u 2>&1 grep -o 'method.*write\|method.*issue\|m` |
| 2026-03-13 11:36:09 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o '"method": \\"[a-zA-Z]*\\"' channeltalk_article.html | sort -u 2>&1` |
| 2026-03-13 11:36:16 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -oP '(?<="method": \\\\")[a-zA-Z]+(?=\\\\")' channeltalk_article.html | sort -u 2>&1` |
| 2026-03-13 11:36:28 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && strings channeltalk_article.html | grep -E '"method".*[A-Z][a-z]{3,}' | head -20 2>&1` |
| 2026-03-13 11:36:34 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o 'write[A-Z][A-Za-z]*\|issue[A-Z][A-Za-z]*\|update[A-Z][A-Za-z]*\|delete[A-Z][A-Za-z]*\|register[A-Z][A-Za-z]*\|` |
| 2026-03-13 11:36:39 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o "issueToken\|issueChannelToken\|issue[A-Z][A-Za-z]*" channeltalk_article.html | sort -u 2>&1` |
| 2026-03-13 11:36:48 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && grep -o '[a-zA-Z]*[Tt]oken[a-zA-Z]*' channeltalk_article.html | sort -u 2>&1` |
| 2026-03-13 11:37:35 | allow | `-` | `cd "C:/Users/USER/AppData/Local/Temp" && curl -sL "https://developers.channel.io/en/articles/Authentication-e7c2fb6f" --max-time 30 -A "Mozilla/5.0 (Windows NT ` |
| 2026-03-13 11:41:39 | allow | `-` | `curl -s "https://developers.channel.io/reference/overview" -A "Mozilla/5.0" --max-time 15 2>&1| head -100` |
| 2026-03-13 11:41:42 | allow | `-` | `curl -s "https://api.channel.io/open/v5" -A "Mozilla/5.0" --max-time 10 2>&1` |
| 2026-03-13 11:42:44 | allow | `-` | `curl -s -L "https://developers.channel.io/reference/overview-1" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" --max-time 15 2>&1` |
| 2026-03-13 11:42:46 | allow | `-` | `curl -s -L "https://developers.channel.io/docs/open-api" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" --max-time 15 2>&1 | head` |
| 2026-03-13 14:02:47 | allow | `-` | `python -c "from services.channel_client import send_group_message; print('channel_client OK')"` |
| 2026-03-13 14:03:24 | allow | `-` | `python -c "from apps.api.channel_integration import channel_integration_bp; print('channel_integration OK')"` |
| 2026-03-13 14:03:28 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 14:03:52 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 14:05:59 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-13 16:43:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-13 16:43:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-13 16:44:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/AI_STATUS.md docs/context/COMPACT_CHECKPOINT.md docs/context` |
| 2026-03-13 16:44:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/AI_STATUS.md docs/context/COMPACT_CHECKPOINT.md docs/context` |
| 2026-03-13 16:45:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-13 16:45:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-15 12:28:28 | allow | `-` | `ls docs/plans/` |
| 2026-03-15 12:29:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 12:30:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 12:30:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_beta_js.html docs/AI_CHANGELOG.md; git commit --trailer "Made-w` |
| 2026-03-15 12:30:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-15 12:53:48 | allow | `-` | `wc -l "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_beta_js.html" 2>nul || powershell -Command "(Get-Content 'c:\Users\USE` |
| 2026-03-15 12:53:51 | allow | `-` | `powershell -Command "(Get-Content 'c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_beta_js.html').Count"` |
| 2026-03-15 12:54:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 12:57:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 12:57:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -3` |
| 2026-03-15 12:57:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show HEAD:check_orders.py` |
| 2026-03-15 12:57:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show HEAD:r2_storage.py` |
| 2026-03-15 12:57:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show HEAD:templates/partials/_erp_amount_block.html` |
| 2026-03-15 12:57:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show HEAD:templates/partials/chat_scripts.html` |
| 2026-03-15 13:31:20 | allow | `-` | `grep -n "function escapeHtml\|const escapeHtml\|escapeHtml =" templates/**/*.html static/**/*.js 2>/dev/null | wc -l` |
| 2026-03-15 13:37:35 | allow | `-` | `grep -rn "function escapeHtml" templates/ 2>/dev/null | cut -d: -f1 | sort | uniq -c` |
| 2026-03-15 13:55:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch` |
| 2026-03-15 13:55:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status` |
| 2026-03-15 13:56:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash pop` |
| 2026-03-15 13:56:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-15 14:03:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 14:03:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest -q 2>&1 | head -80` |
| 2026-03-15 14:04:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest -q 2>&1` |
| 2026-03-15 14:05:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest -q 2>&1` |
| 2026-03-15 14:07:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 14:07:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest -q 2>&1` |
| 2026-03-15 14:13:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 14:13:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; alembic current` |
| 2026-03-15 14:15:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 14:19:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL = "postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.` |
| 2026-03-15 14:19:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL = "postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.` |
| 2026-03-15 14:19:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL = "postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.` |
| 2026-03-15 14:19:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL = "postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.` |
| 2026-03-15 14:20:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL = "postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.` |
| 2026-03-15 14:20:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL = "postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.` |
| 2026-03-15 14:28:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL = "postgresql://postgres:XMuhzNDZDeBlQStbmUQymJTGQvgIKAVq@yamanote.proxy.rlw` |
| 2026-03-15 14:28:53 | allow | `-` | `alembic upgrade head` |
| 2026-03-15 14:29:06 | allow | `-` | `alembic current` |
| 2026-03-15 14:34:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 14:35:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "import app; print('APP_OK')"` |
| 2026-03-15 14:36:27 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-15 14:48:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 14:49:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status --short` |
| 2026-03-15 14:57:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-15 14:57:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash pop` |
| 2026-03-15 15:19:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 -p -- apps/api/erp_map.py` |
| 2026-03-15 17:29:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run psql $env:DATABASE_URL -f scripts/check_map_orders_2670_2662.sql` |
| 2026-03-15 17:30:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/run_map_check.py` |
| 2026-03-15 17:30:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:PYTHONIOENCODING='utf-8'; railway run python scripts/run_map_check.py` |
| 2026-03-15 17:31:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/run_map_check.py` |
| 2026-03-15 17:31:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/run_map_check.py` |
| 2026-03-15 17:31:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway --help` |
| 2026-03-15 17:32:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway connect --help` |
| 2026-03-15 17:32:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway connect` |
| 2026-03-15 17:32:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway status` |
| 2026-03-15 17:32:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway connect Postgres` |
| 2026-03-15 17:32:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; echo "python scripts/run_map_check.py" | railway shell` |
| 2026-03-15 17:33:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pip show psycopg 2>$null; pip show psycopg2 2>$null` |
| 2026-03-15 17:33:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/run_map_check.py` |
| 2026-03-15 17:33:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python -c "import os; k=[k for k in os.environ if 'DATABASE' in k or 'PG' in k]; p` |
| 2026-03-15 17:34:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/run_map_check.py` |
| 2026-03-15 17:35:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-03-15 17:35:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-15 17:36:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/api/erp_map.py docs/ docs/evolution/MAP_ORDERS_2670_2662_ANALYSIS_2026-03-15.md; ` |
