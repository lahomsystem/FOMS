# 한 주문 안에서 제품마다 시공일이 다를 때 — 1단계 설계서 (구멍 막기)

> 2026-11-20 작성. 상태: **승인됨 — 구현 중.** 사장님 승인(2026-11-20): 방향 "구멍부터 막기", 아래 결정 M1 · M9 · M14, "PC · 휴대폰 화면까지", "완결까지 진행".
> 기준 코드: `origin/deploy` `963818eb1`. 줄 번호는 그 시점 값이다.
> 고객 이름은 적지 않고 주문 번호로만 적는다. 목업: `docs/design/mockups/multi-item-split-schedule-process.html`.
> 만든 방법: 조사 5 → 설계안 3 → 총괄 종합 → 교차 검수 3(1차, 계획) → 묶음별 정밀 조사 4(2차, 이 설계서) → 총괄이 운영 자료와 핵심 줄을 다시 확인.

## 1. 한 장 요약

- **문제**: 주문 하나에 제품이 여럿이고 제품마다 시공일이 다를 수 있는데, 단계(접수 → 실측 → 도면 → 컨펌 → 생산 → 시공 → CS → 완료)는 주문 전체에 하나뿐이다. 그래서 남은 제품을 새 주문으로 다시 등록하고, 매출이 두 번 잡히고, 도면을 다시 그리고, 채널톡 · AS 가 꼬였다(주문 5687 · 6026).
- **실제로 일을 망가뜨린 구멍 넷**
  1. AS 가 접수되면 그 주문의 남은 시공 줄이 화면에서 빠지거나 AS 줄로 바뀌고, 시공 단추가 사라진다.
  2. 지난 주문 일괄 완료 도구가 첫 시공일만 본다. 완료를 누를 때도 "뒤 시공일이 남았다"는 말이 없다.
  3. 단계를 손으로 바꾸면 주문 상태 글을 직접 덮어 AS 표시가 지워진다.
  4. 새 주문을 만들 때 같은 고객의 진행 중 주문이 있다는 것을 알려 주지 않는다.
- **이번에 하는 일(1단계)**: 주문은 하나로 두고 단계 엔진은 건드리지 않는다. 위 구멍을 PC · 태블릿 · 휴대폰 화면에서 모두 막는다. 묶음 넷(A~D)이고 서로 기대지 않는다.
- **하지 않는 일**: 제품마다 단계를 따로 두는 큰 구조 변경(11절).

## 2. 규모 (운영 자료, 읽기 전용)

| 항목 | 값 |
|---|---|
| 2026-07-01 이후 ERP 주문 | 1,719건 |
| 시공일이 이틀 이상 벌어진 주문 | 37건 (한 달에 8건쯤) |
| 11-11 일괄 완료 506건 가운데 뒤 시공일이 남아 있던 주문 | 2건 |
| 11-20 일괄 완료(4차) 101건 가운데 뒤 시공일이 남아 있던 주문 | 0건 (11-20 점검) |
| 지금 "AS 상태 + 생산 · 시공 단계"인 주문 | 0건 (11-20 점검) |
| AS 는 열려 있는데 주문 상태가 AS 가 아닌 주문 | 1건 (5687) |

읽는 법: 지금 꼬여 있는 주문을 푸는 일이 아니라, 다음에 같은 일이 생기지 않게 막는 일이다. 생산 · 시공 단계는 아직 실사용이 적어(도면 · 고객컨펌까지 실사용) 해당 주문이 0건이지만, 그 단계를 쓰기 시작하면 5687 과 같은 일이 그대로 되풀이된다.

## 3. 결정

