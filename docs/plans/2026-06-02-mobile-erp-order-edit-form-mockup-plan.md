# 모바일 ERP Order 편집 폼 — mockup 컴포넌트 구현 계획서

- 작성: 2026-06-02
- 대상 실행자: 임의의 LLM/개발자 (이 문서만 보고 바로 착수 가능하도록 자기완결식으로 작성)
- 브랜치: `deploy` (스테이징) → 검증 후 `production`
- 셸/명령 예시: PowerShell 5.x (Win11). Claude Code 세션은 bash 가능.

---

## 0. 한 줄 요약

`/edit/<id>?open=erp-order` 의 ERP Order 편집 폼은 **레거시 Bootstrap 마크업**(`templates/orders/partials/erp_order_tab.html`, 484줄)이다. mobile-v2 코호트에서 이를 **위저드 mockup 컴포넌트(`field`/`foms-input`/`foms-select`/`foms-textarea`/`product-item-card`)로 remarkup한 신규 모바일 템플릿**으로 교체한다. **데스크톱(≥992px)은 레거시 그대로**, 저장/계산/연동 JS는 **element id·name·data-* 전수 보존**으로 무중단.

---

## 1. 배경 / 의사결정 (확정)

- 증상: 모바일 주문편집 화면이 mockup 스타일 미적용(레거시 폼).
- 이미 적용된 것(선행 커밋): 셸 chrome(헤더 `주문 수정` + 하단 내비) + mobile-v2 코호트 게이트 + 정적 캐시 no-cache. **폼 본문(ERP Order)은 미착수.**
- 사용자 결정: **"위저드 컴포넌트 재사용 신규 제작"** (mobile-v2 전용 신규 템플릿, 데스크톱 레거시 유지).

---

## 2. 핵심 제약 (위반 시 주문 저장/계산 깨짐 — 절대 준수)

1. **element `id` 전수 보존.** `static/js/orders/erp-order-shared.js`가 `getElementById('erp-...')`로 폼을 구동한다(저장·견적·라인아이템·계약금/잔금·채널톡·주소검색·실측패널). §8 인벤토리의 id는 **하나도 변경/삭제 금지**.
2. **`name` 속성 보존.** 비-ERP/POST 경로(`foms/web/orders/edit.py` `edit_order`)가 `request.form.get('received_date'...)` 등으로 읽는다(§7). ERP 탭은 주로 JS+API 저장이지만, name이 있는 input은 유지.
3. **JS-hook 클래스 보존.** `erp-amount-value`, `erp-amount-value--deposit`, `erp-item-row`, `erp-item-title`, `erp-spec-row`, `erp-spec-rows`, `erp-add-spec-row-btn`, `erp-remove-spec-row-btn`, `erp-remove-item-btn`, `erp-item-attachments-gallery`, `erp-item-attachment-hint`, `erp-item-date-multiple`, `erp-custom-payment-icon`, `data-erp`, `data-erp-order-id`, `data-erp-order-enabled`, `data-erp-surface`, `data-erp-ready` — **유지**.
4. **데스크톱 무영향.** 신규 템플릿은 `erp_mobile_v2_enabled` 분기에서만 렌더. 데스크톱은 기존 `erp_order_tab.html` 유지.
5. **클린코드/근본수정.** 증상 우회·임시 CSS 덮어쓰기 금지. 마크업은 mockup 컴포넌트로 정직하게 재작성.
6. **캐시 함정 인지(§10).** 변경한 CSS/템플릿은 자동 no-cache(선행 커밋)지만, `?v=` 쿼리 가진 링크는 버전 올릴 것.

---

## 3. 사전조사 결과 (반드시 알고 시작)

