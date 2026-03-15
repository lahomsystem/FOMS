# Phase B 실행 완료 보고서

**실행일**: 2026-03-15
**계획서**: docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md
**목표**: 성능 저하 개선 (과다 로드, 반복 쿼리, 중복 DOM 작업, 요청 직렬화 감소)

---

## 실행 요약

| 항목 | 상태 | 수정 내용 |
|------|------|-----------|
| **B-1** | ⏭️ 생략 | mine 의미 확정 전제 필요 (착수 전 전제) |
| **B-2** | ✅ 완료 | ERP 대시보드 User N+1 → 단일 IN 조회 + user_map |
| **B-3** | ✅ 완료 | 시공/AS 첨부 삭제 `for await` → `Promise.all` 병렬화 |
| **B-4** | ✅ 완료 | 출고 대시보드 `applyShipmentWorkerSortAndColors` 중복 호출 제거 |

---

## B-2: ERP 대시보드 루프 내 User N+1

### 수정 파일
- `apps/erp_dashboard.py`

### 변경 사항
1. 루프 전 pre-pass: 모든 주문에서 assignee `user_id` 수집 (MEASURE/CONFIRM: sales_assignee_user_ids, DRAWING: drawing_assignee_user_ids)
2. 단일 `db.query(User).filter(User.id.in_(all_assignee_ids)).all()` 조회
3. `user_map = {u.id: u.name for u in users if u.name}` 생성
4. 루프 내 `assignee_display_names = [user_map.get(uid, '') for uid in user_ids if user_map.get(uid)]` 사용

### 검증 포인트
- [ ] 주문 수가 늘어나도 User 조회 쿼리 수가 상수(1) 수준으로 유지

---

## B-3: 시공 화면 첨부 삭제 순차 요청

### 수정 파일
- `templates/partials/erp_construction_scripts.html`

### 변경 사항
1. **construction 재업로드** (794~798행):
   - `for (const att of ...) { await fetch(DELETE) }` → `await Promise.all(toDelete.map(att => fetch(DELETE)))`

2. **as 재업로드** (844~848행):
   - 동일 패턴 적용 (CURRENT_USER_ID 필터 유지)

### 검증 포인트
- [ ] 재업로드 시 기존 삭제가 빨라짐
- [ ] 일부 삭제 실패 시 사용자에게 실패 표시

---

## B-4: 출고 대시보드 정렬/색상 적용 중복

### 수정 파일
- `templates/erp_shipment_dashboard.html`

### 변경 사항
- fetch `.then` 내 1회만 `applyShipmentWorkerSortAndColors()` 호출 유지
- fetch `.catch` 내 `applyShipmentWorkerSortAndColors()` 제거
- `DOMContentLoaded` + `setTimeout(applyShipmentWorkerSortAndColors, 50)` 제거 (초기 로드 4경로 → 1경로)

### 검증 포인트
- [ ] 정렬/색상 표시 결과 유지
- [ ] 초기 렌더링 중 재배치 횟수 감소

---

## 자동 검증 결과

- `python -c "import app"` → **성공**
- `pytest -q` → **5 passed**

---

## 다음 단계

1. **수동 검증**: ERP 대시보드 로드, 시공 재업로드, 출고 대시보드 초기 로드
2. **Phase C**: soft-delete 기준 통일, 인덱스 추가 (Alembic CONCURRENTLY 전략 확정 후)
