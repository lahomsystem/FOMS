# T2 — 문자열로 남은 옛 잔금이 0 클램프를 빠져나간다 (CEO L-2)

작업 트리: `c:\tmp\nvfix` (여기서만 편집한다)

## 배경

잔금은 어느 표면에서나 **0 에서 자른다**(`max(0, …)`). 음수 잔금을 화면에 내면 안 되기 때문이다
(정본: `foms/services/orders/structured_form_projection.py` `recompute_totals`).

오늘 같은 파일에 과입금 표식도 붙였다 — `_overpaid_after_payments`
(`foms/services/estimate_service.py`). 넘친 금액은 따로 낸다. 먼저 읽어라.

## 고칠 것

`foms/services/erp_mobile_order_display.py` 의 `mobile_amount_summary` 안 `_fmt_balance`:

```python
def _fmt_balance(value) -> str | None:
    """잔금 라벨: 숫자로 읽히면 0 에서 클램프해 포맷한다(음수 잔금 표기 차단)."""
    if value in (None, ""):
        return None
    try:
        return f"{max(0, int(float(value))):,}원"
    except (TypeError, ValueError):
        return str(value)          # ← 여기
```

**문제**: 숫자로 안 읽히는 옛 값(예: `"-1,229,000"`, `"1,229,000원"`, `"-1229000 "`)은
`str(value)` 로 **원문 그대로** 나간다. 즉 클램프를 통째로 빠져나가 화면에 **음수 잔금**이 뜬다.
legacy 주문의 `pricing.balance` · `totals.balance` 가 문자열로 남아 있는 경로다
(`legacy_balance` 로 흘러 들어온다).

**고치는 방향**:
1. 이 저장소에는 이미 원화 문자열을 정수로 읽는 정본 헬퍼가 있다 —
   `foms/services/erp_display.py` 의 `_erp_coerce_item_price_krw`. **먼저 그걸 읽어라.**
   같은 규칙을 두 벌로 만들지 않는다(같은 값을 두 화면이 다르게 읽으면 안 된다).
   그 헬퍼가 이 자리에 맞으면 재사용하고, 안 맞으면 **왜 안 맞는지**를 보고에 적고 최소한으로 만들어라.
2. 콤마·원·공백·부호가 붙은 문자열은 숫자로 읽어 클램프한다.
3. **정말로 못 읽는 값은 지어내지 않는다.** 0 원이라고 말하면 화면이 거짓말을 한다 —
   그때 무엇을 낼지(원문 유지 / `-` / None) 는 네가 정하고 **근거를 보고에 써라**.
   다만 **음수가 그대로 찍히는 일만은 없어야 한다**(이 task 의 존재 이유다).
4. 과입금 축과 어긋나지 않게 하라 — 잔금이 0 으로 잘렸는데 넘친 금액을 아무도 말하지 않으면
   오늘 고친 L-1 이 이 경로에서만 되살아난다.

## 하지 말 것

- `_balance_after_payments` · `_overpaid_after_payments` 규칙 변경 금지(오늘 승격됐다).
- 다른 표면(완료 대시보드·이력 시트) 편집 금지 — 그 둘은 저장 totals 를 안 쓰고 매번 재파생한다.
- 커밋·푸시 금지.

## 완료 기준 (이걸로 판정한다)

```bash
cd /c/tmp/nvfix
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_erp_mobile_order_display.py -q
```

- 전량 통과
- **신규 단언 3건 이상**:
  ① 문자열 음수 잔금(`"-1,229,000"`)이 **화면에 음수로 안 나온다**
  ② 콤마·`원` 이 붙은 정상 문자열은 **값을 잃지 않는다**
  ③ 정말 못 읽는 값(`"미정"` 같은)에서 **없는 숫자를 지어내지 않는다**
- 기존 단언(`test_mobile_amount_summary_clamps_legacy_negative_balance` 등)은 그대로 통과해야 한다
- 테스트 docstring 은 한국어로, **왜** 필요한지 적어라(옆 테스트들을 보라)

## 보고 형식

변경 파일 · 바꾼 것 요약 · 재사용했는지/새로 만들었는지와 그 근거 ·
"못 읽는 값" 에서 무엇을 내기로 했는지와 근거 · 위 명령의 실제 출력 마지막 줄.
