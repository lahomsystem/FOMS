# 실행 플랜 — AS 일정 매칭 링크 + 기준일 변경 감지

스펙: `docs/specs/2026-07-30-as-schedule-link-drift-design.md` (승인 후 착수)
브랜치: `deploy` (푸시는 세션 커밋만 cherry-pick)
원장: `docs/plans/2026-07-30-as-schedule-link-drift-ledger.md`

각 task 는 서브에이전트 위임 단위다. 완료 기준의 명령이 실제로 통과해야 DONE.

---

## T1 — 링크 서비스 (순수 함수)

**신규** `foms/services/orders/as_schedule_link.py`

```python
LINK_PATH = ("schedule", "as_visit", "schedule_link")
SOURCE_NEARBY = "as_nearby_modal"
SOURCE_SHIPMENT = "shipment_asrec"

def read_link(sd: dict) -> dict | None
def write_link(sd: dict, *, ref_order_id: int, ref_date: str, source: str,
               user_id: int | None, user_name: str, now: datetime) -> dict
def clear_link(sd: dict) -> bool
def ack_link(sd: dict, ref_date_now: str) -> bool          # ack_ref_date = 현재 기준일
def relink(sd: dict, ref_date_now: str) -> bool            # ref_date 갱신 + ack 해제
def evaluate_drift(link: dict | None, *, ref_current_date: str | None,
                   as_visit_date: str | None, ref_missing: bool) -> dict
    # -> {"state": "none|ok|ref_moved|both_moved|resolved|acked|ref_gone",
    #     "ref_order_id", "ref_date", "ref_current_date", "as_visit_date"}
```

- 판정표는 스펙 §4 그대로. 순수 함수 — DB·Flask 의존 금지(테스트 용이).
- 날짜 비교 전 `_normalize_date_str` 동등 유틸로 정규화(문자열 `2026-8-5` 대비).

**완료 기준**
`python -m pytest tests/domains/test_as_schedule_link.py -q` green — 신규 테스트로
6개 state 전부 + 링크 없음/기준일 없음/ack 후 기준일 재변경 케이스 커버.

---

## T2 — 링크 API

**수정** `foms/api/cs/as_orders.py`

- 라우트 `POST /<int:order_id>/as/schedule-link`, `@login_required @erp_edit_required`
  (선례 `as_orders.py:801-803`).
- `POLICY_AS_SCHEDULE_LINK = "STATE_AS_SCHEDULE_LINK"` 상수 추가(선례 `:73`).
- `_run_sd_mutation(..., command_id="AS_SCHEDULE_LINK", body=data)` 로 쓰기.
- action 4종: `link` / `relink` / `ack` / `unlink`.
- 서버가 기준 주문을 재조회해 현재 시공일을 확정하고(`erp_construction_date` → 없으면
  `scheduled_date`) 클라 `ref_date` 와 다르면 서버 값 채택.
- 검증 실패 400 / 기준 주문 없음·DELETED 404 / 무결성 409.
- `link`·`unlink` 시 `append_system_log(sd, text=...)` 로 AS 타임라인에 흔적:
  `"기준 일정 매칭: 주문 #3694 (2026-08-05)"` / `"기준 일정 매칭 해제"`.
- 성공 후 `_invalidate_shipment_asrec_caches("api_as_schedule_link")`.

**완료 기준**
`python -m pytest tests/domains/test_as_schedule_link_api.py -q` green — 신규 테스트:
비로그인 302·편집권한 없음 차단·link 후 sd 반영·자기 자신 링크 400·존재하지 않는
기준 주문 404·unlink 후 키 부재·system 로그 1건 append 확인.

---

## T3 — 가까운 일정 찾기 모달: `이 일정에 매칭` 버튼

**수정** `static/js/cs/as-dashboard.js`

- `renderResults()`(`:1410-1472`) 행 하단 버튼 그룹에 `.js-as-schedule-link` 추가.
  `data-ref-order-id={item.id}`, `data-ref-date={item.date}`.
