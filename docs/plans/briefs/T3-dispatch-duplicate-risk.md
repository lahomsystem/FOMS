# T3 — 네이버 단독 발송 집에서 발송처리 중복호출이 나는가 (읽기 전용 조사)

작업 트리: `c:\tmp\nvfix` — **파일을 하나도 고치지 마라.** 이 task 는 조사다.

## 왜 묻는가

오늘 실측한 사실:

- 스테이징 워크벤치 링크 100건 중 **발송 행 44건**. 방향을 세니
  **네이버에만 발송 기록 41 · 양쪽 3 · 우리 쪽만 0**.
- 즉 "네이버에는 발송이 찍혔는데 FOMS 에는 우리 발송처리 표식이 없는" 집이 흔하다
  (판매자센터에서 직접 나간 발송으로 보인다).
- 운영은 반대다 — 같은 방향 **0건**, 양쪽 다 기록.

발송처리는 **되돌릴 수 없는 호출**이다(구매자에게 '배송 시작' 으로 보이고 구매확정·정산 시계가
돈다). FOMS 가 "아직 발송 안 함" 으로 알고 있는 집에 발송처리 버튼이 그대로 열려 있으면,
사람이 누르는 순간 이미 나간 발송에 **두 번째 호출**이 간다.

## 답해야 할 질문 (근거는 반드시 파일:라인)

1. **버튼이 열리는가** — 네이버 `delivery.sendDate` 는 있는데 우리 `triage_state.fulfillment
   .dispatched_at` 이 없는 집에서, 워크벤치 pane 의 발송처리 버튼(`wb-dispatch`)이 **활성인가**?
   판정식이 어디에 있는지 찾아라(`foms/web/admin/naver_ingest.py` 의 pane 컨텍스트에서
   `can_dispatch` · `dispatched` · `dispatched_any` 를 만드는 자리).
2. **눌리면 어떻게 되는가** — `foms/services/integrations/naver_commerce/fulfillment.py` 의
   `dispatch_order` 가 이미 발송된 상품주문을 어떻게 다루는가? skip 하는가, 그냥 부르는가?
   네이버 API 가 거절하는가(그 근거가 코드·주석·문서 어디에 있는가)?
3. **실제 위험 등급** — 위 둘을 합쳐 판정하라. 셋 중 하나로:
   - **없음**(서버가 이미 막는다 — 어디서 막는지 라인으로)
   - **있음, 화면만**(서버는 안전한데 버튼이 열려 헛클릭·오해를 만든다)
   - **있음, 실호출**(두 번째 호출이 실제로 네이버로 나간다)
4. **고친다면 가장 작은 수정은 무엇인가** — 코드를 쓰지 말고 **한 문단으로** 제안하라.
   (참고로 오늘 `_dispatch_view.mismatch` 를 "우리 기록만 있고 네이버가 침묵" 한 방향으로
   좁혔다. 그 반대 방향은 지금 화면에 아무 표식이 없다.)

## 읽을 자리 (출발점)

- `foms/web/admin/naver_ingest.py` — `_dispatch_view` · pane 컨텍스트의 `can_*` 판정 · `_group_queue`
- `foms/services/integrations/naver_commerce/fulfillment.py` — `dispatch_order` · `household_key`
- `templates/admin/partials/naver_workbench_pane.html` — `wb-dispatch` 버튼의 `disabled` 조건
- `tests/services/integrations/test_naver_fulfillment.py` — 이미 잠긴 계약이 있는지
- 오늘 원장: `docs/plans/2026-08-26-naver-field-surfacing-ledger.md`

## 하지 말 것

- **파일 편집 금지**(테스트 파일 포함).
- 네이버로 나가는 호출 금지. 스테이징·운영 접속 금지.
- "고칠 수 있다" 로 끝내지 마라 — 묻는 건 **지금 위험한가** 다.

## 보고 형식

질문 1~4 각각에 대해: **결론 한 줄 + 근거 `파일:라인`**. 추측과 확인한 사실을 섞지 마라.
확인 못 한 것은 "확인 못 함" 이라고 써라.
