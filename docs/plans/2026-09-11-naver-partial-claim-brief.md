# 브리프: 네이버 수집 워크벤치 — 취소·반품의 **부분(상품주문 일부) 처리** (2026-09-11)

> 사용자 지시(원문): "https://lahom-production.up.railway.app/admin/naver-ingest/triage?tab=work&link_id=2354 —
> 수집 > 취소, 반품 시 부분 취소 반품도 가능하게 변경 해 봐. 멀티 에이전트 사용해서 병렬로 처리하고 CEO 에이전트가 총괄 지휘 해"

이 문서는 **1단계(조사·설계)** 브리프다. 네이버 커머스API 클레임 호출은 **불가역**이고 API 축(코어 변경)이라
스펙 → 사용자 승인 → 구현 순서를 지킨다. 1단계 산출 = 스펙 문서 `docs/specs/2026-09-11-naver-partial-claim_SPEC.md`
(CEO 가 쓴다) + 사용자에게 보일 요약·결정 질문. 구현은 2단계 워크플로에서.

작업 트리: `c:/tmp/foms-s-s0908-102606`(= origin/deploy `65c955ea7`). **1단계는 읽기만** — 코드·테스트 편집 금지, git 금지.

## 0. 지금 구조(총괄이 grep 으로 확인한 앵커)

- 클레임 라우트(`foms/web/admin/naver_ingest.py`): `POST /admin/naver-ingest/<link_id>/cancel` (:5128) ·
  `/return` (:5185) · `/reject-templates` (:5260) · `/return-reject` (:5322) · `/cancel-approve` (:5506) · `/return-approve` (:5530).
  전부 **link_id 하나**를 받고 서버가 그 집(같은 `external_order_no`)의 상품주문 전부를 대상으로 잡는다("집 단위").
- 서비스(`foms/services/integrations/naver_commerce/fulfillment.py`): `request_return` (:1695) · `reject_return` (:2111) ·
  `approve_return` (:2434). 취소 요청 함수도 같은 파일(이름은 리더가 확정). **범위 규격** FAQ 3880(:1481-1560, :1811-1830):
  본품을 반품하려면 그 본품의 추가구성상품이 전부 처리돼 있어야 한다 — 걸리면 한 건도 안 보낸다(불가역이라).
  호출 순서는 **본품 먼저**(`dispatch_call_order`, :2154). 취소 축은 FAQ 3880 검사를 안 한다(:1548).
- 집 클레임 집계: `dock.py:_household_claim`(코드 `partial` 이 이미 있다 — "일부 반품" 라벨, `claim_money_back` 쌍),
  `mapping.aggregate_claim` / `is_money_back_claim`. 이력 탭·도크·pane 배지가 이 집계를 읽는다.
- 화면(`templates/admin/partials/naver_workbench_pane.html`): 버튼 `#wb-return`(:409) · `반품 거부 N건`(:422) ·
  `네이버 반품 승인 — 환불 확정 N건`(:445) · 취소 처리 버튼(리더가 위치 확정), 모달 `#wb-modal-return` 등.
  pane 은 상품주문 1건을 열지만 버튼은 집 전체에 나간다(:80 주석). 상품주문 번호는 :190 에만 보인다.
- JS(`static/js/admin/naver-workbench.js`): `submitCancel` (:2194) · `submitReturn` (:2225) · `submitOriginCancel` (:1984) ·
  `submitOriginReturn` (:2019) · `submitReturnReject` (:2725) · `submitClaimApprove` (:2785) · `submitPlanClaimApprove` (:2826).
  요청 본문에 상품주문 목록이 있는지(없으면 집 전체) 리더가 확정.
- 워커: 클레임 호출은 WORKER 단일 출구(네이버 호출 IP 계약) — 큐 job 이 상품주문 1건씩 호출(사유 7코드), 멱등.
  `claim_watch.py` 가 클레임 모양 변화를 `triage_state['claim_sync']['history']` 에 남긴다.
