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