| # | 결정 | 누가 |
|---|---|---|
| M1 | AS 상태 주문이라도 **본 흐름이 열려 있으면**(단계가 생산 또는 시공 진행) 그 주문의 시공일 줄은 시공 줄로 그린다. 본 흐름이 끝난 주문(CS · 완료)은 지금 그대로다. 태블릿 설계서 D43 의 범위를 이만큼 좁힌다 | 사장님 승인 |
| M2 | "본 흐름 열림"에 CS 단계는 넣지 않는다(승인 문구 그대로 생산 · 시공만) | 총괄 |
| M3 | 같은 날 시공 + AS 방문이면 **한 줄**(시공 줄)로 그리고 시간 칸 작은 글에 "AS 방문도"를 붙인다. 날짜 수는 집 수 그대로다. 계획 초안의 "두 줄"은 화면 다섯 곳이 주문 번호를 열쇠로 써서 같은 id 가 둘이 되므로 접는다 | 총괄 |
| M4 | 태블릿 시공 상세의 [시공 시작] · [시공 완료] · [시공 불가] · 사진 단추는 본 흐름이 열려 있으면 AS 상태여도 그린다 | 총괄(M1 따름) |
| M5 | 지방 · 수도권 · 자가실측 보드는 이번에 고치지 않는다("칸 = 상태"가 2026-08-07 승인 규칙). 그래서 `complete_path_policy.py` 의 숨김 조건도 그대로 둔다(고쳐도 보이는 변화가 없다) | 총괄 |
| M6 | 손으로 하는 단계 변경에서 **열린 AS**(접수 · 처리 중)는 본 흐름 목표 쓰기를 이긴다 — 단계는 옮기고 주문 상태 글은 AS 그대로 둔다. 닫힌 AS(완료)는 지금처럼 덮인다. 물류 · 보류 · AS 목표 쓰기는 건드리지 않는다 | 총괄 |
| M7 | M6 을 거는 곳은 여섯 곳: 강제 단계 변경, 단건 상태 쓰기, 일괄 상태 쓰기, 칸 고치기, 수정 제작 시작, 옛 목록 일괄 · 옛 수정 폼 | 총괄 |
| M8 | 응답 · 이벤트의 `as_overlay_cleared` 는 지우지 않게 됐으므로 `as_overlay_kept` 로 바꾸고 화면 글도 "AS 표시는 그대로 남습니다"로 바꾼다 | 총괄 |
| M9 | "AS 접수 취소"를 새로 만든다 | 사장님 승인 |
| M10 | 취소는 현재 건이 **접수(RECEIVED)** 일 때만, 관리자 · CS 능력(회계 포함)만, 사유 필수. 처리 중 · 완료는 취소가 아니다 | 총괄 |
| M11 | 취소한 건은 `as_lifecycle.cycles[]` 에서 빼 `cancelled_cycles[]` 로 옮긴다(순번을 세는 일곱 곳이 틀리지 않게). 그 건의 기록 줄은 지우지 않고 가림 표시만 한다 | 총괄 |
| M12 | 취소를 AS 방 · 협력사에 따로 알리지 않는다. 열린 AS 도면 요청이 있으면 취소를 막고 먼저 닫게 한다 | 총괄 |
| M13 | 완료 확인 창의 한 줄: [시공 완료]는 오늘보다 뒤 시공일이 남았을 때, [제작 완료]는 서로 다른 시공일이 둘 이상일 때만. 막지 않는다 | 총괄 |
| M14 | 주문 복사는 "넣을 것만 넣는" 방식으로 바꾼다 | 사장님 승인 |
| M15 | 새 주문 안내는 알리기만 한다. PC 폼은 저장하면 바로 화면을 떠나므로 **전화 · 주소 칸을 벗어날 때** 미리 보인다. 휴대폰 마법사는 마지막 확인 단계 맨 위 | 총괄 |
| M16 | "진행 중"은 단계가 완료가 아닌 ERP 주문이다(휴지통 · 초안 · 자기 자신 제외). 이름만 같은 것은 치지 않는다(전화, 또는 도로명 + 건물번호 + 동 · 호) | 총괄 |
| M17 | 안내는 본사 직원 화면에만. 프리랜서 · 협력사에게는 안 보인다(남의 주문 정보가 새지 않게). 모든 생성 길은 `ORDER_CREATED` 기록에 진행 주문 번호를 남겨 4~8주 뒤에 센다 | 총괄 |
| M18 | 둘째 AS 건의 첫 PUSH 는 재전송이 아니라 "새 AS 접수 (N번째 AS)"로 보낸다. 순번이 1 인 건은 머리말 없이 보통 첫 PUSH. 협력사 쪽 글도 같은 판정을 쓴다 | 총괄 |
| M19 | 생산 · 시공 단계에서 최종 도면이 한 장일 때, 이번에 보내는 파일이 **다른 시트**면 바꾸지 않고 더한다. 알 수 없으면 지금처럼 바꾼다. 작업실 전달 창의 기본값도 같은 조건에서 "더하기"로 둔다. 2026-10-27 결정 3 을 이만큼 좁힌다 | 총괄 |
| M20 | 자동 할 일 · 임박 배지는 시공일이 여럿이면 오늘 이후 가장 가까운 날(모두 지났으면 마지막 날)을 쓴다 | 총괄 |

## 4. 묶음 A — AS 가 본 흐름을 가리지 않게

### 4.1 판정 하나

- **본 흐름 열림** = `erp_stage_code` 가 `PRODUCTION` · `생산` · `CONSTRUCTION` · `시공` · `CONSTRUCTING` 중 하나.
- **AS 상태** = `order.status ∈ (AS, AS_RECEIVED, AS_COMPLETED)`. AS 를 끝내도 현재 건 표시가 남아 상태가 계속 `AS_COMPLETED` 이므로 세 값 모두 다룬다.
- **그 날짜 줄의 종류**
  - 시공 줄 = 일정 줄 `kind='construction'` 이고 (AS 상태가 아님 **또는** 본 흐름 열림).
  - AS 방문 줄 = 일정 줄 `kind='as_visit'` 이고 AS 상태(지금 그대로).
  - 같은 주문 · 같은 날에 둘 다면 시공 줄 하나 + "AS 방문도"(M3).
- 판정은 새 작은 모듈 하나(`foms/services/orders/schedule_row_kind.py`)에 둔다. `shipment_dashboard_helpers.py` 는 잎 모듈이라 다른 읽기 모델을 가져오면 순환한다 — 단계 코드 묶음은 새 모듈에 다시 적는다.
- 옛 자료 함정: 옛 흐름은 AS 방문일을 시공일 칸에 적기도 했다. "AS 상태의 시공 줄"을 통째로 풀면 지난 AS 가 시공 줄로 되살아난다. 본 흐름 열림 조건이 이것을 막는다.

### 4.2 화면별로 바뀌는 것 (견본: 생산 단계 + AS 접수 + 앞날 시공일)

