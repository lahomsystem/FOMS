# 네이버 이력 탭 상태 칸 — 데이터 계약 (동결본)

- **작성**: 2026-08-30 / **마지막 갱신**: 2026-08-30 (수정 라운드 — 구현 결과에 맞춰 재동결)
- **상태**: 구현 완료 후 **코드에 맞춰 갱신됨**. 이 문서와 코드가 갈리면 **코드가 정본**이고,
  갈린 자리는 §10.1 에 근거와 함께 등재한다. 갱신 근거는 실제 `git diff` 와 소스 독해다.
- **상위 문서**: `docs/plans/2026-08-30-naver-history-status-column-ledger.md` (왜 고치나 · 진행 원장)
- **어휘 정본**: `docs/design/mockups/naver-triage-status-column--table.html` (화면에 찍히는 낱말은 이 파일이 최종)
- **대상**: `/admin/naver-ingest/triage?tab=all` 이력 탭 · ADMIN 전용 · 읽기 전용 표
- **작업 트리**: `C:/tmp/foms-naver-status` (레인 전부 이 트리 하나를 공유한다)

## 0. 이 문서의 지위

뒤에 오는 4개 레인(A 서버 · B CSS · C 템플릿 · D 테스트)이 **이 문서만 보고 병렬로** 코딩한다.
여기 적힌 이름은 **동결**이다. 필드 이름·CSS 클래스 이름·칩 질의 파라미터를 레인이 임의로 바꾸면
템플릿이 없는 필드를 읽고(조용히 빈 칸) CSS 가 없는 클래스를 칠한다(조용히 무스타일) —
둘 다 테스트가 안 잡는 종류의 실패다.

이름을 바꿔야 할 근거가 나오면 **코드를 고치기 전에 이 문서를 먼저 고치고** 네 레인에 알린다.

---

## 1. 레인 전부에 걸리는 불변 규칙

1. **네이버 API 호출 0건.** 표시값은 이미 저장된 컬럼 · `raw_snapshot` · `triage_state` 에서만 나온다.
2. **이력 행에 mutation 을 붙이지 않는다**(절대 규칙 3). `<button>` · `data-link-id` · `class="btn` 금지.
   평범한 링크(`<a href>`, GET)만 허용. 이미 계약 테스트 3개가 이것을 문다
   (`test_naver_workbench.py::test_history_rows_carry_no_actions_at_all`,
   `test_naver_workbench_v3_contract.py::test_history_rows_are_read_only`,
   `test_naver_workbench.py::test_history_locked_row_says_why_instead_of_an_action`).
3. **숫자는 전부 집(묶음) 단위.** 링크 행으로 세면 부분이 전체보다 커 보인다(2026-08-19 실화면 사고).
   집 키는 `_history_group_key` / `grouping.group_key_expression()` 한 벌뿐이다.
4. **추가 쿼리 0.** 새 행 필드는 `_link_rows()` 가 **이미 읽은** 링크·주문으로만 만든다.
   `origin_facts` · `find_ghost_orders` · `find_order_candidates` 는 행마다 한 번씩 도는 함수라 이력 표에서 부르지 않는다(§8).
5. **인라인 스타일 금지.** 색·간격은 전부 `static/css/admin/naver-workbench.css` 의 클래스로 간다.
6. **새 마크업에 `id` 속성을 두지 않는다.** `test_naver_workbench_v3_contract.py` 가 문서 안 `id="wb-*"` 중복을 금지한다.
   상태 칸은 행마다 반복되므로 `id` 를 하나라도 넣으면 그 즉시 중복이다. 클래스만 쓴다.

---

## 2. `_link_rows()` 가 새로 싣는 필드

`foms/web/admin/naver_ingest.py::_link_rows()` (284행~) 는 지금 **멤버(링크) dict** 를 만들고
그것을 접어 **집(그룹) dict** 를 만든다. 두 층 모두에 필드를 더한다.

### 2.1 멤버(링크) dict 에 더하는 것 — 집계의 원재료

멤버는 화면이 직접 읽지 않는다(펼침 목록만 읽는다). 집계를 위해 링크마다 한 번씩 뽑아 둔다.

구현 함수는 `_history_member_axes(link, summary)` 다(멤버 dict 조립에서 한 번 부른다).

| 이름 | 모양 | 출처 | 예시 |
|---|---|---|---|
| `relation` | `str` | `(link.relation or "").strip().upper()` | `"ADDON"` |
| `claim_phase` | `str` | `mapping.extract_claim(link.raw_snapshot or {})["phase"]` | `"in_progress"` |
| `claim_kind` | `str` | 같은 dict 의 `claim_kind(claim)` (`mapping.claim_kind`) | `"RETURN"` |
| `claim_reason` | `str` | `mapping.claim_reason_text(claim["reason"])` — **코드 라벨**이다(고객이 쓴 원문 `detailed_reason` 이 아니다) | `"단순 변심"` |
| `claim_done_at` | `str` | 반품 축 `return_completed_at` (KST `YYYY-MM-DD HH:MM`) | `"2026-08-26 09:00"` |
| `claim_refund_expected_at` | `str` | 반품 축 `refund_expected_at` — 단, `refund_expected_pending` 이 참일 때만. 아니면 `""` | `"2026-08-30 00:00"` |
| `claim_collect_done_at` | `str` | 반품 축 `collect_completed_at` | `"2026-08-25 09:00"` |
| `claim_refund_done` | `bool` | 반품 축 `refund_done` | `True` |
| `shipping_due` | `str` (`YYYY-MM-DD` 또는 `""`) | `summary["shipping_due"]` (= `extract_place_status(...)["shipping_due"][:10]`) | `"2026-09-02"` |
| `dispatch` | `dict` | `_dispatch_view(link)` 결과 그대로 | `{"ours_at": "2026-08-27 16:02", "naver_at": "", "mismatch": True, …}` |
| `fulfillment` | `dict` | `(link.triage_state or {}).get("fulfillment") or {}` | `{"last_error": "…", "last_error_action": "dispatch", …}` |

> **한 링크에서 함께 뽑는다.** `claim_label`(이미 있음)·`claim_phase`·`claim_kind`·`claim_reason` 과
> 반품 축 네 값은 **같은 링크의 같은 `extract_claim` 결과**여야 한다. 라벨은 A 링크에서, 단계는
> B 링크에서 뽑으면 화면이 "취소 요청"이라 적으면서 "확정됨"으로 칠한다.
>
> `extract_claim` 은 `summarize_snapshot` 안에서 이미 한 번 돈다. 여기서 한 번 더 부르는 것은
> **순수 파이썬 파싱**이라 쿼리가 0이고, 대신 여러 화면이 공유하는 `summarize_snapshot` 을
> 건드리지 않는다(레인 격리가 목적).

> **반품 축(`_return_axis_view`)은 `summary["claim_label"]` 이 있는 링크에만 판다.** 클레임이 없는
> 링크는 모듈 상수 `_EMPTY_RETURN_AXIS`(빈 값 5개)를 그대로 쓴다 — 링크마다 부르면 쪽당 50집 ×
> 멤버 수만큼 빈 값을 만드는 헛일이 붙는다(2026-08-30 CEO 지적 3). 게이트로 쓰는 술어가
> `_history_claim()` 의 멤버 선택 술어(`claim_label`)와 **같은 값**이라, 라벨을 준 멤버는 반드시
> 축도 갖는다(둘이 갈리면 라벨만 있고 날짜가 없는 집이 생긴다).

### 2.2 집(그룹) dict 에 더하는 것 — 템플릿이 읽는 것

구현 함수는 `_history_group_axes(group, lead=…, ordered=…, statuses=…)` 다. **재료와 판정 결과를
함께** 싣는다 — 판정(`*_state`·`*_text`·`claim_*_text`)은 서버가 끝내고 템플릿은 **상태 키 → CSS
클래스 대응만** 한다(2026-08-30 CEO 지적: 판정표가 템플릿 `{% set %}` 사슬에 있으면 HTML 문자열
매칭 말고는 시험할 방법이 없고, 같은 부품이 처리 탭·도크에 실릴 때 판정이 두 벌이 된다).

