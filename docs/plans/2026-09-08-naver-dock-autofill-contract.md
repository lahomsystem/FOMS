# 네이버 도크 자동 입력 — 확정 계약 (CEO, 2026-09-08)

정본 요구: `docs/plans/2026-09-08-naver-dock-autofill-brief.md`.
이 문서가 **이름·모양·문구의 정본**이다. W1·W2·W3 는 여기 적힌 이름을 한 글자도 바꾸지 않는다.

## 0. 왜 이 모양인가 (결론 먼저)

- 서버는 칩마다 **어느 칸에 들어갈 값인지**만 말한다. 화면은 한국어 옵션 키를 다시 파싱하지 않는다.
- 서버 응답은 **덧붙이기(additive)** 다. 기존 `copies`(문자열 목록)를 그대로 두고 새 키 `copy_chips` 를 더한다.
- 값을 넣는 판단(어느 항목·어느 행·덮어쓸까)은 **전부 화면**에 있다. 서버는 DOM 을 모른다.

## 1. 서버 반환 모양 (고정)

`build_dock_payload` 의 행(row)마다:

```python
"copies": ["보테가 슬라이딩", "포그 그레이"],                      # 기존 그대로 (list[str])
"copy_chips": [                                                   # 신규
    {"value": "보테가 슬라이딩", "target": "product_name"},
    {"value": "포그 그레이",     "target": "color"},
],
```

- `copy_chips[i]["value"]` 는 `copies[i]` 와 **항상 같다**(길이·순서 동일). 한 파서에서 나온다.
- `target` 은 다섯 중 하나: `"product_name"` · `"color"` · `"handle"` · `"spec_width"` · `""`(모름 = 복사만).
- 추가옵션 행: `copies == [name_chip]`, `copy_chips == [{"value": name_chip, "target": ""}]`.
  이름 칩은 `… ×3` 수량 꼬리가 붙은 **구성 이름**이라 ERP 제품명이 아니다.
- 서버가 `spec_width` 를 내보내는 경로는 **없다**. 총폭 칩은 화면(`buildWidthHint`)이 만들고 거기서 target 을 단다.

### 왜 `copies` 를 안 바꾸나 (브리프 초안을 뒤집는다 — 근거)

SW 가 `staticCacheFirst` 라 배포 직후 **옛 JS + 새 payload** 조합이 반드시 생긴다
(`project_sw_stale_js_version_bump`). 옛 JS 는
`(row.copies || []).forEach(function (value) { ... '📋 ' + value })`
(`static/js/orders/erp-naver-dock.js:234`) 라, `copies` 를 dict 목록으로 바꾸면 그 창에서 칩이 전부
`📋 [object Object]` 로 뜬다. 덧붙이기면 그 창이 아예 없다.
또 서버 테스트가 `copies == [...]` 문자열을 물고 있어(`test_naver_dock.py:126·138·142·147·149·150·389·390`,
`test_naver_dock_household_split.py:186`) 덧붙이기는 **기존 테스트 0건 파손**이다.

### 옛 응답 호환 (화면 쪽)

`copy_chips` 가 없으면 화면이 `copies` 문자열을 `{value: v, target: ''}` 로 감싼다 → 오늘과 똑같은 복사 전용 화면.

## 2. 키 → 칸 매핑 상수 (서버, `dock.py`)

```python
COPY_TARGET_BY_KEY: dict[str, str] = {
    **{key: "product_name" for key in PRODUCT_NAME_KEYS},   # 제품·제품명·상품·상품명·품목
    "컬러": "color", "색상": "color", "색깔": "color", "color": "color",
    "손잡이": "handle", "핸들": "handle", "handle": "handle",
}
```

조회는 `COPY_TARGET_BY_KEY.get(key.strip().lower(), "")` — `size_option_mm` 이 이미 쓰는 정규화다(`dock.py:199`).

**운영 근거(코드에서 찾은 실제 키)**

