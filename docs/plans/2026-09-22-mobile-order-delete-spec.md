# 모바일 주문 삭제 — 구현 스펙 (2026-09-22, 승인 대기)

목업: `C:\tmp\mobile_order_delete_mockup.html` (사용자 검토 완료. 사유 칩 3종으로 확정).

## 1. 목표

모바일 주문 상세(`/erp/orders/<id>/mobile`)에서 ADMIN·CS·영업이 주문을 휴지통으로 보낼 수 있게 한다.
실수 방지 4겹: ① ⋯ 메뉴 안에만 노출 ② 대상 카드 확인 ③ 길게 눌러(1.5초) 삭제 ④ 5초 되돌리기 + PC 휴지통 복원.

## 2. 권한 (코어 변경 — AUTH-01 정책)

현재 삭제 경로 2개 모두 ADMIN/MANAGER 전용이다.

| 경로 | 현재 게이트 |
|---|---|
| `POST /delete/<id>` (`foms/web/orders/trash.py:175`) | `role_required(["ADMIN","MANAGER"])` |
| bulk `DELETED` (`foms/api/orders/status.py:377`) | `user_can("MANAGER_MUTATION")` |

**추가**: `POLICY_REGISTRY["ORDER_SOFT_DELETE"] = _p("ORDER_SOFT_DELETE", teams=("CS","SALES"), description="단건 soft delete(휴지통) — ADMIN/MANAGER 또는 STAFF+CS/SALES. VIEWER deny.")`
(`foms/services/orders/order_mutation_policy.py` POLICY_REGISTRY). 팀 정규화는 엔진이 하므로 `MEASURE`→`SALES` 도 포함된다. 이 집합은 `ERP_EDIT_ALLOWED_TEAMS` 와 같다.

- 새 모바일 API 는 이 정책에 등재한다(route manifest). 기존 PC bulk 삭제·PC `/delete/<id>` 는 **건드리지 않는다**(범위 밖).
- UI 노출 판정 = 같은 `user_can("ORDER_SOFT_DELETE", current_user)` 값을 서버가 렌더 시 내려준다(권한 게이트와 같은 답 원칙, 2026-09-13 신고 재발 방지).

## 3. 단계 가드 (서버가 강제, UI 는 같은 값 표시)

`build_mobile_delete_guard(order) -> {"level": "free"|"warn"|"blocked", "label": str}`

| 단계 | level | 동작 |
|---|---|---|
| 접수 · 해피콜 · 실측 · 도면 진행 | free | 사유 선택 → 길게 눌러 삭제 |
| 도면 확정 · 생산 · 출고 · 시공 진행 | warn | 경고 배너 + 사유 선택 전 버튼 잠금 |
| 시공 완료 · 정산 완료 · AS 진행 | blocked | 메뉴 항목 회색 "PC에서만 가능", API 는 409 `MOBILE_DELETE_BLOCKED` |

판정 기준은 `erp_stage`(canonical stage) 하나로. 단계 코드 매핑은 구현 시 `foms/services/erp_stage*` 의 stage 상수를 재사용한다.

## 4. API

`POST /erp/api/orders/<int:order_id>/mobile-delete` (Blueprint `foms/api/orders/`, 정책 `ORDER_SOFT_DELETE`)

요청 JSON:
```json
{"reason_code": "customer_request|input_correction|other", "reason_note": "직접 입력 텍스트", "mutation_version": 12}
```

처리(단일 트랜잭션, `trash.py:delete_order` 와 같은 순서):
1. `Order.active_filter()` 로 조회. 없으면 404.
2. 단계 가드 blocked → 409.
3. `reason_code == "other"` 이면 `reason_note` 필수(빈칸 400). warn 단계는 모든 코드에서 사유 필수. free 단계에서 사유 없으면 `unspecified` 로 진행(PC 와 동일 — "사유 때문에 삭제가 막히면 현장이 멈춘다").
4. `apply_production_change_alert(... "cancelled")` (기존과 동일).
5. `soft_delete_order(db, order_id, actor_user_id, reason=<label>, expected_version=mutation_version)` — 409 on version mismatch.
6. `record_action_reason(...)` — 기존 ORDER-REASON-00 사용. 칩 매핑: 고객 취소→`customer_request`, 잘못 입력→`input_correction`, 직접 입력→`other`+note. **새 사유 코드 추가 없음.**
7. commit → `_invalidate_dashboard_caches_after_delete("order_delete")` → `finalize_production_change_alert` → `log_access(action="ORDER_SOFT_DELETED", detail={change_set, reason_code, reason_note, surface: "mobile"})`.

응답: `{"success": true, "data": {"order_id", "mutation_version", "undo_until": <iso, +5s>, "return_to": <목록 URL>}}`.

`POST /erp/api/orders/<int:order_id>/mobile-restore` (같은 정책) — 되돌리기 전용. `restore_order(...)` + status 미러 정리 + 캐시 무효화 + `log_access(action="ORDER_RESTORED")`. 5초 제한은 UI 만; 서버는 시간 검사 없음(PC 휴지통 복원과 같은 권한이므로).

trash.py 의 legacy `status='DELETED'`/`original_status` 미러(dual-write, `status.py:_bulk_soft_delete_response` 주석)를 **같은 방식으로 미러**해 PC 휴지통 목록·복원이 보이게 한다.

## 5. UI

