# ERP 도크가 **취소 확정된 집**을 '이번 주문(재결제)' 로 잡는다 — 워커 브리프 (초안, CEO 가 고쳐도 된다)

> 2026-09-16 사용자 제보(긴급): "김선미 09-07 은 이미 취소 완료인데 도크가 그걸 이번 주문(재결제)으로
> 잡아서 재결제 금액이 왜곡된다. 사용자가 혼동할 수 있는 큰 문제니 빨리 해결해."

## 1. 사실 (운영 실측 2026-09-16, 주문 #5158 김선미)

`external_order_links` 를 집(`external_order_no`) 단위로 센 값이다.

| 집 주문번호 | 관계 | 상품주문 | 클레임 | 결제액 |
|---|---|---:|---|---:|
| 2026090498433601 (09-04 수집) | `NEW` | 9 | **전부 `CANCEL_DONE`** (09-07 취소 완료 · 주문 실수) | 1,932,800원 |
| 2026090764605051 (09-07 수집) | `REPAY` | 5 | **전부 `CANCEL_DONE`** (09-14 취소 완료 · 단순 변심) | 1,134,200원 |
| 2026091643473411 (09-16 수집) | `REPAY` | 3 | 없음 — **살아 있는 유일한 결제** | 1,034,800원 |

화면(ERP 주문 편집 옆 네이버 도크)이 지금 말하는 것:

```html
<div class="naver-dock-grp">본품 3 — 라홈 로라 무몰딩 붙박이장 작은방 여닫이 푸쉬타입 240cm
  <span class="naver-dock-hh" title="네이버 주문번호 2026090764605051">이번 주문(재결제) …5051</span>
  <span class="naver-dock-grp-sub"><span class="naver-dock-grp-amt">본품+옵션 1,134,200원</span></span>
</div>
```

`…5051` 은 **09-14 에 취소 완료된 집**이다. 그런데 `이번 주문(재결제)` 라 부르고 금액 1,134,200원을
재결제 금액으로 보여준다. 살아 있는 결제는 1,034,800원(…3411)이다.

담당자가 이 화면만 보면 **고객에게 청구할 금액을 10만원 틀리게 읽는다.** 그게 이 건이 급한 이유다.

## 2. 원인 (코드 한 줄)

`foms/services/integrations/naver_commerce/dock.py:585` — `_household_facts`

```python
superseded = has_repay and relation == "NEW"
```

죽은 집 판정이 **관계(`relation`) 한 축뿐**이다. "재결제가 있으면 `NEW` 집이 대체됐다"만 안다.

그래서 재결제가 **두 번** 일어난 주문(첫 재결제도 취소되고 다시 재결제)에서:

* `NEW` 집(09-04)만 `superseded=True`
* `REPAY` 집 **둘 다** 살아 있는 것으로 보고 둘 다 `_household_label` 이 `"이번 주문(재결제)"` 를 준다
  (`dock.py:609` — `relation == "REPAY"` 면 무조건 그 라벨)
* 화면은 앞선 집(…5051)을 먼저 그려 그것이 '이번 주문' 으로 읽힌다

금액도 같은 축을 탄다 — `_deposit_target`(`dock.py:649`)은 `not superseded` 인 집을 전부 더하므로
**1,134,200 + 1,034,800 = 2,169,000원** 을 살아 있는 결제로 센다. `_deposit_relation_label`
(`dock.py:663`)도 같은 목록을 본다.

**클레임(취소·반품 확정)은 이 판정에 한 글자도 들어가지 않는다.** 그게 결함의 전부다.

## 3. 계약 초안 (이름 고정 — 워커가 바꾸지 않는다)

### 3.1 집 단위 '정산 끝' 판정 (`dock.py`)

`_row_source`(`dock.py:376`)가 이미 링크마다 `claim_phase`·`claim_kind`·`claim_money_back` 를 뽑는다.
집 단위 판정은 **그 값들의 집계**로 한다 — 새 술어를 만들지 않는다.

```python
def _household_settled(rows: list[dict[str, Any]]) -> bool:
    """이 집의 결제가 **전부 환불 확정**인가 — 죽은 집 판정의 돈 축.

    링크가 하나도 없으면 False(모르면 살아 있는 것으로 읽는다 — 죽었다고 잘못 말하면
    화면이 살아 있는 청구를 지운다).
    """
```

판정 규칙: 그 집의 모든 행이 `claim_money_back` 이고 `claim_phase == "done"` 일 때만 True.
**확정 전(`requested`·`in_progress`)은 죽은 집이 아니다** — 거부될 수 있다(유령 띠와 같은 규율).

### 3.2 `_household_facts` — 죽은 집 축을 둘로

```python
settled = _household_settled(rows_of_that_household)
superseded = settled or (has_repay and relation == "NEW")
```

`facts` 항목에 `"settled": settled` 를 함께 싣는다(화면이 사유를 갈라 말할 수 있게).

**라벨**(`_household_label`)에 `settled` 를 넘긴다:

| 집 상태 | 라벨 | 비고(note) |
|---|---|---|
| `settled` 인 `REPAY` 집 | `"취소된 결제"` | `"취소·반품이 확정된 결제입니다 — 환불 완료"` |
| `settled` 인 `NEW` 집 | `"취소된 결제"` | 같음 |
| 살아 있는 `REPAY` 집 | `"이번 주문(재결제)"` | 종전 |
| 재결제로 대체된 `NEW` 집(취소 아님) | `"이전 주문"` | 종전 `_SUPERSEDED_NOTE` |
| `ADDON` | `"추가결제분"` | 종전 |

