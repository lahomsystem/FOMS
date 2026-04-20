# Wave 5 Batch W5-B7 — ERP Beta contract freeze

> **batch ID:** W5-B7  
> **risk axis:** docs / contract  
> **실행일:** 2026-04-14  
> **attempt:** 1 — completed  
> **locked pilot:** `templates/partials/erp_beta_js.html`

## Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record 생성 | runtime code edit |
| globals / DOM / API / load-order contract freeze | add/edit order behavior change |
| preferred canonical shape 정의 | upload/payment semantics change |

## Inputs consumed

1. `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md` §5.8
2. `docs/plans/2026-04-14-wave5-batch6-shared-erp-island-lock-run-record.md`
3. `templates/add_order.html`
4. `templates/edit_order.html`
5. `templates/partials/erp_beta_tab.html`
6. `templates/partials/erp_beta_js.html`
7. `static/js/erp/beta-shared.js`

## Globals / load-order contract table

### A. Host preconditions before `erp_beta_js.html`

| Host file | Must define before include | Live truth |
|-----------|----------------------------|------------|
| `add_order.html` | `ORDER_ID` (`let`, default `0`), `ERP_BETA_ENABLED`, `USE_DIRECT_UPLOAD`, `window.__ERP_BETA_DRAFT_MODE = true`, `window.__ERP_DRAFT_ENDPOINT = '/api/orders/erp/draft'` | add-order uses data-* + `safeJsonParse` bootstrap just before include |
| `edit_order.html` | `ORDER_ID` (`const`, existing order id), `ERP_BETA_ENABLED`, `USE_DIRECT_UPLOAD`, `window.__ERP_BETA_DRAFT_MODE = false`, `window.__ERP_DRAFT_ENDPOINT = '/api/orders/erp/draft'` | edit-order injects constants before include |
| shared host DOM | `#erp-beta-tab`, `templates/partials/erp_beta_tab.html` DOM subtree | partial JS assumes tab button + rendered ERP form DOM already exist |

### B. Runtime load order

1. `erp_beta_tab.html` DOM renders in add/edit template body
2. host globals (`ORDER_ID`, `ERP_BETA_ENABLED`, `USE_DIRECT_UPLOAD`, draft flags) are defined
3. `erp_beta_js.html` top script injects `window.__ERP_PAYMENT_ICON_URLS`
4. `erp_beta_js.html` loads `static/js/erp/beta-shared.js`
5. `erp_beta_js.html` inline shared-form logic executes

### C. Public callable surface to preserve

| Surface | Source | Why it is contract |
|---------|--------|--------------------|
| `window.erpTogglePayment` | `erp_beta_js.html` | payment confirm buttons call it inline |
| `window.erpInitFlatpickrForItemRow` | `erp_beta_js.html` | item-row date UI bootstrapping hook |
| `erpLoadStructured`, `erpSaveStructured` | `erp_beta_js.html` top-level global declarations | save/load flow anchor |
| `erpUploadItemAttachmentsPromptless`, `erpUploadSelectedAttachments`, `erpDeleteAttachment`, `erpOpenAttachmentPreview`, `erpLinkAttachmentToItem` | `erp_beta_js.html` | inline attachment UI / button handlers rely on names |
| `erpGetDraftEndpoint`, `erpEnsureDraftOrderId`, `erpRequireOrderIdOrWarn`, `erpSetStatus`, `erpFormatMoneyKRW`, `erpParseDepositValue`, `erpFormatDepositDisplay` | `beta-shared.js` | cross-band helpers reused by save/payment/attachment flows |
| `_erpNormalizePaymentData`, `_erpUpdatePaymentConfirmUI`, `_erpPaymentIconSrc` | `beta-shared.js` | payment icon contract / optimistic update contract |
| `escapeHtml`, `formatPhoneAuto`, `toggleOrdererUI`, `syncWorkflowStageByOrderer`, `adjustTextareaHeight` | `beta-shared.js` | shared form utilities consumed by partial logic |

## DOM selector / data-attribute contract

### Host shell contract (`erp_beta_tab.html`)

