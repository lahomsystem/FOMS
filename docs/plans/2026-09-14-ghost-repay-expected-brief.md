# 유령 주문 띠 '재결제 예정' 상태 — 워커 브리프 (초안, CEO 가 고쳐도 된다)

> 2026-09-14 · 사용자 요청: "취소·반품 후 '재결제 예정' state 도 추가해. 김선미(#5158)·이신혜(#5136)는
> 각각 취소·반품 후 재결제 예정인 상태다."

## 1. 무엇이 문제인가 (실화면 근거)

운영 워크벤치 `네이버 결제가 전부 취소된 주문` 띠에 두 행이 떠 있다.

| 주문 | 클레임 | 진행 | 재결제 짝 | 할 일 |
|---|---|---|---|---|
| #5158 김선미 3,067,000원 | 취소 완료 (14건 전부) | 실측 · 실측 전 09-30 예정 | **없음** | 휴지통으로 보내기 |
| #5136 이신혜 1,369,000원 | 반품 완료 (5건 전부) | 실측 · 실측 후 09-10 | **없음** | 휴지통으로 보내기 |

둘 다 **재결제 예정**이다. 그런데 화면은 "재결제 짝 없음 → 접어라"라고만 말한다.
`find_repay_candidate_links` 는 **이미 네이버 큐에 들어온 집**만 짝으로 찾으므로, 아직 결제가
안 들어온 건은 구조적으로 `없음` 이다. 시스템이 알 수 없는 사실이라 **사람이 표시**해야 한다.

지금 상태로 두면 담당자가 두 행을 매일 보면서 "접지도 못하고 치우지도 못하는" 채로 남고,
언젠가 실수로 접으면 재결제가 들어왔을 때 붙일 주문이 휴지통에 있다.

## 2. 사용자가 정한 정책 (2026-09-14, 확정)

1. **표시하면 휴지통 버튼을 잠근다.** 버튼 자리는 `재결제 기다림` 표시로 바뀐다. 표시를 풀면 다시 열린다.
2. **자동 해제 + 수동 해제 둘 다.** 재결제가 실제로 그 주문에 붙으면 표시가 저절로 사라지고, 사람이 직접 풀 수도 있다.
3. **이 화면을 쓰는 사람 모두** 표시·해제할 수 있다(ADMIN·MANAGER·STAFF). 되돌릴 수 있는 표시라 휴지통보다 문턱을 낮게 둔다.

## 3. 계약 초안 (이름은 고정 — 워커가 바꾸지 않는다)

### 3.1 저장 위치

`Order.structured_data["naver_repay_expected"]` = `{"at": "<표시 문자열 %Y-%m-%d %H:%M (KST)>", "by": <user_id:int>, "by_name": "<표시 이름>", "note": "<≤200자>"}`

> **정정 2026-09-14 (CEO)**: `at` 은 ISO8601 이 아니다. 템플릿이 아무 변환 없이 그대로 찍으므로
> ISO naive 로 두면 시각 표시 함수가 그 값을 UTC 로 읽어 9시간이 밀린다. `by_name` 키도 계약이다 —
> 담당자 이름 자리에 로그인 아이디가 뜨지 않게 `User.name` 을 먼저 읽고 없을 때만 아이디로 물러선다.
표시 해제는 **키 삭제**(빈 dict 를 남기지 않는다 — `if sd.get(key)` 한 비트로 읽히게).

JSONB 수정은 저장소 규약을 그대로 따른다: `copy.deepcopy` → 수정 → 재대입 → `flag_modified(order, 'structured_data')` → commit.

### 3.2 `foms/services/integrations/naver_commerce/ghost_orders.py`

```python
REPAY_EXPECTED_SD_KEY = "naver_repay_expected"

def read_repay_expected(order) -> Optional[dict[str, Any]]: ...
    """표시가 있으면 {"at","by","note"} dict, 없으면 None. sd 가 dict 가 아니면 None."""

def set_repay_expected(order, *, actor_user_id: int, note: str = "") -> dict[str, Any]: ...
    """표시를 켠다(제자리 수정 — 커밋은 부르는 쪽). 반환은 저장된 dict."""

def clear_repay_expected(order) -> bool: ...
    """표시를 지운다. 지울 게 있었으면 True(없었으면 False — 호출이 무해하다)."""
```

