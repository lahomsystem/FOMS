# 네이버 도크 자동 입력 (2026-09-08)

작업 트리: `c:\tmp\foms-s-s0908-102606` (브랜치 `session/s0908-102606`, base `origin/deploy`).
bash cwd 는 호출 사이에 리셋된다 — 모든 명령을 `cd /c/tmp/foms-s-s0908-102606 && pwd && ...` 로 시작한다.

## 담당자 요구 (2026-09-08)

주문 편집 화면(`/edit/5198?open=erp-order`)의 네이버 원본 도크에서, 복사 칩을 누르면 **해당 ERP 입력 칸에 바로 들어가야** 한다.
지금은 클립보드 복사만 되고 사람이 칸을 찾아 붙여 넣는다.

담당자가 지목한 짝 4개:

| 도크 칩 | 들어갈 칸 |
| --- | --- |
| 총폭 `3400` | `input[data-erp="spec_width"]` |
| 제품 `리라 TV 월플렉스` | `input[data-erp="product_name"]` |
| 컬러 `클린 화이트` | `textarea[data-erp="color"]` |
| 손잡이 (그 탭의 손잡이 값) | `textarea[data-erp="handle"]` |

## 이 작업이 뒤집는 결정 (알고 하는 것)

지금 코드에는 **자동 기입 금지**가 명시적 설계 결정으로 박혀 있다:

- `foms/services/integrations/naver_commerce/dock.py:84` docstring — `자동 기입 금지 — 스펙 확정 결정 3`
- `static/js/orders/erp-naver-dock.js:521` — `규격 SSOT 를 지키기 위해 값을 폼에 넣지 않는다. 계산식과 복사 버튼까지다.`
- 같은 파일 429 — `자동 기입은 하지 않는다(폼 불가침 계약)`

담당자가 이번에 **위 4칸에 한해** 그 결정을 바꾼다. 그래서:
- 4칸 밖(예약금·금액·발송기한 등 돈 칸)은 **여전히 복사만** 한다. 돈은 사람이 넣는다.
- 코드 주석·docstring 의 "자동 기입 금지" 문장을 이번 범위에 맞게 **정확히** 고친다.
  (금지가 남아 있으면 다음 사람이 이 기능을 버그로 읽고 되돌린다.)

## 계약 초안 (이름 고정 — CEO 가 확정한다)

서버가 칩마다 **어느 칸에 들어갈 값인지** 말한다. 화면이 한국어 키를 다시 파싱하지 않는다.

- `dock.py` 의 칩 값 목록(`split_option_copies`, `copies`)을 `{"value", "target"}` 목록으로 바꾼다.
  `target` 은 `spec_width` · `product_name` · `color` · `handle` · `""`(모름 = 복사만).
- 키→칸 매핑 상수 한 벌(`COPY_TARGET_BY_KEY`)을 서버에 둔다. 옵션 키 실사례: `제품`·`컬러`·`색상`·`손잡이`·`사이즈`.
  총폭 칩(`buildWidthHint`)은 키가 없으므로 `spec_width` 로 고정한다.
- 옛 응답(`copies` 가 문자열 목록)도 화면이 죽지 않게 받는다.

화면(`erp-naver-dock.js`):
- 칩에 `data-naver-dock-target` 을 싣는다. 있으면 **넣기**, 없으면 지금처럼 복사.
- 넣을 때: 칸이 비어 있으면 바로 넣는다. 값이 있으면 **확인창 1회**(무엇을 무엇으로 바꾸는지 재진술) 후 덮어쓴다.
- 넣은 뒤 `input`·`change` 이벤트를 버블로 쏜다 — ERP 자동저장·계산기 트리거가 그것을 듣는다
  (`static/js/orders/erp-order-shared.js:1585`·`1644` 가 같은 방식).
- 넣은 칸으로 스크롤·포커스하고, 칩은 1.2초간 `✓ 넣음` 으로 바뀐다(지금 `✓ 복사됨` 과 같은 자리).
- 클립보드 복사도 **함께** 한다 — 다른 칸에 또 붙일 수 있다.

## 정해야 할 것 (CEO 가 근거를 대고 정한다)

1. **여러 항목(item) 중 어디에 넣나.** ERP 는 항목이 여러 개다(`data-item-idx`, `templates/macros/foms_product_item.html`).
   권고: 마지막으로 사람이 만졌던 항목, 없으면 첫 항목. 어느 항목에 넣었는지 화면이 말해야 한다.
2. **`data-spec-row`** 가 붙은 규격 행이 여럿일 때 총폭을 어느 행에 넣나.
3. 확인창 문구(덮어쓰기). 짧게 — 오늘 문구 규칙(`docs/plans/2026-09-08-naver-tab-copy-plan.md`)을 따른다.
4. 도크의 `0 / 4 반영` 체크를 자동으로 켤지. 권고: **켜지 않는다** — 반영 체크는 사람이 확인했다는 뜻이다.

## 경계

- 판정 축·저장 경로·자동저장 로직은 건드리지 않는다. 값을 칸에 넣고 이벤트를 쏘는 것까지다.
- 인라인 스타일 금지, jQuery 금지, `querySelector`/`fetch` 만.
- JS 를 고치면 `templates/orders/partials/erp_order_js.html` 의 `erp-naver-dock.js` 핀을 함께 올린다
  (SW staticCacheFirst 가 옛 파일을 준다). 그 핀을 세는 계약 테스트가 있으면 함께 고친다.
- 새 테스트는 실제 렌더·동작을 문다. 소스 문자열만 훑는 테스트는 만들지 않는다.

## 검증 (완료 기준)

```
cd /c/tmp/foms-s-s0908-102606 && pwd
python -m pytest tests/services/integrations -q
python -m pytest tests/domains -q
python -c "import app; print('APP_OK')"
```
