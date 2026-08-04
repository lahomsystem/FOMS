# Progress Ledger — 출고 대시보드 시공일 변경 알림 (2026-07-30, `**C`)

스펙: `docs/specs/2026-07-30-shipment-construction-date-change-alert-design.md`
플랜: `docs/plans/2026-07-30-shipment-construction-date-change-alert-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T1 시공일 변경 이벤트 SSOT 통합 | PENDING | |
| T2 출고 변경 수집 서비스 | PENDING | |
| T3 ack API | PENDING | |
| T4 PC 대시보드 표시 | PENDING | |
| T5 태블릿 표시(그리드·시트) | PENDING | |
| T6 벨 알림 + 푸시 타입 등록 | PENDING | |
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

## 미해결 / 대기

- **스펙 승인 대기** — 승인 전 T1~T8 착수 금지.
- 승인 시 함께 정할 것: 감지 통합안 A(단일 이벤트 SSOT, 생산 칸반 노출도 함께 증가) vs
  대안 B(신규 타입 분리, 이벤트 중복). 스펙 권장은 **A**.
- `target_team` 실제 코드값은 T6 착수 시 확인(현재 이 팀 대상 알림이 0건이라 미검증).
