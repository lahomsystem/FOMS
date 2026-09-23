# 실측 방문 체크("실측만 완료") — SPEC (승인됨)

> 2026-09-23 · 상태: **승인됨(2026-09-23 사용자 — §7 기본값 그대로: ERP_EDIT·해제 허용·PC 표 미표시)** · 짝 브리프: `docs/plans/2026-09-23-measurement-mobile-glance-brief.md`
> 등급: 코어 변경(API + structured_data 새 서버 소유 키) → Spec → 승인 → 구현.

## 1. 왜
모바일 실측 화면의 새 "오늘 체크리스트"에서, 영업(실측) 담당이 **그 집 실측을 마쳤다**고 체크한다.
이 체크는 카드의 **"실측 완료" 버튼과 다른 개념**이다.

| | 체크(이 스펙) | "실측 완료" 버튼(기존) |
|---|---|---|
| 뜻 | 현장 실측만 마침 | 모든 정보 입력 뒤 **도면 단계로 넘김** |
| 누르는 때 | 방문 직후, 차 안에서 | 사무 입력까지 끝낸 뒤 |
| 단계 전이 | **없음** | MEASURE → DRAWING (`quest.py` `_STAGE_ADVANCE`) |
| 저장 | 새 키 `structured_data.measurement_visits` | quest 승인 + (지방·자가실측만) `Order.measurement_completed` |

`Order.measurement_completed` 를 재사용하지 않는 이유: 이 값은 도면 넘김 전이가 같은 tx 에서 켜고(`foms/api/quest.py:218`),
지방·자가실측 4체크 집계(`dashboard_control_tower.py:75-81`)·네이버 일괄 발송 표시(`bulk_dispatch.py:452`)·
실측 전후 판정(`measure_progress.py:207`)이 읽는다. 뜻을 바꾸면 이 넷이 조용히 달라진다.

## 2. 저장 모델
`Order.structured_data` 최상위 새 키 — **서버 소유**(폼이 렌더·전송하지 않음):
```json
"measurement_visits": {
  "2026-09-23": {"at": "2026-09-23T14:05:11+09:00", "by_user_id": 12, "by_name": "최진호"}
}
```
- 키 = 실측 **날짜(ISO)**. 재실측(다른 날)도 날짜별로 따로 남는다. 목록은 `selected_date` 키가 있으면 체크.
- 체크 해제 = 그 날짜 키 삭제(잘못 누른 경우 복구). 이력은 OrderEvent 에 남는다.
- 상한: 날짜 키 최대 20개(오래된 것부터 제거) — 무한 증가 방지.
- 마이그레이션 없음(JSONB 키 추가). 인덱스 없음(목록은 이미 로드한 행에서 읽는다 — 새 쿼리 0).
- **폼 전체 저장 보존**: `foms/api/erp_orders_structured.py` `_OPERATIONAL_TOP_LEVEL_KEYS` 에 `'measurement_visits'` 등재(2026-09-10 `drawing_wizard` 소실 사고와 같은 축). 계약 테스트가 이 목록을 읽는다.

## 3. API
`POST /api/orders/<id>/measurement-visit` — `foms/api/orders/measurement_visit.py`(신규), 라우트 `foms/api/orders/__init__.py`(call-log 옆).
- Body: `{"date": "YYYY-MM-DD", "done": true|false}` — 그 외 키 무시. date 는 ISO 만, 없으면 400.
- 권한: 정책 `ERP_EDIT`(STAFF+CS/SALES 또는 ADMIN/MANAGER, VIEWER 거부) — `call_log.py` 와 같은 `evaluate_policy`.
- 쓰기: `execute_order_mutation`(REV-00 한 tx: row lock · mutation_version bump · idempotency receipt · OrderEvent parity). optional `If-Match`·`Idempotency-Key` 헤더 — `call_log.py:111-249` 를 본으로 삼는다.
- structured_data 수정 규약: `copy.deepcopy` → 수정 → 재대입 → `flag_modified(order,'structured_data')`.
- OrderEvent: `MEASUREMENT_VISIT_MARKED` / `MEASUREMENT_VISIT_UNMARKED`, payload `{date}`. 표시 문구 `order_event_display.py`: "실측 방문을 체크했습니다" / "실측 방문 체크를 해제했습니다".
- 같은 상태로 다시 보내면 no-op 성공(`changed:false`, 이벤트·버전 증가 없음).
  - 판정 순서(2026-09-23 통합 검증 결정): **If-Match 가 no-op 보다 먼저**다. If-Match 를 보냈고 버전이 어긋나면 이미 같은 상태여도 409. 잠금 경로(`execute_order_mutation`)도 If-Match → 업무 변경 순서라 두 경로가 같다.
  - 잠금 전 판정이 "바뀜"이었는데 잠금 아래 최신 값에서 이미 같은 상태면(경합) 쓰기·`flag_modified`·버전 bump·receipt 없이 되감고 `changed:false` 성공.
  - 같은 Idempotency-Key 재요청(replay) 응답의 `done` 은 지금 저장된 상태(`changed` 는 원 요청 기준 true).
