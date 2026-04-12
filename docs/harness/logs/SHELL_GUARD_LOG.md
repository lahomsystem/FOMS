# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-12 15:33:39 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-12 15:35:03 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_settings.py tests/test_wdcalculator_estimate_totals_node.py tests/test_wdcalculator_current_estimate_contract_n` |
| 2026-04-12 15:35:03 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-12 15:35:03 | allow | `-` | `node -e "const fs=require('fs'); let s=fs.readFileSync('templates/wdcalculator/partials/wdcalculator_scripts.html','utf8'); s=s.replace(/^<script>\s*/, '').repl` |
| 2026-04-12 15:36:17 | allow | `-` | `node -e "const fs=require('fs'); let s=fs.readFileSync('templates/wdcalculator/partials/wdcalculator_scripts.html','utf8'); s=s.replace(/^<script>\s*/, '').repl` |
| 2026-04-12 15:36:17 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_settings.py tests/test_wdcalculator_estimate_totals_node.py tests/test_wdcalculator_current_estimate_contract_n` |
| 2026-04-12 15:36:17 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-12 15:47:34 | allow | `-` | `node -e "const fs=require('fs'); let s=fs.readFileSync('templates/wdcalculator/partials/wdcalculator_scripts.html','utf8'); s=s.replace(/^<script>\s*/, '').repl` |
| 2026-04-12 15:47:34 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_settings.py tests/test_wdcalculator_estimate_totals_node.py tests/test_wdcalculator_current_estimate_contract_n` |
| 2026-04-12 16:08:08 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_settings.py tests/test_wdcalculator_product_catalog_contract_node.py` |
| 2026-04-12 16:08:51 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_settings.py tests/test_wdcalculator_product_catalog_contract_node.py` |