* `_discard_verdict(bucket, status, *, repay_expected: bool = False)` — `repay_expected` 가 True 면
  `can_discard=False`, `discard_block="재결제 예정으로 표시돼 있습니다 — 결제가 들어오면 저절로 풀립니다"`.
  **순서 규칙**: 살아 있는 결제(`whole=False`)·확정 전(`claim_phase != done`) 문구가 우선이다.
  재결제 표시는 그 둘이 통과한 뒤에만 이유가 된다(사람이 먼저 알아야 할 사실 순서).
* `find_ghost_orders` 의 각 row 와 `judge_order_discard` 의 반환에 `"repay_expected": dict | None` 추가.
* 표시가 있어도 **모집단에서 빼지 않는다**(사용자 결정 ①: 숨기지 않는다).

### 3.3 라우트 — `foms/web/admin/naver_ingest.py`

```
POST /admin/naver-ingest/ghost/<int:order_id>/repay-expected
body {"expected": true|false, "note": "<선택, ≤200자>"}
200  {"success": true, "data": {"order_id": N, "repay_expected": {...}|null}, "error": null}
```

* 게이트: `is_naver_workbench_enabled` (403), 권한 `["ADMIN","MANAGER","STAFF"]`.
* **켤 때만 띠에 뜬 주문으로 제한한다** — 기존 discard 라우트와 같은 규율(`find_ghost_orders` 로 다시 판정해 목록 밖이면 400).
  **정정 2026-09-14 (CEO)**: 푸는 요청(`expected=false`)에는 그 관문을 걸지 않는다. 파싱을 `find_ghost_orders`
  호출보다 앞에 두고 `if expected:` 일 때만 모집단을 본다. 표시가 켜진 주문이 붙이기 없이 모집단을 벗어나면
  (클레임 거부·철회로 전부 취소가 아니게 되는 등) 띠에서 행이 사라지고 pane 버튼은 400 이라 수동 해제 길이
  없어져 §2-2(자동 해제 + 수동 해제 둘 다)를 못 지킨다. 해제는 파괴적이지 않다.
* 클레임 확정 전(`claim_phase != "done"`)이어도 **표시는 허용한다**(표시는 파괴적이지 않고, 확정 전 건이야말로 재결제 예정이 흔하다).
* 감사: `log_access(..., session.get("user_id"), action="NAVER_INGEST_GHOST_REPAY_EXPECTED", ...)`.
  **`user_id` 를 반드시 넘긴다** — 이 파일은 소스 스캔 계약이 행위자 누락을 red 로 잡는다.
  `detail` 에 `{"order_id", "expected": bool, "note"}`.

### 3.4 자동 해제

`foms/services/integrations/naver_commerce/repay_reconcile.py` 의 `run_reconcile` **승계 경로**
(`attach_link_to_order` 성공 뒤, 파일 끝 `return` 직전)에서 `clear_repay_expected(order)` 를 부른다.
같은 트랜잭션 안이다(호출자가 commit). 지울 게 없으면 아무 일도 안 한다.

### 3.5 화면

`templates/admin/naver_workbench.html` 띠 행(현재 `can_discard` 분기):

* `row.repay_expected` 가 있으면 **할 일 칸**은 휴지통 버튼 대신
  `<span class="wb-ghost__repay">재결제 기다림</span>` + 표시 푸는 버튼
  (`id="wb-ghost-repay-expected"`, `data-order-id`, `data-expected="0"`) + 언제·누가 표시했는지 한 줄.
* 표시가 없고 `row.can_discard` 면 기존 휴지통 버튼 **옆에** 표시 버튼
  (`id="wb-ghost-repay-expected"`, `data-order-id`, `data-expected="1"`).
* `templates/admin/partials/naver_workbench_pane.html` 의 `ghost_discard` 블록도 같은 규칙(값 이름만 `ghost_discard.repay_expected`).

