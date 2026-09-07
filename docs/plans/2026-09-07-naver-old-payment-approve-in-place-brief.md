# 정리 계획 카드에서 **옛 결제 취소·반품 승인**까지 (2026-09-07)

## 0. 사용자 요구 (원문)

> 기존 주문 취소 요청(네이버) > 재결제 건인데 / 기존 주문을 한 화면에서 취소, 반품 >
> 승인까지 할 수 있게 해 줘야 될 거 아냐

지금 화면은 "네이버가 아직 확정하지 않았습니다 — 확정된 뒤에 정리하세요"라고만 적고,
확정시킬 방법을 이 화면에 두지 않는다. 담당자는 판매자센터로 나가야 한다.

## 1. 운영 실데이터 (production, 2026-09-07 read-only 조회 · 확정 사실)

화면: `/admin/naver-ingest/triage?tab=work&f=all&link_id=2215` (김선미)

| 무엇 | 값 |
|---|---|
| 지금 집 | `2026090764605051` · 기준 링크 **2215** · `PAYED`(살아 있음) · 미연결(COLLECTED) |
| 후보 주문 | **#5158** (김선미) |
| 후보에 붙은 옛 집 | `2026090498433601` · 링크 **2162~2170 (9건)** · 전부 `CANCEL_REQUEST` / `claimType=CANCEL` |

즉 후보 집계 코드는 `all_pending`. 그래서:

- `repay_reconcile.run_gate("all_pending")` → `(False, "네이버가 아직 취소를 확정하지
  않았습니다 — 확정된 뒤에 정리하세요")` → `정리 실행` 비활성.
- 후보 표 권고도 없음(2026-09-07 쌍 판정에서 `all_pending` 은 권하지 않기로 확정).

**이 브리프의 일**: 그 칸에서 **옛 집의 취소·반품 승인**을 눌러 확정까지 갈 수 있게 한다.
run_gate 와 권고 규칙은 **건드리지 않는다** — 확정되면 저절로 열린다.

## 2. 이미 있는 재료 (새로 만들지 말 것 · 경로:행)

- 라우트: `foms/web/admin/naver_ingest.py:5130` `POST /admin/naver-ingest/<link_id>/cancel-approve`,
  `:5154` `.../return-approve`. 둘 다 `role_required(["ADMIN","MANAGER"])`,
  공통 몸통 `_enqueue_claim_approve`(`:5041`).
  **비동기다** — 큐에 넣고 워커가 네이버 HTTP 를 낸다(호출 IP 3슬롯 계약).
- 서버 술어: `fulfillment.is_cancel_approvable`(`:2268`) · `is_return_approvable`.
  **승인 대상은 이 술어로만 고른다.** 화면이 집 전체 수로 재진술하면 "3건 승인합니다"인데
  서버는 1건만 보낸다 — 불가역 경로에서 그 과대 진술이 곧 사고다(원 docstring).
- 지금 집(grp)용 계산 예시: `foms/web/admin/naver_ingest.py:4074~4088`
  (`cancel_approvable_count`·`return_approvable_count`·`*_approve_targets`).
- 지금 집용 버튼·모달: `templates/admin/partials/naver_workbench_pane.html:172~178`(게이트 set),
  `:410~430`(버튼), `:1600~1660`(모달), `static/js/admin/naver-workbench.js`(fetch 배선).
- 후보 쪽 링크 수집: `order_candidates._naver_facts`(`:493`) — 이미 후보 주문의 링크를
  한 번에 읽는다(집계·금액·`alive_rows`). 승인 재료도 **여기서 같은 조회로** 낸다.
- 정리 계획: `repay_reconcile.build_reconcile_plan`(`:171`) → 화면 `cand.reconcile[rel]`.

운영 게이트(확인함): `FOMS_NAVER_CANCEL_APPROVE_ENABLED=1`,
`FOMS_NAVER_RETURN_APPROVE_ENABLED=1`, `FOMS_NAVER_WORKBENCH_ENABLED=1`/`COHORT=all`.

## 3. 만들 것 (계약 초안 — 이름은 CEO 가 확정)

1. **후보 옛 집의 승인 재료**를 후보 행에 싣는다. 최소한:
   - `old_cancel_approve_targets` / `old_return_approve_targets`:
     `[{"link_id", "external_id", "amount"}]` — **서버 술어로 고른 것만**.
   - 개수는 목록 길이로 센다(따로 세지 말 것 — 두 수가 갈린다).
   - `link_id` 를 반드시 싣는다: 승인 라우트는 **옛 집의 링크 id** 를 받는다.
     지금 집 링크(2215)를 넘기면 엉뚱한 집이 승인된다.