| 화면 | 기기 | 지금 | 고친 뒤 | 고칠 곳 |
|---|---|---|---|---|
| 시공 탭 첫 화면(날짜 단추 수 + 그날 줄) | 태블릿 | 수에도 줄에도 없다 | 시공 줄로 든다 | `foms/services/construction/tablet_first.py:77-89`(짝 조건) · `:319-361`(줄 글 · 출고 칸 · 자수), `templates/construction/partials/tablet_first_body.html:92-99` |
| 시공 탭 "날짜 미정" | 태블릿 | 시공 단계 + AS 상태면 빠진다 | 든다 | `tablet_first.py:174-180` |
| 시공 탭 상세 · 찾기 | 태블릿 | "AS 방문 집이에요", 시공 단추 없음 | 본 흐름 글 + 단추(M4) | `foms/services/construction_dashboard_display.py:451-452`, `foms/services/construction/tablet_view.py:66-118` |
| 출고 탭 하루치 출고표 · 줄 서랍 | 태블릿 | 줄은 있으나 AS 줄(자수 0 · 맨 뒤 · 제품 칸 AS 글) | 시공 줄 | `foms/services/shipment/tablet_day_sheet.py:88-135`, `foms/web/shipment/dashboard.py:846-847`, `templates/shipment/partials/tablet_ship_grid.html:79-100`, `tablet_sheet.html:15-39` |
| 출고 대시보드 표 | PC | 줄은 있으나 AS 줄(맨 아래 · 제품 칸 = AS 내용 · 규격 칸 = AS 배지) | 시공 줄 | `foms/services/shipment_dashboard_display.py:50, 116-117`, `templates/shipment/partials/dashboard_main.html:495, 520, 566-592` |
| 출고 날짜 띠(시공 건수 · 잔여 자수 · 잔여 시공자) | PC · 태블릿 | 수에서 빠진다 | 센다 | `foms/services/shipment_read_model.py:42-44` + 캐시 열쇠 판 올리기(`foms/web/shipment/dashboard.py:446`) |
| 출고 카드 목록 | 휴대폰 | AS 카드(날짜 머리 = AS 방문일) | 시공 카드 | `shipment_dashboard_display.py:180-190` |
| 협력사 출고 탭 | 협력사 | AS 표시 | 태블릿 출고표와 같은 함수라 같이 바뀐다 — 협력사에게 보이는 줄 종류만 바뀐다 | (따라옴) |

**이미 맞는 곳(고치지 않음)**: PC · 휴대폰 시공 목록(단계만 본다), 홈 관제탑, 주문 대시보드 날짜 필터, 생산 화면 전부, 일정 표 쓰기.

**이번에 넣지 않는 곳**: 지방 · 수도권 · 자가실측 보드(M5), 아래 탭 배지 수, 지도, 출고 [AS 추천] 기준 줄, 완료(정산) 대시보드 — 11절.

지킬 것: 태블릿 첫 화면 쿼리는 딱 두 문장 · CASE 꼴 유지(`tests/domains/test_construction_tablet_first.py:243-262`), 쿼리 수 10 / 8 / 7(`test_construction_tablet_d43.py:252-268`). 새 OR 은 주문 표 한쪽 안에만 둔다. 줄 종류는 이미 싣는 자료로만 정한다. `tablet_first.py` 478줄 · `construction_dashboard_display.py` 499줄이라 500줄 래칫에 닿는다 — 늘리지 말고 새 모듈로 뺀다.

### 4.3 단계를 손으로 바꿔도 AS 표시가 남게 (M6 · M7 · M8)

- 지금: 아래 곳들이 `order.status` 를 본 흐름 글로 직접 덮는다. `as_lifecycle` 과 `as_axis_status` 는 그대로라 AS 화면에는 남고 주문 화면에서는 AS 표시가 사라진다.
- 고침: 목표가 본 흐름 코드이고 AS 축이 열려 있으면(접수 · 처리 중) 단계만 옮기고 상태 글은 쓰지 않는다. 이미 있는 좁은 문지기 `as_overlay_outranks_status_write`(`foms/services/orders/state_axes.py:220-242`, 지금은 물류 목표만)를 본 흐름 목표까지 넓힌 짝 함수를 둔다.

| # | 곳 | 줄 |
|---|---|---|
| 1 | 강제 단계 변경(단건 · 일괄 · 운영 도구) | `foms/services/orders/stage_override.py:371` |
| 2 | 단건 상태 쓰기 | `foms/api/orders/status.py:422` |
| 3 | 일괄 상태 쓰기 | `foms/api/orders/status.py:693` |
| 4 | 칸 고치기 `status` | `foms/api/orders/field_update.py:760-778` |
| 5 | 수정 제작 시작 | `foms/api/production/orders.py:1099` |
| 6 | 옛 목록 일괄 · 옛 수정 폼 | `foms/web/orders/listing.py:660`, `foms/web/orders/edit.py:427` |

- 함정: `state_axes.py` 가 `stage_override` 를 가져오므로 `stage_override.py` 맨 위에서 `state_axes` 를 가져오면 순환한다. 함수 안 가져오기는 래칫이 막는다. 판정을 잎 모듈로 빼거나 부르는 쪽에서 판정한다.
- 강제 변경 창 안내 한 줄: "AS 표시는 그대로 남습니다. 잘못 접수한 AS 는 [AS 접수 취소]로 지워 주세요."(`templates/orders/partials/erp_stage_override_modal.html:44-48`)

