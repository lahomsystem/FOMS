# WD 계산기 태블릿 v2 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 승인 스펙(docs/plans/2026-07-16-wdcalculator-tablet-v2-redesign-spec.md, v3)대로 — 엔진 확장 5점(E1~E5, PC·모바일 공통) + 태블릿 가로 계산기 표면(tablet-skin) 그라운드업 재작성.

**Architecture:** 계산·저장 엔진 코어 무접촉. E1~E5만 엔진 텍스트/필드 최소 확장. 태블릿 표면은 신규 DOM + 은닉 엔진 위젯 양방향 미러(T16/T18 검증 패턴 승계).

**Tech Stack:** Vanilla JS(IIFE, ES5 스타일 준수 — 기존 파일과 동일), CSS(자체 링크 tablet-skin.css), pytest 구조 계약 테스트.

**목업 SSOT:** `docs/design/mockups/tablet-wdcalculator-v2.html` (Task 0에서 커밋) — Frame 1(메인)·2(제품 시트)·3(저장 견적 오버레이).

## Global Constraints

- 게이트: `(min-width: 992px) and (orientation: landscape) and (pointer: coarse)` 且 비임베디드 — 변경 금지.
- 손대지 않는 것: `composition.js` 부트스트랩 구조, `foms/api/wdcalculator/blueprint.py`, 계산 수식 일체, `mobile-enhance.js`의 빌더 구조(라벨·이름 폴백만 수정).
- 커밋 메시지 한글 = UTF-8 파일 작성 후 `git commit -F` (Win11 — `-m "한글"` 금지).
- JS/CSS 내용 변경과 `?v=` 범프는 같은 커밋에서 원자적으로 (SW stale 캐시 함정).
- `python -c "import app; print('APP_OK')"` 성공 유지.
- 신규 함수 docstring·타입힌트(Python), 인라인 스타일 금지(CSS 파일로), G4(전역 리스너 singleton 가드).
- CRLF 파일 주의: `templates/wdcalculator/*.html` 편집 후 팬텀 diff 확인 (`git diff --stat`).

---

### Task 0: 목업 SSOT 커밋 (오케스트레이터 직접)

- [ ] 세션 스크래치패드 `wdc-tablet-v2-mockup.html` → `docs/design/mockups/tablet-wdcalculator-v2.html` 복사, 커밋.

---

### Task 1: 엔진 확장 E1·E3·E4·E5 (PC·모바일 공통)

**Files:**
- Modify: `static/js/wdcalculator/primary-form.js` (renderBaseComponentRow ~464, readBaseComponentsFromUI ~563, base-add-fee 라벨 ~533)
- Modify: `static/js/wdcalculator/pricing-core.js` (manual 분기 100~143, 폴백 compData 178~191, 추가금 표기 192~215)
- Modify: `static/js/wdcalculator/mobile-enhance.js` (~462-475 이름 폴백, 모드 토글 라벨)
- Modify: `templates/wdcalculator/partials/wdcalculator_body.html` (calculateBtn 블록 195~198 삭제)
- Test: `tests/domains/test_wdcalculator_engine_v2_contract.py` (신규)

**Interfaces (Produces — Task 2가 의존):**
- `.base-manual-name` — MINE 행 제품명 `<input type="text">` (manual 영역 내, placeholder "제품명 입력")
- `readBaseComponentsFromUI()` 반환 comp에 `manualName: string` 포함(manual 모드)
- pricing-core 정규화 compData에 `manualName` 보존 → 저장/재로드 왕복 성립
- PC 모드 버튼 라벨: `선택` / `MINE` (클래스·data-mode="manual" 불변)
- fee 추가 버튼 라벨: `직접입력` (클래스 `.base-add-fee-btn` 불변)

- [ ] **Step 1: 실패하는 계약 테스트 작성**

`tests/domains/test_wdcalculator_engine_v2_contract.py`:

```python
"""WD 계산기 엔진 v2 확장(E1~E5) 구조 계약.

E1: MINE(직접) 행 제품명 필드 + 저장 왕복(compData 보존)
E3: '직접'→'MINE', '추가금 추가'→'직접입력' 리네임
E4: 행별 직접입력 표기에서 '추가금' 접미사 제거(이름 있을 때)
E5: 견적 계산 버튼 전 플랫폼 삭제(계산은 전 입력 경로 자동)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = (ROOT / "static/js/wdcalculator/primary-form.js").read_text(encoding="utf-8")
PRICING = (ROOT / "static/js/wdcalculator/pricing-core.js").read_text(encoding="utf-8")
MOBILE = (ROOT / "static/js/wdcalculator/mobile-enhance.js").read_text(encoding="utf-8")
BODY = (ROOT / "templates/wdcalculator/partials/wdcalculator_body.html").read_text(encoding="utf-8")


def test_e1_manual_name_field_rendered_and_collected():
    assert PRIMARY.count("base-manual-name") >= 2  # 템플릿 렌더 + 수집
    assert "manualName" in PRIMARY


def test_e1_manual_name_survives_pricing_normalization():
    # compData 재구성(1m·30cm·폴백)에서 manualName 보존
    assert PRICING.count("manualName") >= 3


def test_e3_mode_button_renamed_to_mine():
    assert 'data-mode="manual">MINE<' in PRIMARY
    assert 'data-mode="manual">직접<' not in PRIMARY


def test_e3_fee_button_renamed():
    assert "직접입력" in PRIMARY  # base-add-fee-btn 라벨
    assert "추가금 추가" not in PRIMARY


def test_e4_fee_suffix_removed_when_named():
    # 이름 있으면 이름만, 이름 없을 때만 '추가금' 폴백
    assert 'name + " " :' not in PRICING or "추가금 " in PRICING
    assert PRICING.count('feeName + "추가금') == 0
    assert PRICING.count('feeNameA + "추가금') == 0


def test_e5_calculate_button_removed_from_template():
    assert "calculateBtn" not in BODY


def test_e5_binding_null_guard_kept():
    # 버튼 부재 시 무해해야 함 — 가드 존치 확인
    assert "if (!calculateBtn)" in PRIMARY


def test_mobile_manual_name_fallback():
    assert MOBILE.count("manualName") >= 2  # 1m·30cm 분기
```

- [ ] **Step 2: 테스트 실패 확인** — `python -m pytest tests/domains/test_wdcalculator_engine_v2_contract.py -v` → 전부 FAIL 예상.

- [ ] **Step 3: primary-form.js 수정**

3a. `renderBaseComponentRow` (~464): 변수 추가 후 manual 영역 최상단에 제품명 입력 삽입.

```js
var manualName = component.manualName != null ? String(component.manualName) : "";
```

base-manual-area 내부, `row g-2` div **앞**에:

```html
<div class="mb-2">
    <label class="form-label small mb-1">제품명</label>
    <input type="text" class="form-control form-control-sm base-manual-name"
           placeholder="제품명 입력" value="${escapeHtml(manualName)}">
</div>
```
(기존 문자열 연결 스타일 그대로 — 템플릿 리터럴 금지, `+ escapeHtml(manualName) +` 연결.)

3b. `readBaseComponentsFromUI` (~563) manual 분기: 두 return 객체(1m ~607, 30cm ~621) 모두에 추가:

```js
var manualNameEl = rowEl.querySelector(".base-manual-name");
var manualName = (manualNameEl && manualNameEl.value.trim()) || "";
// ... 각 객체 리터럴에:
manualName: manualName,
```

3c. 모드 버튼 라벨 (~497): `data-mode="manual">직접</button>` → `data-mode="manual">MINE</button>`.

3d. fee 라벨 (~521 '추가금' label, ~533 버튼): `<label class="form-label small mb-2">추가금</label>` → `직접입력`, `<i class="fas fa-plus"></i> 추가금 추가` → `<i class="fas fa-plus"></i> 직접입력`.

- [ ] **Step 4: pricing-core.js 수정**

4a. 1m 분기(107~117): compData 객체에 `manualName: comp.manualName || "",` 추가, 라벨:

```js
var label1m = (comp.manualName && String(comp.manualName).trim()) || "직접입력(1m)";
detailLines.push(label1m + " " + widthLabel(compData, formatNumber));
displayParts.push(label1m + " " + widthLabel(compData, formatNumber));
```