| Selector / attribute | Purpose |
|----------------------|---------|
| `.card[data-erp-order-id]` | fallback order-id host for save/payment flows |
| `#erp-beta-tab` | tab shown hook / deep-link activation |
| `#erp-orderer-direct`, `#erp-orderer-select`, `#erp-orderer` | 발주사 토글 contract |
| `#erp-workflow-stage` | workflow stage write/read contract |
| `#erp-save-btn`, `#erp-load-btn`, `#erp-add-item-btn` | shared form button anchors |
| `#erp-items`, `.erp-item-row` | line-item container + row identity |
| `#erp-items-total`, `#erp-remaining-section`, `#erp-remaining-amount`, `#erp-deposit-amount` | pricing/payment display contract |
| `.erp-payment-confirm-btn[data-payment-type="deposit|balance"]` + `img.erp-custom-payment-icon` | payment icon/button contract |
| `#erp-attachments-category`, `#erp-attachments-input`, `#erp-attachments-upload-btn`, `#erp-attachments-status`, `#erp-attachments-progress`, `#erp-attachments-progress-bar`, `#erp-attachments-gallery` | common attachment host contract |
| `.erp-item-attachments-input`, `.erp-item-attachments-gallery` | per-item measurement attachment contract |
| `#erp-draft-banner`, `#erp-draft-order-id`, `#erp-draft-edit-link` | add-order draft mode banner contract |

### Item row data contract (`erp_beta_js.html`)

| Data attr | Meaning |
|-----------|---------|
| `data-erp="product_name"` | 제품명 |
| `data-erp="spec_width"`, `data-erp="spec_depth"`, `data-erp="spec_height"` | 규격 row fields |
| `data-erp="internal"`, `data-erp="color"`, `data-erp="option_detail"`, `data-erp="handle"`, `data-erp="misc"` | 옵션/메모 subfields |
| `data-erp="price"` | 항목 금액 |
| `data-erp="measurement_date"`, `data-erp="construction_date"` | 항목 날짜 |
| `data-erp="extra_input"` | 멀티라인 추가 입력 |

## API / fetch contract snapshot

| Endpoint | Method | Request contract | Expected success shape / usage |
|----------|--------|------------------|--------------------------------|
| `/api/orders/erp/draft` | `POST` | no body | `{ success, order_id }` required by draft bootstrap |
| `/api/orders/{id}/structured` | `GET` | none | `{ success, structured_data, structured_confidence? }` |
| `/api/orders/{id}/structured` | `PUT` | JSON with `structured_data`, `raw_order_text`, `structured_schema_version`, `structured_confidence`, optional `received_date`, `received_time`, `notes`, `is_self_measurement` | `{ success, message? }` |
| `/api/orders/{id}/payment-confirm` | `POST` | `{ type: 'deposit'|'balance', confirmed: boolean }` | `{ success, payment }` |
| `/api/address/search` | `GET` | query string from modal search | address lookup success payload |
| `/api/orders/{id}/attachments` | `GET` | none | `{ attachments: [] }` used for gallery reload |
| `/api/orders/{id}/attachments` | `POST` | multipart `file`, `category`, optional `item_index` | `{ success, attachment }` |
| `/api/orders/{id}/attachments/{attachmentId}` | `DELETE` | none | `{ success, message? }` |
| `/api/upload/session` | `POST` | `{ filename, size, folder }` | `{ success, upload_url, key }` or fallback to form upload |
| `/api/upload/session/batch` | `POST` | `{ files: [{ filename, size }], folder, category }` | `{ success, sessions }` or fallback to form upload |
| `/api/orders/{id}/attachments/complete` | `POST` | `{ key, filename, category, item_index, size }` | attachment register success payload |
| `/api/orders/{id}/quest` | `GET` | none | `{ success, quest, auto_transitioned?, next_stage? }` |
| `/api/orders/{id}/quest/approve` | `POST` | `{ team }` | `{ success, quest, all_approved?, auto_transitioned?, next_stage? }` |
| `/api/orders/{id}/quest/status` | `PUT` | `{ status }` | `{ success, quest }` |

## Shared behavior freeze