### 4.4 AS 접수 취소 (M9 ~ M12)

- 명령 하나 `cancel_as_cycle`(`foms/services/orders/as_cycle_service.py` 의 명령 틀 안, 파일이 커지면 새 모듈), 라우트 `POST /api/orders/<id>/as/cancel`(`foms/api/cs/as_orders.py`), 본문 `{reason}`, 응답 `{success, data, error}`.
- 조건: 현재 건이 접수 상태, 사유 있음, 권한(관리자 · CS 능력). 열린 AS 도면 요청이 있으면 409 로 막는다. 건 기록이 없는 옛 AS 주문은 먼저 건을 세운 뒤(이미 있는 틀) 취소한다.
- 하는 일
  1. 그 건을 `cycles[]` 에서 빼 `cancelled_cycles[]` 로 옮긴다(취소 시각 · 사람 · 사유). `current_cycle_id` 는 남은 마지막 건, 없으면 비운다.
  2. 주문 상태 글을 다시 계산해 쓴다. 남은 건이 없으면 AS 축을 비운 값(물류 → 본 흐름)으로, 남은 건이 완료면 `AS_COMPLETED` 로.
  3. 평면 칸 `as_axis_status` · `as_received_date` · `as_completed_date` 를 손으로 맞춘다(동기화는 값이 없으면 안 지운다 — `foms/services/erp_sync_columns.py:103-105`).
  4. `shipment.as_content` 는 남은 건의 마지막 접수 글 또는 빈 값. AS 방문일 · 시간 · 일정 연결 · 출고 추천 표식을 비운다.
  5. 그 건 번호가 찍힌 기록 줄은 가림 표시(`deleted=True`). 원문과 첨부는 지우지 않는다. "AS 접수 취소됨 · 사유" 시스템 줄 하나를 남긴다(호출부 목록 시험 `tests/domains/test_as_timeline_contract.py:278` 에 올린다).
  6. 이벤트 `AS_CANCELLED` + 감사 기록 + 이벤트 글.
- 되돌릴 수 없는 것: 접수가 덮은 시공자 칸(`shipment.construction_workers`)과 지방 상차일. 스냅샷이 없다 — 12절 위험.
- 단추 자리(새 화면 없음, 기존 줄에 단추 하나)

| 화면 | 기기 | 자리 |
|---|---|---|
| [AS 접수 수정] 창(`asReceiveModal`)의 아래 줄 왼쪽 | PC · 휴대폰 | `templates/orders/partials/erp_order_tab.html:777-782` · `erp_order_tab_mobile.html:740-745` 의 창 아래 단추 줄 — [취소] · [수정 내용 저장] 왼쪽에 "이 AS 접수 취소" |
| AS 화면 회차 차트의 현재 건 머리 | PC · 휴대폰 | `templates/cs/partials/as_round_chart.html:156` 근처 |

주문 화면의 "본공정 단계" 줄에는 두지 않는다. 휴대폰에서 그 줄은 이미 단추 넷(단계 고르기 · 강제 · AS 표시 · AS 수정)으로 차 있어 다섯째가 화면 밖으로 밀린다(2026-11-20 스테이징 실화면 확인). PC 도 같은 창을 쓰므로 자리를 하나로 맞춘다.

단추는 접수 상태 + 권한이 있을 때만 그린다. 누르면 사유를 묻고, 끝나면 화면을 다시 읽는다.

## 5. 묶음 B — 틀린 완료 막기

### 5.1 시공일 읽는 도우미 하나

새 파일 `foms/services/orders/construction_dates.py`

- `all_construction_dates(sd) -> list[str]` — 주문 칸 글(`schedule.construction.date`, "2026-11-05, 2026-11-17" 꼴) + 취소 안 된 제품 칸 날짜. 정렬 · 중복 제거한 `YYYY-MM-DD`.
- `remaining_construction_dates(sd, after) -> list[str]` — `after` 보다 뒤인 날만.
- `remaining_construction_note(sd, today=None) -> str` — "11/17 시공이 남아 있어요" 또는 빈 글. 오늘은 `get_today_kst()`.
- 읽는 곳은 `structured_data` 다. 정본이고, 완료 단추가 있는 화면의 줄이 이미 들고 있어 추가 질의가 없다. `order_schedule_dates` 는 저장 훅이 만드는 사본이라 화면 판정에는 쓰지 않는다.
- 참고: 평면 칸 `erp_construction_date` 는 "가장 이른 날"이 아니라 글에서 "먼저 적힌 날"이다.

### 5.2 일괄 완료 도구

- `tools/ops/bulk_complete_past_construction_core.py:138-140` 은 `erp_construction_date < 기준일` 만 본다.
- 고침: `order_schedule_dates` 하위 질의로 `later_construction_date`(기준일 이후 가장 이른 시공일, 날짜 형식인 것만)를 뽑아 판정 함수(`:186-225`)가 **제외 사유**로 남긴다(`later_construction_date`). `main` · `as_stage_only` 둘 다.
- 안전망 둘: 판정에서 주문 칸 글을 도우미로 한 번 더 읽는다. 적용 직전(`:342-346`)에 다시 확인한다(계획 뒤에 시공일이 더해졌을 수 있다).
- 도구는 PostgreSQL 전용이라 PG 레인 시험에 5687 꼴 줄(일정 표 줄을 직접 넣는다)과 견줄 줄(시공일 하나)을 둔다.
- 문서 `docs/plans/2026-09-22-past-construction-bulk-complete-spec.md` 에 제외 사유 한 줄을 더한다.

