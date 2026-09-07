# 네이버 워크벤치 — 휴지통 표기 + 유령 문장 사실화 (2026-09-07)

작업 트리: `c:\tmp\foms-s-s0907-143127` (브랜치 `session/s0907-143127`, base `origin/deploy` + 세션 커밋 2개 cherry-pick, HEAD `16c1c57e2`).
모든 명령은 `pwd` 로 시작한다 — bash cwd 는 호출 사이에 메인 트리로 리셋된다.

## 왜 하는가

### 문제 1 — 휴지통으로 보냈다는 기록이 화면에 없다 (사용자 보고 2026-09-07)
담당자가 상세 pane 에서 `이 ERP 주문을 휴지통으로` 버튼을 눌렀다. 주문은 실제로 휴지통에 들어갔는데,
화면에는 그 사실이 한 글자도 남지 않는다. 원인은 두 곳이다.

1. `foms/services/integrations/naver_commerce/ghost_orders.py:497` (`judge_order_discard`)
   `if order is None or order.deleted_at is not None or not bucket["canceled"]: return blank`
   → 휴지통에 들어간 순간 `applicable=False` 가 되어 **블록이 통째로 사라진다**.
2. `templates/admin/partials/naver_workbench_pane.html:200`
   머리줄 배지 `주문 #{{ selected.order_id }}` 는 휴지통 여부를 보지 않는다 — 접힌 주문도 살아 있는 것처럼 보인다.

버튼을 누르면 `static/js/admin/naver-workbench.js:520` 이 성공 시 `softRefresh()` 로 pane 을 다시 그린다.
그래서 **서버가 사실을 말하기만 하면** 누른 직후 화면에 바로 나타난다(추가 JS 없음).

### 문제 2 — 유령 문장이 재결제 집과 옛 집을 한 통에 센다
같은 함수 `judge_order_discard` 의 문장 재작성 구간(`ghost_orders.py:505-517`):

- 지금 집이 살아 있는 집 목록(`alive`)에 **없을 때**만 사실 문장을 쓴다
  (`이 집만 취소됐고, …은 살아 있습니다`).
- 그 반대 방향, 즉 **지금 보고 있는 집이 살아 있는 쪽**이 빠져 있어서
  `이 주문에는 아직 살아 있는 결제가 있습니다 — 14건 중 9건만 취소됐습니다` 로 떨어진다.
  실제로는 9건이 옛 주문(취소된 집)이고 5건이 지금 받은 새 결제다. 링크 수를 한 통에 세니 문장이 사실이 아니다.

## 무엇을 바꾸는가 (경계)

**판정을 바꾸지 않는다.** `_discard_verdict` · `can_discard` · `discard_needs_reason` · 유령 모집단
(`find_ghost_orders` 의 필터) · `UNSETTLED_CLAIM_CODES` · `RELATION_BY_CLAIM_PAIR` · `run_gate` 는
한 글자도 손대지 않는다. 이번 작업은 **사실 표기와 문장**뿐이다.

CSS 는 건드리지 않는다 — 부트스트랩 배지와 기존 `wb-ghost__dim` 만 쓴다. 그래야 `?v=` 핀 범프가 필요 없다.
(만약 CSS 를 꼭 바꿔야 한다는 결론이 나오면 `templates/admin/naver_workbench.html:22` 핀을
`?v=20260907d` 로 올리는 것까지가 한 작업 단위다.)

## 계약 초안 (이름 고정 — 워커는 이 이름을 바꾸지 않는다)

`judge_order_discard` 반환 dict 에 다음 키를 **항상** 넣는다(휴지통이 아니어도 False/빈 문자열).

| 키 | 뜻 |
| --- | --- |
| `trashed` | 이 주문이 휴지통에 있는지 (`order.deleted_at` 또는 `state_axes.read_deleted(order) == "DELETED"`) |
| `trashed_at_text` | 휴지통에 넣은 시각 표시용(`MM-DD HH:MM`). 모르면 빈 문자열 — 지어내지 않는다 |
| `trashed_note` | 접은 사유 문장(`structured_data['delete']` projection). 없으면 빈 문자열 |

휴지통 주문이면서 클레임이 있는 경우: `applicable=True`, `can_discard=False`,
`discard_block` 은 `이미 휴지통에 있습니다 — 주문 목록 휴지통에서 되돌립니다`.
클레임이 아예 없는 주문은 지금처럼 `applicable=False` 로 남긴다(블록을 그리지 않는다).