### 3-1. 파일 지도
| 역할 | 경로 |
|---|---|
| ERP Order 폼(대상) | `templates/orders/partials/erp_order_tab.html` (484줄) |
| 폼 포함부(분기 지점) | `templates/orders/partials/edit_order_body.html:536` `{% include "orders/partials/erp_order_tab.html" %}` |
| 폼 구동 JS | `static/js/orders/erp-order-shared.js` (id 의존) |
| 라인아이템 JS | `static/js/foms/product-item.js` |
| 견적 JS | `static/js/orders/estimate-preview.js` |
| POST 저장 라우트 | `foms/web/orders/edit.py` `edit_order` |
| 위저드 참고 마크업 | `templates/orders/wizard/step1_basic.html` 등 |
| 디자인 출처(mockup) | `docs/design/mockups/mobile-wizard-new-order.html`, `docs/design/mockups/_tokens.css` |

### 3-2. ⚠️ 결정적 발견 — 폼 원자 CSS가 shipped 안 됨
위저드/ mockup이 쓰는 `.field`, `.field__label`, `.field__label--required`, `.field__hint`, `.field-grid-2`, `.foms-input`, `.foms-select`, `.foms-textarea`, `.foms-tabular` 는 **`static/css` 어디에도 정의가 없다**(현재 mockup 프로토타입 inline / `_tokens.css`에만 존재). `foms-wizard.css`는 wizard chrome(`foms-wizard__*`)만 정의하고 input은 손대지 않는다.
→ **Phase 0에서 이 원자 CSS를 shipped 컴포넌트로 포팅**하지 않으면 폼이 unstyled가 된다. (이 작업은 위저드 자체의 일관성도 개선함.)

### 3-3. CSS 로드 경로
- edit 페이지(`/edit/<id>`)는 선행 커밋으로 `foms-mobile-surfaces.css` 번들을 로드한다(`templates/partials/shared/layout_head.html`, 조건 `erp_mobile_v2_enabled and (path /erp or endpoint order_edit.edit_order)`).
- `foms-mobile-surfaces.css`가 `@import`하는 것 중 **로드됨**: `foms-product-item.css`(라인아이템 카드), `foms-shell.css` 등.
- **미로드**: `foms-wizard.css`(필요 없음 — chrome용), 신규 원자 CSS(Phase 0에서 추가 후 import 필요).

### 3-4. 디자인 토큰(이미 shipped — `static/css/foundation/foms-tokens.css`)
사용 토큰 전부 존재 확인: `--foms-touch-target-min`, `--foms-border-default`, `--foms-border-focus`, `--foms-shadow-focus-ring`, `--foms-radius-md`, `--foms-radius-full`, `--foms-surface-base`, `--foms-text-primary/secondary/tertiary`, `--foms-font-size-base/sm/xs`, `--foms-font-weight-medium`, `--foms-color-danger-500`, `--foms-space-2/3/4`. → 포팅 CSS는 토큰만 참조하면 됨.

---

## 4. 아키텍처 / 변경 파일 개요

```
[신규] static/css/components/foms-form-field.css      ← 폼 원자(.field/.foms-input/...) shipped 포팅 (Phase 0)
[수정] static/css/foundation/foms-mobile-surfaces.css ← @import foms-form-field.css 1줄 추가 (Phase 0)
[신규] templates/orders/partials/erp_order_tab_mobile.html ← mockup 컴포넌트 remarkup (Phase 1~4, 점진)
[수정] templates/orders/partials/edit_order_body.html:536  ← erp_mobile_v2_enabled 분기 include
[신규] tests/visual/test_erp_order_edit_mobile_form.py     ← 렌더 계약 + id 보존 회귀 테스트
```

분기(분기 지점 edit_order_body.html:536):
```jinja
{% if erp_mobile_v2_enabled %}
  {% include "orders/partials/erp_order_tab_mobile.html" %}
{% else %}
  {% include "orders/partials/erp_order_tab.html" %}
{% endif %}
```

> **드리프트 방지:** 신규 모바일 템플릿은 레거시와 별도 파일이라 id가 어긋날 수 있다. §6 계약 테스트가 **두 템플릿의 id 집합 동일성**을 강제한다. 반드시 함께 작성.