**기존 `_SUPERSEDED_NOTE`("재결제로 대체된 이전 주문 — 옛 결제는 환불됐습니다")를 취소 집에 쓰지 않는다.**
그 집은 대체된 게 아니라 취소된 것이고, 두 사실은 담당자에게 다른 행동을 부른다.

### 3.3 살아 있는 재결제가 둘 이상이면

정상 데이터에서는 없어야 하지만 생길 수 있다(붙이기 실수 등). 그때는 **수집 순서가 가장 늦은 집
하나만** `"이번 주문(재결제)"` 이고 나머지 살아 있는 `REPAY` 집은 `"재결제분"` 으로 부른다.
금액 카드는 종전대로 살아 있는 집 전부를 더한다(그게 실제로 받은 돈이다).

### 3.4 금액 카드

`_deposit_target`·`_deposit_relation_label` 은 **고치지 않는다** — 둘 다 `not superseded` 를 읽으므로
§3.2 가 바뀌면 자동으로 1,034,800원·`재결제` 로 떨어진다. **그게 이 설계의 요점이다**(판정 한 곳,
소비처 여럿).

### 3.5 화면 (`static/js/orders/erp-naver-dock.js`)

집 표식 조각(`:121` 근처)이 서버 라벨을 그대로 쓴다. 새 라벨·note 가 그대로 흐르는지 확인하고,
취소된 집은 **금액을 흐리게**(기존 죽은 집 표시 규칙 재사용, 새 색 만들지 말 것) 낸다.
자산 핀은 `erp-naver-dock.js` 의 `?v=` 를 올린다 — `grep -rn "erp-naver-dock.js?v=" templates/ tests/` 가
소유권 표의 근거다.

## 4. 파일 소유권 (겹치면 안 된다)

| 워커 | 편집 허용 파일 |
|---|---|
| **W1 판정** | `foms/services/integrations/naver_commerce/dock.py` |
| **W2 화면** | `static/js/orders/erp-naver-dock.js`, 그 핀을 든 템플릿(위 grep 결과) |
| **W3 테스트** | `tests/services/integrations/test_naver_dock*.py` 와 신규 테스트 파일, 핀 리터럴을 든 테스트 |

## 5. 반드시 잠글 계약 (W3)

1. **재현 테스트**: NEW(전부 취소) + REPAY(전부 취소) + REPAY(살아 있음) 세 집 → 살아 있는 집만
   `"이번 주문(재결제)"`, 금액 카드 합계 = 살아 있는 집 금액 하나, 취소된 두 집은 `"취소된 결제"`.
2. **음성 대조군 ①**: 취소가 하나도 없는 NEW+REPAY 두 집 → 종전 그대로(`이전 주문` / `이번 주문(재결제)`).
3. **음성 대조군 ②**: 확정 전 취소 요청(`CANCEL_REQUEST`)만 있는 집 → **죽은 집이 아니다**.
4. **음성 대조군 ③**: 추가결제(`ADDON`) 집 → 라벨·금액 종전 그대로.
5. 집이 하나뿐인 보통 주문 → 라벨 없음(종전).

## 6. 검증 명령

```bash
python -m pytest -q tests/services/integrations -k "dock"
python -m pytest -q tests/services/integrations tests/domains tests/contracts tests/harness
python -c "import app; print('APP_OK')"
node --check static/js/orders/erp-naver-dock.js
```

## 7. 함정

1. **금액을 두 번 고치지 마라** — `_deposit_target` 을 손대면 판정이 두 벌이 된다(§3.4).
2. 확정 전 클레임을 죽은 집으로 세지 않는다(음성 대조군 ②) — 거부되면 살아 있는 청구를 지운다.
3. 새 broad `except` 금지(`foms_failopen_inventory.json` 드리프트로 red).
4. 인라인 스타일 금지 · jQuery 금지 · CRLF 보존 · 한자 금지.
5. 워커는 git 명령을 쓰지 않는다(커밋·푸시는 총괄 몫).
6. 새 `.py` 는 500줄 미만(`tests/harness/test_file_size_ratchet.py`).
7. `dock.py` 는 이미 1,111줄이다 — 기존 파일이 커지는 것은 허용이지만, 새 헬퍼를 넣을 때
   기존 함수 자리(§3.1 은 `_household_facts` 바로 위)를 지켜 읽는 순서를 깨지 않는다.

## 8. 자산 핀 실측 (2026-09-16)

현재 핀은 `?v=20260910a`, 새 핀은 `?v=20260916a`. 든 곳은 네 군데다.

| 파일 | 소유 |
|---|---|
| `templates/orders/partials/erp_order_js.html:36` | W2 |
| `tests/services/integrations/test_naver_dock.py:790` | W3 |
| `tests/services/integrations/test_naver_dock.py:973` | W3 |
| `tests/services/integrations/test_naver_dock_household_split.py:318` | W3 |

`grep -rn "erp-naver-dock.js') }}?v=" templates/ tests/` 결과가 곧 이 표다 — 하나라도 빠지면 red 다.