- 위임 바인딩은 `addAsDashboardListener`(`:81-101`) 사용, 핸들러 첫 줄에
  `e.stopPropagation(); e.preventDefault();`(행이 `<a>` — 선례 `:1592-1596`).
- 기준 AS id 는 `_searchState.excludeId`(`:1573`). 없으면 버튼 자체를 렌더하지 않는다.
- 성공: 버튼 `매칭됨` + `disabled`, 같은 모달 내 다른 행 버튼은 `매칭 변경`으로 표기.
  실패: 행 하단에 빨강 메시지(무음 실패 금지 — 이번 세션 출고 버튼 사고와 동일 함정).
- `fetch` 는 `.catch` 필수, 응답은 텍스트로 받아 방어적 파싱(선례: 이번 세션
  `shipment-dashboard.js` `parseJsonResponse`).

**수정** `templates/cs/partials/as_dashboard_body.html` — `as-dashboard.js` 핀 범프
(`?v=20260730g` → 다음 값), 저장소 전체 동일 핀 동시 범프.

**완료 기준**
`python -m pytest tests/domains/test_as_dashboard_schedule_link_render.py -q` green —
실제 렌더 응답에 버튼 클래스/핀 존재 확인 + 저장소 핀 grep 일치 테스트.

---

## T4 — 드리프트 계산 + AS 대시보드 표시

**수정** `foms/services/as_dashboard_display.py` (`apply_as_dashboard_row_display_fields`, `:324`)

- 렌더 대상 행에서 `schedule_link` 를 모아 `ref_order_id` 집합 → `Order.id.in_(ids)` 1회
  조회(`id, status, deleted_at, erp_construction_date, scheduled_date`).
- 행마다 `evaluate_drift(...)` 결과를 `row.schedule_link_drift` 로 부착.
- 페이지 합계 `drift_count` 를 뷰 컨텍스트로 전달(`foms/web/cs/as_dashboard.py:186`).

**수정** `templates/cs/partials/as_dashboard_body.html`

- 상단 배너: 기존 `#as-timeline-hint`(`:39-42`) 아래에 `#as-schedule-drift-banner`,
  `{% if drift_count %}` 게이트. 문구 `현재 목록에서 기준 일정이 변경된 AS N건`.
  마크업/톤은 도면 배너(`templates/drawing/partials/workbench_detail_body.html:961-984`) 참조,
  CSS 는 인라인 금지 — `static/css/foundation/erp-pro.css` 체계 사용.
- 행 배지: 상태별 색(ref_moved=빨강, both_moved=주황, ref_gone/acked=회색) + 기준 표기
  `기준 #3694 8/5 → 8/12`.
- 모바일 카드(`templates/cs/partials/as_mobile_order_card.html`)에도 같은 배지.

**완료 기준**
`python -m pytest tests/domains/test_as_dashboard_drift_render.py -q` green — 시드:
AS 1건 + 기준 주문 1건 링크 → 기준 시공일 변경 → 렌더 응답에 배너·배지 존재,
변경 없을 때 배너 부재. + `python -m pytest tests/performance/test_perf_regression_guard.py -q` green.

---

## T5 — 재적용 / 무시 / 연결 해제 액션

**수정** `static/js/cs/as-dashboard.js`

- 배지·배너의 액션 버튼 3종 위임 바인딩(`addAsDashboardListener`).
- `재적용`: ① `POST /api/update_order_field` `{order_id, field_name:"as_visit_date", value:Ds}`
  (기존 `saveDateField` 경로 재사용 — 새 날짜 쓰기 코드 금지) → 성공 시
  ② `POST .../as/schedule-link {action:"relink"}` → 행 갱신.
  `both_moved` 상태면 사전 `confirm`.
