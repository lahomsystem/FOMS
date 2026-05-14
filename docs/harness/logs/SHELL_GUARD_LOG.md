# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-05-13 22:30:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" $msg = @" feat: FOMS Brain AX Designer V2 MVP 援ы쁽 (B0-B8 ?꾨즺) - /wdplanner-v2 蹂묓뻾 ?댁쁺 route 諛?n` |
| 2026-05-13 22:31:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin HEAD 2>&1 | Select-Object -Last 5` |
| 2026-05-13 22:34:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; dir "foms\web\designer" /b; dir "foms\api\designer" /b; dir "foms\persistence\designer" /b; di` |
| 2026-05-13 22:34:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; dir "templates\designer" /b; dir "static\designer" /b; dir "migrations\versions" /b | Select-S` |
| 2026-05-13 22:34:16 | allow | `-` | `$base = "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" Get-ChildItem "$base\foms\web\designer" | Select-Object Name Get-ChildItem "$base\foms\api` |
| 2026-05-13 22:34:18 | allow | `-` | `$base = "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" Get-ChildItem "$base\templates\designer" | Select-Object Name Get-ChildItem "$base\static\` |
| 2026-05-13 22:39:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-13 22:39:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 2` |
| 2026-05-13 22:39:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" git add "Add In Program/FOMSBrainDesigner/src/canvas/SelectionGizmo.tsx" git add "Add In Progra` |
| 2026-05-13 22:40:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin HEAD 2>&1 | Select-Object -Last 3` |
| 2026-05-13 22:41:23 | allow | `-` | `Test-Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner\scripts\copy-to-static.js" Get-ChildItem "c:\Users\USER\` |
| 2026-05-13 22:41:30 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\docs\plans" | Select-Object Name` |
| 2026-05-13 22:41:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" python -m pytest tests/domains/test_designer_routes.py tests/domains/test_designer_projects_api` |
| 2026-05-13 22:45:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 2` |
| 2026-05-13 22:45:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" git add "Add In Program/FOMSBrainDesigner/package.json" git add "docs/plans/2026-05-13-foms-bra` |
| 2026-05-13 22:45:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin HEAD 2>&1 | Select-Object -Last 3` |
| 2026-05-13 22:46:44 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tests\domains" | Where-Object {$_.Name -like "*namespace*"} | Select-Object Name` |
| 2026-05-13 22:47:00 | allow | `-` | `Select-String -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tests\domains\test_foms_namespace_imports.py" -Pattern "wdcalculator" | Select-` |
| 2026-05-13 22:47:08 | allow | `-` | `Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tests\domains\test_foms_namespace_imports.py" -Encoding UTF8 | Select-Object -First 5` |
| 2026-05-13 22:47:15 | allow | `-` | `Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tests\domains\test_foms_namespace_imports.py" -Encoding UTF8` |
| 2026-05-13 22:47:35 | allow | `-` | `Select-String -Path "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\tests\contracts\runtime\foms_namespace_surface_tests.py" -Pattern "wdcalculator` |
| 2026-05-13 22:48:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_foms_namespace_imports.py::test_slg_literal_gap_templates_` |
| 2026-05-13 22:48:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" git add tests/contracts/runtime/foms_namespace_surface_tests.py $msg = @" fix: namespace closed` |
| 2026-05-13 22:48:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin HEAD 2>&1 | Select-Object -Last 3` |
| 2026-05-13 22:54:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-13 22:55:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 2` |
| 2026-05-13 22:55:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS" git add "Add In Program/FOMSBrainDesigner/src/App.tsx" git add "Add In Program/FOMSBrainDesigne` |
| 2026-05-13 22:55:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin HEAD 2>&1 | Select-Object -Last 3` |
| 2026-05-13 23:09:18 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\WDPlanner\src" -Recurse -File | Where-Object {$_.Extension -eq ".tsx" ` |
| 2026-05-13 23:09:30 | allow | `-` | `Get-Content "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\WDPlanner\src\components\Canvas3D.tsx" | Select-Object -First 30` |
| 2026-05-13 23:09:39 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\WDPlanner\src" -Recurse -File | Select-Object FullName | ForEach-Objec` |
| 2026-05-14 08:28:44 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner\src" -Recurse -Name 2>$null | head -80` |
| 2026-05-14 08:28:52 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner\src" -Recurse -Name 2>$null | Select-Object -First 8` |
| 2026-05-14 08:28:54 | allow | `-` | `Get-ChildItem "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services\designer" -Name 2>$null; Get-ChildItem "c:\Users\USER\OneDrive\Desktop\` |
| 2026-05-14 08:37:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1` |
| 2026-05-14 08:38:13 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py tests/domains/test_designer_form` |
| 2026-05-14 08:40:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py tests/domains/test_designer_form` |
| 2026-05-14 08:40:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py::TestWardrobeFactory::test_valid` |
| 2026-05-14 08:41:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py tests/domains/test_designer_form` |
| 2026-05-14 08:42:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py tests/domains/test_designer_form` |
| 2026-05-14 08:44:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 5` |
| 2026-05-14 08:45:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 5` |
| 2026-05-14 08:46:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_command_engine.py tests/domains/test_designer_cor` |
| 2026-05-14 08:46:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_command_engine.py tests/domains/test_designer_cor` |
| 2026-05-14 08:48:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_projects_api.py -v 2>&1 | Select-Object -Last 25` |
| 2026-05-14 08:48:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py tests/domains/test_designer_form` |
| 2026-05-14 08:53:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1 | Select-Object -Last 50` |
| 2026-05-14 08:54:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1 | Select-Object -Last 40` |
| 2026-05-14 08:54:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 08:54:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff --stat HEAD 2>&1 | Select-Object -Last 30` |
| 2026-05-14 08:54:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short 2>&1 | Select-Object -First 50` |
| 2026-05-14 08:55:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short 2>&1 | Select-Object -Last 20` |
| 2026-05-14 08:55:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/domain/ontologyTypes.ts" "Add In Program/FOMSBra` |
| 2026-05-14 08:55:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-05-13-foms-brain-design-kernel-v1-execution-plan.md docs/plans/2026-05` |
| 2026-05-14 08:55:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $commitMsg = @" feat: FOMS Brain Design Kernel V1 援ы쁽 (DK-B1~B10) Atomic Ontology + Formula En` |
| 2026-05-14 08:55:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy 2>&1 | Select-Object -Last 10` |
| 2026-05-14 09:03:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-05-13-foms-brain-design-kernel-v1-execution-plan.md; $msg = "docs: Des` |
| 2026-05-14 09:29:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3` |
| 2026-05-14 09:29:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py tests/domains/test_designer_form` |
| 2026-05-14 09:29:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "foms\services\designer" -Name; Get-ChildItem "foms\api\designer" -Name; Get-Chi` |
| 2026-05-14 09:31:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 09:34:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_lui_parser.py -v 2>&1 | Select-Object -Last 35` |
| 2026-05-14 09:35:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_lui_parser.py -v 2>&1 | Select-Object -Last 30` |
| 2026-05-14 09:36:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_factory_registry.py -v 2>&1 | Select-Object -Last` |
| 2026-05-14 09:36:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 09:37:07 | allow | `-` | `New-Item -ItemType Directory -Force "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\foms\services\designer\factories" | Out-Null; New-Item -ItemTyp` |
| 2026-05-14 09:38:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_shoe_rack_factory.py -v 2>&1 | Select-Object -Las` |
| 2026-05-14 09:38:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_shoe_rack_factory.py -q 2>&1 | Select-Object -Las` |
| 2026-05-14 09:40:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_kitchen_factory.py -q 2>&1 | Select-Object -Last ` |
| 2026-05-14 09:40:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 09:44:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 09:44:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_lui_parser.py tests/domains/test_designer_factory` |
| 2026-05-14 09:45:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/schemas.py foms/services/designer/langgraph_workflows.py foms/s` |
| 2026-05-14 09:45:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $msg = @" feat: FOMS Brain Post-V1 援ы쁽 (PV2-B0~B10, Tranche 1~3) [Tranche 1 - Contract + LUI +` |
| 2026-05-14 09:46:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "Add In Program\FOMSBrainDesigner\src\ui" -Name; Get-ChildItem "Add In Program\F` |
| 2026-05-14 09:46:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "foms\services\designer\factories" -Name; Get-ChildItem "foms\persistence\design` |
| 2026-05-14 09:46:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 09:50:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-05-14-foms-brain-post-v1-roadmap-plan.md; $msg = "docs: Post-V1 怨꾪쉷??泥` |
| 2026-05-14 09:55:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git show --stat HEAD 2>&1 | Select-Object -First 30` |
| 2026-05-14 09:55:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git diff HEAD "foms/services/designer/command_engine.py" 2>&1 | Select-Object -First 10` |
| 2026-05-14 09:55:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "tests" -Name -Filter "conftest.py" -Recurse; Get-ChildItem "tests\domains" -Nam` |
| 2026-05-14 09:55:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem "migrations\versions" -Name -Filter "*designer*" | Select-Object -First 10` |
| 2026-05-14 09:55:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-Content "migrations\versions\designer_ax_initial.py" | Select-Object -First 50` |
| 2026-05-14 09:55:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-Content "migrations\versions\designer_ax_initial.py" | Select-String "rule_candidate|embed` |
| 2026-05-14 09:56:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Select-String "def test_" "tests\domains\test_designer_ai_runs.py" | Select-Object -First 5` |
| 2026-05-14 09:56:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short | Select-String "designer"` |
| 2026-05-14 09:56:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_rule_candidate.py tests/domains/test_designer_fac` |
| 2026-05-14 09:57:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 09:57:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "foms/services/designer/command_engine.py" "tests/domains/test_designer_rule_candidate` |
| 2026-05-14 10:20:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3; python -m pytest tests/d` |
| 2026-05-14 10:20:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1 | Select-Object -Last 10` |
| 2026-05-14 10:20:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/domain/constraintEngine.ts" "foms/api/designer/c` |
| 2026-05-14 10:27:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-Object -Last 3` |
| 2026-05-14 10:27:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1 | Select-Object -Last 6` |
| 2026-05-14 10:27:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_kernel.py tests/domains/test_designer_form` |
| 2026-05-14 10:29:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import urllib.request, urllib.parse, json, ssl BASE = 'https://lahom-dev.up.railwa` |
| 2026-05-14 10:29:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import requests, json, sys BASE = 'https://lahom-dev.up.railway.app' s = requests.` |
| 2026-05-14 10:30:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import requests, json BASE = 'https://lahom-dev.up.railway.app' s = requests.Sessi` |
| 2026-05-14 10:30:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tests\qa_deploy_test.py 2>&1 | Select-Object -Last 5` |
| 2026-05-14 10:31:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tests\qa_deploy_test.py 2>&1` |
| 2026-05-14 10:32:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tests\qa_deploy_test.py 2>&1` |
| 2026-05-14 10:34:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tests\qa_deploy_test.py 2>&1` |
| 2026-05-14 10:35:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:PYTHONIOENCODING = "utf-8"; python tests\qa_deploy_test.py 2>&1` |
| 2026-05-14 10:36:51 | allow | `-` | `$env:PYTHONIOENCODING = "utf-8"; cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python tests\qa_deploy_test.py 2>&1 | Select-Object -Last 25` |
| 2026-05-14 10:42:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:PYTHONIOENCODING = "utf-8"; python -c " from foms.services.designer.factory_registry impo` |
| 2026-05-14 10:43:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:PYTHONIOENCODING = "utf-8"; python -c " import os; os.environ['DATABASE_URL'] = 'sqlite:/` |
| 2026-05-14 10:46:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1 | Select-Object -Last 6` |
| 2026-05-14 10:46:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/domain/assemblyFactories.ts" "static/designer/as` |
| 2026-05-14 12:01:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-05-14 12:01:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_product_grade_contract.py -v 2>&1 | head -80` |
| 2026-05-14 12:01:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_product_grade_contract.py -v` |
| 2026-05-14 12:02:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_product_grade_contract.py -v` |
| 2026-05-14 12:02:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_*.py -q` |
| 2026-05-14 12:02:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q` |
| 2026-05-14 12:02:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status --short` |
| 2026-05-14 12:03:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/domains/test_designer_product_grade_contract.py docs/plans/PRODUCT_GRADE_STATUS.` |
| 2026-05-14 12:03:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $msg = @" PG-B0: FOMS Brain ?쒗뭹湲?Reality Reset + Product Contract Freeze - tests/domains/test_` |
| 2026-05-14 12:03:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-05-14 12:26:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pip show google-generativeai 2>$null; pip show google-genai 2>$null; pip show google-ai-genera` |
| 2026-05-14 12:27:08 | ask | `pip\s+install\s+(?!-r)` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pip install google-generativeai --quiet` |
| 2026-05-14 12:27:22 | allow | `-` | `python -c "import google.generativeai as genai; print('genai version:', genai.__version__)"` |
| 2026-05-14 12:27:29 | ask | `pip\s+install\s+(?!-r)` | `pip install google-genai --quiet; python -c "import google.genai; print('google-genai OK:', google.genai.__version__)"` |
| 2026-05-14 12:29:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "tests\fixtures\drawings" | Out-Null; echo "dir crea` |
| 2026-05-14 12:32:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_gemini_provider.py -v -k "not Live"` |
| 2026-05-14 12:32:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyAc0CnD3QhbZJyHNZgEMq1PjMecKzpx6pw"; python -m pytest tests/domain` |
| 2026-05-14 12:33:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyAc0CnD3QhbZJyHNZgEMq1PjMecKzpx6pw"; python -m pytest tests/domain` |
| 2026-05-14 12:33:47 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyAc0CnD3QhbZJyHNZgEMq1PjMecKzpx6pw"; python -c " from google impor` |
| 2026-05-14 12:34:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import os, time, json os.environ['GEMINI_API_KEY'] = 'AIzaSyAc0CnD3QhbZJyHNZgEMq1P` |
| 2026-05-14 12:34:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyAc0CnD3QhbZJyHNZgEMq1PjMecKzpx6pw"; python -c @" import os, time ` |
| 2026-05-14 12:34:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyAc0CnD3QhbZJyHNZgEMq1PjMecKzpx6pw"; python -m pytest tests/domain` |
| 2026-05-14 12:35:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String -Pattern "passed|failed|` |
| 2026-05-14 12:35:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String -Pattern "passed|failed|` |
| 2026-05-14 12:36:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/gemini_provider.py foms/services/designer/extraction_scorecard.` |
| 2026-05-14 12:36:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $msg = @" PG-B0A: Gemini Provider POC + Extraction Scorecard 援ы쁽 ?좉퇋 ?뚯씪: - foms/services/desi` |
| 2026-05-14 12:36:59 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-05-14 12:40:16 | ask | `pip\s+install\s+(?!-r)` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; pip install "pydantic>=2.9.0,<3.0.0" "pydantic-settings>=2.3.0" --dry-run --quiet 2>&1 | Selec` |
| 2026-05-14 12:40:23 | allow | `-` | `pip index versions pydantic 2>&1 | Select-String "Available" | Select-Object -First 1` |
| 2026-05-14 12:40:31 | ask | `pip\s+install\s+(?!-r)` | `pip install "pydantic==2.11.10" "pydantic-settings>=2.3.0" --quiet --dry-run 2>&1 | Select-String -Pattern "pydantic"` |
| 2026-05-14 12:40:39 | ask | `pip\s+install\s+(?!-r)` | `pip install "pydantic==2.11.10" --quiet 2>&1 | Select-String -Pattern "pydantic|install"; python -c "import pydantic; print(pydantic.VERSION)"` |
| 2026-05-14 12:40:51 | allow | `-` | `python -c "import pydantic_core; print('pydantic_core:', pydantic_core.__version__); import pydantic_settings; print('pydantic-settings:', pydantic_settings.VER` |
| 2026-05-14 12:40:56 | allow | `-` | `python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK|Error|Import"` |
| 2026-05-14 12:41:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed|error" | ` |
| 2026-05-14 12:41:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add requirements.txt; $msg = @" fix: pydantic ?섏〈??異⑸룎 ?닿껐 (google-genai 2.2.0 ?명솚) google` |
| 2026-05-14 12:44:18 | allow | `-` | `pip show google-genai 2>&1 | Select-String "Requires"` |
| 2026-05-14 12:44:25 | allow | `-` | `pip download google-genai==2.2.0 --no-deps -d /tmp/genai_check 2>&1 | Out-Null; pip show --files google-genai 2>&1 | Select-String "Requires-Dist" | Select-Obje` |
| 2026-05-14 12:45:17 | ask | `pip\s+install\s+(?!-r)` | `pip install "typing_extensions>=4.14.0,<5.0.0" --quiet 2>&1 | Select-String "install|Successfully"; python -c "import typing_extensions; print('typing_extension` |
| 2026-05-14 12:45:25 | allow | `-` | `python -c "import importlib.metadata; print('typing_extensions:', importlib.metadata.version('typing_extensions')); import app; print('APP_OK')" 2>&1 | Select-S` |
| 2026-05-14 12:45:37 | allow | `-` | `pip check 2>&1 | Select-String "google-genai|pydantic|typing" | Select-Object -First 10` |
| 2026-05-14 12:45:44 | allow | `-` | `pip check 2>&1 | Select-Object -First 20` |
| 2026-05-14 12:46:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add requirements.txt; $msg = @" fix: typing-extensions ?섏〈??異⑸룎 ?닿껐 (google-genai 2.2.0 ?명` |
| 2026-05-14 12:49:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyBXtjtOFZtCSA-jOlsTTubjMf4L9oPDKmQ"; python -m pytest tests/domain` |
| 2026-05-14 12:49:40 | allow | `-` | `$env:GEMINI_API_KEY = "AIzaSyBXtjtOFZtCSA-jOlsTTubjMf4L9oPDKmQ"; python -c @" import os, time, json from google import genai from google.genai import types clie` |
| 2026-05-14 12:49:55 | allow | `-` | `$env:GEMINI_API_KEY = "AIzaSyBXtjtOFZtCSA-jOlsTTubjMf4L9oPDKmQ"; python -c @" import os, time, json from google import genai from google.genai import types clie` |
| 2026-05-14 12:50:08 | allow | `-` | `$env:GEMINI_API_KEY = "AIzaSyBXtjtOFZtCSA-jOlsTTubjMf4L9oPDKmQ"; python -c @" import os, time, json from google import genai from google.genai import types clie` |
| 2026-05-14 12:50:30 | allow | `-` | `$env:GEMINI_API_KEY = "AIzaSyBXtjtOFZtCSA-jOlsTTubjMf4L9oPDKmQ"; python -m pytest tests/domains/test_designer_gemini_provider.py::TestGeminiConnectivityLive -v ` |
| 2026-05-14 12:50:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyBXtjtOFZtCSA-jOlsTTubjMf4L9oPDKmQ"; python -m pytest tests/domain` |
| 2026-05-14 12:51:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/gemini_provider.py tests/domains/test_designer_gemini_provider.` |
| 2026-05-14 12:53:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "tests\fixtures\designer\drawings\expected_extractio` |
| 2026-05-14 12:57:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_drawing_fixture_manifest.py -v 2>&1` |
| 2026-05-14 12:57:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_drawing_fixture_manifest.py -v 2>&1 | Select-Stri` |
| 2026-05-14 12:57:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " import json, sys, io sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='ut` |
| 2026-05-14 12:57:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_drawing_fixture_manifest.py -v 2>&1 | Select-Stri` |
| 2026-05-14 12:58:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed|error" | ` |
| 2026-05-14 12:58:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/fixtures/designer/ tools/designer/ tests/domains/test_designer_drawing_fixture_m` |
| 2026-05-14 13:05:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK|Error|Import|Traceback"` |
| 2026-05-14 13:06:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 13:06:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; $env:GEMINI_API_KEY = "AIzaSyBXtjtOFZtCSA-jOlsTTubjMf4L9oPDKmQ"; python -m pytest tests/domain` |
| 2026-05-14 13:07:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/designer/drawings.py foms/platform/blueprints.py templates/designer/wdplanner` |
| 2026-05-14 13:13:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner\src"; New-Item -ItemType Directory -Force -Path "domain\factori` |
| 2026-05-14 13:16:06 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 13:18:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 13:18:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_frontend_factory_contract.py -v 2>&1 | Select-Str` |
| 2026-05-14 13:19:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from foms.services.designer.factories.shoe_rack import create_shoe_rack_assembly, ` |
| 2026-05-14 13:19:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from foms.services.designer.constraint_engine import validate_design_graph from fo` |
| 2026-05-14 13:20:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_frontend_factory_contract.py -q 2>&1 | Select-Str` |
| 2026-05-14 13:20:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from foms.services.designer.assembly_factories import default_design_json_v2 g = d` |
| 2026-05-14 13:20:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from foms.services.designer.assembly_factories import default_design_json_v2, crea` |
| 2026-05-14 13:20:30 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from foms.services.designer.assembly_factories import default_design_json_v2, crea` |
| 2026-05-14 13:20:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_frontend_factory_contract.py -q 2>&1 | Select-Str` |
| 2026-05-14 13:21:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_frontend_factory_contract.py::TestWardrobeFactory` |
| 2026-05-14 13:21:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_frontend_factory_contract.py -q 2>&1 | Select-Str` |
| 2026-05-14 13:21:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 13:22:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/domain/factoryRegistry.ts" "Add In Program/FOMSB` |
| 2026-05-14 13:22:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner\src"; New-Item -ItemType Directory -Force -Path "styles" | Out-` |
| 2026-05-14 13:25:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 13:25:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 13:25:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "docs\design" | Out-Null; echo "OK"` |
| 2026-05-14 13:27:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_frontend_product_contract.py -q 2>&1 | Select-Str` |
| 2026-05-14 13:27:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 13:28:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/App.tsx" "Add In Program/FOMSBrainDesigner/src/s` |
| 2026-05-14 13:28:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK|Error|Traceback"` |
| 2026-05-14 13:28:58 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m alembic revision --autogenerate -m "PG-B3 drawing intake models" 2>&1 | Select-Strin` |
| 2026-05-14 13:29:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m alembic heads 2>&1 | Select-Object -Last 3; python -m alembic current 2>&1 | Select-` |
| 2026-05-14 13:29:12 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m alembic upgrade heads 2>&1 | Select-Object -Last 3` |
| 2026-05-14 13:29:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem migrations/versions/ | Sort-Object Name | Select-Object -Last 3 | Select-Object ` |
| 2026-05-14 13:29:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem migrations\versions\ | Sort-Object Name | Select-Object -Last 5 Name` |
| 2026-05-14 13:29:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m alembic history --verbose 2>&1 | Select-String "Rev:" | Select-Object -Last 5` |
| 2026-05-14 13:29:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m alembic history --verbose 2>&1 | Select-String "Rev:|designer" | Select-Object -Firs` |
| 2026-05-14 13:30:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_drawing_intake.py -q 2>&1 | Select-String "passed` |
| 2026-05-14 13:30:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 13:31:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/persistence/designer/models.py migrations/versions/designer_drawing_intake.py tes` |
| 2026-05-14 13:32:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_pii_redactor.py -q 2>&1 | Select-String "passed|f` |
| 2026-05-14 13:33:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 13:33:56 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/pii_redactor.py tests/domains/test_designer_pii_redactor.py tes` |
| 2026-05-14 13:35:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_model_router.py -q 2>&1 | Select-String "passed|f` |
| 2026-05-14 13:35:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 13:36:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 13:37:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/drawing_template_classifier.py foms/services/designer/model_rou` |
| 2026-05-14 13:39:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_parts_table_parser.py -q 2>&1 | Select-String "pa` |
| 2026-05-14 13:39:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 13:40:02 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/parts_table_parser.py tests/domains/test_designer_parts_table_p` |
| 2026-05-14 13:58:50 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_case_memory.py -q 2>&1 | tail -10` |
| 2026-05-14 13:58:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_case_memory.py -q 2>&1 | Select-String "pa` |
| 2026-05-14 13:59:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 14:00:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/persistence/designer/models.py foms/services/designer/design_case_memory.py migra` |
| 2026-05-14 14:03:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_dimension_parser.py -q 2>&1 | Select-String "pass` |
| 2026-05-14 14:03:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from foms.services.designer.dimension_parser import parse_ocr_text text = '''?꾩옣洹쒓` |
| 2026-05-14 14:03:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_dimension_parser.py -q 2>&1 | Select-String "pass` |
| 2026-05-14 14:03:55 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 14:04:37 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/dimension_parser.py foms/services/designer/view_detector.py tes` |
| 2026-05-14 14:06:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_ontology_mapper.py -q 2>&1 | Select-String "passe` |
| 2026-05-14 14:06:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 14:07:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/ontology_mapper.py tests/domains/test_designer_ontology_mapper.` |
| 2026-05-14 14:09:16 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_drawing_review_contract.py -q 2>&1 | Select-Strin` |
| 2026-05-14 14:09:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_drawing_review_contract.py -q 2>&1 | Select-Strin` |
| 2026-05-14 14:10:18 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/designer/drawings.py tests/domains/test_designer_drawing_review_contract.py; ` |
| 2026-05-14 14:11:52 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_learning_loop_product.py -q 2>&1 | Select-String ` |
| 2026-05-14 14:12:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_learning_loop_product.py::TestPromotionGate::test` |
| 2026-05-14 14:12:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_learning_loop_product.py -q 2>&1 | Select-String ` |
| 2026-05-14 14:12:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c " from unittest.mock import MagicMock, patch mock_candidate = MagicMock() mock_candi` |
| 2026-05-14 14:13:08 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_learning_loop_product.py -q 2>&1 | Select-String ` |
| 2026-05-14 14:13:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 14:14:00 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_learning_loop_product.py::TestPromotionGate::test` |
| 2026-05-14 14:14:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_learning_loop_product.py::TestPromotionGate::test` |
| 2026-05-14 14:14:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest "tests/domains/test_designer_learning_loop_product.py::TestPromotionGate::tes` |
| 2026-05-14 14:14:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest "tests/domains/test_designer_learning_loop_product.py::TestPromotionGate::tes` |
| 2026-05-14 14:15:04 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 14:15:33 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"` |
| 2026-05-14 14:15:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/correction_clusterer.py foms/services/designer/rule_replay.py t` |
| 2026-05-14 14:21:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -10` |
| 2026-05-14 14:22:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"` |
| 2026-05-14 14:22:42 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "passed|failed" | Select` |
| 2026-05-14 14:23:24 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/designer/wdplanner_v2.html; $msg = @" fix: ?꾨㈃ ?깅줉 ?⑤꼸 ?쒖떆 踰꾧렇 ?섏젙 + 臾댁젣???숈` |
| 2026-05-14 14:23:31 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline origin/deploy..HEAD` |
| 2026-05-14 14:23:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git push origin deploy` |
| 2026-05-14 14:29:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py::test_strict_canonica` |
| 2026-05-14 14:29:35 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/contracts/ -q 2>&1 | Select-String "passed|failed" | Select-Object -Las` |
| 2026-05-14 14:29:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/contracts/runtime/foms_namespace_surface_tests.py; $msg = @" fix: canonical taxo` |
| 2026-05-14 14:33:48 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"` |
| 2026-05-14 14:34:10 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add templates/designer/wdplanner_v2.html; $msg = @" feat: ?꾨㈃ ?ㅼ쨷 ?낅줈??+ Gemini ??誘몄꽕???덈궡` |
| 2026-05-14 14:41:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "p` |
| 2026-05-14 14:43:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_design_retrieval.py -q 2>&1 | Select-String "pass` |
| 2026-05-14 14:43:41 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/design_retrieval.py tests/domains/test_designer_design_retrieva` |
| 2026-05-14 14:45:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_product_archetype_learning.py -q 2>&1 | Select-St` |
| 2026-05-14 14:45:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/product_archetype_types.py foms/services/designer/product_arche` |
| 2026-05-14 14:46:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_self_evaluation.py -q 2>&1 | Select-String "passe` |
| 2026-05-14 14:46:40 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/services/designer/self_evaluation.py tests/domains/test_designer_self_evaluation.` |
| 2026-05-14 14:46:57 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "tools\designer" | Out-Null; echo "OK"` |
| 2026-05-14 14:47:54 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/domains/test_designer_finetune_export.py -q 2>&1 | Select-String "passe` |
| 2026-05-14 14:48:11 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tools/designer/export_finetune_dataset.py tests/domains/test_designer_finetune_export.` |
| 2026-05-14 14:49:15 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; New-Item -ItemType Directory -Force -Path "tests\performance" | Out-Null; New-Item -ItemType D` |
| 2026-05-14 14:49:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 14:50:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add tests/performance/ tests/security/ tests/performance/__init__.py tests/security/__init` |
| 2026-05-14 14:51:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -m pytest tests/ -q --ignore=tests/contracts 2>&1 | Select-String "passed|failed|error"` |
| 2026-05-14 14:53:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add docs/plans/2026-05-14-foms-brain-production-grade-run-record.md docs/plans/PRODUCT_GRA` |
| 2026-05-14 14:56:29 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"` |
| 2026-05-14 14:56:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add foms/api/designer/drawings.py templates/designer/wdplanner_v2.html; $msg = @" fix: 異붿텧` |
| 2026-05-14 15:44:26 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 15:44:53 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 15:45:09 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 15:46:01 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/domain/commandHistory.ts" "Add In Program/FOMSBr` |
| 2026-05-14 15:48:38 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline -5; python -m pytest tests/domains/ -k "designer" -q 2>&1 | Select-String "p` |
| 2026-05-14 15:51:17 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "docs/plans/2026-05-14-foms-brain-production-grade-product-plan.md" "docs/plans/PRODUC` |
| 2026-05-14 15:56:21 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline origin/deploy..HEAD; git status --short | Select-Object -First 5` |
| 2026-05-14 16:01:20 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 16:02:45 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 16:03:31 | allow | `-` | `(payload에 command 없음)` |
| 2026-05-14 16:34:27 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 16:34:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 16:35:53 | allow | `-` | `(payload에 command 없음)` |
| 2026-05-14 16:37:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 16:38:03 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK|Error|Import"` |
| 2026-05-14 16:38:28 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 16:39:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "templates/designer/wdplanner_v2.html" "foms/api/designer/evolution_api.py" "docs/plan` |
| 2026-05-14 16:47:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1 | Select-String "error|built in|TS" | Sele` |
| 2026-05-14 16:48:07 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 16:49:23 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts" "Add In Program/FOMSBra` |
| 2026-05-14 17:08:32 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build 2>&1` |
| 2026-05-14 17:10:14 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')" 2>&1 | Select-String "APP_OK"; python -m pytest tests/` |
| 2026-05-14 17:11:44 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add "Add In Program/FOMSBrainDesigner/src/ui/ViewCube.tsx" "Add In Program/FOMSBrainDesign` |
| 2026-05-14 19:23:49 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git log --oneline origin/deploy..HEAD; git status --short | Select-Object -First 8` |
| 2026-05-14 19:24:05 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add AGENTS.md "docs/AI_CHANGELOG.md" "docs/AI_STATUS.md" "docs/ARCHIVE_INDEX.md" "docs/con` |
| 2026-05-15 08:54:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build` |
| 2026-05-15 08:54:25 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; python -c "import app; print('APP_OK')"` |
| 2026-05-15 08:55:34 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\Add In Program\FOMSBrainDesigner"; npm run build` |
| 2026-05-15 08:56:39 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; Get-ChildItem -LiteralPath ".cursor\skills" -Force | Select-Object Name, Mode` |
| 2026-05-15 08:56:43 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; dir ".cursor\skills"` |
| 2026-05-15 08:56:51 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; dir ".agents\skills\gstack" | Select-Object -First 30` |
| 2026-05-15 08:57:22 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git status; git branch --show-current` |
| 2026-05-15 08:57:36 | allow | `-` | `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"; git add -u; git add "Add In Program\FOMSBrainDesigner\src\domain\blockPlacement.ts"; git add "` |