| 키 | 근거 |
| --- | --- |
| `제품` | `dock.py:43 PRODUCT_NAME_KEYS` · 운영 샘플 `제품: 보테가 슬라이딩 30cm （풀오토댐퍼 포함）` (`test_naver_dock.py:137`) |
| `컬러` | 운영 샘플 `컬러: 포그 그레이` · `컬러: 클린 화이트` · `컬러: 화이트` (`test_naver_dock.py:137·141·219·268`) |
| `색상` | 운영 실사례 2026-09-01 주문 `2026090191203001` — `사이즈 ／ 색상: 180cm ／ 클린 화이트` (`dock.py:127-128·182-183`, `test_naver_dock.py:275-283`) |
| `손잡이` | 운영 샘플 `손잡이: 푸쉬타입` (`test_naver_dock.py:141·219·232·280`) · 사양 축 이름 (`attribution.py:28`) |
| `색깔`·`핸들`·`color`·`handle` | 오타·영문 변형 방어. 같은 파일의 선례 `SIZE_OPTION_KEYS = ("사이즈", "싸이즈", "규격", "폭", "size")` (`dock.py:120`) 와 같은 급의 값싼 보험이다. |

**`사이즈`·`규격`·`폭` 는 일부러 `""` 로 둔다.** 그 값(`150`·`180cm`)은 고객이 고른 **모듈 폭**이지
ERP 의 총폭이 아니다. 실제 총폭은 `모듈 × 수량 + 길이추가` 다 — 실사례 30cm×12 + 1cm×12 = **3,720mm**
(`test_naver_dock.py:187-195`). `150` 을 W 칸에 넣으면 1,500mm 라 2,220mm 를 잃는다.
W 칸을 채울 자격은 총폭 칩(`buildWidthHint`, 이미 mm 정수) 하나뿐이다.

## 3. 옵션 원문 파싱 — 전각 짝 처리 (신규, 의도된 동작 변경)

한 `/` 그룹 안에서 키와 값이 **전각 `／` 로 자리 짝짓기**된 실사례가 있다:
`사이즈 ／ 색상: 180cm ／ 클린 화이트`.

- 지금: 칩 1개 `180cm ／ 클린 화이트` (키가 `사이즈 ／ 색상` 이라 어느 칸도 못 고른다)
- 앞으로: 키 조각 수 == 값 조각 수 일 때만 **자리로 짝지어** 칩 2개 —
  `180cm`(target `""`) · `클린 화이트`(target `color`)
- 짝이 안 맞으면(`색상 ／ 사이즈: 클린 화이트`) 오늘 그대로 칩 1개, target `""`.
  근거: `size_option_mm` 이 이미 같은 규칙을 쓴다 — "짝이 모자라면 그 값은 쓰지 않는다"(`dock.py:183-186`).

이 모양을 무는 기존 테스트는 없다(`copies` 를 무는 테스트는 전부 반각 그룹 형태). W3 가 두 갈래를 새로 못박는다.

## 4. 화면 계약 (`erp-naver-dock.js`)

칩 DOM: `data-naver-dock-copy="<값>"`(기존) + `data-naver-dock-target="<target>"`(신규).
target 이 빈 값이면 **속성을 달지 않는다**.
칩 글자: target 이 있으면 `⤵ 값`, 없으면 오늘대로 `📋 값`.

### 4.1 어느 항목에 넣나 (정할 것 ①)

`dockPickItemRow(rows, lastRow)` 순서:

1. **마지막으로 사람이 만진 항목** — `focusin` 위임으로 기록한 `.erp-item-row`.
   **아직 목록에 있고 + 숨겨지지 않았을 때만**(`erp-item-row--md-hidden` 이 붙어 있으면 버리고 2번으로 내려간다).
   레일 항목은 `role=option` 인 div 라 클릭해도 포커스가 안 옮겨 간다(`erp-items-master-detail.js` `selectItem` 에 `focus()` 없음) —
   "항목 1 색상 칸에 타이핑 → 레일에서 항목 3 선택" 뒤 마지막 포커스는 `display:none` 인 항목 1 에 남아 있다
   (`erp-items-master-detail.css` 의 `erp-item-row--md-hidden`). 가시성을 안 보면 값이 **화면에 안 보이는 항목**에 들어간다.
