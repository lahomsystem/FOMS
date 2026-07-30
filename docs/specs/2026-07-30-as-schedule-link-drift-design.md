# AS 일정 매칭 링크 + 기준일 변경 감지 (설계 스펙)

- 작성일: 2026-07-30
- 상태: **승인 대기**
- 관련 커밋: `c652a339`(출고 AS 추천 모달 타임라인/지도), 본 세션 버그수정(추가 버튼 침묵)

## 1. 문제 (Pain)

AS 일정을 잡을 때 담당자는 **다른 주문의 시공일**을 보고 그 날짜에 맞춘다.
이후 **그 기준 주문의 시공일이 변경되면 아무도 모른다.** AS만 옛 날짜에 남아
현장 동선이 꼬인다.

현재 두 경로 모두 "무엇을 보고 잡았는지"가 기록되지 않는다.

| 경로 | 위치 | 링크 기록 |
|---|---|---|
| A. 출고 대시보드 "AS 일정추천" → `추가` | `templates/shipment/partials/dashboard_main.html:156-181` | 출고 쪽에만 스냅샷 (`sd.shipment.recommendations`, `foms/services/shipment/as_recommendation.py:245-264`) — AS 쪽에는 흔적 없음 |
| B. AS 대시보드 "가까운 일정 찾기" 모달 | `templates/cs/partials/as_dashboard_body.html:440-519`, 렌더 `static/js/cs/as-dashboard.js:1410-1472` | **없음.** 결과는 `/edit/<id>?open=erp-order` 링크뿐, 날짜는 손으로 입력 |

경로 B가 실제 pain 발생 지점이다.

## 2. 설계 원칙 / 방식 선택

### 감지 방식: 이벤트 훅이 아니라 **읽기 시점 값 비교**

| 안 | 내용 | 판정 |
|---|---|---|
| 훅 (도면 패턴 이식) | 시공일 쓰기 사이트에서 `OrderEvent` 소비 → pending 플래그 + Notification + ack | **불채택.** 쓰기 사이트 3곳 중 `foms/web/orders/edit.py:225,251`이 `OrderEvent`를 안 남긴다 → 그 경로 변경은 영원히 미감지(= 지금 pain 재현). 플래그와 실제 값의 스큐 위험도 추가 |
| **값 비교 (채택)** | 매칭 시점 날짜(D0)를 링크에 저장하고, 렌더 시 기준 주문의 현재 시공일과 비교 | 쓰기 사이트 수정 0, 훅 0, cron 0, 마이그레이션 0. 경로 무관하게 감지(엑셀·모바일·edit.py 전부 커버) |

선례: 도면 `foms/services/notifications/drawing_order_change.py`, 생산
`foms/services/notifications/production_change.py`. **배관은 참고하되 이식하지 않는다** —
v1은 알림센터/푸시 없이 화면 표시만으로 pain을 해소한다(§7 Phase 2).

## 3. 데이터 모델

### 3.1 링크 SSOT (신규)

AS 주문의 `structured_data.schedule.as_visit.schedule_link` (단일 객체, 1 AS = 1 링크):

```json
{
  "ref_order_id": 3694,
  "ref_kind": "construction",
  "ref_date": "2026-08-05",
  "linked_at": "2026-07-30T02:11:00",
  "linked_by_user_id": 12,
  "linked_by": "홍길동",
  "source": "as_nearby_modal",
  "ack_ref_date": null
}
```

- `ref_date` = **매칭 시점의 기준 주문 시공일 (D0)**. 드리프트 판정 기준선.
- `source`: `as_nearby_modal`(경로 B) | `shipment_asrec`(경로 A).
- `ack_ref_date`: "무시" 누른 시점의 기준일. 이 값과 현재 기준일이 같으면 경고를 숨긴다.
- 링크 해제 = 키 삭제.

