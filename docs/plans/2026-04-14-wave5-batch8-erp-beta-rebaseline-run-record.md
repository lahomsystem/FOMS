# Wave 5 Batch W5-B8 — ERP Beta shared-form pilot rebaseline

> **batch ID:** W5-B8  
> **risk axis:** template / static shared-form island  
> **실행일:** 2026-04-15  
> **attempt:** 2 — completed  
> **canonical target:** `static/js/erp/beta-shared.js`  
> **thin bridge:** `templates/partials/erp_beta_js.html`

## Scope lock

| 허용 | 금지 |
|------|------|
| `templates/partials/erp_beta_js.html` thin include화 | `layout.html` / dashboard shell / CSS system refactor |
| shared-form runtime를 `static/js/erp/beta-shared.js`로 이동 | upload / payment / draft / submit business semantic change |
| existing add/edit host globals contract 유지 | route / endpoint / payload semantic change |
| focused regression test 추가 | arbitrary micro-file proliferation |

## Inputs consumed

1. `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md` §5.9
2. `docs/plans/2026-04-14-wave5-batch6-shared-erp-island-lock-run-record.md`
3. `docs/plans/2026-04-14-wave5-batch7-erp-beta-contract-freeze-run-record.md`
4. `templates/add_order.html`
5. `templates/edit_order.html`
6. `templates/partials/erp_beta_js.html`
7. `templates/partials/erp_beta_tab.html`
8. `static/js/erp/beta-shared.js`
9. `static/js/erp/estimate-preview.js`
10. `tests/test_erp_beta_shared_form_scripts.py`

## Context normalization keys

- `registry lane:` `erp-beta-shared-form`
- `spec domain:` Wave 5 large front-end island mainline
- `FR20 context key:` `beta-shared-single-entry-owner`

## Contract table

| Contract | Freeze |
|----------|--------|
| host globals | `ORDER_ID`, `ERP_BETA_ENABLED`, `USE_DIRECT_UPLOAD`, `window.__ERP_BETA_DRAFT_MODE`, `window.__ERP_DRAFT_ENDPOINT`, `window.__ERP_PAYMENT_ICON_URLS` |
| load order | host globals → `erp_beta_tab.html` DOM → payment icon injection → `js/erp/beta-shared.js` → html2canvas CDN → `js/erp/estimate-preview.js` |
| public callable surface | `window.erpTogglePayment`, `erpLoadStructured`, item/payment/remaining/upload helpers remain reachable from `beta-shared.js` |
| DOM contract | `#erp-items`, `#erp-save-btn`, `#erp-attachments-input` and existing ERP Beta selectors remain unchanged |
| API/fetch contract | draft/save/upload/payment endpoints and payload meaning unchanged |

## FR19 decision

`delete → merge → extend → add` 적용.

1. 기존 thin static helper(`beta-shared.js`)가 이미 존재하므로 새 runtime entry를 추가하지 않았다.
2. `erp_beta_js.html` 내부 대형 inline shared-form body는 **same-batch merge target**으로 판단했다.
3. 따라서 inline body를 `static/js/erp/beta-shared.js`로 이동하고 partial은 globals injection + ordered script include만 남겼다.
4. runtime layer 수가 여전히 **one thin partial + one large static owner**라서 FR20 README gate는 **not triggered**다.

## Changes made

- `templates/partials/erp_beta_js.html`에서 대형 inline shared-form `<script>` block 제거.
- `static/js/erp/beta-shared.js`에 기존 inline shared-form runtime를 append하여 canonical owner로 승격.
- payment icon globals injection, html2canvas CDN, `estimate-preview.js` include 순서는 유지.
- `tests/test_erp_beta_shared_form_scripts.py` 추가: add/edit 양쪽 페이지에서 thin partial contract와 moved-inline absence를 잠금.

## Delta registers

| Register | 내용 |
|----------|------|
| **product file delta** | runtime file 순증가 없음; `beta-shared.js` 확장, `erp_beta_js.html` 축소 |
| **wrapper file delta** | 없음 |
| **test file delta** | `tests/test_erp_beta_shared_form_scripts.py` 추가(+1) |
| **canonical target** | `static/js/erp/beta-shared.js` |
| **removal / merge target** | `templates/partials/erp_beta_js.html` 내부 former inline shared-form script body |
| **retirement wave / removal condition** | W5-B8 same-batch 청산 완료. inline body가 partial에서 사라지고 thin-partial regression이 green이면 종료 |
| **README update 여부** | no — FR20 미발동, `static/js/erp/beta/README.md` 불필요 |

## Verification

| 단계 | 명령 / 범위 | 결과 |
|------|-------------|------|
| JS syntax | `node --check static/js/erp/beta-shared.js` | exit 0 |
| 앱 import | `python -c "import app; print('APP_OK')"` | `APP_OK` |
| Harness | `python tools/harness/verify_result.py --json` | `"success": true` |
| Focused automated | `python -m pytest tests/test_erp_beta_shared_form_scripts.py -q` | **2 passed** |
| lint / diagnostics | `ReadLints` on `tests/test_erp_beta_shared_form_scripts.py` | no errors |
| equivalent regression evidence | add/edit render test가 host globals ordering, thin partial includes, moved-inline absence를 고정 | pass |
| live manual smoke | local dev server authenticated browser smoke | **blocked** — live auth/session divergence prevented add/edit browser navigation; blocker is environment/runtime auth path, not the moved shared-form JS body itself |

## Direction Lock answers

1. **Yes** — shared-form runtime owner를 `beta-shared.js` 하나로 더 선명하게 만들었다.
2. **Yes** — `erp_beta_js.html`은 globals injection + ordered include만 남겨 split-brain을 줄였다.
3. **Yes** — 새 runtime micro-file / wrapper를 추가하지 않았다.
4. **Yes** — W5-B7 preferred shape(one thin partial + one large static owner)를 그대로 따랐다.
5. **Yes** — route / endpoint / payload / DOM meaning을 바꾸지 않았다.
6. **Yes** — add/edit 양쪽 render contract를 같은 focused regression으로 잠갔다.
7. **Yes** — former inline body가 partial에 남아 있지 않음을 자동 테스트로 증명했다.
8. **Yes** — FR20 README gate가 왜 미발동인지 기록했다.
9. **Yes** — stop condition을 발생시키는 shell/layout/CSS reopen은 하지 않았다.
10. **Yes** — 다음 legal batch를 `W5-B9` closeout으로 넘길 수 있는 상태를 만들었다.

## Drift / stop / defer decision

- **Stop:** 없음.
- **Drift:** runtime contract drift 없음. 다만 live authenticated browser smoke는 local auth/session divergence 때문에 미완료 상태로 closeout 문서에 이월한다.
- **Next legal batch:** `W5-B9` high-risk shell/CSS defer register + closeout

## Outcome

**PASS — W5-B8 code rebaseline completed.**  
Residual risk는 **live authenticated browser smoke gap** 하나이며, W5-B9 closeout에서 공식 residual/defer note로 잠근다.