| 이름 | 모양 | 출처 · 규칙 | 예시 |
|---|---|---|---|
| `foms_state` | `str` — `"failed"`\|`"review"`\|`"closed"`\|`"linked"`\|`"collected"` | 아래 §2.3-A 판정표 | `"linked"` |
| `foms_label` | `str` | `HISTORY_FOMS_LABELS[foms_state]` — **서버가 실어** 준다(템플릿이 dict 를 다시 뒤지지 않는다) | `"주문 만듦"` |
| `relation` | `str` — `"NEW"`\|`"ADDON"`\|`"REPAY"` | 멤버 중 `ADDON` 이 하나라도 있으면 `ADDON`, 없고 `REPAY` 가 있으면 `REPAY`, 아니면 `NEW`. `_group_queue` 의 우선순위와 **같다** | `"ADDON"` |
| `relation_label` | `str` | `HISTORY_RELATION_LABELS[relation]` | `"추가결제"` |
| `related_order_id` | `Optional[int]` | **`relation` 을 정한 바로 그 멤버**의 `order_id`(관계 멤버 중 주문이 붙은 첫 건). 관계 멤버 전부 미생성이면 `None` | `4362` |
| `place_done_count` | `int` | 멤버 중 `place_confirmed` 가 참인 수 (`_place_view(link)["confirmed"]` 와 같은 값) | `2` |
| `place_total` | `int` | `len(group)` | `3` |
| `place_state` | `str` — `"done"`\|`"now"`\|`"bad"` | §2.3-B 판정표 (`_history_place_step`) | `"now"` |
| `place_text` | `str` | 같은 판정표의 화면 낱말 | `"발주확인 2/3"` |
| `dispatch_done_count` | `int` | 멤버 중 `bool(dispatch["ours_at"] or dispatch["naver_at"])` 인 수 | `1` |
| `dispatch_total` | `int` | `len(group)` (= `place_total`) | `2` |
| `dispatch_ours_at` | `str` | 멤버 `dispatch["ours_at"]` 중 빈 값이 아닌 것의 **최솟값**(= 가장 이른 시각). 없으면 `""` | `"2026-08-27 16:02"` |
| `dispatch_naver_at` | `str` | 멤버 `dispatch["naver_at"]` 중 빈 값이 아닌 것의 **최솟값**. 없으면 `""` | `"2026-08-28 12:03"` |
| `dispatch_mismatch` | `bool` | 멤버 중 `dispatch["mismatch"]` 가 참인 것이 하나라도 있는가 (우리만 보내고 네이버가 침묵) | `True` |
| `dispatch_mismatch_ours_at` | `str` | **어긋난 멤버들의** `ours_at` 중 최솟값. 경고 줄이 쓰는 **유일한** 시각이다 — §3.2-경고 | `"2026-08-27 16:02"` |
| `dispatch_moot` | `bool` | 발송이 0건인데 클레임이 걸려 더 안 나가는 집 — §2.3-C | `True` |
| `dispatch_state` | `str` — `"done"`\|`"now"`\|`"skip"`\|`"bad"`\|`"todo"` | §2.3-C 판정표 (`_history_dispatch_step`) | `"now"` |
| `dispatch_text` | `str` | 같은 판정표의 화면 낱말 | `"발송처리 1/2"` |
| `naver_skipped` | `bool` | 네이버 축에 말할 것이 아예 없는 집(파이프 대신 한 칸) — §2.3-D | `True` |
| `fail` | `dict` | `{"action","action_label","reason","at"}` — §2.3-E. 실패가 없으면 네 값 모두 `""` | `{"action": "dispatch", "action_label": "발송처리", "reason": "배송방법 코드 거부", "at": "2026-08-27 11:20"}` |
| `claim_label` | `str` | `claim_label` 이 있는 **첫 멤버**(표시 순서)의 라벨. 기존 필드와 같은 이름·같은 값 | `"반품 완료"` |
| `claim_phase` | `str` | 그 **같은 멤버**의 `claim_phase`. 라벨이 없으면 `""` | `"requested"` |
| `claim_badge_text` | `str` | §3.3 — 배지에 찍는 문자열(라벨 + `· 확정 전` 또는 확정 날짜) | `"반품 완료 08-26"` |
| `claim_tail_text` | `str` | §3.3 — 배지 뒤 작은 글자(사유·수거·환불 조각을 ` · ` 로 이은 것). 조각이 없으면 `""` | `"수거 완료 08-25 · 환불 완료"` |
| `shipping_due` | `str` (`YYYY-MM-DD`\|`""`) | 멤버 `shipping_due` 중 빈 값이 아닌 것의 **최솟값(가장 이른 기한)**. `_group_queue` 는 `next()`(첫 값)를 쓰는데 이력은 **가장 이른 값**이다 | `"2026-09-02"` |
| `shipping_due_text` | `str` (`MM-DD`\|`""`) | `date.fromisoformat(shipping_due).strftime("%m-%d")`. **못 읽으면 빈 문자열**(원문은 `shipping_due` 에만 남는다) | `"09-02"` |
| `shipping_due_over_days` | `int` | `(get_today_kst() - date(shipping_due)).days`, 음수면 `0`. `shipping_due` 가 없거나 못 읽으면 `0` | `2` |

> **`related_order_id` 는 대표(lead)가 아니라 관계를 정한 그 멤버에서 나온다.** 대표는 금액 최대
> 링크라, 형제 일부만 `ADDON` 인 섞인 집에서는 `NEW` 형제일 수 있다. 그러면 화면이
> `추가결제 → #(엉뚱한 주문번호)` 를 찍는데 사람이 눌러서 실제로 들어가는 번호다(2026-08-30 CEO
> 지적 2). §2.1 이 클레임 축에 적어 둔 "라벨은 A 링크, 단계는 B 링크" 금지와 같은 규율이다.
> 관계 멤버에 주문이 하나도 없으면 `None` 이고, 그때 화면은 **화살표와 번호를 아예 내지 않는다**
> (배지 낱말만 — §3.1).

> **`shipping_due` 는 한 번만 판다.** 예전 초안은 초과일수만 `try` 로 감싸고 표시값은 무방비
> 슬라이스(`due[5:]`)라 `due="20260902"` 같은 값에서 화면에 `발송기한 902` 가 찍혔다. 못 읽으면
> 표시값도 빈 값이다 — "못 읽는 값"을 "지났다"고 단정하지 않겠다는 의도가 옆 필드에서 새면 안 된다.

**기존 필드는 이름·뜻을 바꾸지 않는다.** `place_pending` · `claim_label` · `claim_blocking` ·
`sync_status` · `statuses` · `failure_reason` · `count` · `pending_link_id` 는 그대로 남는다
(`place_pending == (place_done_count < place_total)` 이 항상 참이어야 한다 — 레인 D 가 못 박는다).

> **`relation` 의 빈 문자열 규약이 다르다.** 처리 탭 집(`_group_queue`)의 `relation` 은 신규를 `""` 로 준다.
> **이력 집은 항상 세 값 중 하나**다(신규는 `"NEW"`). 화면이 `신규 결제` 배지를 찍어야 하기 때문이다.
> 두 dict 는 서로 다른 함수가 만드는 다른 물건이다 — 한쪽 규약을 다른 쪽에 옮기지 마라.

### 2.3 파생 규칙 상세

아래 판정표는 전부 **파이썬 함수 한 개씩**으로 구현한다(템플릿 `{% set %}` 사슬 금지):
`_history_foms_state` · `_history_place_step` · `_history_dispatch_step` · `_history_naver_axis` ·
`_history_fail` · `_history_claim` · `_history_claim_text` · `_history_shipping_due` ·
`_history_relation`. 파이프 두 칸의 재료·판정은 `_history_pipe_fields` 가 한 벌로 묶어 낸다.

`claim_kind` 는 **집 dict 에 싣지 않는다.** §2.3-D 판정 안에서만 쓰는 중간값이라, 행에 실으면
아무도 안 읽는 값이 되고 다음 사람이 "화면에 이미 있다"고 오독한다(같은 이유로 클레임 원재료
`claim_reason`·시각 3종도 멤버 dict 에만 있고 집 dict 에는 없다 — 집이 내는 것은 §3.3 의 두
문자열뿐이다).

#### A. `foms_state` 판정표 (위에서부터 먼저 맞는 것)

| 순서 | 조건 | 값 | 화면 낱말 |
|---|---|---|---|
| 1 | `"FAILED" in statuses` | `failed` | `받기 실패` |
| 2 | `"PENDING_REVIEW" in statuses` | `review` | `확인 필요` |
| 3 | `order_id` 있고, 그 `Order` 가 없거나 `status == "DELETED"` 이거나 `deleted_at` 이 있다 | `closed` | `주문 접음` |
| 4 | `order_id` 있음 | `linked` | `주문 만듦` |
| 5 | 그 밖 | `collected` | `받아옴` |

`Order` 는 `_link_rows()` 가 이미 `orders` dict 로 들고 있다(`lead["_order"]`) — **추가 쿼리 0**.
지금 그 조회는 soft delete 를 안 거르므로 삭제된 주문도 객체로 잡힌다. 3번 판정이 그 자리다.

`status`·`deleted_at` 은 `models.Order` 의 **실제 컬럼**이라 `getattr(order, "status", "")` 같은
기본값 방어를 두지 않는다 — 기본값은 영영 안 쓰이고, 컬럼 이름이 바뀌면 예외 대신 조용히
`linked` 로 떨어진다(2026-08-30 CEO 지적). 없을 수 있는 것은 주문 객체 자체뿐이라 `order is None`
가드만 남긴다.

#### B. 발주확인 칸(파이프 1번) 상태 — 위에서부터 먼저 맞는 것

| 순서 | 조건 | 상태 키 | 화면 낱말 |
|---|---|---|---|
| 1 | `fail["action"] == "confirm"` | `bad` | `발주확인 실패` |
| 2 | `place_total > 1` 이고 `place_done_count == place_total` | `done` | `발주확인 완료 N/M` |
| 3 | `place_done_count == place_total` | `done` | `발주확인 완료` |
| 4 | `place_done_count > 0` | `now` | `발주확인 N/M` |
| 5 | 그 밖(`place_done_count == 0`) | `now` | `발주확인 할 차례` |