| Area | Frozen behavior |
|------|-----------------|
| add-order draft mode | `ORDER_ID == 0`일 때 저장/결제/첨부 경로는 draft 생성 helper를 통해 order id를 먼저 확보한다 |
| edit-order mode | existing `ORDER_ID`를 사용하고 draft mode는 false |
| payment toggle | optimistic UI 후 `/payment-confirm` authoritative payload로 normalize/rollback 한다 |
| totals | item price sum → `#erp-items-total`, deposit input 반영 → `#erp-remaining-amount` 계산 |
| attachment mode | `USE_DIRECT_UPLOAD` true면 `session → PUT → complete`, 실패 시 form upload fallback |
| item attachment linking | measurement attachment는 `item_index` 기반으로 제품 항목과 연결/해제된다 |

## Preferred canonical file shape (for W5-B8)

### Preferred shape

- **one thin include partial:** `templates/partials/erp_beta_js.html`
- **one large static entry owner:** `static/js/erp/beta-shared.js`

### Rules

1. W5-B8의 기본 목표는 `erp_beta_js.html`을 **globals injection + thin bridge** 수준으로 줄이고, shared logic의 primary owner를 `beta-shared.js`로 키우는 것이다.
2. 새 runtime 분리가 꼭 필요할 때만 **최대 2개의 large helper**를 허용한다.
3. `static/js/erp/beta/*`가 **3개 이상 runtime module** 또는 **2개 이상 layer**가 되면 `static/js/erp/beta/README.md`를 local entrypoint로 요구한다.
4. arbitrary micro-file proliferation은 금지한다.

## Manual smoke checklist (W5-B8 minimum)

- `add_order`에서 ERP Beta 탭 진입 후 draft 생성 배너/주문번호 확보 확인
- `edit_order`에서 기존 structured data load 및 re-save 확인
- item row add/remove 후 합계/잔금 계산과 per-item attachment 패널 재색인 확인
- 예약금/잔금 payment icon toggle 및 optimistic rollback path 확인
- `USE_DIRECT_UPLOAD=true` / fallback form upload 모두에서 공통 첨부 + item attachment 업로드 확인
- draft/save path 후 redirect / status text / attachment reload가 정상인지 확인

## Verification

| 검사 | 결과 |
|------|------|
| docs-only consistency | 통과 — 계획서 §5.8 필수 산출물 5종 충족 |
| host global precondition extraction | 통과 — add/edit inject block 확인 |
| DOM host contract extraction | 통과 — `erp_beta_tab.html` truth 기준으로 고정 |
| API snapshot extraction | 통과 — `erp_beta_js.html` live fetch paths 기준으로 고정 |
| APP_OK / verify_result | N/A (docs-only batch) |

## Direction Lock (10문항)

| # | Y/N | 한 줄 근거 |
|---|-----|------------|
| 1 | **Y** | add/edit shared-form contract를 한 문서에 고정했다 |
| 2 | **Y** | host globals / DOM / API / shape가 분리 없이 한 번에 freeze됐다 |
| 3 | **Y** | docs-only; runtime touch 없음 |
| 4 | **Y** | preferred shape를 thin partial + one large static entry로 잠갔다 |
| 5 | **Y** | helper split이 필요해도 max 2 large helper로 제한했다 |
| 6 | **Y** | DOM ids는 live truth 기준으로 기록했다 (`#erp-save-btn` 등) |
| 7 | **Y** | direct-upload / fallback dual path를 explicit contract로 남겼다 |
| 8 | **Y** | add_order draft mode와 edit_order fixed-order mode를 구분했다 |
| 9 | **Y** | W5-B8 manual smoke minimum을 선행 체크리스트로 고정했다 |
| 10 | **Y** | 다음 legal batch를 W5-B8로 명확히 넘겼다 |

## Changes made

- `docs/plans/2026-04-14-wave5-batch7-erp-beta-contract-freeze-run-record.md` 생성 (본 파일)

## product / wrapper / test delta

| 구분 | delta |
|------|-------|
| product | 없음 |
| wrapper | 없음 |
| test | 없음 |

## README update 여부

- 없음 (docs-only batch)

## Outcome

**PASS — W5-B7 complete. W5-B8 may rebaseline the ERP Beta shared-form pilot within this frozen contract.**