2. 없으면 **지금 보이는 항목** — 마스터-디테일에서 선택 안 된 행에는 `erp-item-row--md-hidden` 이 붙는다
   (`erp-items-master-detail.js:125`). 즉 "안 숨겨진 행"이 곧 선택된 행이다.
3. 그중 **펼쳐진 항목**(`.is-open`) 우선 — 모바일 아코디언은 한 번에 하나만 펼친다(`erp-order-shared.js:1242`).
4. 그래도 못 고르면 **첫 항목**.
5. 항목이 하나도 없으면 넣지 않는다 → 복사만 하고 칩이 `✓ 복사됨 — 넣을 항목이 없습니다`.

근거: 이 세 축(`erp-item-row--md-hidden` · `.is-open` · 포커스)이 "지금 사람이 보고 있는 항목"의 화면상 정본이다.
`window.ErpItemsMasterDetail` API 는 부르지 않는다 — 도크는 폼 스크립트에 의존하지 않는 additive 부품이다.

### 4.2 규격 행이 여럿일 때 (정할 것 ②)

**첫 `.erp-spec-row` 의 W 칸**에 넣는다.
근거: 화면 요약(`erp-order-shared.js:1221`), 마스터-디테일 레일(`erp-items-master-detail.js:40`),
규격 계산기(`erp-spec-calc.js:142`) — 셋 다 이미 **첫 규격 행**을 그 항목의 대표 W 로 읽는다.
네 번째 정의를 만들지 않는다.

다만 **규격 행이 2개 이상이면 칸이 비어 있어도 확인창을 띄운다.** 어느 행에 넣을지가 사람의 판단이기 때문이다.

셀렉터: `.erp-spec-row [data-erp="spec_width"][data-spec-row]` 의 첫 번째.

### 4.3 덮어쓰기 규칙과 확인창 문구 (정할 것 ③)

**빈 칸 판정 `dockIsBlankValue(v)`**: `''` · 공백만 · **`'상담'`**.
`'상담'` 을 빈 값으로 세지 않으면 색상·손잡이는 **언제나** 확인창이 뜬다 —
신규 항목의 색상·손잡이·내부·옵션·기타는 기본값이 `'상담'` 이다
(`erp-order-shared.js:1370-1372 defaultConsult`, `1443-1450`).

- 빈 칸(위 판정) + 규격 행 1개 → **바로 넣는다**(확인창 없음).
- 값이 있음, 또는 규격 행 2개 이상 → **확인창 1회**.

문구 정본 `dockFillConfirmText(itemLabel, fieldLabel, oldValue, newValue, note)`:

```
항목 2 · 색상
지금 값: 포그 그레이
넣을 값: 클린 화이트

덮어쓸까요? (취소하면 그대로 둡니다)
```

규격 여러 행:

```
항목 1 · W(가로·총폭)
지금 값: (비어 있음)
넣을 값: 3720
규격 행이 3개입니다 — 1행에 넣습니다.

여기에 넣을까요? (취소하면 그대로 둡니다)
```

조립 규칙(정확히 이대로, `\n` 으로 잇는다):

1. `itemLabel + ' · ' + fieldLabel`
2. `'지금 값: ' + (값이 있으면 그 값, 없으면 '(비어 있음)')`
3. `'넣을 값: ' + newValue`
4. `note` (있을 때만)
5. `''`
6. 지금 값이 비어 있으면 `'여기에 넣을까요? (취소하면 그대로 둡니다)'`,
   아니면 `'덮어쓸까요? (취소하면 그대로 둡니다)'`

칸 이름 `dockFieldLabel(target)` — **화면 라벨과 같은 글자**를 쓴다:
`spec_width` → `W(가로·총폭)`(`erp-order-shared.js:1435`), `product_name` → `제품명`,
`color` → `색상`, `handle` → `손잡이`.