### 5.3 완료 확인 창의 한 줄 (M13)

서버가 줄 · 카드 뿌리에 `data-remaining-construction="11/17 시공이 남아 있어요"` 를 그리고, 확인 글을 만드는 곳이 주문 번호로 찾아 덧붙인다. 새 끝점 · 새 JS 파일은 없다.

| 화면 | 기기 | 확인 창 | 글이 만들어지는 곳 |
|---|---|---|---|
| 시공 대시보드 [시공 완료] | PC · 휴대폰 | Bootstrap 창 | `templates/construction/partials/modals.html:34`, `static/js/construction/dashboard.js:455-469` |
| 시공 [완료 준비] · 작업 모드 | 휴대폰 · 태블릿 | 바닥 시트 | `templates/construction/partials/complete_gate_sheet.html:78-89`, `static/js/construction/foms-complete-gate.js:101-131` |
| 생산 대시보드 · 목록 카드 [제작 완료] | PC · 휴대폰 | `confirm()` | `templates/production/partials/scripts.html:294-297` |
| 생산 칸반 | 태블릿 | `confirm()` | `static/js/foms/tablet-production-kanban.js:54-76` |
| 생산 옆 시트 · 시트 페이지 | 태블릿 · 휴대폰 · PC | `confirm()` | `static/js/foms/tablet-domain-sheets.js:64-68, 148-154` |
| 실측 화면 [완료] | PC | `confirm()`, 글은 서버가 준다 | `foms/services/orders/complete_path_policy.py:256-277` |

- [제작 완료]의 글은 따로 둔다: "시공일이 11/5 · 11/17 두 번이에요. 제품이 모두 제작됐나요?"(서로 다른 시공일이 둘 이상일 때만).
- `construction_dashboard_display.py` 는 499줄이라 한 줄도 늘릴 수 없다 — 새 값은 웹 쪽(`foms/web/construction/dashboard.py:236` 뒤)에서 단다.
- 주문 화면 단계 고르기와 목록 일괄 상태 바는 확인 창이 없어 한 줄 붙일 곳이 없다 — 남는 구멍으로 적는다(11절).

### 5.4 자동 할 일 · 임박 배지 (M20)

- `foms/services/orders/erp_policy_tasks.py:50-56, 76-79`: 날짜가 둘이면 시공 D-3 · 생산 D-2 할 일이 안 나오고, 긴급 할 일 기한에 날짜 둘이 든 글이 들어간다.
- 고침: 도우미로 목록을 읽어 오늘 이후 가장 가까운 날(모두 지났으면 마지막 날)을 쓴다. 날짜마다 따로 만들지 않는다(열린 할 일은 주문 · 키당 하나).
- 같은 구멍인 대시보드 임박 배지(`foms/services/erp_display.py:472-480`)도 같이 고친다.

## 6. 묶음 C — 다시 등록하기 전에 알려 주기

### 6.1 찾는 함수 하나 + 읽기 API 하나

- 새 모듈 `foms/services/orders/open_order_lookup.py`
  `find_open_orders_for_customer(db, *, phone, name=None, address=None, exclude_order_id=None, scope_clause=None, limit=3) -> list[dict]`
- 돌려주는 칸: `order_id, stage_code, stage_label, construction_dates[], address, customer_name, reason(phone|address)`.
- 거르기: `Order.active_filter()`(휴지통 · 초안 · 숨은 초안), ERP 주문, 단계가 완료가 아님, 자기 자신 제외, 자리표시자 전화(`010-0000-0000` 류) 버림.
- 찾는 축: 전화는 `erp_phone_digits` 포함 검색 뒤 조각 확인(전화 두 개가 붙은 칸 나누기는 상담 AI 용 `foms/services/cs_agent/order_find.py:88-120` 의 것을 중립 자리로 옮겨 같이 쓴다), 주소는 도로명 + 건물번호 + 동 · 호. 이름만 같은 것은 치지 않는다.
- 읽기 API `GET /api/orders/open-for-customer?phone=&name=&address=&exclude_order_id=` — 본사 직원 이상(프리랜서 · 협력사 403, M17). 응답 `{success, data:{orders:[…+url], more}, error}`.
- 네이버용 후보 찾기(`order_candidates.py`)는 입력이 네이버 링크이고 완료 · 휴지통까지 넣어 함수째로는 쓰지 않는다.

### 6.2 주문을 만드는 길 일곱과 안내 자리 (M15 · M17)