- 응답: `{"success": true, "data": {"date", "done", "at", "by_name", "changed", "mutation_receipt"}, "error": null}`.
- **하지 않는 것**: 단계 전이, quest 변경, `measurement_completed` 변경, 알림 발송.

## 4. 화면 (브리프 계약에 추가)
- 체크 칸 = 줄 안의 **별도 버튼** `<button type="button" class="foms-meas-glance__check" data-meas-visit-toggle="{id}" data-meas-visit-date="{selected_date}" aria-pressed="true|false" aria-label="{고객명} 실측 체크">`. 줄의 나머지(이름·주소)를 누르면 카드로 이동(기존 계약). 버튼은 앵커 밖(중첩 인터랙티브 금지) — 줄 = `div.foms-meas-glance__row` 안에 `button.check` + `a.foms-meas-glance__go[href="#meas-card-{id}"][data-meas-glance-go]`.
- 누르면 즉시 체크 표시(낙관적) → POST → 실패 시 되돌리고 짧은 안내("체크를 저장하지 못했어요. 다시 눌러 주세요"). `fetch` try/catch + `data.success` 검증.
- 권한 없는 사용자(`can_edit_erp` 거짓)는 버튼 `disabled`, 체크 상태만 보임.
- 묶음 머리 수치 "실측 d/n" 과 진행 막대, 패널 머리 "N곳 · 실측 d · 남은 r" 은 **이 체크 기준**. 기존 요약줄(`foms-visit-summary`, `measurement_completed` 기준)은 그대로 둔다.
- 담당자 이름 = `tel:` 링크 + 전화 아이콘 버튼(`manager_phone` 있을 때만; 없으면 이름 텍스트만). `data-queue-card-call-link` 와 같은 번호 정규화(하이픈·공백 제거).
- 서버: `mobile_queue_rows` 행에 `measurement_visit_done`(selected_date 키 존재) 불리언을 채운다(`dashboard.py` 행 조립 루프, 새 쿼리 0).

## 5. PNG
이미지 저장(PC 와 같은 표)은 이 체크를 **싣지 않는다**(PC 표 무변경 원칙). 필요하면 후속.

## 6. 테스트(신규 `tests/domains/test_measurement_visit_api.py` 등)
- 권한: VIEWER 403, SALES 200.
- 체크 → 날짜 키 생성·by_name·OrderEvent 1건·version +1; 같은 요청 반복 no-op; 해제 → 키 삭제·UNMARKED 이벤트.
- 단계·quest·`measurement_completed` 불변.
- 폼 전체 저장 뒤 `measurement_visits` 보존(`_OPERATIONAL_TOP_LEVEL_KEYS` 등재 단언 + 실제 PUT 경로 1건).
- Idempotency-Key replay, If-Match 불일치 409.
- 날짜 형식 오류 400, 없는 주문 404.
- 모바일 목록 렌더: 체크된 주문 `aria-pressed="true"`, 권한 없음 `disabled`, 담당자 tel 링크.

## 7. 결정이 필요한 것
1. 체크를 누를 수 있는 사람: 스펙은 `ERP_EDIT`(영업·CS·관리자). **담당자 본인만**으로 좁힐지?
2. 체크 해제 허용(스펙: 허용, 이력은 남김).
3. PC 실측 표에도 체크 표시를 보일지(스펙: 이번엔 안 함).
