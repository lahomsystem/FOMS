# 출고 대시보드 AS 일정 추천 기능 Spec
> 작성일: 2026-05-04 | 상태: 🟡 승인대기

## 0. 조사 요약

### 0.1 확인한 기존 구현
- AS 대시보드의 "가까운 일정 찾기"는 `templates/cs/partials/as_dashboard_body.html`에서 `/api/orders/nearby`를 호출한다.
- `/api/orders/nearby` 구현은 `foms/api/orders/nearby.py`에 있으며, 현재 후보를 `construction` 일정으로 제한하고 AS 상태(`AS_RECEIVED`, `AS_COMPLETED`)는 제외한다.
- 이 API는 `_MAX_RESULTS = 5`로 거리순/날짜순/복합 추천을 각각 5건만 반환한다.
- 출고 대시보드는 `foms/web/shipment/dashboard.py` + `templates/shipment/partials/dashboard_main.html` 조합이다.
- 출고 row의 시공자는 `structured_data.shipment.construction_workers`에 저장되고, 기존 저장 API는 `POST /api/erp/shipment/update/<order_id>`이다.
- AS 방문일은 `structured_data.schedule.as_visit.date`에 저장되고, `OrderScheduleDate(kind='as_visit')`는 `foms/services/order_date_sync.py`의 SQLAlchemy `before_flush` 리스너로 동기화된다.

### 0.2 요구 해석
이번 기능은 기존 AS 화면의 방향을 그대로 호출하는 기능이 아니다.

기존 방향:
- AS 건 1개를 기준으로 인근 출고/시공 일정 찾기

이번 기능의 방향:
- 출고 대시보드에 표시된 출고건들을 기준으로, 인근 AS 건을 각 출고건당 최대 2건 추천
- 사용자가 추천 모달에서 `추가`를 누르면 해당 AS 건의 방문일을 기준 출고건 날짜로 잡고, 기준 출고건의 시공자를 AS 건에 자동 입력
- 기준 출고건에 시공자가 없으면 AS 건의 시공자도 공란, 즉 `construction_workers = []`
- 사용자가 출고 대시보드 추천 모달의 `추가된 AS 일정`에서 해당 AS 건을 취소/삭제하면 AS 방문일을 비우고, 출고 대시보드에서도 해당 AS 일정이 빠진다.

### 0.3 병렬 리뷰 결론
- 기존 `/api/orders/nearby`를 프론트에서 출고 row마다 반복 호출하면 `N * geocode`가 되어 느리고, 기존 5건 제한도 요구와 충돌한다.
- 새 기능은 batch API가 맞다. 한 번의 요청으로 현재 화면의 출고건들을 받아, 후보 AS 건 목록을 한 번만 로드하고 주소/좌표 캐시를 공유해야 한다.
- 추천 적용/취소는 화면에서 단순히 문자열을 넣고 빼는 일이 아니라 AS 방문일과 시공자를 함께 갱신해야 하므로, 부분 성공을 막기 위해 atomic apply/cancel API가 필요하다.

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
출고 대시보드의 조회 버튼 옆에 `AS일정 추천` 버튼이 생긴다.

버튼 클릭 시:
- 현재 출고 대시보드에 표시된 일반 출고/시공 row를 기준 대상으로 삼는다.
- 각 출고건 주소 주변의 미완료 AS 건을 최대 2건씩 추천한다.
- 추천 결과는 모달에 출고건별 그룹으로 표시한다.
- 각 추천 AS 항목에는 AS 주문번호, 고객명, 주소, 현재 AS 방문일, 거리/추천 사유, 적용될 시공자가 보인다.
- `추가` 버튼을 누르면 해당 AS 건의 방문일과 시공자가 저장되고, 결과가 성공/실패 상태로 표시된다.
- 모달에는 이미 추가된 AS 일정도 함께 표시되며, 각 항목에서 `취소` 또는 `삭제`를 눌러 출고 대시보드 일정과 AS 대시보드 방문일을 함께 제거할 수 있다.

