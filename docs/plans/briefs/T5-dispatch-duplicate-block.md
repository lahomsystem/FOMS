# T5 — 네이버에 이미 발송이 찍힌 집의 발송처리 버튼을 잠근다

작업 트리: `c:\tmp\nvfix`. 사용자 지시: **"막아줘 — 버튼 잠그고 이유 표시"**.

## 확인된 사실 (조사 완료 — 다시 조사하지 마라)

발송처리 판정은 **우리 표식만** 본다. 네이버가 이미 발송을 말하고 있어도 아무도 안 본다.

- `templates/admin/partials/naver_workbench_pane.html:75`
  `{% set can_dispatch = not locked and not dispatched and (not place_pending or close_now) %}`
  → `selected.dispatch.naver_at` 을 참조하지 않는다.
- `templates/admin/partials/naver_workbench_pane.html:51`
  `{% set dispatched = grp.dispatched if grp else selected.fulfillment.dispatched_at %}` (우리 마커만)
- `foms/services/integrations/naver_commerce/fulfillment.py:544`
  `todo = [row for row in links if not _state(row).get("dispatched_at")]` (우리 마커만)
  → `todo` 가 비지 않으면 `client.dispatch_product_orders(payload)` 가 **실제로 나간다**.
- `foms/services/integrations/naver_commerce/fulfillment.py:10-11` docstring:
  "네이버의 400(이미 처리됨)을 정상 흐름으로 삼지 않는다" — 설계자가 네이버 거절을
  안전망으로 기대하지 않았다는 명시적 진술이다.

즉 판매자센터에서 이미 나간 집에 버튼이 열리고, 누르면 **되돌릴 수 없는 두 번째 호출**이 간다.
발송처리는 구매자에게 '배송 시작' 으로 보이고 구매확정·정산 시계가 돈다.

## 만들 것 — 방어선 2겹

**① 화면 (버튼 잠금 + 이유)**
`_dispatch_view` 가 이미 만들어 두는 `selected.dispatch.naver_at` 을 `can_dispatch` 판정에 넣는다
(`foms/web/admin/naver_ingest.py:499-546` — **새 조회·새 API 호출 0**. 이미 계산된 값이다).
잠근 이유를 `title` 로 단다. 문구는 사람을 **맞는 곳으로** 보내야 한다 — 예:
`네이버에 이미 발송 기록이 있습니다(2026-08-25 14:03) — 판매자센터에서 확인하세요`.
기존 잠금 사유(`locked` · `dispatched` · `place_pending`)와 **어느 것이 이겼는지**가 갈리게 써라.

**주의**: 집(household) 단위 판정과 링크 단위 판정이 섞여 있다. `dispatch` 는 pane 이 연 링크
1건의 값이고 버튼은 집 전체에 나간다 — 이 차이를 어떻게 다룰지 판단하고 **근거를 보고에 써라**
(형제 중 하나만 네이버 발송이 찍힌 경우 어떻게 할지가 이 task 의 진짜 판단이다).

**② 서버 (같은 신호로 한 겹 더)**
`dispatch_order` 의 `todo` 필터에 같은 신호를 더한다. 원본에서 읽는 헬퍼가 이미 있다 —
`foms/services/integrations/naver_commerce/mapping.py` 의 `extract_delivery`.
네이버가 이미 `sendDate` 를 말하는 상품주문은 `todo` 에서 빼고 `skipped` 로 돌린다.
**전부 skip 되면** 지금 코드가 이미 `{"dispatched": [], "skipped": [...]}` 를 돌려준다(`:545-546`) —
그 모양을 그대로 쓸지, 사람에게 다르게 말해야 하는지 판단하고 근거를 써라.

## 경계 — 하지 말 것

- **`_dispatch_view.mismatch` 규칙 변경 금지.** 오늘 운영에 올라간 판정이다
  ("우리 기록만 있고 네이버가 침묵" 한 방향만 어긋남).
- 발주확인·취소 판정 건드리지 마라.
- 이력 표 건드리지 마라(절대 규칙 3).
- 커밋·푸시 금지.

## 완료 기준

```bash
cd /c/tmp/nvfix
python -c "import app; print('APP_OK')"
export PYTHONIOENCODING=utf-8
python -m pytest tests/services/integrations -q
```

- 전량 통과(현재 739 passed 가 기준선이다 — 줄어들면 안 된다)
- **신규 단언 4건 이상**:
  ① 네이버에 `sendDate` 가 있고 우리 표식이 없는 집에서 **버튼이 잠긴다**
  ② 잠긴 이유가 **화면에 보인다**(title 에 시각까지)
  ③ 서버 `dispatch_order` 가 그 상품주문을 **호출에 넣지 않는다**(client 호출 0회 또는 payload 에서 제외)
  ④ 양쪽 다 기록 없는 정상 집은 **예전 그대로** 버튼이 열린다(못을 빼면 안 된다)
- 테스트 docstring 은 한국어로, **왜** 필요한지 적어라

## 보고 형식

변경 파일 · 집 vs 링크 단위 판단과 근거 · "전부 skip" 일 때 무엇을 돌려주기로 했는지와 근거 ·
위 명령의 실제 출력 마지막 줄.