### ⭐ 핵심 전략 — "복사 → 분기 연결 → 섹션 점진 변환" (섹션별 신규 작성 금지)
처음부터 섹션을 새로 짜면 id 누락·중간 단계 폼 깨짐 위험이 크다. 대신:
1. `erp_order_tab.html`을 `erp_order_tab_mobile.html`로 **그대로 복사**(verbatim) → 이 시점 모바일=레거시와 100% 동일·동작(id 자동 보존, 계약 테스트 통과).
2. edit_order_body.html 분기 연결.
3. 이후 Phase 1~4는 **이 복사본 안에서 섹션 마크업만 mockup 컴포넌트로 치환**(id/name/data-*/JS-hook 클래스는 절대 손대지 않음). 매 Phase마다 폼은 항상 완전 동작 상태.
> 즉 "신규 제작"의 결과물은 신규 파일(`erp_order_tab_mobile.html`)이되, 작업 방식은 안전한 incremental 변환이다.

---

## 5. Phase별 실행 단계

### Phase 0 — 폼 원자 CSS shipped 포팅 (선행 필수, 저위험)

1. `static/css/components/foms-form-field.css` 신규 생성. 아래 내용을 그대로 작성(mockup `_tokens.css:133-145` + `mobile-wizard-new-order.html:74-159`에서 포팅, 값은 토큰 참조로 변환):

```css
/* foms-form-field.css — shipped 폼 원자 컴포넌트 (mockup field/foms-input 포팅).
 * 출처: docs/design/mockups/_tokens.css, docs/design/mockups/mobile-wizard-new-order.html */
.field { display: grid; gap: var(--foms-space-2); margin-bottom: var(--foms-space-4); }
.field__label { font-size: var(--foms-font-size-sm); font-weight: var(--foms-font-weight-medium); color: var(--foms-text-secondary); }
.field__label--required::after { content: " *"; color: var(--foms-color-danger-500); }
.field__hint { font-size: var(--foms-font-size-xs); color: var(--foms-text-tertiary); }
.field-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--foms-space-2) var(--foms-space-3); margin-bottom: var(--foms-space-3); }
.field-grid-2 .field { margin-bottom: 0; }

.foms-input, .foms-textarea, .foms-select {
  width: 100%; min-height: var(--foms-touch-target-min);
  padding: var(--foms-space-2) var(--foms-space-3);
  font-family: inherit; font-size: max(16px, var(--foms-font-size-base)); /* 16px=iOS 줌 방지 */
  color: var(--foms-text-primary); background: var(--foms-surface-base);
  border: 1px solid var(--foms-border-default); border-radius: var(--foms-radius-md);
  appearance: none;
}
.foms-input:focus, .foms-textarea:focus, .foms-select:focus {
  outline: none; border-color: var(--foms-border-focus); box-shadow: var(--foms-shadow-focus-ring);
}
.foms-textarea { min-height: 80px; resize: vertical; }
.foms-tabular { font-variant-numeric: tabular-nums; }
```

2. `static/css/foundation/foms-mobile-surfaces.css` 상단 `@import` 목록에 추가:
```css
@import url("../components/foms-form-field.css");
```
3. 검증(Phase 0): `python -c "import app; print('APP_OK')"` → APP_OK. test_client로 `/static/css/foundation/foms-mobile-surfaces.css` 200 + `/static/css/components/foms-form-field.css` 200. gstack로 위저드(`/add`, 플래그 ON시) 또는 임시 하네스에서 `.foms-input` 스타일 적용 육안 확인.
4. 커밋: `feat(css): 폼 원자 컴포넌트 shipped 포팅 (field/foms-input/foms-select/foms-textarea)`

> Phase 0만으로도 기존 위저드 폼 스타일이 정상화된다(부수 효과 이득).

### Phase 1 — 복사본 생성 + 분기 연결 + 기본/고객/발주/주소 섹션 변환