### 1.2 기능 요구사항
1. `templates/shipment/partials/dashboard_main.html`의 `.erp-pro-filter-actions` 내부에서 기존 `조회` submit 버튼 바로 옆에 `AS일정 추천` 버튼을 추가한다.
2. 버튼은 폼 submit이 되면 안 되므로 `type="button"`으로 구현한다.
3. 시공팀 조회 전용 사용자는 저장 권한이 없으므로 버튼을 숨기거나 disabled 처리한다. 기준은 기존 `can_edit_shipment`를 따른다.
4. 추천 API는 현재 화면의 출고건 order id 목록과 선택 기준일을 받아 batch로 처리한다.
5. 기준 대상은 일반 출고/시공 건이다. `AS`, `AS_RECEIVED`, `AS_COMPLETED`, `DELETED` 상태는 기준 대상에서 제외한다.
6. 후보 대상은 미완료 AS 건이다. 기본 후보 상태는 `AS`, `AS_RECEIVED`이며 `AS_COMPLETED`, `DELETED`는 제외한다.
7. 후보 AS 건은 주소가 있어야 추천 가능하다. 주소 없음/좌표 실패는 대상별 메시지로 표시한다.
8. 추천은 실제 소요시간 30분 이하인 AS를 출고건당 최대 2건 반환한다. 실제 경로 거리는 참고 표시값이며 추천 제외 기준으로 쓰지 않는다.
9. 전체 결과 수를 5건으로 제한하지 않는다. `출고건 수 * 2`가 기본 상한이다.
10. 같은 AS 건이 여러 출고건 주변에 잡힐 수 있다. 모달에서는 중복 추천을 허용하되, 이미 적용된 AS 건은 다른 그룹에서 `이미 추가됨` 상태로 바꾼다.
11. `추가`는 AS 건에 다음 값을 한 트랜잭션으로 저장한다.
    - `structured_data.schedule.as_visit.date = 기준 출고건의 시공일`
    - `structured_data.shipment.construction_workers = 기준 출고건의 construction_workers`
12. 기준 출고건 시공자가 없으면 `construction_workers = []`로 저장한다. UI 문구는 `시공자 공란으로 적용`으로 표시한다.
13. 기준 출고건에 시공자가 여러 명이면 그대로 여러 명을 복사한다.
14. 후보 AS 건에 이미 다른 방문일이 있으면 모달에서 현재 방문일을 표시하고, 다른 날짜로 덮어쓰기 전에 확인 문구를 보여준다.
15. 저장 성공 후 모달 항목은 `추가 완료`로 바뀌고 버튼은 비활성화한다.
16. 저장 실패 시 모달을 닫지 않고 서버 메시지를 항목 안에 표시한다.
17. `추가` 성공 시 AS 건은 출고 대시보드의 해당 날짜 일정에도 나타나야 한다. 원장은 `structured_data.schedule.as_visit.date`이며, `OrderScheduleDate(kind='as_visit')` 동기화가 출고 대시보드 노출을 만든다.
18. `추가` 성공 시 AS 대시보드의 `AS 방문일`에도 같은 날짜가 등록되어야 한다.
19. 추천 모달에는 `추가된 AS 일정` 영역을 둔다. 여기에는 현재 화면 출고건에서 추천 기능으로 연결된 AS 건을 표시한다.
20. `추가된 AS 일정`의 `삭제`는 AS 건의 `structured_data.schedule.as_visit.date`와 time 값을 비우고, 추천 연결 메타데이터를 제거한다.
21. `삭제` 후에는 출고 대시보드 해당 날짜에서 그 AS 일정이 사라지고, AS 대시보드의 `AS 방문일`도 공란이 되어야 한다.
22. 삭제는 추천 기능으로 만든 연결만 기본 허용한다. 사용자가 이후 AS 방문일을 수동으로 다른 날짜로 바꾼 경우에는 409로 막고, 데이터 보존 메시지를 표시한다.