4b. 30cm 분기(127~141): 동일 패턴(`label30`, 폴백 `"직접입력(30cm)"`), compData에 `manualName` 추가.

4c. 폴백 compData(187~188): `compData.manualPricing = comp.manualPricing;` 옆에 `compData.manualName = comp.manualName || "";`.

4d. 추가금 표기(196~213):

```js
// 198행 무폭(width<=0) displayParts:
var feeLabelA = feeA.name ? feeA.name + " " : "추가금 ";
displayParts.push(feeLabelA + formatNumber(amtA) + "원");
// 209~213행:
var feeLabel = fee.name ? fee.name + " " : "추가금 ";
detailLines.push("+ " + feeLabel + formatNumber(amount) + "원");
if (widthMm > 0) {
    displayParts.push("+ " + feeLabel + formatNumber(amount) + "원");
}
```

- [ ] **Step 5: mobile-enhance.js 수정** — 466행 `name = "직접입력 (1m)"` → `name = (row && row.manualName) || "직접입력 (1m)";`, 472행 동일(30cm). 파일 내 base 모드 토글 가시 라벨 `직접` → `MINE` (grep으로 전수 — 단, "직접입력 (30cm)" 폴백 문자열·비고 관련 문구는 유지).

- [ ] **Step 6: wdcalculator_body.html** — calculateBtn `<button>` 블록(195~198) 삭제. addEstimateBtn·saveEstimateBtn 유지.

- [ ] **Step 7: 검증** — `python -m pytest tests/domains/test_wdcalculator_engine_v2_contract.py -v` 전부 PASS + `python -c "import app; print('APP_OK')"` + `python -m pytest tests/domains -k wdcalculator -v` 기존 무회귀.

- [ ] **Step 8: 커밋** — `feat: 계산기 엔진 v2 확장 E1~E5(MINE 제품명·리네임·추가금 표기·계산버튼 삭제)`

---

### Task 2: tablet-skin v2 그라운드업 재작성

**Files:**
- Rewrite: `static/js/wdcalculator/tablet-skin.js` (전면)
- Rewrite: `static/css/wdcalculator/tablet-skin.css` (전면)
- Modify: `tests/domains/test_wdcalculator_tablet_skin.py` (v2 계약으로 갱신)
- 참조(읽기 전용): `docs/design/mockups/tablet-wdcalculator-v2.html` — 시각/레이아웃 SSOT

**Interfaces (Consumes):** Task 1의 `.base-manual-name`, MINE 라벨, fee 서브행 위젯 클래스.

**구조 계약 (구현 필수 — 목업 Frame 1~3 정합):**

1. **게이트/수명주기(승계)**: GATE 동일, `__WDC_TABLET_SKIN_BOUND` 싱글톤, embedded(`wdcalculator-container--embedded`) 즉시 무시, 폰 셸(`body.wd-builder`) 양보, 게이트 이탈 시 이동 노드 역순 복원(`relocations` 배열 + `restoreAll`)·신규 DOM 파기·옵저버 해제. `body.wdc-tablet-v2` 클래스가 CSS 발현 키.
2. **D/H 코드 전면 삭제**: `encodeDH/parseDH/readRowDH/writeRowDH/feeItemHtml/DH_PREFIX` 제거. 구견적 `[규격]` 센티널은 fee 서브행으로 자연 노출(특별 처리 금지).
3. **레이아웃 DOM**: `.wdc2-topbar`(제목/고객명 이동/견적검색 버튼/제품설정 링크 이동) + `.wdc2-sheet`(구성 섹션·옵션 섹션·비고 섹션·조정 스트립) + `.wdc2-abar`(총견적 미러 + [진행 견적에 추가]) + `.wdc2-panel`(현재 견적 브레이크다운/estimatesListContainer 도킹/단가 토글 이동/전체합계/새 견적·전체 저장) + `.wdc2-saved-overlay`(저장 사이드바 카드 이동) + `.wdc2-sheetpicker`(공용 바텀시트). 기존 48px saved-rail 폐지.
4. **기본 구성 행 미러**(엔진 행 childList observer → 재빌드, 타이핑 클로버 금지 — 기존 v1 옵저버 패턴 승계):
   - 선택 행: [모드칩(n·선택/MINE, 탭=`.base-mode-btn` click 위임)] [제품 버튼→시트(`.base-product-select` 옵션 복제, pick→value+change)] [W(`.base-width-input` 양방향)] [단가(`wdcComputeCurrentEstimateMath([comp])` READ-ONLY, 금액만)] [✕(`.base-remove-btn`)]
   - MINE 행: 메인 행 상세 셀 = 제품명(`.base-manual-name` 양방향, 전폭) / **서브행** = 방식 드롭다운(`.base-manual-pricing-type` 미러, 자체 경량 시트 30cm·1m)+단가 입력(`.base-manual-price30` 또는 `-price1m` 미러, 소형 110px). 1cm 자동값 미노출.
   - fee 서브행: 엔진 `.base-additional-fee-item`별 [이름(`.base-additional-fee-name`)·금액(`.base-additional-fee-amount`)·✕(`.base-remove-fee-btn`)] 미러 + [＋ 직접입력](`.base-add-fee-btn` click).
   - 행 추가: [＋ 구성 행 추가](`#addBaseComponentBtn` click) / [✎ MINE 행 추가](동일 click 후 신규 행 `.base-mode-btn[data-mode="manual"]` click).
