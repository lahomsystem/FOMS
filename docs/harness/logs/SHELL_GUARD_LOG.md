# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-06-25 19:11:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline 65260a22 -5; git merge-base origin/production origin/deploy; git log --oneli` |
| 2026-06-25 19:11:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a --contains ddd50295; git merge-base --is-ancestor ddd50295 origin/production; ec` |
| 2026-06-25 19:11:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git merge-base --is-ancestor ddd50295 65260a22; echo "ddd50295 in production merge: $LASTEXITC` |
| 2026-06-25 19:32:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_theme.py tests/domains/test_as_dashboard_mobile.py -q` |
| 2026-06-25 19:33:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_theme.py tests/domains/test_as_dashboard_mobile.py -q` |
| 2026-06-25 19:33:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_theme.py tests/domains/test_as_dashboard_mobile.py -q` |
| 2026-06-25 19:34:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-25 19:34:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/components/foms-completion-mobile.css static/css/components/foms-as-mobile-` |
| 2026-06-25 19:38:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1` |
| 2026-06-25 19:38:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_completion_search_api.py -q --tb=short 2>&1` |
| 2026-06-25 19:38:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-06-25 19:38:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- foms/api/cs/dashboard.py templates/cs/partials/completion_scripts.html static/css/` |
| 2026-06-25 19:38:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- templates/cs/partials/completion_styles.html` |
| 2026-06-25 19:40:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_mobile_attachment_p` |
| 2026-06-25 19:40:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_completion_search_api.py tests/domains/test_as_content_saf` |
| 2026-06-25 19:40:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_completion_search_api.py tests/domains/test_as_content_saf` |
| 2026-06-25 19:41:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-06-25 19:41:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 15` |
| 2026-06-25 19:42:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-06-25 19:42:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_spec_calc_` |
| 2026-06-25 19:42:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git status -sb; git diff --stat; git log --oneline origin/deploy..deploy; gi` |
| 2026-06-25 19:42:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/cs/dashboard.py foms/services/as_content_safety.py foms/services/shipment_as_` |
| 2026-06-25 19:42:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --no-color foms/api/cs/dashboard.py foms/services/as_content_safety.py tests/domains/` |
| 2026-06-25 19:42:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5 deploy` |
| 2026-06-25 19:43:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse deploy origin/deploy; git log --oneline origin/deploy..deploy; git status -s` |
| 2026-06-25 19:43:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-remote origin refs/heads/deploy; git diff tests/domains/test_erp_order_shared_form_scri` |
| 2026-06-25 19:43:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_mobile_attachment_p` |
| 2026-06-25 19:43:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_spec_calc_f` |
| 2026-06-26 11:53:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-26 11:53:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -1; git push origin production; git ls-remote origin refs/heads/production r` |
| 2026-06-26 13:46:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-26 13:46:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_order_draft_w` |
| 2026-06-26 13:46:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-06-26 13:46:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- templates/orders/wizard/step2_products.html templates/orders/wizard/step4_confirm.` |
| 2026-06-26 13:48:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_draft_wizard.py -q --tb=short` |
| 2026-06-26 13:48:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/erp_order_draft.py static/css/components/foms-wizard.css static/js/foms/wizar` |
| 2026-06-26 13:58:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git status -sb; git diff --stat; git log --oneline origin/production..origin` |
| 2026-06-26 13:58:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff foms/api/wdcalculator/blueprint.py static/js/wdcalculator/estimate-lifecycle.js; git ` |
| 2026-06-26 13:58:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-remote origin refs/heads/deploy refs/heads/production` |
| 2026-06-26 13:58:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_wdc_order_estimates_query_count.py -q` |
| 2026-06-26 13:59:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/wdcalculator/blueprint.py static/js/wdcalculator/estimate-lifecycle.js tests/` |
| 2026-06-30 16:50:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline production; git log refs/remotes/origin/deploy..production --oneline; git` |
| 2026-06-30 16:50:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-30 16:51:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git fetch origin deploy production; git rev-parse refs/remotes/ori` |
| 2026-06-30 16:51:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-remote origin refs/heads/production refs/heads/deploy; git update-ref refs/remotes/orig` |
| 2026-06-30 19:25:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard; python -c "import app; print('APP_OK')"` |
| 2026-06-30 19:25:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff` |
| 2026-06-30 19:25:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- templates/drawing/partials/workbench_detail_body.html static/js/orders/dashboard/e` |
| 2026-06-30 19:26:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path js = Path('static/js/orders/dashboard/erp-dashboard-attac` |
| 2026-06-30 19:26:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path js = Path('static/js/orders/dashboard/erp-dashboard-detai` |
| 2026-06-30 19:27:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-06-30 19:27:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-30 19:27:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/dashboard/erp-dashboard-attachments.js static/js/orders/dashboard/erp` |
| 2026-06-30 19:40:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-06-30 19:40:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_quest_display.py -q --tb=short 2>&1 | Select-Object -L` |
| 2026-06-30 19:40:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-06-30 19:40:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 15` |
| 2026-06-30 19:45:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_quest_display.py -q --tb=short 2>&1 | Select-Object -L` |
| 2026-06-30 19:46:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_quest_display.py foms/services/erp_order_detail.py foms/services/erp` |
| 2026-06-30 19:46:18 | allow | `-` | `Start-Sleep -Seconds 90` |
| 2026-06-30 19:48:12 | allow | `-` | `curl -s "https://lahom-dev.up.railway.app/static/js/orders/order-detail-fragment.js" | Select-String -Pattern "resolveOrderRoleAssignees|buildOrderRoleAssignees` |
| 2026-06-30 19:52:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_mobile_` |
| 2026-06-30 19:53:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_mobile_` |
| 2026-06-30 19:53:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 8` |
| 2026-06-30 19:53:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_quest_display.py foms/services/orders/dashboard_dto.py foms/web/draw` |
| 2026-06-30 19:53:34 | allow | `-` | `Start-Sleep -Seconds 75` |
| 2026-06-30 19:55:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -3 --oneline; git status -sb` |
| 2026-06-30 19:56:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (Get-Item "static\js\orders\order-detail-fragment.js").Length` |
| 2026-06-30 19:56:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 58c2dd2d --stat | Select-String "order-detail-fragment"; git diff origin/deploy -- st` |
| 2026-06-30 19:56:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 58c2dd2d --stat | Select-String "erp-dashboard-detail-dom"; Select-String -Path "stat` |
| 2026-06-30 19:56:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD; git rev-parse origin/deploy; git log origin/deploy -1 --oneline` |
| 2026-06-30 19:57:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $urls = @('https://lahom-dev.up.railway.app/static/js/orders/order-detail-fragment.js','https:` |
| 2026-06-30 19:57:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_measurement_mobile_render.py::test_measurement_mobile_` |
| 2026-06-30 19:58:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard; python -c "import app; print('APP_OK')"` |
| 2026-06-30 19:58:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-dashboard-entry.js templates/partials/shared/layout_scripts.html;` |
| 2026-06-30 22:17:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_quest_display.py::test_mobile_order_detail_renders_rol` |
| 2026-07-01 09:00:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=short 2>&1 | Sele` |
| 2026-07-01 09:00:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 15` |
| 2026-07-01 09:00:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --no-color` |
| 2026-07-01 09:02:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_dashbo` |
| 2026-07-01 09:02:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-01 09:02:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 30` |
| 2026-07-01 09:03:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-07-01 09:03:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_mobile_order_display.py foms/services/estimate_service.py foms/servi` |
| 2026-07-01 09:12:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=short 2>&1 | Sele` |
| 2026-07-01 09:22:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current; git diff --stat` |
| 2026-07-01 09:23:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 8` |
| 2026-07-01 09:23:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_mobile_order_display.py foms/services/estimate_service.py foms/servi` |
| 2026-07-01 09:28:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path p = Path('docs/design/mockups/pc-erp-order-full-page-foms` |
| 2026-07-01 09:28:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/_tmp_patch_preset.py` |
| 2026-07-01 09:29:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from pathlib import Path; a=Path('docs/design/mockups/pc-erp-items-master-detail-fo` |
| 2026-07-01 09:29:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import re; from pathlib import Path; b=Path('docs/design/mockups/pc-erp-order-full-` |
| 2026-07-01 09:29:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import re; from pathlib import Path; a=Path('docs/design/mockups/pc-erp-items-maste` |
| 2026-07-01 09:29:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from pathlib import Path; p=Path('docs/design/mockups/pc-erp-order-full-page-foms.h` |
| 2026-07-01 09:29:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/_tmp_fix_label.py; Remove-Item tools/_tmp_fix_label.py` |
| 2026-07-01 09:32:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=short 2>&1 | Sele` |
| 2026-07-01 09:33:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 6` |
| 2026-07-01 09:33:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-order-shared.js templates/orders/partials/erp_order_tab.html temp` |
| 2026-07-01 09:34:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import re; from pathlib import Path; pat=re.compile(r'\s*<button type=\"button\" cl` |
| 2026-07-01 09:34:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/_tmp_rm_triggers.py; Remove-Item tools/_tmp_rm_triggers.py` |
| 2026-07-01 09:49:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-07-01 09:49:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-01 09:49:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_sticky` |
| 2026-07-01 09:50:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_add_order_page_rend` |
| 2026-07-01 09:50:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 09:50:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-07-01 09:51:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/orders/erp-items-master-detail.css static/js/orders/erp-items-master-detail` |
| 2026-07-01 09:51:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-07-01 09:51:24 | allow | `-` | `Start-Sleep -Seconds 90; Write-Output "waited"` |
| 2026-07-01 09:53:00 | allow | `-` | `if (Test-Path "$env:USERPROFILE\.claude\skills\gstack\bin\browse") { & "$env:USERPROFILE\.claude\skills\gstack\bin\browse" --help 2>&1 | Select-Object -First 20` |
| 2026-07-01 09:53:04 | allow | `-` | `try { $r = Invoke-WebRequest -Uri "https://lahom-dev.up.railway.app/static/js/orders/erp-items-master-detail.js?v=20260630a" -UseBasicParsing -TimeoutSec 30; Wr` |
| 2026-07-01 09:53:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c @" from playwright.sync_api import sync_playwright import sys BASE = 'https://lahom-` |
| 2026-07-01 09:53:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/qa/erp_md_staging_check.py` |
| 2026-07-01 09:57:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard; python -m pyt` |
| 2026-07-01 09:57:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_sp` |
| 2026-07-01 09:57:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=line` |
| 2026-07-01 09:58:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-order-shared.js templates/orders/partials/erp_order_tab.html temp` |
| 2026-07-01 10:02:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/visual/test_erp_ord` |
| 2026-07-01 10:07:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_order_shared_` |
| 2026-07-01 10:07:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 20` |
| 2026-07-01 10:08:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git diff --stat static/css/orders/erp-items-master-detail.css static/js/or` |
| 2026-07-01 10:08:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 25` |
| 2026-07-01 10:09:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/orders/erp-items-master-detail.css static/js/orders/erp-items-master-detail` |
| 2026-07-01 10:22:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat -- static/js/orders/erp-order-shared.js templates/orders/partials/` |
| 2026-07-01 10:22:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff tests/domains/test_erp_order_shared_form_scripts.py 2>&1 | Select-Object -First 5` |
| 2026-07-01 10:22:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 6` |
| 2026-07-01 10:23:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/visual/test_p1_mockup_structure.py -q --tb=short 2>&1 | Select-Object -` |
| 2026-07-01 10:23:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest -v tests/performance/test_perf_regression_guard.py tests/performance/test_sta` |
| 2026-07-01 10:24:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 5` |
| 2026-07-01 10:24:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- tests/domains/test_erp_order_shared_form_scripts.py | Select-Object -First 3;` |
| 2026-07-01 10:24:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_shared_erp_order_js` |
| 2026-07-01 10:24:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-order-shared.js templates/orders/partials/erp_order_tab.html temp` |
| 2026-07-01 10:24:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_shared_erp_order_js` |
| 2026-07-01 10:25:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/deploy:static/js/orders/erp-order-shared.js | Select-String -Pattern "free_inp` |
| 2026-07-01 10:25:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff static/js/orders/erp-order-shared.js | Select-String -Pattern "free_input" -Context 3` |
| 2026-07-01 10:25:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/main:static/js/orders/erp-order-shared.js 2>$null | Select-String -Pattern "fr` |
| 2026-07-01 10:25:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_shared_erp_order_js` |
| 2026-07-01 10:25:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -5 --oneline -- static/js/orders/erp-order-shared.js; git log -3 -p -- static/js/order` |
| 2026-07-01 10:25:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 3b6bc988:static/js/orders/erp-order-shared.js | Select-String -Pattern "free_input:" ` |
| 2026-07-01 10:25:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d:static/js/orders/erp-order-shared.js | Select-String -Pattern "free_input: e` |
| 2026-07-01 10:25:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 273ec601:static/js/orders/erp-order-shared.js | Select-String -Pattern "free_input: e` |
| 2026-07-01 10:25:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 273ec601:static/js/orders/erp-order-shared.js | Select-String -Pattern "payment:" -Co` |
| 2026-07-01 10:25:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline --all -S "free_input: erpBuildFreeInputStoredValue" -- static/js/orders/erp-` |
| 2026-07-01 10:25:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -3 --oneline origin/deploy; git log -1 -S "free_input: erpBuildFreeInputStoredValue" -` |
| 2026-07-01 10:25:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 273ec601 -- tests/domains/test_erp_order_shared_form_scripts.py` |
| 2026-07-01 10:25:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d:tests/domains/test_erp_order_shared_form_scripts.py | Select-String -Pattern` |
| 2026-07-01 10:26:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy 2>&1; git log -1 origin/deploy --oneline; python -m pytest tests/domai` |
| 2026-07-01 10:26:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD; git rev-parse origin/deploy; git status -sb` |
| 2026-07-01 10:26:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; gh run list --branch deploy --limit 3 2>&1` |
| 2026-07-01 10:33:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_order_shared_` |
| 2026-07-01 10:33:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-07-01 10:33:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_sp` |
| 2026-07-01 10:34:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 20` |
| 2026-07-01 10:34:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-order-shared.js static/js/orders/erp-spec-calc.js static/js/foms/` |
| 2026-07-01 10:34:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 30` |
| 2026-07-01 10:35:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "tools\qa") { Get-ChildItem "tools\qa" | Select-Object -First 5 Name }` |
| 2026-07-01 10:35:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem tools -Directory | Select-Object Name` |
| 2026-07-01 10:35:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tools"; dir` |
| 2026-07-01 10:35:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status tools/qa 2>&1; git ls-files tools/qa` |
| 2026-07-01 10:35:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-tree -d HEAD tools` |
| 2026-07-01 10:35:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-tree --name-only HEAD tools/` |
| 2026-07-01 10:35:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-07-01 10:43:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_add_order_page_rend` |
| 2026-07-01 10:43:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/domains/test_erp_order_shared_form_scripts.py; git commit --trailer "Co-authored` |
| 2026-07-01 10:52:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_channel_push_messages.py tests/domains/test_channel_integr` |
| 2026-07-01 10:52:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_channel_push_messages.py tests/domains/test_channel_integr` |
| 2026-07-01 10:53:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard 2>&1` |
| 2026-07-01 10:56:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_orders_structured_put.py::test_structured_put_preserve` |
| 2026-07-01 10:56:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-07-01 10:57:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-07-01 10:57:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/channel/channel_integration.py foms/api/erp_orders_structured.py foms/service` |
| 2026-07-01 10:59:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/visual/test_erp_order_edit_mobile_form.py tests/domains/test_erp_order_` |
| 2026-07-01 11:00:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d --stat; git log --oneline -10 73a4e48d; git log --oneline --all -20 --grep="` |
| 2026-07-01 11:00:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d -- templates/orders/partials/erp_order_tab_mobile.html` |
| 2026-07-01 11:00:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d -- static/js/orders/erp-order-shared.js | Select-String -Pattern "textarea|s` |
| 2026-07-01 11:00:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d^:templates/orders/partials/erp_order_tab_mobile.html | Select-String -Patter` |
| 2026-07-01 11:00:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline 479a7b68^..73a4e48d -- static/js/orders/erp-order-shared.js templates/orders` |
| 2026-07-01 11:00:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_channel_push_messages.py tests/domains/test_channel_integr` |
| 2026-07-01 11:00:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -15 -- templates/orders/partials/erp_order_tab_mobile.html static/js/orders/` |
| 2026-07-01 11:01:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d^:static/js/orders/erp-order-shared.js | Select-String -Pattern "function erp` |
| 2026-07-01 11:01:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d -- static/js/orders/erp-order-shared.js | Select-String -Pattern "^[\+\-].*(` |
| 2026-07-01 11:01:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d --stat; git show 73a4e48d -- templates/orders/partials/erp_order_tab_mobile.` |
| 2026-07-01 11:01:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from foms.services import channel_policy as cp def show(label, **data): data.setde` |
| 2026-07-01 11:01:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5 --grep="autosize" --all; git log --oneline -3 -S "erpAutosizeTextarea" --` |
| 2026-07-01 11:01:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/qa/_tmp_channel_resend_virtual.py 2>&1` |
| 2026-07-01 11:01:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d^:static/js/orders/erp-order-shared.js | Select-String -Pattern "function erp` |
| 2026-07-01 11:01:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d^:static/js/orders/erp-order-shared.js | Select-String -Pattern "spec_width|p` |
| 2026-07-01 11:01:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:PYTHONPATH="."; python tools/qa/_tmp_channel_resend_virtual.py 2>&1` |
| 2026-07-01 11:01:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show bafb47d3 --stat; git show bafb47d3 -- static/css/components/foms-form-field.css | Sel` |
| 2026-07-01 11:01:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d^:static/js/orders/erp-order-shared.js | Select-String -Pattern "product_name` |
| 2026-07-01 11:01:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d^:static/js/orders/erp-order-shared.js | Select-String -Pattern "function erp` |
| 2026-07-01 11:01:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/performance/test_perf_regression_guard.py -q --tb=short 2>&1; python to` |
| 2026-07-01 11:01:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 479a7b68 --stat; git show 479a7b68 -- templates/orders/partials/erp_order_tab_mobile.` |
| 2026-07-01 11:01:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -5 --oneline -S "erp-flex-textarea" -- static/css/components/foms-form-field.css; git ` |
| 2026-07-01 11:02:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 73a4e48d^:templates/orders/partials/erp_order_tab_mobile.html | Select-String -Patter` |
| 2026-07-01 11:08:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_order_shared_` |
| 2026-07-01 11:08:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 8` |
| 2026-07-01 11:08:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_erp_sp` |
| 2026-07-01 11:08:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- "static/css/**/foms-form-field.css" "static/css/foms-form-field.css"` |
| 2026-07-01 11:08:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_channel_push_confir` |
| 2026-07-01 11:09:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-channel-push-confirm.js static/js/orders/erp-order-shared.js temp` |
| 2026-07-01 11:09:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_mobile_erp_autosize` |
| 2026-07-01 11:10:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/components/foms-form-field.css static/css/foundation/foms-mobile-surfaces.c` |
| 2026-07-01 11:12:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log origin/deploy..HEAD --oneline 2>$null; git log HEAD..origi` |
| 2026-07-01 11:12:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a; git log origin/deploy..origin/production --oneline 2>$null; git log origin/prod` |
| 2026-07-01 11:12:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff --stat HEAD -- docs/ static/ templates/ tests/ data/ 2>$null | Selec` |
| 2026-07-01 11:12:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -5 --oneline; git rev-parse HEAD origin/deploy` |
| 2026-07-01 11:12:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- "static/css/contexts/orders/dashboard-control-tower.css" "static/css/foundation/er` |
| 2026-07-01 11:12:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short -- "**/holidays_kr_2027-2099.json" "**/holidays_kr*.json"` |
| 2026-07-01 11:13:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only -- "templates/orders/partials/"` |
| 2026-07-01 11:13:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-files "data/holidays_kr*.json"; git status --short "static/js/orders/dashboard/erp-dash` |
| 2026-07-01 11:13:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short "static/js/orders/dashboard/"` |
| 2026-07-01 11:14:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-01 11:14:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-07-01 11:14:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 11:14:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -3 --oneline -- tools/qa` |
| 2026-07-01 11:14:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "tools/qa") { Get-ChildItem "tools/qa" -Recurse | Select-Object FullName } else ` |
| 2026-07-01 11:15:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; dir tools` |
| 2026-07-01 11:15:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item "tools/qa" -Force -Recurse -ErrorAction SilentlyContinue; dir tools | Select-Objec` |
| 2026-07-01 11:15:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 11:15:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/contexts/orders/dashboard-control-tower.css static/css/foundation/erp-pro/0` |
| 2026-07-01 11:15:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F commit_msg.txt; Remo` |
| 2026-07-01 11:15:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline; git status -sb` |
| 2026-07-01 11:31:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=short 2>&1 | Sele` |
| 2026-07-01 11:31:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1 | Select-Object -Last 6` |
| 2026-07-01 11:32:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-order-shared.js static/css/components/foms-form-field.css static/` |
| 2026-07-01 11:35:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log origin/deploy..HEAD --oneline; git log HEAD..origin/deploy --oneline; ` |
| 2026-07-01 11:35:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -3 --oneline; git fetch origin deploy 2>&1; git rev-parse HEAD origin/deploy; git bran` |
| 2026-07-01 11:36:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "tools/qa") { "tools/qa EXISTS" } else { "tools/qa ok" }` |
| 2026-07-01 11:36:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 78adcbec --stat --oneline` |
| 2026-07-01 11:36:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/ --stat` |
| 2026-07-01 11:36:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard` |
| 2026-07-01 11:36:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 11:37:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/EDIT_LO` |
| 2026-07-01 11:37:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -3 --oneline; git status -sb` |
| 2026-07-01 11:41:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/visual/test_erp_order_edit_mobile_form.py -q --tb=line 2>&1 | Select-Ob` |
| 2026-07-01 11:46:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin production deploy 2>&1; git log -1 --oneline origin/production; git log -1 --` |
| 2026-07-01 11:46:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff origin/production..origin/deploy --stat -- templates/orders/partials/erp_order_tab.ht` |
| 2026-07-01 11:46:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/production:templates/orders/partials/erp_order_tab.html 2>$null | Select-Strin` |
| 2026-07-01 11:47:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/production:templates/orders/partials/erp_order_tab.html | Select-String -Patte` |
| 2026-07-01 11:47:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/production:static/js/orders/erp-order-shared.js | Select-String -Pattern "erpA` |
| 2026-07-01 11:47:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/production:static/js/orders/erp-order-shared.js | Select-String -Pattern "erpB` |
| 2026-07-01 11:47:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff origin/production..HEAD -- templates/orders/partials/erp_order_tab.html 2>&1 | Select` |
| 2026-07-01 11:47:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show origin/production:static/js/orders/erp-order-shared.js | Select-String -Pattern "cons` |
| 2026-07-01 11:47:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show refs/remotes/origin/production:templates/orders/partials/erp_order_tab.html | Out-Fil` |
| 2026-07-01 11:49:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=short 2>&1 | Sele` |
| 2026-07-01 11:49:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=short 2>&1` |
| 2026-07-01 11:50:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-07-01 11:50:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff static/css/components/foms-form-field.css static/css/foundation/erp-pro/04-filter-tab` |
| 2026-07-01 11:50:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard 2>&1` |
| 2026-07-01 11:50:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-07-01 11:51:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/orders/partials/erp_order_tab.html templates/orders/partials/erp_order_js.ht` |
| 2026-07-01 11:51:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy 2>&1` |
| 2026-07-01 11:51:45 | allow | `-` | `Start-Sleep -Seconds 45` |
| 2026-07-01 12:00:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q --tb=short 2>&1; pytho` |
| 2026-07-01 12:00:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_erp_order_page_incl` |
| 2026-07-01 12:00:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q 2>&1` |
| 2026-07-01 12:01:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_shared_erp_order_js` |
| 2026-07-01 13:07:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat; git log -3 --oneline` |
| 2026-07-01 13:07:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff static/js/orders/erp-order-shared.js templates/orders/partials/erp_order_tab.html tem` |
| 2026-07-01 13:07:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_order_shared_` |
| 2026-07-01 13:08:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-order-shared.js templates/orders/partials/erp_order_js.html templ` |
| 2026-07-01 13:09:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy 2>&1; git status -sb; git log origin/deploy..HEAD --oneline; git log -` |
| 2026-07-01 13:09:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "tools/qa") { "tools/qa EXISTS" } else { "ok" }` |
| 2026-07-01 13:09:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD origin/deploy; git log origin/deploy..HEAD --oneline; git show b747200a --s` |
| 2026-07-01 13:09:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log origin/deploy..HEAD --oneline; git log HEAD..origin/deploy --oneline` |
| 2026-07-01 13:09:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard` |
| 2026-07-01 13:09:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 13:10:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/COMPACT` |
| 2026-07-01 13:21:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_order_attachment_permissions.py -q` |
| 2026-07-01 13:21:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-07-01 13:21:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-07-01 13:24:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_shared_erp_order_js` |
| 2026-07-01 13:24:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/orders/erp-order-shared.js templates/orders/partials/erp_order_js.html tests` |
| 2026-07-01 13:25:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- foms/services/order_attachment_permissions.py foms/api/files/common.py foms/api/fi` |
| 2026-07-01 13:25:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- static/js/orders/erp-order-shared.js foms/services/order_attachment_permissions.py` |
| 2026-07-01 13:25:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short foms/services/order_attachment_permissions.py static/js/orders/erp-order-sh` |
| 2026-07-01 13:25:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD -- static/js/orders/erp-order-shared.js | Select-Object -First 80` |
| 2026-07-01 13:27:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-07-01 13:27:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 13:28:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/order_attachment_permissions.py foms/api/files/common.py foms/api/files/` |
| 2026-07-01 13:39:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 740b254c --stat; git diff 740b254c^..740b254c` |
| 2026-07-01 13:39:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 740b254c --stat; git show 740b254c --no-color` |
| 2026-07-01 13:40:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_order_attachment_permissions.py -q` |
| 2026-07-01 13:41:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff 740b254c^..740b254c -- static/js/orders/erp-order-shared.js` |
| 2026-07-01 13:41:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline 848efdbc; git log -3 --oneline -- static/js/orders/erp-order-shared.js` |
| 2026-07-01 13:41:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 3fa79e2b:static/js/orders/erp-order-shared.js | Select-String -Pattern "erpCanDeleteA` |
| 2026-07-01 13:41:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show 3fa79e2b --stat | Select-Object -First 20; git diff 3fa79e2b 740b254c -- static/js/or` |
| 2026-07-01 13:41:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff 2bb423e1 3fa79e2b -- static/js/orders/erp-order-shared.js | Select-String -Pattern "e` |
| 2026-07-01 14:05:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_order_attachment_permissions.py -q` |
| 2026-07-01 14:05:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-07-01 14:05:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_order_attachment_permissions.py -q` |
| 2026-07-01 14:05:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 14:06:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/order_attachment_permissions.py foms/api/files/order_routes.py templates` |
| 2026-07-01 14:39:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin deploy 2>&1; git status -sb; git log origin/deploy..HEAD --oneline; git log -` |
| 2026-07-01 14:39:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "tools/qa") { "BLOCK: tools/qa" } else { "ok" }` |
| 2026-07-01 14:39:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD origin/deploy; git log origin/deploy..HEAD --oneline; git show 3fa79e2b --s` |
| 2026-07-01 14:39:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard` |
| 2026-07-01 14:39:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-07-01 14:40:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/COMPACT` |