`static/js/admin/naver-workbench.js`: 핸들러 맵에 `'wb-ghost-repay-expected': submitGhostRepayExpected` 추가.
표시 켤 때는 `window.prompt` 로 메모 한 줄(빈 값 허용), 끌 때는 `window.confirm` 1회. 성공 뒤 `softRefresh()`.

`static/css/admin/naver-workbench.css`: `.wb-ghost__repay` (경고색 계열, `.wb-ghost__claim` 이웃에 둔다).

**자산 핀**: `?v=20260911a` → `?v=20260914a` (CSS·JS 둘 다, 템플릿 2줄).

## 4. 파일 소유권 표 (작업 2 §3 의 통합표가 정본 — 아래는 작업 1 만 있을 때의 초안)

| 워커 | 편집 허용 파일 |
|---|---|
| **W1 판정** | `foms/services/integrations/naver_commerce/ghost_orders.py`, `foms/services/integrations/naver_commerce/repay_reconcile.py` |
| **W2 라우트** | `foms/web/admin/naver_ingest.py` |
| **W3 화면** | `templates/admin/naver_workbench.html`, `templates/admin/partials/naver_workbench_pane.html`, `static/js/admin/naver-workbench.js`, `static/css/admin/naver-workbench.css` |
| **W4 테스트** | `tests/services/integrations/test_naver_ghost_repay_expected.py`(신규), 그리고 핀 문자열만 고치는 7개 파일: `test_naver_backfill_route.py`, `test_naver_fulfillment_err_at.py`, `test_naver_origin_cleanup.py`, `test_naver_partial_claim_ui.py`, `test_naver_post_action_refresh.py`, `test_naver_repay_followup.py`, `test_naver_workbench_async_result.py` |

W4 의 7개 파일에서 고치는 것은 `?v=20260911a` → `?v=20260914a` **그 한 리터럴뿐**이다.
`grep -rn "20260911a" tests/` 결과가 곧 그 목록이다(2026-09-14 기준 7건).

## 5. 검증 명령

```bash
python -m pytest -q tests/services/integrations/test_naver_ghost_repay_expected.py
python -m pytest -q tests/services/integrations -k "ghost or workbench or repay or pin"
python -m pytest -q tests/services/integrations tests/domains tests/contracts tests/harness
python -c "import app; print('APP_OK')"
node --check static/js/admin/naver-workbench.js
```

## 6. 함정

1. **인라인 스타일 금지** — 새 색·여백은 `naver-workbench.css` 에. ratchet 테스트가 강제한다.
2. **jQuery 금지**, `fetch` 는 이 파일의 `postJson` 헬퍼를 쓴다(`data.success` 검증 포함).
3. **핀을 올리면 테스트 7곳이 red** 가 된다 — W4 소유. W3 은 템플릿 2줄만 고친다.
4. `log_access` 에 `user_id` 누락 금지(소스 스캔 계약이 red).
5. `structured_data` 수정은 deepcopy → 재대입 → `flag_modified` 없이는 저장되지 않는다.
6. 문구에 한자를 쓰지 않는다. 화면 문구는 담당자가 읽는 말로.
7. 워커는 git 명령을 쓰지 않는다(커밋·푸시는 총괄 몫). CRLF 를 보존한다.
8. 테스트는 docs 를 읽지 않는다(문서 문구를 단언하는 테스트 금지).

---

# 작업 2 — 일부 반품 집도 **나머지는 발송**되게 (같은 워크플로)

> 2026-09-14 사용자 요청: "이지학은 소비자 주문 잘못으로 일부 반품 건이 있는데, 네이버에서
> 나머지 발송 처리 가능하니 발송 가능하게 만들어."

## 1. 지금 무엇이 막는가 (실화면 근거)

운영 `#5245 이지학` / 네이버 주문 `2026091065471311` — 이력 탭이 말하는 사실:

* `발주확인 완료 5/5` · `발송 안 함` · 발송기한 10-02
* `일부 취소 09-10` — 구매 의사 취소 · 환불 완료

