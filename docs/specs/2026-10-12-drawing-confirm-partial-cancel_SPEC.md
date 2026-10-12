# 도면 확정 때 일부 제품 취소 + 최종 생산 도면 고르기 — SPEC

- 상태: 승인 2026-10-12 (사유=고객 변심·기타(메모 필수), 생산 뒤 취소 포함, 금액은 표시만)
- 등급: 코어 변경(DB JSONB 형태·API·화면). Spec → 승인 → 구현.
- 목업: https://claude.ai/artifact/XUea6Sit1eBomGi4AoLta8 (PC 확정 창 · 모바일 확정 창 · 확정 뒤 도면 목록)

## 1. 문제

고객이 도면을 보고 "이건 빼 주세요"라고 하면 지금은 막을 길이 없다.

- 확정 창(`#dwCustomerOkModal`, `templates/drawing/partials/workbench_customer_send_modals.html:127-183`)은 확인 방법·메모·확정 뒤 동작만 받는다.
- `POST /api/orders/<id>/confirm-drawing-receipt`(`foms/api/drawing/erp_orders_draftsman.py:287-467`)는 `drawing_current_files` 전체를 최종본으로 만든다(`foms/services/drawing_confirm_cleanup.py:284-304`).
- 품목에 취소 상태가 없다. 지금 할 수 있는 건 주문 편집에서 품목을 지우는 것뿐이고, 사유·이력이 남지 않는다.
- 도면이 어느 품목 것인지 저장하지 않는다. `drawing_current_files[]` 항목은 `{key, filename, view_url, download_url, sheet_id?}` 뿐이다(`foms/services/orders/drawing_transfer.py:186-218`).

결과: 영업은 도면팀에 "남길 도면만 다시 보내 달라"고 부탁한 뒤 확정하고, 견적은 따로 고친다. 공장에 엉뚱한 도면이 갈 위험이 있다.

## 2. 목표 / 비목표

목표
1. 확정 창 안에서 품목별 [생산 / 취소]를 고르고, 취소에는 사유를 남긴다.
2. 확정 창 안에서 최종 생산 도면을 체크로 고른다. 취소 품목에 묶인 도면은 자동으로 빠진다.
3. 확정 뒤 도면팀·생산팀은 "최종 생산 도면"만 기본으로 보고, 빠진 도면은 사유와 함께 접힌 칸에 남는다.
4. 견적 수정이 필요하다는 사실을 놓치지 않게 표시한다(표시만, 알림 없음).
5. 확정 뒤(생산 넘긴 뒤)에도 품목 하나를 취소할 수 있다(10절).

비목표
- 견적·금액 자동 재계산 (표시만 한다).
- 주문 전체 취소 (생산 품목 0개면 확정 대신 기존 주문 취소 흐름으로 보낸다).
- 옛 데이터 일괄 정리.

## 3. 데이터 (structured_data JSONB, 마이그레이션 없음)

### 3.1 품목 취소 표시 — `structured_data.items[]`
품목을 배열에서 지우지 않고 필드를 붙인다. 품목 식별은 이미 있는 `items[].uid`(`foms/services/orders/structured_item_uid.py`)를 쓴다.

```json
{"uid": "…", "product_name": "보테가 슬라이딩장", "...": "...",
 "cancel": {"at": "2026-10-12T15:40:00+09:00", "by_user_id": 12,
            "reason": "customer_change", "note": null, "source": "drawing_confirm"}}
```
- `reason` 값: `customer_change`(고객 변심) · `other`(기타 — `note` 필수, 200자).
- `source`: `drawing_confirm`(확정 창) · `after_confirm`(확정 뒤 취소, 10절).
- `cancel` 이 있으면 취소 품목. 없으면 생산 품목. 되살리기는 `cancel` 제거(이력은 OrderEvent 에 남는다).

