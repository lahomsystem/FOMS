# W2 — 화면 배선 (도크 JS·CSS·자산 핀 소유)

작업 트리: `c:\tmp\foms-s-s0908-102606` (브랜치 `session/s0908-102606`).
bash cwd 는 호출 사이에 리셋된다 — 모든 명령을 `cd /c/tmp/foms-s-s0908-102606 && pwd && ...` 로 시작한다.

**먼저 읽어라**: `docs/plans/2026-09-08-naver-dock-autofill-contract.md` §4·§5·§6.
함수 이름·확인창 문구·칩 글자·핀 값은 그 문서가 정본이다. 한 글자도 바꾸지 마라.

## 네가 만지는 파일 (셋뿐)

- `static/js/orders/erp-naver-dock.js`
- `static/css/orders/erp-naver-dock.css`
- `templates/orders/partials/erp_order_js.html` (자산 핀 2줄만)

W1 이 `dock.py` 를, W3 이 테스트를 맡는다. **그 파일들은 읽기만** 해라.
`erp-order-shared.js`·`erp-items-master-detail.js`·`erp-order-autosave.js` 는 **읽기 전용 계약 근거**다 — 절대 고치지 마라.

## 앵커 (지금 코드 위치)

| 자리 | 무엇 |
| --- | --- |
| `erp-naver-dock.js:1-11` | 헤더 docstring — "값 전달은 사람이 복사 버튼으로만 한다" |
| `erp-naver-dock.js:12-17` | IIFE 시작 · 싱글톤 가드 · 모듈 변수(`state`, `completing`) |
| `erp-naver-dock.js:232-240` | 행 칩 렌더 — `(row.copies || []).forEach(...)`, `'📋 ' + value` |
| `erp-naver-dock.js:415-435` | 예약금 카드 — **돈은 계속 복사만**. 문구 유지·강화. |
| `erp-naver-dock.js:518-542` | `buildWidthHint` — 총폭 칩 (`data-naver-dock-copy`, 값은 쉼표 없는 mm 정수) |
| `erp-naver-dock.js:677-722` | `render()` · `syncStatus()` — `.naver-dock-hint` 는 여기가 매번 덮어쓴다 |
| `erp-naver-dock.js:795-810` | 문서 위임 클릭 — `[data-naver-dock-copy]` 분기 |
| `erp-naver-dock.css:453-472` | `.naver-dock-copy` · `:hover` · `.is-copied` |
| `erp_order_js.html:37-38` | 도크 CSS·JS 핀 (`?v=20260902a` / `?v=20260907b`) |

읽기 전용 근거 앵커:

| 자리 | 근거 |
| --- | --- |
| `erp-order-shared.js:1370-1372` | `defaultConsult` — 빈 값이면 `'상담'` |
| `erp-order-shared.js:1423-1435` | W 칸 = `[data-erp="spec_width"][data-spec-row]`, 라벨 `W(가로·총폭)`, `.erp-spec-row` 안 |
| `erp-order-shared.js:1585`·`1644` | 값 주입 뒤 `dispatchEvent(new Event('input', { bubbles: true }))` |
| `erp-order-shared.js:1191` | `row.dataset.itemIndex` 가 항목 번호(0부터) |
| `erp-order-shared.js:1242` | 모바일 아코디언 — 열린 항목은 `.erp-item-row.is-open` 하나뿐 |
| `erp-items-master-detail.js:125` | 선택 안 된 항목에 `erp-item-row--md-hidden` |
| `erp-order-autosave.js:413-417` | `#erp-order` 에서 `input`·`change` 를 **캡처**로 듣는다 |
| `erp-order-shared.js:1353·1355` | 색상/손잡이 = `data-erp="color"` / `data-erp="handle"` textarea (PC 속성 시트) |
| `erp-order-shared.js:1457·1467` | 같은 이름의 모바일 textarea |

## 해야 할 변경

### A. 순수 도우미 함수 — **반드시 최상위 `function 이름(...) { ... }` 선언으로** 쓴다

W3 의 테스트가 도크 JS 에서 함수를 통째로 뜯어 **Node 에 태워 실제로 실행**한다
(`tests/services/integrations/test_naver_dock_width_live.py:_extract_function` 방식).
그래서 다음 규칙이 계약이다:

- 화살표 함수·`var f = function` 금지. `function name(` 로 시작하는 선언만.
- 아래 함수들은 **모듈 변수(`state`, `lastItemRow` 등)를 참조하지 않는다.** 전부 인자로 받는다.
- DOM 을 만지는 함수도 인자로 받은 객체의 `querySelector`/`querySelectorAll`/`dataset`/`classList`/
  `value`/`dispatchEvent`/`focus`/`scrollIntoView` 만 쓴다(전역 `document` 참조 금지).

