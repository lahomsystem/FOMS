# T8 — 반품을 FOMS 에서 네이버로 보내는 것: 설계 판정 (코드 금지)

작업 트리: `c:\tmp\nvfix`. **파일을 하나도 수정하지 마라.** 결과물은 판정과 설계서다.
스테이징·운영 접속 금지. 네이버 호출 금지.

## 배경 — 앞선 판정이 "하지 말자" 였고, 사용자가 "둘 다" 로 답했다

CEO 1차 판정은 이랬다:

> **C. 반품(return) 을 네이버로 전송 — 하지 말자.** 새 불가역 호출이다. 돈(환불)과 고객
> 통보가 걸린다. 클라이언트에 API 가 없고(`client.py` 메서드 4개), 현재 코드는 발송 뒤
> 취소를 막으며 "판매자센터에서 반품으로" 라고 사람을 보낸다
> (`foms/services/integrations/naver_commerce/fulfillment.py:642-651`) — 이건 결함이 아니라
> **의도된 경계**다. 반품은 취소보다 상태가 많다(수거·검수·환불 승인). 그 상태기계를 FOMS 에
> 두 벌 만드는 값어치가, 판매자센터를 한 번 여는 비용보다 크다고 볼 근거를 못 찾았다.

사용자는 그 판정을 읽은 뒤 **"둘 다"** 를 골랐다 — 읽기 버튼을 먼저 만들고, **반품 전송도
그 다음에 따로 설계해서 한다**는 뜻이다.

**그러니 이 task 는 "할까 말까" 를 다시 묻는 자리가 아니다.** 사용자가 하기로 정했다.
네 몫은 **"한다면 어떤 모양이어야 안전한가, 그리고 그 전에 무엇을 알아야 하는가"** 다.
다만 조사 끝에 **정말로 불가능한 것**(예: API 자체가 없다)이 나오면 그건 그대로 보고해라 —
못 하는 것을 할 수 있다고 말하는 쪽이 훨씬 나쁘다.

## 답해야 할 것

1. **네이버 커머스API 에 반품 처리 엔드포인트가 실제로 있는가.**
   우리 클라이언트(`foms/services/integrations/naver_commerce/client.py`)에 없다는 것은 확인됐다.
   API 자체의 유무를 코드·주석·`docs/` 안 문서·타입 정의에서 찾아라. 못 찾으면
   **"확인 못 함 — 네이버 공식 문서 확인 필요"** 라고 명시해라(지어내지 마라).
   `docs/guides/NAVER_*` 와 `docs/specs/` 를 뒤져라.

2. **반품의 상태기계가 실제로 몇 갈래인가.** 원본 스냅샷에 이미 오는 값으로 답해라 —
   `mapping.py` 의 `extract_claim` 이 읽는 `claimStatus`·`claimType`, 그리고
   `docs/guides/NAVER_FIELD_INVENTORY.md`. 취소(CANCEL)와 반품(RETURN)이 어떻게 다른지를
   **우리가 이미 받고 있는 값**으로 보여라. 오늘 실데이터에서 `RETURN_DONE` 이 관측됐다.

3. **어디까지가 FOMS 몫이고 어디부터가 판매자센터 몫인가.** 한 줄씩 갈라라.
   (예: 반품 접수는 고객이 한다 / 수거는 택배사 / 검수는 사람 / 환불 승인은? …)
   **FOMS 버튼 하나로 끝나는 갈래가 있는지**가 이 판정의 핵심이다. 없으면 없다고 해라.

4. **한다면 1단계는 무엇인가.** 가장 작고 되돌릴 수 있는 조각부터 순서를 매겨라.
   각 단계마다: 새로 생기는 **불가역 호출이 있는지 없는지**를 맨 앞에 표시해라.
   (참고: 지금 이미 있는 불가역 호출 3종 — 발주확인·발송처리·취소 — 은 전부 모달로
   재진술한 뒤에만 나간다. `naver_workbench_pane.html` 의 `wb-modal-*` 참고.)

5. **착수 전에 사람이 확인해야 할 것.** 네가 코드로 답할 수 없는 것들(네이버 API 계약,
   업무 규칙, 환불 정책). **한 줄 질문 목록**으로.

## 읽을 자리 (출발점)

- `foms/services/integrations/naver_commerce/client.py` — 메서드 4개가 무엇인지, 인증·재시도 구조
- `foms/services/integrations/naver_commerce/fulfillment.py:606-700` — `cancel_order` 와 발송 뒤 거절
- `foms/services/integrations/naver_commerce/mapping.py` — `extract_claim`
- `foms/services/integrations/naver_commerce/claim_watch.py` — 이미 반품을 **감지**하고 있다
- `docs/guides/NAVER_FIELD_INVENTORY.md` · `docs/guides/NAVER_INGEST_SETUP.md` · `docs/specs/`

## 보고 규율

- 모든 결론에 근거 `파일:라인`. 추측과 확인한 사실을 섞지 마라.
- 확인 못 한 것은 **"확인 못 함"** 이라고 써라. 특히 네이버 API 계약은 우리 저장소 밖이다.
- 새 불가역 호출이 생기는 설계라면 그 사실을 **보고서 맨 앞**에 써라.
- 한국어로.