- 스펙 이력(`docs/specs/`): `2026-08-22-naver-workbench-relation-and-cancel_SPEC.md` · `2026-08-27-naver-return-send_SPEC.md` ·
  `2026-08-28-naver-claim-phase-labeling_SPEC.md` · `2026-08-28-naver-repay-origin-cancel_SPEC.md` ·
  `2026-08-31-naver-return-approve_SPEC.md` · `2026-08-31-naver-return-reject_SPEC.md`. 원장 `docs/plans/2026-08-28-naver-claim-phase-ledger.md`,
  `2026-09-01-naver-claim-approve-ledger.md`, `2026-09-02-naver-addon-claim-order-ledger.md`.
- 테스트(`tests/services/integrations/`): `test_naver_cancel.py` · `test_naver_return_send.py` · `test_naver_return_reject.py` ·
  `test_naver_return_approve.py` · `test_naver_claim_approve.py` · `test_naver_addon_claim_order.py` · `test_naver_return_axis*.py` ·
  `test_naver_claim_phase.py` · `test_naver_dock_household_claim.py` · `test_naver_claim_guard_exchange.py` 등 28 파일.
- 전제(메모리): 반품은 **금액만**(물건 회수 축 없음) · 보류(holdback)는 실측 0회 · 읽기 범례 ≠ 쓰기 범례 ·
  네이버 규격 정본 = llms.txt + 공식 Discussions(`docs/` 에 인용 있음, 리더가 위치 확정).

## 1. 리더 3명이 답할 질문(읽기 전용)

**R1 서버·워커·규격**
1. 취소/반품/거부/승인 각 라우트가 대상 상품주문 집합을 어떻게 만드는가(집 전체? 상태 필터?). 함수·행 번호.
2. 워커 job 은 상품주문 1건씩 호출하는가, 집 단위 job 하나인가. 부분 실패 시 기록(`last_error`)·재시도·멱등 키.
3. 부분 처리에 걸리는 **규격**: FAQ 3880(본품↔추가구성) 검사 코드, 취소 축 예외, `dispatch_call_order`, 환불 방식(반품은 금액만).
   네이버 API 가 상품주문 단위 호출이라는 근거(client.py 메서드 시그니처·llms.txt 인용 위치).
4. 집 클레임 집계(`aggregate_claim`·`_household_claim`·`partial` 코드)와 이력·도크·pane·알림이 부분 상태를 어떻게 보이는가 —
   이미 "일부 반품" 이 표시되는 경로(네이버가 부분 처리했을 때)가 있는지.
5. 부분 처리가 정산·재결제/추가결제 관계·발주확인/발송·주문 만들기 가드(취소한 집은 차단 등)에 미치는 영향 지점.

**R2 화면·JS**
1. 취소/반품/거부/승인 모달 4종의 마크업(id·본문 문구·건수 표시·사유 입력·"승인까지 한 번에" 체크)과 JS submit 이 보내는 본문.
2. 집의 상품주문 목록이 pane 어디에 어떻게 그려지는가(멤버 표, 본품/추가구성 구분, 수량·금액, 상태 배지). 체크박스를 달 자리.
3. 성공/실패 결과 표시(줄마다 재시도 버튼, `wb-sendline`), 폴링·soft refresh 규약(2026-08-23), `.alert` 자동닫힘 함정(`data-foms-no-autodismiss`).
4. 기존 JS 계약 테스트가 못박은 문자열(모달 id·문구·건수 술어) 목록 — 부분 처리로 바뀌면 어떤 단언이 깨지는가.

**R3 스펙·테스트·결정 이력**
1. 6개 스펙에서 "집 단위" 를 택한 **이유**(D 결정 번호·문장 인용)와 부분 처리를 배제/유보한 문장.
2. 클레임 테스트 28 파일 중 부분 처리와 충돌할 계약(집 전체 건수 술어, 본품 먼저 순서, 범위 규격 차단, 멱등)을 파일:테스트명으로.
3. 네이버 규격 정본 인용(llms.txt·Discussions·FAQ 3880)의 저장소 내 위치와 부분 클레임 관련 문장.
4. 메모리·원장에 적힌 함정: 규격 감사 5건(`780011bd`)·잔여 5건(`f050ad32`)·본품만 반품 규격 위반(`8ad8348b`)·
   추가구성상품 집의 클레임 호출 순서(`555cfe8d`) — 커밋 메시지·원장에서 요지 인용.

## 2. CEO 가 낼 것(스펙 문서 + 요약)