**먼저(필수):**
1. `copy templates/orders/partials/erp_order_tab.html templates/orders/partials/erp_order_tab_mobile.html` (verbatim 복사).
2. `edit_order_body.html:536` 을 §4 분기 코드로 교체.
3. 이 상태로 §9 검증 → cohort ON이 레거시와 동일하게 동작하는지 확인(회귀 0 base 확보).

**그 다음 변환 대상:** 복사본 상단 입력군 (대략 line 59~175, `#erp-form` pane 내).
필드(↔ 보존 id): 접수일 `erp-received-date`, 접수시간 `erp-received-time`, 긴급 `erp-urgent-flag`, 자가실측 `erp-self-measurement`, 긴급사유 `erp-urgent-reason`, 고객명 `erp-customer-name`, 연락처 `erp-customer-phone`, 수동입력 `erp-manual-phone-input`, 연락처특이 `erp-phone-note`/`erp-collapse-phone-note`, 발주사 `erp-orderer-direct`/`erp-orderer-select`/`erp-orderer`, 담당 `erp-manager`, 시공자 `erp-construction-workers`, 단계 `erp-workflow-stage`, 비고 `erp-notes`, 주소 `erp-address`/`erp-address-search-btn`/`erp-address-note`/`erp-collapse-address-note`(+btn).

remarkup 규칙(필드 1개당):
```jinja
<div class="field">
  <label class="field__label" for="erp-customer-name">고객명</label>
  <input class="foms-input" id="erp-customer-name" name="customer_name" autocomplete="name" lang="ko">
</div>
```
- `class="form-control form-control-sm"` → `class="foms-input"` (input), `class="form-select form-select-sm"` → `class="foms-select"` (select), textarea → `foms-textarea`.
- 날짜/시간/금액 input엔 `foms-input foms-tabular`.
- 한 줄 2칼럼(예: 접수일+접수시간, 실측일+시공일)은 `<div class="field-grid-2"> … </div>`.
- 체크박스/토글은 mockup 패턴 유지(가능하면 `field` 밖 inline). Bootstrap `form-check`는 시각만 정리하되 id/`form-check-input` 동작 보존.
- **id/name/data-*/JS-hook 클래스 그대로.** Bootstrap 레이아웃 클래스(`row`,`col-*`,`mb-3`,`g-2`)는 제거 가능(시각만).
- 카드 헤더 "구조화 입력/계약서" pill 탭(`erp-form-tab`/`erp-estimate-tab`, target `#erp-form`/`#erp-estimate`)과 `#erp-order` 루트 컨테이너 구조/속성(`data-erp-surface`, `data-erp-ready`, `data-erp-order-id`)은 **반드시 유지**(JS 진입점).

검증(§9) 후 커밋: `feat(mobile): ERP 주문편집 폼 모바일화 Phase1 기본/고객/발주/주소`

### Phase 2 — 일정 섹션
실측패널 `erp-order-measurement-panel`, 실측일 `erp-measurement-date`(+open), 시공일 `erp-construction-date`(+open), 실측시간 `erp-measurement-time`/`-select`, 시공시간 `erp-construction-time`/`-select`, 실측특이 `erp-measurement-note`/`erp-collapse-measure-note`. → `field-grid-2`로 일자/시간 2칼럼. 캘린더 버튼(`-open`) `field__addon` 패턴.

### Phase 3 — 라인아이템 / 금액 (가장 까다로움)
`erp-items`(컨테이너), `erp-add-item-btn`, 합계 `erp-items-total`, 계약금 `erp-deposit-amount`/`erp-deposit-section`, 잔금 `erp-remaining-amount`/`erp-remaining-section`, `erp-status-text`. 라인아이템 카드는 **이미 shipped된 `foms-product-item.css`의 `product-item-card`** 재사용. ⚠️ `product-item.js`가 생성/복제하는 DOM 구조(`.erp-item-row`, `.erp-spec-row(s)`, `.erp-add-spec-row-btn`, `.erp-remove-*`, `.erp-amount-value`)와 **정확히 일치**해야 함 → product-item.js의 템플릿 생성 코드를 먼저 읽고 클래스/구조를 맞출 것. 금액 input(`erp-deposit-amount` 등)은 `erp-amount-value` 클래스 유지(쉼표 포맷 JS).