| 길 | 누가 쓰나 | 주문이 생기는 곳 | 안내 |
|---|---|---|---|
| 1 PC ERP 폼(초안 → 승격) | PC · 아이패드 | `foms/api/erp_orders_structured.py:964-1002` | 폼 위 띠 자리(`templates/orders/partials/erp_order_tab.html:49-61` 아래). 전화 · 주소 칸을 벗어날 때 |
| 2 휴대폰 마법사 | 휴대폰 · 안드로이드 태블릿 | `foms/api/erp_order_draft.py:782` | 4단계 맨 위(`templates/orders/wizard/step4_confirm.html:3` 아래) |
| 3 옛 폼 | PC | `foms/web/orders/listing.py:478` | 화면 안내 없음, 기록만 |
| 4 주문 복사 | PC 대시보드 표 | `foms/services/order_copy.py:196-215` | 도착한 편집 화면에 한 줄(1번과 같은 JS, 자기 자신 제외) |
| 5 협력사 | 협력사 직원 | `foms/services/partners/orders.py:223` | 화면 안내 없음, 기록만 |
| 6 채널톡 | 자동 | `foms/services/channel_order/creation.py:129` | 화면 없음, 기록만 |
| 7 네이버 | PC(사람이 누름) | `…/naver_commerce/promotion.py:229` | 이미 후보 표가 있다, 기록만 |

- 기록: `create_order`(`foms/services/orders/order_create.py:199-205`)와 초안 승격(`erp_orders_structured.py:890-895`)이 `ORDER_CREATED` payload 에 `open_order_ids` 를 남긴다. 새 칸은 없다. 4~8주 뒤 "안내를 보고도 만든 주문" 수를 여기서 센다.
- PC 길의 초안은 `orders` 표의 진짜 줄이고 자동 저장이 전화 숫자 칸까지 채운다. 초안과 자기 자신을 반드시 뺀다(안 빼면 헛 안내).
- 화면 글: "이 고객의 진행 중인 주문이 있습니다 — 주문 #5687 · 생산 단계 · 시공 11/17 · (주소) [그 주문 열기]". 여럿이면 세 건까지, 넘으면 "외 n건".
- PC 는 Bootstrap `alert alert-warning` + `data-foms-no-autodismiss` 로 새 CSS 없이 그린다. 휴대폰 마법사는 `foms-wizard.css` 에 클래스 하나를 더한다(인라인 스타일 금지).
- 새 JS: `static/js/orders/erp-same-customer-notice.js`, `static/js/foms/wizard-same-customer.js`(각 300줄 미만, jQuery 없음, `fetch` 는 try/catch + `data.success`).

### 6.3 주문 복사 — 넣을 것만 넣기 (M14)

`foms/services/order_copy.py` 를 "빼는 목록"에서 "넣는 목록"으로 뒤집는다.

- **옮긴다**: 고객 · 발주사 · 주문한 사람, 주소, 제품 본문(가격 · 할인 · 자유입력 포함), 접수 메모, 전화 · 주소 특이사항, 라홈시스템 표식, 영업 담당(지금 규칙 그대로).
- **옮기지 않는다**: 결제 확인 · 예약금 · 현금영수증, `settlement`, `as_lifecycle` · `as_info` · `as_drawing*`, `alimtalk_*`, AS PUSH 이력, `measurement_visits`, `calls`, `production`, `construction*`, 네이버 칸, 협력사 표식, `delete`, 제품 칸의 날짜 · 첨부 · 네이버 금액, 긴급 표시, 실측 메모, `meta` 의 나머지.
- 새 열쇠가 생기면 기본이 "안 옮김"이 된다 — 그것이 뒤집는 까닭이다.
- 시험: `tests/domains/test_order_copy_api.py:159`(예약금이 따라간다는 단언)를 뒤집고, 허용 목록 · `as_axis_status` · 일정 줄 단언을 더한다.

## 7. 묶음 D — 작은 것 둘

### 7.1 둘째 AS 의 첫 PUSH (M18)

- 지금: `is_resend = prev_push.pushed` 하나로 판정하고 AS 건을 보지 않는다(`foms/api/channel/channel_integration.py:640-652`). 그래서 둘째 건의 첫 PUSH 가 "[수정] 재전송"이 되고 변경 내용을 강요한다.
- 새 판정(미리 보기와 전송이 같은 함수, 중립 services 모듈에 두고 협력사 쪽 `foms/services/partners/as_intake.py:138-152` 도 그것을 부른다)
  - 재전송: 현재 건이 없음 / 현재 건이 옛 주문 끌어올리기 건 / 이력의 `as_cycle_id` 가 현재 건과 같음.
  - 새 건의 첫 PUSH: 이력의 `as_cycle_id` 가 현재 건과 다름. 건 번호가 없는 옛 이력은 `보낸 시각 < 건을 연 시각` 일 때.
- 새 건 첫 PUSH 는 변경 내용을 요구하지 않고 `[수정]` 도 없다. 순번이 2 이상이면 본문 맨 앞에 "새 AS 접수 (N번째 AS)".
- 저장 모양: `channeltalk_push_as` 에 `as_cycle_id` 한 칸만 더한다. 옮기는 작업은 없다.
- 화면: AS 화면 첨부 창 · AS 카드 · 도면 작업실 AS 카드는 클라이언트를 고치지 않아도 된다(지금 있는 "400 → 입력 창 → 다시 보내기"가 같은 건 재전송을 받는다). ERP 주문 화면만 미리 묻기를 AS 에서 뺀다(`static/js/orders/erp-order-shared.js:6171-6177`).
- 같이 풀리는 것: 도면 작업실 "접수하고 시작"이 전에 AS PUSH 를 보낸 주문에서 400 이 나던 것.
- 검증은 미리 보기와 가짜 발송 시험만 쓴다(스테이징 AS 방이 운영 실제 방이다).

