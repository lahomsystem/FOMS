# 네이버 추가구성상품 클레임 호출 순서 — 설계서 (NVCLAIM-ORDER-01)

> 2026-09-02 작성. 사고: 황민철 집(ERP 주문 5026, 네이버 2026082772909971) 반품 4건 중
> **본품 1건 실패**, 추가상품 3건만 환불 확정. 운영 미해결 상태.

## 0. 사고 사실 (운영 DB 실측, readonly)

| link_id | 상품주문번호 | `productClass` | `productOrderStatus` | 결과 |
|---|---|---|---|---|
| 117 | 2026082754601551 | `조합형옵션상품`(본품) | `DELIVERING` | **실패** |
| 118 | 2026082754601561 | `추가구성상품` | `RETURNED` | 성공 |
| 119 | 2026082754601571 | `추가구성상품` | `RETURNED` | 성공 |
| 120 | 2026082754601581 | `추가구성상품` | `RETURNED` | 성공 |

- link 117 `triage_state.fulfillment.last_error` =
  `추가상품 반품진행 후, 본 상품 반품진행을 할 수 있습니다.` / `last_error_action="return"` /
  `last_error_at=2026-09-01T23:33:44.177615`.
- 117 에는 `return` 축 기록이 **아예 없다**(접수 미성립). 118~120 은 같은 타임스탬프에
  `requested_at`+`approved_at`, 4초 뒤 `RETURN_DONE`.
- 선행: 23:27:14 `NAVER_ORDER_ATTACHED` relation=`REPAY` (새 주문 2026090227951661) —
  실측 후 재결제로 새 주문을 붙이고 옛 주문을 반품한 흐름.
- ERP 주문 5026 은 `status=MEASURE`, `completion_date=NULL` — **ERP 가 종결된 것이 아니다.**
  사용자가 본 '마무리'는 2026-08-31 발송처리 + 화면 잠금·`반품 완료` 배지의 효과다.

## 1. 규격 정본 (네이버 공식, 재검증 완료)

**GitHub Discussion #1321**, author `commerce-api-naver`, category 자주 묻는 질문
(https://github.com/commerce-api-naver/commerce-api/discussions/1321 — `intro-문제해결.md` 가
지정한 공식 기술지원 채널). GitHub API 로 원문 직접 확인:

> **A. 발송 처리(취소 철회)는 "본상품 → 추가구성상품" 순서로, 클레임 요청/승인은
> "추가구성상품 → 본상품" 순서로 호출해야 합니다.**
>
> ### 발송 처리 (취소 철회(거부))
> - 조건: … 모두 취소 요청 상태인 경우
> - 처리 순서: 1. 본상품 상품주문번호 2. 추가상품 상품주문번호
>
> ### 클레임 요청/승인
> - 조건: … 모두 취소 요청, 취소 요청 승인, **반품 요청, 반품 승인**, 교환 재배송 처리를
>   진행하려는 경우
> - 처리 순서: 1. 추가상품 상품주문번호 2. 본상품 상품주문번호

보강 근거:
- `wiki-스마트스토어-상품-가이드.md` §추가상품: "구매자가 본 상품을 취소/반품하고
  추가상품만 취득할 수 없도록 설계되어있습니다."
- 판매자센터 FAQ 3880: "본상품과 추가구성 상품을 **모두 접수하여** 반품/취소 처리하셔야 합니다."
  → **접수(요청) 단계에서 순서를 지키면 된다. 추가상품이 수거·환불 완료까지 갈 필요 없다.**
- Discussion #1410 (커머스API 이민석): "API 1회 호출에 1개 상품주문번호만 요청이 가능합니다."
  `successProductOrderIds` 배열은 스키마 공통화일 뿐 다건 지원이 아니다 → **순서는 호출자 책임**.
- Discussion #2588 (커머스API 안아영): 추가상품 판별은 `productOrder.productClass == "추가구성상품"`.
  `productClass` **전체 범례는 미공개** → 본품 화이트리스트 금지, `== 추가구성상품` 부정 판정만 안전.