### 1.3 예외/제약 조건
- DB 스키마 변경은 하지 않는다.
- 추천 조회 API는 DB를 변경하지 않는다.
- 기존 `/api/orders/nearby` 응답 계약은 깨지 않는다.
- AS 대시보드의 기존 일정찾기 모달/지도 기능은 동작 그대로 유지한다.
- 추천 기준은 실제 소요시간 30분 이하이다. 실제 경로 거리는 화면 참고값과 동률 정렬 보조값으로만 쓰며, 직선거리는 실제 경로 계산 후보 우선순위에만 쓴다.
- 실제 경로 거리는 HTTP로 `/api/calculate_route`를 반복 호출하지 않고, 백엔드 서비스에서 기존 `FOMSAddressConverter.calculate_route()`를 직접 재사용한다.
- 대량 화면에서 외부 지오코딩 호출이 폭증하지 않도록 주소별 캐시와 batch 처리를 적용한다.
- 실제 경로 계산도 폭증하지 않도록 출고건별 직선거리 상위 후보를 경로 계산 대상으로 삼되, 최종 추천 제외 기준은 실제 소요시간 30분 초과 여부 하나로 둔다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `foms/services/schedule_recommendations.py` | 기존 nearby 거리/주소/랭킹 로직을 재사용 가능한 서비스로 추출 |
| `foms/services/common/address_converter.py` | `calculate_route()`에 선택적 timeout 파라미터 추가. 기본값은 기존 동작 유지 |
| `foms/api/orders/nearby.py` | 기존 `/api/orders/nearby`가 새 서비스의 construction 후보 모드를 호출하도록 정리, 기존 5건 계약 유지 |
| `foms/api/shipment/recommendations.py` | 출고용 AS 추천 batch 조회 API와 atomic apply/cancel API 추가 |
| `foms/api/shipment/__init__.py` | `erp_shipment_bp` 로드 후 `foms.api.shipment.recommendations`를 import해 route side effect 등록 |
| `templates/shipment/partials/dashboard_main.html` | `AS일정 추천` 버튼, 추천 모달, inline JS 연결 추가 |
| `tests/domains/test_orders_boundary_contract.py` | 기존 nearby API 하위 호환 테스트 보강 |
| `tests/domains/test_erp_mobile_layout_and_shipment.py` | 버튼/모달/시공자 공란 계약 테스트 추가 |
| `tests/domains/test_shipment_as_recommendations.py` | 신규 추천/적용 API 서비스 테스트 추가 |

### 2.2 추천 서비스 설계

새 서비스는 API 라우트에서 분리한다.

핵심 함수:
```python
recommend_nearby_schedules_for_targets(
    *,
    targets,
    candidates,
    per_target_limit=2,
    duration_limit_min=30,
    route_candidates_per_target=10,
    max_targets_per_request=5,
    max_route_calls_per_request=50,
    route_timeout_sec=3,
    reference_date=None,
    include_workers=False,
)
```

입력 모델:
- `targets`: 출고건 id, 고객명, 주소, 날짜, 시공자 목록, 좌표 캐시
- `candidates`: AS 건 id, 고객명, 주소, 현재 AS 방문일, 상태, 좌표 캐시

출력 모델:
```json
{
  "targets": [
    {
      "order_id": 1234,
      "customer_name": "홍길동",
      "address": "서울 ...",
      "target_date": "2026-05-04",
      "workers": ["시공자A"],
      "recommendations": [
        {
          "as_order_id": 2001,
          "customer_name": "김AS",
          "address": "서울 ...",
          "current_visit_date": "",
          "route_distance_km": 3.1,
          "route_duration_min": 12,
          "straight_distance_km": 2.4,
          "score_text": "실제 3.1km / 12분, 출고일에 함께 배정 가능",
          "as_info_id": 1,
          "will_apply_workers": ["시공자A"],
          "will_apply_date": "2026-05-04",
          "already_scheduled": false,
          "linked_from_shipment_order_id": null,
          "can_cancel_link": false
        }
      ],
      "linked_as_schedules": [
        {
          "as_order_id": 2001,
          "customer_name": "김AS",
          "as_info_id": 1,
          "applied_date": "2026-05-04",
          "applied_workers": ["시공자A"],
          "can_cancel_link": true
        }
      ],
      "message": ""
    }
  ]
}
```

### 2.3 후보 조회 규칙

출고 기준 대상:
- 현재 화면에서 전달받은 `order_ids`만 로드한다.
- 서버에서 다시 상태와 삭제 여부를 검증한다.
- `AS`, `AS_RECEIVED`, `AS_COMPLETED`, `DELETED`는 기준 대상에서 제외한다.
- 기준 날짜는 서버가 주문 데이터에서 추출한다. 클라이언트가 보낸 날짜는 화면 필터 확인용으로만 사용한다.

AS 후보 대상:
- `Order.status in ('AS', 'AS_RECEIVED')`
- `Order.deleted_at is NULL`
- 주소가 있는 주문
- 기본적으로 AS 완료 건은 제외
- 이미 방문일이 있는 AS도 추천에는 표시하되, `already_scheduled=true`로 내려 보내고 적용 전 확인을 요구한다.

### 2.4 거리/랭킹 규칙