- `무시`: `{action:"ack"}`. `연결 해제`: `{action:"unlink"}` + confirm.
- 모든 실패는 화면에 노출(무음 금지).

**완료 기준**
`python -m pytest tests/domains/test_as_schedule_link_api.py -q` green(relink/ack 케이스 포함)
+ 수동: 로컬에서 재적용 후 `as_log` 에 `방문일 확정` system 항목 1건 확인.

---

## T6 — 출고 경로(A) 링크 동기화

**수정** `foms/services/shipment/as_recommendation.py`

- `apply_as_recommendation`(`:196-271`): AS 주문 sd 에 `write_link(source=SOURCE_SHIPMENT,
  ref_order_id=ship.id, ref_date=ship_date)` — 이미 같은 tx 에서 AS sd 를 쓰므로
  추가 커맨드 없이 기존 mutation 안에 포함.
- `cancel_as_recommendation`(`:274-`): `clear_link` (단, `source != SOURCE_SHIPMENT`
  이거나 `ref_order_id != ship.id` 면 건드리지 않는다 — 사용자가 나중에 손으로 다른
  기준에 매칭했을 수 있다).

**완료 기준**
`python -m pytest tests/domains/test_shipment_as_recommendations.py -q` green
(기존 `:616` "legacy 직접쓰기 흔적 없음" 단언과 충돌하지 않는지 확인 — 신규 키는
`schedule_link` 이므로 통과해야 정상) + apply 후 `schedule_link` 존재를 단언하는 케이스 추가.

---

## T7 — 기존 적용분 백필 (1회성)

**신규** `tools/ops/backfill_as_schedule_links.py`

- `sd.shipment.recommendations` 가 있는 출고 주문을 순회 → 각 `as_order_id` 의 AS 주문에
  `schedule_link`(source=`shipment_asrec`, ref_date=`applied_visit_date`) 를 채운다.
- 이미 링크가 있으면 건너뛴다. `--dry-run` 기본, `--execute` 로만 쓰기.
- 대상 조회는 JSONB 컨테인먼트가 아니라 `OrderEvent.event_type == "AS_RECOMMENDATION_APPLIED"`
  의 `order_id` 집합으로 좁힌다(인덱스 사용, `models.py:770-784`).

**완료 기준**
로컬 dev DB `--dry-run` 출력에 대상 건수 표시 + `--execute` 후 재실행 시 0건(멱등).

---

## T8 — 최종 검증·커밋·푸시

- `python -c "import app; print('APP_OK')"`
- `python -m pytest tests/postgres -q` (PG 레인 전수 — JSONB 쓰기 포함)
- `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` exit 0
- 커밋(한글, `-F` 파일 방식) → `git push origin HEAD:deploy`(세션 커밋만)
- `python tools/harness/ci_watch.py <SHA> deploy` exit 0
- production 승격은 사용자 승인 후 cherry-pick.

**완료 기준** 위 명령 전부 exit 0 + CI green.

---

## 함정 체크리스트 (브리프에 반드시 포함)

1. JS 수정 = `?v=` 핀 전 저장소 동시 범프(서비스워커 stale).
2. AS 대시보드 JS 는 fragment swap 재실행 — 리스너는 `addAsDashboardListener` 만 사용.
3. 결과 행이 `<a>` 이므로 버튼 핸들러는 `stopPropagation` + `preventDefault`.
4. JSONB 는 `_run_sd_mutation` 경유(직접 `structured_data` 대입 금지).
5. `as_log` append-only, `type="system"` 은 서버 전용(`coerce_client_log_type` 이 클라 입력 거부).
6. GET 렌더 경로에서 DB write 금지(`resolved` 자동 갱신은 다음 쓰기 때).
7. 무인덱스 JSONB 필터 금지 — 드리프트는 렌더된 행 집합 한정.
8. 실패 무음 금지 — 이번 세션 출고 `추가` 버튼 사고(errEl null + catch 부재)와 같은 형태 반복 금지.
