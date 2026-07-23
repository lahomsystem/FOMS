# 모바일 계산기 Field Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모바일(<992) 계산기에서 모드를 3칸 세그먼트로 고르고, 커스텀·직접 가격을 세로 전폭·크게 보이게 한다.

**Architecture:** `mobile-enhance.js`의 `buildBaseToolbar`가 기존 숨김 `.base-mode-btn`을 툴바 세그먼트로 올리고 `.base-mode-select`는 화면에서만 숨긴다(엔진 SSOT 유지). 커스텀/직접 배치는 `mobile.css`/`builder.css`에서 `display:contents` 한줄 압착을 폐기하고 전폭 세로 스택으로 덮는다. PC·pricing-core·태블릿 비범위.

**Tech Stack:** Vanilla JS, Bootstrap 5 classes, FOMS CSS tokens, pytest 계약 테스트

**Spec:** `docs/plans/2026-07-23-mobile-wdcalculator-field-form-design.md`

## Global Constraints

- 모바일만 (`body.wd-calc-mobile` / `body.wd-builder` 미디어 범위 유지). 데스크톱 ≥992 회귀 금지.
- `.base-mode-select` DOM·엔진 경로 유지. UI만 세그먼트.
- `pricing-core` / 제품 바텀시트 / 태블릿 스킨 / 빌더 IA 재작성 금지.
- 캐시 범프: `mobile-enhance.js`·`mobile.css`·`builder.css` → `?v=20260723a` (및 계약 리터럴 동기).
- 커밋은 사용자 요청 시에만. 임의 commit/push 금지.
- Win11 PowerShell: 명령 연결은 `;` ( `&&` 금지).

---

## File map

| File | Responsibility |
|------|----------------|
| `static/js/wdcalculator/mobile-enhance.js` | 툴바: 세그먼트 노출 + select 숨김 |
| `static/css/wdcalculator/mobile.css` | 세그먼트·세로스택·가격 크기 |
| `static/css/wdcalculator/builder.css` | builder 셸 manual/direct 그리드 정렬 |
| `templates/wdcalculator/calculator.html` | `?v=` 범프 |
| `tests/domains/test_wdcalculator_engine_v2_contract.py` | 세그먼트/스택 계약 핀(+캐시 허용) |
| `docs/plans/2026-07-23-mobile-wdcalculator-field-form-design.md` | 상태 🟢 |

---

### Task 1: 모드 세그먼트 툴바 (JS)

**Files:**
- Modify: `static/js/wdcalculator/mobile-enhance.js` (`buildBaseToolbar` ~556–580)
- Test: `tests/domains/test_wdcalculator_engine_v2_contract.py` (신규 assert 추가)

**Interfaces:**
- Consumes: host `.base-mode-select`, `.base-mode-btn` (hooks), `.base-remove-btn`, `applyBaseMode` via existing click 위임
- Produces: toolbar DOM `.wd-bc-toolbar` > `.wd-bc-mode-seg.btn-group` + `.base-remove-btn`; select has `.wd-bc-mode-select-hidden`

- [ ] **Step 1: Write failing contract asserts**

`tests/domains/test_wdcalculator_engine_v2_contract.py`에 추가:

```python
def test_mobile_mode_segment_toolbar_contract():
    """모바일 툴바: 세그먼트 클래스 + select 숨김 클래스 + buildBaseToolbar 존재."""
    assert "function buildBaseToolbar" in MOBILE
    assert "wd-bc-mode-seg" in MOBILE
    assert "wd-bc-mode-select-hidden" in MOBILE
    assert "base-mode-btn" in MOBILE
```

- [ ] **Step 2: Run test — expect FAIL**

```powershell
pytest tests/domains/test_wdcalculator_engine_v2_contract.py::test_mobile_mode_segment_toolbar_contract -q
```

Expected: FAIL (`wd-bc-mode-seg` not in MOBILE)

- [ ] **Step 3: Replace `buildBaseToolbar` implementation**

