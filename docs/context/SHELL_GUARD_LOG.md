# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
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
| 2026-03-15 17:36:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-03-15 17:36:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F commit_msg.txt` |
| 2026-03-15 17:36:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-03-15 17:36:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git checkout production; git merge deploy -m "Merge deploy: 실측 지도 #2670 #2662 미표시 해결"; git pus` |
| 2026-03-15 17:36:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git stash; git checkout production; git merge deploy -m "Merge deploy: 실측 지도 2670 2662 미표시 해결"` |
| 2026-03-15 18:15:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:15:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:15:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; grep -n -C 5 "address" apps/api/erp_map.py` |
| 2026-03-15 18:16:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; grep -n -C 5 "def self_measurement_four_checks_done" services/erp_display.py` |
| 2026-03-15 18:17:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:18:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:19:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:19:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_flask_2629.py` |
| 2026-03-15 18:21:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_flask_2629.py` |
| 2026-03-15 18:23:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:23:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:24:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:25:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_flask_2629.py` |
| 2026-03-15 18:26:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_flask_2629.py` |
| 2026-03-15 18:26:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:27:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:27:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:28:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:30:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 18:32:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway run python scripts/debug_order_2629.py` |
| 2026-03-15 19:13:05 | allow | `-` | `python -m py_compile "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\apps\api\erp_map.py" "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\F` |
| 2026-03-15 19:18:52 | allow | `-` | `python -m py_compile "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\apps\api\erp_map.py" "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\F` |
| 2026-03-15 19:19:44 | allow | `-` | `python -c "from app import app; print('APP_OK')"` |
| 2026-03-15 19:26:56 | allow | `-` | `python -m py_compile "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\apps\api\erp_map.py" "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\F` |
| 2026-03-15 19:39:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git status` |
| 2026-03-15 19:39:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git branch --show-current` |
| 2026-03-15 19:39:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" ; git log --oneline -5` |
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
