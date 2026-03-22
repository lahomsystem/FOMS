# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-03-15 19:39:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git diff --stat` |
| 2026-03-15 19:40:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git add -A` |
| 2026-03-15 22:21:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 22:21:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status` |
| 2026-03-15 22:22:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-15 22:22:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash pop` |
| 2026-03-15 22:32:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 22:32:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/map_snapshot.py; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-15 22:32:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-15 22:32:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy -m "Merge deploy: geocode failed pink fix"; git push` |
| 2026-03-15 22:32:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; del commit_msg.txt` |
| 2026-03-15 22:38:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from services.map_snapshot import build_measurement_map_query, _measurement_search_` |
| 2026-03-15 22:39:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 22:39:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/api/erp_map.py services/map_snapshot.py docs/evolution/ORDER_2662_MAP_MARKER_ROOT` |
| 2026-03-15 22:39:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-15 22:39:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy -m "Merge deploy: map limit 500, order ID search"; g` |
| 2026-03-15 22:39:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; del commit_msg.txt` |
| 2026-03-15 22:54:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 22:56:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-15 22:56:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from services.map_snapshot import _measurement_date_variants assert _measurement_d` |
| 2026-03-15 22:56:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from services.map_snapshot import _measurement_date_variants r = _measurement_date` |
| 2026-03-15 22:56:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from services.map_snapshot import _measurement_date_variants assert _measurement_d` |
| 2026-03-15 22:57:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 22:57:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/map_snapshot.py services/order_date_sync.py; git commit --trailer "Made-with:` |
| 2026-03-15 22:57:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-15 22:57:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy -m "Merge deploy: 3월 16일` |
| 2026-03-15 22:57:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-15 23:00:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from services.map_snapshot import _measurement_date_variants v = _measurement_date` |
| 2026-03-15 23:00:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.app_context(): from db import get_db from services.ma` |
| 2026-03-15 23:03:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from sqlalchemy import create_engine, text engine = create_engine('sqlite:///:memo` |
| 2026-03-15 23:08:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.app_context(): from db import get_db from services.ma` |
| 2026-03-15 23:13:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 23:13:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add services/map_snapshot.py scripts/diagnose_measurement_date_missing.py; git commit --tr` |
| 2026-03-15 23:13:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-15 23:14:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git pull origin production; git merge deploy -m "Merge deploy: 동일 좌표 ` |
| 2026-03-15 23:14:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-16 09:05:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from app import app; print('APP_OK')"` |
| 2026-03-16 09:08:54 | allow | `-` | `wc -l "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_beta_js.html" 2>nul || powershell -Command "(Get-Content 'c:\Users\USE` |
| 2026-03-16 09:08:58 | allow | `-` | `powershell -Command "(Get-Content 'c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_beta_js.html').Count"` |
| 2026-03-17 08:08:43 | allow | `-` | `cat Procfile` |
| 2026-03-18 09:24:57 | allow | `-` | `wc -l "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/css/erp-pro.css"` |
| 2026-03-18 09:33:23 | allow | `-` | `ls c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/docs/plans/` |
| 2026-03-18 15:19:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-18 15:26:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-18 15:27:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-18 15:27:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_construction_filters_grid.html templates/partials/erp_construct` |
| 2026-03-18 15:27:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-18 15:27:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-18 15:32:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-18 15:32:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-03-18 15:32:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status` |
| 2026-03-18 15:32:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-18 15:33:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-18 15:42:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-18 15:47:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-18 15:53:40 | allow | `-` | `wc -l "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\css\style.css" "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\css` |
| 2026-03-18 15:53:45 | allow | `-` | `Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\css\style.css" | Measure-Object -Line; Get-Content "c:\Users\USER\OneDrive\Deskt` |
| 2026-03-19 08:29:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-19 08:30:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (Get-Content "templates\partials\erp_beta_js.html" | Measure-Object -Line).Lines` |
| 2026-03-19 08:33:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-19 08:33:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-19 08:33:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status` |
| 2026-03-19 08:33:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only` |
| 2026-03-19 08:33:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-19 08:34:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-19 08:34:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash pop` |
| 2026-03-19 09:14:29 | allow | `-` | `python -m py_compile apps/erp_dashboard.py` |
| 2026-03-19 09:32:55 | allow | `-` | `python -m py_compile apps/erp_as_page.py` |
| 2026-03-19 11:49:58 | allow | `-` | `python -m py_compile apps/erp_shipment_page.py` |
| 2026-03-19 13:42:22 | allow | `-` | `git blame -L 44,92 -- "apps/erp_shipment_page.py"` |
| 2026-03-19 13:42:24 | allow | `-` | `git blame -L 84,139 -- "services/order_date_sync.py"` |
| 2026-03-19 13:42:25 | allow | `-` | `git blame -L 858,864 -- "templates/erp_shipment_dashboard.html"` |
| 2026-03-19 13:42:32 | allow | `-` | `git blame -L 15,18 -- "apps/api/orders.py"` |
| 2026-03-19 13:42:34 | allow | `-` | `git blame -L 730,732 -- "apps/api/orders.py"` |
| 2026-03-19 13:42:36 | allow | `-` | `git blame -L 217,225 -- "apps/api/erp_orders_as.py"` |
| 2026-03-19 13:42:37 | allow | `-` | `git blame -L 858,864 -- templates/erp_shipment_dashboard.html` |
| 2026-03-19 13:42:38 | allow | `-` | `git blame -L 56,96 -- "services/as_content_safety.py"` |
| 2026-03-19 13:43:02 | allow | `-` | `git blame -L 166,189 -- "apps/erp_shipment_page.py"` |
| 2026-03-19 13:43:04 | allow | `-` | `git blame -L 317,336 -- "apps/erp_shipment_page.py"` |
| 2026-03-19 13:43:06 | allow | `-` | `git blame -L 155,161 -- "services/erp_display.py"` |
| 2026-03-19 13:43:08 | allow | `-` | `git blame -L 289,295 -- "apps/api/erp_orders_as.py"` |
| 2026-03-19 13:58:10 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order, OrderScheduleDate; from sqlalchemy import func; from sqlalchemy.sql import and_` |
| 2026-03-19 13:58:21 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order, OrderScheduleDate; from sqlalchemy import func; app.app_context().push(); db=ge` |
| 2026-03-19 13:58:30 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order, OrderScheduleDate; from sqlalchemy import func; app.app_context().push(); db=ge` |
| 2026-03-19 13:59:30 | allow | `-` | `python -c "from models import Order; o=Order(received_date='2026-03-19', customer_name='x', phone='x', address='x', product='x'); import sys; print(type(o.sched` |
| 2026-03-19 13:59:39 | allow | `-` | `python -c "from models import Order; from apps.api.orders import _build_order_update_response; o=Order(received_date='2026-03-19', customer_name='x', phone='x',` |
| 2026-03-19 13:59:48 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order; from sqlalchemy import or_, func; app.app_context().push(); db=get_db(); base=d` |
| 2026-03-19 14:01:47 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order; app.app_context().push(); db=get_db(); rows=db.query(Order).filter(Order.status` |
| 2026-03-19 14:02:59 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order; from sqlalchemy import or_, and_, func; app.app_context().push(); db=get_db(); ` |
| 2026-03-19 14:20:57 | allow | `-` | `pytest "tests/test_shipment_dashboard_regression.py" -q` |
| 2026-03-19 14:23:10 | allow | `-` | `pytest "tests/test_shipment_dashboard_regression.py" -q` |
| 2026-03-19 14:23:34 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-19 14:25:09 | allow | `-` | `python -c "from services.as_content_safety import as_content_html_to_text; print(repr(as_content_html_to_text('<div><b>경첩</b> 교체</div><div><font color=\'red\'>긴` |
| 2026-03-19 14:25:16 | allow | `-` | `python -c "from services.as_content_safety import as_content_html_to_text; print(repr(as_content_html_to_text('<div><b>hinge</b> replace</div><div><font color=\` |
| 2026-03-19 14:26:01 | allow | `-` | `pytest "tests/test_shipment_dashboard_regression.py" -q` |
| 2026-03-19 14:28:34 | allow | `-` | `pytest "tests/test_shipment_dashboard_regression.py" -q` |
| 2026-03-19 14:29:16 | allow | `-` | `pytest "tests/test_shipment_dashboard_regression.py" -q` |
| 2026-03-19 14:30:45 | allow | `-` | `pytest tests/test_shipment_dashboard_regression.py -q` |
| 2026-03-19 14:35:36 | allow | `-` | `python -c 'from app import app; from db import get_db; from models import Order; from sqlalchemy.orm import selectinload; import json; statuses=("AS","AS_RECEIV` |
| 2026-03-19 14:35:51 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order; from sqlalchemy.orm import selectinload; import json; statuses=('AS','AS_RECEIV` |
| 2026-03-19 14:36:02 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order, OrderScheduleDate; app.app_context().push(); db=get_db(); import json; statuses` |
| 2026-03-19 14:36:09 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order, OrderScheduleDate; import json; app.app_context().push(); db=get_db(); statuses` |
| 2026-03-19 14:36:34 | allow | `-` | `python "scripts/backup_order_schedule_dates.py"` |
| 2026-03-19 14:36:45 | allow | `-` | `python "scripts/restore_order_schedule_dates.py" --input "backups/order_schedule_dates-20260319-143638.json" --dry-run` |
| 2026-03-19 14:36:55 | allow | `-` | `python -c "from app import app; from db import get_db; from models import Order; import json; app.app_context().push(); db=get_db(); rows=[{'id':o.id,'status':o` |
| 2026-03-19 14:37:08 | allow | `-` | `python "scripts/backfill_phase4_dates.py" --dry-run --order-id 1083 --verbose` |
| 2026-03-19 14:41:26 | allow | `-` | `railway status` |
| 2026-03-19 14:42:09 | allow | `-` | `railway run python -c "from app import app; from db import get_db; from models import Order, OrderScheduleDate; import json; app.app_context().push(); db=get_db` |
| 2026-03-19 14:42:49 | allow | `-` | `Start-Sleep -Seconds 10` |
| 2026-03-19 14:43:13 | allow | `-` | `railway run python "scripts/backup_order_schedule_dates.py" --output "backups/remote-production-order_schedule_dates-20260319-remote.json"` |
| 2026-03-19 14:43:50 | allow | `-` | `Start-Sleep -Seconds 8` |
| 2026-03-19 14:44:05 | allow | `-` | `railway run python "scripts/backfill_phase4_dates.py" --dry-run --order-id 1798 --verbose` |
| 2026-03-19 14:44:43 | allow | `-` | `railway run python "scripts/backfill_phase4_dates.py" --verbose` |
| 2026-03-19 14:45:22 | allow | `-` | `Start-Sleep -Seconds 10` |
| 2026-03-19 14:45:39 | allow | `-` | `Start-Sleep -Seconds 15` |
| 2026-03-19 14:46:03 | allow | `-` | `Start-Sleep -Seconds 20` |
| 2026-03-19 14:46:35 | allow | `-` | `Start-Sleep -Seconds 30` |
| 2026-03-19 14:47:16 | allow | `-` | `railway run python -c "from app import app; from db import get_db; from models import OrderScheduleDate; import json; app.app_context().push(); db=get_db(); cou` |
| 2026-03-19 14:47:44 | allow | `-` | `railway run python -c "from app import app; from db import get_db; from models import OrderScheduleDate; from sqlalchemy import func; import json; app.app_conte` |
| 2026-03-19 14:48:22 | allow | `-` | `railway run python -c "from app import app; from db import get_db; from models import OrderScheduleDate; from sqlalchemy import func; import json; app.app_conte` |
| 2026-03-19 14:49:09 | allow | `-` | `Stop-Process -Id 430492` |
| 2026-03-19 14:49:15 | allow | `-` | `railway run python "scripts/backfill_phase4_dates.py" --order-id 1798 --verbose` |
| 2026-03-19 14:49:46 | allow | `-` | `railway run python -c "from app import app; from db import get_db; from models import Order; import json; app.app_context().push(); db=get_db(); statuses=('AS',` |
| 2026-03-19 14:50:22 | allow | `-` | `Start-Sleep -Seconds 10` |
| 2026-03-19 14:50:56 | allow | `-` | `railway run python "scripts/_tmp_apply_selected_schedule_dates.py" --order-ids 1776 2636 2475 2070 2364 2623 2587 2382 2186 2440 2259 2508 2487 2497 2572 2191 2` |
| 2026-03-19 14:52:02 | allow | `-` | `Start-Sleep -Seconds 10` |
| 2026-03-19 14:52:20 | allow | `-` | `railway run python -c "from app import app; from db import get_db; from models import OrderScheduleDate; from sqlalchemy import func; import json; app.app_conte` |
| 2026-03-19 14:52:51 | allow | `-` | `Start-Sleep -Seconds 10` |
| 2026-03-19 14:53:07 | allow | `-` | `railway run python -c "from app import app; from db import get_db; from models import Order, OrderScheduleDate; from sqlalchemy import func; import json; app.ap` |
| 2026-03-19 14:53:44 | allow | `-` | `Start-Sleep -Seconds 10` |
| 2026-03-19 14:54:08 | allow | `-` | `railway run python "scripts/restore_order_schedule_dates.py" --input "backups/remote-production-order_schedule_dates-20260319-remote.json" --dry-run` |
| 2026-03-19 14:54:44 | allow | `-` | `Start-Sleep -Seconds 10` |
| 2026-03-19 15:03:56 | allow | `-` | `python -m py_compile "apps/erp_as_page.py" ; python -c "import app; print('APP_OK')"` |
| 2026-03-19 15:04:56 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-19 15:50:51 | allow | `-` | `pytest "tests/test_erp_order_detail_preload.py" -q` |
| 2026-03-19 15:58:36 | allow | `-` | `pytest "tests/test_erp_order_detail_preload.py" -q` |
| 2026-03-19 15:58:54 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-19 16:14:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-19 16:15:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status -u` |
| 2026-03-19 16:15:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --stat` |
| 2026-03-19 16:15:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline -5` |
| 2026-03-19 16:15:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add apps/api/notifications.py apps/auth.py apps/erp_shipment_page.py && git commit -F /t` |
| 2026-03-19 16:15:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin deploy` |
| 2026-03-19 16:15:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin deploy:production` |
| 2026-03-19 16:18:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -1` |
| 2026-03-19 16:31:29 | allow | `-` | `Get-Command railway` |
| 2026-03-19 16:31:38 | allow | `-` | `railway status` |
| 2026-03-19 16:31:40 | allow | `-` | `railway environment` |
| 2026-03-19 16:31:51 | allow | `-` | `railway service` |
| 2026-03-19 16:31:53 | allow | `-` | `railway status --help` |
| 2026-03-19 16:32:03 | allow | `-` | `railway status --json` |
| 2026-03-19 16:41:34 | allow | `-` | `railway status` |
| 2026-03-19 16:41:37 | allow | `-` | `railway domain` |
| 2026-03-19 16:41:56 | allow | `-` | `$resp = Invoke-WebRequest -Uri "https://lahom-production.up.railway.app/static/css/erp-pro.css" -Method Head; Write-Output "STATUS=$($resp.StatusCode)"; Write-O` |
| 2026-03-19 16:41:59 | allow | `-` | `$resp = Invoke-WebRequest -Uri "https://lahom-production.up.railway.app/erp/dashboard" -MaximumRedirection 0 -ErrorAction SilentlyContinue; if ($resp) { Write-O` |
| 2026-03-19 16:50:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway variables 2>&1 | Select-String -Pattern "FLASK_ENV|RAILWAY_ENVIRONMENT|WHITENOISE"` |
| 2026-03-19 22:11:05 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-19 22:11:37 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-19 22:11:49 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && for f in apps/erp_dashboard.py apps/erp_production_page.py apps/erp_construction_page.py app` |
| 2026-03-19 22:12:03 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && grep -n "from flask import" apps/erp_dashboard.py apps/erp_production_page.py apps/erp_const` |
| 2026-03-19 22:12:12 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && grep -n "flash\|session\b" apps/api/erp_shipment_settings.py | head -10` |
| 2026-03-19 22:14:11 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-19 22:21:28 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3 && echo "---" && python -c "from serv` |
| 2026-03-19 22:23:13 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-19 22:25:39 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-19 22:47:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-19 22:51:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-19 22:52:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-03-19 22:52:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-19 22:55:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat HEAD` |
| 2026-03-19 22:55:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- apps/erp_construction_page.py` |
| 2026-03-19 22:55:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- apps/erp_measurement_dashboard.py` |
| 2026-03-19 22:55:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- services/erp_order_detail.py services/db_indexes.py` |
| 2026-03-19 22:55:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- templates/layout.html templates/erp_shipment_dashboard.html static/js/erp/mea` |
| 2026-03-19 22:55:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- templates/partials/erp_construction_filters_grid.html` |
| 2026-03-19 22:57:25 | allow | `-` | `rg -n "block scripts" "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\layout.html"` |
| 2026-03-19 22:59:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-19 23:00:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat HEAD` |
| 2026-03-19 23:03:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-19 23:04:18 | allow | `-` | `Select-String -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\erp_shipment_dashboard.html" -Pattern "endblock|block scripts|html2ca` |
| 2026-03-19 23:04:26 | allow | `-` | `$content = Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\erp_shipment_dashboard.html" -Raw; $lines = $content -split "`n"; ` |
| 2026-03-19 23:04:34 | allow | `-` | `$content = Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_construction_filters_grid.html" -Raw; $lines = $conte` |
| 2026-03-19 23:05:00 | allow | `-` | `$content = Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_construction_filters_grid.html" -Raw; $lines = $conte` |
| 2026-03-19 23:05:37 | allow | `-` | `$content = Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\layout.html" -Raw; $lines = $content -split "`n"; Write-Host "Tota` |
| 2026-03-19 23:05:43 | allow | `-` | `Select-String -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\layout.html" -Pattern "block scripts|flatpickr|Bootstrap" | Select-Ob` |
| 2026-03-19 23:05:49 | allow | `-` | `$content = Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\layout.html"; $i = 0; foreach ($line in $content) { $i++; if ($lin` |
| 2026-03-19 23:06:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import ast, sys files = [ 'apps/erp_measurement_dashboard.py', 'apps/erp_construct` |
| 2026-03-19 23:08:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " with open('templates/layout.html', encoding='utf-8') as f: lines = f.readlines() f` |
| 2026-03-19 23:09:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-19 23:09:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat HEAD` |
| 2026-03-19 23:17:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-19 23:18:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat HEAD 2>&1` |
| 2026-03-19 23:20:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m py_compile db.py app.py services/erp_permissions.py services/db_indexes.py services/` |
| 2026-03-19 23:20:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pyflakes . 2>&1 | head -100` |
| 2026-03-19 23:20:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import ast, os, sys errors = [] for root, dirs, files in os.walk('.'): dirs[:] = [` |
| 2026-03-19 23:20:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pyflakes . 2>&1 | Select-Object -First 150` |
| 2026-03-19 23:21:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import ast, os, sys # 미사용 import 및 undefined name 등 기본 분석 errors = [] warnings = [` |
| 2026-03-19 23:21:43 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" -Name "models.py" -Recurse 2>$null | Select-Object -First 3` |
| 2026-03-19 23:21:44 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" -Name "constants.py" -Recurse 2>$null | Select-Object -First 3` |
| 2026-03-19 23:25:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-19 23:32:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git log --oneline -5` |
| 2026-03-19 23:33:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-19 23:35:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-19 23:35:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash drop; git status` |
| 2026-03-19 23:35:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/context/SHELL_GUARD_LOG.md; git commit --trailer "Made-with: Cursor" -m "chore: S` |
| 2026-03-19 23:41:18 | allow | `-` | `curl -sI "https://lahom-production.up.railway.app/static/css/erp-pro.css" 2>&1 | Select-String -Pattern "cache|Cache|max-age|content-type|status|HTTP"` |
| 2026-03-19 23:41:24 | allow | `-` | `Invoke-WebRequest -Uri "https://lahom-production.up.railway.app/static/css/erp-pro.css" -Method Head | Select-Object -ExpandProperty Headers` |
| 2026-03-19 23:41:31 | allow | `-` | `$r = Invoke-WebRequest -Uri "https://lahom-production.up.railway.app/static/css/erp-pro.css" -Method Head -UseBasicParsing; $r.StatusCode; $r.Headers | Format-T` |
| 2026-03-19 23:41:40 | allow | `-` | `$start = Get-Date; $r = Invoke-WebRequest -Uri "https://lahom-production.up.railway.app/" -UseBasicParsing 2>&1; $elapsed = (Get-Date) - $start; "StatusCode: $(` |
| 2026-03-19 23:41:50 | allow | `-` | `$urls = @( "https://lahom-production.up.railway.app/erp", "https://lahom-production.up.railway.app/erp/construction", "https://lahom-production.up.railway.app/e` |
| 2026-03-20 08:42:39 | allow | `-` | `python -c "from services.business_calendar import business_days_between; import datetime; print(business_days_between(datetime.date(2025,1,1), datetime.date(202` |
| 2026-03-20 08:45:40 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "from apps.erp_production_page import erp_production_page_bp; print('IMPORT_OK')"` |
| 2026-03-20 08:46:24 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-20 08:46:59 | allow | `-` | `cd "c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS" && git diff --stat` |
| 2026-03-20 08:54:11 | allow | `-` | `ls /c/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/apps/api/` |
| 2026-03-20 08:54:59 | allow | `-` | `mkdir -p /c/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/docs/plans` |
| 2026-03-20 09:03:58 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-20 09:06:12 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && python -c "import app; print('APP_OK')" 2>&1` |
| 2026-03-20 09:10:41 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && cat docs/plans/2026-03-20-large-data-search-plan.md 2>/dev/null | head -80` |
| 2026-03-20 09:10:48 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && git log --oneline -6` |
| 2026-03-20 09:16:36 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-20 09:19:09 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-03-20 10:16:28 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-03-20 10:40:34 | allow | `-` | `python -c "from app import create_app; from db import get_db; from models import Order; from sqlalchemy import text; app = create_app(); with app.app_context():` |
| 2026-03-20 10:40:51 | allow | `-` | `python check_urgent.py` |
| 2026-03-20 10:41:17 | allow | `-` | `python check_urgent.py` |
| 2026-03-20 10:44:42 | allow | `-` | `python verify_phase_a.py` |
| 2026-03-20 10:46:42 | allow | `-` | `python verify_phase_a3.py` |
| 2026-03-20 10:50:24 | allow | `-` | `grep -rn "structured_data = " apps/api/` |
| 2026-03-20 10:54:15 | allow | `-` | `alembic revision --autogenerate -m "add erp_measurement_date and erp_construction_date columns"` |
| 2026-03-20 10:54:26 | allow | `-` | `flask db migrate -m "add erp_measurement_date and erp_construction_date columns"` |
| 2026-03-20 10:54:48 | allow | `-` | `$env:PYTHONUTF8=1; alembic revision --autogenerate -m "add erp_measurement_date and erp_construction_date columns"` |
| 2026-03-20 10:55:38 | allow | `-` | `python -X utf8 -m alembic revision --autogenerate -m "add erp_measurement_date and erp_construction_date columns"` |
| 2026-03-20 10:56:15 | allow | `-` | `alembic revision --autogenerate -m "add erp_measurement_date and erp_construction_date columns"` |
| 2026-03-20 10:56:46 | allow | `-` | `ls migrations/versions` |
| 2026-03-20 10:57:48 | allow | `-` | `python -c "from app import app; from db import db_session; db_session.execute('ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_measurement_date VARCHAR(10)'); d` |
| 2026-03-20 10:58:14 | allow | `-` | `python apply_migration.py` |
| 2026-03-20 10:58:38 | allow | `-` | `python scripts/backfill_erp_date_columns.py` |
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