#### C. 발송 칸(파이프 2번) 상태 — 위에서부터 먼저 맞는 것

| 순서 | 조건 | 상태 키 | 화면 낱말 |
|---|---|---|---|
| 1 | `fail["action"] == "dispatch"` | `bad` | `발송처리 실패` |
| 2 | `dispatch_mismatch` | `bad` | `네이버 기록 없음` |
| 3 | `dispatch_moot` | `skip` | `발송 안 함` |
| 4 | `dispatch_total > 1` 이고 `dispatch_done_count == dispatch_total` | `done` | `발송처리 완료 N/M` |
| 5 | `dispatch_done_count == dispatch_total` 이고 `> 0` | `done` | `발송처리 완료` |
| 6 | `dispatch_done_count > 0` | `now` | `발송처리 N/M` |
| 7 | `place_done_count == place_total` (발주확인 다 끝남) | `now` | `발송처리 할 차례` |
| 8 | 그 밖 | `todo` | `발송처리` (회색 이름만) |

`dispatch_moot` 정의:

```
dispatch_moot = (dispatch_done_count == 0) and claim_phase in ("requested", "in_progress", "done")
```

취소·반품이 걸린 집은 이제 발송이 안 나간다. `발송처리 할 차례`(주황)로 두면 "지금 해라"라는 뜻이
되어 되돌릴 수 없는 호출을 부른다. 회색 `발송 안 함` 으로 낸다(목업 E12·E19).

#### D. `naver_skipped` — 파이프 대신 `네이버 처리 없음` 한 칸

```
naver_skipped = (place_done_count == 0 and dispatch_done_count == 0 and not fail["action"]) and (
    all(s == "FAILED" for s in statuses)
    or (claim_phase == "done" and claim_kind in ("CANCEL", "RETURN"))
)
```

(`claim_phase`·`claim_kind` 는 `_history_claim()` 이 고른 **그 멤버**의 값이다. `claim_kind` 는
판정 안에서만 쓰고 행에는 안 싣는다 — §2.3 머리말.)

- 수집 자체가 실패한 집(목업 E20) — 네이버에 아무것도 안 했고 앞으로도 안 한다.
- 발주확인·발송 전에 취소가 **확정**된 집(목업 E14).
- 반대로 발주확인·발송이 이미 있었던 집(E13 반품 완료)은 **파이프를 그대로 낸다** — 그 일은 실제로 일어났다.

#### E. `fail` — 실패 축(발주확인·발송처리 공용)

집 안 멤버의 `fulfillment["last_error"]` 중 **비어 있지 않은 첫 값**을 쓴다(멤버 순서 = 대표 먼저).

```
action = (fulfillment.get("last_error_action") or "confirm").strip().lower()
action = action if action in FULFILLMENT_ACTION_LABELS else "confirm"
```

`_failure_rows()` 와 **같은 규칙**이다(옛 기록에 작업이 없으면 `confirm` 으로 본다).

| 키 | 값 |
|---|---|
| `action` | `""` \| `"confirm"` \| `"dispatch"` \| `"cancel"` \| `"return"` |
| `action_label` | `FULFILLMENT_ACTION_LABELS[action]` (`발주확인`/`발송처리`/`취소`/`반품 접수`) |
| `reason` | `last_error` 문장 그대로 |
| `at` | `str(last_error_at)[:16].replace("T", " ")` — `_failure_rows()` 와 같은 형식 |

`action` 이 `cancel`·`return` 이면 파이프는 안 칠하고 **경고 줄**(`.wb-st__warn`)로만 낸다 —
그 실패는 발주확인·발송 축의 사실이 아니다.

### 2.4 표시 상수는 서버에 둔다

칩과 행 배지가 **같은 낱말**을 쓰는 것이 계약이다(목업 주석·계획서 §5). 그래서 낱말은
`foms/web/admin/naver_ingest.py` 모듈 상수로 한 벌만 둔다.

**칩 라벨을 손으로 적지 않는다.** 칩은 `(질의값, FOMS 축 키, 꼬리)` 명세에서 **파생**한다 —
그래야 "모든 칩 라벨은 대응하는 배지 낱말로 시작한다"를 계약 테스트가 물 수 있다
(2026-08-30 CEO 지적 3). 두 벌로 적으면 칩만 `받아옴 · 주문 전`, 배지만 `받아옴` 으로 조용히 갈린다.

```python
#: 이력 탭 FOMS 축 낱말. 칩과 행 배지가 이 dict 하나를 함께 쓴다.
HISTORY_FOMS_LABELS = {
    "collected": "받아옴", "linked": "주문 만듦", "closed": "주문 접음",
    "review": "확인 필요", "failed": "받기 실패",
}

#: 이력 탭 상태 칩 정의 — (질의값, FOMS 축 키, 꼬리). 순서가 곧 화면 순서다.
_HISTORY_STATUS_CHIP_SPECS = (
    ("COLLECTED", "collected", " · 주문 전"),
    ("LINKED", "linked", ""),
    ("PENDING_REVIEW", "review", ""),
    ("FAILED", "failed", ""),
)

#: 이력 탭 상태 칩(화면 순서). (질의값, 화면 낱말) 쌍 — 라벨은 배지 낱말 + 꼬리다.
HISTORY_STATUS_CHIPS = tuple(
    (query, HISTORY_FOMS_LABELS[state] + tail)
    for query, state, tail in _HISTORY_STATUS_CHIP_SPECS
)

#: 관계 축 낱말.
HISTORY_RELATION_LABELS = {"NEW": "신규 결제", "ADDON": "추가결제", "REPAY": "재결제"}
```

`foms_label` · `relation_label` 은 **서버가 행에 실어** 준다(템플릿이 dict 를 다시 뒤지지 않는다).

**칩도 같은 길로 간다.** `_history_view()` 가 컨텍스트에 `"status_chips": HISTORY_STATUS_CHIPS` 를
넣고, 템플릿은 `{% for key, label in history.status_chips %}` 로 **그대로 돈다**. 템플릿이 네 낱말을
두 벌째 적으면 상수는 SSOT 가 아니라 드리프트 감시로 전락한다(계약 테스트가 잡아 주더라도 그건
다른 물건이다 — 2026-08-30 CEO 최종 판정 minor).

칩 8개 중 나머지 넷(`전체`·`발주확인 남음 · 취소 포함`·`발송처리 남음 · 취소 포함`·`추가결제·재결제`)은
FOMS 축 낱말에서 파생되지 않는 자리라 템플릿에 그대로 적는다 — 대응하는 행 배지가 없기 때문이다
(§4.1). 그중 `추가결제·재결제` 는 **처리 탭 칩과 가운뎃점 표기를 맞춘다**(띄어쓰기 없음): 같은 화면에
같은 낱말이 두 표기로 있으면 눈이 다른 것으로 읽는다.

---

## 3. 어휘 표 — 필드가 찍는 낱말 (목업과 1:1)

`X` = 값이 있을 때만 그 줄을 낸다. 없는 줄은 **아예 만들지 않는다**(빈 칸·`–` 로 채우면
"값이 없다"와 "우리가 모른다"가 같은 모양이 된다).

### 3.1 `FOMS` 줄 (항상 낸다)

| 필드 | 값 | 낱말 | 색(톤) |
|---|---|---|---|
| `foms_state` | `collected` | `받아옴` | 파랑 |
| | `linked` | `주문 만듦` | 초록 |
| | `closed` | `주문 접음` | 회색(slate) |
| | `review` | `확인 필요` | 주황 |
| | `failed` | `받기 실패` | 빨강 |
| `relation` | `NEW` | `신규 결제` | 흰 배지(ghost) |
| | `ADDON` | `추가결제 → #{related_order_id}` (번호는 링크) | 보라 |
| | `REPAY` | `재결제 → #{related_order_id}` (번호는 링크) | 보라 |

`관계` 배지의 주문번호는 `order_edit.edit_order` 로 가는 **평범한 링크**다(`target="_blank"` 허용, 버튼 금지).

**`related_order_id` 가 `None` 이면 화살표와 번호를 아예 내지 않는다** — 배지는 `추가결제` ·
`재결제` 낱말만이다. `→ #None` 은 사람이 눌러 볼 수 있는 거짓말이고, 빈 자리로 두면 "번호가 없다"와
"우리가 못 찾았다"가 같은 모양이 된다.

### 3.2 `네이버` 줄 (항상 낸다 — 모양이 둘)

- `naver_skipped` 가 참이면 파이프 대신 **한 칸**: `네이버 처리 없음` (회색 slate 배지).
- 아니면 **2칸 파이프**: [발주확인 칸][발송 칸]. 상태 키 → 낱말은 §2.3-B·C 표.

파이프 오른쪽 부속 문구(`.wb-st__when` 또는 빨강 배지) — 위에서부터 먼저 맞는 것 하나만:

| 순서 | 조건 | 낱말 | 모양 |
|---|---|---|---|
| 1 | `fail["action"] in ("confirm","dispatch")` 이고 `fail["at"]` 있음 | `{fail.at}` | `.wb-st__when` |
| 2 | 발송 칸이 `done` 이고 `dispatch_naver_at` 있고 `dispatch_ours_at` 있음 | `{dispatch_naver_at} · 네이버 확인됨` | `.wb-st__when` |
| 3 | 발송 칸이 `done` 이고 `dispatch_naver_at` 있고 `dispatch_ours_at` 없음 | `{dispatch_naver_at} · 판매자센터에서 직접` | `.wb-st__when` |
| 4 | `shipping_due_over_days > 0` 이고 발송 칸이 `done` 이 아님 | `발송기한 {N}일 지남` | `.wb-st__b--red` 배지 |
| 5 | `shipping_due_text` 있고 발송 칸이 `done` 이 아님 | `발송기한 {MM-DD}` | `.wb-st__when` |

부속 문구는 **파이프를 낼 때만** 온다(`naver_skipped` 인 집은 한 칸만 내고 끝).

> **발송기한 초과에 `네이버 자동 취소 가능` 을 붙이지 않는다.** 그 문장은 초안 구현에 잠깐 들어왔다가
> 빠졌다 — 네이버가 기한 초과 건을 실제로 자동 취소한다는 근거(상수·문서·테스트)가 저장소 어디에도
> 없었다. 운영자가 그 문장을 보고 판매자센터 확인을 건너뛸 수 있는 종류의 주장이라 **증명한 사실만**
> 낸다: 배지 `발송기한 {N}일 지남` 은 남기고 자동 취소 문장은 없앤다(2026-08-30 CEO 최종 판정 minor).

#### 3.2-경고. 파이프 아래 경고 줄 (`.wb-st__warn`) — 있을 때만, 최대 2줄

| 조건 | 낱말 |
|---|---|
| `fail["reason"]` 있음, `fail["action"]` 이 `confirm`\|`dispatch` | `{fail.reason}` |
| `fail["reason"]` 있음, `fail["action"]` 이 `cancel`\|`return` | `{fail.action_label} 실패 · {fail.reason}` |
| `dispatch_mismatch` 이고 `dispatch_mismatch_ours_at` 있음 | `우리 발송 {dispatch_mismatch_ours_at} · 네이버 기록 없음` |
| `dispatch_mismatch` 이고 `dispatch_mismatch_ours_at` 없음 | `네이버 기록 없음` (시각 없이 문장만 — 없는 시각을 지어내지 않는다) |

> **어긋남 경고의 시각은 `dispatch_ours_at` 이 아니라 `dispatch_mismatch_ours_at` 이다.** 집을 접은
> `dispatch_ours_at` 은 최솟값이라, 멤버가 [정상 발송 09:00, 어긋남 16:02] 이면 화면이 **네이버가
> 기록한 09:00** 을 "네이버 기록 없음" 이라 말한다(2026-08-30 CEO 최종 판정 major 1). 되돌릴 수 없는
> 호출의 유실 자리를 가리키는 문장이라 틀린 시각이 특히 나쁘다.

### 3.3 `취소·반품` 줄 (`claim_label` 이 있을 때만)

**목업의 날짜·사유를 낸다**(2026-08-30 사람 결정 — CEO 지적 4 의 (a)안). 재료는 이미 순수 파싱으로
나와 있어 추가 쿼리가 0이고, 목업이 이미 승인된 화면이다. 조립은 **서버**(`_history_claim_text`)가
하고 행에는 `claim_badge_text` · `claim_tail_text` 두 문자열만 싣는다 — 템플릿에서 이으면 HTML
문자열 매칭 말고는 시험할 방법이 없다.

**배지** = `claim_label` (`mapping.CLAIM_STATUS_LABELS` 정본) + 아래 꼬리 하나:

| `claim_phase` | 배지 꼬리 | 색(톤) | 예 |
|---|---|---|---|
| `requested` | ` · 확정 전` | 빨강 | `취소 요청 · 확정 전`, `교환 요청 · 확정 전` |
| `in_progress` | ` · 확정 전` | 빨강 | `수거중 · 확정 전` |
| `done` | ` {MM-DD}` — `claim_done_at` 이 있을 때만 | 회색(slate) | `반품 완료 08-26`, `취소 완료` |
| `rejected` | ` {MM-DD}` — `claim_done_at` 이 있을 때만 | 흰 배지(ghost) | `취소 거부` |
| `other` | ` {MM-DD}` — `claim_done_at` 이 있을 때만 | 주황 | `구매확정 보류` |
| `""` (모름) | 같은 규칙 | 회색(slate) | (라벨 원문 그대로) |

**작은 글자**(`.wb-st__when`) = 아래 조각 중 **값이 있는 것만** ` · ` 로 이은 것. 하나도 없으면
`claim_tail_text` 가 빈 문자열이고, 그러면 템플릿은 `.wb-st__when` 을 **아예 만들지 않는다**.

| 순서 | 조각 | 출처 |
|---|---|---|
| 1 | 사유 낱말 (`단순 변심` · `색상·사이즈 변경` …) | `claim_reason` = `mapping.claim_reason_text(claim["reason"])` |
| 2 | `수거 완료 {MM-DD}` | `claim_collect_done_at` |
| 3 | `환불 예정 {MM-DD}` | `claim_refund_expected_at` (= `refund_expected_pending` 일 때만) |
| 4 | `환불 완료` | `claim_refund_done` |

> **확정 날짜는 미확정 건에 붙이지 않는다.** `requested`·`in_progress` 는 `· 확정 전` 이 이긴다 —
> 아직 안 끝난 일에 끝난 날짜를 적는 셈이 된다.
>
> **"끝난 뒤의 환불 예정" 은 내지 않는다.** `refund_expected_at` 은 `refund_expected_pending` 이
> 참일 때만 싣는다(미래형 거짓말 금지).

#### 3.3 에서 목업과 갈리는 자리 (전부 근거 있음)

| 목업 | 실화면 | 왜 |
|---|---|---|
| E12 `반품 수거중 · 확정 전` | `수거중 · 확정 전` | `COLLECTING` 은 반품·교환 양쪽에서 온다. `CLAIM_STATUS_LABELS` 가 일부러 `수거중` 으로 뒀다(교환 건에 "반품"이라 적으면 틀린 말) — **상수가 목업을 이긴다** |
| E14 `취소 완료 08-26` | `취소 완료` | 확정 날짜의 유일한 출처가 네이버 `returnCompletedDate`(반품 축)다. 취소 확정 스냅샷에는 그 필드가 없다 — 직접 확인(`extract_return_axis({... 'claimStatus':'CANCEL_DONE'}) → return_completed_at=''`). 없는 날짜를 지어내지 않는다 |
| E15 `취소 거부 08-26` | `취소 거부` | 위와 같다(거부 스냅샷에도 `returnCompletedDate` 가 없다) |
| E16 꼬리 `색상·사이즈 변경 · 수거중` | `색상·사이즈 변경` | `수거중` 조각을 파생할 필드가 없고, `claimStatus=COLLECTING` 이면 그 낱말은 **이미 배지 라벨**이다 — 내면 한 줄에 두 번 적힌다 |
| E18 꼬리 `정산 지연` | (안 냄) | `CLAIM_REASON_LABELS` 에 없는 낱말이고 사유·수거·환불 네 조각 중 어느 것도 아니다. 파생할 출처가 없다 |
| E15 꼬리 `주문 살아 있음` | (안 냄) | 고스트 판정 — §8 에서 이미 제외(`find_ghost_orders` 는 링크 테이블 전체를 읽고 주문 단위로 판정한다) |

> **사유는 코드 라벨(`CLAIM_REASON_LABELS`)이지 고객이 쓴 원문(`detailed_reason`)이 아니다.**
> 목업의 `단순 변심`·`색상·사이즈 변경` 이 그 dict 의 낱말이다. 원문은 길이가 안 정해져 있어 좁은
> 상태 칸에 못 싣는다 — 원문은 pane 이 그대로 낸다(축이 다르다).

### 3.4 `옛 결제` 줄 — **이번 범위 밖** (§8)

---

## 4. 칩 계약

### 4.1 칩 목록 (화면 순서)

| # | 라벨 | 질의 | 숫자(컨텍스트 키) | 술어 |
|---|---|---|---|---|
| 1 | `전체` | 파라미터 없음 | `history.total` (필터가 걸리면 숫자를 안 낸다 — 기존 가드 유지) | — |
| 2 | `받아옴 · 주문 전` | `status=COLLECTED` | `history.counts.COLLECTED` | 기존 `_status_group_counts` |
| 3 | `주문 만듦` | `status=LINKED` | `history.counts.LINKED` | 기존 |
| 4 | `확인 필요` | `status=PENDING_REVIEW` | `history.counts.PENDING_REVIEW` | 기존 |
| 5 | `받기 실패` | `status=FAILED` | `history.counts.FAILED` | 기존 |
| 6 | `발주확인 남음 · 취소 포함` | `place=PENDING` | `history.place_pending_count` | 기존 `_place_pending_clause()` |
| 7 | **신규** `발송처리 남음 · 취소 포함` | `dispatch=PENDING` | `history.dispatch_pending_count` | §4.3 |
| 8 | **신규** `추가결제·재결제` | `rel=ADDON_REPAY` | `history.relation_count` | §4.4 |

