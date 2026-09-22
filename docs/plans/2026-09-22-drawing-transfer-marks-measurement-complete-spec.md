# 도면 전달 = 실측완료 표시 + 단계 이동 (Spec)

- 작성 2026-09-22 · 브랜치 `deploy`
- 등급: 코어 변경(상태 축) — Spec → 승인 → 구현

## 1. 문제

"실측 완료"라는 이름이 서로를 갱신하지 않는 **두 축**에 붙어 있다.

| 표면 | 정체 | 쓰는 경로 | stage | `Order.measurement_completed` |
|---|---|---|---|---|
| PC 실측 대시보드 "도면 전달" 버튼 | MEASURE quest 승인 | `POST /api/orders/<id>/quest/approve` (`static/js/measurement/drawing-transfer-btn.js:33`) | MEASURE→DRAWING | **안 찍힘** |
| 모바일 "실측 완료" 버튼 | 같은 quest 승인 | 같은 API (`static/js/foms/erp-quest-approve.js:140`) | MEASURE→DRAWING | **안 찍힘** |
| 태블릿 실측 폼 저장 후 승인 | 같은 quest 승인 | 같은 API (`static/js/foms/tablet-measure-form.js:1635`) | MEASURE→DRAWING | **안 찍힘** |
| 지방·자가실측 체크리스트 0번 체크박스 | 평면 불리언 | `POST /api/update_regional_status` (`foms/api/orders/regional.py:139`) | 그대로 | 찍힘 |

전이 엔진은 main 축만 쓴다 — `foms/services/orders/order_transition_service.py:192`
(`COMPLETE_MEASUREMENT`, axis=`AXIS_MAIN`)이고 `quest_transition_service.py` 전체에
`measurement_completed` 라는 이름이 없다.

결과: 버튼 확인문은 이미 "실측을 완료하고 도면 단계로 넘길까요?"
(`foms/services/orders/quest_approve_cta.py:36`)라고 약속하는데 실제로는 단계만 넘어가고
실측완료 표시는 꺼진 채 남는다. **문구와 동작이 어긋나 있다.**

## 2. 결정 (2026-09-22 사용자 승인)

1. 적용 범위: **지방(`is_regional`)·자가실측(`is_self_measurement`) 주문만.** 일반 ERP
   주문은 지금처럼 단계만 이동한다. 체크리스트 API 가 이미 막고 있는 경계
   (`regional.py:125-133` `_order_or_404`)와 같은 잣대를 쓴다.
2. 표면 범위: **서버 한 곳**에서 처리한다. quest approve 라우트가 정본이므로
   PC·모바일·태블릿이 자동으로 같이 고쳐진다.
3. 모바일 v3 셸(`templates/partials/v3/persona_home_sales.html`)에 승인 버튼이 없는 건
   **이번 범위 밖.** 사용자 판정: "v3 는 사용 안 함, 삭제 검토" → 별도 과제로 남긴다(§7).

## 3. 설계

### 3-1. 체크리스트 writer 추출 (행동 불변)

`foms/api/orders/regional.py` 의 `_mutate`(174-207행) 안에 있는 3동작 —
컬럼 setattr + `OrderEvent(REGIONAL_CHECKLIST_UPDATED)` + `record_field_changes(path=평면 컬럼명)` —
을 세션을 인자로 받는 순수 함수로 뽑는다.

```
foms/services/orders/regional_checklist.py
    mark_checklist_flag(session, order, field, value, *, actor_user_id, change_set_id) -> bool
```

- `before == after` 면 원장 행을 만들지 않고 `False` 반환(기존 무변경 억제 규칙 그대로).
- `regional.py:_mutate` 는 이 함수 호출로 치환한다. **기존 동작·원장 path·이벤트 타입은
  한 글자도 바뀌지 않는다**(`tests/domains/test_audit_gap_regional.py:226-235` 가 강제).

### 3-2. 전이 직후 호출

`foms/api/quest.py` — `auto_transitioned` 계산(441행) 과 `db.commit()`(445행) **사이**.

조건 4개를 모두 만족할 때만 쓴다:

1. `is_complete` 이고 `transition_result is not None`
2. `transition_result.replayed` 가 아님 (idempotency replay 는 side effect 없음)
3. 전이 대상이 DRAWING (`current_stage_code == "MEASURE"`)
4. `order.is_regional or order.is_self_measurement`