`buildBaseToolbar`를 아래로 교체 (기존 함수 전체 교체):

```javascript
    function buildBaseToolbar(rowEl) {
      var body = rowEl.querySelector(".card-body");
      if (!body || body.querySelector(".wd-bc-toolbar")) return;
      var modeSelect = rowEl.querySelector(".base-mode-select");
      var hooks = rowEl.querySelector(".base-mode-btn-hooks");
      var modeBtns = rowEl.querySelectorAll(".base-mode-btn");
      var del = rowEl.querySelector(".base-remove-btn");
      if (!modeSelect && !modeBtns.length && !del) return;

      var toolbar = document.createElement("div");
      toolbar.className = "wd-bc-toolbar";

      if (modeSelect) {
        modeSelect.classList.add("wd-bc-mode-select-hidden");
        modeSelect.setAttribute("aria-hidden", "true");
        modeSelect.tabIndex = -1;
        var selectCol = modeSelect.closest('[class*="col-"]');
        if (selectCol) selectCol.classList.add("wd-bc-orphan-col");
      }

      if (modeBtns.length) {
        var seg = document.createElement("div");
        seg.className = "btn-group wd-bc-mode-seg";
        seg.setAttribute("role", "group");
        seg.setAttribute("aria-label", "방식");
        forEachNode(modeBtns, function (btn) {
          seg.appendChild(btn);
        });
        if (hooks) {
          hooks.classList.add("wd-bc-orphan-col");
          hooks.classList.remove("d-none");
          hooks.setAttribute("aria-hidden", "true");
        }
        toolbar.appendChild(seg);
      } else if (modeSelect) {
        // fallback: 세그먼트 없으면 select 노출(레거시)
        modeSelect.classList.remove("wd-bc-mode-select-hidden");
        toolbar.appendChild(modeSelect);
      }

      if (del) {
        var delCol = del.closest('[class*="col-"]');
        toolbar.appendChild(del);
        if (delCol) delCol.classList.add("wd-bc-orphan-col");
      }

      body.insertBefore(toolbar, body.firstChild);
    }
```

Note: `forEachNode` already exists in this file. If not in scope of this function’s closure, use `Array.prototype.forEach.call(modeBtns, ...)`.

- [ ] **Step 4: Run contract — expect PASS**

```powershell
pytest tests/domains/test_wdcalculator_engine_v2_contract.py::test_mobile_mode_segment_toolbar_contract tests/domains/test_wdcalculator_engine_v2_contract.py::test_base_mode_select_ssot -q
```

Expected: PASS (select SSOT still in PRIMARY)

- [ ] **Step 5: Commit only if user asks** — skip unless requested

---

### Task 2: 세그먼트 + 커스텀/직접 세로 스택 CSS

**Files:**
- Modify: `static/css/wdcalculator/mobile.css` (mode select block ~441–469; manual contents block ~365–415; fee area)
- Modify: `static/css/wdcalculator/builder.css` (manual grid ~143–220)
- Test: same contract file + CSS 문자열 pin

**Interfaces:**
- Consumes: `.wd-bc-mode-seg`, `.wd-bc-mode-select-hidden`, `.base-manual-*`, `.base-additional-fee-*`
- Produces: visual vertical stack; price ≥48px

- [ ] **Step 1: Add failing CSS contract**

```python
def test_mobile_field_form_stack_css_contract():
    css = (ROOT / "static/css/wdcalculator/mobile.css").read_text(encoding="utf-8")
    assert ".wd-bc-mode-seg" in css
    assert ".wd-bc-mode-select-hidden" in css
    assert "wd-field-price" in css or "base-manual-price30" in css
    # 한줄 압착(contents로 30cm|1cm|W) 대신 전폭 스택 마커
    assert "wd-field-stack" in css
```

- [ ] **Step 2: Run — expect FAIL**

```powershell
pytest tests/domains/test_wdcalculator_engine_v2_contract.py::test_mobile_field_form_stack_css_contract -q
```

- [ ] **Step 3: CSS — mode segment + hide select**