**기존 legacy 키 `schedule.as_visit.shipment_recommendation` 은 되살리지 않는다.**
읽는 코드가 3곳 살아 있고(`foms/api/shipment/recommendations.py:299`,
`foms/services/shipment_as_recommendation_cache.py:232-247`,
`foms/services/shipment_dashboard_display.py:56`) 그 값이 있으면 출고 대시보드가
"추천 취소" 가능으로 오판한다 — 경로 B로 만든 링크에는 출고 쪽 복원 스냅샷이 없어
취소가 깨진다. 신규 키로 분리한다.

### 3.2 기존 스냅샷과의 관계

`sd.shipment.recommendations`(출고 쪽, `as_recommendation.py:156-193`)는 **취소 복원용
데이터로 그대로 유지**한다. 경로 A 적용/취소 시 AS 쪽 `schedule_link` 를 함께
기록/삭제해 두 경로의 감지 로직을 하나로 통일한다.

### 3.3 기준 주문의 현재 시공일 (Ds) 조회

`Order.erp_construction_date`(`models.py:100`, `String(10)` + index) 우선,
없으면 `Order.scheduled_date`. 배치 조회 `Order.id.in_(ref_ids)` 1회 — JSONB 스캔 없음.

## 4. 드리프트 판정

D0 = `schedule_link.ref_date`, Ds = 기준 주문 현재 시공일, Da = AS 현재 방문일
(`sd.schedule.as_visit.date`).