### 3.2 도면 ↔ 품목 연결 — `drawing_current_files[]`
전달 때 항목에 `item_uids: ["…"]` 를 선택적으로 단다. 한 도면이 여러 품목을 담을 수 있어 배열이다. 없으면 "공통/모름".
- 마법사 시트는 `drawing_wizard.sheets[].product_index` 를 이미 저장한다 → 읽을 때 `sheet_id` → `product_index` → `items[i].uid` 로 유도한다(`file_item_uids`, 5단계). 저장 데이터 변경·백필 없음, 이미 전달된 도면에도 적용. 범위 밖·공통 시트·uid 없음은 "모름"(자동 제외 안 함).
- 직접 올린 도면은 전달 창에서 품목을 고를 수 있게 하되 선택 사항(이번 단계는 비워 두면 됨).

### 3.3 확정 결과 — 확정 이력 항목(`CONFIRM_RECEIPT`)
```json
{"final_drawing_keys": ["…/1.png"], "excluded_drawings": [{"key": "…/2.png", "reason": "item_cancelled", "item_uid": "…"}],
 "cancelled_item_uids": ["…"], "estimate_needs_update": true}
```
그리고 `drawing_current_files` 는 최종 도면만 남기고, 빠진 도면은 `drawing_excluded_files`(새 키)로 옮긴다. 파일·첨부는 지우지 않는다(2026-09-29 결정 유지).
`estimate_needs_update` 는 `structured_data.flags.estimate_needs_update` 에도 올려 주문 화면에 배지를 띄운다.

JSONB 수정은 규약대로 deepcopy → 수정 → 재대입 → `flag_modified` → commit.

## 4. API

`POST /api/orders/<id>/confirm-drawing-receipt` 에 선택 입력 2개 추가. 안 보내면 지금과 똑같이 동작(호환).
```json
{"customer_ok": true, "customer_ok_via": "phone", "customer_ok_note": "…",
 "final_drawing_keys": ["…"],
 "cancel_items": [{"uid": "…", "reason": "other", "note": "색상 다시 고민"}]}
```
서버 검증(실패 시 아무것도 안 바꾼다, 400 + `error`):
- `final_drawing_keys` 는 현재 `drawing_current_files` 의 key 부분집합, 1개 이상.
- `cancel_items[].uid` 는 이 주문의 품목 uid, `reason` 은 2개 값 중 하나, `other` 면 `note` 필수.
- 생산 품목이 0개가 되면 거부 ("주문 취소로 처리해 주세요").
- 취소 품목에만 묶인 도면이 `final_drawing_keys` 에 있으면 거부.
- 같은 트랜잭션에서 품목 cancel·도면 정리·확정 이력·OrderEvent(`ITEM_CANCELLED_AT_CONFIRM`)를 함께 쓴다.

확정 창 열 때 필요한 데이터(품목 목록·도면 목록·연결)는 기존 workbench 컨텍스트에 `data-*` 로 싣는다 (새 조회 API 없음).

## 5. 화면

- 확정 창(PC·모바일 같은 템플릿): 목업대로 ① 제품 ② 최종 생산 도면 ③ 확인 방법·메모. 요약 줄과 버튼 문구가 상태에 따라 바뀐다. 품목 1개·도면 1장이면 ①② 를 접어 지금 창과 거의 같게 보인다.
- 새 JS 는 `static/js/foms/drawing-customer-ok.js` 옆 새 모듈로 (300줄 래칫). 인라인 스타일 금지 → CSS 파일.
- 확정 뒤 도면 목록(모바일 handoff·PC 사이드바·생산 화면): 최종 도면만 기본, "제외된 도면 N장 보기" 접힘.
- 주문 화면: 취소 품목은 줄 긋고 "취소 · 사유" 배지, `estimate_needs_update` 배지.

## 6. 함께 확인해야 할 곳 (취소 품목을 생산 대상에서 빼야 함)

구현 전 전수 조사 필요. 후보: 생산/시공 카드(construction card), 발주·자재 집계, 일정(품목별 schedule), 네이버 연동 매핑, 정산 매출 집계, 알림톡 품목 문구. 각 곳이 `items[]` 를 그대로 세면 취소 품목이 섞인다 → 공용 헬퍼 `active_items(sd)` 를 두고 바꾼다.

