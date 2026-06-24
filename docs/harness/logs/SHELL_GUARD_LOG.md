# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
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