그런데 벌크 발송 띠는 `보낼 수 없음 — 취소·반품·교환이 걸린 주문입니다` 로 **집 전체**를 막는다.
네이버 판매자센터에서는 남은 상품주문 발송이 가능한데, 우리 화면에서만 영영 못 보낸다.

원인은 두 곳의 **집 단위 클레임 가드**다:

* `bulk_dispatch._blocking_reason` ([bulk_dispatch.py:348-355]) — 링크 하나라도
  `blocks_irreversible` 이면 집 전체에 사유를 낸다. 예외는 **우리가 일부 선택 취소한 행**
  (`is_partial_canceled`)뿐이라, **구매자가 네이버에서 직접 낸 부분 클레임**은 그대로 집을 잠근다.
* `fulfillment.dispatch_order` ([fulfillment.py:1129-1131]) — `_claim_guard` scope 에서 빼는 것도
  `is_partial_canceled` 행뿐이다.

즉 2026-09-11 NVCLAIM-PARTIAL-01 이 **우리가 취소한 행**에는 라인 스코프를 열어 뒀고, **구매자가
취소한 행**에는 안 열어 둔 상태다. 이 작업은 그 비대칭을 없앤다.

## 2. 계약 초안 (이름 고정)

### 2.1 `foms/services/integrations/naver_commerce/fulfillment.py`

```python
def claim_blocked_rows(links: list[ExternalOrderLink]) -> list[ExternalOrderLink]: ...
    """`blocks_irreversible` 클레임이 걸린 행 — 발송 대상에서 빼는 목록(판정 SSOT)."""
```

`dispatch_order` 변경:

* `claimed = claim_blocked_rows(links)` 를 구하고, `_claim_guard` 의 `scope` 에서 `partial` **과** `claimed` 를 뺀다.
* `todo` 에서도 `claimed` 를 뺀다(`excluded` 와 같은 자리).
* **남는 게 하나도 없으면**(`claimed` 가 곧 전체) 지금과 같은 문구로 `FulfillmentError` —
  `"취소·반품·교환이 걸린 상품주문뿐입니다 — 판매자센터에서 처리하세요."`
* 발주확인 선행 검사(`not_confirmed`)도 `claimed` 를 뺀 나머지만 본다 — 클레임 행은 발주확인이 영영 안 된다(부분 취소 행과 같은 이유).
* 반환 `skipped` 에 클레임 제외 건을 `reason="클레임"` 으로 싣는다(화면이 몇 건을 뺐는지 말할 수 있게).

**절대 규칙**: 클레임이 걸린 상품주문 id 는 네이버 호출 payload 에 **한 건도** 들어가지 않는다.
이 작업의 안전 전부가 이 한 줄이다. 테스트는 payload 를 직접 열어 확인한다.

### 2.2 `foms/services/integrations/naver_commerce/bulk_dispatch.py`

`_blocking_reason(links)`:

* 클레임 판정을 `claim_blocked_rows` 로 바꾸고, **전부 클레임일 때만** 사유를 낸다.
* 나머지 검사(취소 표식·취소 실패 잔존·수집 상태·발주확인 선행)는 **클레임 행을 뺀 목록**으로 본다.
* 집 단위 취소 표식(`cancel_locks_household_state`)·취소 **실패 잔존**은 지금 그대로 집을 잠근다(NVCLAIM-PARTIAL-01 결정 5 불변).

행 뷰에 `claim_excluded: int`(제외된 상품주문 수)를 추가한다. 후보 수 계산(`eligible`)은 제외 뒤 남은 건으로 센다.

### 2.3 화면

`templates/admin/naver_workbench.html` 벌크 발송 행([:479-512]):

* `row.eligible` 인데 `row.claim_excluded > 0` 이면 `보낼 수 있음` 아래 한 줄:
  `클레임 {{ row.claim_excluded }}건은 빼고 보냅니다`.
* `보낼 상품주문 N건` 문구의 N 은 **빼고 남은 수**다(모달 재진술과 같은 수여야 한다).

## 3. 파일 소유권 (작업 1·2 통합)