1. 기존 `foms/api/orders/nearby.py`의 주소 추출, 좌표 캐시, Haversine 계산, 실제 경로 계산, 토큰 fallback 개념을 서비스로 옮긴다.
2. 카카오 지오코딩 성공 시 직선거리는 경로 계산 후보 우선순위에만 사용한다. 직선거리 30km 같은 값은 추천 제외 기준이 아니다.
3. 출고건별로 직선거리 상위 후보를 `route_candidates_per_target=10`건까지 경로 계산 대상으로 잡는다.
4. 한 요청은 최대 5개 출고건만 처리한다. 프론트는 5개 단위 chunk로 나눠 진행률을 표시한다.
5. 한 요청의 실제 경로 계산은 최대 50회로 제한한다. 이 값은 `max_targets_per_request * route_candidates_per_target`와 일치해야 한다.
6. prefilter 후보에 대해 `FOMSAddressConverter.calculate_route(timeout=3)`로 실제 경로 거리와 예상 시간을 계산한다.
7. route 계산은 작은 worker pool로 병렬화하되, 외부 API 보호를 위해 동시성은 5 이하로 제한한다.
8. 실제 경로 계산 결과에서 `route_duration_min <= 30`인 후보만 기본 추천에 남긴다.
9. 최종 추천 기본 정렬은 `route_duration_min` 오름차순이다. 화면에는 실제 소요시간을 먼저, 실제 경로 거리를 보조값으로 표시한다.
10. 실제 소요시간이 같으면 `route_distance_km`가 짧은 건을 우선한다.
11. 그 다음 현재 AS 방문일 없는 건을 우선한다.
12. 그 다음 AS 접수일이 오래된 건을 우선한다.
13. 그 다음 order id 오름차순으로 안정 정렬한다.
14. 최종 추천은 실제 소요시간 30분 이하에서 각 출고건당 `per_target_limit=2`만 반환한다.
15. 경로 계산이 일부 실패한 후보는 기본 추천에서 제외하고, 해당 출고건에 실제 경로 계산 성공 후보가 전혀 없을 때만 `fallback=true`와 `실제거리/소요시간 확인 불가` 메시지로 주소 토큰/직선거리 fallback 결과를 별도 표시한다.

### 2.5 API 설계

#### 2.5.1 추천 조회
`POST /api/erp/shipment/as-recommendations`

Request:
```json
{
  "order_ids": [3368, 3370],
  "selected_date": "2026-05-04"
}
```

Response:
```json
{
  "success": true,
  "per_target_limit": 2,
  "duration_limit_min": 30,
  "partial": false,
  "warnings": [],
  "targets": []
}
```

권한:
- `@login_required`
- `@erp_edit_required`
- `@role_required(["ADMIN", "MANAGER", "STAFF"])`
- 기존 출고 수정 API와 동일하게 `current_user.team == "CONSTRUCTION"`이면 403
- 프론트 버튼도 `can_edit_shipment` 사용자에게만 노출

#### 2.5.2 추천 적용
`POST /api/erp/shipment/as-recommendations/apply`

Request:
```json
{
  "shipment_order_id": 3368,
  "as_order_id": 2001,
  "as_info_id": 1,
  "force": false
}
```

권한:
- `@login_required`
- `@erp_edit_required`
- `@role_required(["ADMIN", "MANAGER", "STAFF"])`
- 기존 출고 수정 API와 동일하게 `current_user.team == "CONSTRUCTION"`이면 403

서버 처리:
1. 기준 출고건과 AS 건을 DB에서 로드한다.
2. 기준 출고건이 일반 출고/시공 건인지 검증한다.
3. AS 건이 `AS` 또는 `AS_RECEIVED`인지 검증한다.
4. 기준 출고건의 시공일을 서버에서 추출한다.
5. 기준 출고건의 `construction_workers`를 서버에서 추출한다.
6. AS 건에 열린 `as_info`가 여러 개이고 `as_info_id`가 없으면 잘못된 AS 항목 갱신을 막기 위해 409를 반환한다.
7. `as_info_id`가 있으면 해당 열린 AS 항목만 방문일/시간 동기화 대상으로 삼는다.
8. AS 건에 기존 방문일이 있고 기준일과 다르며 `force=false`이면 409를 반환한다.
9. `force=true` 또는 기존 방문일 없음이면 한 트랜잭션으로 AS 방문일과 시공자를 저장한다.
10. AS 건 `structured_data.schedule.as_visit.shipment_recommendation`에 연결 메타데이터를 저장한다.
   - `source = "shipment_dashboard_as_recommendation"`
   - `shipment_order_id`
   - `as_info_id`
   - `applied_date`
   - `applied_workers_snapshot`
   - `previous_visit_date`
   - `previous_visit_time`
   - `previous_workers_snapshot`
   - `applied_at`
   - `applied_by_user_id`
