# 워크플로 단계 강제 변경(역행·건너뛰기) Spec
> 작성일: 2026-07-15 | 상태: 🟢 승인됨 (기본안 A~F · 축소 금지 · deploy+스테이징 실테스트)

## 0. 배경 · 원칙

**사고:** ERP 폼 저장의 stale `workflow.stage`가 DRAWING→MEASURE로 덮어써 도면 목록에서 사라짐.  
**조치(이미 deploy):** structured PUT + 클라 수집은 **전진만 허용**(역행 차단).

**갭:** 의도적 역행·단계 건너뛰기는 “폼 저장”이 아니라 **확인+권한+사유**가 있는 별도 경로여야 함.  
현재 `POST /api/update_order_status`는 ADMIN/MANAGER/STAFF가 **아무 STATUS로도** 바꿀 수 있고(역행·스킵 포함), 확인 모달·사유·감사 필드가 약함.

**모드: HOLD SCOPE** — 퀘스트/도메인 전진 API(생산시작·도면수령확정 등)는 유지.  
폼 PUT 가드는 **절대 풀지 않음**. 새 경로는 “특권 단계 변경”만 추가하고, 기존 status API의 **위험 이동을 잠근다**.

---

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
운영자(권한 있는 사용자)가 ERP에서:

1. **인접 전진**(예: DRAWING→CONFIRM) — 기존 경로 유지(퀘스트/도메인 API/status 인접 전진).
2. **역행**(예: DRAWING→MEASURE) · **건너뛰기**(예: MEASURE→CONFIRM, 중간 스킵) · **임의 점프** —  
   **「단계 강제 변경」모달**(대상 단계 + 사유 필수 + 확인 체크) → 전용 API만 성공.
3. 변경마다 `OrderEvent`에 **from/to/mode/reason/actor**가 남고, 도면·이관 이력 JSONB는 **지우지 않음**(단계 ≠ 데이터 리셋).

### 1.2 기능 요구사항

1. **전용 API**  
   `POST /api/orders/<id>/workflow/stage-override`  
   Body:
   ```json
   {
     "to_stage": "MEASURE",
     "reason": "실측 재방문 필요 — 도면 착수 전 치수 오류",
     "confirm": true
   }
   ```
   - `to_stage` ∈ 메인 파이프라인 코드(아래 SSOT). AS_* / DELETED는 **이번 범위 제외**(기존 AS·삭제 플로우 유지).
   - `reason` trim 후 **최소 8자**.
   - `confirm` !== true → 400.
   - 성공 시: `order.status` + `structured_data.workflow.stage` 동기화(기존 `_sync_erp_stage`/`_handle_stage_transition`과 동일 계열), flat sync, commit.
   - `OrderEvent.event_type = "STAGE_OVERRIDE"` payload:
     `{ "from", "to", "mode": "regress"|"skip"|"jump"|"same", "reason", "manual": true }`
     - `regress`: to_rank < from_rank  
     - `skip`: to_rank > from_rank + 1  
     - `jump`: 한쪽 rank 미지(레거시 라벨 등)이지만 코드 유효  
     - `same`: from==to → 400 (무의미 호출 거절)

2. **권한 (승인 대기 — 기본안)**  
   | 이동 종류 | 허용 역할 |
   |-----------|-----------|
   | 역행 / 건너뛰기 / jump | **ADMIN, MANAGER만** |
   | 인접 전진(+1) | 이 API 불필요 — 기존 status·퀘스트·도메인 API |

   STAFF는 override API **403**. (원하면 “사유+이중확인만 STAFF 허용”으로 완화 가능 — 승인 시 선택)

3. **기존 status API 강화 (핵심)**  
   `POST /api/update_order_status` · `POST /api/bulk_update_order_status`:
   - ERP 주문 + 메인 파이프라인 단계끼리 비교 시:
     - **역행 또는 비인접 전진(skip)** → **403** + 메시지:  
       `단계 역행/건너뛰기는 「단계 강제 변경」에서 사유·확인 후 진행하세요.`
     - **인접 전진(+1)** 또는 **동일** → 기존처럼 허용(동일은 no-op 가능).
   - AS_* ↔ 메인, DELETED, 비ERP 레거시 주문: 기존 동작 유지(이번 가드 적용 안 함 또는 rank 미지 시 기존 허용 — Spec 구현 시 단위테스트로 고정).
   - bulk: 한 건이라도 override 필요하면 그 건 스킵/실패 집계(전체 롤백 아님 — 기존 bulk 패턴 따름). 응답에 `blocked_override_required: [ids]` 포함.

4. **UI**  
   - ERP Order 탭(`#erp-workflow-stage`):  
     - 셀렉트에서 **역행/스킵 대상**을 고르면 저장(PUT)하지 않고 **강제 변경 모달** 오픈.  
     - 인접 전진만 셀렉트 변경 후 일반 저장 가능(또는 셀렉트는 표시용·변경은 버튼만 — 구현은 B안 권장).
   - **권장 B안:** stage 셀렉트를 읽기 위주로 두고, 「단계 강제 변경」버튼(ADMIN/MANAGER만 노출) → 모달(현재→목표 select + 사유 textarea + 확인 체크 + 실행).  
     STAFF는 버튼 숨김; 인접 전진은 퀘스트/도메인 CTA만.
   - 실측 대시보드 등 `.status-dropdown` → `update_order_status`:  
     역행/스킵 선택 시 confirm만으로는 부족 → 모달(사유) 후 override API, 또는 드롭다운에서 해당 옵션 비활성+툴팁.
   - 모바일/태블릿 ERP 동일 게이트(버튼+모달). 새 무거운 CDN/동기 script 금지(`defer`).