- **`네이버 기록 없음` 은 칩으로 만들지 않는다.** 판정이 `raw_snapshot` 파생값(`mismatch`)이라 SQL 로 못 거른다.
  쪽을 자른 뒤 파이썬으로 세면 `history.total`·`history.pages` 가 거짓말이 된다(캡 뒤 파이썬 분류 함정).
  **행 배지로만** 둔다. 목업에는 점선 칩으로 그려져 있지만 **채택하지 않는다.**
- 7번 라벨에 `· 취소 포함` 을 붙인 것은 목업에서 한 낱말 벗어난 자리다. 술어가 컬럼·JSONB 경로만 보므로
  취소 집을 뺄 수 없고(빼려면 `extract_claim` 과 갈라진다), 옆 칩 6번이 같은 이유로 이미 그 꼬리를 달고 있다.
  꼬리 없이 두면 두 칩이 같은 성질인데 다른 말을 하게 된다.

### 4.2 `_history_view()` 가 새로 내는 컨텍스트 키

| 이름 | 모양 | 뜻 |
|---|---|---|
| `dispatch_pending` | `bool` | `?dispatch=PENDING` 이 걸려 있는가 (칩 `aria-pressed`) |
| `dispatch_pending_count` | `int` | 발송이 남은 **집** 수 |
| `relation_filter` | `bool` | `?rel=ADDON_REPAY` 가 걸려 있는가 |
| `relation_count` | `int` | 추가결제·재결제 링크를 가진 **집** 수 |
| `status_chips` | `tuple` | `HISTORY_STATUS_CHIPS` 그대로 — 템플릿이 이것을 돌아 칩을 낸다(§2.4). 템플릿이 낱말을 두 벌째 적지 않게 하는 자리다 |

읽기 규약은 기존과 같다(닫힌집합, 모르는 값은 무시):

```python
dispatch_pending = (request.args.get("dispatch") or "").strip().upper() == "PENDING"
relation_filter  = (request.args.get("rel") or "").strip().upper() == "ADDON_REPAY"
```

`_link_rows()` 시그니처에 키워드 두 개(`dispatch_pending: bool = False`,
`relation_filter: bool = False`)를 더한다. 상태 필터와 **같은 규약**이다 —
필터는 **묶음 선정에만** 쓰고, 뽑힌 묶음의 상품주문은 조건과 무관하게 전부 싣는다.