감사: `log_access(action="ORDER_CHECKLIST_UPDATED", detail.change_set=<같은 uuid>)` 를
원장과 같은 `change_set_id` 로 남긴다(`regional.py:229-240` 와 같은 모양).

버전 축: 이 라우트는 `execute_order_mutation` 밖이지만 같은 요청의 `transition_order` 가
이미 `mutation_version` bump 를 한다. 별도 bump 를 추가하지 않는다.

### 3-3. 왜 전이 서비스에 안 넣나

`quest_transition_service.advance_stage_on_quest_completion` 은 docstring 이 "전이만
한다"를 못박았고, RECEIVED→MEASURE 전이에서도 호출된다. 여기에 플래그를 얹으면
`_STAGE_ADVANCE` 표의 의미가 오염되고 잘못된 stage 에서 켜질 위험이 생긴다.

### 3-4. 왜 JS 2콜이 아닌가

`tests/domains/test_measurement_drawing_transfer_button.py::test_transfer_js_calls_quest_approve_only`
가 단일 호출을 리터럴로 고정한다. 2콜은 비원자적이라 "단계는 넘어갔는데 체크는 안 켜짐"이
생긴다.

## 4. 부수효과 (알고 들어간다)

`measurement_completed=True` 가 되면 **읽기 판정**이 즉시 달라진다:

- `foms/services/erp_display.py:53` 자가실측 4체크 — 나머지 3개가 이미 켜져 있던 건은
  실측 대시보드에서 빠지고 시공 쪽으로 옮겨 보인다.
- `foms/web/measurement/dashboard.py:737` 상차 예정 알림 버킷 편입.
- `foms/services/orders/measure_progress.py:207` 판정 근거가 `stage` → `completed` 로 바뀜
  (결과 문구는 둘 다 "실측 후"라 사용자 눈에는 같다).

단, **자동 승격(status→SCHEDULED)은 일어나지 않는다.** 그 승격은 브라우저가 행의 체크박스
DOM 을 전부 보고 쏘는 별도 요청이다(`regional_dashboard.html:1371-1410`,
`self_measurement_dashboard.html:877-892`). 서버에서 플래그 하나만 쓰면 트리거되지 않는다.
어차피 전이로 stage 가 DRAWING 이 되어 행이 MEASURE 버킷을 떠난다.

## 5. 검증

- 새 계약: `tests/domains/test_measurement_drawing_transfer_button.py` T11 에
  `moved.measurement_completed is True` 단언 추가(자가실측 건).
- 새 계약: 일반 ERP 주문(지방·자가실측 아님)은 전이 후에도 `measurement_completed` 가
  False 로 남는다 — 음성 대조군.
- 새 계약: 체크리스트 원장 path 가 버튼 경로에서도 `measurement_completed` 로 같게 남는다.
- 회귀: `tests/domains/test_audit_gap_regional.py`, `tests/postgres/test_data_measurement.py`,
  `tests/domains/test_orders_boundary_contract.py`, `tests/domains/test_measure_progress.py`.
- `python -c "import app; print('APP_OK')"`
- push 전 `scripts/ops/pre_push_smoke.ps1` exit 0.
- 줄이 밀려 라인 핀이 깨지면 `python tools/harness/order_mutation_writer_scan.py` 로
  `docs/harness/foms_order_mutation_writer_inventory.json` 재생성.

## 6. 범위 밖 (건드리지 않는다)

- `drawing_status` 축(도면팀 도면 **파일** 전달, `foms/api/drawing/erp_orders_drawing.py`).
- 버튼 문구·CSS·마크업(T8/T9 계약 그대로).
- CTA 노출 판정(`foms/services/measurement/drawing_transfer_cta.py`).

## 7. 별도 과제로 남기는 것

**모바일 v3 셸 폐기 검토.** `templates/measurement/partials/dashboard_main.html:57` 이
`shell_variant != 'v3'` 로 v2 실측 표면을 막아서, v3 코호트 영업 담당자는 실측 목록에서
승인 버튼을 못 만난다(주문상세로 들어가야 나온다). 사용자 판정은 "v3 는 사용 안 함,
삭제 검토" 다. 코호트 실사용자 수 확인 → 삭제 범위 산정이 선행이라 이번 작업에 섞지
않는다.
