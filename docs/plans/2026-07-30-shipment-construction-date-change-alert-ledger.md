# Progress Ledger — 출고 대시보드 시공일 변경 알림 (2026-07-30, `**C`)

스펙: `docs/specs/2026-07-30-shipment-construction-date-change-alert-design.md`
플랜: `docs/plans/2026-07-30-shipment-construction-date-change-alert-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T1 시공일 변경 이벤트 SSOT 통합 | DONE | 커밋 `be817cc3`(+인벤토리 `2a3faad2`) → deploy. 실 라우트 7경로 각 1건·부정 4종 0건, domains 3799 passed, PG 147 passed, smoke exit 0 |
| T2 출고 변경 수집 서비스 | DONE | `shipment_change_alerts.py` 신규(배치 1쿼리·쿼리수 단언), 17 passed |
| T3 ack API | DONE | `POST /api/orders/<id>/shipment/change-ack`, 매니페스트 2종 등재, 9 passed |
| T4 PC 대시보드 표시 | PENDING | |
| T5 태블릿 표시(그리드·시트) | PENDING | |
| T6 벨 알림 + 푸시 타입 등록 | DONE(미커밋) | `shipment_change.py` 신규, `_DEFAULT_P1_TYPES` 등재, 신규 11 passed / 인접 4파일 59 passed / domains 전수 3866 passed / contracts 65 / performance 78 / APP_OK |
| T7 성능 측정(TTFB·EXPLAIN) | PENDING | |
| T8 최종 검증·커밋·푸시 | PENDING | |

## 사용자 결정 (2026-07-30)

- 감지 범위: **시공일만**(시공팀·주소·품목 제외)
- ack: **사용자 개인별**(생산 칸반 방식)
- 채널: **화면 + 알림센터 벨 + 모바일 푸시**
- 표면: **PC · 태블릿**(모바일 v2/v3 범위 밖)

## 조사 확정 사실 (재조사 금지)

- 출고/시공 팀 대상 변경 알림은 **코드베이스에 0건** — 세 번째 복사본을 만드는 게 아니라
  생산 칸반 패턴(OrderEvent 윈도 + 개인 ack)을 확장하는 것이 맞다.
- ack 클라이언트(`tablet-domain-sheets.js` `changeAck()`)는 **이미 출고 페이지에 로드돼 있다**.
- `CONSTRUCTION_DATE_CHANGED` emit 은 2개 파일뿐 — 재예약·품목별 날짜·레거시 폼·엑셀 임포트가
  전부 무음. 유일한 공통 통과 지점은 `order_date_sync.py` 전역 `before_flush`.
- 대시보드 변경감지는 슬라이스 캐시(TTL 300s) 밖에서 계산한다 — 생산 칸반 선례가 명시.
- `/erp/shipment?view=fragment` TTFB 예산 291ms, 상향 금지 이력 있음.
- 푸시는 `_DEFAULT_P1_TYPES` 등록이 없으면 발송되지 않는다(생산이 그 상태).

### T1 (2026-07-30)

- emit 을 `order_date_sync` 전역 `before_flush` 로 이관, 라우트 emit 2곳 제거.
- **flush 단위 diff 만으로는 경로당 1건이 안 된다** — `field_update` 는 레거시 컬럼 먼저,
  JSONB 나중의 2단 쓰기라 중간 flush 에서 이벤트가 2건 났다. 트랜잭션 최초값(origin)을
  `session.info` 에 기억해 이후 flush 는 `to` 만 갱신하고, 값이 origin 으로 되돌아오면
  이벤트를 취소한다(커밋·롤백 시 상태 정리). 재진입 가드 별도.
- **엑셀 임포트는 생성 전용 경로**라 이벤트 0건이 정상 — 스펙 §3 "구멍 #5" 는 기존 주문의
  날짜 이동이 아니었다. T2 소비자 설계에 영향 없음(생성은 알릴 것이 없다).
- 인벤토리 3종은 타 세션 재생성과 충돌 → **원격 tip 클린 worktree 재생성**으로 분리 커밋.
  (수기 병합 금지. 이 충돌은 코드 의존 신호가 아니다.)

### T2·T3 (2026-07-30)

- 배너는 `collect_shipment_change_alerts` → `build_shipment_change_banner` 2줄 호출.
  쿼리는 앞의 1회뿐이고 배너는 순수 파생 — **대시보드 슬라이스 캐시 밖**에서 호출한다.
- ack 응답이 in-place DOM 갱신용 값을 준다: `remaining`(그 주문 잔여=0),
  `banner_count_hint`(배너 카운트 증감, 미확인이 있었으면 -1). 사용자 결정 "확인하면 그
  표시만 사라지기"라 T4 는 페이지 리로드를 쓰지 않는다(생산 선례의 `location.reload()` 미답습).
- 다중값 시공일 표기: 토큰마다 `M/D`, 3개 초과분은 `외 N`.
- 손상 payload(구형·비정규화·비-dict) 전부 무예외 처리 — 못 읽으면 표시에서 제외.
- `login_required` 데코레이터는 쓰지 않았다(302 redirect 라 API 계약을 깬다) —
  in-handler 강제로 미인증 401 JSON. packing API 선례. 테스트로 고정.

## 추가 사용자 결정 (2026-07-30)

- 진행: 1단계 확인 후 바로 계속
- 알림 모양: **AS 화면과 동일**(파스텔 배너 + 점프 칩 + 행 배지)
- 확인 버튼: **그 표시만 사라짐**(리로드 없음)
- 노출 기간: **확인할 때까지 계속**(시간 상한 없음 — 생산의 14일 컷오프 미적용)

### T6 (2026-08-05)

- **`target_team` 확정 = `CONSTRUCTION`**(시공팀). 운영 DB 활성 사용자 실측(2026-08-05):
  CONSTRUCTION 10 · SALES 8 · CS 6 · DRAWING 3 · ADMIN(팀 공란) 2 — **`SHIPMENT`(출고팀)은
  enum 에만 있고 실사용자 0명**이다. `SHIPMENT` 를 고르면 `fan_out` 이 0건이 되어
  `PRODUCTION_ORDER_CHANGED`(PRODUCTION 팀 0명, 운영 알림 1건이 아무에게도 안 감)와 같은
  무음 알림이 된다. 출고 대시보드도 이미 `team == 'CONSTRUCTION'` 전용 모드를 가진다
  (`shipment_dashboard_filters.py:58`).
- **배선 = 전역 세션 이벤트**(`register_shipment_change_alert_listener`, `order_date_sync`
  등록부에서 함께 호출). `before_commit` = apply(같은 트랜잭션 + fan_out),
  `after_commit` = finalize(push·배지·realtime). 쓰기 경로별 명시 호출은 T1 이 없앤 구멍 6종을
  알림 쪽에 되살리므로 채택하지 않았다.
- **함정**: `before_commit` 은 커밋 flush 보다 **먼저** 돈다 → T1 의 pending 상태가 아직 비어
  있다. apply 진입부에서 `session.flush()` 를 한 번 해 주지 않으면 알림이 통째로 무음이었다.
- merge 시 최초 `from` 은 본문 정규식으로 되읽는다(Notification 모델에 구조화 필드가 없다).
- 딥링크: 모델에 링크/날짜 컬럼이 **없어** 신설하지 않고, 벨 목록 API가 이미 로드한 주문
  `structured_data` 에서 파생한다(`/erp/shipment?date=`). push payload 는 generic 규약이라
  날짜 없이 `/erp/shipment`.
- 미검증: `tests/postgres` 전수(T8), 스테이징 실브라우저 벨·푸시 수신.

## 미해결 / 대기

- 스펙 **승인 완료**(2026-07-30). 감지 통합안 = **A**(단일 이벤트 SSOT, 생산 칸반 노출도 함께 증가).
- 다음: T7(성능 측정) → T8(마감). T6 은 커밋 전 상태다.
- `target_team` = `CONSTRUCTION` 확정(위 T6 절 근거).