만들 함수(이름 고정):

1. `dockChipsOf(row)` → `[{value, target}]`.
   `row.copy_chips` 가 배열이면 그대로, 아니면 `row.copies` 문자열을 `{value: v, target: ''}` 로 감싼다(옛 응답 호환).
2. `dockFieldLabel(target)` → 계약 §4.3 의 4개 라벨. 모르는 값이면 `''`.
3. `dockIsBlankValue(value)` → `''` · 공백만 · `'상담'` 이면 `true`.
4. `dockItemLabel(itemRow)` → `'항목 2'`. `dataset.itemIndex`(없으면 `dataset.itemIdx`)를 숫자로 읽어 `+1`.
   숫자가 아니면 `'항목'`.
5. `dockPickItemRow(rows, lastRow)` → 계약 §4.1 순서. 못 고르면 `null`.
6. `dockSpecRowCount(itemRow)` → `itemRow.querySelectorAll('.erp-spec-row').length`.
7. `dockFieldFor(itemRow, target)` →
   `spec_width` 는 `itemRow.querySelector('.erp-spec-row [data-erp="spec_width"][data-spec-row]')`,
   나머지는 `itemRow.querySelector('[data-erp="' + target + '"]')`. 없으면 `null`.
8. `dockFillConfirmText(itemLabel, fieldLabel, oldValue, newValue, note)` → 계약 §4.3 조립 규칙 그대로.
9. `dockApplyValue(field, value)` → `field.value = value` → `input` → `change` 를
   `new Event(name, { bubbles: true })` 로 발사 → `scrollIntoView({block:'center',behavior:'smooth'})` →
   `focus({preventScroll:true})`. `scrollIntoView`·`focus` 가 없는 객체여도 죽지 않게 존재 확인 후 호출.
10. `dockFillFromChip(target, value, rows, lastRow, confirmFn)` → 판단 전체. 반환:
    - 성공 `{ok: true, itemLabel: '항목 2', fieldLabel: '색상'}`
    - 실패 `{ok: false, reason: '넣을 항목이 없습니다' | '넣을 칸을 못 찾았습니다' | '넣지 않았습니다'}`
    - `target` 이 빈 값이면 `{ok: false, reason: ''}` (복사만 하는 오늘 경로)
    확인창 조건은 계약 §4.3: `!dockIsBlankValue(field.value) || note` 일 때만 `confirmFn(...)` 을 부른다.
    `note` 는 규격 행이 2개 이상일 때 `'규격 행이 N개입니다 — 1행에 넣습니다.'`.

### B. 마지막으로 만진 항목 기억

IIFE 안 모듈 변수 `var lastItemRow = null;` + 문서 위임:

```js
document.addEventListener('focusin', function (event) {
    var row = event.target.closest && event.target.closest('.erp-item-row');
    if (row) lastItemRow = row;
});
```

싱글톤 가드 안(파일 하단 위임 블록 옆)에 둔다 — fragment 재실행에도 리스너가 겹치지 않아야 한다.
`erpDockItemRows()` 는 `document.querySelectorAll('#erp-items .erp-item-row')` 를 배열로 돌려주는
얇은 함수로 따로 둔다(이 함수만 `document` 를 만진다).

### C. 칩에 target 싣기

- 행 칩(`:232-240`): `(row.copies || [])` → `dockChipsOf(row)` 로 바꾸고,
  `chip.setAttribute('data-naver-dock-copy', chip값)`, target 이 있으면
  `chip.setAttribute('data-naver-dock-target', target)`.
  글자는 `(target ? '⤵ ' : '📋 ') + value`.
- 총폭 칩(`buildWidthHint`, `:527` 부근): 같은 방식으로 `data-naver-dock-target="spec_width"` 를 달고
  글자를 `'⤵ ' + hint.total_mm` 로 바꾼다. 값은 지금대로 `String(hint.total_mm)`(쉼표 없음).
- **예약금 칩(`:425` 부근)에는 target 을 달지 마라.** 돈은 사람이 넣는다.

### D. 클릭 위임 분기 (`:795-810`)

```js
var copy = event.target.closest('[data-naver-dock-copy]');
if (copy) {
    var value = copy.getAttribute('data-naver-dock-copy');
    if (navigator.clipboard) navigator.clipboard.writeText(value).catch(function () {});
    var filled = dockFillFromChip(copy.getAttribute('data-naver-dock-target') || '',
                                  value, erpDockItemRows(), lastItemRow, window.confirm);
    var original = copy.textContent;   // 반드시 글자를 바꾸기 **전에** 잡는다
    ...
}
```