11. `flag_modified(order, "structured_data")`를 호출한다.
12. `sync_erp_flat_columns(order, structured_data)`를 호출한다.
13. `before_flush`의 `sync_order_dates`로 `OrderScheduleDate(kind='as_visit')`가 갱신되게 한다.
14. `OrderEvent`와 `SecurityLog`에 출고 대시보드 추천 적용 기록을 남긴다.

Response:
```json
{
  "success": true,
  "as_order_id": 2001,
  "applied_date": "2026-05-04",
  "applied_workers": ["시공자A"],
  "message": "AS 일정이 출고 일정에 추가되었습니다."
}
```

#### 2.5.3 추천 적용 취소/삭제
`POST /api/erp/shipment/as-recommendations/cancel`

Request:
```json
{
  "shipment_order_id": 3368,
  "as_order_id": 2001,
  "as_info_id": 1
}
```

권한:
- `@login_required`
- `@erp_edit_required`
- `@role_required(["ADMIN", "MANAGER", "STAFF"])`
- 기존 출고 수정 API와 동일하게 `current_user.team == "CONSTRUCTION"`이면 403

서버 처리:
1. 기준 출고건과 AS 건을 DB에서 로드한다.
2. AS 건의 `structured_data.schedule.as_visit.shipment_recommendation` 메타데이터를 확인한다.
3. 메타데이터의 `shipment_order_id`가 요청의 기준 출고건과 다르면 409를 반환한다.
4. 요청 `as_info_id`가 있고 메타데이터의 `as_info_id`와 다르면 409를 반환한다.
5. AS 건이 이미 `AS_COMPLETED`이면 완료된 작업 보호를 위해 409를 반환한다.
6. 현재 `as_visit.date`가 메타데이터의 `applied_date`와 다르면 수동 변경으로 판단해 409를 반환한다.
7. 안전 조건을 통과하면 같은 트랜잭션에서 추천 적용분을 제거한다.
   - `previous_visit_date`가 있으면 `as_visit.date/time`을 이전 값으로 복원한다.
   - `previous_visit_date`가 없으면 `as_visit.date/time`을 빈 값으로 비운다.
8. `shipment_recommendation` 메타데이터를 제거한다.
9. 메타데이터의 `as_info_id`가 있으면 그 AS 항목만 찾아 `visit_date`, `visit_time`을 동일하게 비우거나 이전 값으로 복원한다.
10. 메타데이터의 `as_info_id`가 없을 때만, 열린 AS 항목 중 같은 방문일이 들어 있는 단일 항목을 찾아 동기화한다. 여러 항목이 매칭되면 409로 막는다.
11. AS 건의 `construction_workers`는 현재 값이 `applied_workers_snapshot`과 같을 때만 이전 값으로 복원한다. `previous_workers_snapshot`이 없으면 `[]`로 되돌린다. 사용자가 이후 수동 수정한 시공자는 보존한다.
12. `flag_modified`, `sync_erp_flat_columns`, `OrderEvent`, `SecurityLog`를 적용 API와 동일하게 처리한다.
13. commit 후 `OrderScheduleDate(kind='as_visit')`가 비워져 출고 대시보드 해당 날짜에서 AS row가 사라진다.

Response:
```json
{
  "success": true,
  "as_order_id": 2001,
  "cleared_visit_date": "2026-05-04",
  "workers_cleared": true,
  "message": "AS 일정이 출고 일정에서 삭제되었습니다."
}
```

### 2.6 프론트 설계

위치:
- `templates/shipment/partials/dashboard_main.html`

버튼:
```html
<button class="erp-pro-btn erp-pro-btn--secondary" type="button" id="shipment-as-recommend-btn">
  <i class="fas fa-magic"></i>
  <span>AS일정 추천</span>
</button>
```

모달:
- Bootstrap modal을 `dashboard_main.html` 하단에 추가한다.
- 출고건별 그룹을 compact table/list 형태로 표시한다.
- 카드 안에 카드를 중첩하지 않는다.
- 모바일에서는 한 줄 요약 + 펼침형 상세로 표시한다.

