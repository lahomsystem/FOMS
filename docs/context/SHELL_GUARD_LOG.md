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
