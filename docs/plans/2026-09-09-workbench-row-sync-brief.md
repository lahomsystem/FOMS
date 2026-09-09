# 워크벤치 처리 탭 — 왼쪽 줄이 거짓말한다 (2026-09-09 담당자 신고)

작업 트리: `c:\tmp\foms-s-s0908-102606` (브랜치 `session/s0908-102606`, `origin/deploy` = `da4ec29ad`).
**모든 워커는 첫 명령으로 `cd /c/tmp/foms-s-s0908-102606 && pwd` 를 찍고 그 안에서만 일한다.**
git 명령 금지(커밋·푸시·rebase 전부 총괄 몫). CRLF 보존.

## 담당자가 본 것 (운영, 2026-09-09)

주소: `https://lahom-production.up.railway.app/admin/naver-ingest/triage?tab=work&f=all&link_id=2295`
임선경 · 상품주문 `2026090990409101` · 3건 묶음 · 추가결제 · **주문 #5200** · 이미 **발송처리 완료**
(pane 이 `발송처리 2026-09-09 10:53` 과 `이 주문은 발송처리가 끝났습니다.` 를 낸다).

그런데 **왼쪽 큐 줄**은 이렇게 말한다:

```
3건 묶음 | 추가결제 | 발주확인 완료 | 발송기한 10-01 | 주문 #5200 | 규격 입력할 차례
```

신고 두 줄:

1. "추가결제로 발송 처리까지 끝났는데, 이 텍스트(`규격 입력할 차례`) 필요없지?"
2. "오른쪽 refresh 된 상태를 왼쪽에도 즉시 반영하도록 변경해 봐"

## 결함 A — `규격 입력할 차례` 가 사실을 안 본다

`templates/admin/naver_workbench.html:693-695`

```jinja
{% set row_kind = 'stop' if row_locked
                  else ('spec' if group.order_id
                        else ('wait' if group.place_pending else 'go')) %}
```

`group.order_id` **하나만** 보고 `spec` 으로 떨어진다. 그래서

* 규격을 이미 다 넣은 집도 `규격 입력할 차례`,
* 발송처리까지 끝난 집도 `규격 입력할 차례`.

같은 서버가 이미 더 정확한 값을 들고 있다:

* `foms/web/admin/naver_ingest.py:1117` — `next_step` 은 `"규격 입력"` 을
  **`order_has_spec_rows(lead["_order"])` 가 False 일 때만** 낸다. 단 이 필드는 이력 탭 행
  (`_history_group_row`)의 것이다 — **처리 탭 집에 같은 키가 있는지 워커가 직접 확인할 것.**
* `_group_queue`(처리 탭 집의 유일한 빌더 — `_place_groups` 도 이 함수를 부른다)는
  집 단위로 `dispatched`(집 전체가 나갔다) · `dispatched_any`(하나라도 나갔다) ·
  `dispatched_count` · `place_pending` · `canceled` 를 이미 싣는다.
  `_dispatched_count` / `_dispatched_any` 주석을 반드시 읽을 것 — **두 값의 뜻이 다르다**
  (우리 표식 vs 우리 표식+네이버 원본).
* pane 은 같은 사실을 `dispatched` 로 읽어 `발송처리 완료` 배지를 낸다
  (`templates/admin/partials/naver_workbench_pane.html:358-360`, `:667-672`).

`.wb-can` 라벨 자리: `templates/admin/naver_workbench.html:808-813`.
`row_kind` 는 색띠 클래스(`wb-row--{{ row_kind }}`, `.wb-can--{{ row_kind }}`)와
배지 억제 조건(`:768`, `:781`)에도 쓰인다 — 값을 바꾸면 그 셋이 같이 움직인다.

**설계 원칙(프로젝트 규약)**: 판정은 서버가 한 번만 한다. 템플릿이 같은 식을 다시 쓰면
한쪽만 고쳐졌을 때 조용히 어긋난다(`_attach_row_flags` docstring 의 H1 사고). `row_kind`
계산을 서버로 올리는 것을 **1순위 후보**로 검토하라 — 다만 그러면 pane 프래그먼트도
같은 값을 낼 수 있어야 결함 B 가 쉬워진다.

## 결함 B — pane 만 갈리고 왼쪽 줄은 그대로다

`static/js/admin/naver-workbench.js:1126-1137` `swapPane()` 은 `#wb-pane` **하나만**
`replaceWith` 한다. 발주확인·발송처리·다시 읽기·정리 실행 뒤 pane 은 새 사실을 말하는데
왼쪽 줄의 배지(`발주확인 완료`·`주문 #N`)와 `.wb-can` 라벨은 **다음 전체 새로고침까지 옛
값**이다. 담당자는 한 화면에서 서로 다른 말을 듣는다.

