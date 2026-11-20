# 한 주문 여러 시공일 1단계 — 검수 원장

> 설계서: `docs/specs/2026-11-20-multi-item-split-schedule_SPEC.md`. 검수에서 나온 지적을 받는 즉시 여기에 적는다.
> 상태: OPEN(고칠 것) · FIXED(고침 · 확인함) · KEPT(그대로 둠, 까닭 적음) · LATER(다음 단계).

## 묶음 D (둘째 AS PUSH · 도면 한 장) — 검수 1회차 2026-11-20

| # | 심각도 | 내용 | 자리 | 상태 |
|---|---|---|---|---|
| D-1 | 고칠 것 | 수정 요청에 답하는 길(도면 상태 RETURNED)에서는 여전히 한 장이 통째로 바뀐다. 생산 단계 + 최종 한 장(시트 A) + 시트 B 만 전달 → A 가 사라진다. 작업실 전달 창 기본값도 RETURNED 에서는 "교체" | `foms/api/drawing/erp_orders_drawing.py:275-276, 362-366`, `foms/web/drawing/workbench.py:1564` | FIXED |
| D-2 | 작음 | AS 접수 취소로 앞 건(완료)으로 돌아간 주문의 다음 PUSH 가 "첫 PUSH"로 판정된다(변경 내용 · [수정] 없이 나감). 이력에 적힌 건 번호가 `cycles[]` 에 없을 때만 시각 비교로 내려가게 | `foms/services/channel_as_push_cycle.py:54-61` | FIXED |
| D-3 | 작음 | 주문 화면에서 같은 건을 다시 보낼 때 여러 줄 입력 창 대신 "확인 창 → 전송 → 400 → 브라우저 기본 입력 창(한 줄)" 순서가 된다. 설계서 7.1 이 허용한 흐름. `as-push-confirm.js` 가 282줄(한도 300)이라 손대지 않는다 | `static/js/cs/as-push-confirm.js:206-211` | KEPT |
| D-4 | 작음(미확인) | 도면 작업실 AS 카드의 [AS방에 접수 올리기] 단추가 차수의 건과 지금 건을 견주지 않는다. 앞 건의 차수가 안 닫힌 채 새 건이 열리면 도면팀 단추로 새 건의 첫 PUSH 가 나갈 수 있다 | `foms/services/drawing_workbench_as_rows.py:201` | FIXED |
| D-5 | 작음 | 협력사 둘째 AS 가 실제 발송 함수까지 가는 시험이 없다 | `tests/security/test_partner_as_intake_v2.py` | FIXED |
| D-6 | 범위 밖 | 고객컨펌 단계 + 확정 + 한 장 + 다른 시트 대기일 때 작업실 전달 창 기본값 "교체"가 그 한 장을 미리 골라 둔다(서버의 방식 없는 길은 더한다). 이번 갈래가 만든 동작은 아니다 | `templates/drawing/partials/workbench_detail_body.html` | LATER |
| D-7 | 범위 밖 | 수동 PUSH 가 주문을 슬롯 잡기 전에 읽는다 — 앞 요청 커밋 직후 들어온 요청은 낡은 사본으로 판정할 수 있다. 옛 코드도 같다 | `foms/api/channel/channel_integration.py:579-593` | LATER |

검수가 확인해 맞았던 것: 판정 블록 이동으로 달라지는 값 없음, 파일 유실 · 중복 없음, 이력 쓰는 곳 하나, 미리 보기와 전송이 같은 함수, 새 시험 9개가 옛 코드에서 실패함, 손댄 시험 231개 통과.

검수 고침(2회차): D-1 · D-2 · D-4 · D-5 를 `26f5817ce` · `21c44a2da` 로 고침. 총괄이 닿는 시험 8개를 다시 돌려 241개 통과를 확인. D-1 은 전달 창이 늘 방식을 보내므로 조건을 "방식이 비었거나 추가"로 넓혔다(교체 · 전체 교체를 고른 것은 그대로 따른다). D-4 확인: AS 도면 차수는 건을 넘겨 살아남을 수 있다(코드 확인).

## 묶음 A-1 (줄 종류 판정과 그 화면들) — 검수 1회차 2026-11-20

심각한 결함 없음. 진리표(상태 3 × 단계 5 × 날짜 5 = 75칸)를 실제 함수로 돌려 설계서 4.1 · 4.2 와 맞는 것을 확인.