JS 흐름:
1. `#shipment-as-recommend-btn` 클릭
2. `#shipment-dashboard-table tr[data-order-id]`에서 현재 표시 row ids 수집
3. 로딩 상태로 모달 open
4. 5개 order id 단위로 `POST /api/erp/shipment/as-recommendations`
5. chunk 응답을 합쳐 출고건별 그룹으로 렌더하고 진행률 표시
6. 추천 항목의 `추가` 클릭
7. `POST /api/erp/shipment/as-recommendations/apply`
8. 성공 시 해당 항목 상태 변경
9. 성공 항목을 `추가된 AS 일정` 영역으로 이동하거나 복제 표시
10. 현재 출고 대시보드 fragment를 자동 새로고침해 해당 날짜 rows와 날짜 패널 카운트를 즉시 갱신
11. 모달은 열린 상태를 유지하고, 새로고침 후에도 `추가된 AS 일정` 상태를 다시 렌더
12. `추가된 AS 일정`의 `삭제` 클릭
13. `POST /api/erp/shipment/as-recommendations/cancel`
14. 성공 시 출고 대시보드 fragment를 자동 새로고침해 해당 AS row와 날짜 패널 카운트를 즉시 제거
15. 모달은 열린 상태를 유지하고, `추가된 AS 일정` 영역에서도 해당 항목을 제거

### 2.7 기존 코드 재사용 포인트
- 주소 표시: `foms.services.geocode_helpers.get_order_display_address`
- 주소 좌표 캐시: 기존 nearby API의 `_get_order_cached_coords` 개념
- 후보 prefilter: 기존 nearby API의 `_haversine_km`
- 실제 거리 계산: `FOMSAddressConverter.calculate_route()`
- 출고 시공자 저장 구조: `foms/api/shipment/settings.py`
- AS 방문일 구조: `foms/api/cs/as_orders.py`와 `foms/api/orders/field_update.py`
- 날짜 정규화: `foms/services/order_date_sync.py`

## 3. Steps — 실행 단계

- [ ] Step 1: `foms/api/orders/nearby.py`에서 서비스로 뽑을 순수 로직 범위를 확정한다.
- [ ] Step 2: `foms/services/schedule_recommendations.py`를 추가하고 기존 nearby API의 동작을 그대로 통과시키는 테스트를 먼저 만든다.
- [ ] Step 3: `/api/orders/nearby`가 새 서비스를 사용하되 기존 응답 키와 5건 제한을 유지하게 한다.
- [ ] Step 4: `foms/api/shipment/recommendations.py`에 batch 추천 API를 추가한다.
- [ ] Step 5: 같은 파일에 atomic apply/cancel API를 추가한다.
- [ ] Step 6: `foms/api/shipment/__init__.py`에서 신규 route가 등록되게 한다.
- [ ] Step 7: `dashboard_main.html`에 버튼과 모달을 추가한다.
- [ ] Step 8: 기존 inline IIFE 안에 추천 조회/렌더/적용 JS를 추가한다.
- [ ] Step 9: 권한 없는 사용자, 빈 rows, 주소 없는 rows, 추천 없음, 이미 방문일 있는 AS 케이스를 UI에서 구분 표시한다.
- [ ] Step 10: 테스트를 추가하고 관련 테스트를 실행한다.
- [ ] Step 11: 코드 리뷰 감리 후 불필요한 범위 확장, 중복 API, 기존 AS 일정찾기 회귀 가능성을 제거한다.

## 4. 검증 기준

- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `/erp/shipment` 200 OK
- [ ] 출고 대시보드에서 `조회` 옆 `AS일정 추천` 버튼 표시
- [ ] 시공팀 조회 전용 계정에서는 `AS일정 추천` 버튼이 보이지 않거나 비활성
- [ ] 출고 row 3건, 인근 AS 후보 10건 환경에서 각 출고건당 최대 2건만 반환
- [ ] 출고 row 60건 이상이면 프론트가 5건 단위 chunk로 추천 조회
- [ ] 한 추천 API 요청의 route 계산 호출이 50회를 넘지 않음
- [ ] route 계산 timeout이 발생한 후보는 기본 추천에서 제외되고 fallback으로 구분
- [ ] `FOMSAddressConverter.calculate_route()` 기존 호출부는 timeout 인자 없이도 그대로 동작
- [ ] `/api/calculate_route` 기존 응답 계약 유지
- [ ] 전체 추천 수가 5건을 초과해도 잘리지 않음
- [ ] 추천 정렬과 화면 표시는 직선거리가 아니라 `route_duration_min` 기준
- [ ] 실제 경로 거리가 30km를 넘어도 실제 소요시간이 30분 이내이면 추천 가능
- [ ] 실제 소요시간이 30분을 넘으면 기본 추천에서 제외
- [ ] 실제 경로 계산 실패 후보는 기본 추천에 섞이지 않고 fallback으로 구분 표시
- [ ] AS 완료/삭제 건은 추천되지 않음
- [ ] 출고건 시공자가 `["A", "B"]`이면 추가된 AS 건도 `["A", "B"]`
- [ ] 출고건 시공자가 없으면 추가된 AS 건 `construction_workers`는 `[]`
- [ ] AS 건 기존 방문일이 다른 날짜이면 `force=false`에서 409 반환
- [ ] `force=true` 적용 시 AS 방문일과 `OrderScheduleDate(kind='as_visit')` 동기화
- [ ] 추천 적용 성공 시 AS 대시보드 `AS 방문일`에 같은 날짜 표시
- [ ] 추천 적용 성공 시 출고 대시보드 해당 날짜에 AS row 표시
- [ ] 추천 적용 성공 후 사용자가 `조회`를 누르지 않아도 출고 대시보드 rows/패널 카운트 즉시 갱신
- [ ] 추천 취소 성공 시 AS 대시보드 `AS 방문일` 공란
- [ ] 추천 취소 성공 시 출고 대시보드 해당 날짜에서 AS row 제거
- [ ] 추천 취소 성공 후 사용자가 `조회`를 누르지 않아도 출고 대시보드 rows/패널 카운트 즉시 갱신
- [ ] 추천 취소는 `shipment_recommendation.shipment_order_id`가 맞지 않으면 409
- [ ] `force=true`로 기존 AS 방문일을 덮어쓴 뒤 취소하면 기존 방문일/시간/시공자가 복원
- [ ] AS 완료(`AS_COMPLETED`) 건은 추천 취소/삭제 409
- [ ] 추천 조회/적용/취소는 시공팀 계정에서 서버 403
- [ ] AS 건에 열린 `as_info`가 여러 개이고 `as_info_id`가 없으면 적용/취소 409
- [ ] `as_info_id`가 있으면 해당 AS 항목만 visit_date/visit_time 변경
- [ ] 사용자가 AS 방문일을 수동으로 바꾼 뒤 추천 취소를 누르면 409로 데이터 보존
- [ ] 추천 취소 시 시공자가 적용 당시 snapshot과 같으면 `construction_workers=[]`
- [ ] 추천 취소 시 시공자가 수동 변경되어 snapshot과 다르면 시공자 값 보존
- [ ] 기존 `/api/orders/nearby` 응답의 `by_distance`, `by_date`, `by_combined`, `search_radius_km`, `ref_lat`, `ref_lng` 유지

필수 테스트:
- [ ] `pytest tests/domains/test_orders_boundary_contract.py -q`
- [ ] `pytest tests/domains/test_erp_mobile_layout_and_shipment.py -q`
- [ ] `pytest tests/domains/test_shipment_as_recommendations.py -q`
- [ ] `pytest tests/domains/test_order_date_sync.py -q`
- [ ] `pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q`

## 5. 리뷰 감리 Loop

### 5.1 1차 코드 리뷰 결론
문제의 핵심은 "AS 대시보드 일정찾기 로직 재사용"이라는 표현이 단순 API 호출 재사용을 의미하지 않는다는 점이다. 기존 API는 AS 건 기준으로 인근 시공 일정을 찾는다. 출고 대시보드에서는 반대로 출고건 기준으로 인근 AS를 찾아야 한다.

따라서 프론트에서 `/api/orders/nearby`를 반복 호출하는 안은 폐기한다.

### 5.2 엔지니어링 감리
- batch API를 사용해 지오코딩과 후보 조회를 한 번으로 줄인다.
- 실제 소요시간을 기본 추천 기준으로 사용한다.
- 실제 소요시간 30분 초과 후보는 기본 추천에서 제외한다.
- 직선거리는 실제 경로 계산량을 줄이기 위한 prefilter에만 사용한다.
- 추천 조회와 적용 저장을 분리한다.
- 적용 저장은 atomic API로 묶어 방문일만 저장되고 시공자가 실패하는 부분 성공을 막는다.
- 적용 취소도 atomic API로 묶어 출고 대시보드 일정 삭제와 AS 방문일 삭제가 어긋나지 않게 한다.
- 추천 기능으로 만든 연결임을 판단하기 위해 AS 건 `as_visit` 아래에 연결 메타데이터를 저장한다.
- 기존 AS 일정찾기 API의 5건 계약은 유지한다.
- 새 요구의 "각 출고건당 2건"은 새 batch API에서만 적용한다.