`docs/specs/2026-09-11-naver-partial-claim_SPEC.md` 에:
- **문제 정의**: 지금은 집 전체만 취소/반품. 사용자는 상품주문 일부만 골라 처리하고 싶다(#2354 화면).
- **설계 안 2~3개**(예: A 모달에 상품주문 체크박스 + 서버 `product_order_ids` 옵션(기본=전체, 하위호환) /
  B 상품주문 행마다 개별 버튼 / …) — 각 안의 규격 제약 처리(FAQ 3880: 본품 체크 시 추가구성 자동 포함 또는 차단),
  워커 job 모양, 부분 상태 표시(집계 `partial`), 되돌림 불가 경고 문구, 테스트 영향, 위험. **권고안 1개**.
- **범위 결정 질문**(사용자에게 물을 것): 취소·반품 둘 다인가 / 거부·승인도 부분인가 / 재결제·추가결제 집에서도 허용인가 /
  본품 반품 시 추가구성 자동 동반 vs 차단.
- **2단계 구현 계획**: task 목록·파일 소유권 표(핀 복제 테스트 `grep -rn "?v=<옛핀>" tests/` 포함)·검증 명령·완료 기준·
  스테이징 QA 한계(**실호출 금지** — 네이버 클레임은 불가역. 스테이징에서도 실제 요청을 보내지 않는 방법: 워커 큐 미소비/드라이런/모의 클라이언트 중 무엇이 가능한지 R1 이 확인).
- 스펙은 한국어, 한자 없음, 코드·API 이름은 원문.

## 2-1. 사용자가 본 실제 집(운영 DB 읽기 전용, 2026-09-11) — 설계의 기준 사례

`link_id=2354` = 네이버 주문 `2026091191753751`, FOMS 주문 #5261(NEW·LINKED·발주확인 OK). 상품주문 **8건**:

| link | 상품 | 분류 | 수량 | 결제액 | 상태 |
|---|---|---|---|---|---|
| 2354 | 라홈 무몰딩 붙박이장 로라 30cm 푸쉬타입 (여닫이·클린 화이트) | **본품**(조합형옵션상품) | 13 | 1,233,700 | PAYED |
| 2355 | TYPE G (반통 반옷장) | 추가구성상품 | 1 | 0 | PAYED |
| 2356 | TYPE B | 추가구성상품 | 1 | 50,000 | **CANCELED(CANCEL_DONE)** |
| 2357 | TYPE J | 추가구성상품 | 1 | 50,000 | **CANCELED** |
| 2358 | TYPE E | 추가구성상품 | 1 | 100,000 | **CANCELED** |
| 2359 | TYPE D | 추가구성상품 | 1 | 50,000 | **CANCELED** |
| 2360 | TYPE I (긴옷장) | 추가구성상품 | 1 | 0 | PAYED |
| 2361 | TYPE A (반옷장) | 추가구성상품 | 1 | 0 | PAYED |

읽히는 뜻: 추가구성 4건은 **네이버 판매자센터에서 이미 개별 취소**됐다(우리 화면은 집 전체 버튼뿐이라 FOMS 에서는 못 했을 것).
사용자가 원하는 "부분 취소·반품" = **집 안의 상품주문 일부를 골라** 취소/반품 — 수량 일부(13개 중 몇 개)가 아니다
(네이버 `claim/cancel/request` 는 상품주문 단위, 수량 인자 없음 — R1 이 client.py 로 확정). 설계는 이 집을 기준 사례로:
① 이미 취소된 4건은 목록에 "취소 완료" 로 보이고 체크 불가 ② 0원 추가구성(PAYED)도 취소 대상이 될 수 있다(환불 0원) ③ 본품을 고르면
FAQ 3880 규격상 남은 추가구성 3건이 함께 가야 하는가(반품 축) — 취소 축은 예외인지 R1 확정.

## 3. 규칙

- 1단계는 **읽기만**. 파일 생성은 CEO 의 스펙 문서 1개만. git 금지.
- 추측 금지 — 인용은 경로:행. 모르면 "확인 못 함" 으로 적는다.
- 리더 보고는 각 2,500자 안(요약 + 앵커 표). CEO 는 리더 보고를 그대로 믿지 말고 핵심 앵커 5곳은 직접 열어 확인한다.
