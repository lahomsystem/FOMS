# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-17 09:31:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p="templates\drawing\workbench_dashboard.html"; (Get-Content $p -Encoding UTF8)[283..1076] | ` |
| 2026-04-15 23:11:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=line` |
| 2026-04-15 23:14:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api"; Copy-Item "attachments_internal\blueprint.py" "files\blueprint.py" -Force; Copy-Item ` |
| 2026-04-15 23:15:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api"; Copy-Item "chat\blueprint.py" "channel\chat_blueprint.py" -Force; Copy-Item "chat\rou` |
| 2026-04-15 23:15:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api\channel"; Move-Item -Force "chat_blueprint.py" "blueprint.py"; Move-Item -Force "chat_f` |
| 2026-04-15 23:17:51 | ask | `remove-item\s+.+-recurse.+-force` | `Remove-Item -Recurse -Force "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\api\chat"; Remove-Item -Recurse -Force "c:\Users\USER\OneDrive\Des` |
| 2026-04-15 23:18:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-15 23:18:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no 2>&1 | Sel` |
| 2026-04-15 23:18:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1 | Select-Object -Last 15` |
| 2026-04-15 23:19:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services"; Copy-Item "erp_policy_internal\constants.py" "orders\erp_policy_constants.py" -F` |
| 2026-04-15 23:20:04 | allow | `-` | `Remove-Item -Recurse -Force "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services\erp_policy_internal"` |
| 2026-04-15 23:20:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no 2>&1 | Sel` |
| 2026-04-15 23:20:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -Path "foms\api" -Directory | ForEach-Object { $_.Name } | Sort-Object` |
| 2026-04-15 23:20:32 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\web" -Directory | ForEach-Object { $_.Name } | Sort-Object` |
| 2026-04-15 23:20:33 | allow | `-` | `Get-ChildItem -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services" -Directory | ForEach-Object { $_.Name } | Sort-Object` |
| 2026-04-15 23:20:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-15 23:22:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-15 23:22:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-15 23:22:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no 2>&1` |
| 2026-04-15 23:22:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" feat(strict): SLG-B1~B7 literal-gap 트랜치 마감 - templates/shared·errors 제거, partials/shared 레이` |
| 2026-04-15 23:23:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-files _commit_msg_slg.txt; git show HEAD:_commit_msg_slg.txt 2>&1 | Select-Object -Firs` |
| 2026-04-15 23:23:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rm -f _commit_msg_slg.txt; git commit --trailer "Made-with: Cursor" --amend --no-edit` |
| 2026-04-15 23:23:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:23:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" chore: 커밋 메시지 임시 파일 패턴 _commit_msg*.txt gitignore 추가 SLG UTF-8 -F 커밋 시 실수로 스테이징되는 것 방지 "@ |` |
| 2026-04-15 23:24:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:24:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" docs: SLG-B7 run record·AI_STATUS에 CLEAN_ROOM_OK·커밋 SHA 반영 HEAD f4d7410a 기준 clean-room 재증명 ` |
| 2026-04-15 23:24:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:25:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-slgb7-run-record.md docs` |
| 2026-04-15 23:25:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --format=%B` |
| 2026-04-15 23:25:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD` |
| 2026-04-15 23:26:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" docs: SLG-B7·AI_STATUS 최종 tip SHA 90cf2667로 정합 "@ | Set-Content -Path ".git_commit_msg_tip.` |
| 2026-04-15 23:27:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-slgb7-run-record.md docs` |
| 2026-04-15 23:27:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; @" docs: SLG-B7·AI_STATUS CLEAN_ROOM 증거 문구 정합 (고정 앵커 92bbb5af) 자기 참조 tip SHA 제거 "@ | Set-Conte` |
| 2026-04-15 23:27:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git push origin feature/modular-monolith-wip` |
| 2026-04-16 09:34:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\orders\partials","templates\construction\` |
| 2026-04-16 09:34:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\partials\shared"; Remove-Item -Force erp_production_*.html,erp_measurement_mobile_*.ht` |
| 2026-04-16 09:35:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 09:36:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; if (Test-Path "templates\partials\http_errors") { Remove-Item -Recurse -Force "templates\parti` |
| 2026-04-16 09:36:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=line 2>&1 | S` |
| 2026-04-16 09:36:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=line 2>&1 | Select-Object -Last 30` |
| 2026-04-16 09:37:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "tools\harness\strict_canonical_b12_clean_room.ps1" -Ref HEAD -Run` |
| 2026-04-16 09:37:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git log -1 --oneline` |
| 2026-04-16 09:38:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-16 09:39:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/platform/http.py templates/ tests/contracts/runtime/foms_namespace_surface_tests.` |
| 2026-04-16 09:39:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F ".git\COMMIT_EDITMSG_PAC.txt"` |
| 2026-04-16 09:39:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 09:40:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File "tools\harness\strict_canonical_b12_clean_room.ps1" -Ref HEAD -Run` |
| 2026-04-16 09:42:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "docs/plans/2026-04-16-pac-b2-through-b5-closeout-run-record.md" docs/AI_STATUS.md; $u` |
| 2026-04-16 09:42:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 10:33:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 10:35:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git ls-tree --name-only HEAD | Sort-Object` |
| 2026-04-16 10:36:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ptc_physical_exactness_tests.py -q` |
| 2026-04-16 10:37:47 | ask | `remove-item\s+.+-recurse.+-force` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rm -f "data/dumps/.gitkeep" "data/localdb/.gitkeep" 2>$null; if (Test-Path "data\dumps") {` |
| 2026-04-16 10:37:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ptc_physical_exactness_tests.py -q` |
| 2026-04-16 10:38:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ -q --tb=no -q 2>&1 | Select-Object -Last 25` |
| 2026-04-16 10:38:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ -q` |
| 2026-04-16 10:38:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/ptc_physical_exactness_tests.py --collect-only -q` |
| 2026-04-16 10:39:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest "tests/contracts/runtime/" --collect-only 2>&1 | Select-Object -Last 15` |
| 2026-04-16 10:39:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py --collect-only -q 2>&` |
| 2026-04-16 10:39:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts --collect-only -q 2>&1 | Select-Object -Last 5` |
| 2026-04-16 10:39:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime --collect-only` |
| 2026-04-16 10:40:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests --collect-only -q 2>&1 | Select-Object -Last 3` |
| 2026-04-16 10:41:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q; python -m pytest t` |
| 2026-04-16 10:41:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no` |
| 2026-04-16 10:43:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q --tb=no` |
| 2026-04-16 10:44:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q --tb=no` |
| 2026-04-16 10:44:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_hygiene_probe.ps1; echo "exit=$LASTEXI` |
| 2026-04-16 10:50:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 10:51:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q; powershell -NoPro` |
| 2026-04-16 10:52:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_hygiene_probe.ps1 -RecursePyCache` |
| 2026-04-16 10:52:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 10:52:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 10:54:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log -1 --oneline` |
| 2026-04-16 10:59:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 10:59:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat tools/harness/run_codex.ps1 tests/harness/test_run_codex_levels.py docs/AI_CHA` |
| 2026-04-16 10:59:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff tools/harness/run_codex.ps1 tests/harness/test_run_codex_levels.py` |
| 2026-04-16 11:00:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -u data/; git add docs/ARCHIVE_INDEX.md docs/guides/MIGRATION_GUIDE_RAILWAY.md docs/gu` |
| 2026-04-16 11:00:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p = "commit_msg_ptc.txt"; $utf8 = New-Object System.Text.UTF8Encoding $false; $t = @" feat: P` |
| 2026-04-16 11:00:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:02:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:02:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 11:09:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git status -u` |
| 2026-04-16 11:10:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat; git diff tools/harness/run_codex.ps1 | Select-Object -First 80` |
| 2026-04-16 11:10:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff tests/harness/test_run_codex_levels.py` |
| 2026-04-16 11:10:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/AI_CHANGELOG.md docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/COMPACT` |
| 2026-04-16 11:10:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p = "commit_msg_ptc2.txt"; $utf8 = New-Object System.Text.UTF8Encoding $false; $t = @" chore:` |
| 2026-04-16 11:10:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 ` |
| 2026-04-16 11:12:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md | Select-Object -First 40` |
| 2026-04-16 11:12:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg.txt"; $utf8 = New-Object Sys` |
| 2026-04-16 11:12:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:14:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:14:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat docs/harness/logs/SHELL_GUARD_LOG.md; git add docs/harness/logs/SHELL_GUARD_LO` |
| 2026-04-16 11:14:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:14:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md | Select-Object -First 25` |
| 2026-04-16 11:15:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg3.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:15:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:15:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; git diff --cached --stat` |
| 2026-04-16 11:15:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p = "commit_msg_sg4.txt"; $utf8 = New-Object System.Text.UTF8Encoding $false; $t = "chore: SH` |
| 2026-04-16 11:15:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md` |
| 2026-04-16 11:16:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg5.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:16:19 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:17:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:17:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg6.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:19:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -8 --oneline; git status -sb` |
| 2026-04-16 11:20:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git diff --stat` |
| 2026-04-16 11:20:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/runtime/SESSION_LOG.md` |
| 2026-04-16 11:21:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md docs/harness/runtime/SESSION_LOG.md; $p = "commit` |
| 2026-04-16 11:21:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:21:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg.txt"; $utf8 = New-Object Sys` |
| 2026-04-16 11:21:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:21:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff docs/harness/logs/SHELL_GUARD_LOG.md | Select-Object -First 30` |
| 2026-04-16 11:21:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg2.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:21:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:22:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_sg3.txt"; $utf8 = New-Object Sy` |
| 2026-04-16 11:22:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:22:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 11:22:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q` |
| 2026-04-16 11:22:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests -q` |
| 2026-04-16 11:24:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFu` |
| 2026-04-16 11:25:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache; powershel` |
| 2026-04-16 11:25:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git diff --stat` |
| 2026-04-16 11:26:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_final_ev.txt"; $utf8 = New-Obje` |
| 2026-04-16 11:26:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git log -3 --oneline` |
| 2026-04-16 11:26:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_tail.txt"; $utf8 = New-Object S` |
| 2026-04-16 11:26:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb` |
| 2026-04-16 11:26:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/harness/logs/SHELL_GUARD_LOG.md; $p = "commit_msg_tail2.txt"; $utf8 = New-Object ` |
| 2026-04-16 14:40:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log -1 --oneline cc3496be2a229908385b1dac4202de8616bb8da6; git log -1 --oneline eb01c5d768` |
| 2026-04-16 14:40:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat eb01c5d768c5ea6d9a52aafc2b61cf1264f92bc3 cc3496be2a229908385b1dac4202de8616bb8` |
| 2026-04-16 14:40:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff eb01c5d768c5ea6d9a52aafc2b61cf1264f92bc3 cc3496be2a229908385b1dac4202de8616bb8da6 -- ` |
| 2026-04-16 14:43:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff eb01c5d768c5ea6d9a52aafc2b61cf1264f92bc3 cc3496be2a229908385b1dac4202de8616bb8da6 -- ` |
| 2026-04-16 14:48:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js` |
| 2026-04-16 14:48:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-16 14:51:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js; python -c "import a` |
| 2026-04-16 14:53:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log -3 --oneline` |
| 2026-04-16 14:53:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $msg = @" fix: WDCalculator 사이드바 init이 loadSidebarEstimates API를 반환하도록 수정 initWdCalculatorSide` |
| 2026-04-16 14:53:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 14:54:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch -a; git fetch origin 2>&1; git log origin/deploy -1 --oneline 2>$null; git log orig` |
| 2026-04-16 14:54:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git fetch origin; git log --oneline origin/deploy..origin/feature/modular-monolith-wip | head ` |
| 2026-04-16 15:00:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 15:00:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app from flask import render_template_string with app.app_context(` |
| 2026-04-16 15:00:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_request_context('/'): html = app.jinja_env.get_t` |
| 2026-04-16 15:00:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app with app.test_request_context('/'): html = app.jinja_env.get_t` |
| 2026-04-16 15:00:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-04-16 15:01:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/admin/layout.html templates/auth/layout.html templates/channel/layout.html t` |
| 2026-04-16 15:01:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 15:17:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js; node tests/support/` |
| 2026-04-16 15:18:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_late_bootstrap_contract_node_checks.js; node tests/support/wdc` |
| 2026-04-16 15:18:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-16 15:18:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/wdcalculator/composition.js templates/wdcalculator/partials/wdcalculator_scr` |
| 2026-04-16 15:25:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-16 15:25:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_url_bootstrap_contract_node_checks.js` |
| 2026-04-16 15:25:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json 2>&1` |
| 2026-04-16 15:26:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; node tests/support/wdcalculator_url_bootstrap_contract_node_checks.js` |
| 2026-04-16 15:26:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add static/js/wdcalculator/estimate-lifecycle.js templates/wdcalculator/partials/wdcalcula` |
| 2026-04-16 15:26:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F ".git/COMMITMSG_WDC_SIDEBAR.txt"; Remove-Item ".gi` |
| 2026-04-16 16:21:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-16 16:21:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py -q` |
| 2026-04-16 16:21:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/harness/verify_result.py --json` |
| 2026-04-16 16:24:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m py_compile foms/web/orders/dashboard.py; python -m pytest tests/domains/test_dashboa` |
| 2026-04-16 16:24:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_p` |
| 2026-04-16 16:29:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 16:29:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_p` |
| 2026-04-16 16:31:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-16 16:32:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py tests/domains/test_erp_measure` |
| 2026-04-16 16:43:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 16:43:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 16:43:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_p` |
| 2026-04-16 16:44:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py::test_get_or_compute_logs_compute_ms_hi` |
| 2026-04-16 16:45:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-16 16:45:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 16:54:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short; git diff --stat` |
| 2026-04-16 16:54:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 16:54:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json 2>&1 | S` |
| 2026-04-16 16:54:45 | allow | `-` | `where.exe railway 2>$null; railway --version 2>&1` |
| 2026-04-16 16:54:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; railway status 2>&1` |
| 2026-04-16 16:55:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --name-only HEAD -- migrations/ templates/ 2>&1` |
| 2026-04-16 19:35:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log origin/HEAD..HEAD --oneline 2>$null; git log HEAD..origin/HEAD --oneli` |
| 2026-04-16 19:35:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git rev-parse HEAD; git rev-parse origin/feature/modular-monolith-wip 2>&1; git cherry -v orig` |
| 2026-04-16 19:37:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-04-16 19:37:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git reset HEAD -- _commit_msg_dmc_utf8.txt 2>$null; git status --short` |
| 2026-04-16 19:37:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git commit --trailer "Made-with: Cursor" -F _commit_msg_dmc_utf8.txt` |
| 2026-04-16 19:37:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin feature/modular-monolith-wip` |
| 2026-04-16 19:51:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 19:51:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-04-16 19:52:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 19:52:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cach` |
| 2026-04-16 19:53:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status` |
| 2026-04-16 19:53:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/common/dashboard_cache.py; git commit --trailer "Made-with: Cursor" -F "` |
| 2026-04-17 08:37:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-17 08:38:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-Content -Path "templates\orders\dashboard.html" -Encoding UTF8 | Select-Object -Skip 3 -Fi` |
| 2026-04-17 08:39:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-17 08:41:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\measurement\partials" | Out-Null; $lines ` |
| 2026-04-17 08:42:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\shipment\partials" | Out-Null; $lines = G` |
| 2026-04-17 08:42:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\cs\partials" | Out-Null; $lines = Get-Con` |
| 2026-04-17 08:44:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-17 08:44:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_dashboard_micro_cache_http_fallback.py -q --tb=short 2>&1` |
| 2026-04-17 09:02:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app rules = [] for r in app.url_map.iter_rules(): if 'GET' not in ` |
| 2026-04-17 09:02:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from app import app; rules=[]; for r in app.url_map.iter_rules(): if 'GET' not in r` |
| 2026-04-17 09:02:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "from app import app for r in sorted(app.url_map.iter_rules(), key=lambda x: str(x.r` |
| 2026-04-17 09:03:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-17 09:10:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app html_get = [] for r in app.url_map.iter_rules(): if 'GET' not ` |
| 2026-04-17 09:11:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from app import app for r in sorted(app.url_map.iter_rules(), key=lambda x: str(x.` |
| 2026-04-17 09:12:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-17 09:18:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-17 09:25:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_erp_shell_fragment_contract.py -q` |
| 2026-04-17 09:25:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json` |
| 2026-04-17 09:27:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_erp_shell_fragment_contract.py -q` |
| 2026-04-17 09:30:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p="templates\production\dashboard.html"; (Get-Content $p -Encoding UTF8)[3..128] | Set-Conten` |
| 2026-04-17 09:30:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p="templates\construction\dashboard.html"; (Get-Content $p -Encoding UTF8)[3..128] | Set-Cont` |
| 2026-04-17 09:30:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p="templates\orders\history_dashboard.html"; (Get-Content $p -Encoding UTF8)[3..583] | Set-Co` |
| 2026-04-17 09:31:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p="templates\cs\completion_dashboard.html"; (Get-Content $p -Encoding UTF8)[3..92] | Set-Cont` |
| 2026-04-17 09:31:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p="templates\drawing\workbench_dashboard.html"; (Get-Content $p -Encoding UTF8)[2..31] | Set-` |
| 2026-04-17 09:31:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $p="templates\drawing\workbench_dashboard.html"; $styleInner = (Get-Content $p -Encoding UTF8)` |
| 2026-04-17 09:31:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "templates\drawing\partials" | Out-Null; $p="templat` |
| 2026-04-17 09:31:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $import = "{% import 'drawing/partials/workbench_dashboard_macros.html' as wb %}`n"; $raw = Ge` |
| 2026-04-17 09:34:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-17 09:35:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_shell_fragment_contract.py -q --tb=short` |
| 2026-04-17 09:36:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_shell_fragment_contract.py -q --tb=short` |
| 2026-04-17 09:38:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-17 09:42:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $wb = Get-Content "templates\drawing\workbench_detail.html" -Encoding UTF8; $wb[3..1918] | Set` |
| 2026-04-17 09:42:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $all = Get-Content "templates\orders\edit_order.html" -Encoding UTF8; $new = New-Object System` |
| 2026-04-17 09:44:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $lines = Get-Content -Path "templates\shipment\settings.html" -Encoding UTF8; $body = $lines[5` |
| 2026-04-17 09:45:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-17 09:47:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_erp_shell_fragment_contract.py -q --tb=short` |
| 2026-04-17 09:58:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-17 10:00:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_` |
| 2026-04-17 10:00:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_` |
| 2026-04-17 10:02:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-17 10:05:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('.') # orders dashboard_main p = root / 'temp` |
| 2026-04-17 10:06:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('.') p = root / 'templates/orders/partials/da` |
| 2026-04-17 10:06:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path root = Path('.') # AS p = root / 'templates/cs/partials/a` |
| 2026-04-17 10:06:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from pathlib import Path p = Path('templates/orders/partials/dashboard_main.html')` |
| 2026-04-17 10:07:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tools/_ept_b7_patch_templates.py` |
| 2026-04-17 10:09:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-17 10:11:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_` |
| 2026-04-17 10:20:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; pytest ` |
| 2026-04-17 10:22:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"; python tools/harness/verify_result.py --json; python ` |
| 2026-04-17 10:24:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status -sb; git log -1 --oneline` |
| 2026-04-17 10:25:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git branch --show-current; git remote -v` |
| 2026-04-17 10:25:46 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -A; git status --short | Select-Object -First 80` |