5. **추가 옵션 미러**: 엔진 옵션 item별 [배지(옵션/MINE=자유텍스트 여부)] [옵션 버튼→시트(`[data-category-option-select]` 복제) + 직접명(`.option-name-input` 양방향)] [금액(`[data-option-price]` 양방향)] [✕] + [＋ 옵션 추가](`#addOptionBtn`).
6. **비고 정식 섹션**: 엔진 note item(구현 착수 시 `#notesContainer` 실 DOM 클래스 실사 — composition.js WdCalculatorNotesUiBootstrap ~1311) 별 행 미러: [배지 문구/MINE] [내용 버튼→시트(저장 문구 그리드 + MINE 텍스트 입력)] [✕] + [＋ 비고 추가](`#btnAddNote`).
7. **조정 스트립**: 할인(`#globalCouponValue` 이동)·배송(`#shippingCost`·`#shippingIncluded` 이동) — 이동(재부모화), 폭 104px.
8. **라이브 패널/액션바**: `#finalPrice` MutationObserver → abar 대형 금액·패널 총견적. `#totalBasePrice`/`#totalAdditionalPrice` 옵저버 → 브레이크다운 행. 할인/배송 행은 입력값 직접 반영. [진행 견적에 추가]=`#addEstimateBtn` click 미러, [전체 저장]=`#saveEstimateBtn` **미러(cloneNode 교체 함정 — 이동 금지, 클릭 시 live lookup)**, [새 견적]=`#resetEstimateBtn` **동적 생성 — live lookup 미러**, 단가 토글=`#wdUnitPriceMetaToggle` 체크박스 이동.
9. **저장 견적 오버레이**: 탑바 [견적 검색] → `.saved-estimates-sidebar` 카드 노드 이동 + 슬라이드 오버레이(392px)+백드롭. `#refreshEstimatesBtn`·검색·리스트 그대로 작동.
10. **CSS**: 전면 재작성 — `:root` 아닌 게이트 블록 내 `.wdc-tablet-v2` 스코프 토큰(`--wdc2-desk:#EDEBE4; --wdc2-ink:#1C1E22; --wdc2-line:#E6E4DE; --wdc2-accent:#0F7B52; --wdc2-accent-ink:#0B5C3E; --wdc2-accent-tint:#EFF7F2; --wdc2-mine-tint:#FFF8EC; --wdc2-mine-ink:#8A6A1F; --wdc2-danger:#C2453B`). 행 52px·입력 44px·`font-variant-numeric: tabular-nums`. PC 스캐폴딩 은닉은 게이트+`body.wdc-tablet-v2` 이중 조건(파일 스코프 유령 규칙 금지). 목업의 픽셀 값 준수.
11. **G4**: 전역/document 리스너 singleton 가드. fragment 재실행 무해.