**되돌리기(undo)는 만들지 않는다.** 근거: (a) 파괴적인 경우는 확인창이 이미 막는다,
(b) 도크는 귀속이 바뀔 때마다 통째로 다시 그려서(`render()`) 되돌리기 버튼의 수명을 지킬 자리가 없다,
(c) 자동저장이 로컬 미러 + 서버 draft 로 이미 복원 경로를 갖는다.
**수용하는 위험**: `field.value = ...` 대입은 브라우저 네이티브 undo 스택을 지운다 — 그 칸에서 Ctrl+Z 로는 못 되돌린다.
확인창이 지금 값을 글자로 보여 주는 것이 그 대가다.

### 4.4 넣은 뒤 (사람에게 어디에 넣었는지 말하기)

1. `field.value = value`
2. `input` → `change` 순서로 `new Event(name, { bubbles: true })` 발사.
   근거: 자동저장이 `#erp-order` 에서 `input`·`change` 를 캡처로 듣는다(`erp-order-autosave.js:416-417`),
   폼도 같은 방식으로 쏜다(`erp-order-shared.js:1585`·`1644`).
3. `field.scrollIntoView({ block: 'center', behavior: 'smooth' })` → `field.focus({ preventScroll: true })`
4. 칩 글자를 **1.6초** 동안 `✓ 항목 2 색상에 넣음` 으로 바꾸고 `is-filled` 클래스를 단다.
   (복사만 한 칩은 오늘 그대로 `✓ 복사됨` · 1.2초 · `is-copied`.)
5. **클립보드 복사는 넣기와 무관하게 항상 한다** — 다른 칸에 또 붙일 수 있어야 한다.

`.naver-dock-hint`(바닥 안내)는 쓰지 않는다 — `syncStatus()` 가 매번 덮어쓴다(`erp-naver-dock.js:700`).

### 4.5 반영 체크 (정할 것 ④)

**자동으로 켜지 않는다.** `checked` 는 체크 즉시 서버에 저장되는 **팀 공유 상태**이고
(`erp-naver-dock.js:5-6`, `dock.py` 행 조립의 `state.get("checked")`), 완료 버튼의 게이트다.
그 뜻은 "사람이 확인했다" 이지 "값이 이동했다"가 아니다. 스크립트가 켜면 동료가 사람의 확인으로 읽는다.

## 5. 뒤집는 결정 (주석·docstring 정정 — 빠뜨리면 다음 사람이 되돌린다)

| 자리 | 지금 | 어떻게 |
| --- | --- | --- |
| `dock.py:3-6` 모듈 docstring "값 전달은 사람이 복사 버튼으로만 한다" | 전면 금지 | 4칸(제품명·색상·손잡이·총폭)은 사람이 **칩을 눌러** 넣는다. 그 밖(돈·발송기한)은 여전히 복사만. |
| `dock.py:84` "(자동 기입 금지 — 스펙 확정 결정 3)" | 전면 금지 | 이 결정이 2026-09-08 에 4칸에 한해 뒤집혔음을 적는다. |
| `dock.py:264` `build_width_hint` "자동 기입은 하지 않는다(규격 SSOT 보호)" | 전면 금지 | 총폭은 이제 확인창 뒤에 W 칸에 넣는다. 계산 정본은 그대로. |
| `erp-naver-dock.js:4-6` 헤더 "값 전달은 사람이 복사 버튼으로만 한다" | 전면 금지 | 4칸 예외를 적는다. 폼 **id·name** 무참조 원칙은 유지(`data-erp` 계약만 읽는다). |
| `erp-naver-dock.js:429` 예약금 카드 "자동 기입은 하지 않는다(폼 불가침 계약)" | 유지·강화 | **돈은 여전히 사람이 넣는다**로 못박는다. 화면 문구도 그대로 둔다. |
| `erp-naver-dock.js:521` `buildWidthHint` "값을 폼에 넣지 않는다" | 전면 금지 | W 칸에 넣는다로 고친다. |

