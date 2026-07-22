# 출고 모바일 큐 카드 IA (배차/현장 우선)

> 승인: 2026-07-22. 출고 표면만. 타 도메인 큐 카드 무변경.

## 문제

DRAWING stage 주문이 출고 큐에 오면 공용 v2 메타(실측일·도면 담당)와 출고 detail(시공일·도면)이 겹쳐 스캔이 느리고 중복·모순이 난다.

## 최종 표기 순서 (위→아래)

1. 헤더 — 출고 뱃지·알림·#·타임라인
2. **고객** — 고객이름 · 발주사(라홈/하우드=로고, 기타=텍스트) · 주소·연락처 · 제품
3. **시공** — 시공일 · 시공시간(빈값 숨김)
4. **배차** — 차량 · 회차 · 현장추가(빈값 숨김)
5. **담당3** — 영업 · 도면 · 시공 (항상 3칸, 빈값 `-`)
6. W/300 · AS(해당 시)
7. 첨부 썸네일
8. 패킹 · QR
9. 액션 · 도면창구

## 금지 (출고 표면)

- 메타 실측일 / 실측 담당 / 메타 도면 담당 / 메타 단독 `담당`
- `도면`·`시공자` 단독 행과 담당3 이중 표기

## 데이터

| 라벨 | 소스 |
|------|------|
| 발주사 | `orderer_name` — AS `render_as_orderer_line`과 동일 규칙 |
| 영업 | `manager_name` |
| 도면 | `shipment.drawing_managers` (수정 시트 동기) |
| 시공 | `shipment.construction_workers` (수정 시트 동기) |

## 구현 요지

- `render_queue_card_v2` 옵트인 플래그: `suppress_schedule_meta`, `suppress_role_meta`, `show_orderer`, `defer_product`, `defer_attachments`
- 출고 `shipment_mobile_queue.html`이 플래그+detail_slot 재배치
- JS sync는 담당 행을 숨기지 않고 `-` 유지