- 오류 문자열 `추가상품 반품진행 후…` 는 **문서에 없다(NOT IN DOCS)**. 실패 항목 코드는
  사유 불문 `"9999"` 로 온다(#1457 원문) → **메시지 파싱으로 판별 금지, 순서로 예방한다.**
- **반품 거부(`return/reject`) 의 순서는 문서에 없다(NOT IN DOCS).** 취소 철회와 대칭이라
  본품 먼저로 **추정**되며, 현행 코드가 이미 본품 먼저다 → **이번 변경에서 건드리지 않는다.**

## 2. 근본 원인 5층

| # | 원인 | 위치 |
|---|---|---|
| RC1 | 클레임 호출이 수집 순서(본품 먼저)로 나간다 — 규격의 정반대 | `fulfillment.py:1189-1190` ← `_links_of_group` `:311` `id.asc()` |
| RC2 | 부분 실패가 성공으로 종결(`if failures and not ok_ids`) | `fulfillment.py:1221` (대조: 취소 `:943` `if failures:`) |
| RC3 | 부분 성공이 남은 라인을 영구 잠근다(집 단위 all-or-nothing 가드) | `fulfillment.py:1160/336-375`, `naver_workbench_pane.html:36-38,122,342` |
| RC4 | 집 배지가 집계가 아니라 첫 라벨(first-non-empty-wins) | `naver_ingest.py:3552`, `:661`, `dock.py:833` |
| RC5 | `확인함` 이 집 전체 `last_error` 를 지워 유일한 증거를 없앤다 | `fulfillment.py:629-665` |

RC1 은 반품 접수만이 아니라 **클레임 요청·승인 4경로 전부**에 있다(아직 안 터졌을 뿐):
`cancel_order:922` · `request_return:1190` · `_approve_returns:1070` · `approve_cancel:1555` ·
`approve_return`. 반대로 `confirm_place_order:611` · `dispatch_order:815` 는 **본품 먼저가 정답**이라
바꾸면 안 된다.

## 3. 설계

### T1 — 호출 순서 SSOT (RC1)
`fulfillment.py` 에 정렬 한 벌을 둔다.

```python
def claim_call_order(links: list[ExternalOrderLink]) -> list[ExternalOrderLink]:
    """클레임 **요청·승인** 호출 순서 — 추가구성상품 먼저, 본품 나중.
    근거: 네이버 공식 FAQ Discussion #1321. 정렬은 안정정렬이라 같은 부류 안에서는
    수집 순서(id asc)가 보존된다 — 귀속 판정(attribution)과 어긋나지 않는다."""
```
- 판정: `mapping.is_addon_detail(link.raw_snapshot or {})` (기존 함수 재사용, `unwrap_detail` 이
  `raw_snapshot` 모양을 그대로 받는다). 값이 없는 옛 원본은 본품으로 본다 = 뒤로 간다(안전측).
- 적용: `cancel_order` · `request_return` · `_approve_returns` · `approve_cancel` · `approve_return`.
- **미적용(고정)**: `confirm_place_order` · `dispatch_order` · `reject_return` — 본품 먼저 유지.
  계약 테스트로 이 방향을 못박는다(누가 "일관성" 이유로 뒤집는 것을 막는다).

### T2 — 부분 실패는 실패다 (RC2)
`request_return:1221` 을 `if failures:` 로 바꿔 취소 경로와 규율을 맞춘다. 안전 확인:
`tasks.py:441-452` 의 `except FulfillmentError:` 는 **rollback 하지 않고 commit 한 뒤 raise** 하므로
성공분 표식과 실패 사유가 모두 보존된다. 같은 규율을 승인 경로에도 적용한다.

### T3 — 실패한 라인에 반품 축 기록 (RC2·RC5)
실패분에도 `return` 축에 `failed_at`/`failed_reason` 을 남긴다. 지금은 축이 비어 있어
"아직 안 보냄"과 구분되지 않는다.

### T4 — 가드 스코프를 라인으로 (RC3)
`_claim_guard` 를 **보낼 대상(todo)** 에만 적용한다. 지금은 집 안 형제 한 건이라도 클레임이면
전체를 거절해서, 부분 성공한 집이 자기 자신을 잠근다. 불가역 호출을 이미 클레임 걸린 라인에
보내지 않는다는 원래 목적은 라인 스코프로 그대로 지켜진다.
→ **이 변경만으로 황민철 본품이 FOMS 에서 접수 가능해진다**(추가상품 3건이 이미 `RETURN_DONE`
이라 네이버 선행조건은 충족 상태).
- `confirm`/`dispatch` 의 집 단위 가드는 **그대로 둔다**(축이 다르다).

### T5 — 화면이 부분 반품을 말한다 (RC4)
- 집 배지: `naver_ingest.py:3552` first-wins → 부분/전부 집계. 어휘는 이미 있다
  (`order_candidates.py:238-243` `partial="일부 취소"` …) — 반품용 문구를 같은 자리에 둔다.
- 상품주문 표 `_member_rows:3340` 에 라인별 클레임 상태 칸 추가 → "어느 건이 반품됐나"를 말한다.
- 실패 띠에 **어느 상품주문이 실패했는지** 노출.

### T6 — 재시도 경로 (RC3)
pane `can_return`(`:122`)·`{% if dispatched_any and not locked %}`(`:342`) 이 `locked` 로 버튼을
닫는다. 라인 단위로 "보낼 게 남았는가"(`return_pending_count > 0`)를 기준으로 바꾼다.
서버 라인 가드(T4)가 최종 문이다.

### T7 — `확인함` 을 라인 단위로 (RC5)
`clear_failure` 가 집 전체 `last_error` 를 지운다 → 실패한 라인만 지우거나, 실패가 남은 집은
지우지 못하게 한다.

### T8 — 테스트 (전부 신규)
1. 혼합 집(본품 1 + 추가상품 3) 반품 접수 → **호출 순서가 추가상품 먼저**임을 단언.
2. 같은 집에서 `dispatch` 는 **본품 먼저**임을 단언(방향 고정).
3. 부분 실패(성공 3 + 실패 1) → `FulfillmentError` 가 오르고, 성공분 표식·실패 사유가 **둘 다** 남는다.
4. 형제가 `RETURN_DONE` 인 집에서 남은 본품 접수가 **통과**한다(T4 회귀).
5. 부분 반품 집의 배지가 `반품 완료` 가 아니라 부분 표기다(T5 회귀).
6. 승인 경로 3종의 순서 계약.

### T9 — 기록
`DECISIONS.md` + 본 설계서 + 메모리. 저장소에 이 제약 기록이 **0건**이었다.

### T0 — 운영 복구 (사용자 승인 필요)
배포 후 FOMS 트리아지에서 본품 2026082754601551 반품 접수 + 승인.
**그 전까지 실패 띠의 `확인함` 을 누르지 말 것** — 유일한 증거가 사라진다(RC5).

## 4. 범위 밖
- 반품 거부 순서(NOT IN DOCS) — 현행 유지.
- 발주확인·발송처리 순서 — 현행 유지, 테스트로 고정.
- ERP 주문 상태 자동 변경 — 없음이 정본(`claim_watch.py:11`), 유지.

---

# 부록 A — CEO 리뷰 판정 (2026-09-02, 판정=CHANGE)

본문 §3 의 T 번호는 아래 **최소 출하 세트**로 대체한다. 되돌린 판단 3가지:

## A-1. 발송처리 본품-먼저는 "현행 유지+테스트 고정"이 아니라 **코드로 강제**해야 한다
`confirm_place_orders(ids)`(`fulfillment.py:601`)·`dispatch_product_orders(payload)`(`:805`) 의
배열 순서는 `todo` 를 그대로 쓰고, `todo` 순서는 `_links_of_group:311` 의 `ORDER BY id ASC` 다.
**본품 먼저를 강제하는 코드는 0줄이고, 오늘 맞는 건 수집 순서와 우연히 일치하기 때문이다.**
변경 피드 기반 재수집(`ingest.py:135,287`)은 상태가 바뀐 상품주문만 골라 넣으므로 추가상품 행이
본품보다 작은 id 를 갖는 집이 만들어질 수 있다. 그런 집에서 발송처리는 #1321 을 **불가역
방향으로** 위반한다. 일괄 발송처리는 한 번에 여러 집을 처리해 폭발 반경이 이번 사고보다 크다.
→ `dispatch_call_order()`(본품 먼저)를 대칭 SSOT 로 신설하고 두 자리에 적용한다.
→ 계약 테스트 픽스처는 **추가상품 id 가 본품보다 작게** 만든다. 본품 id 가 작은 픽스처는
   정렬이 없어도 통과하는 동어반복이다.

## A-2. RC2 는 1곳이 아니라 4곳
`request_return:1221` · `reject_return:1384` · `approve_cancel:1581` · `approve_return:1650`.
뒤 둘은 **환불 확정** 경로다(되돌리는 API 없음). 넷 다 이번 배에 고친다 — 각 1줄이다.
안전 확인: `tasks.py:443-453` 은 `FulfillmentError` 에서 **commit 후 raise** 라 성공 표식과 실패
사유가 둘 다 보존되고, `queue.py` 에 `Retry(`/`retry=` **0건**이라 raise 가 불가역 호출을
자동 재전송하지 않는다.

## A-3. T5(배지)·T6(버튼)은 가시성이 아니라 **필수**다
- 실패 띠는 실제로 떴다(link 117 에 `last_error` 존재). 사람이 성공으로 믿은 직접 원인은
  집 배지가 `naver_ingest.py:3552` 의 first-non-empty-wins 로 `반품 완료` 라고 말한 것이다.
- 오늘 그 집은 `locked=True` 라 `naver_workbench_pane.html:342`
  `{% if dispatched_any and not locked %}` 가 반품 버튼을 **렌더조차 안 한다** →
  T4(서버 가드 라인화)만 배포하면 열린 문에 도달할 UI 가 없다.

## A-4. 다중 본품 집 — 평면 정렬 유지, 인터리브 **기각**
평면 `[추가상품 전부…, 본품 전부…]` 는 임의의 본품 M 에 대해 그 addon 들이 전부 접두부에
있으므로 **모든 per-main 선행조건을 만족하는 상위집합**이다. 인터리브(`a(M1),M1,a(M2),M2`)는
불가역 호출 순서를 `attribution.py` 의 **추정 휴리스틱**에 묶는다 — 그 모듈은 스스로
`REASON_UNRESOLVED`(`attribution.py:38`)를 내고 `split_main_groups:1264` 는 미정 옵션을
`fallback_index` 로 아무 본품에나 붙인다. 화면 귀속이 틀리는 것과 환불 호출 순서가 틀리는 것은
대가가 다르다.

## A-5. 가드 라인화에 예외 1종을 남긴다
분할발송 + **진행 중 교환** 집: M1 이 미발송 `EXCHANGE_REQUEST` 이고 그 추가상품 a1 만 발송된
경우 `todo=[a1]` 이라 라인 가드를 통과해 **교환이 도는 집에 불가역 반품 접수가 나간다**.
이는 `_claim_guard` docstring `:346-349` 가 R-4(2026-08-28)로 못 박은 회귀다.
→ `household_exchange_in_flight(links)` 면 집 단위로 계속 막는다. 그 외 클레임(취소·반품,
진행·완료 불문)은 라인 스코프.
→ `todo` 자체를 `return_sendable` 로 좁히지 **않는다.** 좁히면 빈 `todo` 가
`{"returned": []}` 로 **조용한 성공**이 되어 RC2 를 다른 문으로 되살린다.

## A-6. 최소 출하 세트 (한 배)
1. `claim_call_order()` 신설 + 클레임 5경로 적용(정렬은 `_approve_returns` **안**에서도)
2. `dispatch_call_order()` 신설 + `confirm`·`dispatch` 적용
3. 부분 실패 = 실패 (4곳)
4. `_claim_guard` `scope` 인자 + 교환 예외 + `return_sendable` 신설
5. 집 배지 first-wins → 부분/전부 집계 (`claim_code` 를 판정축으로, 라벨은 표시축)
6. `return_sendable` 기반 버튼 술어 재작성 (막힌 집도 `disabled`+사유로 **보이게**)
7. 실패가 남은 집은 `확인함` 비활성 (RC5 를 규칙이 아니라 코드로 막는다)
8. 계약 테스트 6종 / 9. DECISIONS.md 두 방향 기록 / 0. 운영 복구(사용자 승인)

## A-7. 2차 배 (이번 제외, 근거 포함)
- 실패 라인 `return` 축 기록 — `last_error` 가 이미 사유를 담는다(진단 편의).
- `_member_rows:3340` 라인별 클레임 칸 — 배지 수정만으로 오판이 끊긴다.
- `clear_failure` 라인 단위화 — 1차는 버튼 비활성으로 버틴다.
- `dock.py:833` ERP 상세 도크의 first-wins — 폭발 반경 밖.

## A-8. 잔여 리스크 (순위)
1. `is_return_pending` 이 판매자센터 **수동 처리분**을 못 본다(우리 표식으로만 멱등 판정,
   `:1002-1004`). 화면 카운트를 `return_sendable` 로 방어해도 표시상 과대/과소는 남는다.
2. 교환 예외는 운영 표본 0이라 **테스트로만** 검증된다 → 안전측(막는 쪽)으로 둔다.
3. 다중 본품 집에 반품이 걸린 실측 표본이 없다 — 평면 정렬은 논증으로만 안전하다.
4. **`productClass` 가 없는 옛 원본 집은 전부 본품 판정** → 정렬이 무의미해지고 `id.asc` 로
   되돌아간다. 백필 이전 집에서 이 수정은 작동하지 않는다.
5. `if failures: raise` 전환으로 실패 띠가 늘어난다 → 7번(확인함 비활성)이 같은 배에 있어야
   담당자가 습관적으로 증거를 지우지 않는다.