2. **정리 계획 카드의 ⓘ '네이버 옛 결제' 자리**에 승인 버튼을 낸다.
   조건은 라우트와 **같다**: 게이트 ON + `claim_approve_can_act`(ADMIN·MANAGER) +
   대상 ≥ 1. 한쪽만 열면 눌린 버튼이 403 을 받는다.
3. **모달은 대상 목록을 재진술한다**(건수만 쓰지 말 것). 불가역 문구 필수:
   승인 시점에 환불이 확정되고 되돌릴 수 없다. 취소 승인에는 거절 API 가 없다.
4. 누른 뒤 화면이 **무슨 일이 일어났는지** 말한다: 큐에 들어갔다는 것과, 확정되면
   정리를 실행할 수 있다는 것. **즉시 `all_done` 이 되지 않는다** — 워커가 처리한다.

## 4. 하지 말 것

- `run_gate`·`UNSETTLED_CLAIM_CODES`·`RELATION_BY_CLAIM_PAIR`·`recommended_relation`
  **손대지 마라**(2026-09-07 에 방금 고친 축이다). 승인이 확정되면 `all_done` 이 되어
  기존 규칙이 저절로 연다.
- 지금 집 전용 모달 id(`#wb-modal-cancel-approve` 등)를 **재사용하지 마라** — 대상이
  후보마다 다르다. 링크 id 는 `data-*` 로 싣는다.
- 화면에서 승인 대상을 자기 술어로 다시 고르지 마라(서버 술어만). **모집단도 서버와
  같아야 한다** — `fulfillment.links_of_group` 으로 집을 모은 뒤 그 ORM 행에 술어를
  건다(CEO FIX 2026-09-07). 후보 표 조회(`order_id.in_(...)`)로 세면 **다른 FOMS
  주문에 붙은 형제**·**미연결 형제**·**`productOrder` 래퍼 없는 평평한 원본**이 빠져,
  화면이 2건이라 적고 서버가 3건을 보낸다.
- 자산 핀(`?v=…`)을 **한 줄만 올리지 마라.** 워크벤치 계약 테스트 5개가
  `markup.count("?v=…") == 2` 로 CSS·JS 두 핀의 동시 이동을 강제한다 — JS 만 고쳤어도
  두 줄을 함께 올린다(`tests/services/integrations/test_naver_fulfillment_err_at.py:62`
  외 4곳).
- 네이버 HTTP 를 web 에서 직접 내지 마라(워커 전용).
- 새 파이썬/테스트 파일은 **500줄 미만**, JS 는 **300줄 미만**. 이건 이 저장소의
  **규약이지 코드 강제가 아니다** — `tests/harness/test_file_size_ratchet.py` 는
  **존재하지 않는다**(2026-09-07 실측 확인). 게이트가 없으니 지키는 것은 사람 몫이고,
  넘길 것 같으면 파일을 새로 판다(공용 헬퍼는 한 벌로 공유해서 픽스처가 갈리지 않게).

## 5. 파일 소유권 (겹치면 안 됨)

| 워커 | 편집 허용 파일 |
|---|---|
| A | `foms/services/integrations/naver_commerce/order_candidates.py` |
| B | `foms/services/integrations/naver_commerce/repay_reconcile.py`, `foms/web/admin/naver_ingest.py` |
| C | `templates/admin/partials/naver_workbench_pane.html`, `static/js/admin/naver-workbench.js` |
| D | `tests/services/integrations/` (신규 파일 우선) |

## 6. 완료 기준

```bash
python -m pytest tests/services/integrations/ -q      # **실패 0 · skip 0** 으로 판정한다
# (2026-09-07 실측 기준선 1731 passed. '1900' 은 오기였다 — 수치를 외우지 말고
#  마지막 줄에 failed/error/skipped 가 하나도 없는지로 본다)
python -c "import app; print('APP_OK')"
```

계약 테스트(최소):
- 후보 옛 집이 `CANCEL_REQUEST` 9건이면 취소 승인 대상 9건이 **링크 id 와 함께** 실린다
  (운영값: 링크 2162~2170).
- 렌더: 그 카드에 취소 승인 버튼이 있고, 버튼이 무는 `link_id` 가 **옛 집 링크**다
  (지금 집 링크가 아니다 — 음성 대조군).
- 음성 대조군: 옛 집이 이미 `CANCEL_DONE` 이면 승인 버튼이 **없다**.
- 음성 대조군: `claim_approve_can_act` 이 아닌 role(STAFF)에게는 버튼이 없다.
- 음성 대조군: 승인 게이트 env 를 끄면 버튼이 없다.
- 승인은 `run_gate` 를 바꾸지 않는다 — 누른 직후에도 `정리 실행`은 여전히 막혀 있다
  (워커가 확정시키기 전까지).