- [ ] **Step 1: 계약 테스트 갱신** — `tests/domains/test_wdcalculator_tablet_skin.py`를 v2로 재작성:

```python
"""WD 계산기 태블릿 v2 스킨 구조 계약."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/wdcalculator/tablet-skin.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/wdcalculator/tablet-skin.css").read_text(encoding="utf-8")
CAL = (ROOT / "templates/wdcalculator/calculator.html").read_text(encoding="utf-8")


def test_singleton_and_gate():
    assert "__WDC_TABLET_SKIN_BOUND" in JS
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in JS


def test_v2_dom_sections_present():
    for cls in ["wdc2-topbar", "wdc2-sheet", "wdc2-abar", "wdc2-panel",
                "wdc2-saved-overlay", "wdc-tablet-v2"]:
        assert cls in JS, cls


def test_dh_sentinel_removed():
    assert "[규격]" not in JS
    assert "parseDH" not in JS and "encodeDH" not in JS


def test_mine_mirror_contract():
    assert "base-manual-name" in JS
    assert "base-manual-pricing-type" in JS


def test_engine_button_mirrors():
    for sel in ["addBaseComponentBtn", "addOptionBtn", "btnAddNote",
                "addEstimateBtn", "saveEstimateBtn", "wdUnitPriceMetaToggle"]:
        assert sel in JS, sel


def test_calculate_btn_not_referenced():
    assert "calculateBtn" not in JS


def test_css_gate_and_tokens():
    assert "pointer: coarse" in CSS and "landscape" in CSS
    assert "--wdc2-accent" in CSS and "wdc-tablet-v2" in CSS


def test_calculator_template_wiring_defer():
    assert 'tablet-skin.js?v=' in CAL and "defer" in CAL
```

- [ ] **Step 2: 실패 확인** — v2 클래스 부재로 FAIL.
- [ ] **Step 3: tablet-skin.js 전면 재작성** (구조 계약 1~9·11, 목업 정합).
- [ ] **Step 4: tablet-skin.css 전면 재작성** (구조 계약 10, 목업 정합).
- [ ] **Step 5: 검증** — 해당 테스트 PASS + APP_OK + `python -m pytest tests/domains -k wdcalculator -v`.
- [ ] **Step 6: 커밋** — `feat: 계산기 태블릿 v2 표면 그라운드업(워크시트+라이브 패널, D/H 폐지)`

---

### Task 3: 캐시 범프 + 전수 검증 (오케스트레이터 직접)

- [ ] `templates/wdcalculator/calculator.html` — tablet-skin.css/js `?v=20260716a` → `?v=20260716b` (Task 1·2 내용 변경 동커밋 원칙이므로, 미범프 시 여기서 원자 처리).
- [ ] `grep -rn "tablet-skin" tests/` — ?v 핀 테스트 있으면 동기.
- [ ] `python -m pytest tests/domains -k "wdcalculator" -v` 전체 green.
- [ ] APP_OK + 로컬 서버 + coarse landscape 에뮬(CSSOM `(pointer:coarse)` strip + matchMedia 패치)로 Frame 1 실렌더 스냅샷 — 커버리지 25항목 체크표 작성.
- [ ] PC 뷰(폭 1600 fine) 무회귀: 계산 버튼 부재 + 자동 계산 확인, MINE 제품명 입력 노출.
- [ ] 커밋(범프 잔여분) — `chore: 계산기 태블릿 v2 ?v 범프`

## Self-Review 결과

- 스펙 §5 커버리지 25항목 → Task 2 계약 3~9가 전부 매핑(1↔topbar, 2·9↔overlay, 4~11↔계약4, 12~14↔계약5, 15↔계약6, 16·17↔계약7, 18 삭제=E5, 19~24↔계약8, 25↔계약1). §7 E1~E5 → Task 1. §6 D/H → Task 2 계약 2.
- 플레이스홀더: 비고 note item 클래스만 "착수 시 실사"로 명시(계약 6) — 실사 지점(파일:라인) 제공됨.
- 타입/명칭 일관성: `.base-manual-name`(T1 Produces = T2 Consumes), `wdc2-*` 접두 통일.