5. **데이터 보존 (절대)**  
   단계 override는 **status/stage만** 바꾼다.  
   `drawing_transfer_history`, 도면 파일, assignees, `drawing_status`, 시공/생산 JSON 등 **삭제·리셋 금지**.  
   (이미 structured PUT 보존과 동일한 원칙 — override 핸들러에서 structured wipe 금지.)

6. **알림**  
   Out of scope(1차): STAGE_OVERRIDE 전용 Web Push.  
   선택(승인 시): 도면 게이트 충족 시 기존 ERP_ORDER_CHANGED와 별도 `STAGE_OVERRIDE` 알림 — **기본은 로그/이벤트만**.

### 1.3 예외/제약

- **하지 않음:** structured PUT 역행 허용으로 되돌리기.
- **하지 않음:** 폼 저장으로 skip/역행.
- **하지 않음:** AS 접수/완료·DELETED를 override API에 흡수(기존 API 유지).
- COMPLETED → 임의 과거 단계: **허용하되** MANAGER+사유(운영 실수 복구용). 더 빡세게 ADMIN only 원하면 승인 시 명시.
- reason에 비밀번호·개인정보 장문 붙여넣기 금지 안내는 UI placeholder만(서버 PII 필터 없음).

---

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일 (예상)

| 파일 | 변경 |
|------|------|
| `foms/services/orders/stage_override.py` (신규) | rank SSOT 공유·mode 판정·권한·apply |
| `foms/api/orders/stage_override.py` (신규) 또는 `status.py` 확장 | route 핸들러 |
| `foms/api/orders/__init__.py` | 라우트 등록 |
| `foms/api/orders/status.py` | regress/skip 차단 |
| `foms/api/erp_orders_structured.py` | rank 헬퍼를 서비스로 import(중복 제거 권장) |
| `templates/orders/partials/erp_order_tab*.html` | 강제 변경 버튼/모달 마크업 |
| `static/js/orders/erp-stage-override.js` (신규, defer) | 모달·fetch |
| `static/js/orders/erp-order-shared.js` | stage 셀렉트 연동(최소) |
| 대시보드 status-dropdown 호출부 | override 분기 |
| `tests/domains/test_workflow_stage_override.py` (신규) | API·가드·권한 |

### 2.2 아키텍처

- Rank SSOT: structured 가드와 **동일 맵**을 `stage_override` 서비스(또는 `status_constants`)로 승격 → PUT 가드·override·status 가드가 한 소스.
- apply: `order.status = to`; ERP면 workflow.stage + `flag_modified` + `sync_erp_flat_columns` + OrderEvent.
- `_handle_stage_transition` 부수효과(퀘스트 등)는 **override 시 호출 여부 결정**:  
  **기본안 = 호출하지 않음**(강제 이동은 퀘스트 자동 전진과 분리). 필요 시 stage만 맞춤.

### 2.3 의존성 · 영향

- DB 마이그레이션 **불필요**(OrderEvent JSON payload).
- 기존 STAFF의 status 드롭다운 역행/스킵은 **막힘** → UX 안내 필수(의도).

---

## 3. Steps

- [x] Step 1: rank/mode SSOT + `stage_override` 서비스 + API + status API 가드
- [x] Step 2: ERP 탭 모달 UI(ADMIN/MANAGER) + defer JS
- [x] Step 3: 대시보드 status-dropdown 역행/스킵 → 모달 또는 차단 메시지
- [x] Step 4: pytest(권한·역행·스킵·reason·PUT 가드 회귀) + APP_OK
- [ ] Step 5: deploy 푸시(승인 후)

---

## 4. 검증 기준

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] structured PUT DRAWING→MEASURE 여전히 차단
- [ ] override API: MANAGER + reason + confirm → DRAWING→MEASURE 성공, STAGE_OVERRIDE 이벤트
- [ ] STAFF override → 403
- [ ] update_order_status로 역행 → 403
- [ ] update_order_status 인접 전진 → 200
- [ ] reason 짧음/confirm false → 400
- [ ] drawing_transfer_history 길이·내용 override 후 불변
- [ ] perf: 동기 CDN script 없음

---

## 5. 승인 시 확인할 선택지

| # | 항목 | 기본안 | 대안 |
|---|------|--------|------|
| A | override 역할 | ADMIN+MANAGER | ADMIN only |
| B | COMPLETED→과거 | MANAGER 허용 | ADMIN only |
| C | status API 잠금 | 역행·스킵 403 | 경고만(비권장) |
| D | UI | 전용 버튼+모달(B안) | 셀렉트 선택 시 모달 |
| E | STAGE_OVERRIDE 푸시 | 없음(1차) | 도면팀 알림 |
| F | 벌크 역행 | 건별 차단+목록 | 벌크 override 미지원 유지 |

---

## 6. 참고

- 선행: structured PUT `_guard_accidental_stage_regression` (`erp_orders_structured.py`)
- 기존 의도 경로: `POST /api/update_order_status` (`foms/api/orders/status.py`) — 이번 작업으로 **위험 이동 잠금**
- 관련 Spec: `docs/plans/2026-07-15-drawing-erp-order-change-alert_SPEC.md`