### Phase 4 — 액션바 / 계약서 탭
채널톡 `erp-channeltalk-push-btn`, 텍스트생성 `erp-gen-text-btn`/`erp-conversion-text`/`erp-copy-text-btn`, 저장 `erp-save-btn`, 불러오기 `erp-load-btn`. **계약서 탭(pill `erp-estimate-tab` → pane `#erp-estimate`, 라벨 "계약서")** 의 견적/계약 미리보기(estimate-preview.js)·첨부 갤러리(`erp-attachments-*`) 유지. 액션은 하단 고정 바(`foms-btn foms-btn--primary foms-btn--lg` 등 mockup 버튼) 권장.

---

## 6. 계약 테스트 (Phase 1과 함께 작성, 이후 갱신)

`tests/visual/test_erp_order_edit_mobile_form.py`:
- **id 동일성**: `erp_order_tab.html`과 `erp_order_tab_mobile.html`에서 정규식으로 `id="..."` 집합 추출 → 모바일이 레거시의 §8 핵심 id를 **모두 포함**(누락 0). 드리프트 방지의 핵심.
- **렌더**: cohort ON으로 `/edit/<id>?open=erp-order` GET → 200 + `foms-input`/`field` 포함 + 레거시 `form-control form-control-sm` 미포함(모바일 분기 시).
- **데스크톱**: cohort OFF → 기존 `erp_order_tab.html`(`form-control`) 렌더, `foms-input` 미포함.
- 픽스처 패턴은 `tests/visual/test_edit_order_mobile_v2_shell.py`(선행 작성됨) 참고.

---

## 7. POST 저장 필드 계약 (edit.py — name 보존 확인용)
`received_date, received_time, customer_name, phone, address, product, notes, status, measurement_date, measurement_time, completion_date, manager_name, scheduled_date, as_received_date, as_completed_date, shipping_scheduled_date, option_type, direct_*, options_online, payment_amount, is_regional, is_self_measurement, measurement_completed, construction_type, is_cabinet, regional_*`.
※ ERP 탭은 주로 `erp-order-shared.js`가 `/api/...`로 저장(structured_data). name보다 **id 보존이 우선**. 비-ERP 경로 호환 위해 name 있는 건 유지.

## 8. 보존 id 인벤토리 (erp-order-shared.js 의존 — 전수)
```
erp-order, erp-order-config, erp-order-bootstrap, erp-order-tab, erp-order-measurement-panel,
erp-received-date, erp-received-time, erp-urgent-flag, erp-urgent-reason, erp-self-measurement,
erp-customer-name, erp-customer-phone, erp-manual-phone-input, erp-phone-note,
erp-orderer-direct, erp-orderer-select, erp-orderer, erp-manager, erp-construction-workers,
erp-workflow-stage, erp-notes, erp-address, erp-address-search-btn, erp-address-note,
erp-measurement-date, erp-measurement-date-open, erp-construction-date, erp-construction-date-open,
erp-measurement-time, erp-measurement-time-select, erp-construction-time, erp-construction-time-select,
erp-measurement-note, erp-items, erp-add-item-btn, erp-items-total,
erp-deposit-amount, erp-deposit-section, erp-remaining-amount, erp-remaining-section, erp-status-text,
erp-channeltalk-push-btn, erp-gen-text-btn, erp-conversion-text, erp-copy-text-btn,
erp-save-btn, erp-load-btn, erp-draft-banner, erp-draft-order-id, erp-draft-edit-link,
erp-quest-container, erp-quest-title, erp-quest-description, erp-quest-owner-team,
erp-quest-status-badge, erp-quest-status-btn, erp-quest-status-text, erp-quest-approvals,
erp-attachments-input, erp-attachments-upload-btn, erp-attachments-gallery, erp-attachments-category,
erp-attachments-progress, erp-attachments-progress-bar, erp-attachments-status,
erp-attachment-preview-body, erp-attachment-preview-download,
erp-address-modal-query, erp-address-modal-detail, erp-address-modal-search-btn,
erp-address-modal-results, erp-address-modal-status, erp-address-modal-apply-btn,
erp-collapse-phone-note, erp-collapse-address-note, erp-collapse-address-note-btn, erp-collapse-measure-note
```
JS-hook 클래스: `erp-amount-value`(+`--deposit`), `erp-item-row`, `erp-item-title`, `erp-spec-row(s)`, `erp-add-spec-row-btn`, `erp-remove-spec-row-btn`, `erp-remove-item-btn`, `erp-item-attachments-gallery`, `erp-item-attachment-hint`, `erp-item-date-multiple`, `erp-custom-payment-icon`. 속성: `data-erp`, `data-erp-order-id`, `data-erp-order-enabled`, `data-erp-surface`, `data-erp-ready`.
> 실행 전 재확인: `grep -oE "getElementById\(['\"][a-zA-Z0-9_-]+['\"]\)" static/js/orders/erp-order-shared.js` 로 현행 id를 다시 추출해 대조.

