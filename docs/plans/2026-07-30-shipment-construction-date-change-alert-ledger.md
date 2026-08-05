# Progress Ledger — 출고 대시보드 시공일 변경 알림 (2026-07-30, `**C`)

스펙: `docs/specs/2026-07-30-shipment-construction-date-change-alert-design.md`
플랜: `docs/plans/2026-07-30-shipment-construction-date-change-alert-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T1 시공일 변경 이벤트 SSOT 통합 | DONE | 커밋 `be817cc3`(+인벤토리 `2a3faad2`) → deploy. 실 라우트 7경로 각 1건·부정 4종 0건, domains 3799 passed, PG 147 passed, smoke exit 0 |
| T2 출고 변경 수집 서비스 | DONE | `shipment_change_alerts.py` 신규(배치 1쿼리·쿼리수 단언), 17 passed |
| T3 ack API | DONE | `POST /api/orders/<id>/shipment/change-ack`, 매니페스트 2종 등재, 9 passed |
| T4 PC 대시보드 표시 | DONE | 배너+행 배지+확인, 캐시 밖 1쿼리(행 수 무관 단언), 172 passed |
| T5 태블릿 표시(그리드·시트) | DONE | 공유 매크로 1개로 PC·그리드·시트, 태블릿 계약 green, 번들 무변경 |
| T6 벨 알림 + 푸시 타입 등록 | DONE(미커밋) | `shipment_change.py` 신규, `_DEFAULT_P1_TYPES` 등재, 신규 11 passed / 인접 4파일 59 passed / domains 전수 3866 passed / contracts 65 / performance 78 / APP_OK |
| T7 성능 측정(TTFB·EXPLAIN) | DONE | 스테이징 dTTFB **74ms**/예산 291 PASS · 실데이터 EXPLAIN Seq Scan 없음(1.3ms) → 인덱스 불필요 |
| T8 최종 검증·커밋·푸시 | DONE | domains 3870 passed(실패 3=로컬 인벤토리 드리프트, 원격 tip은 CI green) · PG 147 passed · smoke exit 0 · deploy `5286012c` CI ALL GREEN |

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

### T7 측정 기록 (2026-07-30)

- perf-gate(스테이징, T6 포함 커밋 `4eed91a0`): `/erp/shipment?view=fragment`
  **dTTFB 74ms / 예산 291ms PASS**, wire 19,068B / 예산 34,405B, 304 OK.
- 실데이터 EXPLAIN(운영 읽기전용, `order_events` 11,177행 중
  `CONSTRUCTION_DATE_CHANGED` 2,651건): 이벤트 보유 주문 300건 표본에서
  `Bitmap Index Scan on ix_order_events_order_id` → **Seq Scan 없음**,
  662행 반환 Execution **1.307ms**.
- 따라서 복합 인덱스 `(order_id, event_type, created_at)` **추가하지 않는다**
  (측정 전 인덱스 금지·효과 없으면 무변경 종료 원칙). 마이그레이션 0.

## T9 스테이징 실브라우저 검증 (2026-08-05, deploy `73320a30`)

lahom-dev, claude_master(ADMIN) + 강민수(id 28, CONSTRUCTION) 전환. 5개 항목 중 4개 통과,
결함 2건 발견·수정.

| 항목 | 결과 |
|---|---|
| 배너 + 행 배지 | PASS (배지 잘림 결함 D1 동반 → 수정) |
| 배너 칩 → 행 점프·하이라이트 | PASS — `#shipment-row-<id>` 해시 이동 + `tr:target > td` inset 2px 빨강 |
| [확인] in-place 소멸 | PASS — ack POST 200, 배지·칩 전 표면 제거, 카운트 2→1→0, 배너 소멸, 리로드 0, 새로고침 후에도 유지 |
| 태블릿(coarse landscape 1376) | PASS — PC표 `display:none`·클린 그리드 `table`·칩 코호트 교대(pc none/tablet flex)·그리드 배지 무잘림·배정 시트 fragment 에 배지+[확인] |
| 종모양 벨 + 푸시 | **FAIL → D2 수정 후 PASS** |

- 폐루프: 주문 4295 시공일 8/5→8/6 실변경 → 8/6 대시보드에 배너 4건·해당 행 배지
  (`8/5 → 8/5, 8/6` — 품목별 일정이 남아 합집합이 되는 것이 정상) → 되돌리기까지 확인.
- 콘솔 에러 0(출고 대시보드), ack 네트워크 200/159ms.

### D1 — PC 행 배지가 고객 셀 밖으로 잘림 (수정 완료)

고객 `td` 가 `white-space: nowrap; overflow: hidden` 인데 배지가 `inline-flex` 라 전화번호
`<small>` 과 같은 줄에서 시작해 셀 오른쪽 밖으로 78px 밀렸다(1600px 실측: 폭 113px 중
35px 만 노출). **`max-width:100%` 는 남은 줄 폭이 아니라 셀 폭 기준**이라 이 겹침을 막지
못한다. `#shipment-dashboard-table .erp-ship-change{display:flex}` 로 PC 표에서만 자기 줄을
준다(태블릿 그리드는 셀이 넓고 고객명 옆 inline 이 의도). `?v` 20260730d→20260805a.
회귀 테스트 `test_pc_table_badge_is_block_level_not_inline`.

### D2 — CONSTRUCTION 팀 벨·푸시가 통째로 무음 (수정 완료)

`foms/platform/http.py` `_erp_construction_team_restrict` 가 시공팀의 `/erp/` **전체**를
출고 대시보드로 302 시키는데 `/erp/api/` 예외가 없었다. T6 가 `target_team=CONSTRUCTION`
으로 보낸 알림을 정작 대상 팀이 못 읽는다:

```
GET /erp/api/notifications → 302 → /erp/shipment?date=...   (배지 "0" hidden 고정)
console: [foms-push] mobile-state error SyntaxError: Unexpected token '<'
```

같은 prefix 라 웹 푸시 **구독**(`push/subscribe`·`vapid-public-key`)까지 막혀 푸시도
못 나갔다. 이 가드는 페이지 이동 제한이지 인가 경계가 아니고, `/api`·`/erp/api` 는 권한
실패도 302 가 아니라 403 JSON 이어야 한다는 불변식(P1-13/P1-18)이 이미 있으므로 API
네임스페이스를 예외로 뺐다. 엔드포인트별 권한 가드는 그대로, **페이지** 제한도 유지
(계약 테스트 2종으로 고정).

수정 후 재검증: 강민수 계정에서 `/erp/api/notifications` **200 JSON · unread 2건**
(`[출고] 시공일 변경 — 최복근`) 수신, `vapid-public-key` 200. 알림 row 는 원래부터
생성되고 있었고 **읽는 경로만 막혀 있었다.**

## 남은 확인

- production 승격 PR **#49** (base=production, cherry-pick 10커밋) — checks pass, 머지 대기.
- `docs/AI_STATUS.md` 진행 중 항목은 워킹트리에만 있다 — 같은 파일에 타 세션 미커밋 변경이
  섞여 있어 이 세션이 커밋하지 않았다.

## 미해결 / 대기

- 스펙 **승인 완료**(2026-07-30). 감지 통합안 = **A**(단일 이벤트 SSOT, 생산 칸반 노출도 함께 증가).
- 다음: T7(성능 측정) → T8(마감). T6 은 커밋 전 상태다.
- `target_team` = `CONSTRUCTION` 확정(위 T6 절 근거).