### 7.2 최종 도면 한 장 덮어쓰기 (M19)

- 지금: 생산 · 시공 단계 + 방식 지정 없음 + 현재 한 장이면 통째로 바뀐다(`foms/api/drawing/erp_orders_drawing.py:279-283, 358-362`).
- 새 조건(순수 함수는 `foms/services/orders/drawing_transfer.py`): 그 한 장이 살아 있는 시트 S 의 도면이고, 이번 파일이 전부 S 가 아닌 시트면 바꾸지 않고 더한다. 알 수 없으면(직접 올린 파일, 시트 번호 없음) 지금 그대로 바꾼다.
- 가를 수 있는 것은 "다른 제품"이 아니라 "다른 시트"다. 시트와 제품은 자리 번호로만 이어져 있다.
- 작업실 전달 창의 미리 골라진 값도 같은 조건에서 "더하기"로 둔다(`foms/web/drawing/workbench.py`, `templates/drawing/…/workbench_detail_body.html:1855`).
- "확정 전 재전달 = 전체 교체"(`erp_orders_drawing.py:269-273`)와 "ERP 에는 최종본만"은 건드리지 않는다.

## 8. 기기별 한눈 표

| 고침 | PC | 태블릿 | 휴대폰 |
|---|---|---|---|
| A 남은 시공 줄 | 출고 대시보드 표 · 날짜 띠 | 시공 탭 첫 화면 · 날짜 미정 · 상세 단추, 출고 탭 출고표 · 서랍 | 출고 카드 |
| A 단계 바꿔도 AS 표시 | 주문 화면 [강제], 목록 상태 바꾸기 | (같은 창) | 주문 화면 |
| A AS 접수 취소 | [AS 접수 수정] 창, AS 화면 회차 차트 | AS 화면 회차 차트 | [AS 접수 수정] 창, AS 카드의 회차 차트 |
| B 완료 확인 한 줄 | 시공 대시보드, 생산 대시보드, 실측 화면 | 시공 작업 모드, 생산 칸반 · 옆 시트 | 시공 [완료 준비], 생산 카드 |
| B 일괄 완료 도구 | (화면 없음) | | |
| C 새 주문 안내 | ERP 주문 폼, 복사 도착 화면 | (아이패드 = PC 폼, 안드로이드 = 마법사) | 새 주문 마법사 4단계 |
| C 주문 복사 | 대시보드 표의 복사 | (없음) | (없음) |
| D 둘째 AS PUSH | AS 화면 · 주문 화면 · 도면 작업실 | AS 비교 판 | AS 카드 · 주문 화면 아래 막대 |
| D 도면 한 장 | 작업실 전달 창 | [시트 전달] | 작업실 전달 창 |

## 9. 구현 나누기 — 갈래와 파일 소유

갈래마다 세션 워크트리 하나. 다른 갈래가 가진 파일은 고치지 않는다. 겹치는 파일은 아래처럼 한 갈래에 몰았다.

| 갈래 | 워크트리 | 가진 파일(대표) | 핀 글자 |
|---|---|---|---|
| A | `c:/tmp/foms-s-ms-a` | 4절의 모든 파일, `as_cycle_service.py`, `foms/api/cs/as_orders.py`, `erp_order_tab*.html` 의 "본공정 단계" 줄, `as_round_chart.html`, 새 `static/js/orders/erp-as-cancel.js`, `erp-stage-override.js`, `construction_dashboard_display.py`, `foms/web/shipment/dashboard.py`, `foms/api/production/orders.py` | `20261121a` |
| B | `c:/tmp/foms-s-ms-b` | 5절의 모든 파일, `tools/ops/bulk_complete_*`, `complete_path_policy.py`, `foms/web/construction/dashboard.py`, `erp_policy_tasks.py`, `erp_display.py`, 생산 · 시공 확인 창 템플릿과 JS | `20261121b` |
| C | `c:/tmp/foms-s-ms-c` | 6절의 모든 파일, `order_copy.py`, `order_create.py`, `erp_orders_structured.py`, 마법사 템플릿 · CSS, `erp_order_tab.html` 의 띠 자리(49-61줄 근처만) | `20261121c` |
| D | `c:/tmp/foms-s-ms-d` | 7절의 모든 파일, `channel_integration.py`, `partners/as_intake.py`, `erp-order-shared.js`, `drawing_transfer.py`, `erp_orders_drawing.py`, 작업실 전달 창 | `20261121d` |
| 통합 | `c:/tmp/foms-s-ms-integ` | 이 설계서, `docs/AI_STATUS.md`, 인벤토리 다시 뽑기, 핀 · 자산 수 맞추기 | — |

갈래 공통 규칙: 인벤토리 JSON 은 마지막 커밋 하나로 따로(통합 때 다시 뽑는다). 자산 수를 세는 시험(`tests/contracts/assets/test_asset_manifest.py`)은 각자 +1 하고 통합이 맞춘다. 함수 안 `foms` 가져오기 금지. 새 파이썬 파일 500줄 · 새 JS 300줄 미만. 인라인 스타일 금지. push 하지 않는다.

