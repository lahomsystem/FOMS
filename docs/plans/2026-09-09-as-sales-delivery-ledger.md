# AS 전달 배정 — 진행 원장

설계서: `docs/specs/2026-09-09-as-sales-delivery-measurement-assignment-design.md`
브리프: `docs/plans/2026-09-09-as-sales-delivery-measurement-link-brief.md`
목업: Claude Design 캔버스 "AS 전달 배정 화면" (아트보드 6장)
사용자 승인: 2026-09-09 (3단계 상태 · 후보 0건이면 택배 우선 · 멀티 에이전트 병렬)

## 파일 소유권 (동시 편집 충돌 방지)

| Task | 소유 파일 (편집 허용) |
|---|---|
| T1 | `foms/services/orders/sales_delivery_link.py`, `tests/domains/test_sales_delivery_link.py` |
| T2 | `foms/api/cs/as_orders.py`, 레지스트리 JSON 2종, `foms/services/audit_message_display.py`, `tests/domains/test_sales_delivery_api.py` |
| T3 | `foms/services/schedule_recommendations.py`, `foms/api/orders/nearby.py`, `tests/domains/test_nearby_measurement_kind.py` |
| T3b | `foms/services/orders/sales_delivery_map.py`, `tests/domains/test_sales_delivery_map.py` |
| T4 | `foms/services/as_dashboard_display.py`, `templates/cs/partials/as_dashboard_body.html`, `templates/cs/partials/as_card_macros.html`, `static/js/cs/as-dashboard.js`, `static/css/contexts/cs/as-dashboard-body.css`, `tests/domains/test_as_dashboard_sales_delivery_render.py` |
| T5 | `foms/web/measurement/dashboard.py`, `templates/measurement/partials/dashboard_main.html`, 실측 CSS, `tests/domains/test_measurement_sales_delivery_render.py` |
| T6 | v3 모바일 템플릿·CSS, 해당 테스트 |
| T7 | (총괄 전용) 전체 게이트·smoke·push |

공통 규칙: CRLF 보존 · git 명령 금지(총괄이 수행) · docs 를 읽는 테스트 금지 ·
`_AS_SERVER_OWNED_SHIPMENT_KEYS` 등재는 T2 소유.

## 진행 상태

| Task | 상태 | 검증 명령 / 결과 |
|---|---|---|
| T1 순수 서비스 | **DONE** | `pytest tests/domains/test_sales_delivery_link.py -q` → 20 passed (총괄 재실행 확인), `APP_OK` |
| T2 쓰기 API + 레지스트리 4종 | **DONE** | 총괄 재실행 `tests/domains` 6773 passed. 부수 근본수정: 서버 전용 키 보존이 dict/list 만 지켜 문자열 키가 폼 저장마다 지워지던 것 수정 |
| T3 nearby kind=measurement | **DONE** | 총괄 재실행 59 passed (nearby+boundary+asrec+timeline), `APP_OK`. 판단: 실측 경로만 route_timeout 3.0s, 대시보드 스코프 헬퍼는 자가실측·지방을 포함시키는 반대 술어라 미재사용 |
| T3b 역방향 맵 | **DONE** | 총괄 재실행 10 passed, `APP_OK`. 총괄 보완: `item_text` 가 항상 빈 문자열이던 것을 AS 내용(`shipment.as_content`) 평문 한 줄(60자 말줄임)로 채우고 테스트 3건 추가 |
| T4 AS 탭 화면 | **DONE** | 렌더 테스트 + 로컬 dev 실화면 확인(미배정 버튼→배정 칩→요약 pill 갱신) |
| T5 실측 대시보드 | **DONE** | 렌더 테스트 + 실화면에서 `전달 1` 배지·동행 전달 카드 확인 |
| T6 모바일 v3 | **DONE** | 13 passed + v3 셸 실화면에서 '오늘 동선'·전달 카드 확인. wiring(2줄)·자산 핀은 총괄이 처리 |
| T7 전체 게이트 | **DONE(푸시 제외)** | `tests/domains` 6810 passed, `APP_OK`, pre_push_smoke exit 0. 커밋 `399292497`(백엔드)·`a2a36d462`(화면). **푸시는 사용자 지시 대기** |

## 기록

- 2026-09-09: 조사 4건·목업 6장·설계서 작성 완료. T1·T3 착수.

## 푸시 전 처리 필요 (중요)

- 공유 워킹트리에 **다른 세션의 미커밋 도면 작업**(`foms/api/drawing/erp_orders_drawing.py`,
  `tests/domains/test_state_drawing.py`, `docs/AI_CHANGELOG.md`)이 있다.
- 그 때문에 재생성된 `foms_order_mutation_writer_inventory.json` 에 도면 파일 줄밀림
  (514→523, 547→556)이 함께 들어갔다. REV-99 `test_no_new_external_writers` 는 (path, lineno, kind)
  를 정확 비교하므로, 도면 작업이 커밋되지 않은 채 push 하면 **CI red** 가 된다.
- push 직전에: 도면 세션 커밋 여부 확인 → 미커밋이면 인벤토리를 그 상태로 재생성
  (`python tools/harness/order_mutation_writer_scan.py`) 후 push.

## 로컬 QA 메모

- 로컬 dev DB 는 alembic 체인 불일치라 `upgrade head` 가 DuplicateColumn 으로 실패 → `stamp head` 로 우회함.
- QA 계정 `qa_claude` 는 로컬에 없다(메모리가 낡음). 이번엔 `qa_sd` 를 만들어 쓰고 비활성화해 뒀다
  (security_logs FK 때문에 삭제 불가). 시드 주문 2건은 soft-delete.
- v3 셸 로컬 재현 env 4개: `ERP_MOBILE_V2_ENABLED=1 FOMS_V3_SHELL_COHORT=all FOMS_SHELL_V3_ENABLED=1 FOMS_SHELL_V3_COHORT=all`.
- Git Bash 에 `pkill` 이 없다 — 옛 dev 서버가 남아 새 env 가 안 먹는다. `taskkill //F //PID` 로 정리.
