# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-02-28 20:29:16 | ask | `pip\s+install\s+(?!-r)` | `pip install flask` |
| 2026-03-01 12:18:47 | allow | `-` | `(payload에 command 없음)` |
| 2026-03-01 12:30:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Remove-Item "docs\context\.hook_debug_once" -ErrorAction SilentlyContinue; Remove-Item "docs\c` |
| 2026-03-01 12:30:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; echo "=== SHELL_GUARD_LOG ==="; Get-Content "docs\context\SHELL_GUARD_LOG.md"; echo ""; echo "` |
| 2026-03-01 12:30:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "docs\context\HOOK_PAYLOAD_DEBUG.jsonl") { python -c "import json; [print(json.d` |
| 2026-03-01 12:32:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; echo "=== SHELL_GUARD_LOG (last 5 rows) ==="; Get-Content "docs\context\SHELL_GUARD_LOG.md" | ` |
| 2026-03-01 12:32:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import sys; sys.path.insert(0, '.cursor/hooks'); from shared_utils import find_key_` |
| 2026-03-01 12:32:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $hooks = @("session_start.py", "session_stop.py", "guard_shell.py", "track_edits.py", "pre_com` |
| 2026-03-01 12:32:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $payload = '{"conversation_id":"test-verify","workspace_roots":["/c:/Users/USER/OneDrive/Deskt` |
| 2026-03-01 12:32:51 | allow | `-` | `echo test` |
| 2026-03-01 12:32:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; echo '{"conversation_id":"test-verify","workspace_roots":["/c:/Users/USER/OneDrive/Desktop/SY/` |
| 2026-03-01 12:37:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch -a` |
| 2026-03-01 12:37:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add .cursor/hooks/guard_shell.py .cursor/hooks/hook_payload_debug.py .cursor/hooks/post_ta` |
| 2026-03-01 12:38:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-01 12:38:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash pop` |
| 2026-03-01 12:55:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git branch --show-current` |
| 2026-03-01 12:55:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/css/erp-pro.css static/css/style-pro-max.css; git add templates/layout.html tem` |
| 2026-03-01 12:55:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-01 12:56:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-01 12:58:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import sys sys.path.insert(0, '.') from app import create_app app = create_app() w` |
| 2026-03-01 12:58:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import sys sys.path.insert(0, '.') from app import app with app.test_client() as c` |
| 2026-03-01 12:59:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_client() as c: for path in ['/', '/erp/dashboard` |
| 2026-03-01 17:13:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; Get-ChildItem -Path "templates\partials\chat_scripts*.html" | ForEach-Object { $n = (Get-Cont` |
| 2026-03-01 17:51:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; Get-ChildItem -Path "templates\partials" -Filter "chat_scripts*.html" | ForEach-Object { $n =` |
| 2026-03-01 17:52:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " # Simulate line count: layout up to {% block content %} then chat content then {%` |
| 2026-03-01 17:53:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " from app import app with app.test_client() as c: rv = c.get('/chat') if rv.status` |
| 2026-03-01 17:53:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $files = @('templates/partials/chat_scripts_core.html','templates/partials/chat_scripts_light` |
| 2026-03-01 17:53:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $all = Get-Content "templates/partials/chat_scripts_core.html","templates/partials/chat_scrip` |
| 2026-03-01 17:53:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $all = Get-Content "templates/partials/chat_scripts_core.html","templates/partials/chat_scrip` |
| 2026-03-01 17:55:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; foreach ($f in (Get-ChildItem "templates\partials\chat_scripts*.html")) { $content = Get-Cont` |
| 2026-03-01 17:57:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " from app import app # Test bundle render (no login - will 302 for /chat/scripts.j` |
| 2026-03-01 18:01:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $base = 0; $files = @('templates/partials/chat_scripts_core.html','templates/partials/chat_sc` |
| 2026-03-01 18:11:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git diff HEAD` |
| 2026-03-01 18:12:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; cat templates/partials/chat_scripts_dom.html | grep -n "addEventListener('click'"` |
| 2026-03-01 18:21:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " from app import app with app.test_request_context(): from flask import render_tem` |
| 2026-03-01 18:21:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " from app import app with app.test_request_context(): from flask import render_tem` |
| 2026-03-01 18:21:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " from app import app with app.test_request_context(): from flask import render_tem` |
| 2026-03-01 18:22:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " with open('temp_script.js', 'r', encoding='utf-8') as f: lines = f.read().splitli` |
| 2026-03-01 18:23:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " with open('templates/partials/chat_styles.html', 'r', encoding='utf-8') as f: con` |
| 2026-03-01 18:23:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " with open('templates/partials/chat_styles.html', 'r', encoding='utf-8') as f: lin` |
| 2026-03-01 18:55:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c " from app import app with app.test_request_context(): from flask import render_tem` |
| 2026-03-01 19:02:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git add . ; git commit --trailer "Made-with: Cursor" -F commit_msg.txt ; git push origin depl` |
| 2026-03-01 19:02:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git checkout production ; git merge deploy ; git push origin production ; git checkout deploy` |
| 2026-03-01 19:02:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git add docs/context/SHELL_GUARD_LOG.md ; git commit --trailer "Made-with: Cursor" -m "chore:` |
| 2026-03-01 19:02:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git push origin deploy` |
| 2026-03-02 10:29:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "from app import app; from apps.erp_completion_page import erp_completion_page_bp; ` |
| 2026-03-02 10:38:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "from app import app; from apps.api.erp_orders_completion import erp_orders_complet` |
| 2026-03-02 11:21:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-02 11:22:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add app.py apps/erp_completion_page.py apps/api/erp_orders_completion.py templates/erp_com` |
| 2026-03-02 11:22:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg_deploy.txt` |
| 2026-03-02 11:22:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-02 12:03:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-02 12:04:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/partials/erp_completion_scripts.html templates/partials/erp_completion_style` |
| 2026-03-02 12:04:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg_deploy.txt; git push origin deploy` |
| 2026-03-02 13:39:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-02 13:39:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add apps/api/erp_orders_completion.py templates/erp_completion_dashboard.html templates/pa` |
| 2026-03-02 13:39:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg_deploy.txt; git push origin deploy` |
| 2026-03-02 17:17:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "import app; print('OK')"` |
| 2026-03-02 17:20:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "import app; print('OK')"` |
| 2026-03-02 17:25:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "from apps.api.personal_board import api_summary; print('OK')"` |
| 2026-03-02 18:33:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-02 18:33:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-02 18:34:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status` |
| 2026-03-02 18:35:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-02 18:35:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash pop` |
| 2026-03-02 19:11:17 | allow | `-` | `ls "C:\Users\USER\.cursor\projects\c-Users-USER-OneDrive-Desktop-SY-program-lahomproject-FOMS\mcps\user-postgres\tools"` |
| 2026-03-02 19:16:26 | allow | `-` | `ls "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\admin\"` |
| 2026-03-02 19:20:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python -c "import app; print('OK')"` |
| 2026-03-02 20:33:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git status --short` |
| 2026-03-02 20:40:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python .cursor/hooks/cleanup_temp.py` |
| 2026-03-02 20:51:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python scripts/run_notifications_migration.py "postgresql://postgres:XMuhzNDZDeBlQStbmUQymJTG` |
| 2026-03-02 20:51:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; python scripts/run_notifications_migration.py "postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDa` |
| 2026-03-02 20:55:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git status` |
| 2026-03-02 21:40:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; (Get-Content "templates\layout.html" | Measure-Object -Line).Lines ; (Get-Content "templates\` |
| 2026-03-02 21:48:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $lines = Get-Content "templates\partials\erp_construction_scripts.html"; $line858 = $lines[85` |
| 2026-03-02 21:49:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $lines = Get-Content "templates\partials\erp_construction_scripts.html"; for ($i = 0; $i -lt ` |
| 2026-03-02 21:50:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $layout = Get-Content "templates\layout.html"; $blockStart = 0; for ($i = 0; $i -lt $layout.C` |
| 2026-03-02 21:51:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $content = [System.IO.File]::ReadAllText("templates\partials\erp_construction_scripts.html", ` |
| 2026-03-02 21:52:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; $line = (Get-Content "templates\partials\erp_construction_scripts.html")[596]; $bytes = [Syst` |
| 2026-03-02 22:12:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git status` |
| 2026-03-02 22:12:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git add templates/partials/erp_construction_scripts.html templates/erp_as_dashboard.html temp` |
| 2026-03-02 22:12:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-02 22:12:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git push origin deploy` |
| 2026-03-02 22:13:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git checkout production ; git merge deploy -m "Merge branch 'deploy' into production"` |
| 2026-03-02 22:13:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git push origin production` |
| 2026-03-02 22:14:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git checkout deploy` |
| 2026-03-03 09:29:59 | allow | `-` | `wc -l "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_construction_scripts.html"` |
| 2026-03-03 09:30:06 | allow | `-` | `(Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_construction_scripts.html").Count` |
| 2026-03-03 09:31:18 | allow | `-` | `(Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\erp_construction_modals.html" -Tail 5)` |
| 2026-03-03 09:44:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-03 09:45:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Made-with: Cursor" -F .git_commit_msg.txt` |
| 2026-03-03 09:45:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add .git_commit_msg.txt; git commit --trailer "Made-with: Cursor" -m "chore: remove tempor` |
| 2026-03-03 11:00:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app"` |
| 2026-03-03 11:18:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-03 11:18:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Made-with: Cursor" -F .git_commit_msg.txt` |
| 2026-03-03 11:18:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add .git_commit_msg.txt; git status` |
| 2026-03-03 11:19:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F .git_commit_msg2.txt` |
| 2026-03-03 11:19:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/context/COMPACT_CHECKPOINT.md docs/context/SHELL_GUARD_LOG.md; git status` |
| 2026-03-03 11:19:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/context/EDIT_LOG.md` |
| 2026-03-03 11:20:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F .git_commit_msg3.txt` |
| 2026-03-03 11:20:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-03 11:23:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; (Get-Content "templates\partials\erp_dashboard_scripts_detail.html").Count` |
| 2026-03-03 11:25:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-Content "templates\partials\erp_dashboard_scripts_detail.html" -Tail 25` |
| 2026-03-03 11:40:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $d = Get-Content "templates\partials\erp_dashboard_scripts_detail.html" -Raw; $dom = Get-Conte` |
| 2026-03-03 11:42:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " with open('templates/partials/erp_dashboard_scripts_detail.html', 'r', encoding='u` |
| 2026-03-03 13:21:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-03-03 13:21:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-03 13:22:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status -s` |
| 2026-03-03 13:22:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-03 13:22:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash list` |
| 2026-03-03 13:23:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash pop stash@{1}` |
| 2026-03-03 13:23:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash pop "stash@{1}"` |
| 2026-03-03 13:42:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-03-03 13:42:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Made-with: Cursor" -F commit_msg_deploy.txt` |
| 2026-03-03 13:42:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-03 13:42:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-03 13:51:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-03-03 13:51:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-03 13:52:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-03 13:52:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy` |
| 2026-03-04 10:43:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-03-04 10:43:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-03-04 10:43:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-04 10:43:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-04 10:49:01 | allow | `-` | `grep -rn "api/orders/completion" apps/api/` |
| 2026-03-04 14:32:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-04 14:32:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-04 14:32:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status` |
| 2026-03-04 14:33:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin production` |
| 2026-03-04 14:33:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout deploy; git stash list` |
| 2026-03-04 22:25:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app"` |
| 2026-03-04 22:36:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from apps.api.erp_orders_structured import erp_orders_structured_bp, api_get_order_` |
| 2026-03-04 23:07:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-03-04 23:07:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a` |
| 2026-03-04 23:08:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status -s` |