`mobile.css`에서 `[A] 방식 select` 블록(~441)을 보강/교체:

```css
  /* Field Form: 모드 세그먼트 (select는 SR/엔진용 숨김) */
  body.wd-calc-mobile .wd-bc-mode-select-hidden,
  body.wd-calc-mobile .base-component-row .base-mode-select.wd-bc-mode-select-hidden {
    position: absolute !important;
    width: 1px !important; height: 1px !important;
    padding: 0 !important; margin: -1px !important;
    overflow: hidden !important; clip: rect(0, 0, 0, 0) !important;
    border: 0 !important;
  }
  body.wd-calc-mobile .wd-bc-toolbar {
    display: flex; align-items: stretch; gap: 10px;
    margin-bottom: var(--foms-space-3);
  }
  body.wd-calc-mobile .wd-bc-mode-seg {
    flex: 1; min-width: 0; display: flex; width: auto !important; margin: 0;
  }
  body.wd-calc-mobile .wd-bc-mode-seg .base-mode-btn {
    flex: 1; min-width: 0; min-height: 44px;
    font-size: 13px; padding: 0 4px;
  }
  body.wd-calc-mobile .wd-bc-toolbar .base-remove-btn {
    flex-shrink: 0; width: 44px; min-height: 44px;
    margin-left: 4px;
  }
  /* hooks 컨테이너는 버튼 이동 후 빈 껍질 — 숨김 */
  body.wd-calc-mobile .base-mode-btn-hooks { display: none !important; }
```

- [ ] **Step 4: CSS — custom vertical stack (replace contents one-line block)**

`mobile.css` ~365–415 블록을 **교체**:

```css
  /* Field Form: 커스텀 = 세로 전폭 스택 (한줄 압착 폐기) */
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-area.wd-field-stack,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-area {
    display: flex !important;
    flex-direction: column !important;
    gap: 10px !important;
    width: 100% !important;
  }
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-details-area,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-area > .row {
    display: flex !important;
    flex-direction: column !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
  }
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-area > .mb-2,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-area > .row > [class*="col-"],
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-30cm-col,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-1cm-col,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-1m-col,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .card-body > .row > .base-width-col {
    flex: 0 0 auto !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    margin: 0 0 8px 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
  }
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-name,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-pricing-type,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-price30,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-price1,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-price1m,
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-width-input,
  body.wd-calc-mobile .base-component-row .base-additional-fee-name,
  body.wd-calc-mobile .base-component-row .base-additional-fee-amount {
    display: block !important;
    width: 100% !important;
    min-height: 48px !important;
    height: auto !important;
    font-size: 18px !important;
    font-variant-numeric: tabular-nums;
    box-sizing: border-box !important;
  }
  body.wd-calc-mobile .base-component-row[data-mode="manual"] .base-manual-price30,
  body.wd-calc-mobile .base-component-row .base-additional-fee-amount {
    font-size: 20px !important;
    font-weight: var(--foms-font-weight-semibold);
  }
  /* 직접 fee: 가로 그리드 → 세로 */
  body.wd-calc-mobile .base-component-row .base-additional-fee-item {
    display: flex !important;
    flex-direction: column !important;
    gap: 8px !important;
    margin-bottom: 10px !important;
  }
  body.wd-calc-mobile .base-component-row .base-additional-fee-item > [class*="col-"] {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
  }
  body.wd-calc-mobile .base-component-row .base-additional-fee-item .base-remove-fee-btn {
    align-self: flex-end;
    min-height: 44px;
    width: 44px;
  }
```

Also add inert marker comment for contract:

```css
  /* wd-field-stack: Field Form vertical stack marker */
```

(또는 JS에서 `base-manual-area`에 `wd-field-stack` 클래스 부여 — Task 1에 한 줄 추가해도 됨.)

`enhanceBaseRow` 또는 `buildBaseToolbar` 끝에서:

```javascript
      var manualArea = rowEl.querySelector(".base-manual-area");
      if (manualArea) manualArea.classList.add("wd-field-stack");
```