## 10. 시험과 검증

- 갈래마다: 고친 파일에 닿는 시험만(`python -m pytest <파일> -n 4 -q`), 새 시험 추가, `python -c "import app; print('APP_OK')"`, 고친 JS 는 `node --check`.
- 통합 뒤: 인벤토리 다섯 개 다시 뽑기, 층 의존 · 파일 크기 래칫, `scripts/ops/pre_push_smoke.ps1`(한 번), `tests/harness`, PG 레인(일괄 도구 · 주문 복사).
- 실화면(스테이징, 가상 주문 `CLAUDE-TEST-`): 5687 꼴 주문(제품 2개 이상 · 시공일 2개 · 생산 단계 · AS 접수)과 견줄 주문(시공일 하나 / 완료 + AS 접수)을 만들어 8절의 화면을 기기별로 본다. 채널톡은 실제로 보내지 않고 미리 보기만 본다.
- 바뀌는 기존 시험(대표): `test_construction_tablet_d43.py:194-208, 271-280`, `test_as_bulk_status_guard.py:119-160`, `test_as_overlay_stage_preserve.py:138-162`, `test_order_copy_api.py:159`, `test_bulk_complete_past_construction_plan.py:101-105`, `tests/security/test_partner_as_intake_v2.py:180-191`.

## 11. 하지 않는 것 · 남는 구멍

- 제품마다 단계 · 승인 · 생산 기록을 따로 두지 않는다. 주문 안 묶음(1차 · 2차)도 만들지 않는다.
- 제품별 "시공 끝" 표시(계획 2단계)는 1단계가 들어간 뒤 4~8주 숫자를 보고 정한다.
- 나중에 더 산 제품을 같은 주문에 넣는 일(계획 3단계)은 따로 설계한다. 그 전까지는 새 제품만 담은 새 주문으로 받는다.
- 주문 자동 합치기, 돈을 제품별로 쪼개기, 날짜가 지났다고 자동으로 단계를 넘기기 — 하지 않는다.
- 남는 구멍
  - 지방 · 수도권 · 자가실측 보드는 AS 상태 주문을 AS 칸에만 둔다(M5).
  - 아래 탭 배지 수 · 지도 · 출고 [AS 추천] 기준 줄 · 완료(정산) 대시보드는 그대로다.
  - 주문 화면 단계 고르기와 목록 일괄 상태 바에는 "시공이 남았다"는 한 줄이 없다(확인 창이 없다).
  - AS 접수가 시공자 칸을 접수자 한 명으로 덮는다. 본 흐름이 열린 주문이면 남은 시공 줄의 시공자 묶음이 바뀐다.
  - 본 흐름이 안 끝났는데 AS 가 걸린 주문은 실제 매출에 전액이 보인다(회계팀과 정할 일).
  - 시공일 안내 알림톡: 제품 칸에만 적힌 뒤 시공일은 안내가 안 나간다.
  - 새 주문 안내가 못 찾는 것: 비 ERP 주문, 네이버 둘째 번호, 동 · 호 없는 주소.

## 12. 위험

1. 1단계는 "막기"라 직원이 단추를 누르지 않아도 돈다. 다만 생산 · 시공 단계를 실제로 쓰기 시작해야 효과가 보인다.
2. AS 접수 취소는 접수가 덮은 시공자 칸 · 상차일을 되돌리지 못한다.
3. 손으로 단계를 바꿔 AS 표시를 지우던 습관이 막힌다. 강제 변경 창 안내 한 줄과 취소 단추가 대신한다.
4. 둘째 AS 의 PUSH 글이 실제 직원 방에 나가는 글을 바꾼다. 운영 첫 발송 한 건은 눈으로 확인한다.
5. 출고 날짜 띠 수가 바뀐다(캐시 판을 올린다).
6. 사람들이 왜 그렇게 했는지는 추정이다(11-05 에 왜 아무것도 안 눌렀는지, 6026 에 왜 세 제품을 다시 넣었는지).

## 13. 진행 원장

| # | 일 | 완료 기준 | 상태 |
|---|---|---|---|
| T0 | 설계서 · 워크트리 · 갈래 브리프 | 이 문서 커밋 | DONE |
| T1 | 갈래 A 구현 + 시험 | 4절 전부, 닿는 시험 초록 | PENDING |
| T2 | 갈래 B 구현 + 시험 | 5절 전부, 닿는 시험 초록 | PENDING |
| T3 | 갈래 C 구현 + 시험 | 6절 전부, 닿는 시험 초록 | PENDING |
| T4 | 갈래 D 구현 + 시험 | 7절 전부, 닿는 시험 초록 | PENDING |
| T5 | 갈래별 교차 검수 + 고침 | 지적 0 또는 원장에 남김 | PENDING |
| T6 | 통합(체리픽 · 인벤토리 · 핀 · 래칫) | 전체 레인 초록 | PENDING |
| T7 | smoke → deploy push → CI 초록 | 스테이징 배포 확인 | PENDING |
| T8 | 스테이징 실화면 확인(PC · 태블릿 · 휴대폰) | 8절 화면 전부 | PENDING |
| T9 | 운영 반영 | 사장님이 따로 말씀하실 때 | 대기 |