| 워커 | 편집 허용 파일 |
|---|---|
| **W1** | `ghost_orders.py`, `repay_reconcile.py` |
| **W2** | `foms/web/admin/naver_ingest.py` |
| **W3** | `fulfillment.py`, `bulk_dispatch.py` |
| **W4** | `templates/admin/naver_workbench.html`, `templates/admin/partials/naver_workbench_pane.html`, `static/js/admin/naver-workbench.js`, `static/css/admin/naver-workbench.css` |
| **W5** | 테스트 전부 — 신규 `tests/services/integrations/test_naver_ghost_repay_expected.py`·`test_naver_partial_claim_dispatch.py`, 그리고 핀 리터럴 7개 파일 |

## 4. 검증 명령 (작업 2)

```bash
python -m pytest -q tests/services/integrations/test_naver_partial_claim_dispatch.py
python -m pytest -q tests/services/integrations -k "dispatch or bulk or claim"
```

## 5. 함정 (작업 2)

1. **불가역 경로다.** 발송처리는 구매자에게 '배송 시작'으로 보이고 정산 시계를 돌린다. 제외 판정이 틀리면 클레임 건이 나간다 — 음성 대조군(집 전부 클레임 → 여전히 차단) 테스트를 반드시 둔다.
2. `_mark_failures` 는 **막힌 건에만** 찍는다(형제까지 빨갛게 만들지 않는다) — 기존 규율 유지.
3. `close_now`(추가결제 집) 판정은 `all()` 이다 — 클레임 행을 뺀 목록으로 다시 세면 의미가 바뀐다. **`close_now` 는 집 전체로 계속 센다.**
4. 화면 건수와 모달 재진술 건수는 같은 함수에서 나와야 한다(`is_dispatch_pending` 술어 한 벌).

---

# 6. 확정 계약 정정 — 소유권 표와 인벤토리 (2026-09-14 CEO)

## 6.1 소유권 표에 빠져 있던 파일 4개

계약 §3 의 소유권 표는 사실과 달랐다. 아래 4개는 **전부 게이트가 요구한 정당한 변경**인데
표에 없었다. 커밋 범위를 표대로 좁게 잡으면 `test_admin_audit_screen_readability_3` ·
`test_auth_enforcement` · `test_write_guard` · `test_failopen_inventory` 가 red 다.

| 워커 | 추가되는 파일 | 왜 |
|---|---|---|
| **W2** | `foms/services/audit_message_display.py` | 새 감사 action 의 화면 문구 등재 |
| **W2** | `docs/harness/foms_write_guard_manifest.json` | 새 POST 라우트 등재 |
| **W2** | `docs/harness/foms_order_mutation_policy_manifest.json` | 새 쓰기 경로 등재 |
| **W2** | `docs/harness/foms_failopen_inventory.json` | 항목이 lineno 를 들고 있어 라우트 삽입만으로 드리프트 |

## 6.2 §0-4 정정

계약 §0-4 의 "`foms_failopen_inventory.json` 은 **아무도 안 만진다**" 는 틀렸다. 이 인벤토리는
**항목이 lineno 를 들고 있어** 같은 파일에 라우트를 끼워 넣는 것만으로 뒤 항목의 줄 번호가
밀려 드리프트한다 — 새 broad except 가 0 건이어도 **재생성이 필요하다**.

## 6.3 다음 packet 부터의 규칙

> **새 POST 라우트 1개 = 인벤토리 5종 재생성.**
> `order_mutation_writer` · `audit_coverage` · `write_guard` · `order_mutation_policy` · `failopen`.

라우트를 붙이는 워커의 소유권에 이 5개 파일을 처음부터 넣는다. 총괄 몫으로 미루면 워커가
녹색을 보고했는데 총괄 게이트에서 red 가 나는 자리가 된다.

## 6.4 커밋

이번 packet 은 변경 파일 전부를 **한 커밋**에 넣는다(pathspec 으로 명시). 인벤토리·문구
등재가 코드와 갈라져 들어가면 두 커밋 사이의 트리가 red 다.
