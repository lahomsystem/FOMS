# 주문 완전 삭제 때 사진·도면 파일도 지우기 — SPEC (2026-10-20)

## 목적
휴지통에서 보존 기간(기본 1년)이 지난 주문을 관리자 승인으로 완전 삭제하면(`tools/ops/apply_delete_retention.py` → `foms/services/orders/delete_retention.py`) DB 행만 지워지고 저장소(R2)의 사진·도면·첨부 파일은 그대로 남는다. 파일 정리 함수 `delete_storage_files_for_order`(`foms/services/order_storage_cleanup.py`)는 있지만 부르는 곳이 0이다. 지운 주문의 고객 사진·도면이 저장소에 영구히 남는다.

## 사용자 결정(2026-10-20)
- 완전 삭제 때 **기록(주문 이력·변경 값·공유 화면 사본·변경 사유)은 전부 남긴다** — AUDIT-LOG T9(`order_events` 를 주문과 떼어 독립 감사 원장으로 둔 결정)를 그대로 유지. SEC-47 은 수정하지 않는다.
- 사진·도면 파일은 지운다(이 문서).

## 지금 구조
- 주문 파일 위치: 대부분 `orders/<주문번호>/` 아래(첨부·도면·도면 마법사·도면 창구·협력사 업로드·업로드 티켓). 썸네일 등 다른 폴더의 파일은 표에 키가 있다.
- 키를 들고 있는 표: `order_attachments`(storage_key·thumbnail_key) · `upload_tickets.object_key` · `upload_drafts.object_keys` · `drawing_wizard_pending.object_key` · `orders.blueprint_image_url`(`/api/files/view/<키>`) · `structured_data.drawing_current_files[].key`.
- 완전 삭제는 승인 토큰 소비와 DB 삭제가 한 트랜잭션이고, 커밋은 도구가 한다.

## 변경
1. `foms/services/storage.py` — `delete_prefix(prefix)` 추가: R2/S3 는 목록(페이지 단위) → 1,000개씩 일괄 삭제, 로컬은 그 폴더 삭제. `orders/<숫자>/` 모양이 아니면 거부(빈 접두어로 전체 삭제 방지).
2. `foms/services/order_storage_cleanup.py`
   - `storage_targets_for_orders(db, order_ids)` — 위 표들에서 키를 모으고 주문마다 `orders/<id>/` 접두어를 만든다. DB 행이 남아 있을 때(삭제 전) 부른다.
   - `delete_storage_targets(targets)` — 키·접두어를 지우고 `(지운 수, 실패 수)` 를 돌려준다. 실패는 기록만 하고 멈추지 않는다.
3. `delete_retention.apply_delete_retention` — `apply` 일 때 삭제 전에 대상을 모아 결과(`storage_targets`)에 싣는다. 파일은 여기서 지우지 않는다.
4. `tools/ops/apply_delete_retention.py` — **DB 커밋이 성공한 뒤에만** 파일을 지운다(커밋 실패로 주문이 되살아났는데 파일만 사라지는 일 방지). 출력에 `storage_deleted`·`storage_failed` 수를 더한다. 기존 `order_events` 잔존 확인 문구는 그대로(정상).

## 건드리지 않는 것
- 기록 표(order_events·order_field_changes·order_share_snapshots·order_change_reasons) — 사용자 결정으로 남긴다.
- 휴지통 넣기(soft delete)·복원 — 파일을 지우지 않는다.
- 야간 잡에 완전 삭제 넣기 — 지금처럼 관리자 승인 도구로만.

## 테스트
새 파일 `tests/domains/test_purge_storage_files.py`:
- `storage_targets_for_orders` 가 다섯 표·도면 URL·구조화 도면 키와 접두어를 모두 모으고, 다른 주문 키는 넣지 않는다(음성 대조군).
- `delete_storage_targets` 가 가짜 저장소에 키·접두어 삭제를 부르고, 하나가 실패해도 나머지를 지운다.
- `delete_prefix` 가 `orders/<숫자>/` 모양이 아닌 값(빈 값·`orders/`·`orders/1`·`../`)을 거부한다.
- 도구: 커밋 실패면 파일 삭제를 부르지 않고, 커밋 성공이면 부른다.
