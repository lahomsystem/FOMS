# 협력사 주문 지우기 — 라운즈가 올린 주문을 라운즈가 휴지통으로 SPEC (2026-11-04 사용자 결정 · 승인)

등급: 코어 변경(권한 · 주문 상태 · 협력사 쓰기 API) — 결정 4개를 묻고 받은 답을 승인으로 본다.
선행: `docs/specs/2026-10-08-partner-portal_SPEC.md`(협력사 문지기 · 허용 목록) · `docs/specs/2026-11-03-partner-statement_SPEC.md`(명세서).

## 0. 사용자 결정 (2026-11-04)

1. **지울 수 있는 때 = "이대로 만들어 주세요" 전까지.** 접수 · 실측 예정 · 도면 작업 중 · 도면 확인 대기(도면을 받은 뒤도). 생산 · 시공 · 완료는 막는다.
2. **이유 한 줄은 꼭 적는다.** 우리 알림 · 휴지통 · 감사 기록에 같이 남는다.
3. **알림 = 담당 팀 알림 + 발주방 채널 글.** 팀 알림은 협력사 품목 고치기와 같은 팀(도면 단계면 도면팀, 그 밖은 CS). 발주방에는 짧은 "주문 삭제" 글만 보낸다(주문 PUSH 본문 · 도면 첨부 없음).
4. **버튼 자리 = 주문 화면 "정보" 탭 맨 아래**(PC · 휴대폰 같은 템플릿). 아래 고정 버튼 줄은 그대로.

## 1. 지금 코드의 사실

- 주문 지우기의 정본은 `soft_delete_order`(`foms/services/orders/soft_delete.py:234`) — `deleted_at` · `structured_data.delete{deleted_by, deleted_at, reason}` · `ORDER_SOFT_DELETED` 이벤트 · 버전. 커밋 · 감사 · 캐시는 부르는 쪽. 엔진의 `policy_id` 는 영수증 열쇠라 협력사 행위자도 같은 함수를 쓴다.
- 협력사 쓰기는 허용 목록 `PARTNER_ALLOWED_ENDPOINTS`(`foms/services/auth/partner_scope.py`) + 매니페스트 2개(`PARTNER_PORTAL`)에 같이 넣어야 지난다. 소유 판정은 회사 단위(`partner_can_read_order`).
- 되살리기는 우리 휴지통(`/erp/orders/trash`, ADMIN · MANAGER)뿐. 영구 삭제는 365일 보관 정리만.
- 발행 명세서가 있는 주문은 이 기능으로 지울 수 없다(명세서는 주문 FK CASCADE — 영구 정리 때 명세서가 같이 사라진다).

## 2. 동작

- `POST /api/partner/orders/<id>/delete` `{reason}` — 자기 회사 주문만(아니면 404). 주문 줄을 `FOR UPDATE` 로 잠근 뒤:
  - 이유 빈칸 → 400 "지우는 이유를 한 줄 적어 주세요."
  - 단계가 RECEIVED · MEASURE · DRAWING · CONFIRM 이 아니거나 도면 확정(`blueprint.customer_confirmed`)이면 409 "제작을 시작한 주문은 지울 수 없습니다. 저희 담당자에게 연락해 주세요."
  - 취소 아닌 명세서가 있으면 409.
  - `soft_delete_order(reason="협력사 삭제: …")` → 감사 `PARTNER_ORDER_DELETED` → 팀 알림 `PARTNER_ORDER_DELETED` → 커밋 → 대시보드 캐시 전부 무효화(`invalidate_dashboard_caches_after_delete_transition`) · 팀 배지.
  - 커밋 뒤 발주방 글 한 번(`send_group_message`, 발주 그룹). 실패해도 지우기는 되돌리지 않고 기록만 남긴다.
- 화면: 정보 탭 맨 아래 "이 주문 지우기"(지울 수 있을 때만) → 누르면 이유 칸 · "지우기" · "그만두기"가 펼쳐진다. 지우면 주문 목록으로 간다(지운 주문은 목록에서 빠진다).

## 3. 검증

- 시험: 자기 회사 실측 예정 · 도면 확인 대기 200(대조군) · 다른 회사 404 · 생산 409 · 이유 빈칸 400 · 발행 명세서 409 · 지운 뒤 협력사 목록에서 빠짐 · 감사 · 팀 알림 · 발주방 글 한 번(보내기는 시험에서 가짜) · 문지기 래칫(`tests/security/test_partner_gate.py`) 초록.
- 스테이징 실화면: PC 1440 · 휴대폰 390. 발주방은 실제 직원 방이라 시험 글은 사용자 허락 뒤에만.

## 4. 바꾸지 않는 것

- 우리 직원 지우기 · 휴지통 · 되살리기 · 보관 정리.
- 협력사 고치기 창(`partner_edit_open`) · 수정 요청 · 승인 흐름.