- [ ] **Step 5: builder.css — stop fighting mobile stack**

`builder.css` manual `display: contents` + 12-col grid (~143–190)를 **모바일 builder에서 세로로 덮기**. `body.wd-builder`는 모바일에서만 enable되므로 해당 규칙을 세로 스택으로 교체:

```css
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .card-body > .row {
    display: flex !important;
    flex-direction: column !important;
    gap: 8px !important;
  }
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-details-area,
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-manual-area,
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-manual-area > .row {
    display: flex !important;
    flex-direction: column !important;
    width: 100% !important;
  }
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-manual-area > .mb-2,
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-manual-area > .row > .col-4,
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-manual-30cm-col,
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-manual-1cm-col,
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-manual-1m-col,
  body.wd-builder .wd-esec .base-component-row[data-mode="manual"] .base-width-col {
    width: 100% !important;
    max-width: 100% !important;
    grid-column: auto !important;
  }
  body.wd-builder .wd-esec .base-component-row .base-additional-fee-item {
    grid-template-columns: 1fr !important;
    display: flex !important;
    flex-direction: column !important;
  }
```

- [ ] **Step 6: Run CSS contract + engine suite subset**

```powershell
pytest tests/domains/test_wdcalculator_engine_v2_contract.py -q
```

Expected: PASS

---

### Task 3: 캐시 범프 + 스펙 상태 + 검증

**Files:**
- Modify: `templates/wdcalculator/calculator.html` (`mobile.css`/`builder.css`/`mobile-enhance.js` `?v=`)
- Modify: `docs/plans/2026-07-23-mobile-wdcalculator-field-form-design.md` 상태 → 🟢
- Optionally loosen: `test_wdcalculator_engine_v2_contract.py` line ~89 if it pins exact `20260716i`

- [ ] **Step 1: Bump cache versions**

`calculator.html`:

```html
<link ... wd-line.css') }}?v=20260723a">
<link ... mobile.css') }}?v=20260723a">
<link ... builder.css') }}?v=20260723a">
...
<script ... mobile-enhance.js') }}?v=20260723a" defer></script>
```

- [ ] **Step 2: Fix any hard-pinned `?v=20260716i` / `20260716g` asserts for these three assets**

Grep:

```powershell
rg "20260716[ig].*mobile|mobile.*20260716" tests
```

Update pins to `20260723a` or keep the existing loose `?v=` alternate assert.

- [ ] **Step 3: APP_OK + focused pytest**

```powershell
python -c "import app; print('APP_OK')"
pytest tests/domains/test_wdcalculator_engine_v2_contract.py tests/domains/test_wdcalculator_estimate_reset_contract.py -q
```

Expected: `APP_OK`, pytest green

- [ ] **Step 4: Manual smoke checklist (390px or DevTools)**

1. 새 견적 → 모드 3버튼 보임, 네이티브 모드 드롭다운 안 보임
2. 커스텀 → 가격 `187000` 전폭·크게
3. 직접 → 금액 전폭
4. 데스크톱 폭 → select 유지·깨짐 없음

- [ ] **Step 5: Spec status → 🟢 승인됨 / 구현 완료 표기**

- [ ] **Step 6: Commit/push only if user asks**

---

## Spec coverage (self-review)

| Spec req | Task |
|----------|------|
| 3칸 세그먼트 + 삭제 격리 | Task 1 + Task 2 CSS |
| select SSOT 숨김 동기 | Task 1 (btn→기존 applyBaseMode) |
| 커스텀 세로 전폭 | Task 2 |
| 직접 세로 전폭 | Task 2 |
| 가격 ≥48px tabular-nums | Task 2 |
| 데스크톱 무변경 | Global + Task 1 only under mobile enhance |
| ?v= + 계약 | Task 3 |
| 태블릿/엔진 비범위 | Global Constraints |

Placeholder scan: none. Type names: `wd-bc-mode-seg`, `wd-bc-mode-select-hidden`, `wd-field-stack` consistent across tasks.
