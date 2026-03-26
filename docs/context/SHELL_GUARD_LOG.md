# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-03-20 10:59:20 | allow | `-` | `python verify_phase_b.py` |
| 2026-03-20 11:00:07 | allow | `-` | `git rm apply_migration.py check_urgent.py commit_msg.txt verify_phase_a.py verify_phase_a3.py verify_phase_b.py ; git commit --trailer "Made-with: Cursor" -m "c` |
| 2026-03-20 11:00:26 | allow | `-` | `git rm apply_migration.py check_urgent.py verify_phase_a.py verify_phase_a3.py verify_phase_b.py ; git commit --trailer "Made-with: Cursor" -m "chore: remove te` |
| 2026-03-20 11:05:01 | allow | `-` | `grep -rn "detail_payload.attachments" templates/` |
| 2026-03-20 11:10:27 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-20 11:23:43 | allow | `-` | `python -c "import apps.erp_dashboard"` |
| 2026-03-20 11:24:00 | allow | `-` | `python verify_phase_c.py` |
| 2026-03-20 11:25:35 | allow | `-` | `python -c "import apps.erp_dashboard"` |
| 2026-03-20 11:27:37 | allow | `-` | `python verify_phase_c_override.py` |
| 2026-03-20 11:34:52 | allow | `-` | `python -c "import app"` |
| 2026-03-20 11:44:56 | allow | `-` | `pytest tests/test_erp_order_detail_preload.py` |
| 2026-03-20 11:45:13 | allow | `-` | `pytest` |
| 2026-03-20 11:51:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pyright apps/erp_dashboard.py services/erp_order_detail.py services/db_indexes.py se` |
| 2026-03-20 11:54:43 | allow | `-` | `git mv scripts/backfill_erp_date_columns.py scripts/backfill_erp_flat_columns.py` |
| 2026-03-20 11:58:31 | allow | `-` | `python -c " from app import app from services.db_indexes import ensure_erp_date_columns with app.app_context(): ensure_erp_date_columns() "` |
| 2026-03-20 11:58:51 | allow | `-` | `python -c " from app import app from services.db_indexes import ensure_erp_date_columns with app.app_context(): ensure_erp_date_columns() "` |
| 2026-03-20 11:59:01 | allow | `-` | `python scripts/backfill_erp_flat_columns.py` |
| 2026-03-20 11:59:25 | allow | `-` | `python verify_phase_d.py` |
| 2026-03-20 11:59:30 | allow | `-` | `pytest tests/test_erp_order_detail_preload.py` |
| 2026-03-20 12:00:14 | allow | `-` | `python verify_phase_d.py` |
| 2026-03-20 12:31:08 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-20 12:43:14 | allow | `-` | `python verify_phase_h.py` |
| 2026-03-20 12:43:37 | allow | `-` | `python test_cutoff.py` |
| 2026-03-20 12:44:17 | allow | `-` | `python -c "import app; print('APP_OK')" && pytest tests/test_erp_order_detail_preload.py` |
| 2026-03-20 12:44:25 | allow | `-` | `python -c "import app; print('APP_OK')" ; pytest tests/test_erp_order_detail_preload.py` |
| 2026-03-20 13:01:25 | allow | `-` | `python test_history_error.py` |
| 2026-03-20 13:02:06 | allow | `-` | `python test_history_error.py` |
| 2026-03-20 13:03:24 | allow | `-` | `railway --help` |
| 2026-03-20 13:03:35 | allow | `-` | `railway logs -n 50` |
| 2026-03-20 13:04:00 | allow | `-` | `railway service` |
| 2026-03-20 13:04:09 | allow | `-` | `railway status` |
| 2026-03-20 13:04:57 | allow | `-` | `python test_jinja_error.py` |
| 2026-03-20 13:05:16 | allow | `-` | `python test_jinja_error.py` |
| 2026-03-20 13:05:37 | allow | `-` | `python test_jinja_error.py` |
| 2026-03-20 13:05:52 | allow | `-` | `python -c "from jinja2 import Template; print(Template('{{ stage|replace(\" \", \"-\") }}').render(stage=None))"` |
| 2026-03-20 13:06:28 | allow | `-` | `python test_jinja_replace.py` |
| 2026-03-20 13:07:32 | allow | `-` | `railway list` |
| 2026-03-20 13:08:06 | allow | `-` | `railway service` |
| 2026-03-20 13:08:26 | allow | `-` | `ls -l railway.json` |
| 2026-03-20 13:08:40 | allow | `-` | `railway service web` |
| 2026-03-20 13:09:09 | allow | `-` | `railway logs -n 100` |
| 2026-03-20 13:09:53 | allow | `-` | `railway logs | Select-String "Traceback" -Context 0,20` |
| 2026-03-20 13:10:03 | allow | `-` | `railway logs | Select-String "500" -Context 5,5` |
| 2026-03-20 13:12:02 | allow | `-` | `railway logs | Select-String "Exception" -Context 3,10` |
| 2026-03-20 13:12:15 | allow | `-` | `railway logs -n 500 > logs.txt` |
| 2026-03-20 13:12:59 | allow | `-` | `python -c " from app import app from db import get_db from models import Order from sqlalchemy import or_, cast, String with app.app_context(): db = get_db() _q` |
| 2026-03-20 13:13:38 | allow | `-` | `python -c " from app import app from db import get_db from models import Order from sqlalchemy import or_, cast, String from sqlalchemy.dialects import postgres` |
| 2026-03-20 13:14:25 | allow | `-` | `railway variables` |
| 2026-03-20 13:14:43 | allow | `-` | `railway environment dev` |
| 2026-03-20 13:16:06 | allow | `-` | `python test_jinja_error.py` |
| 2026-03-20 13:16:57 | allow | `-` | `rm commit_msg.txt test_history_error.py test_jinja_error.py test_jinja_replace.py logs.txt` |
| 2026-03-20 15:11:42 | allow | `-` | `& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" --help 2>&1 | Select-String -Pattern "exclude"` |
| 2026-03-20 15:11:45 | allow | `-` | `& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" --help` |
| 2026-03-20 15:54:10 | allow | `-` | `& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" --section=data --section=post-data 2>&1` |
| 2026-03-20 16:34:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from copy import deepcopy; from models import Order; from services.erp_display impo` |
| 2026-03-20 16:36:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-03-20 16:36:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/erp_history_page.py templates/erp_history_dashboard.html templates/index.html app` |
| 2026-03-20 16:36:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg_deploy.txt; Remove-Item commit_msg_depl` |
| 2026-03-20 16:36:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-22 10:20:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-22 10:20:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-22 10:21:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/erp_history_page.py templates/erp_history_dashboard.html docs/plans/2026-03-20-hi` |
| 2026-03-22 10:45:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-22 10:46:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_production_styles.html templates/partials/erp_production_filter` |
| 2026-03-22 10:49:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy; git push origin product` |
| 2026-03-22 10:49:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/context/SESSION_LOG.md docs/context/SHELL_GUARD_LOG.md; git ` |
| 2026-03-22 10:49:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy; git push origin product` |
| 2026-03-22 10:49:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash; git checkout production; git pull origin production; git merge deploy; git push ori` |
| 2026-03-22 10:49:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-23 09:18:41 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c " from db import get_db from models import Order from services.erp_policy import S` |
| 2026-03-23 09:20:52 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c " from app import app from db import get_db from models import Order from services` |
| 2026-03-23 09:21:58 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff 1b0521f0^..1b0521f0 -- apps/erp_dashboard.py models.py` |
| 2026-03-23 09:22:01 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff 16ed530d^..16ed530d -- apps/erp_history_page.py apps/order_pages.py` |
| 2026-03-23 09:24:19 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')"` |
| 2026-03-23 09:25:39 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git status && git diff models.py` |
| 2026-03-23 09:25:43 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -3` |
| 2026-03-23 09:26:00 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git push origin deploy` |
| 2026-03-23 09:26:11 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git checkout production && git pull origin production && git merge deploy --no-edit && git p` |
| 2026-03-23 09:26:19 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git checkout deploy` |
| 2026-03-23 09:31:28 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python - <<'PYEOF' import sys sys.path.insert(0, '.') from app import app from db import db_` |
| 2026-03-23 09:37:32 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python - <<'PYEOF' import sys sys.path.insert(0, '.') from app import app from db import db_` |
| 2026-03-23 09:40:57 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')"` |
| 2026-03-23 09:41:21 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git add models.py services/app_init.py apps/erp_dashboard.py && printf 'fix: erp_stage_code ` |
| 2026-03-23 09:41:38 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git push origin deploy` |
| 2026-03-23 09:41:46 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git checkout production && git pull origin production && git merge deploy --no-edit && git p` |
| 2026-03-23 09:52:15 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git checkout production && git pull origin production && git merge deploy --no-edit && git p` |
| 2026-03-23 09:52:24 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git checkout deploy` |
| 2026-03-24 09:22:20 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git status && git diff --stat` |
| 2026-03-24 09:25:46 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git push origin deploy` |
| 2026-03-24 09:27:06 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git status && git diff --stat` |
| 2026-03-24 09:28:09 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff --stat app.py apps/api/erp_orders_structured.py apps/api/orders.py apps/order_pages` |
| 2026-03-24 09:32:12 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff HEAD --stat` |
| 2026-03-24 09:45:27 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && wc -l templates/erp_measurement_dashboard.html` |
| 2026-03-24 11:13:52 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git status && git log --oneline -5` |
| 2026-03-24 11:14:02 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline origin/production..origin/deploy` |
| 2026-03-24 11:14:11 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git checkout production && git merge origin/deploy --no-edit && git push origin production &` |
| 2026-03-24 11:14:18 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git stash && git checkout production && git merge origin/deploy --no-edit && git push origin` |
| 2026-03-24 11:30:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git diff --stat` |
| 2026-03-24 13:01:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add static/css/erp-pro.css templates/erp_drawing_workbench_detail.html templates/erp_mea` |
| 2026-03-24 13:01:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin deploy` |
| 2026-03-24 13:11:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add static/css/erp-pro.css templates/layout.html && git commit -F commit_msg.txt && rm c` |
| 2026-03-24 13:37:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add static/css/erp-pro.css templates/layout.html && git commit -F commit_msg.txt && rm c` |
| 2026-03-24 13:51:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add templates/partials/erp_dashboard_scripts_detail_dom.html templates/erp_measurement_d` |
| 2026-03-24 13:55:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git log --oneline -3` |
| 2026-03-24 14:13:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add static/css/erp-pro.css templates/layout.html && git commit -F commit_msg.txt && rm c` |
| 2026-03-24 14:25:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add static/css/style-pro-max.css static/css/erp-pro.css templates/layout.html && git com` |
| 2026-03-24 14:29:43 | allow | `-` | `ls -la .cursor/rules/` |
| 2026-03-24 14:37:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add templates/partials/erp_dashboard_styles.html && git commit -F commit_msg.txt && rm c` |
| 2026-03-24 14:53:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && git log --oneline -5` |
| 2026-03-24 14:55:47 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git status --short` |
| 2026-03-24 15:08:18 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git stash && git checkout production && git merge deploy --no-edit && git push origin produc` |
| 2026-03-24 15:38:10 | allow | `-` | `grep -n "measurement-chevron\|detail-row\|toggleRow\|chevron" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/erp/measurement.js" | head ` |
| 2026-03-24 15:39:40 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git add templates/partials/erp_dashboard_scripts_detail_dom.html templates/partials/erp_dash` |
| 2026-03-24 15:58:56 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -30 -- apps/api/ apps/erp_as*.py services/nearby*.py services/route*.py | ` |
| 2026-03-24 15:59:07 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -- apps/api/erp_as_nearby*.py apps/api/as_schedule*.py services/nearby*.py` |
| 2026-03-24 16:00:03 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -20 -- apps/api/orders.py` |
| 2026-03-24 16:00:11 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 07e04e7b --stat | head -20 && echo "---" && git diff 07e04e7b~1 07e04e7b -- apps/ap` |
| 2026-03-24 16:00:35 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -- apps/api/orders.py | head -5` |
| 2026-03-24 16:00:48 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 9df3a376 --stat && echo "---" && git diff 9df3a376~1 9df3a376 -- apps/api/orders.py` |
| 2026-03-24 16:00:55 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff 258e50dc~1 258e50dc -- apps/api/orders.py | grep "^[+-]" | grep -v "^---\|^+++" | h` |
| 2026-03-24 16:01:05 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff -- apps/api/orders.py | head -100` |
| 2026-03-24 16:01:12 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git status --short` |
| 2026-03-24 16:01:52 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -10 -- foms_address_converter.py` |
| 2026-03-24 16:01:55 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git log --oneline -20 -- apps/api/erp_orders_structured.py` |
| 2026-03-24 16:02:01 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff 6fedefe3~1 6fedefe3 -- foms_address_converter.py | grep "^[+-]" | grep -v "^---\|^+` |
| 2026-03-24 16:02:05 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop\SY/program/lahomproject/FOMS" && git log --oneline --all -- apps/api/orders.py | head -5 && echo "---" && git show a1b54820 -` |
| 2026-03-24 16:02:33 | allow | `-` | `grep -n "directions_url\|KAKAO_REST\|kakao.*api\|api\.kakao\|navi\|waypoints\|v1/future" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/foms_addre` |
| 2026-03-24 16:02:36 | allow | `-` | `grep -n "KAKAO_REST\|api_key\|Authorization\|headers" "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/foms_address_converter.py" | head -20` |
| 2026-03-24 16:02:45 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git show 1402be16 --stat && echo "---" && git show 1402be16 -- foms_address_converter.py | h` |
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