---

## 9. 검증 절차 (Phase마다 반복 — gstack 필수)

로컬 DB는 Postgres 스키마 드리프트로 `/edit` 직접 렌더 불가 → **sqlite + test_client로 HTML 렌더 → static 참조를 repo 절대경로로 치환 → gstack file:// 로드**(선행 세션 검증법 동일).

1. `APP_OK`: `python -c "import app; print('APP_OK')"`.
2. 렌더 캡처(sqlite): `ERP_MOBILE_V2_ENABLED=true` + `FOMS_V3_SHELL_COHORT=<uid>` 로 cohort 유저+ERP order 시드 후 `/edit/<id>?open=erp-order` GET → HTML 저장, `="/static/`→`="file:///<repo>/static/` 치환.  ※ sqlite 영속이므로 유저 username은 유니크하게.
3. gstack 412×915:
```bash
B="$HOME/.claude/skills/gstack/browse/dist/browse"
$B viewport 412x915
$B goto "file:///<TEMP>/edit_rendered.html"
$B wait --networkidle
$B js "JSON.stringify({inputStyled: getComputedStyle(document.querySelector('#erp-customer-name')).borderRadius, ids: ['erp-items','erp-deposit-amount','erp-save-btn'].map(function(i){return !!document.getElementById(i)})})"
$B screenshot --viewport "/<TEMP>/edit_mobile.png"   # Read 툴로 육안 확인
```
   - 기준: 보존 id 전부 present(true), `.foms-input` 라운드/포커스 적용, mockup과 시각 일치.
4. 저장 회귀: cohort ON으로 폼 변경 후 POST(또는 erp save API) → 정상 저장 + structured_data 반영 확인(가능하면 test_client POST 어서션).
5. 계약 테스트: `python -m pytest tests/visual/test_erp_order_edit_mobile_form.py -q`.
6. 전체 가드: `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual` → exit 0. (UI 변경이므로 win32 baseline stale면 `python -m pytest tests/visual --update-snapshots -q` 후 변경분만 커밋. /edit는 baseline 세트 밖이라 보통 변경 0.)

---

## 10. 함정 / 주의 (선행 세션에서 실제 발생)

- **캐시:** `/static`은 선행 커밋으로 css/js no-cache(ETag) 서빙 → 배포 자동 반영. 단 `?v=` 가진 `<link>`는 편집 시 버전 올릴 것. 클라이언트 잔존 캐시 있으면 1회 강력 새로고침.
- **service worker:** v2 network-first(css/js). 신규 css도 자동 최신.
- **gstack file:// 렌더 함정:** 캡처 스크립트가 sqlite 유저 username 중복으로 죽으면 stale 파일을 보고 "CSS 미로드" 오판하기 쉬움 → 유니크 username + try/except + `has foms-form-field` 출력으로 확인.
- **product-item.js 구조 일치:** Phase 3은 JS가 만드는 DOM과 클래스가 어긋나면 라인아이템/금액이 깨짐 → JS 먼저 읽고 맞출 것.
- **데스크톱 회귀 금지:** 분기 `else`로 레거시 유지 확인(계약 테스트 cohort OFF).