| # | 심각도 | 내용 | 자리 | 상태 |
|---|---|---|---|---|
| A-1 | 고칠 것 | 태블릿 시공 상세가 "그날"을 모른다. AS 방문일(시공일과 다른 날)의 "AS 방문" 줄을 눌러 들어가도 상세는 [시공 시작]을 그리고 "AS 방문 집이에요"가 없다. 왼쪽 목록 순서도 첫 화면과 어긋날 수 있다. 결정: 상세는 그날 줄 종류를 따른다 — AS 방문 줄로 들어오면 지금처럼 "AS 방문 집이에요" · 시공 단추 없음 | `foms/services/construction/tablet_view.py:92`, `foms/services/construction_dashboard_display.py:451` | FIXED |
| A-2 | 고칠 것(실화면 미확인) | 태블릿 출고표 시공시간 칸(폭 9.5% · 한 줄 · 말줄임)에 "AS 방문도"를 붙여 잘릴 가능성이 높다. 고객 칸 표식처럼 따로 놓는다 | `templates/shipment/partials/tablet_ship_grid.html:92`, `static/css/contexts/shipment/tablet-day-sheet.css:46, 104-112` | FIXED |
| A-3 | 고칠 것(작음) | 협력사 출고 탭이 AS + 본 흐름 열림 주문마다 쿼리를 한 번씩 더 쓴다(1건 → 6건일 때 5 → 10). `selectinload(Order.schedule_dates)` | `foms/services/partners/shipment_board.py:154-157` | FIXED |
| A-4 | 작음 | 휴대폰 [AS 추천] 줄 키가 PC 표와 어긋난다. 서버가 AS 상태 주문을 걸러 결과는 같고 주석 · 시험 설명만 틀렸다 | `foms/web/shipment/dashboard.py:713` | FIXED |
| A-5 | 작음 | CASE 꼴을 지키는 시험의 첫 단언이 새 표식 글자 때문에 헛돈다 | `tests/domains/test_construction_tablet_first.py:259` | FIXED |
| A-6 | 작음 | 출고 기간 보기에서는 다른 날이어도 "AS 방문도"가 붙는다(M3 은 같은 날만) | `foms/services/shipment_dashboard_display.py:65-69` | FIXED |
| A-7 | 작음 | 옛 딥링크가 지난 시공일로 열린다(전에는 앞날 AS 방문일로 열렸다) | `foms/services/construction/tablet_view.py:67-73` | FIXED |
| A-8 | 작음 | PC 표 템플릿의 대비 값이 파이썬 판정과 다르다. 라우트가 늘 값을 붙여 닿지 않는 길 | `templates/shipment/partials/dashboard_main.html:497` | KEPT |

미확인으로 남은 것: 실제 PostgreSQL 에서의 계획 시간과 `max(CASE…)` 형 추론(통합 뒤 PG 레인으로 확인), A-2 실화면. 운영에 "AS 상태 + 생산 · 시공 단계" 주문은 0건(2026-11-20 총괄이 읽기 전용으로 셈)이라 옛 AS 방문일이 시공 줄로 되살아날 주문은 지금 없다.

## 묶음 A-2 (손으로 단계 바꾸기 · AS 접수 취소) — 검수 1회차 2026-11-20

심각한 결함 없음. 단계 쓰기 여섯 길(4.3)은 결함을 찾지 못함. 취소 명령(4.4)에 고칠 것 다섯.