### 5.1 서버 → 템플릿 (`foms/web/orders/dashboard.py:erp_order_mobile_detail`)
```
mobile_delete = {"can": user_can("ORDER_SOFT_DELETE", current_user), "guard": build_mobile_delete_guard(order), "version": order.mutation_version}
```

### 5.2 템플릿 (`templates/orders/partials/order_detail_mobile_v2.html`)
- 상세 헤더 우측 ⋯ 버튼(`foms-detail-more`). 현재 셸에 more 메뉴가 없으므로 신설. 기존 항목(수정·공유 링크·라벨)은 이번 범위에서 **링크만** 연결하거나 없으면 삭제 항목 단독.
- `data-can-delete`·`data-guard-level`·`data-order-id`·`data-mutation-version`·`data-target-label`("김민수 · 붙박이장 2400") 를 `#foms-mobile-delete-root` 에 싣는다(Jinja→JS 는 `data-*`).
- 시트 2개(더보기·확인)와 토스트는 같은 partial 의 `<template>` 로.

### 5.3 JS (`static/js/foms/mobile-detail-delete.js`, 새 파일, defer)
- `pointerdown` → rAF 진행바 1.5초 → 완료 시 fetch. `pointerup/leave/cancel` → 취소.
- 사유 칩 3종. "직접 입력" 선택 시 input 표시, 빈칸이면 버튼 `disabled`. warn 단계는 사유 미선택 시 disabled.
- fetch: try/catch + `data.success` 검증. 409 `VERSION_CONFLICT` → "다른 곳에서 바뀐 주문이에요. 새로고침 후 다시" 토스트. 403 → 메뉴 숨김 상태와 불일치이므로 "권한이 없어요" + 콘솔 warn.
- 성공: `navigator.vibrate(30)`, `return_to` 로 이동 후 목록 위에 토스트 "휴지통으로 옮겼어요 · 되돌리기"(5초). 되돌리기 → mobile-restore fetch → 성공 시 토스트 "되돌렸어요".
  - 페이지 이동 후 토스트는 `sessionStorage` 에 `{order_id, version, until}` 1건 남겨 목록 페이지 로드 시 그린다(같은 JS 가 목록에도 로드됨 — `dashboard_mobile_tower/queue` 두 분기 모두).
- jQuery 금지, 인라인 스타일 금지.

### 5.4 CSS (`static/css/components/foms-mobile-delete.css`, 새 파일 + surfaces 번들 `<link>` 핀 갱신)
시트·칩·hold 버튼·토스트. 토큰은 `foms-tokens.css` 의 `--foms-*` 만 사용(danger 는 `--erp-danger*`).

## 6. 제외

- 모바일 다중 선택 삭제 없음.
- 영구 삭제 없음(DELETE-TRASH-01 유지).
- PC 삭제 경로 권한 변경 없음.

## 7. 테스트 (완료 기준)

- `tests/domains/test_mobile_order_delete.py`
  - 정책: ADMIN·MANAGER·STAFF+CS·STAFF+SALES·STAFF+MEASURE 200 / STAFF+DRAWING·PRODUCTION·VIEWER 403.
  - 단계 가드: free/warn/blocked 3단계, warn 에서 사유 없음 400, blocked 409.
  - `other` + 빈 note 400.
  - version 불일치 409, 성공 시 `deleted_at` set + `ORDER_SOFT_DELETED` 이벤트 + reason 기록 + status 미러.
  - restore 후 `deleted_at` None, PC 휴지통 목록에서 사라짐.
  - 템플릿: 권한 없는 사용자는 `data-can-delete="false"` 이고 메뉴 항목 마크업 없음.
- `tests/postgres/` 에 동일 흐름 1건(FK·JSONB 는 PG 에서만 검증).
- 정적: `node --check static/js/foms/mobile-detail-delete.js`, 인라인 스타일 ratchet, `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1` exit 0.
- 실기기: 스테이징 `claude_master` 로 iPhone Safari 길게 누르기(터치 취소·스크롤 중 오작동) 확인.

## 8. 변경 파일 (예상)

| 파일 | 변경 |
|---|---|
| `foms/services/orders/order_mutation_policy.py` | `ORDER_SOFT_DELETE` 정책 추가 |
| `foms/api/orders/mobile_delete.py` (신규) | delete/restore API + 단계 가드 |
| `foms/web/orders/dashboard.py` | `mobile_delete` 컨텍스트 |
| `templates/orders/partials/order_detail_mobile_v2.html` | ⋯ 버튼·시트 템플릿 |
| `templates/orders/mobile_order_detail.html`, 목록 템플릿 2분기 | 스크립트·CSS 핀 |
| `static/js/foms/mobile-detail-delete.js` (신규) | 상호작용 |
| `static/css/components/foms-mobile-delete.css` (신규) | 스타일 |
| `tests/domains/test_mobile_order_delete.py`, `tests/postgres/…` | 테스트 |
| `docs/AI_STATUS.md`, `docs/AI_CHANGELOG.md` | 기록 |

## 9. 결정 필요 (승인 시 답 주세요)

1. MANAGER 역할도 포함(정책 엔진 기본값이 MANAGER 통과) — 기본 **포함**.
2. blocked 단계 범위: 시공 완료·정산 완료·AS 진행 — 기본 **3종**.
3. 더보기 메뉴의 다른 항목(수정·공유·라벨) — 기본 **삭제 항목만** 넣고 나머지는 후속.