관련 자리:

* `markCurrent(row)` (`:1139-1148`) — 이미 왼쪽 줄을 만지는 유일한 자리.
* `watchFulfillment` / `watchOriginAct` 완료 뒤 pane 을 다시 받는 경로
  (`submitRefresh` `:1693`, 승인·정리 갈래).
* 행 매칭 함정: 목록 행의 `data-link-id` 는 **모집단 안 최대금액 링크**이고
  `selected_group.id` 는 집 전체에서 뽑은 값이라 **두 값이 갈릴 수 있다**
  (`naver_workbench.html:706-711` 주석). 집 동일성은 `link_ids` 포함으로 본다 —
  단순히 `data-link-id` 로 찾으면 못 찾는 집이 생긴다.
* `paneOfflist` (`:1108-1125`) — 프래그먼트에 목록이 없어 서버가 못 하는 판정을 JS 가
  들고 다니는 선례. 같은 규율을 따를 것: **술어를 JS 에 두 벌 만들지 마라.**

### 두 갈래 (CEO 가 고른다)

* **갈래 1 — 서버가 줄 HTML 을 함께 준다.** 목록 루프의 줄 마크업을 include/macro 로 빼
  pane 프래그먼트 응답에 같은 줄을 렌더해 실어 보내고, JS 가 통째로 갈아 끼운다.
  SSOT 가 한 벌로 남는다. **함정**: 템플릿 매크로 추출은 이 저장소에서 smoke 사각
  CI red 2종을 낸 이력이 있다(`project_template_macro_extraction_contract_gap`).
* **갈래 2 — 서버가 값만 준다.** pane 루트에 `data-row-kind` 등 표시 값 몇 개를 싣고
  JS 가 `.wb-can` 글자와 클래스만 갈아 낀다. 추출 위험은 없지만 **배지 규칙을 JS 가
  다시 쓰기 시작하면 두 벌이 된다** — 값의 범위를 라벨·색띠로 좁게 끊을 것.

## 손대면 안 되는 축

`run_gate` · `UNSETTLED_CLAIM_CODES` · `RELATION_BY_CLAIM_PAIR` · `recommended_relation` ·
`discard_policy` · 유령 모집단/`can_discard` · `_discard_verdict` ·
`_group_matches_filter` 의 필터 술어(칩 숫자와 목록 모집단의 SSOT) ·
`_attach_row_flags` 의 `locked`/`can_pick` 판정.

**모집단·잠금·체크박스는 이 작업의 범위가 아니다. 표시 축만 고친다.**

## 자산 핀 (한 워커가 몰아서)

`templates/admin/naver_workbench.html:22`(CSS)·`:1360`(JS) 두 줄이 **함께** 움직여야 한다
(서비스워커 staticCacheFirst). 지금 값 `20260909a` → `20260909b`.
같은 값을 하드코딩한 계약 테스트 **6개**를 함께 고친다:

```
tests/services/integrations/test_naver_backfill_route.py
tests/services/integrations/test_naver_fulfillment_err_at.py
tests/services/integrations/test_naver_origin_cleanup.py
tests/services/integrations/test_naver_post_action_refresh.py
tests/services/integrations/test_naver_repay_followup.py
tests/services/integrations/test_naver_workbench_async_result.py
```

`tests/services/integrations/test_naver_dock*.py` 의 `20260909a` 는 **도크 핀**
(`templates/orders/partials/erp_order_js.html`)이다 — **건드리지 마라.**

## 검증 (총괄이 직접 재실행한다)

```bash
cd /c/tmp/foms-s-s0908-102606
python -m pytest tests/services/integrations -q
python -c "import app; print('APP_OK')"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1
```

`docs/harness/*.json` 은 테스트 실행이 재생성한다 — 커밋 전 `git checkout -- docs/harness/`.

## 새 테스트에 요구하는 것

* 결함 A: **발송처리가 끝난 집**과 **규격이 이미 들어간 집**에서 `규격 입력할 차례` 가
  안 나온다. 음성 대조군 필수 — **주문이 있고 규격이 없고 발송 전인 집에서는 그대로 나온다**
  (대조군은 같은 모집단 안에서 고른다).
* 결함 B: pane 을 갈아 끼운 뒤 왼쪽 줄이 새 값을 말한다. JS 순수 함수는 Node 로 돌린다
  (`tests/services/integrations/test_naver_dock_autofill_wire.py::_run`,
  `test_naver_dock_width_live.py::_needs_node` 가 기존 하네스).
* 문자열 존재 단언만 쓰지 마라 — 갈래를 `if (false)` 로 꺼도 통과하는 단언은 무효다
  (2026-09-09 에 실제로 한 번 잡혔다).