| # | 심각도 | 내용 | 자리 | 상태 |
|---|---|---|---|---|
| A-11 | 고칠 것(높음) | 건 기록이 없는 옛 AS 완료 주문을 잘못 재접수한 뒤 취소하면 AS 이력이 통째로 사라진다(상태 CS, AS 축 · 접수일 · 완료일 빔, AS 화면 완료 탭과 정산 AS 모집단에서 빠짐). 재접수가 유일한 건이 되어 "남은 건 없음"으로 보기 때문. 같은 뿌리: 접수 전 물류 상태였던 주문이 취소 뒤 본 흐름 글이 된다. 고침: 접수가 덮기 전 값을 건에 `pre_register` 로 남기고 취소가 그 값으로 되돌린다. 스냅샷 없는 기존 건은 그 건보다 오래된 안 가려진 AS 기록 줄이 있으면 409 | `foms/services/orders/as_cycle_cancel.py:157-166`, `as_cycle_service.py:312-333` | FIXED |
| A-12 | 고칠 것 | 보류 중인 주문의 AS 를 취소하면 보류가 조용히 풀린다(`ON_HOLD` → `PRODUCTION`). 상태 글이 AS 글일 때만 단계 글로 바꾼다 | `as_cycle_service.py:332` | FIXED |
| A-13 | 고칠 것(돈) | 취소한 접수에서 확정한 유상 금액이 남아 정산에 계속 잡힌다. 그 건을 연 뒤에 확정한 판정은 걷는다 | `as_cycle_cancel.py:106-111` | FIXED |
| A-14 | 고칠 것 | 단추 자리가 바뀐 설계서와 다르다(주문 화면 단계 줄 → [AS 접수 수정] 창 아래 줄). 설계서가 지목한 템플릿도 틀렸다 — `asReceiveModal` 은 `erp_order_tab.html:777-782` · `erp_order_tab_mobile.html:740-745` 에 있다 | `templates/orders/partials/erp_order_tab*.html`, `static/js/orders/erp-as-cancel.js`, `tests/domains/test_as_cancel.py:281-304` | FIXED |
| A-15 | 고칠 것(낮음) | 비 ERP 주문은 단추가 그려지지만 늘 409 다. 단추를 숨긴다 | `foms/services/orders/as_cancel_policy.py:27-34` | FIXED |
| A-16 | 작음 | 사고 복구 도구가 취소한 주문을 AS 접수로 되살리자고 제안한다(`AS_CANCELLED` 를 모름) | `tools/ops/data_doctor.py:223-227` | FIXED |
| A-17 | 작음 | 취소 뒤에도 `shipment.sales_delivery_link` 가 남는다 | `as_cycle_cancel.py` | FIXED |
| A-18 | 작음 | 수정 제작 시작 응답의 `new_status` 가 저장값과 다르게 `PRODUCTION` 으로 고정 | `foms/api/production/orders.py:1132` | FIXED |
| A-19 | 작음 | 강제 변경 안내 글 "AS 대시보드에서 사라지므로"가 이제 사실과 다르다 | `foms/services/orders/stage_override.py:98-101` | FIXED |
| A-20 | 작음 | 사유가 500자를 넘으면 400 이 아니라 409 | `foms/api/cs/as_orders.py` | FIXED |
| A-21 | 작음 | 핀 단언이 정확값에서 `>=` 글자 비교로 느슨해졌다 | `tests/domains/test_confirm_drawing_gate_screens.py:224-226` | FIXED |
| A-22 | 그대로 | 상태 쓰기 감사 글의 before 와 after 가 같은 AS 글, 칸 고치기 응답에 "단계만 옮김" 안내 없음, 닫힌 AS 를 덮을 때 "AS 표시 해제" 흔적이 응답에 없음(이벤트 `from_status` 는 남음) | `foms/api/orders/status.py:442, 729`, `field_update.py:787` | KEPT |
| A-23 | 그대로 | 처리 중으로 잘못 넘어간 건은 완료 → 완료일 지우기 → 취소 세 걸음이 필요하다(길은 있다) | — | KEPT |

검수가 확인해 맞았던 것: 여섯 길의 여덟 주문 꼴, 막다른 길 없음, 순환 · 래칫, 취소 명령의 건 하나 · 앞선 완료 건 · 옛 주문 · 연속 두 번 · 재접수 순번 · 열린 AS 도면 409, 읽는 화면들, 권한(영업 403 · 회계 200), JS.
미확인: PostgreSQL 행 잠금 아래 동시 요청, 본사 취소 뒤 협력사 옛 화면의 "수정", 다른 탭의 옛 폼 저장이 AS 글을 되살리는지.

검수 고침(묶음 A 2회차): 위 OPEN 18개를 `aceeea1aa` · `e2c65d512` · `95dd397e7` 로 고침. 총괄이 취소 · 줄 종류 · 상태 쓰기 · 태블릿 · 층 래칫 시험 10파일을 다시 돌려 133개 통과를 확인. 워커 판단 둘을 받아들임: (1) 스냅샷 없는 기존 건의 409 는 남은 건도 없을 때만 건다(남은 건이 있으면 그 건 값으로 되돌릴 수 있다), 옛 주문 끌어올리기 건은 409 검사에서 뺀다. (2) 전달 배정(`sales_delivery_link`)은 통째로 지우지 않고 접수 전 값으로 되돌린다. 남은 확인: PG 레인, 스테이징 실화면([AS 접수 수정] 창 단추 → 창 닫힘 → 사유 시트, 태블릿 출고표 고객 칸 표식).
