# 네이버 워크벤치 취소·반품 — 상품주문 **일부만 골라** 처리 (NVCLAIM-PARTIAL-01) — 설계서

> 2026-09-11 · 1단계(조사·설계) 산출. 트리 `c:/tmp/foms-s-s0908-102606`(= origin/deploy `65c955ea7`), 읽기 전용.
> 브리프 `docs/plans/2026-09-11-naver-partial-claim-brief.md`. 리더 3명 보고(R1 서버·워커·규격 / R2 화면·JS /
> R3 스펙·테스트·이력)를 CEO 가 앵커 직접 확인 뒤 정리. 선행 스펙: `2026-08-22-naver-workbench-relation-and-cancel_SPEC.md`(취소),
> `2026-08-27-naver-return-send_SPEC.md`(반품 접수), `2026-09-02-naver-addon-claim-order_SPEC.md`(순서·범위 규격).
> **구현은 사용자 승인 뒤 2단계에서.** 네이버 클레임 호출은 되돌릴 수 없고 API 축(코어)이다.

## 0. 한 줄

지금 화면의 취소·반품 버튼은 **집(같은 `external_order_no`) 전체**에 나간다. 사용자는 집 안 상품주문 **일부만 골라**
취소·반품하고 싶다(#2354). 권고안은 **모달에 상품주문 목록+체크박스를 그리고, 서버가 명시된 `product_order_ids` 만 처리**하되,
본품을 고르면 그 집의 남은 추가구성상품을 **자동 동반**(FAQ 3880)하고, 취소 축의 집 단위 가드를 **라인 스코프**로 내리는 것이다.
수량 일부(13개 중 몇 개) 취소는 범위 밖이다.

## 1. 문제

- 기준 사례 `link_id=2354`(네이버 `2026091191753751`, FOMS #5261): 상품주문 8건 중 추가구성 4건(2356~2359)이 판매자센터에서
  이미 `CANCELED` 다(브리프 §2-1). 남은 4건(본품 2354 + 0원 추가구성 2355·2360·2361) 중 일부를 FOMS 에서 취소하고 싶다.
- 지금은 두 겹으로 막힌다:
  1. **화면**: 취소 모달은 "상품주문 {{ member_count }}건을 … 판매자 직접취소"(pane :1654)로 집 전체를 재진술하고, 고를 자리가 없다.
     JS `submitCancel` 본문은 `{reason, detail}` 뿐(js :2206-2209), 라우트도 `reason`/`detail` 만 읽는다(naver_ingest.py :5149-5150).
  2. **서버**: `cancel_order` 가 `_claim_guard(session, links, action="cancel", stamp=stamp)` 를 **집 단위**(scope=None)로 부른다
     (fulfillment.py :1254). 형제 1건이 `CANCEL_DONE` 이면 `blocks_irreversible` 이 참이라 **집 전체 취소가 거절**된다. 즉 #2354 집은
     지금 "전체 취소" 도 안 된다.
- 반품 축은 이미 반쯤 라인 단위다: `request_return` 이 `is_return_pending` 으로 고르고(:1770) `return_sendable` 로 막힌 라인을
  사유와 함께 뺀 뒤(:1801) `_claim_guard(..., scope=todo)`(:1833)를 쓴다. 다만 **사람이 고르는 축**은 없다.

## 2. 지금 구조 (CEO 가 직접 연 앵커 — 리더 보고 정정 포함)

| 층 | 사실 | 앵커 |
|---|---|---|
| 라우트 | 6개 전부 `link_id` 하나. 본문은 cancel `reason/detail`, return `reason/detail/approve`, return-reject `reason`, 승인 2종은 본문 안 읽음 | `foms/web/admin/naver_ingest.py` :5128-5153, :5185-5221, :5417-5503(`_enqueue_claim_approve`), :5506-5535 |
| 집 판정 | `_links_of_group`(같은 `external_order_no` + household) | `fulfillment.py` :351 |
| 취소 서비스 | `_claim_guard` 집 단위(:1254) → 발송된 집 거절 → `todo = claim_call_order([... not canceled_at])`(:1277) → 상품주문 1건씩 `request_cancel_product_order(pid, reason, detail)` → 성공분 `canceled_at` 표식, 실패분 `_mark_failures` → 부분 실패면 `FulfillmentError` | `fulfillment.py` :1220-1330 |
| 반품 서비스 | `todo = claim_call_order([... is_return_pending])`(:1770) → 교환 집 거절 → `return_sendable` 아닌 라인 사유 남기고 제외(:1801) → `addon_return_gap(links, todo)` 걸리면 **0건 전송**(:1815-1830) → `_claim_guard(scope=todo)`(:1833) | `fulfillment.py` :1695-1920 |
| 거부·승인 | `reject_return` `todo = dispatch_call_order([... is_return_rejectable])`(**:2163**, R1 보고 :2154 는 정정) · `approve_cancel` :2372 · `approve_return` :2475 — 셋 다 "요청이 걸린 행만" | `fulfillment.py` :2111-2545 |
| 호출 순서 | 취소·반품·승인 = **추가구성 먼저** `claim_call_order`(:440, #1321·#1410 인용 :456) · 발주확인·발송·거부 = 본품 먼저 `dispatch_call_order`(:482). **브리프 §0 "호출 순서 본품 먼저(:2154)" 는 거부에만 해당 — 정정** | `fulfillment.py` :440-503 |
| 범위 규격 | FAQ 3880 `addon_return_covered`(:1479) / `addon_return_gap`(:1521). **취소 축은 검사 안 함 — NOT IN DOCS**(:1547-1550). 단 addon 스펙 :46 이 인용한 FAQ 문장은 "반품/취소 처리하셔야 합니다" 로 취소를 함께 적는다(원문 전문은 저장소에 없음) | `fulfillment.py` :1479-1560, `docs/specs/2026-09-02-naver-addon-claim-order_SPEC.md` :46 |
| 가드 | `_claim_guard` 는 `scope` 인자가 있고 기본 집 전체(:538-598). `_cancel_guard` 는 `canceled_at` 1건이면 발주확인·발송을 **집 전체** 차단(:635-664, docstring "부분 취소 실패는 남은 건을 발송할 상황이 아니라 취소를 다시 보낼 상황이다") | `fulfillment.py` |
| 클라이언트 | 메서드 전부 `product_order_id: str` 단건. **`quantity` 인자가 있다**(`cancelQuantity` :575·:610, `returnQuantity` :683·:733) — **브리프 §2-1 "수량 인자 없음" 은 틀림.** 호출자는 넘기지 않아 현 기능은 상품주문 단위 전체 수량 | `client.py` :572-614, :680-738 |
| 워커 | job 은 집 단위 1개 `run_naver_fulfillment_task(link_id, action, actor, reason, detail, approve)`; `NaverCommerceClient()` 기본 생성(:448); `FulfillmentError` 는 commit 후 re-raise(:495-505, 성공분 표식 보존), 그 밖 예외는 rollback + `record_task_failure`(:506-514). RQ `Retry` 없음, job_id 없음, `job_timeout="5m"` | `tasks.py` :419-521, `queue.py` :260-425 |
| 집계 | `claim_aggregate_code` alive&&(done‖pending) → `partial`("일부 취소"/"일부 반품") — 네이버가 부분 처리한 집은 **이미** 그렇게 보인다 | `order_candidates.py` :559-585 |
| 화면 | 취소 모달 `#wb-modal-cancel` 건수 `member_count`(pane :1654); 반품 모달 `return_sendable_count`(:1712) + 부분 발송 부기(:1722-1727); 멤버 표 `.wb-cmp--members`(:800-903) 행에 상품주문번호·본품/추가구성·클레임 배지·"우리 접수 …"·수량·금액. 행 데이터 `_member_rows` 에 `link_id` 있음(:4121). 체크 가능/불가를 그릴 **행 단위 술어는 없음** | `templates/admin/partials/naver_workbench_pane.html`, `naver_ingest.py` :4056-4142 |
| 집 술어 | `_group_of_link` 가 `return_pending_count`·`return_sendable_count`·`return_scope_gap`·`*_approvable_count`·`*_approve_targets` 를 **서버 술어 그대로** 계산 | `naver_ingest.py` :4400-4470 |
| JS | `submitCancel`(:2194) `{reason, detail}` / `submitReturn`(:2225) `{reason, detail, approve}` / 승인 `{}`(:2785). `lockPaneActions` 는 `wb-confirm/dispatch/cancel/create` 4개만 잠금(:1590-1597). **"선택 없으면 전체" 패턴 금지** 주석(:1658-1664, 2026-08-14 사고) | `static/js/admin/naver-workbench.js` |
| CSS | `.wb-cmp--members th:nth-child(2)` 폭 규칙 — 열을 앞에 끼우면 한 칸 밀림 | `static/css/admin/naver-workbench.css` :520-521 |
| 핀 | `naver_workbench.html` :22/:1309 `?v=20260910a`. `count("?v=20260910a") == 2` 를 못박은 테스트는 **6개**(R2 보고 2개는 정정): `test_naver_backfill_route.py:168`, `test_naver_fulfillment_err_at.py:119`, `test_naver_origin_cleanup.py:551`, `test_naver_post_action_refresh.py:105`, `test_naver_repay_followup.py:134`, `test_naver_workbench_async_result.py:415` | `grep -rn "?v=20260910a" tests/` |
| 스테이징 | 스테이징 WORKER 도 같은 실계정 — 실호출 QA 불가 | `docs/specs/2026-08-31-naver-return-approve_SPEC.md` :129-130 |

"집 단위" 를 D 번호로 결정한 문장은 없다(R3 확인). 원점은 취소 스펙 §3.4 "상품주문 1건씩 부른다 … 집 단위로 돌며"(08-22 :85-88)와
`test_cancel_covers_the_whole_household_one_call_each`(test_naver_cancel.py :83 docstring "형제가 남으면 반쪽 취소가 된다").
부분 처리를 유보한 문장: claim-phase 스펙 :225 "부분 취소 케이스 — 운영 0건". **이제 운영 1건(#2354)이 생겼다.**

## 3. 설계를 강제하는 사실

1. **API 는 상품주문 1건 단위다**(#1410, client.py 단건 시그니처). 부분 클레임은 API 수준에서 자연스럽고, 우리 코드가 집을 묶은 것뿐이다.
2. **순서 규격**(#1321): 클레임 요청·승인은 추가구성 먼저. 부분집합에도 `claim_call_order` 를 그대로 적용하면 초집합 증명이 유지된다(:460-470).
3. **범위 규격**(FAQ 3880): 본품을 반품하려면 그 집 추가구성이 전부 처리돼 있어야 한다. 걸리면 0건 전송(부분 전송 = 2026-09-01 사고 모양).
   사용자가 **본품만 체크**하면 이 가드가 그대로 서버 거절이 된다 → 화면이 먼저 풀어야 한다(§5 결정 3).
4. **재진술 = 서버 처리 대상 한 벌**(계약 §0-2, 2026-08-27 CEO; 09-01 "건수가 아니라 목록"). 선택 UI 는 이 규율을 행 단위로 내려야 한다.
5. **멱등 키는 라인별 우리 표식**(`canceled_at` / `return.requested_at` / `approved_at`). 부분 처리와 호환된다.
6. **"선택 없으면 전체" 금지**(js :1658-1664). 서버 `product_order_ids` 가 비어 있으면 400 이어야 하고, 기본=전체 하위호환은 **키 부재**일 때만.
7. 실패 코드는 사유 불문 `9999`(#1457) — 메시지 파싱으로 판별 금지, 사전 가드로 예방.
8. 네이버 클레임은 불가역 + 스테이징도 실계정 → **실호출 없는 검증 경로가 필수**(§8).

## 4. 설계 안

### 안 A — 모달 안 상품주문 목록 + 체크박스, 서버 `product_order_ids` 명시 (권고)

- **화면**: 취소·반품 모달에 집의 상품주문 목록을 행으로 그린다(승인 모달 `<li>` 목록과 같은 모양, pane :1827). 행마다
  `<input type="checkbox" name="po" value="{{ row.external_id }}" data-link-id>` + 상품주문번호 + 본품/추가구성 + 금액 + 상태.
  서버 술어로 **체크 가능/불가**를 나눈다: 불가 행은 `disabled` + 사유("취소 완료"·"이미 발송"·"이미 접수"·"교환 중").
  가능 행은 **기본 전부 체크**(오늘 동작과 같음). 재진술 문장 "상품주문 <b data-wb-selected-count>N</b>건을" 은 JS 가 체크 수로 갱신하고,
  아래에 **선택된 상품주문번호 목록**을 다시 적는다(09-01 규율: 건수가 아니라 목록).
- **FAQ 3880 처리(반품, 결정 4 에 따라 취소도)**: 본품 체크 시 그 집의 `addon_return_covered` 아닌 추가구성이 **자동 체크·잠금**되고
  "본품과 함께 가야 하는 추가구성 N건이 자동으로 포함됩니다(네이버 규격)" 안내. 본품을 풀면 잠금도 풀린다. 서버는 그래도
  `addon_return_gap(links, scope)` 를 다시 검사한다(방어 깊이 — 화면 우회 요청도 0건 전송).
- **서버**: 라우트가 `product_order_ids: list[str]` 를 읽는다. 키 있음+빈 목록 → 400 "대상 상품주문을 고르세요". 키 없음 → 지금과 같은
  집 전체(옛 탭 하위호환). 집 밖 id 가 섞이면 400. `enqueue_naver_cancel/return(..., product_order_ids=...)` → `run_naver_fulfillment_task(..., product_order_ids=None)`
  → `cancel_order/request_return(..., product_order_ids=None)`. 서비스는 `scope = [row for row in links if external_id in ids]` 를 만들고
  `todo` 는 **기존 술어 ∩ scope** 로 좁힌다. 그 뒤 순서(`claim_call_order`)·범위(`addon_return_gap(links, todo)`)·가드(`_claim_guard(scope=todo)`)는 지금 코드 그대로.
- **취소 축 두 가지 변경**: ① `_claim_guard` 를 `scope=todo` 로(반품 T4 와 같은 모양) — 이것이 없으면 #2354 는 부분이든 전체든 취소 불가.
  ② 새 술어 `cancel_sendable(link)` = `not canceled_at and not dispatched and not blocks_irreversible(claim)` 를 fulfillment 에 한 벌 두고
  화면(체크 가능)·모달 기본 건수(`cancel_sendable_count`)·서버 `todo` 가 같은 술어를 쓴다(`return_sendable` 의 거울, :1444).
- **워커 job**: 모양 그대로(집 단위 job 1개 + `product_order_ids` kwarg). 새 job 종류·새 라우트 없음. 재시도 없음 유지.
- **부분 상태 표시**: 우리가 부분 취소하면 다음 수집 전까지 형제 스냅샷엔 클레임이 없다 → 멤버 표 클레임 칸에 **취소 축 "우리 취소 {canceled_at}"** 줄을
  추가한다(지금은 반품 축 "우리 접수 …" 만 있음, pane :860-873). 집 배지는 재수집(`_enqueue_refresh_after`) 뒤 `partial` → "일부 취소" 로 자동 전환(기존 경로).
- **되돌림 불가 경고**: 기존 빨간 띠(pane :1657) 유지 + 자동 동반 안내 alert(`data-foms-no-autodismiss` 필수) + "고르지 않은 N건은 그대로 남습니다" 부기.
- **테스트 영향**: `test_naver_workbench_v3_contract.py:379,401`(취소 모달 = member_count) → `cancel_sendable_count` 로 이동;
  `:384` `wb-cmp__k` 개수 — 체크박스를 멤버 표가 아니라 **모달에** 두므로 유지; `test_naver_cancel.py:83` 집 전체 계약은 **키 없음** 경로로 유지,
  `product_order_ids` 부분집합 테스트 신설; `test_naver_workbench_relation.py:494` → 재진술 술어 변경; `test_naver_return_wiring.py:408,453,475` 유지(대조군);
  `test_naver_addon_claim_order.py:365-450` 유지(서버 가드 그대로) + "본품만 고른 부분집합도 0건 전송" 신설; 핀 6 테스트 갱신; JS 함수명·`watchFulfillment(` 문자열 유지.
- **위험**: 체크 UI 가 붙으면 재클릭 표면이 커진다 → `lockPaneActions` 를 `wb-return/wb-return-reject/wb-*-approve-btn` 까지 확장. 같은 집에 서로 다른
  부분집합 job 2개가 겹치면 순차 실행되며 멱등 표식만 지킨다 — 합집합이 되므로 사고는 아니나 재진술과 다르다(잠금으로 예방).

### 안 B — 멤버 표 행마다 개별 "이 건만 취소/반품" 버튼

- 8건 집에서 클릭 8번. 행 단위 job 이 **본품·추가구성 순서(#1321)와 범위(FAQ 3880)를 job 사이에서 보장 못 한다** — 본품 행 버튼을
  먼저 누르면 서버가 gap 으로 거절하고, 사람은 추가구성부터 하나씩 눌러야 한다. 옛 결제(띠) 모달·승인 모달과 모양이 갈린다.
- 장점은 모달 재진술 계약을 건드리지 않는 것뿐. **기각** — 규격 순서를 사람 손에 맡긴다.

### 안 C — 선택 UI 없이 서버만 라인 스코프(취소 `_claim_guard(scope=todo)` + `cancel_sendable`)

- 최소 변경. #2354 의 **"남은 4건 전체 취소"** 는 열리지만 "그중 일부만" 은 여전히 불가. 모달 건수만 `cancel_sendable_count` 로 바뀐다.
- 사용자 요구("일부를 골라")를 못 채운다. 다만 **안 A 의 1차 조각(T1)** 으로 그대로 들어가므로 버리지 않는다.

### 권고: **안 A**, 구현은 안 C 를 1차 조각으로 삼아 두 조각으로.

## 5. 범위 결정 질문 (사용자 답 필요 — 권고 병기)

| # | 질문 | 선택지 | 권고 |
|---|---|---|---|
| 1 | 부분 선택을 어느 축에 여나 | 취소만 / 반품만 / **둘 다** | 둘 다 — 술어 모양(`*_sendable`)이 같아 한 벌로 만든다 |
| 2 | 거부·승인도 부분 선택인가 | 예 / **아니오** | 아니오 — 이미 "요청 걸린 행만" 처리하고 모달이 목록을 재진술한다(승인 스펙 §4-3 "부분 승인이 정상"). 사용자 임의 선택은 후속 |
| 3 | 본품을 고르면 남은 추가구성상품은 | **자동 동반(잠금)** / 차단(본품 체크 불가) | 자동 동반 + 서버 `addon_return_gap` 재검사 유지. 차단은 사고 복구 경로까지 막는다 |
| 4 | 취소 축에도 범위 규격(FAQ 3880)을 적용하나 | **예(안전측)** / 아니오(NOT IN DOCS 그대로) | 예 — 인용 FAQ 문장이 "반품/취소" 를 함께 적고, 위반 시 거절은 본품에만 오며 이미 나간 추가구성 취소는 되돌릴 수 없다. `test_naver_addon_claim_order.py:435` 대조군(추가구성만은 안 막힘) 을 취소 축에도 복제 |
| 5 | 부분 취소 뒤 남은 라인의 발주확인·발송을 여나(`_cancel_guard`) | **허용(표식 기반)** / 차단 유지 | 허용 — 부분 취소 job 이 성공 라인에 `cancel_scope: "partial"` 을 함께 찍고, `_cancel_guard` 는 그 표식이 있는 취소 라인을 "차단" 이 아니라 "발송 대상 제외" 로 읽는다. 취소 **실패**가 남은 라인(`last_error_action == "cancel"`)이 있으면 지금처럼 집 전체 차단. `test_naver_cancel.py:354` 는 실패 시나리오라 그대로 통과 |
| 6 | 재결제·추가결제 관계가 붙은 집에서도 허용하나 | **허용** / 관계 없는 집만 | 허용 — `repay_reconcile.discard_policy` 는 이미 `partial` 을 "옛 결제가 일부만 취소됐습니다" 로 폐기 차단한다(:176-182). 단 **옛 결제 띠 모달(`submitOriginCancel/Return`)은 이번 범위 밖**(집 전체 유지) |
| 7 | 수량 일부 취소(`cancelQuantity`) | 포함 / **범위 밖** | 범위 밖 — 호출자는 `quantity` 를 넘기지 않는다고 스펙에 고정. 읽기 축 `extract_partial_cancel` 만 유지 |

## 6. 계약 (mutation 규율 — 이 프로젝트가 데인 자리)

- **C1 재진술 = 처리**: 모달이 보이는 체크된 목록 == 서버 `todo`(순서까지 `claim_call_order`). 화면 술어와 서버 술어는 `fulfillment` 한 벌(`cancel_sendable`·`return_sendable`·`addon_return_gap`).
- **C2 빈 선택은 400**: `product_order_ids == []` 는 거절. 키 부재만 집 전체(옛 탭). 집 밖 id 400.
- **C3 0건 전송 규율 유지**: gap·교환·스코프 밖 클레임에 걸리면 한 건도 안 보내고 라인별 사유 기록(`_mark_failures`), `FulfillmentError`.
- **C4 조용한 축소 금지**: 체크됐는데 서버가 뺀 라인은 실패로 세어 예외(T3). 화면 실패 띠 + 멤버 표 라인 표시.
- **C5 멱등**: 같은 부분집합을 두 번 보내면 두 번째는 `todo` 가 빈다(호출 0회). 다른 부분집합은 합집합 — 잠금으로 겹침 예방.
- **C6 순서**: 부분집합 안에서도 추가구성 먼저(취소·반품), 본품 먼저(거부·발송). 기존 테스트 `test_naver_addon_claim_order.py:107,128,480,153` 유지.
- **C7 자동닫힘**: 새 alert 전부 `data-foms-no-autodismiss`(`tests/domains/test_alert_autodismiss_contract.py:36`).
- **C8 게이트**: 새 UI 는 `FOMS_NAVER_PARTIAL_CLAIM_ENABLED` + `_COHORT`(feature_flags 패턴 :309-330) 뒤. 꺼져 있으면 오늘 모달 그대로(롤백 경로 = 게이트 끄기).

## 7. 2단계 구현 계획

### 7-1. 조각(task)

| T | 내용 | 파일 |
|---|---|---|
| T1 (= 안 C) | `cancel_sendable(link)` 신설, `cancel_order` 의 `_claim_guard` 를 `scope=todo` 로, `todo` 술어를 `cancel_sendable` 로. 결정 4 면 `addon_return_gap` 을 취소 축에도 호출(도스트링 NOT IN DOCS 문장 갱신). `_group_of_link` 에 `cancel_sendable_count`·`cancel_scope_gap`. 취소 모달 건수를 `cancel_sendable_count` 로 | `fulfillment.py`, `naver_ingest.py`(집 술어), pane(취소 모달 건수) |
| T2 | 서비스 `product_order_ids` 인자: `cancel_order`·`request_return`(scope ∩ 술어, 집 밖 id 거절). 결정 5 면 성공 라인에 `cancel_scope` 표식 + `_cancel_guard` 표식 판독 | `fulfillment.py` |
| T3 | 큐·워커 인자 전달(`enqueue_naver_cancel/return` → `run_naver_fulfillment_task(product_order_ids=None)`) | `queue.py`, `tasks.py` |
| T4 | 라우트: `product_order_ids` 파싱·검증(C2), 감사 이력 payload 에 목록 | `naver_ingest.py` :5128-5260 |
| T5 | 미리보기 라우트 `GET /admin/naver-ingest/<link_id>/claim-plan?action=cancel|return&po=…` — 서버가 **같은 함수**로 `todo` 순서·자동 동반·gap·불가 사유를 계산해 JSON 으로 준다(네이버 HTTP 0회, web 에서 실행). 모달이 체크 변경마다 이걸 읽어 재진술한다(C1 을 서버가 보증) | `naver_ingest.py`, `fulfillment.py`(계획 함수 `plan_claim_scope` 순수 함수) |
| T6 | 화면: 모달 목록+체크박스+사유·자동 동반 안내·선택 목록 재진술, 멤버 표 "우리 취소" 줄, 게이트 분기, JS `submitCancel/submitReturn` 본문에 `product_order_ids`, `lockPaneActions` 확장, 핀 범프 | pane, `naver-workbench.js`, `naver-workbench.css`, `naver_workbench.html` |
| T7 | 게이트 함수 `is_naver_partial_claim_enabled(user_id)` | `feature_flags.py` |
| T8 | 테스트: 신설(부분집합 호출·빈 선택 400·집 밖 id·본품만 선택 0건·자동 동반 재진술·멱등·`_cancel_guard` 표식) + 기존 갱신(§4-A 목록, 핀 6곳) | `tests/services/integrations/` |
| T9 | 문서: `docs/AI_STATUS.md` 상단, `AI_CHANGELOG.md`, `DECISIONS.md`(결정 1~7), 이 스펙 §9 에 결정 기록 | docs |

### 7-2. 파일 소유권 (동시 편집 금지 — 워크트리 1개, 소유자 1명씩)

| 파일 | 소유 | 비고 |
|---|---|---|
| `foms/services/integrations/naver_commerce/fulfillment.py` | 서버 워커 A | T1·T2·T5 순수 함수 |
| `foms/services/jobs/queue.py`, `foms/services/jobs/tasks.py` | 서버 워커 A | T3 |
| `foms/web/admin/naver_ingest.py` | 서버 워커 B | T4·T5 라우트, 집 술어 |
| `foms/services/feature_flags.py` | 서버 워커 B | T7 |
| `templates/admin/partials/naver_workbench_pane.html`, `templates/admin/naver_workbench.html` | 화면 워커 C | T6, 핀 |
| `static/js/admin/naver-workbench.js`, `static/css/admin/naver-workbench.css` | 화면 워커 C | `node --check` 필수 |
| `tests/services/integrations/test_naver_partial_claim*.py`(신설) | 테스트 워커 D | 서비스·라우트·화면 계약 |
| 기존 테스트 갱신(v3_contract·relation·cancel·핀 6곳) | 테스트 워커 D | 갱신은 단언 이동만, 삭제 금지 |
| `docs/*` | CEO | T9 |

핀 복제 확인 명령: `grep -rn "?v=20260910a" tests/` → `naver_workbench.html` 을 세는 6개만 새 핀으로(`test_naver_dock*`·`test_drawing_*`·`test_erp_quest_display`·`test_p2_gate` 는 다른 템플릿 — 건드리지 않는다).

### 7-3. 검증 명령 · 완료 기준

```
python -c "import app; print('APP_OK')"
node --check static/js/admin/naver-workbench.js
python -m pytest -q tests/services/integrations/ -k partial_claim
python -m pytest -q tests/services/integrations/test_naver_cancel.py tests/services/integrations/test_naver_return_send.py \
  tests/services/integrations/test_naver_addon_claim_order.py tests/services/integrations/test_naver_return_wiring.py \
  tests/services/integrations/test_naver_workbench_v3_contract.py tests/services/integrations/test_naver_workbench_relation.py \
  tests/services/integrations/test_naver_claim_approve.py tests/services/integrations/test_naver_return_reject.py
python -m pytest -q tests/services/integrations tests/domains
grep -rn "?v=20260910a" tests/ templates/admin/naver_workbench.html   # 워크벤치 6곳 0건이어야
powershell -File scripts/ops/pre_push_smoke.ps1                          # exit 0
```

완료 기준: 위 전부 green · 신설 테스트에 **음성 대조군**(추가구성만 선택은 gap 에 안 걸림, 키 부재는 집 전체, 게이트 꺼짐은 옛 모달) 포함 ·
`APP_OK` · 스테이징 §8 ①②③ 통과 · 사용자가 #2354 스테이징 화면에서 모달 목록·자동 동반·재진술을 확인.

### 7-4. 롤아웃

deploy(스테이징) → 게이트 OFF 로 배포 → §8 QA → 게이트 ON(코호트 = 사용자 1명) → 운영 첫 실사용은 **0원 추가구성 1건 취소**(#2354 의 2355)처럼
환불액 0인 라인으로 — 잘못돼도 돈이 움직이지 않는다. 그 뒤 production 승격은 사용자 명시 요청 시 `promote_own_to_production.py`.

## 8. 실호출 없는 검증 경로 (필수 — 클레임은 불가역, 스테이징도 실계정)

코드에 모의 클라이언트·드라이런·큐 미소비 스위치는 **없다**(R1 확인: `dry_run` 은 backfill/order_sync/settle_sync 만, queue.py :427-560; 워커는
`NaverCommerceClient()` 기본 생성 tasks.py :448; 생성자는 `base_url/transport` 인자만 client.py :330-340). 쓸 수 있는 길 셋:

| # | 길 | 검증 범위 | 조건·한계 |
|---|---|---|---|
| ① | **서비스 계약 테스트** — `_StubClient`(test_naver_cancel.py :24-40 패턴, `request_cancel_product_order` 호출 기록·건별 실패 주입) | 부분집합 선택·순서·gap 0건 전송·멱등·`_cancel_guard` 표식·라인별 실패 기록 전부 | 주 증명 경로. HTTP 0회 |
| ② | **스테이징 web 만** — 게이트 ON(코호트 `claude_master` id58) 상태에서 #2354 급 집을 열어 모달 목록·자동 동반·`claim-plan` 미리보기 JSON 을 확인. **확인 버튼은 누르지 않는다** | 화면·재진술·미리보기 라우트(T5 는 web 에서 돌고 네이버를 부르지 않음) | Cursor browser MCP / gstack browse. 실데이터 집 사용(주입 금지) |
| ③ | **스테이징 WORKER 자격증명 제거 창** — `NAVER_COMMERCE_CLIENT_ID/SECRET` 를 잠시 비우면 `_request` 가 전송 전 토큰 발급에서 `NaverCommerceConfigError`(client.py :222-225) → HTTP 0회, 큐→워커→서비스→라인별 `last_error` 기록→실패 띠·soft refresh 까지 **끝까지** 관찰 | end-to-end(실패 갈래) | 그 창 동안 스테이징의 다른 네이버 job(수집 스윕·다시 읽기·정산)도 전부 실패한다 — 짧은 창 + 끝나면 되돌리고 재배포(`variables --set` 은 재배포를 안 건다, 메모리). 토큰 캐시 키가 client_id 해시라 빈 id 히트 없음(:368-371, R1 주장 — 실측 못 함) |

쓰지 않는 길: **워커 정지 후 큐 적재만 보기** — 재기동 시 적재된 불가역 job 이 뒤늦게 실행된다(RQ 큐를 비우는 절차 없이 금지).
**운영 실호출**은 사용자 명시 요청 1건당 1회·측정만 규칙과 별개로, 이 기능의 첫 실사용(§7-4)이 곧 실호출이다 — 0원 라인으로 시작한다.

## 9. 위험과 대응

| 위험 | 대응 |
|---|---|
| 본품만 선택 → 네이버 거절, 이미 나간 추가구성 취소는 불가역(2026-09-01 사고 모양) | 화면 자동 동반 + 서버 `addon_return_gap` 재검사(0건 전송). 취소 축도 적용(결정 4) |
| 재진술과 처리가 갈림(과대·과소 진술) | T5 미리보기가 서버 함수로 목록을 준다. 계약 테스트가 모달 목록 == `todo` 를 단언 |
| 취소 `_claim_guard` 라인 스코프로 내리면 "형제 클레임이 집을 막는" 기존 계약이 흔들림 | 발주확인·발송·교환 집 가드는 그대로 집 단위. 취소만 반품 T4 와 같은 모양. `test_naver_claim_guard_exchange.py` 유지 확인 |
| 부분 취소 뒤 발송이 집 단위로 막힘 | 결정 5 표식 기반 허용. 취소 실패 라인이 있으면 여전히 차단 |
| 서로 다른 부분집합 job 2개 겹침 | `lockPaneActions` 확장 + 폴링 중 버튼 잠금. 멱등 표식으로 이중 호출은 없음 |
| `quantity` 인자로 범위가 "수량 부분" 으로 번짐 | 결정 7 범위 밖 고정, 호출자에 `quantity` 금지 계약 테스트(호출 kwargs 에 `quantity` 없음 단언) |
| 스테이징 ③ 창에서 다른 job 실패 | 창을 짧게, 사전 공지, 끝나면 재배포로 복구 확인 |
| RQ job TTL·result TTL 미확인 | 코드에 없음(확인 못 함). 큐 미소비 방식은 쓰지 않는다 |
| 옛 탭 JS 가 `product_order_ids` 없이 보냄 | 키 부재 = 집 전체(오늘 동작) + 핀 범프로 새 JS 강제 |

## 10. 확인 못 한 것

- FAQ 3880 원문 전문(취소 포함 여부) — 저장소엔 인용문만. 안전측으로 취소에도 적용 권고.
- 네이버가 취소 축에서 본품만 취소를 거절하는지 — 실측·문서 없음.
- 스테이징 WORKER 의 실제 env(`NAVER_COMMERCE_CLIENT_ID` 존재, `FOMS_NAVER_*_ENABLED` 값).
- RQ 기본 job/result TTL.
- 체크박스 목록이 8행 이상 집에서 모달 높이에 어떻게 보이는지(브라우저 미실행).

## 11. 결정 기록 (사용자 답을 여기에 적는다)

| # | 질문 | 답 | 날짜 |
|---|---|---|---|
| 1 | 부분 선택을 어느 축에 | **취소·반품 둘 다** | 2026-09-11 |
| 2 | 거부·승인도 부분 선택 | **아니오(범위 밖)** — 이미 요청 걸린 행만 다루므로 | 2026-09-11 |
| 3 | 본품 선택 시 남은 추가구성 | **자동 동반 + 서버 재검사(0건 전송 규율)** | 2026-09-11 |
| 4 | 취소 축에도 FAQ 3880 범위 규격 | **예(안전측)** | 2026-09-11 |
| 5 | 부분 취소 뒤 남은 라인 발주확인·발송 | **허용** — 취소 표식 라인 제외, 취소 실패 라인 있으면 차단 유지 | 2026-09-11 |
| 6 | 재결제·추가결제 관계 집 | **허용** | 2026-09-11 |
| 7 | 수량 일부 취소 | **범위 밖** — 호출자 `quantity` 금지 계약 | 2026-09-11 |
| 8 | 취소 버튼이 형제 클레임으로 집을 잠그나 | **아니오(CEO, 계약 §4 개정)** — `can_cancel` 은 `household_claimed` 를 안 본다. 행 술어 `cancel_sendable_count > 0` + 서버 `_claim_guard(scope=todo)` 가 형제 클레임을 라인 단위로 거른다 | 2026-09-11 |
| 9 | 벌크 발송 pre-check(`bulk_dispatch._blocking_reason`) | **`_cancel_guard` 거울(CEO)** — partial 표식 행은 클레임 판정에서 빼고 집도 잠그지 않는다. household·옛 키 없음 표식, 취소 실패 잔존(`last_error_action == "cancel"`)만 잠금 | 2026-09-11 |

기준 사례: 운영 #2354(브리프 §2-1). 스펙 승인 2026-09-11, 2단계 구현 워크플로로 진행.

### 11-1. 계약 개정·앵커 (CEO 재판정 2026-09-11, 구현 반영 뒤 행 번호)

- **계약 §4 개정**: `can_cancel = not household_canceled and not dispatched_any and not naver_sent_at and cancel_sendable_count > 0 and not cancel_scope_gap` (결정 8). pane 은 `household_claimed = selected_household_claimed or (selected.claim.blocking and not selected.partial_canceled) or grp.claim_blocking` 으로 — 어느 형제로 열었느냐에 따라 발주확인·발송 버튼이 달라지지 않는다(M-4).
- **계약 §3 앵커 추가**(결정 5 — 우리가 일부 취소한 행의 `CANCEL_DONE` 은 집을 잠그지 않는다, `_group_queue`·`_household_has_claim` 와 같은 규칙):
  `naver_ingest._attach_household_counts` :3570-3605(옛 경로, `blocking`) · `naver_ingest._build_sibling_index` :3792-3811(`index.blocking`·`index.confirmed_claim_blocked`·`index.canceled`) · `naver_ingest._triage_pane.selected.partial_canceled` :1592 · `bulk_dispatch._blocking_reason` :341-372(결정 9).
- **공존 — 설계 유지**: 목록 줄 `_row_view`(:2786-2790) 는 형제 `CANCEL_DONE`(판매자센터 취소, 우리 표식 없음) 집을 여전히 `stop`/"손대지 않음" 으로 그리고, pane 은 같은 집에서 취소 버튼을 연다. 목록 줄 술어는 **발주확인·발송 축**이고 취소 축은 pane 의 행 단위 모달만 쓴다 — 반품 축과 같은 공존이다. 고치지 않는다.
- 회귀 테스트: `tests/services/integrations/test_naver_partial_claim*.py` (a) `test_list_row_and_pane_stay_open_for_a_partially_canceled_sibling`(음성 대조군 household·옛 표식) (b) `test_pane_buttons_do_not_depend_on_which_sibling_opened_it` (c) `test_bulk_blocking_reason_mirrors_the_cancel_guard`(순수 함수, 네이버 0회). `is_partial_canceled` 를 항상 False 로 바꾸면 셋 다 red 임을 CEO 가 재확인했다.
