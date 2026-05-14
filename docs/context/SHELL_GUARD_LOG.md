# Shell Guard Log

> Claude Code Hook(`PreToolUse:Bash`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-16 11:53:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && cat static/js/wdcalculator/README.md 2>/dev/null || echo "FILE_NOT_FOUND"` |
| 2026-04-16 11:53:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && ls foms/web/wdcalculator/ 2>/dev/null && echo "---" && cat foms/web/wdcalculator/README.md 2` |
| 2026-04-16 11:53:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && ls docs/context/wdcalculator* 2>/dev/null || echo "NOT_FOUND"` |
| 2026-04-16 11:53:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline -5` |
| 2026-04-16 11:53:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && ls data/ 2>/dev/null | head -20` |
| 2026-04-16 11:54:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline -2 && echo "---" && python -c "import app; print('APP_OK')" 2>&1` |
| 2026-04-16 11:55:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git rm static/js/wdcalculator/README.md 2>&1` |
| 2026-04-16 11:55:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q 2>&1 | tail -20` |
| 2026-04-16 11:56:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -3` |
| 2026-04-16 11:56:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add docs/context/wdcalculator-static-js-chunk-map.md foms/web/wdcalculator/README.md tes` |
| 2026-04-16 11:56:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && grep -n "final-audit-gap-closure" docs/ARCHIVE_INDEX.md | head -5` |
| 2026-04-16 11:56:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add docs/plans/2026-04-16-strict-final-canonical-tree-final-audit-gap-closure-plan.md &&` |
| 2026-04-16 11:56:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && ls tools/harness/ptc_workspace_cleanup.ps1 tools/harness/ptc_workspace_hygiene_probe.ps1 2>/` |
| 2026-04-16 11:56:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git rm --cached data/ops_browser_qa.db 2>&1 || echo "NOT_TRACKED"` |
| 2026-04-16 11:56:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git ls-files data/ops_browser_qa.db` |
| 2026-04-16 11:57:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && rm -f data/ops_browser_qa.db && echo "DELETED" && ls data/*.db 2>/dev/null || echo "NO_DB_FI` |
| 2026-04-16 11:57:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && powershell -NoProfile -File tools/harness/ptc_workspace_cleanup.ps1 -RecursePyCache 2>&1` |
| 2026-04-16 11:57:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && powershell -NoProfile -File tools/harness/ptc_workspace_hygiene_probe.ps1 -RecursePyCache 2>` |
| 2026-04-16 11:58:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && powershell -NoProfile -File tools/harness/ptc_workspace_cleanup.ps1 -RecursePyCache 2>&1 && ` |
| 2026-04-16 11:58:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status --short --ignored 2>&1 | head -30` |
| 2026-04-16 11:58:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add tools/harness/ptc_workspace_cleanup.ps1 tools/harness/ptc_workspace_hygiene_probe.ps` |
| 2026-04-16 11:59:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline -3` |
| 2026-04-16 11:59:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests -q 2>&1 | tail -5` |
| 2026-04-16 12:01:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add docs/plans/2026-04-16-ptc-b7-run-record.md docs/AI_STATUS.md docs/ARCHIVE_INDEX.md d` |
| 2026-04-16 12:01:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline -5` |
| 2026-04-16 12:35:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -c "import app; print('APP_OK')" 2>&1 | tail -2` |
| 2026-04-16 12:35:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python tools/harness/verify_result.py --json 2>&1 | tail -5` |
| 2026-04-16 12:35:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python tools/harness/verify_result.py --json 2>&1 | grep -E "(PASS|FAIL|OK|ERROR|success)" |` |
| 2026-04-16 12:35:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q 2>&1 | tail -3` |
| 2026-04-16 12:40:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q 2>&1 | tail -3` |
| 2026-04-16 12:43:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests -q 2>&1 | tail -5` |
| 2026-04-16 12:47:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && powershell -NoProfile -File tools/harness/strict_canonical_b12_clean_room.ps1 -Ref HEAD -Run` |
| 2026-04-16 12:49:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && powershell -NoProfile -File tools/harness/ptc_workspace_cleanup.ps1 -RecursePyCache 2>&1 && ` |
| 2026-04-16 12:49:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add docs/AI_STATUS.md && cat > /tmp/fag_b4_commit.txt << 'EOF' docs: FAG-B4 final exactn` |
| 2026-04-16 12:50:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline -6` |
| 2026-04-16 13:21:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline eb01c5d7..HEAD 2>&1 | wc -l` |
| 2026-04-16 13:21:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --stat eb01c5d7..HEAD 2>&1 | tail -3` |
| 2026-04-16 13:21:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline eb01c5d7..HEAD 2>&1` |
| 2026-04-16 13:21:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --stat eb01c5d7..HEAD -- 'foms/' 2>&1 | tail -5` |
| 2026-04-16 13:21:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git show eb01c5d7 --name-only --format="" 2>&1 | head -5 && echo "---" && git ls-tree --name` |
| 2026-04-16 13:21:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --stat eb01c5d7..HEAD 2>&1 | grep -E "^\s+[0-9]+ files" | head -3` |
| 2026-04-16 13:21:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --name-status eb01c5d7..HEAD 2>&1 | awk '{print $1}' | sort | uniq -c | sort -rn` |
| 2026-04-16 13:21:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --name-status eb01c5d7..HEAD 2>&1 | awk '{print $1}' | sed 's/R[0-9]*/R/' | sort | ` |
| 2026-04-16 13:24:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && cat C:\Users\USER\AppData\Local\Temp\claude\c--Users-USER-OneDrive-Desktop-SY-program-lahomp` |
| 2026-04-20 15:10:55 | allow | `-` | `find c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/foms/services -name "db_url_resolver*" 2>/dev/null` |
| 2026-04-20 15:11:31 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && git log --oneline -20 -- db.py foms/services/db_url_resolver.py` |
| 2026-04-20 15:11:35 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && git show ac3f0ec1 --stat` |
| 2026-04-20 15:12:10 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && git show b202f575 --stat` |
| 2026-04-20 15:13:56 | allow | `-` | `cd c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS && grep -n "DATABASE_PUBLIC_URL\|railway.internal\|UnicodeDecode" docs/guides/RAILWAY_LOCAL_TO_RE` |
| 2026-04-21 09:46:56 | allow | `-` | `wc -l c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/measurement/dashboard-columns.js c:/Users/USER/OneDrive/Desktop/SY/program/lahomproj` |
| 2026-04-21 09:51:55 | allow | `-` | `wc -l "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\static\js\measurement\mobile.js" "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS` |
| 2026-04-21 09:53:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && python -m pytest tests/domains/test_measurement_js_contract.py -x -q 2>&1 | tail -40` |
| 2026-04-21 09:53:40 | allow | `-` | `node -e "new Function(require('fs').readFileSync('c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/measurement/dashboard.js','utf8')); cons` |
| 2026-04-21 09:55:28 | allow | `-` | `node -e "new Function(require('fs').readFileSync('c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/measurement/image-export.js','utf8')); c` |
| 2026-04-21 10:33:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git status && echo "---BRANCH---" && git branch --show-current && echo "---UPSTREAM---" && g` |
| 2026-04-21 10:48:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline -5` |
| 2026-04-21 10:48:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git diff --stat static/js/measurement/dashboard.js static/js/measurement/manual-rows.js stat` |
| 2026-04-21 10:49:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add static/js/measurement/dashboard.js static/js/measurement/manual-rows.js static/js/me` |
| 2026-04-21 10:52:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git add scripts/maintenance/erp_beta_placeholder_backfill.py && git commit -F c:/tmp/foms_co` |
| 2026-04-21 10:52:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git push origin feature/modular-monolith-wip 2>&1` |
| 2026-04-21 10:53:05 | allow | `-` | `rm c:/tmp/foms_commit_msg_measurement.txt c:/tmp/foms_commit_msg_backfill.txt` |
| 2026-04-21 11:01:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git fetch origin deploy production feature/modular-monolith-wip 2>&1 && echo "---" && echo "` |
| 2026-04-21 11:03:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git log --oneline --merges -5 origin/production && echo "---" && git show --stat --format="%` |
| 2026-04-21 11:03:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && echo "local deploy:" && git rev-parse deploy 2>&1 && echo "origin/deploy:" && git rev-parse ` |
| 2026-04-21 11:03:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout deploy && git merge --ff-only feature/modular-monolith-wip && git push origin d` |
| 2026-04-21 11:03:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout production && git merge --no-ff deploy -F c:/tmp/foms_merge_deploy_msg.txt && g` |
| 2026-04-21 11:03:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" && git checkout feature/modular-monolith-wip && rm c:/tmp/foms_merge_deploy_msg.txt 2>&1` |
| 2026-05-13 16:35:13 | allow | `-` | `ls "Add In Program/" 2>&1 | head -20` |
| 2026-05-13 16:35:14 | allow | `-` | `ls foms/web/wdcalculator/ foms/platform/ 2>&1 | head -30` |
| 2026-05-13 16:35:15 | allow | `-` | `test -f package.json && echo "ROOT_PKG_EXISTS" || echo "ROOT_PKG_MISSING"; ls static/wdplanner/ 2>&1 | head -5` |
| 2026-05-13 16:35:22 | allow | `-` | `ls "Add In Program/WDPlanner/" 2>&1 | head -10; echo "---"; test -f "Add In Program/WDPlanner/package.json" && head -30 "Add In Program/WDPlanner/package.json"` |
| 2026-05-13 16:35:23 | allow | `-` | `wc -l docs/plans/2026-05-13-foms-brain-ax-designer-blueprint.md docs/plans/2026-05-13-foms-brain-ax-designer-blueprint-v2-implementation-map.md 2>&1` |
| 2026-05-13 17:02:56 | allow | `-` | `test -d tests/harness && echo "TESTS_HARNESS_EXISTS" || echo "TESTS_HARNESS_MISSING"; test -d tools/harness && ls tools/harness/ | head -10` |
| 2026-05-13 17:03:06 | allow | `-` | `test -f tools/harness/audit_designer_stack.py && echo "AUDIT_EXISTS" || echo "AUDIT_NOT_CREATED_YET"` |