| 조건 | 상태 | 화면 |
|---|---|---|
| Ds == D0 | `ok` | 링크 표시만 (기준 #id, 날짜) |
| Ds ≠ D0, Da == D0 | **`ref_moved`** (주 케이스) | 빨강 배지 + 배너 카운트, `재적용` / `무시` / `연결 해제` |
| Ds ≠ D0, Da ≠ D0, Da ≠ Ds | `both_moved` | 주황 배지, `재적용`은 confirm 후 |
| Ds ≠ D0, Da == Ds | `resolved` | 링크의 `ref_date` 를 Ds 로 자동 갱신(사람이 이미 맞춰 놓음), 경고 없음 |
| Ds ≠ D0 이고 `ack_ref_date == Ds` | `acked` | 경고 숨김(회색 표기만) |
| 기준 주문 `DELETED`/조회 불가 | `ref_gone` | 회색 배지 + `연결 해제` |

`resolved` 자동 갱신은 **렌더 시 쓰기 금지**(GET에서 DB write 금지) — 표시만
`ok` 로 하고, 실제 `ref_date` 갱신은 다음 링크 API 호출 때 수행한다.

## 5. 사용자 흐름

### 5.1 매칭 (경로 B, 신규)

1. AS 행 `일정찾기` 클릭 → 모달(기준 = 그 AS건 주소).
2. 결과 행마다 신규 버튼 **`이 일정에 매칭`**.
3. 클릭 → `POST /api/erp/orders/<as_order_id>/as/schedule-link` `{action:"link", ref_order_id, ref_date}`.
   - 기준 AS id 는 이미 모달 클로저에 있다: `_searchState.excludeId`(`static/js/cs/as-dashboard.js:1573`).
   - 결과 행 전체가 `<a>` 이므로 핸들러에서 `stopPropagation()` + `preventDefault()` 필수
     (지도 버튼 선례 `as-dashboard.js:1592-1596`).
4. 성공 시 버튼 → `매칭됨`, 행에 기준 표기.
5. 방문일 입력은 **기존 흐름 그대로**(`.editable-date-as` → `POST /api/update_order_field`).
   매칭과 날짜 입력은 독립 — 매칭이 날짜를 바꾸지 않는다(v1).

### 5.2 변경 감지 후 대응

AS 대시보드 상단 배너: `연결된 기준 일정이 변경된 AS N건` + 목록 스크롤 앵커.
행 액션 3개:

- **재적용**: 기존 배선 2콜 재사용 — ① `POST /api/update_order_field`
  (`field_name=as_visit_date`, `value=Ds`) → `as_log` 에 `방문일 확정: …` system 항목이
  기존 코드로 남는다(`foms/api/orders/field_update.py:466-498`), ② `schedule-link`
  `{action:"relink"}` 로 `ref_date` 를 Ds 로 갱신. **새 날짜 쓰기 코드 없음.**
- **무시**: `{action:"ack"}` → `ack_ref_date = Ds`.
- **연결 해제**: `{action:"unlink"}` → 키 삭제.

시공자(crew) 복제는 경로 A(`apply_as_recommendation`)만의 동작이며 재적용은 날짜만
건드린다. v1 범위 밖임을 UI 문구에 명시한다.

## 6. API

`POST /api/erp/orders/<int:order_id>/as/schedule-link` — `foms/api/cs/as_orders.py` 에 추가.

- 데코레이터: `@login_required` + `@erp_edit_required` (AS 로그 API 선례 `as_orders.py:801-803`).
  현재 `GET /api/orders/nearby` 는 `@login_required` 뿐이지만(`foms/api/orders/__init__.py:22-26`)
  **쓰기는 편집 권한을 요구**한다.
- body: `{action: "link"|"relink"|"ack"|"unlink", ref_order_id?: int, ref_date?: "YYYY-MM-DD"}`
- 쓰기는 `_run_sd_mutation(policy_id="STATE_AS_SCHEDULE_LINK", command_id="AS_SCHEDULE_LINK")`
  으로 기존 mutation 파이프(버전 bump·receipt·OrderEvent)를 탄다.
- 검증: `ref_order_id` 존재·`DELETED` 아님·자기 자신 아님, `ref_date` 는 `YYYY-MM-DD`.
  `link` 시 서버가 기준 주문의 현재 시공일을 다시 읽어 body 의 `ref_date` 와 다르면
  **서버 값을 채택**(클라 stale 방지).
- 응답: `{success, link, drift}`; 실패는 400(검증)/404(주문 없음)/409(무결성).
- 성공 후 `_invalidate_shipment_asrec_caches(...)` 호출(추천 pool 이 링크 상태를 보여줌).

## 7. 범위

### v1 (본 스펙)
- 링크 스키마 + 서비스 + API
- 가까운 일정 찾기 모달 `이 일정에 매칭` 버튼
- AS 대시보드 배너 + 행 배지 + 재적용/무시/해제
- 경로 A(출고 apply/cancel) 링크 동기화
- 기존 적용분 1회성 백필

### Phase 2 (미착수, 별도 승인)
- 알림센터/푸시(`Notification` + `fan_out_new_notification`) — 도면 패턴 이식
- 출고 대시보드 쪽 드리프트 표시
- `일정 변경됨` 필터 칩(전체 미완료 AS 스캔 → JSONB 표현식 인덱스 필요)

## 8. 성능·함정

- 드리프트 계산은 **렌더된 행 집합**에 대해서만 수행하고 기준 주문은 `in_(ids)` 1회 조회.
  전체 미완료 AS 스캔은 v1에서 하지 않는다(무인덱스 JSONB 필터 금지 규칙).
  배너 문구는 "현재 목록 기준 N건"으로 정직하게 쓴다.
- JSONB 수정은 `copy.deepcopy` + `flag_modified` (기존 `_run_sd_mutation` 이 처리).
- `as_log` 는 append-only — 매칭/해제는 로그를 지우지 않고 `type="system"` 항목만 추가
  (`append_system_log`, `foms/services/orders/as_log.py:123`).
- JS 변경 시 `?v=` 핀 전 파일 동시 범프(서비스워커 stale 트랩). 현재 핀 `20260730g`.
- AS 대시보드 JS 는 fragment swap 마다 재실행되며 리스너는 `addAsDashboardListener`
  (`static/js/cs/as-dashboard.js:81-101`, AbortController)로만 등록한다.
- 모달·행 버튼은 로그인 사용자 전원에게 보인다(현재 게이트 그대로). 쓰기 API 는 편집 권한 요구.

## 9. 검증 기준

- `python -c "import app; print('APP_OK')"`
- 신규 유닛/계약 테스트(§플랜 T1·T2·T4) green
- `tests/postgres` 레인 전수 (JSONB 쓰기 포함)
- `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` exit 0
- 스테이징 실브라우저: 매칭 → 기준 주문 시공일 변경 → AS 대시보드 배너 노출 → 재적용 → 배너 소멸
