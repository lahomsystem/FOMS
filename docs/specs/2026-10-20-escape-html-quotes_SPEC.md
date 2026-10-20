# 화면 글자 변환(escapeHtml)이 따옴표도 바꾸게 통일 — SPEC (2026-10-20)

## 목적
JS 로 HTML 조각을 만들 때 쓰는 이스케이프 함수가 파일마다 따로 있고, 그중 다수가 따옴표(`"`·`'`)를 바꾸지 않는다. 이 결과를 `title="..."`·`data-*="..."`·`value="..."` 같은 속성값 자리에 넣으면, 파일 이름·제품명·치수·주소에 따옴표가 들어간 순간 속성이 거기서 끝나고 뒤 글자가 새 속성으로 읽힌다(화면 깨짐, 심하면 의도치 않은 동작). 2026-10-19 이후 협력사 품목 입력(치수 100자·추가 입력 2000자, `foms/services/partners/orders.py`)도 직원 화면의 같은 함수로 속성값에 들어간다(`static/js/orders/erp-order-shared.js` 품목 렌더).

## 지금 구조(2026-10-20 전수)
- 정적 JS·템플릿 안 이스케이프 함수 정의 40개(`escapeHtml`·`escHtml`·`esc`·`escapeAttr` 등).
- 따옴표 둘 다 바꾸는 것 16 · 큰따옴표만 6 · 둘 다 안 바꾸는 것 18.
- 안 바꾸는 쪽은 거의 `div.textContent = x; return div.innerHTML;` 방식이다 — 이 방식은 `&`·`<`·`>` 만 바꾼다.
- 전역 `escapeHtml` 을 정의하는 곳이 여럿이라(`templates/partials/shared/layout_head.html`·`templates/partials/chat_scripts_utils.html`·`static/js/wdcalculator/shared.js` 등) 나중에 실린 쪽이 앞의 것을 덮는다. 따옴표를 바꾸는 정의가 먼저 실려도 안 바꾸는 정의가 덮으면 효과가 사라진다.
- `static/js/orders/order-detail-fragment.js` 담당자 칸은 `escapeHtml` 이 없을 때 원문을 그대로 쓰는 대체 함수를 갖고 있다.

## 변경
1. 따옴표를 안 바꾸는 정의 24곳(큰따옴표만 바꾸던 6곳 포함)의 몸통을 고쳐 `"`→`&quot;`, `'`→`&#39;` 까지 바꾼다. `textContent` 방식은 `return div.innerHTML` 뒤에 두 `replace` 를 붙이는 한 줄 변경이다.
2. `order-detail-fragment.js` 의 대체 함수도 다섯 글자(`& < > " '`)를 바꾼다.
3. 전역 덮어쓰기는 지우지 않는다 — 모든 정의가 같은 결과를 내므로 누가 덮어도 안전하고, 실리는 순서를 바꾸는 쪽이 더 위험하다.

결과가 달라지는 곳: 따옴표가 든 값을 HTML 로 넣는 화면. 브라우저가 `&quot;`·`&#39;` 를 다시 따옴표로 보여 주므로 화면 글자는 같다. 이스케이프 결과를 `value`·`textContent` 에 바로 넣는 곳은 0곳(전수 검색)이라 `&quot;` 가 글자로 보이는 일은 없다.

## 건드리지 않는 것
- 서버 Jinja 출력(자동 이스케이프가 이미 따옴표를 바꾼다), `|safe` 출력(별건).
- `?v=` 자산 캐시 핀(1일). 기기에 옛 JS 가 최대 하루 남는다.

## 테스트
새 파일 `tests/domains/test_escape_html_quotes.py`:
- 정적 JS·템플릿의 이스케이프 함수 정의를 전부 찾고(30개 이상 — 검색식이 깨져 0 이 되면 거짓 통과하므로 하한 단언), 몸통이 `&quot;` 와 `&#39;` 를 모두 쓰거나 다른 이스케이프 함수에 맡기는지 본다. 새 정의가 따옴표를 빠뜨리면 여기서 걸린다.
- 수정 전 코드에서 24곳 실패, 수정 뒤 통과.
