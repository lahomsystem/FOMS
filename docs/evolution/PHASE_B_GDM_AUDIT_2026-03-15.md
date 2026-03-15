# Phase B GDM 감리 보고서

**감리일**: 2026-03-15  
**감리자**: code-reviewer (FOMS Code Reviewer Agent)  
**대상**: Phase B 성능 저하 개선 실행 결과  
**계획서**: docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md  
**실행 보고서**: docs/evolution/PHASE_B_EXECUTION_REPORT_2026-03-15.md  

---

## 1. 무엇을 발견했는가 (What was found)

### B-2: ERP 대시보드 User N+1 제거 — ✅ 통과

| 검증 항목 | 결과 | 근거 |
|-----------|------|------|
| pre-pass로 user_ids 수집 | ✅ | `apps/erp_dashboard.py:82-102` — 루프 전 `all_assignee_ids` set에 MEASURE/CONFIRM은 `sales_assignee_user_ids`, DRAWING은 `drawing_assignee_user_ids` 및 fallback 수집 |
| 단일 User 조회 | ✅ | `:104-106` — `db.query(User).filter(User.id.in_(all_assignee_ids)).all()` 1회만 실행 |
| user_map 사용 | ✅ | `:106` — `user_map = {u.id: (u.name or '') for u in users if u.name}` |
| 루프 내 map 참조 | ✅ | `:218-219` — `assignee_display_names = [user_map.get(uid, '') for uid in user_ids if user_map.get(uid)]` |

**클린코드**: 함수 50줄 초과 구간 없음, docstring/타입힌트는 기존 라우트 수준 유지.  
**보안**: ORM 사용, SQL injection 없음.  
**성능**: N+1 제거 완료 — 주문 수와 무관하게 User 쿼리 1회.

---

### B-3: 시공 첨부 삭제 Promise.all 병렬화 — ✅ 통과

| 검증 항목 | 결과 | 근거 |
|-----------|------|------|
| construction 재업로드 | ✅ | `templates/partials/erp_construction_scripts.html:547-556` — `await Promise.all(toDelete.map(...))` |
| as 재업로드 | ✅ | `:584-596` — 동일 패턴, `CURRENT_USER_ID` 필터 유지 |

**패턴 일치**:
```javascript
await Promise.all(toDelete.map(function (att) {
  return fetch('/api/orders/' + orderId + '/attachments/' + att.id, { method: 'DELETE' });
}));
```

**에러 처리**: `submitConstructionReupload` / `submitAsAccept` 상위 try/catch에서 실패 시 `statusEl`에 메시지 표시.  
**주의사항**: `Promise.all`은 일부 실패 시 첫 실패에서 reject. 전체 실패 여부를 사용자에게 보여주려면 `Promise.allSettled` + 결과 검사가 더 적합할 수 있으나, 계획서 요구사항(병렬화)은 충족.

---

### B-4: 출고 대시보드 중복 호출 제거 — ✅ 통과

| 검증 항목 | 결과 | 근거 |
|-----------|------|------|
| fetch .then 1회만 호출 | ✅ | `templates/erp_shipment_dashboard.html:913-922` — `.then` 내 `applyShipmentWorkerSortAndColors()` 1회 |
| .catch 내 호출 제거 | ✅ | `.catch` 블록에는 `fillDatalist`만 있고 `applyShipmentWorkerSortAndColors` 없음 |
| DOMContentLoaded/setTimeout 제거 | ✅ | 스크립트는 IIFE `(function(){...})()`로 즉시 실행, 별도 DOMContentLoaded/setTimeout 경유 없음 |

**blur 경로**: `scheduleApplyShipmentWorkerSortAndColors()` — `:924-930` blur 이벤트, `:1118` construction_workers 저장 시. 계획서대로 유지.

---

## 2. 무엇을 작업/수정했는가 (What was changed)

**본 감리는 읽기 전용(code-reviewer)으로 수행되었으며, 코드 수정은 하지 않았습니다.**  
수정 내용은 Phase B 실행 에이전트(python-backend 등)가 이미 반영한 상태입니다.

---

## 3. 왜 그런 결정을 내렸는가 (Why)

- **B-2**: 계획서의 “루프 전 pre-pass → 단일 IN 조회 → user_map → 루프 내 map 참조” 패턴과 일치. N+1 제거 목표 달성.
- **B-3**: construction/as 두 경로 모두 `for await` 대신 `Promise.all` 적용. 계획서 검증 포인트 충족.
- **B-4**: fetch 성공 시 1회만 호출, DOMContentLoaded/setTimeout/.catch 경유 중복 제거. 초기 렌더링 재배치 횟수 감소 목표 달성.

---

## Findings (리뷰 체크리스트 기준)

### [Severity: low] B-4 fetch 실패 시 정렬/색상 미적용 가능성

- **파일**: `templates/erp_shipment_dashboard.html:913-922`
- **근거**: `.catch`에서 `applyShipmentWorkerSortAndColors()`를 제거했으므로, fetch 실패 시 정렬/색상이 적용되지 않을 수 있음.
- **영향**: `/api/erp/shipment-settings` 실패 시 datalist는 채워지지만, 서버 렌더된 초기 행 순서/색상만 유지. `applyInitialWorkerCellColorsFromData()`로 서버 데이터 기반 색상은 이미 적용됨.
- **권장**: 계획서 의도대로라면 현 상태 유지. 필요 시 fetch 실패 시에도 `applyShipmentWorkerSortAndColors()` 호출을 검토할 수 있음.

---

## Open Questions

- B-3: `Promise.all` 대신 `Promise.allSettled` + 부분 실패 사용자 알림이 요구사항에 포함되는지 확인 필요.
- B-4: fetch 실패 시 정렬/색상 적용 여부를 명시적으로 요구하는지 확인 필요.

---

## Residual Risks

- **B-2**: CONSTRUCTION 단계 퀘스트는 메인 대시보드에서 미표시(`:119-120`). assignee 수집 범위와 일치하는지 런타임 검증 권장.
- **B-3**: 삭제 요청이 동시에 다수 발생할 때 서버 부하/rate limit 영향은 미검증.
- **B-4**: `applyInitialWorkerCellColorsFromData()`와 `applyShipmentWorkerSortAndColors()` 실행 순서가 서버 렌더 → fetch 성공 순으로 유지되는지, 타이밍 이슈 없음.

---

## Phase C 착수 권고

| 항목 | 권고 |
|------|------|
| **Phase C 착수** | ✅ **권고** — B-2, B-3, B-4 모두 계획서 검증 포인트 충족, 자동 검증(pytest) 통과 |
| **전제 조건** | Phase C는 Alembic `CREATE INDEX CONCURRENTLY` 적용 방식 확정 후 진행 (계획서 311-314행) |
| **수동 검증** | ERP 대시보드 로드, 시공 재업로드, 출고 대시보드 초기 로드 수동 확인 권장 |

---

## 요약

- **B-2**: User N+1 제거 정상 적용.
- **B-3**: construction/as 경로 모두 Promise.all 적용.
- **B-4**: fetch .then 1회 호출, DOMContentLoaded/setTimeout/.catch 중복 제거 완료.

**Phase B 실행 결과는 계획서 기준으로 통과하며, Phase C 착수를 권고합니다.**