---

## 11. 완료 정의 (DoD)

- [ ] Phase 0~4 전부 머지, 각 Phase gstack 412px 스크린샷이 mockup과 일치.
- [ ] §8 보존 id 전수 present (계약 테스트 green).
- [ ] cohort ON: 모바일 폼(`foms-input`/`field`), cohort OFF/데스크톱: 레거시 폼 — 둘 다 정상.
- [ ] ERP 주문 저장·견적계산·라인아이템·계약금/잔금·채널톡·주소검색·실측 모두 동작(회귀 없음).
- [ ] `pre_push_smoke.ps1 -Visual` exit 0.
- [ ] `docs/AI_STATUS.md`/`AI_CHANGELOG.md` 갱신.

---

## 부록 A — gstack 검증 캡처 스크립트 (그대로 사용)

로컬 Postgres는 `/edit` 직접 렌더 불가 → sqlite + test_client로 HTML 생성 후 file:// 로드. `c:/tmp/capture_edit.py` 로 저장하고 `DATABASE_URL='sqlite:///tests/visual/visual_local.sqlite' python c:/tmp/capture_edit.py` 실행(레포 루트 cwd):

```python
import os, sys, time, datetime, traceback
sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("DATABASE_URL", "sqlite:///tests/visual/visual_local.sqlite")
os.environ["ERP_MOBILE_V2_ENABLED"] = "true"
try:
    import app as app_module
    from db import db_session
    from models import User, Order
    from werkzeug.security import generate_password_hash
    a = app_module.app; a.config["WTF_CSRF_ENABLED"] = False
    a.jinja_env.cache = None; a.jinja_env.auto_reload = True
    uniq = f"cap_{os.getpid()}_{int(time.time())}"            # sqlite 영속 → 유니크 필수
    u = User(username=uniq, password=generate_password_hash("x"), role="ADMIN", team="CS", name="cap", is_active=True)
    db_session.add(u); db_session.commit()
    os.environ["FOMS_V3_SHELL_COHORT"] = str(u.id)
    o = Order(received_date=datetime.date.today().isoformat(), customer_name="박태준",
              phone="010-9409-8108", address="서울시 강남구 1", product="슬라이딩",
              is_erp_order=True, structured_data={"workflow": {"stage": "RECEIVED"}})
    db_session.add(o); db_session.commit()
    c = a.test_client()
    with c.session_transaction() as s:
        s["user_id"] = u.id; s["username"] = u.username; s["role"] = u.role
    html = c.get(f"/edit/{o.id}?open=erp-order").get_data(as_text=True)
    print("has foms-input:", "foms-input" in html, "| has foms-form-field css:", "foms-form-field" in html)
    repo = os.getcwd().replace("\\", "/")
    html = html.replace('="/static/', f'="file:///{repo}/static/').replace("='/static/", f"='file:///{repo}/static/")
    out = os.path.join(os.environ.get("LOCALAPPDATA", "C:/Users/USER/AppData/Local"), "Temp", "edit_rendered.html")
    open(out, "w", encoding="utf-8").write(html); print("wrote", out)
except Exception:
    traceback.print_exc()
```

그 다음 gstack(§9-3) 로 `file:///<...>/Temp/edit_rendered.html` 로드·스크린샷·id present 확인. 작업 후 임시 파일 삭제.

## 12. 착수 순서 한눈에
1) Phase 0 CSS 포팅+import+검증+커밋 → 2) 계약 테스트 골격 + edit_order_body 분기 + `erp_order_tab_mobile.html` 생성(Phase1) → 3) Phase 2 → 4) Phase 3(JS 선독) → 5) Phase 4 → 6) 전체 회귀 + 스모크 + 문서.