## 6. 자산 핀 (고정값)

`templates/orders/partials/erp_order_js.html`:

- `js/orders/erp-naver-dock.js') }}?v=20260907b` → **`?v=20260908a`**
- `css/orders/erp-naver-dock.css') }}?v=20260902a` → **`?v=20260908a`**

이 핀을 무는 기존 assert 6줄(W3 가 고친다):
`tests/services/integrations/test_naver_dock.py:790·791·972·973`,
`tests/services/integrations/test_naver_dock_household_split.py:317·318`.

## 7. 파일 소유권 (겹치지 않는다)

- **W1**: `foms/services/integrations/naver_commerce/dock.py`
- **W2**: `static/js/orders/erp-naver-dock.js` · `static/css/orders/erp-naver-dock.css` · `templates/orders/partials/erp_order_js.html`
- **W3**: 신규 `tests/services/integrations/test_naver_dock_autofill_map.py` · 신규
  `tests/services/integrations/test_naver_dock_autofill_wire.py` + 위 6줄 핀 수정

## 8. 공통 완료 기준

```
cd /c/tmp/foms-s-s0908-102606 && pwd
python -m pytest tests/services/integrations -q
python -m pytest tests/domains -q
python -c "import app; print('APP_OK')"
```

## 9. 같은 날 후속 2건 (담당자 지시 — 2026-09-08 오후)

### 9.1 사이즈 옵션 값이 제품명 칸으로 간다

담당자 화면에는 `제품` 키가 없고 `사이즈: 150（무몰딩）` 만 있는 상품이 있다. 그 화면에서
담당자가 제품명 칸에 적는 글자가 그 값이라, 칩이 복사 전용이면 매번 손으로 옮겨 적는다.

- `COPY_TARGET_BY_KEY` 에 `SIZE_OPTION_KEYS`(사이즈·싸이즈·규격·폭·size) → `product_name` 을 더한다.
- **W 칸 자격은 여전히 없다.** 그 값은 모듈 폭이라 총폭이 아니다(§2 의 3,720mm 사고 그대로).
- 값은 `main_product_name` 으로 깎지 않는다 — 깎으면 `150（무몰딩）` 이 `150` 이 된다.
- `제품` 키가 함께 있으면 그 칩이 먼저 나오고, 일괄 입력은 먼저 나온 칩을 쓴다.

### 9.2 머리줄 `⤵ 전부 넣기` — 네 칸을 한 번에

- 자리: 도크 머리줄(`.naver-dock-hd`), 진행 표시 앞. 넓은 셸·좁은 셸 둘 다.
- 계획은 **지금 그려진 칩**에서 만든다(`[data-naver-dock-target]` DOM 질의) — 칸마다 먼저
  나온 칩 하나. 복사 전용 칩(예약금 등 돈)은 칸 이름이 없으므로 절대 실리지 않는다.
- 항목 고르기는 칩 하나 경로와 **같은 함수**(`dockPickItemRow`).
- 확인창은 **한 번**. 값이 있는 칸(과 규격 행이 여럿인 W 칸)을 한 목록으로 보여 준다.
  취소 = 덮어쓰지 않는다, 다만 **빈 칸은 채운다**(잃을 값이 없다).
- 본품이 둘 이상이면 버튼을 잠근다 — "먼저 나온 칩" 이 곧 "첫째 집" 이라 두 번째 집을
  편집 중인 사람에게는 틀린 값이다.
- 스크롤·포커스는 **첫 칸 하나**만(`dockApplyValue(field, value, quiet)`).

### 9.3 자산 핀

`?v=20260908a` → `?v=20260908b` (CSS·JS 두 줄 함께). 이 핀을 무는 assert 6줄도 같이 옮긴다.

### 9.4 계약 테스트

`tests/services/integrations/test_naver_dock_fill_all.py`(12건) · `..._autofill_map.py` 갱신.
