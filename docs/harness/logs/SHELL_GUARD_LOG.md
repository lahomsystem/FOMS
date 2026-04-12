# Shell Guard Log

> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.

| Time | Decision | Pattern | Command |
|------|----------|---------|---------|
| 2026-04-12 16:38:53 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_settings.py -k "products_api_keeps_legacy_success_shape" -q` |
| 2026-04-12 16:40:23 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_settings.py -k "products_api_keeps_legacy_success_shape" -q` |
| 2026-04-12 16:46:58 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_catalog_contract_node.py tests/test_wdcalculator_product_settings.py -k "product_catalog_contract_node or inlin` |
| 2026-04-12 16:48:55 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_catalog_contract_node.py tests/test_wdcalculator_product_settings.py -k "product_catalog_contract_node or inlin` |
| 2026-04-12 16:49:43 | allow | `-` | `python -m pytest tests/test_wdcalculator_product_catalog_contract_node.py tests/test_wdcalculator_product_settings.py -k "product_catalog_contract_node or inlin` |
| 2026-04-12 16:53:27 | allow | `-` | `python -c "import app; print('APP_OK')"` |
| 2026-04-12 17:01:40 | allow | `-` | `$msg = @' refactor: WDCalculator 상품 카탈로그 UI 분리로 구조 분해 경계 고정 상품 목록 fetch, legacy product select, product info 표시를 정적 모듈로 분리해 giant inline script의 결합도를 낮춘다. base-` |