### 6.1 4단계 적용 결과 (2026-10-12)
- 취소 품목 제외 적용: 생산 대표 품목·라벨·자수·KPI·작업 시트, 출고 품목·자수·시공일, 포장 체크리스트(키는 원래 인덱스 유지), 실측·시공 일정 동기화, 알림톡·채널 실측 안내 품목, 목록 제품 요약(erp_display), 도면·CS 카드 요약, 주문 복사(취소 표시 제거·제외 도면 미복사).
- 일부러 그대로 둔 곳: 결제금액·정산 매출(§9-3 "표시만"), 감사·검색·휴지통(전체 배열 그대로), 도면 마법사 제품 목록(`?item=` 인덱스가 밀린다 — 5단계에서 uid 기준으로 바꿀 때 함께), `build_product_items_for_order`(실측 사진이 인덱스로 붙음 — 3단계 화면 표시에서 플래그로), 인라인 수정 PATCH(취소 줄 수정 허용).
- 통째 덮어쓰기 경로: ERP·태블릿·모바일 폼은 모두 PUT /structured → `preserve_item_cancel_state` 로 보호. 드래프트 자동저장은 드래프트 전용.

## 7. 테스트

- API: 입력 없음(호환) · 정상 부분 취소 · 생산 0개 거부 · 남의 key/uid 거부 · 취소 품목 도면 포함 거부 · 실패 시 무변경.
- 서비스: 도면 정리 후 `drawing_current_files`/`drawing_excluded_files` · 파일 미삭제.
- 화면 계약: 확정 창 마크업, 버튼 비활성 조건.
- PG 레인 + 스테이징 실화면 QA(가상 주문 `CLAUDE-TEST-`).

## 8. 단계

1. 데이터 헬퍼(`active_items`, cancel 기록, 도면 정리) + API 확장 + 테스트.
2. 확정 창 UI (PC·모바일).
3. 확정 뒤 목록·주문 화면 배지.
4. 6절 소비처 전환(조사 결과에 따라 쪼갬).
5. 마법사 시트 `item_uids` 자동 연결.
6. 확정 뒤 품목 취소(10절).

## 9. 결정 (2026-10-12 사용자)

1. 취소 사유: 고객 변심 · 기타(메모 필수) 두 가지.
2. 생산 넘긴 뒤 품목 취소도 이번 범위 (10절).
3. 견적은 화면 표시만.
4. 직접 올린 도면의 품목 연결은 선택 (미정 → 기본안 유지).

## 10. 확정 뒤 품목 취소

- `POST /api/orders/<id>/items/<uid>/cancel` `{reason, note}` — 확정(`drawing_status=CONFIRMED`) 뒤에만. 생산 품목이 0개가 되면 거부.
- 그 품목에만 묶인 최종 도면은 `drawing_excluded_files` 로 옮긴다(사유 `item_cancelled_after_confirm`).
- OrderEvent `ITEM_CANCELLED_AFTER_CONFIRM` + 생산·시공 대시보드 캐시 비우기.
- 생산 단계 이후면 생산팀에게 보이는 배지("취소 품목 있음")를 단다. 이미 만든 것의 처리(폐기·재고)는 이번 범위 밖, 메모로만.
- 화면: 주문/도면 상세의 품목 줄 [더 보기 › 이 제품 취소] → 확인 창(사유·메모).

### 10.1 구현 (2026-10-12)
- 라우트 `foms/api/drawing/erp_orders_item_cancel.py` — 정책 `ERP_EDIT`(CS·SALES·관리자), REV-00 `execute_order_mutation`(If-Match·버전·멱등 키·OrderEvent 한 트랜잭션). 정책·쓰기 가드 매니페스트 등재.
- 화면: 도면 작업실 확정 결과 칸의 [확정 뒤 제품 취소] 접힘 → 제품별 [이 제품 취소] → 창(사유·메모). 남은 생산 품목이 1개면 버튼을 그리지 않는다.
- 생산 칸반 카드에 "취소 품목 N개 있음" 표시.