### 5.3 제품/UX 감리
- 사용자는 여러 출고건에 붙일 수 있는 AS 후보를 한 모달에서 스캔해야 한다.
- 결과는 출고건별 그룹이 가장 이해하기 쉽다.
- 추천 항목에는 "어떤 출고건의 시공자가 적용되는지"가 반드시 보여야 한다.
- 시공자 없는 출고건은 숨기지 않는다. 대신 `시공자 공란으로 적용`으로 명확히 표시한다.

### 5.4 위험 감리
| 위험 | 대응 |
|------|------|
| 기존 AS 일정찾기 회귀 | `/api/orders/nearby` 응답 계약 테스트 유지 |
| 지오코딩 호출 폭증 | batch 후보 조회 + 주소별 캐시 |
| 실제 경로 API 호출 폭증 | 5건 chunk, 요청당 route 50회 cap, 동시성 5 이하 |
| 실제 경로 계산 실패 | 기본 추천 제외, fallback 결과는 명확히 분리 표시 |
| 경로 API 지연 | `calculate_route(timeout=3)` 및 partial 결과 |
| 거리상 가까워도 이동시간이 긴 후보 | `route_duration_min > 30` 기본 추천 제외 |
| AS 방문일 덮어쓰기 | `force=false` 기본 409 + 확인 후 재요청 |
| force 적용 후 취소 시 기존 일정 손실 | 이전 방문일/시간/시공자 snapshot 저장 후 cancel 때 복원 |
| 부분 저장 | 추천 적용 전용 atomic API |
| 잘못된 AS 방문일 삭제 | 추천 연결 메타데이터와 현재 날짜 일치 여부 확인 후 cancel |
| 수동 변경 데이터 손실 | 방문일/시공자가 적용 snapshot과 다르면 보존 또는 409 |
| 권한 우회 | 버튼 가시성 + 서버 권한 검증 |
| 중복 AS 배정 | 모달 내 적용 완료 상태 공유 |

## 6. 결정 기록

| 결정 | 선택 | 이유 |
|------|------|------|
| 기존 `/api/orders/nearby` 직접 반복 호출 | 하지 않음 | 5건 제한과 N배 지오코딩 문제 |
| 추천 조회 API | 신규 batch API | 각 출고건당 2건 요구와 성능 보호 |
| 추천 시간 기준 | 실제 소요시간 30분 이하 | 사용자가 실제 이동 가능성을 판단해야 하므로 거리보다 직접적 |
| 실제 경로 거리 사용처 | 화면 참고값과 동률 정렬 | 거리는 제외 기준이 아니라 판단 보조 정보 |
| 직선거리 사용처 | 내부 prefilter 우선순위만 | 실제 거리 계산 호출량을 통제하면서 기본 추천 품질 유지 |
| 추천 적용 | 신규 atomic apply API | AS 방문일/시공자 부분 저장 방지 |
| 추천 취소/삭제 | 신규 atomic cancel API | 출고 대시보드 일정 삭제와 AS 방문일 삭제를 같은 트랜잭션으로 처리 |
| 추천 연결 추적 | `as_visit.shipment_recommendation` 메타데이터 | 추천으로 만든 일정만 안전하게 취소하기 위해 필요 |
| 시공자 출처 | 기준 출고건 | 사용자 요구의 "각 출고 건 시공자 자동 입력"과 일치 |
| 시공자 없음 | `[]` 저장 | 기존 API가 빈 문자열을 제거하므로 공란의 DB 표현은 빈 리스트 |
| 기존 AS 일정찾기 | 계약 유지 | 다른 화면 회귀 방지 |

## 7. 참고 자료

- `docs/guides/SPEC_TEMPLATE.md`
- `docs/plans/2026-03-25-as-schedule-finder-map-modal-plan.md`
- `docs/plans/2026-03-10-shipment-dashboard-resizable-columns-from-scratch-plan.md`
- `foms/api/orders/nearby.py`
- `templates/cs/partials/as_dashboard_body.html`
- `foms/web/shipment/dashboard.py`
- `templates/shipment/partials/dashboard_main.html`
- `foms/api/shipment/settings.py`
- `foms/services/order_date_sync.py`