- 성공: `copy.classList.add('is-filled')`, 글자 `'✓ ' + filled.itemLabel + ' ' + filled.fieldLabel + '에 넣음'`, **1600ms**.
- 실패·복사만: 오늘대로 `is-copied` · `'✓ 복사됨'` · 1200ms.
  단 `filled.reason` 이 있으면 `'✓ 복사됨 — ' + filled.reason`.
- 되돌릴 때 두 클래스를 모두 지운다.
- 클립보드 복사는 **넣기 성패와 무관하게 항상** 먼저 한다.

### E. CSS (`erp-naver-dock.css:469` 옆)

- `.naver-dock-copy.is-filled` — `.is-copied` 와 구분되는 성공색(테두리·글자).
- `.naver-dock-copy[data-naver-dock-target]` — 넣을 수 있는 칩임을 알리는 약한 표식(테두리색 정도).
- 인라인 스타일 금지. 기존 팔레트(`#059669`·`#059a54`·`#cbd5e1`) 밖으로 나가지 마라.

### F. 자산 핀 (`erp_order_js.html`)

- `js/orders/erp-naver-dock.js') }}?v=20260907b` → `?v=20260908a`
- `css/orders/erp-naver-dock.css') }}?v=20260902a` → `?v=20260908a`

이 두 줄만 고친다. **테스트의 핀 assert 는 W3 이 고친다 — 네가 tests/ 를 만지지 마라.**

### G. 주석 정정 (계약 §5)

- 헤더 `:4-6`: "값 전달은 사람이 복사 버튼으로만 한다" → 4칸 예외를 적는다.
  폼 **id·name 무참조** 원칙은 유지한다고 함께 적어라(도크는 `data-erp` 계약만 읽는다).
- `:521` `buildWidthHint`: "값을 폼에 넣지 않는다" → W 칸에 넣는다(확인창 뒤)로 고친다.
- `:429` 예약금: **유지·강화**. "돈은 여전히 사람이 넣는다"를 못박고, 화면 안내 문구
  `'시스템이 넣지 않습니다 — 예약금(선금) 칸에 직접 입력하세요...'` 는 **글자 그대로 둔다**.

## 하지 말 것

- 폼 스크립트 수정(`erp-order-shared.js`·`erp-items-master-detail.js`·`erp-order-autosave.js`·`erp-spec-calc.js`).
- `window.ErpItemsMasterDetail` 등 폼 API 호출. 도크는 DOM 계약만 읽는다.
- 자동저장·계산기 로직 직접 호출. `input`/`change` 를 쏘는 것까지가 끝이다.
- 반영 체크(`data-naver-dock-check`) 자동 켜기.
- `.naver-dock-hint` 에 안내 쓰기(`syncStatus()` 가 덮어쓴다).
- 되돌리기(undo) 기능 만들기.
- 인라인 스타일 · jQuery · 인라인 script · `innerHTML` 로 원본 문자열 주입.
- `tests/` 수정, git 명령(읽기 전용 제외).

## 완료 기준 (직접 돌려서 확인하고 보고해라)

```
cd /c/tmp/foms-s-s0908-102606 && pwd
python -m pytest tests/services/integrations/test_naver_dock.py tests/services/integrations/test_naver_dock_amounts.py tests/services/integrations/test_naver_dock_household_split.py tests/services/integrations/test_naver_dock_width_live.py tests/services/integrations/test_naver_coupon_visibility.py -q
python -c "import app; print('APP_OK')"
node --check static/js/orders/erp-naver-dock.js
```

`test_naver_dock.py` 와 `test_naver_dock_household_split.py` 의 **핀 assert 4줄·2줄은 빨갛게 나오는 것이 정상**이다
(W3 이 새 핀으로 고친다). 그 6줄 말고 다른 것이 빨개지면 네 잘못이다.

`_extract_function` 이 네 함수를 뜯을 수 있는지 스스로 확인해라:

```
cd /c/tmp/foms-s-s0908-102606 && pwd && python -c "
import sys; sys.path.insert(0,'.')
from tests.services.integrations.test_naver_dock_width_live import _extract_function
src = open('static/js/orders/erp-naver-dock.js', encoding='utf-8').read()
for name in ['dockChipsOf','dockFieldLabel','dockIsBlankValue','dockItemLabel','dockPickItemRow','dockSpecRowCount','dockFieldFor','dockFillConfirmText','dockApplyValue','dockFillFromChip']:
    print(name, len(_extract_function(src, name)))
"
```

10개 전부 길이가 찍혀야 한다(예외가 나면 선언 모양이 틀린 것이다).

## 보고에 반드시 넣을 것

- 위 확인 명령 2개의 출력 원문.
- 빨개진 테스트 전량(핀 6줄 외에 있으면 그 자체가 결함).
- 새 핀 값 2개와, 고친 주석 3곳의 새 문장 원문.