폐기 버튼 꼬리표는 `ghost_discard.trashed` 일 때 `지금은 안 됨` 대신 `휴지통에 있음` 을 쓴다 —
이미 접힌 주문에 "못 한다"는 말은 사실이 아니다(못 하는 게 아니라 **이미 되어 있다**).
낱말만 바꾼다: 버튼 자체·`disabled` 조건·`title` 은 불변이다.
`templates/admin/partials/naver_workbench_pane.html:573` 편집을 W2 범위 안으로 승인한다.

pane 머리줄 배지는 클레임 유무와 무관해야 하므로 `_pane_context`(`foms/web/admin/naver_ingest.py`)가
독립 키 `order_trashed`(bool) · `order_trashed_at_text`(str)를 함께 낸다.

## 파일 소유권 (겹치면 안 된다)

| 워커 | 편집 허용 파일 | 금지 |
| --- | --- | --- |
| W1 | `foms/services/integrations/naver_commerce/ghost_orders.py` | 다른 모든 파일 |
| W2 | `foms/web/admin/naver_ingest.py`, `templates/admin/partials/naver_workbench_pane.html` | `ghost_orders.py`, 테스트 |
| W3 | `tests/services/integrations/test_naver_ghost_trash_trace.py`(신규), `tests/services/integrations/test_naver_ghost_sentence_house_axis.py`(신규) | 기존 파일 수정 |

세 워커 모두 git 명령 금지(커밋·add·stash 전부). CRLF 를 보존한다. 문서를 읽는 테스트를 새로 만들지 않는다
(CI 서브셋 등재 게이트가 있다).

## 앵커 (경로:행)

- `foms/services/integrations/naver_commerce/ghost_orders.py:442` `judge_order_discard` 시작
- 같은 파일 `:497` 휴지통 주문을 blank 로 떨구는 줄
- 같은 파일 `:505-517` 문장 재작성 구간(`whole` / `here` / `alive`)
- 같은 파일 `:250` `find_ghost_orders` — 목록은 `Order.not_deleted_filter()` 로 휴지통을 뺀다(그대로 둔다)
- `foms/web/admin/naver_ingest.py:2079` `_ghost_discard_view`(권한만 겹치는 자리)
- `foms/web/admin/naver_ingest.py:2113` `_pane_context`
- `foms/web/admin/naver_ingest.py:657` 이력 탭이 휴지통 주문을 `closed` 로 접는 선례
- `templates/admin/partials/naver_workbench_pane.html:196-201` 머리줄 배지 무리
- `templates/admin/partials/naver_workbench_pane.html:494` `{% if ghost_discard.applicable %}` 블록 시작
- `foms/services/orders/soft_delete.py` — 삭제 메타(누가·언제·사유)는 `structured_data['delete']` projection
- `foms/services/orders/state_axes.py:259` `read_deleted`
- `static/js/admin/naver-workbench.js:520` 성공 후 `softRefresh()`

## 함정

- 휴지통 주문은 `session.get(Order, id)` 로 여전히 잡힌다(소프트 삭제). 필터는 목록 쪽에만 있다.
- `deleted_at` 은 `models.Order` 에서 **DateTime 컬럼**이고, 레거시 축은 `status == 'DELETED'` 다. 둘 다 본다.
- 시각 표시는 KST 로 낸다. 저장은 naive=UTC 규약이다(`foms/services/datetime_kst.py`).
- 문장을 고칠 때 **집 수**와 **상품주문 링크 수**를 섞지 않는다. `alive` 는 집 단위 dict 이고
  `bucket["link_count"]`·`bucket["canceled"]` 는 링크 수다.
- 기존 테스트가 문장을 문자열로 물고 있을 수 있다. 바꾼 문장에 맞춰 **기존 테스트도 통과**해야 한다
  (W1 이 실패를 보면 그 파일은 W3 소유이므로 CEO 에게 보고한다).

## 검증 명령 (완료 기준)

```
cd /c/tmp/foms-s-s0907-143127 && pwd
python -m pytest tests/services/integrations -q
python -m pytest tests/domains/test_foms_namespace_imports.py -q
python -c "import app; print('APP_OK')"
```

셋 다 통과해야 완료다. 새 테스트는 사실 표기와 문장 두 축을 각각 red 로 만들 수 있어야 한다
(구현 전에 돌리면 실패하는 테스트여야 한다는 뜻).
