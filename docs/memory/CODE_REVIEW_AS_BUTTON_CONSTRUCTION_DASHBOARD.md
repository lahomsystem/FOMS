# 코드 리뷰: 시공 대시보드 AS 버튼 (AS 접수 vs AS 재업로드)

**일자**: 2026-02-25  
**요청**: GDM 관점 코드 리뷰 — 시공완료 시 AS 미접수인데 'AS 재업로드' 버튼이 뜨는 문제  
**참조**: `.cursor/agents/grand-develop-master.md`

---

## 1) 무엇을 발견했는가 (What was found)

### 설계 의도
- **시공완료** 행: AS **접수 전** → 「AS 접수」 버튼  
- **시공완료** 행: AS **접수 후** → 「AS 재업로드」 버튼  

### 현재 구현
- **백엔드** (`apps/erp_construction_page.py`):  
  `enriched` 항목에 `as_received_date`, `as_received_done` 전달.  
  `as_received_done = bool((getattr(o, 'as_received_date', None) or '').strip())`  
  → DB `as_received_date`가 비어 있으면 `False`, 값이 있으면 `True`.
- **템플릿** (`templates/partials/erp_construction_filters_grid.html`):  
  `{% if o.as_received_done %}` → AS 재업로드 / `{% else %}` → AS 접수.
- **시공 완료 API** (`apps/api/erp_orders_construction.py`):  
  시공 완료 시 `workflow.stage` → COMPLETED, `status` → COMPLETED 만 변경.  
  **`as_received_date`는 설정하지 않음** (의도와 일치).

### 가능 원인
1. **DB에 이미 값 존재**: 해당 주문의 `orders.as_received_date`에 과거/다른 경로로 값이 들어가 있음.
2. **키 누락 시 Jinja 동작**: `o.as_received_done`이 없으면 Jinja2에서 undefined → falsy이므로 이론상 「AS 접수」가 나와야 하나, 다른 데이터 소스나 캐시와 혼동 가능.
3. **배포/캐시**: 이전 배포 버전 또는 브라우저 캐시로 예전 HTML이 보일 수 있음.

### 구조적 점검 (GDM §4)
- 데이터 경로: **서버(Order.as_received_date) → enriched → 템플릿** 한 경로만 사용. JS는 그리드 행을 그리지 않고, 시공 완료 후 `window.location.href = '/erp/construction/dashboard'`로 전체 리로드하므로 **서버 렌더만** 사용됨.

---

## 2) 무엇을 작업/수정했는가 (What was changed)

- **템플릿 방어 로직 추가**:  
  `{% if o.as_received_done %}` → `{% if o.as_received_done | default(false) %}`  
  → `as_received_done` 키가 없거나 falsy면 항상 「AS 접수」 표시.
- **코드 리뷰 문서**: 이 파일에 발견 사항·수정 내용·권장 사항 기록.

---

## 3) 왜 그런 결정을 내렸는가 (Why)

- **단순화 우선**: 조건을 한 곳(서버의 `as_received_done`)에서만 결정하고, 템플릿에서는 누락 시에도 안전하게 「AS 접수」로 폴백하도록 함.
- **의존성 제거**: 키 누락/캐시 등으로 인한 오표시 가능성을 줄이기 위해 `default(false)` 적용.
- **매뉴얼 준수**: GDM 문제 해결 프로토콜(구조적 의심, 단순화 우선)에 따라 데이터 경로를 확인하고, 한 곳에서만 진실 소스(Order.as_received_date)를 사용하도록 유지.

---

## 권장 사항 (사용자/운영)

1. **DB 확인**: 문제가 되는 주문 ID(예: 2205)에 대해  
   `SELECT id, as_received_date FROM orders WHERE id = 2205;`  
   로 `as_received_date`가 NULL 또는 빈 문자열인지 확인.
2. **배포 확인**: `as_received_done` 반영 커밋이 실제 배포 환경에 올라갔는지, 배포 후 캐시 무효화/강력 새로고침 후 재현 여부 확인.
3. **재현 시**: 같은 주문으로 시공 완료 직후 대시보드에서 버튼이 「AS 접수」로 나오는지 확인 후, 여전히 「AS 재업로드」면 DB 값과 배포 버전을 다시 점검.
