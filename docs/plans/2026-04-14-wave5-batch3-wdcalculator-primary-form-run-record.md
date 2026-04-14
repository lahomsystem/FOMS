# Wave 5 Batch W5-B3 — WDCalculator `primary-form` canonical chunk

> **batch ID:** W5-B3  
> **lane:** WDCalculator — `primary-form`  
> **실행일:** 2026-04-14  
> **선행:** W5-B0, W5-B1, W5-B2 (complete)

## Ordering discipline

`delete → merge → extend → add` — 7개 소스 파일 **삭제**, 내용은 기존 의미 순서로 `primary-form.js`에 **병합**, `wdcalculator_scripts_config.html`은 다중 `<script src>`를 **`primary-form.js` 한 번 + `current-estimate-orchestration.js`** 순으로 **확장**, 신규 `*-host-bootstrap.js` / wrapper-only 파일 **추가 없음**.

## Delta registers

| Register | 내용 |
|----------|------|
| **product file delta** | `static/js/wdcalculator/primary-form.js` (canonical chunk; 7개 모듈 밴드 포함, 주석 `/* --- included: … --- */`). `templates/wdcalculator/partials/wdcalculator_scripts_config.html` — 개별 7개 `<script src>` 제거, `primary-form.js` 1줄 + orchestration 순서 정리. |
| **wrapper file delta** | 아래 7개 파일 **삭제**(merge 수령). 신규 wrapper **0**. |
| **test file delta** | `tests/support/wdcalculator_{calculate_button,add_option_button,notes,coupon_display,base_components,additional_options,product_catalog,base_live_events,current_estimate}_contract_node_checks.js` — `helperPath`/소스 읽기를 `primary-form.js`로 통일. `tests/test_wdcalculator_product_settings.py` — 인라인 스크립트 순서 assert를 `primary-form` 슬롯 기준으로 갱신. |
| **canonical target** | `static/js/wdcalculator/primary-form.js` — W5-B1 matrix의 **primary-form** 밴드 단일 실행 청크. |
| **removal target** | `notes-ui.js`, `base-components-ui.js`, `coupon-display-helpers.js`, `additional-options-ui.js`, `add-option-button.js`, `calculate-button.js`, `product-catalog-ui.js` — 저장소에서 제거. |
| **retirement condition** | 템플릿이 위 개별 경로를 참조하지 않음; Node/pytest·페이지 계약이 `primary-form.js` 기준으로 통과하면 청산 완료. 후속 W5-B4는 `estimate-lifecycle.js` 등 다음 canonical 파일로만 수령. |

## Public load order (post-merge, 본 batch 관련 구간)

`wdcalculator_scripts_config.html` (요지):  
… → `composition.js` → **`primary-form.js`** → `current-estimate-orchestration.js` → …

## Verification (executed)

| 단계 | 명령 | 결과 |
|------|------|------|
| 앱 import | `python -c "import app; print('APP_OK')"` | APP_OK |
| Harness | `python tools/harness/verify_result.py --json` | success |
| Focused automated | `pytest` — `tests/test_wdcalculator_product_settings.py` + 아래 9개 contract 모듈 | 35 passed |
| Focused 목록 | `test_wdcalculator_calculate_button_contract_node.py`, `add_option_button`, `base_live_events`, `product_catalog`, `additional_options`, `coupon_display`, `base_components`, `notes_contract_node`, `current_estimate_contract_node` | 전부 pass |

**Manual smoke (lane):** 자동화 범위에서 HTML 스크립트 태그 순서·Node VM 계약으로 대체; 브라우저 `/wdcalculator` 수동 스모크는 로컬 운영자 선택.

## Parallel audit loop (W5 규칙)

### 감리 (구현·문서 정리 후)

| Reviewer | HIGH | MEDIUM | LOW / nit |
|----------|------|--------|-----------|
| code-reviewer | 0 | 0 | `wdcalculator_scripts.html` 주석이 여전히 구 `notes-ui.js` 경로를 언급할 수 있음 — W5-B9 defer 범위. |
| evolution-architect | 0 | 0 | primary-form 단일 파일 크기 증가는 의도된 canonical 수령. |
| grand-develop-master | 0 | 0 | 금지 경계(blueprints/API/DB/Wave6) 미침범. |

## Direction Lock (batch 요약)

코드 batch; W5-B0의 10문항 전부 재기록은 생략. **구조-only**: 7모듈 → `primary-form.js` 단일 청크, 신규 host-bootstrap 금지, mainline `composition → primary-form → …` 유지.

## Outcome

**PASS — W5-B4 (`estimate-lifecycle`) 진행 가능.**