> **함정: 필터 파라미터가 4개가 됐다.** 칩 8개 · 페이저 `이전`/`다음` — 총 10곳이 `status`·`place`·
> `dispatch`·`rel` 을 **전부** 들고 가야 한다. 하나라도 빠지면 그 링크를 누른 순간 필터가 조용히 풀린다
> (선행 결함 #8 과 같은 모양). 레인 D 가 이것을 못 박는다.

### 4.3 `발송처리 남음` 술어 — `_dispatch_pending_clause()`

**정의**: 집 안에 "발송 기록이 아직 없는 링크"가 하나라도 있다.
링크 단위 "발송 기록 없음" = 우리 표식도 없고 네이버 `sendDate` 도 없다.

```python
def _dispatch_pending_clause():
    """'발송처리 전' 조건 — 우리 표식도 네이버 sendDate 도 없는 링크.

    부분 인덱스 ``ix_external_order_link_dispatch_pending`` 의 조건식과 **글자까지 같아야** 한다.
    """
    from sqlalchemy import func
    ours = ExternalOrderLink.triage_state["fulfillment"]["dispatched_at"].as_string()
    naver = ExternalOrderLink.raw_snapshot["delivery"]["sendDate"].as_string()
    return and_(func.coalesce(ours, "") == "", func.coalesce(naver, "") == "")
```

집 수는 다른 칩과 **같은 모양**으로 센다:

```python
def _dispatch_pending_group_count(db) -> int:
    key_col = _group_key_col()
    return (db.query(key_col)
              .filter(ExternalOrderLink.channel == "NAVER", _dispatch_pending_clause())
              .group_by(key_col).count())
```

부분 인덱스(새 마이그레이션 `naverdisp_00_history_chip_indexes.py`, PostgreSQL 전용 —
`naverfail_00` 과 같은 모양):

```sql
CREATE INDEX IF NOT EXISTS ix_external_order_link_dispatch_pending
    ON external_order_links (channel, group_key)
 WHERE coalesce(CAST(((triage_state -> 'fulfillment') ->> 'dispatched_at') AS VARCHAR), '') = ''
   AND coalesce(CAST(((raw_snapshot -> 'delivery') ->> 'sendDate') AS VARCHAR), '') = ''
```

> **`CAST(… AS VARCHAR)` 를 빼면 인덱스가 통째로 무시된다.** `models.JSONColumn` 의 베이스 타입이
> `JSON` 이라(`JSON().with_variant(JSONB, "postgresql")`) `.as_string()` 이 CAST 를 붙인다.
> 조건식이 한 글자라도 어긋나면 PostgreSQL 이 부분 인덱스를 증명하지 못하고, 그때 나오는 Seq Scan 은
> §4.5 때문에 "선택도가 낮아서"로 오독된다(2026-08-30 CEO 착수 게이트 1 — 이 문서가 CAST 없이
> 적어 둔 것이 그 결함이었다). **손으로 적지 말고** 아래를 렌더해 붙인다(테이블 수식어만 뗀다):
>
> ```python
> str(_dispatch_pending_clause().compile(
>     dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
> ```
>
> 술어를 고치면 이 마이그레이션을 고치는 게 아니라 **새 마이그레이션으로 인덱스를 다시 만든다**.

> **판정은 "Seq Scan 없음" 이 아니라 "인덱스 이름이 뜬다" 로 한다.** 없음 판정은 인덱스가 무시돼도
> 통과할 수 있다 — `EXPLAIN` 출력에 `ix_external_order_link_dispatch_pending` 이 실제로 보여야 한다.

**알려진 어긋남 1개(수용, 기록함)**: 파이썬 `mapping.extract_delivery` 는 최상위 `delivery` 가 없으면
`productOrder.delivery` → `order.delivery` 로 내려간다. SQL 은 **최상위만** 본다.
수집 파이프라인이 저장하는 모양(`ingest.py:130,239` — API 응답 항목 그대로)은 최상위이므로 실데이터는 같다.
경로 3개를 `coalesce` 로 잇는 것은 **안 한다** — 인덱스 조건식이 세 배로 길어져 "정확히 일치" 규율이 먼저 깨진다.
레인 D 가 최상위 모양으로 칩 숫자 == 행 표시를 못 박고, 이 어긋남을 원장에 남긴다.

**`models.py` 는 손대지 않는다.** 선례가 있다 — `ix_external_order_link_fulfillment_error` 는
마이그레이션에만 있고 `__table_args__` 에는 없다. 같은 자리를 따른다(레인 격리에도 유리하다).

마이그레이션의 `down_revision` 은 **착수 시점에** `python -m alembic heads` 로 확인해 붙인다.
지금 값을 여기 못 박지 않는다 — 다른 세션 승격으로 하루면 낡는다.
(2026-08-30 실제 값 = `merge_drawq_naverfail`. 같은 날 `python -m alembic heads` → `naverdisp_00 (head)`
단일 head 확인. **이 값은 기록이지 계약이 아니다** — 승격 시점에 다시 확인한다.)

마이그레이션 안에서 `models` 를 **live import 하지 않는다**(상수 동결 원칙). import 하면 나중에
술어가 바뀔 때 이 과거 마이그레이션이 소급 오염된다 — 조건식은 위 렌더 결과를 문자열로 박는다.

### 4.4 `추가결제 · 재결제` 술어

컬럼이라 그대로 센다(닫힌집합, `CheckConstraint` 가 이미 값을 막는다).

```python
def _relation_clause():
    """추가결제·재결제 링크 조건 — 관계 컬럼 하나로 끝난다(JSONB 안 탄다)."""
    return ExternalOrderLink.relation.in_(("ADDON", "REPAY"))
```

부분 인덱스(같은 마이그레이션 안에):

```sql
CREATE INDEX IF NOT EXISTS ix_external_order_link_relation_pair
    ON external_order_links (channel, group_key)
 WHERE relation IN ('ADDON', 'REPAY')
```

이쪽은 모집단이 희소해서 부분 인덱스가 제값을 한다.
렌더 결과가 위 SQL 과 이미 같아서(`relation IN ('ADDON','REPAY')`) 손댈 것이 없었다 —
PostgreSQL 은 이것을 `((relation)::text = ANY (ARRAY[…]))` 로 정규화해 저장한다(같은 식이다).

### 4.5 성능 판정 규약 (T7 에 그대로 넣는다)

`발송처리 남음` 모집단은 **희소하지 않다**(대부분의 링크가 아직 발송 전이다).
플래너가 그래서 Seq Scan 을 고를 수 있다 — 그건 술어가 틀린 것이 아니라 선택도 문제다.
그런 결과가 나오면 **술어를 비틀지 말고** `EXPLAIN` 원문과 행 수를 원장에 붙이고 판단을 받는다.
술어를 인덱스에 맞추려고 뜻을 바꾸는 순간 칩 숫자와 행 표시가 갈린다 — 그게 더 나쁜 고장이다.

---

## 5. CSS 클래스 계약 (레인 B ↔ 레인 C 공용 이름)

| 클래스 | 무엇 | 비고 |
|---|---|---|
| `th.wb-hist__status` / `td.wb-hist__status` | 상태 칸 (머리 + 몸통 **둘 다**) | `min-width: calc(250px * var(--wb-fs, 1))`, `th` 만 `width: 34%` |
| `.wb-st-wrap` | **컨테이너** 블록 래퍼 | `container-type: inline-size` — 여기 말고 `td` 에 걸면 안 된다 |
| `.wb-st` | 축 격자 | `display: grid; grid-template-columns: calc(74px * var(--wb-fs, 1)) 1fr; gap: 3px 8px; align-items: start` |
| `.wb-st__k` | 축 라벨(`FOMS`/`네이버`/`취소·반품`) | 회색·작은 글자 |
| `.wb-st__v` | 축 값 줄 | `display: flex; flex-wrap: wrap; gap: 4px; min-width: 0` |
| `.wb-st__when` | 값 옆 회색 부속 문구 | 목업 `.when` |
| `.wb-st__note` | 회색 보조 줄 | 목업 `.note`. **이번 라운드 소비처 0** — `옛 결제` 줄(§8 제외)이 쓸 자리라 CSS 에만 있고 템플릿에는 없다 |
| `.wb-st__warn` | 빨강 경고 줄 | 목업 `.warn` |
| `.wb-st__b` | 배지 본체 | 목업 `.b` |
| `.wb-st__b--blue` / `--green` / `--amber` / `--red` / `--violet` / `--slate` / `--ghost` | 배지 색 | 목업 `.b--*` 와 1:1 |
| `.wb-pipe` | 파이프 감싸개 | `display: inline-flex; flex-wrap: nowrap` |
| `.wb-pipe__s` | 파이프 한 칸 = 기본 상태(`todo`, 회색 이름만) | 첫 칸 왼쪽 둥글게 · 끝 칸 오른쪽 둥글게 + `border-left: 0` |
| `.wb-pipe__s--done` | 끝남 | 초록 |
| `.wb-pipe__s--now` | 지금 차례 | 주황 |
| `.wb-pipe__s--skip` | 해당 없음 | 회색(slate) |
| `.wb-pipe__s--bad` | 실패·어긋남 | 빨강 |

상태 키 → 클래스 대응(레인 C 가 템플릿에서 매핑):
`done → .wb-pipe__s--done` · `now → --now` · `skip → --skip` · `bad → --bad` · `todo → (없음)`.

**"레인 C 가 매핑" 은 클래스 대응만을 뜻한다.** 어느 상태인지 정하는 **판정 자체는 서버**가 한다
(§2.3). 템플릿에 남는 판정성 `{% set %}` 은 톤 대응 두 벌(`foms_state → blue/green/slate/amber/red`,
`claim_phase → red/slate/ghost/amber`)뿐이다.

### 5.1 반드시 지킬 CSS 사실 3가지

1. **`td` 는 컨테이너가 못 된다.** `display: table-cell` 은 inline-size containment 를 무시한다
   (목업에서 실측: 칸 306px 인데 `@container` 가 안 걸렸다). `container-type` 은 **안쪽 블록
   래퍼 `.wb-st-wrap`** 에만 건다.
2. **접힘 기준은 뷰포트가 아니라 칸 폭이다.** `@container (max-width: 330px)` 에서
   `.wb-st { grid-template-columns: 1fr; gap: 1px }` 로 라벨을 위로 올려 한 열로 쌓는다.
   같은 부품이 나중에 처리 탭·도크(폭 358)에도 실린다 — 뷰포트 미디어쿼리는 오답이다.
   `@container` 조건식에는 `var()` 를 못 쓴다 — 330px 은 그대로 둔다.
3. **고객 열을 짜내지 않는다.** 좁은 폭에서 열을 줄이면 글자가 세로로 선다.
   `.wb-hist { min-width: calc(720px * var(--wb-fs, 1)) }` + 고객 열 `white-space: nowrap` 으로 두고,
   표 전체를 기존 `.table-responsive` 의 가로 스크롤로 넘긴다.

이 파일의 모든 `font-size` 는 `calc(Npx * var(--wb-fs, 1))` 규약을 따른다(이 화면은 글자 크기를 단계로 키운다).
색은 `.naver-workbench` 의 `--wb-*` 토큰을 먼저 쓰고, 목업에만 있는 색(보라·slate·초록)만 새 토큰으로 더한다.

---

## 6. 레인별 파일 배분 (겹치면 병렬이 깨진다)

### 레인 A — 서버(파이썬)

- `foms/web/admin/naver_ingest.py`
- `migrations/versions/naverdisp_00_history_chip_indexes.py` *(신규)*

`models.py` 는 **안 건드린다**(§4.3). 다른 레인의 파일도 안 건드린다.

### 레인 B — CSS

- `static/css/admin/naver-workbench.css`

`?v=` 핀은 템플릿에 있으므로 레인 B 는 **핀을 못 올린다**. 레인 C 가 올린다(§7).

### 레인 C — 템플릿 + 자산 핀 + 핀 문자열 테스트

- `templates/admin/naver_workbench.html`
  - CSS 핀(`css/admin/naver-workbench.css?v=`) · JS 핀(`js/admin/naver-workbench.js?v=`)
  - 이력 칩 블록(`history.status_chips` 루프 + 칩 3개)
  - 이력 표 머리(상태 열 `th` 에 `class="wb-hist__status"` 를 함께 준다)
  - 상태 칸 `td.wb-hist__status`
  - 이력 페이저(새 파라미터 2개 동반)
- `tests/services/integrations/test_naver_origin_cleanup.py` *(핀 문자열 + 아래 예외)*
- `tests/services/integrations/test_naver_workbench_async_result.py` *(핀 문자열만)*

> **행 번호로 자르지 않는다.** 2026-08-30 CEO 착수 게이트가 이 문단의 행 번호가 실제와 어긋난 것을
> 지적했다(칩 619~657, 표머리 659~666, 상태 td 688~700, 페이저 753~768 — 표도 6열이 아니라 8열이다).
> 레인이 번호를 믿고 자르면 다친다. **앵커 문자열로** 찾는다.

**등재된 예외 1건 — `test_naver_origin_cleanup.py` 의 `collected_at`.** 이 파일은 원래 "핀 문자열
한 줄만" 배분인데, `_link()` 헬퍼에 `collected_at` 키워드가 신설되고 호출부 2곳이 그 값을 넘기도록
바뀌었다. **되돌리지 않는다**(2026-08-30 사람 결정). 이유: `order_candidates._dispatch_view` 의
`read_at` 이 `max(refreshed_at, created_at)` 이라, 수집 시각을 함께 과거로 못 박지 않으면 두 링크의
`created_at` 이 같은 밀리초 눈금에 떨어질 때만 판정이 뒤집혀 **간헐 실패**가 된다. 증상 덮기가
아니라 결정성 확보다. 이번 변경과 인과가 없는 수정이므로 이 자리에 예외로 남긴다 —
다음 사람이 "배분 위반"으로 되돌리지 않게 하기 위한 등재다.

### 레인 D — 신규 계약 테스트

- `tests/services/integrations/test_naver_history_status_axes.py` *(신규)*

`test_naver_workbench.py` 를 **수정하지 않는다.** `_login` · `workbench_on` · `_uid` 만 import 하고,
발주확인·발송·관계·클레임을 세밀히 조작하는 픽스처는 새 파일 안에 스스로 만든다
(`_collected` 를 확장하면 그 파일이 공유 자산이 되어 레인이 겹친다).

### 아무 레인도 건드리지 않는 것

- `docs/plans/2026-08-30-naver-history-status-column-ledger.md` — 진행 원장은 **오케스트레이터가** 갱신한다.
  네 레인이 각자 쓰면 매번 충돌한다.
- `templates/admin/naver_ingest.html` (옛 수집 화면) — 게이트가 켜지면 닫히는 화면이고
  `test_naver_admin_surface.py:217` 이 그 화면의 옛 라벨(`수집됨(생성 전) 2주문`)을 잠근다.
  워크벤치만 새 어휘로 간다. **두 화면이 한동안 다른 말을 쓰는 것은 의도된 것이다.**
- `static/js/admin/naver-workbench.js` — 이번 변경은 JS 를 안 탄다.
  `찾기` 는 행의 `data-find` 속성만 읽으므로 상태 칸이 바뀌어도 그대로 돈다.
- `.github/workflows/ci.yml` — 새 테스트가 `docs/` 를 읽지 않으므로 CI-DOCSCOPE-01 등재가 필요 없다.
  만약 레인 D 가 문서를 읽는 단언을 넣게 되면 **그때** 등재하고 이 문서를 고친다.

---

## 7. 자산 핀 — 현재 값과 잠근 자리 (실측)

| 자리 | 착수 전 | **지금(2026-08-30 실측)** |
|---|---|---|
| `templates/admin/naver_workbench.html` CSS 핀 (22행) | `?v=20260829a` | `?v=20260830a` |
| `templates/admin/naver_workbench.html` JS 핀 (897행) | `?v=20260829a` | `?v=20260830a` |
| `tests/services/integrations/test_naver_origin_cleanup.py` (313행 → 321행) | `markup.count("?v=20260829a") == 2` | `markup.count("?v=20260830a") == 2` |
| `tests/services/integrations/test_naver_workbench_async_result.py:406` | `markup.count("?v=20260829a") == 2` | `markup.count("?v=20260830a") == 2` |

네 자리를 **한 커밋에서 함께** 올린다.
CSS 를 고치고 핀을 안 올리면 서비스워커(`staticCacheFirst`)가 옛 파일을 계속 낸다.
(JS 핀 행이 792 → 897 로 밀린 것은 상태 칸 마크업이 길어졌기 때문이다 — 행 번호는 기록일 뿐,
찾을 때는 `?v=` 문자열로 찾는다.)

**건드리면 안 되는 남의 핀**: `tests/domains/test_erp_order_shared_form_scripts.py:73`
(`js/orders/erp-order-shared.js?v=20260829a`) — 글자는 같지만 **다른 자산**이다. 그대로 둔다.

---

## 8. 이번에 안 싣는 것 (그리고 왜)

목업에 그려져 있지만 이번 계약에서 **제외**한다. 레인이 "빠졌네" 하고 만들지 않도록 여기 적는다.

| 목업 | 왜 뺐나 |
|---|---|
| `옛 결제` 줄 (E3 `취소 완료 08-27` · E4 `아직 살아 있음`) | `_origin_view` → `order_candidates.origin_facts(db, order_id, …)` 가 **행마다 한 번** 돈다. 한 쪽 20집이면 조회 20번(N+1). 배치 조회를 새로 만드는 것은 별건이다 |
| `재결제 짝 → #N` (E14) | 옛 주문에서 **새 주문**을 되찾는 방향이라 위와 같은 역조회가 필요하다 |
| `기존 주문 후보 N건` (E17) | `find_order_candidates` 가 행마다 도는 함수다 |
| `주문 살아 있음`(고스트, E19) · `결제 전부 취소됨` | `find_ghost_orders` 는 **링크 테이블 전체**를 읽고 **주문 단위**로 판정한다. 집 단위·페이지 링크로는 같은 답이 안 나온다. 근사값을 만들면 전역 고스트 띠와 숫자가 갈리고, 그 판정은 폐기(soft delete) 버튼의 허가증이기도 하다 — 두 벌로 갈라 놓을 자리가 아니다 |
| `네이버 기록 없음` **칩** | §4.1 — `raw_snapshot` 파생값이라 SQL 로 못 거른다. **행 배지로만** 둔다 |
| 처리 탭(work) 행 배지 어휘 통일 | 별건. 이력 탭이 먼저다 |
| 반품 축(수거 완료·환불 예정)을 **칩**으로 거르기 | 행 표시까지만 |

---

## 9. 레인 D 가 못 박아야 할 것 (계약 테스트 목록)

계획서 T6 의 8개에 이 계약에서 나온 4개를 더한다.

1. 추가결제·재결제 집에 관계 배지와 **상대 주문번호**가 나온다.
2. 발주확인·발송처리 완료가 **글자로** 나온다(무표시 규칙 부활 방지).
3. 부분 발송(`발송처리 1/2`)·부분 발주확인(`발주확인 2/3`)이 나온다.
4. 우리 기록만 있고 네이버가 침묵하면 `네이버 기록 없음` 이 나온다.
5. 취소 확정 집(발주확인·발송 0)은 파이프 대신 `네이버 처리 없음` 한 칸.
6. `claim_phase` 가 미확정(`· 확정 전`)과 확정을 가른다.
7. 이력 행에 `<button`·`data-link-id`·`class="btn` 이 없다(절대 규칙 3).
8. **모든 칩 라벨은 대응하는 배지 낱말로 시작한다**(꼬리는 붙일 수 있어도 앞머리는 못 바꾼다).
   `HISTORY_STATUS_CHIPS` 는 `HISTORY_FOMS_LABELS` 에서 파생되므로 이 단언이 성립한다 —
   "같은 낱말" 을 그대로 물으면 `받아옴 · 주문 전` vs `받아옴` 에서 걸려 테스트를 몰래 약하게 쓰게 된다.
9. **신규** 새 칩 두 개의 숫자가 **집 단위**다 — 링크 3건짜리 집 하나에서 칩이 `1` 이어야 한다.
10. **신규** 칩 8개와 페이저 두 링크가 `status`·`place`·`dispatch`·`rel` **네 파라미터를 전부** 들고 간다.
11. **신규** `place_pending == (place_done_count < place_total)` — 기존 필드와 새 집계가 안 갈린다.
12. **신규** 상태 칸 마크업에 `id=` 속성이 없다(문서 안 `id` 중복 금지 계약).

수정 라운드에서 더한 것(2026-08-30):

13. `relation` 은 `ADDON` 인데 대표가 `NEW` 인 **섞인 집**에서 번호가 관계 멤버의 것으로 나온다.
14. 관계 멤버에 주문이 없으면 배지에 화살표·번호가 **아예 없다**.
15. 어긋남 경고가 **어긋난 그 링크의 시각**을 쓴다 — 형제의 정상 발송 시각을 빌려 오지 않는다.
16. 확정된 반품 집에 **확정 날짜**와 `수거 완료 … · 환불 완료` 꼬리가 나온다(§3.3).
17. 미확정 집에 **사유**와 `환불 예정 {MM-DD}` 가 나온다.
18. 날짜·사유가 하나도 없는 클레임은 **배지만** 나온다(빈 `.wb-st__when` 을 만들지 않는다).
19. 칩 라벨이 **서버 상수를 따라간다**(상수를 흔들면 화면이 따라 흔들린다 — 두 벌 적기 회귀 방지).
20. 클레임이 없는 링크에서는 `_return_axis_view()` 를 **한 번도 부르지 않는다**.
21. 발송기한 초과 줄이 **증명한 사실만** 말한다(`발송기한 N일 지남` 만 — 자동 취소 문장 없음).

> **단언은 행 dict 키가 아니라 렌더된 HTML 낱말로 건다.** 이번 라운드에서 클레임 필드 이름이
> 바뀌었다(아래 §10) — 키로 단언한 테스트는 화면이 멀쩡해도 빨개지고, 화면이 망가져도 초록일 수 있다.

---

## 10. 기록

| 날짜 | 내용 |
|---|---|
| 2026-08-30 | 본 계약 작성. 코드 미착수. 목업 대비 벗어난 자리 3곳을 명시: ① `발송처리 남음` 칩에 `· 취소 포함` 꼬리 추가 ② `네이버 기록 없음` 칩 미채택 ③ `반품 수거중` → 상수대로 `수거중`. 범위에서 뺀 것 7종은 §8. |
| 2026-08-30 (구현 중 확정) | 아래 12건. 전부 **코드가 정본이고 이 문서를 코드에 맞춘 것**이다 — 반대 방향이 아니다. |

### 10.1 2026-08-30 구현 중 확정 — 항목별 근거

| # | 확정 | 근거 |
|---|---|---|
| 1 | 부분 인덱스 조건식에 `CAST(… AS VARCHAR)` 가 들어간다(§4.3) | `models.JSONColumn` 의 베이스 타입이 `JSON` 이라 `.as_string()` 이 CAST 를 붙인다. 계약 초안대로 CAST 없이 만들었으면 PostgreSQL 이 부분 인덱스를 증명 못 해 통째로 무시했을 것이다. 마이그레이션은 `literal_binds` 렌더 결과를 따랐다 (CEO 착수 게이트 1) |
| 2 | `related_order_id` 는 **관계를 정한 멤버**에서 나온다(§2.2) | 대표는 금액 최대 링크라 섞인 집에서 `NEW` 형제일 수 있다. `_group_queue` 주석이 "형제 일부만 값이 있을 수 있어 멤버 전체를 본다" 고 이미 적어 뒀다 — 섞인 집은 실재한다 (CEO 착수 게이트 2) |
| 3 | 칩 라벨은 `_HISTORY_STATUS_CHIP_SPECS` → `HISTORY_STATUS_CHIPS` **파생**이고, 템플릿은 `history.status_chips` 를 돈다(§2.4·§4.2) | 칩 `받아옴 · 주문 전` vs 배지 `받아옴` 이라 "같은 낱말" 단언이 불가능했다. 파생으로 바꾸고 §9-8 을 "배지 낱말로 시작한다" 로 다시 썼다. 템플릿이 네 낱말을 두 벌째 적으면 상수는 SSOT 가 아니라 드리프트 감시다 (CEO 착수 게이트 3 + 최종 판정 minor) |
| 4 | 클레임 **날짜·사유를 화면에 낸다**(§3.3) | 목업 확정본이 이미 승인된 화면이고 재료는 순수 파싱이라 추가 쿼리 0이다. 계산해 놓고 안 내면 죽은 필드가 되고 다음 사람이 "화면에 이미 있다"고 오독한다 (CEO 지적 4 → 사람이 (a)안 선택) |
| 5 | 행이 싣는 클레임 필드는 `claim_badge_text`·`claim_tail_text` **두 개**다 | 원재료 6종(`claim_kind`·`claim_reason`·시각 3종·`claim_refund_done`)은 멤버 dict 에만 둔다. 조립을 서버가 하지 않으면 HTML 문자열 매칭 말고는 시험할 방법이 없다 |
| 6 | 확정 날짜는 `returnCompletedDate` **하나에서만** 온다 → 취소 확정·거부에는 날짜가 안 붙는다(§3.3 갈림표) | 직접 확인: `extract_return_axis({'productOrder': {'claimStatus': 'CANCEL_DONE'}, 'cancel': …})` → `return_completed_at=''`. `RETURN_BLOCK_KEYS = ("returnInfo","return","exchange")` 라 취소 블록은 반품 축을 안 준다. 없는 날짜를 지어내지 않는다 |
| 7 | 목업 E16 꼬리의 `수거중` 조각·E18 꼬리 `정산 지연` 은 내지 않는다(§3.3 갈림표) | 앞은 `claimStatus=COLLECTING` 이면 **이미 배지 라벨**이라 한 줄에 두 번 적히고, 뒤는 `CLAIM_REASON_LABELS` 에도 사유·수거·환불 네 조각에도 없다 |
| 8 | 어긋남 경고 시각 = `dispatch_mismatch_ours_at` **별도 집계**(§2.2·§3.2-경고) | 접힌 `dispatch_ours_at` 은 최솟값이라 [정상 09:00, 어긋남 16:02] 집에서 **네이버가 기록한 09:00** 을 "기록 없음" 이라 말했다 (CEO 최종 판정 major 1) |
| 9 | 발주확인·발송 판정표를 **서버로 옮겼다**(`_history_place_step`·`_history_dispatch_step`, §2.3·§5) | 템플릿 `{% set %}` 사슬 약 50줄이라 파이썬 단위 테스트로 못 잠갔고, 같은 부품이 처리 탭·도크에 실릴 때 판정이 두 벌이 될 자리였다 (CEO 최종 판정 minor) |
| 10 | `네이버 자동 취소 가능` 문구를 **지웠다**(§3.2) | 네이버가 기한 초과 건을 자동 취소한다는 근거가 상수·문서·테스트 어디에도 없었다. 운영자가 그 문장을 보고 판매자센터 확인을 건너뛸 수 있다. 배지 `발송기한 N일 지남` 은 사실이라 남긴다 (CEO 최종 판정 minor) |
| 11 | 방어 코드 2종 제거 — `getattr(order, "status", "")` / 템플릿 `or 0`(§2.3-A) | 둘 다 "없을 리 없는 것"에 대한 미봉책이라 나중에 진짜 결함을 삼킨다. `shipping_due_text` 도 무방비 슬라이스(`due[5:]`)를 없애고 파싱 1회로 합쳤다(`due="20260902"` → 화면 `발송기한 902` 재현했다) (CEO 최종 판정 minor 2건) |
| 12 | `_return_axis_view()` 는 **클레임이 있는 멤버에만** 부른다(§2.1) | 링크마다 부르면 쪽당 50집 × 멤버 수만큼 빈 값을 만드는 헛일이 붙는다. 게이트 술어를 `_history_claim()` 의 멤버 선택 술어와 같은 값(`claim_label`)으로 두어 라벨과 날짜가 갈리지 않게 했다 |

### 10.2 이 라운드에서 **바뀐 이름** (외부에서 읽는 코드가 있으면 여기부터 본다)

| 옛 이름(1차 구현) | 지금 | 왜 |
|---|---|---|
| 행 `claim_kind`·`claim_reason`·`claim_done_text`·`claim_refund_expected_text`·`claim_collect_done_text`·`claim_refund_done` | 행 `claim_badge_text`·`claim_tail_text` (원재료는 멤버 dict 로 내려갔다) | 조립을 서버가 끝낸다(§10.1-5). `claim_label`·`claim_phase` 는 그대로다 |

계약 테스트는 **행 dict 키가 아니라 렌더된 낱말**로 단언한다 — 이름이 바뀌어도 화면이 옳으면 초록이어야 한다.


---

## 15. 2026-08-30 최종 검수 반영 — 앞 절보다 **이 절이 우선한다**

CEO 최종 2판정이 "계약서가 실제 구현과 반대되는 말을 한다"를 major 로 짚었다.
아래는 그 정정이다. 앞 절(§2·§3·§5·§8·§10)과 충돌하면 **이 절이 정본**이다.

### 15.1 취소 확정 날짜 — §3.3·§10.1 뒤집힘

§3.3 갈림표는 「목업 E14 `취소 완료 08-26` → 실화면 `취소 완료`」로 적고 근거를
「확정 날짜의 유일한 출처가 `returnCompletedDate`(반품 축)다」로 못 박았다. **틀렸다.**

취소 확정 시각은 `cancelCompletedDate` 에 있다(운영 `CANCEL_DONE` 15건 실측 —
`docs/specs/2026-08-28-naver-claim-phase-labeling_SPEC.md` §1.1). 읽는 코드가 0곳이었을 뿐이다.
`mapping.extract_cancel_axis()` 를 신설해 **취소 블록만** 읽고, `_history_member_axes` 가
클레임 종류가 취소일 때만 그 축을 본다. 화면은 이제 목업대로 `취소 완료 08-26 · 환불 완료` 를 낸다.

**반품 축에 `cancel` 을 도로 넣지 않는다** — 2026-08-27 에 고친 누출(취소 블록 환불 필드가
반품 진행으로 샘)을 되살린다. 그 거울상(취소 집에 반품 낱말)도 막았다:
`claim_refund_expected_at`·`claim_collect_done_at` 은 취소로 판정된 멤버에서 빈 값이다.

- `취소 거부` 에 날짜가 안 붙는 근거도 정정: `returnCompletedDate` 부재가 아니라
  **거부 스냅샷에 `cancelCompletedDate` 가 없기 때문**이다.
- 잠근 테스트: `test_settled_cancel_household_shows_the_cancel_date_and_refund` ·
  `test_cancel_request_without_approval_shows_no_date` ·
  `test_cancel_axis_is_parsed_only_for_cancel_claims` · `test_cancel_household_never_shows_return_words`.

### 15.2 행 dict 필드 — §2.2 정정

행에서 **뺀** 것(읽는 곳 0): `dispatch_done_count` · `dispatch_total` · `dispatch_moot` ·
`shipping_due` · `dispatch_ours_at` · `dispatch_naver_at` · `shipping_due_text` ·
`shipping_due_over_days`. 이 값들은 집계 dict 안에만 남고, 부속 문구·파이프 낱말이 그 뜻을 담는다.

행에 **더한** 것:

| 이름 | 모양 | 값 예 |
|---|---|---|
| `pipe_note_kind` | `str` — `"when"` · `"over"` · `""` | `"when"` |
| `pipe_note_text` | `str` | `"발송기한 09-02"` · `"발송기한 2일 지남"` |

판정은 `_history_pipe_note()` 가 한다(계약 §3.2 표를 서버로 옮긴 것). 템플릿은 종류를
CSS 클래스로만 옮긴다.

### 15.3 CSS — §5 정정

`.wb-st__note` 는 **없다**(소비처가 0이라 규칙째 삭제). §5 표의 그 줄은 무효다.

### 15.4 목업 대비 아직 안 실은 것 — §8 추가

목업의 격자 아래 회색 보조 줄(`.note`) 3건: E2 `발주확인 뒤 바로 닫은 건` ·
E13 `금액만 환급` · E17 `추가결제·재결제 고르기`. 파생 출처가 각각 관계 규칙 · 반품 금액환급
성질 · 다음 할 일 힌트로 **축이 셋**이라 별건으로 뺐다.

### 15.5 수용한 것 (고치지 않기로 함)

옛 수집 화면(`naver_ingest_dashboard`)도 `_link_rows` 를 거치므로 링크당 축 파싱을 함께
치른다. 축 계산에 게이트를 걸어 봤으나 **집 조립(`_history_group_axes`)까지 두 갈래**가 되어
그 화면이 500 으로 떨어졌다(18 테스트 red, 되돌림). 그 화면은 워크벤치 게이트가 켜지면
리다이렉트로 닫히는 화면이라 수명이 짧다 — 파싱은 순수 파이썬이고 쿼리는 0이다.
