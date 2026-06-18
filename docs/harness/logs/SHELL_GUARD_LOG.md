# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-06-17 09:11:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/css/foundation/erp-pro/11-queue-family-mobile.css" "templates/partials/shared/` |
| 2026-06-17 09:11:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy -m "merge: deploy → production (모바일 작업 큐 페이저 1줄 표시)"` |
| 2026-06-17 09:13:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_mobile_order_` |
| 2026-06-17 09:13:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 09:14:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git add foms/services/erp_mobile_order_display.py static/css/compon` |
| 2026-06-17 09:14:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production; git checkout deploy; git merge production -m "merge: production → ` |
| 2026-06-17 09:45:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_spec_width_eval_contract_node_checks.js; node tests/support/wd` |
| 2026-06-17 09:45:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_base_components_contract_node_checks.js` |
| 2026-06-17 09:45:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_base_components_contract_node_checks.js` |
| 2026-06-17 09:45:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/contracts/wdcalculator/test_pr` |
| 2026-06-17 09:45:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff` |
| 2026-06-17 09:46:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short static/js/wdcalculator/spec-width-eval.js tests/support/wdcalculator_spec_w` |
| 2026-06-17 09:46:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_spec_width_eval_contract_node_checks.js; node tests/support/wd` |
| 2026-06-17 09:46:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/wdcalculator/test_current_estimate_contracts.py -q 2>&1` |
| 2026-06-17 09:47:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/wdcalculator/test_pricing_core_contracts.py -q 2>&1` |
| 2026-06-17 09:47:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/performance/test_perf_regression_guard.py tests/contracts/wdcalculator/` |
| 2026-06-17 09:48:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_current_estimate_contract_node_checks.js 2>&1` |
| 2026-06-17 09:48:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_current_estimate_contract_node_checks.js 2>&1` |
| 2026-06-17 09:48:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-06-17 09:48:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current; git diff --stat` |
| 2026-06-17 09:48:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/wdcalculator/spec-width-eval.js static/js/wdcalculator/primary-form.js stati` |
| 2026-06-17 10:30:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/visual/test_scheduler_panel_compact.py::test_erp_order_measurement_pane` |
| 2026-06-17 10:30:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-06-17 10:31:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL="sqlite:///tests/visual/visual_local.sqlite"; python -m pytest tests/visual/` |
| 2026-06-17 10:31:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL="sqlite:///tests/visual/visual_local.sqlite"; python -m pytest tests/visual/` |
| 2026-06-17 10:32:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL="sqlite:///tests/visual/visual_local.sqlite"; python -m pytest tests/visual/` |
| 2026-06-17 10:32:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL="sqlite:///tests/visual/visual_local.sqlite"; python -m pytest tests/visual/` |
| 2026-06-17 10:32:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:DATABASE_URL="sqlite:///tests/visual/visual_local.sqlite"; python -m pytest tests/visual/` |
| 2026-06-17 10:33:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat` |
| 2026-06-17 10:33:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1 | Select-Object -Last 5` |
| 2026-06-17 10:33:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1` |
| 2026-06-17 10:33:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 2>&1 | Select-Object -Last 15` |
| 2026-06-17 10:34:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/contexts/orders/erp-order-measurement-panel.css static/css/foundation/erp-p` |
| 2026-06-17 10:34:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy 2>&1` |
| 2026-06-17 10:38:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_mobile_attachment_p` |
| 2026-06-17 10:38:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/domains/test_erp_order_shared_form_scripts.py; git commit --trailer "Co-authored` |
| 2026-06-17 10:42:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_permissions.p` |
| 2026-06-17 10:42:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_permissions.py tests/domains/test_menu_config.py -q --` |
| 2026-06-17 10:42:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json; python -m pytest tests/domains/test_erp_mobile_l` |
| 2026-06-17 10:42:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff --stat; git log -3 --oneline` |
| 2026-06-17 10:43:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/cs/dashboard.py foms/platform/http.py foms/services/context_processors.py fom` |
| 2026-06-17 10:59:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_mobile_order_` |
| 2026-06-17 10:59:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_mobile_order_display.py tests/domains/test_measurement` |
| 2026-06-17 11:00:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/visual/test_p1_mockup_structure.py -k "queue_card" -q --tb=short` |
| 2026-06-17 11:00:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py tests/domains/test_produc` |
| 2026-06-17 11:00:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py tests/domains/test_produc` |
| 2026-06-17 11:00:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 11:01:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current; git diff --stat` |
| 2026-06-17 11:01:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_mobile_order_display.py foms/web/construction/dashboard.py foms/web/` |
| 2026-06-17 11:01:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-06-17 11:04:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py -q --tb=short; python -c ` |
| 2026-06-17 11:04:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py -q --tb=short` |
| 2026-06-17 11:04:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/construction_dashboard_display.py foms/web/construction/dashboard.py tem` |
| 2026-06-17 11:09:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_p` |
| 2026-06-17 11:09:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py -q --tb=short` |
| 2026-06-17 11:09:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/domains/test_erp_order_detail_preload.py; git commit --trailer "Co-authored-by: ` |
| 2026-06-17 11:17:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py tests/domains/test_erp_or` |
| 2026-06-17 11:17:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_construction_dashboard_mobile.py -q --tb=short` |
| 2026-06-17 11:18:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/shared/erp_attachment_preview_modal.html static/js/foms/erp-attachm` |
| 2026-06-17 11:27:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_pac_b1_partials_shared_htm` |
| 2026-06-17 11:30:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path p = Path('templates/production/partials/scripts.html') li` |
| 2026-06-17 11:30:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path p = Path('templates/production/partials/scripts.html') li` |
| 2026-06-17 11:30:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_pac_b1_partials_shared_htm` |
| 2026-06-17 11:30:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_pac_b1_partials_shared_htm` |
| 2026-06-17 11:30:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-06-17 11:30:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-06-17 11:31:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --no-color` |
| 2026-06-17 11:34:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_attachment_preview_` |
| 2026-06-17 11:34:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/components/foms-form-field.css static/js/foms/mobile-detail-attachments.js ` |
| 2026-06-17 11:37:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only HEAD; git status -s` |
| 2026-06-17 11:37:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-17 11:37:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --audit` |
| 2026-06-17 11:37:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --audit --json 2>$null | python -c "import sys,json; d=json.loa` |
| 2026-06-17 11:37:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --audit --json > .perf_audit.json; python -c "import json; d=js` |
| 2026-06-17 11:37:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/performance/test_perf_regression_guard.py -q` |
| 2026-06-17 11:37:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import json from collections import Counter fs=json.load(open('.perf_audit.json',e` |
| 2026-06-17 11:37:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --audit --json | Out-File -Encoding utf8 .perf_audit.json; pyth` |
| 2026-06-17 11:46:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path def strip_open_attachment_preview_modal(path: str) -> Non` |
| 2026-06-17 11:47:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_constr` |
| 2026-06-17 11:47:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/visual/test_erp_order_edit_mobile_form.py tests/domains/test_erp_order_` |
| 2026-06-17 11:48:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/performance/test_perf_regressi` |
| 2026-06-17 11:48:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff` |
| 2026-06-17 11:49:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short static/js/foms/attachment-preview-modal-bridge.js; git ls-files static/js/f` |
| 2026-06-17 11:49:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_attachment_preview_` |
| 2026-06-17 11:49:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py tests/domains/test_constr` |
| 2026-06-17 11:50:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/foms/erp-attachment-preview-open.js static/js/foms/attachment-preview-modal-` |
| 2026-06-17 13:55:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard` |
| 2026-06-17 13:55:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python -m pytest tests/domains/test_erp_order_shared_` |
| 2026-06-17 13:55:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-06-17 13:55:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 13:56:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff` |
| 2026-06-17 13:56:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff -- foms/services/estimate_service.py static/js/orders/erp-order-shared.js static/css/` |
| 2026-06-17 13:59:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_mobile_order_display.py tests/domains/test_estimate_se` |
| 2026-06-17 13:59:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_shared_form_scripts.py::test_erp_amount_surfaces` |
| 2026-06-17 13:59:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "static/css/foundation/erp-pro/04-filter-table-badges-buttons.css" "static/js/orders/d` |
| 2026-06-17 13:59:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Co-authored-by: Cursor <cursoragent@cursor.com>" -F commit_msg.txt; Remo` |
| 2026-06-17 14:13:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git diff; git log -3 --oneline` |
| 2026-06-17 14:13:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "templates/orders/partials/estimate_pane.html"; git commit --trailer "Co-authored-by: ` |
| 2026-06-17 14:16:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession; $loginPage = Invoke-Web` |
| 2026-06-17 14:16:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession; Invoke-WebRequest -Uri ` |
| 2026-06-17 14:17:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession; Invoke-WebRequest -Uri ` |
| 2026-06-17 14:18:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_search_overlay.py tests/domains/test_completion_searc` |
| 2026-06-17 14:19:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/runtime/erp-shell.js foms/api/cs/dashboard.py foms/web/cs/completion_dashboa` |
| 2026-06-17 14:21:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log -1 --oneline deploy; git log -1 --oneline origin/deploy 2>` |
| 2026-06-17 14:21:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-06-17 14:27:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_queue_card_schedule.py tests/domains/test_foms_search_over` |
| 2026-06-17 14:27:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/perf/perf_scan.py --guard; python -c "import app; print('APP_OK')"` |
| 2026-06-17 14:29:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_queue_card_schedule.py tests/domains/test_foms_search_over` |
| 2026-06-17 14:29:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 14:30:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 14:30:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat` |
| 2026-06-17 14:30:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current; git log -3 --oneline` |
| 2026-06-17 14:30:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/erp_mobile_order_display.py foms/services/erp_template_filters.py foms/s` |
| 2026-06-17 14:30:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-06-17 14:31:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "$env:USERPROFILE\.claude\skills\gstack\bin\gstack-update-check") { & "$env:USER` |
| 2026-06-17 14:31:49 | allow | `-` | `Write-Host "=== .cursor/skills ==="; Get-ChildItem "$env:USERPROFILE\.cursor\skills" -ErrorAction SilentlyContinue | Select-Object Name, Mode; Write-Host "=== .` |
| 2026-06-17 14:31:56 | allow | `-` | `Get-ChildItem "$env:USERPROFILE\.cursor\skills" -Force -Recurse -Depth 2 -ErrorAction SilentlyContinue | Select-Object FullName; Get-ChildItem "$env:USERPROFILE` |
| 2026-06-17 14:32:13 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; if (-not (Test-Path $bash)) { $bash = (Get-Command bash -ErrorAction SilentlyContinue).Source }; Write-Host "bash: ` |
| 2026-06-17 14:32:19 | allow | `-` | `node --version 2>&1; bun --version 2>&1; npx --version 2>&1; codex --version 2>&1` |
| 2026-06-17 14:32:19 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc "curl -fsSL https://raw.githubusercontent.com/garrytan/gstack/main/setup | grep -n 'cursor\|INSTALL_CUR` |
| 2026-06-17 14:32:36 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc "curl -fsSL https://raw.githubusercontent.com/garrytan/gstack/main/setup | grep -n 'INSTALL_' | head -3` |
| 2026-06-17 14:32:42 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc "curl -fsSL https://raw.githubusercontent.com/garrytan/gstack/main/setup | grep -in 'cursor' | head -30` |
| 2026-06-17 14:33:01 | allow | `-` | `claude --version 2>&1; Write-Host "---"; Get-ChildItem "$env:USERPROFILE\.claude\skills" -Directory | Select-Object -First 30 Name; Write-Host "--- codex gstack` |
| 2026-06-17 14:33:13 | allow | `-` | `cmd /c "dir /b /ad %USERPROFILE%\.claude\skills 2>nul"; cmd /c "dir /b /ad %USERPROFILE%\.codex\skills 2>nul"; cmd /c "dir /b /ad %USERPROFILE%\.cursor\skills 2` |
| 2026-06-17 14:33:18 | deny | `git\s+reset\s+--hard\s+origin` | `$bash = "C:\Program Files\Git\bin\bash.exe"; $gstackDir = "$env:USERPROFILE\.claude\skills\gstack"; & $bash -lc "cd '$($gstackDir -replace '\\','/')' && git sta` |
| 2026-06-17 14:33:21 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; $gstackDir = "$env:USERPROFILE\.claude\skills\gstack"; & $bash -lc "cd '/c/Users/USER/.claude/skills/gstack' && git` |
| 2026-06-17 14:33:29 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; $oldVer = Get-Content "$env:USERPROFILE\.claude\skills\gstack\VERSION" -ErrorAction SilentlyContinue; Write-Host "O` |
| 2026-06-17 14:33:50 | allow | `-` | `Get-Content "$env:USERPROFILE\.claude\skills\gstack\VERSION"; Test-Path "$env:USERPROFILE\.claude\skills\gstack.bak"; cmd /c "dir /b %USERPROFILE%\.claude\skill` |
| 2026-06-17 14:33:55 | allow | `-` | `Test-Path "$env:USERPROFILE\.claude\skills\gstack\browse\dist\browse.exe"; Test-Path "$env:USERPROFILE\.claude\skills\gstack.bak\browse\dist\browse.exe"; Get-Ch` |
| 2026-06-17 14:33:59 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; Copy-Item -Recurse -Force "$env:USERPROFILE\.claude\skills\gstack.bak\browse\dist" "$env:USERPROFILE\.claude\skills` |
| 2026-06-17 14:34:12 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc "BROWSE_BIN='/c/Users/USER/.claude/skills/gstack/browse/dist/browse.exe'; ls -la \$BROWSE_BIN; if [ -x ` |
| 2026-06-17 14:34:16 | allow | `-` | `Test-Path "$env:USERPROFILE\.claude\skills\gstack\browse\dist\browse.exe"; (Get-Item "$env:USERPROFILE\.claude\skills\gstack\browse\dist\browse.exe" -ErrorActio` |
| 2026-06-17 14:34:22 | allow | `-` | `$dist = "$env:USERPROFILE\.claude\skills\gstack\browse\dist"; Get-ChildItem $dist | Select-Object Name, Length; Copy-Item "$dist\browse.exe" "$dist\browse" -For` |
| 2026-06-17 14:34:27 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && ./setup --host auto' 2>&1 | Select-Object -Last 60` |
| 2026-06-17 14:34:34 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'BROWSE_BIN="/c/Users/USER/.claude/skills/gstack/browse/dist/browse"; chmod +x "$BROWSE_BIN" "$BROWSE_B` |
| 2026-06-17 14:34:38 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'BROWSE="/c/Users/USER/.claude/skills/gstack/browse/dist/browse"; touch "$BROWSE" "$BROWSE.exe"; cd /c/` |
| 2026-06-17 14:34:45 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && bun install && ./setup --host auto' 2>&1 | Select-Object -La` |
| 2026-06-17 14:35:02 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && rm -rf node_modules && bun install && ls node_modules/diff/p` |
| 2026-06-17 14:35:22 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && touch browse/dist/browse browse/dist/browse.exe && ./setup -` |
| 2026-06-17 14:35:28 | allow | `-` | `Test-Path "$env:USERPROFILE\.claude\skills\gstack.bak\.agents\skills"; if (Test-Path "$env:USERPROFILE\.claude\skills\gstack.bak\.agents\skills") { (Get-ChildIt` |
| 2026-06-17 14:35:33 | allow | `-` | `Test-Path "$env:USERPROFILE\.claude\skills\gstack\qa\SKILL.md"; Test-Path "$env:USERPROFILE\.claude\skills\gstack\qa\SKILL.md.tmpl"; cmd /c "dir /b %USERPROFILE` |
| 2026-06-17 14:35:38 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && bun -e "import diff from \"diff\"; console.log(typeof diff)"` |
| 2026-06-17 14:35:43 | allow | `-` | `Test-Path "$env:USERPROFILE\.claude\skills\gstack.bak\node_modules\diff"; Get-ChildItem "$env:USERPROFILE\.claude\skills\gstack\node_modules\diff" -ErrorAction ` |
| 2026-06-17 14:35:51 | allow | `-` | `cmd /c "dir /b %USERPROFILE%\.claude\skills\gstack\node_modules\diff 2>nul"; cmd /c "dir /b %USERPROFILE%\.claude\skills\gstack\node_modules 2>nul | find /i dif` |
| 2026-06-17 14:35:58 | ask | `remove-item\s+.+-recurse.+-force` | `$bash = "C:\Program Files\Git\bin\bash.exe"; Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\skills\gstack\node_modules" -ErrorAction SilentlyContinue; Co` |
| 2026-06-17 14:37:30 | allow | `-` | `python tools/harness/build_context_bundle.py --all` |
| 2026-06-17 14:38:00 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-17 14:38:00 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-17 14:38:00 | allow | `-` | `pytest tests/harness/test_context_bundle.py -q` |
| 2026-06-17 14:38:14 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && touch browse/dist/browse browse/dist/browse.exe && ./setup -` |
| 2026-06-17 14:39:30 | allow | `-` | `Select-String -Path "$env:USERPROFILE\.claude\skills\gstack\setup" -Pattern "cursor|CURSOR" | Select-Object -First 15 LineNumber, Line` |
| 2026-06-17 14:39:30 | allow | `-` | `irm https://raw.githubusercontent.com/JuliusBrussee/caveman/main/install.ps1 | iex; npx -y github:JuliusBrussee/caveman -- --only cursor --only codex --only cla` |
| 2026-06-17 14:40:17 | allow | `-` | `Write-Host "=== VERSIONS ==="; Get-Content "$env:USERPROFILE\.claude\skills\gstack\VERSION"; Write-Host "=== GLOBAL SKILLS ==="; cmd /c "dir /b /ad %USERPROFILE` |
| 2026-06-17 14:40:29 | allow | `-` | `Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\skills\gstack.bak" -ErrorAction SilentlyContinue; Write-Host "backup removed"` |
| 2026-06-17 14:40:44 | allow | `-` | `cmd /c "dir %USERPROFILE%\.cursor\skills\caveman 2>nul"; cmd /c "dir %USERPROFILE%\.codex\skills\caveman 2>nul"` |
| 2026-06-17 14:40:52 | allow | `-` | `cd $env:USERPROFILE; npx -y skills add JuliusBrussee/caveman --skill caveman -a codex --yes 2>&1 | Select-Object -Last 25; npx -y skills add JuliusBrussee/cavem` |
| 2026-06-17 14:40:52 | allow | `-` | `$src = "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\.agents\skills\caveman\SKILL.md"; $targets = @("$env:USERPROFILE\.claude\skills\caveman\SKIL` |
| 2026-06-17 14:41:06 | allow | `-` | `Write-Host "HOME .agents:"; Test-Path "$env:USERPROFILE\.agents\skills\caveman\SKILL.md"; Write-Host "cursor global:"; Test-Path "$env:USERPROFILE\.cursor\skill` |
| 2026-06-17 14:41:14 | allow | `-` | `cmd /c "dir /b /ad %USERPROFILE%\.claude\skills 2>nul" | find /c /v ""; cmd /c "dir /b /ad %USERPROFILE%\.codex\skills 2>nul" | find /c /v ""; cmd /c "dir /b /a` |
| 2026-06-17 14:41:26 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && bun run gen:skill-docs --host cursor 2>&1 | tail -20'` |
| 2026-06-17 14:41:35 | ask | `remove-item\s+.+-recurse.+-force` | `$srcGstack = "$env:USERPROFILE\.claude\skills\gstack\.cursor\skills"; $dstCursor = "$env:USERPROFILE\.cursor\skills"; New-Item -ItemType Directory -Path $dstCur` |
| 2026-06-17 14:43:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short .agents/skills/caveman .agents/skills/cavecrew .agents/skills/caveman-* 2>$` |
| 2026-06-17 14:43:59 | allow | `-` | `Write-Host "SUMMARY"; Write-Host "gstack global:" (Get-Content "$env:USERPROFILE\.claude\skills\gstack\VERSION"); Write-Host "gstack repo vendor:" (Get-Content ` |
| 2026-06-17 14:48:39 | allow | `-` | `Write-Host "=== CLAUDE ==="; cmd /c "dir /b /ad %USERPROFILE%\.claude\skills 2>nul"; Write-Host "`n=== CODEX ==="; cmd /c "dir /b /ad %USERPROFILE%\.codex\skill` |
| 2026-06-17 14:48:45 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc "cd /c/Users/USER/.claude/skills/gstack && git rev-parse HEAD"` |
| 2026-06-17 14:49:00 | allow | `-` | `python -c " import re, os from pathlib import Path roots = { 'claude': Path(os.environ['USERPROFILE']) / '.claude/skills', 'codex': Path(os.environ['USERPROFILE` |
| 2026-06-17 14:49:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/audit_skills.py` |
| 2026-06-17 14:49:56 | allow | `-` | `cmd /c "dir /b /ad c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\.agents\skills 2>nul"; cmd /c "dir /b /ad c:\Users\USER\OneDrive\Desktop\SY\progr` |
| 2026-06-17 14:50:07 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc "cd /c/Users/USER/.claude/skills/gstack && git rev-parse HEAD && cat VERSION"` |
| 2026-06-17 14:50:19 | allow | `-` | `cmd /c "dir /b /ad c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\.agents\skills\gstack-* 2>nul"; Test-Path "c:\Users\USER\OneDrive\Desktop\SY\prog` |
| 2026-06-17 14:50:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $bash = "C:\Program Files\Git\bin\bash.exe"; $tmp = ".tmp\gstack-upstream-scan"; if (Test-Path` |
| 2026-06-17 14:50:28 | allow | `-` | `cmd /c "dir /b C:\Users\USER\.claude\skills\gstack\gstack-upgrade\migrations 2>nul"` |
| 2026-06-17 14:50:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/import_gstack_source_slice.py --commit c7ae63201ab193a7dc7fb7e0d812386451` |
| 2026-06-17 14:51:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools/harness/cleanup_skill_duplicates.ps1; python tools/harness/a` |
| 2026-06-17 14:51:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools/harness/setup_gstack.ps1 -WhatIf 2>&1 | Select-Object -Last ` |
| 2026-06-17 14:51:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import re, os from pathlib import Path from collections import defaultdict root = ` |
| 2026-06-17 14:51:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/audit_skills.py 2>&1 | Select-String "Total duplicate|claude:|codex:|curs` |
| 2026-06-17 14:51:33 | allow | `-` | `Test-Path "C:\Users\USER\.claude\skills\gstack-browse\SKILL.md"; Test-Path "C:\Users\USER\.claude\skills\gstack\browse\SKILL.md"` |
| 2026-06-17 14:51:43 | allow | `-` | `cmd /c "dir C:\Users\USER\.claude\skills\gstack-browse"; cmd /c "fc /b C:\Users\USER\.claude\skills\gstack-browse\SKILL.md C:\Users\USER\.claude\skills\gstack\b` |
| 2026-06-17 14:51:45 | allow | `-` | `python tools/harness/build_context_bundle.py --all` |
| 2026-06-17 14:51:45 | allow | `-` | `pytest tests/harness/test_context_bundle.py -q` |
| 2026-06-17 14:51:45 | allow | `-` | `python tools/perf/perf_scan.py --guard` |
| 2026-06-17 14:51:45 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-06-17 14:52:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools/harness/cleanup_skill_duplicates.ps1 2>&1 | Select-Object -L` |
| 2026-06-17 14:52:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/import_gstack_source_slice.py --commit c7ae63201ab193a7dc7fb7e0d812386451` |
| 2026-06-17 14:56:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/audit_skills.py 2>&1 | Select-String "Total duplicate|cursor:|claude:|cod` |
| 2026-06-17 14:56:32 | allow | `-` | `$paths = @( "$env:USERPROFILE\.cursor\skills", "$env:USERPROFILE\.cursor\skills-cursor", "$env:USERPROFILE\.claude\skills", "$env:USERPROFILE\.codex\skills", "$` |
| 2026-06-17 14:56:58 | allow | `-` | `Get-ChildItem "$env:USERPROFILE\.cursor\skills\gstack-autoplan" | Select-Object Name, Length; Get-ChildItem "$env:USERPROFILE\.claude\skills\gstack-autoplan" | ` |
| 2026-06-17 14:57:09 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc "grep -n 'cursor\|INSTALL_' /c/Users/USER/.claude/skills/gstack/setup | head -40"` |
| 2026-06-17 14:57:38 | ask | `remove-item\s+.+-recurse.+-force` | `$cursorSkills = "$env:USERPROFILE\.cursor\skills" $removed = 0 Get-ChildItem $cursorSkills -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -li` |
| 2026-06-17 14:57:52 | allow | `-` | `$bash = "C:\Program Files\Git\bin\bash.exe"; & $bash -lc 'cd /c/Users/USER/.claude/skills/gstack && touch browse/dist/browse browse/dist/browse.exe && ./setup -` |
| 2026-06-17 14:58:16 | allow | `-` | `$paths = @("$env:USERPROFILE\.cursor\skills", "$env:USERPROFILE\.cursor\skills-cursor", "$env:USERPROFILE\.claude\skills", "$env:USERPROFILE\.codex\skills") $to` |
| 2026-06-17 14:58:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import re, os from pathlib import Path from collections import defaultdict roots =` |
| 2026-06-17 14:58:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools/harness/cleanup_skill_duplicates.ps1 2>&1 | Select-Object -L` |
| 2026-06-17 14:58:37 | ask | `remove-item\s+.+-recurse.+-force` | `$codexSkills = "$env:USERPROFILE\.codex\skills"; $removed = 0; Get-ChildItem $codexSkills -Directory | Where-Object { $_.Name -like 'gstack*' } | ForEach-Object` |
| 2026-06-17 14:58:37 | allow | `-` | `python -c " import re, os from pathlib import Path from collections import defaultdict roots = [ Path(os.environ['USERPROFILE']) / '.cursor/skills', Path(os.env` |
| 2026-06-17 14:58:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/audit_skills.py 2>&1 | Select-String "Total duplicate|claude:|codex:|curs` |
| 2026-06-17 14:58:45 | allow | `-` | `python -c " import re, os from pathlib import Path from collections import defaultdict roots = [ ('cursor-skills', Path(os.environ['USERPROFILE']) / '.cursor/sk` |
| 2026-06-17 14:58:51 | allow | `-` | `Get-ChildItem "$env:USERPROFILE\.claude\skills" -Recurse -Filter "SKILL.md" | ForEach-Object { $t = Get-Content $_.FullName -TotalCount 5 -ErrorAction SilentlyC` |
| 2026-06-17 14:58:58 | ask | `remove-item\s+.+-recurse.+-force` | `Remove-Item -Recurse -Force "$env:USERPROFILE\.claude\skills\_gstack-command" -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force "$env:USERPROFILE\.code` |
| 2026-06-17 14:58:59 | allow | `-` | `python -c " import re, os from pathlib import Path roots = [ Path(os.environ['USERPROFILE']) / '.cursor/skills', Path(os.environ['USERPROFILE']) / '.cursor/skil` |
| 2026-06-17 15:10:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -vv; git log --oneline -8` |
| 2026-06-17 15:11:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline origin/deploy -3; git log --oneline origin/production -3; ` |
| 2026-06-17 15:11:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/perf/perf_scan.py --guard` |
| 2026-06-17 15:11:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline deploy...origin/production; git merge-base deploy origin/production` |
| 2026-06-17 15:11:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` |
| 2026-06-17 15:11:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/build_context_bundle.py --all` |
| 2026-06-17 15:11:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat docs/harness/bundles/` |
| 2026-06-17 15:12:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A` |
| 2026-06-17 15:16:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py::test_run_gstack_qa_wrapper_propagates` |
| 2026-06-17 15:17:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py -q` |
| 2026-06-17 15:17:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tools/harness/run_gstack_qa.ps1 tools/harness/run_codex.ps1; git commit --trailer "Co-` |
| 2026-06-17 15:17:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-06-17 15:17:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy; git push origin production; git checkout deploy` |
| 2026-06-17 15:17:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -3; git show origin/deploy:tools/harness/run_gstack_qa.ps1 | Select-String "` |
| 2026-06-17 15:18:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-files ".agents/skills/gstack/qa/"; git check-ignore -v ".agents/skills/gstack/qa/SKILL.` |
| 2026-06-17 15:18:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD; git rev-parse origin/deploy; git rev-parse origin/main; git log origin/mai` |
| 2026-06-17 15:18:39 | allow | `-` | `pwsh -NoProfile -Command "$r='c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS'; $c='.agents/skills/gstack/qa/SKILL.md.tmpl'; $p=Join-Path $r $c; Wri` |
| 2026-06-17 15:18:44 | allow | `-` | `powershell -NoProfile -Command "& { $r='c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS'; $c='.agents/skills/gstack/qa/SKILL.md.tmpl'; $p=Join-Path ` |
| 2026-06-17 15:19:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py -q` |
| 2026-06-17 15:20:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py::test_run_gstack_qa_wrapper_propagates` |
| 2026-06-17 15:20:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/harness/test_run_codex_levels.py -q` |
| 2026-06-17 15:20:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools/harness/run_gstack_qa.ps1 -Url "https://example.com" -Scenar` |
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
