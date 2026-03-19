# FOMS 기술 부채 해소 마스터 플랜

**작성일**: 2026-03-19  
**작성 기준**: 3차 GDM 전체 감리 결과 + Problems 패널 에러 해결 이후 잔류 부채  
**상태**: 미래 Sprint 계획 (현재 Production 운영에는 영향 없음)

---

## 개요

이 문서는 FOMS 성능 개선 Phase 0~4 완료 이후 감리에서 발견된 **기술 부채** 항목들을
우선순위·영향도·예상 공수별로 정리한 실행 가능한 로드맵이다.

> 현재 배포 가능 상태. 아래 항목들은 운영 장애 없이 순차적으로 처리한다.

---

## 부채 분류 기준

| 등급 | 기준 | 예시 |
|------|------|------|
| **P0** | 운영 중 데이터 오염·보안 취약점 가능성 | SQL Injection, XSS |
| **P1** | 성능 저하·데이터 누락 위험 | 300건 한도 초과 시 누락 |
| **P2** | 유지보수성 저하·코드 품질 | 인라인 스타일, 중복 코드 |
| **P3** | 미래 호환성 | SQLAlchemy 2.0 스타일 전환 |

---

## Sprint 4 — 데이터 무결성 · 성능 핵심 (P1)

**목표**: 운영 데이터 누락 위험 제거 + DB 쿼리 효율 극대화  
**예상 공수**: 3~4일  

### TD-4-1: `erp_construction_page.py` DB 레벨 페이지네이션 전환

**문제**  
현재 `query.limit(300).all()`로 DB에서 300건을 로드한 뒤 Python 슬라이싱으로 페이지를 나눈다.  
시공 주문이 300건을 초과하는 순간 **데이터 누락 발생**.

**근본 원인**  
`f_stage` 필터(시공대기/시공중/시공완료)가 `structured_data['workflow']['history']`를 파싱해야 판별되므로 현재는 Python에서 처리 중.

**해결 방안**  
```sql
-- orders 테이블에 display_stage 컬럼 추가 (denormalize)
ALTER TABLE orders ADD COLUMN construction_display_stage VARCHAR(20);
-- workflow 변경 시 자동 갱신 트리거 또는 서비스 레이어 동기화
```

```python
# erp_construction_page.py
# f_stage 필터를 SQL WHERE로 전환
if f_stage != 'ALL':
    query = query.filter(Order.construction_display_stage == f_stage)
total_count = query.count()
orders = query.order_by(...).limit(per_page).offset((page-1)*per_page).all()
```

**영향 파일**  
- `models.py` (컬럼 추가)  
- `services/erp_workflow.py` (단계 변경 시 컬럼 동기화)  
- `apps/erp_construction_page.py` (SQL 필터 전환)  
- Alembic 마이그레이션 필수

---

### TD-4-2: `build_mine_sql_filter` JSONB 경로 인덱스 + GIN 쿼리 전환

**문제**  
`cast(structured_data, String).ilike(f'%"{name}"%')` 패턴은 어떤 인덱스도 활용하지 못하고  
전체 테이블 Seq Scan을 강제한다. 주문 수 증가 시 mine 필터 응답 시간이 O(N)으로 늘어난다.

**근본 원인**  
JSONB 컬럼을 TEXT로 CAST하면 PostgreSQL 플래너가 GIN 인덱스를 사용할 수 없다.

**해결 방안**  

단계 1: `structured_data`에 GIN 인덱스 추가 (Alembic)
```sql
CREATE INDEX CONCURRENTLY idx_orders_sd_gin ON orders USING gin (structured_data jsonb_ops);
```

단계 2: `build_mine_sql_filter` 쿼리 방식 전환
```python
# 현재 (Seq Scan 강제)
cast(Order.structured_data, String).ilike(f'%"{safe_name}"%', escape='\\')

# 개선 (GIN 인덱스 활용 가능 — JSONB containment)
Order.structured_data.contains({'parties': {'manager': {'name': u_name}}})
# 또는 JSONB path 추출
Order.structured_data['parties']['manager']['name'].astext.ilike(f'%{safe_name}%')
```

**영향 파일**  
- `services/erp_permissions.py`  
- Alembic 마이그레이션 (인덱스 추가)

**주의**: `structured_data` 스키마가 일관되지 않은 구형 주문 데이터가 있을 경우  
`containment` 방식은 False Negative 발생 가능. 전환 전 데이터 검증 필수.

---

### TD-4-3: `erp_measurement_dashboard.py` `apply_erp_display_fields_to_orders` 이중 호출 제거

**문제**  
148번 줄에서 `all_rows` 전체에 호출 후, 239번 줄에서 `rows`(all_rows의 부분집합)에 재호출.  
동일 ORM 인스턴스에 display field 연산이 2회 적용된다.

**해결 방안**  
```python
# 148줄 제거 (전체 all_rows에 대한 선행 호출 불필요)
# apply_erp_display_fields_to_orders(all_rows)  ← 삭제

# 239줄만 유지 (필터된 rows에만 적용)
apply_erp_display_fields_to_orders(rows)
```

**영향 파일**: `apps/erp_measurement_dashboard.py`

---

## Sprint 5 — CSS/템플릿 클린업 (P2)

**목표**: 인라인 스타일 전면 제거 → 유지보수성 · 테마 적용 가능성 확보  
**예상 공수**: 2~3일  

### TD-5-1: `erp_shipment_dashboard.html` 인라인 `<style>` 블록 → CSS 이전

**문제**  
`{% block content %}` 내에 약 600줄 분량의 인라인 `<style>` 블록 존재.  
FOMS 코딩 규칙("인라인 스타일 금지") 위반.

**해결 방안**  
```
static/css/erp-shipment.css 신규 생성
→ layout.html <head>에 조건부 포함 또는 block head_extra 블록 추가
```

**영향 파일**  
- `templates/erp_shipment_dashboard.html`  
- `static/css/erp-shipment.css` (신규)  
- `templates/layout.html` (block head_extra 추가)

---

### TD-5-2: `erp_measurement_dashboard.html` 인라인 `<style>` + `<th>` 스타일 → CSS 이전

**문제**  
- 약 345줄의 인라인 `<style>` 블록  
- `<th>` 태그 직접 인라인 스타일 (`.erp-grid-th` 클래스 미적용)  
- 담당자 셀 Jinja2 동적 인라인 스타일 (`style="background-color: {{ manager_bg_color }}"`)

**해결 방안 (담당자 색상)**  
```html
<!-- 현재 (서버사이드 인라인 스타일) -->
<td style="background-color: {{ manager_bg_color }}; color: {{ text_color }};">

<!-- 개선 (data-attribute + JS CSS custom property) -->
<td class="manager-cell" data-bg="{{ manager_bg_color }}" data-color="{{ text_color }}">
```
```js
// measurement.js에서 초기화 시 CSS 변수로 적용
document.querySelectorAll('.manager-cell[data-bg]').forEach(el => {
    el.style.setProperty('--manager-bg', el.dataset.bg);
});
```

**영향 파일**  
- `templates/erp_measurement_dashboard.html`  
- `static/css/erp-measurement.css` (신규)  
- `static/js/erp/measurement.js`

---

### TD-5-3: `erp_construction_filters_grid.html` 배지 인라인 스타일 → CSS 클래스

**문제**  
퀘스트/경보 배지에 `style="font-size: 1.1rem; padding: 0.5em 0.8em;"` 반복.

**해결 방안**  
```css
/* erp-pro.css 추가 */
.erp-badge-lg {
  font-size: 1.1rem;
  padding: 0.5em 0.8em;
}
```

**영향 파일**: `templates/partials/erp_construction_filters_grid.html`, `static/css/erp-pro.css`

---

### TD-5-4: `layout.html` `scripts_placeholder` 블록 정리

**문제**  
`{% block scripts_placeholder %}{% endblock %}`(body 중간)와  
`{% block scripts %}{% endblock %}`(body 최하단) 두 블록이 병존하여 혼동 가능.

**해결 방안**  
- `scripts_placeholder` 블록 제거 (또는 명확한 주석으로 사용 중단 표시)  
- 모든 자식 템플릿을 `{% block scripts %}` 단일 블록으로 통일

---

## Sprint 6 — SQLAlchemy 2.0 스타일 마이그레이션 (P3)

**목표**: 미래 SQLAlchemy 3.0 대비 점진적 코드 현대화  
**예상 공수**: 1주 이상 (전체 코드베이스 영향)  

### TD-6-1: `Session.query()` → `select()` 스타일 점진 전환

**문제**  
전체 코드베이스가 SQLAlchemy 1.x 스타일 `db.query(Model).filter(...)` 패턴 사용.  
SQLAlchemy 2.0은 이를 레거시(deprecated)로 분류, 3.0에서 제거 예정.

**전환 예시**  
```python
# 1.x 스타일 (현재)
orders = db.query(Order).filter(Order.active_filter()).all()

# 2.0 스타일 (권장)
from sqlalchemy import select
stmt = select(Order).where(Order.active_filter())
orders = db.execute(stmt).scalars().all()
```

**전환 전략**  
1. 신규 파일/함수는 2.0 스타일로 작성  
2. 기존 파일은 모듈 단위로 점진 전환 (PR 단위 분리)  
3. 전환 순서 권장: `services/` → `apps/api/` → `apps/` → `app.py`

**영향 범위**: 전체 Python 파일 (~30개)

---

### TD-6-2: `typing.List`, `typing.Dict` → Python 3.9+ 내장 타입 전환

**문제**  
일부 파일에서 `from typing import List, Dict, Optional` 사용.  
Python 3.9+에서는 `list[...]`, `dict[...]`, `... | None` 사용 권장.

**전환 예시**  
```python
# 현재
from typing import List, Any
def foo() -> List[Any]: ...

# Python 3.9+ 권장
def foo() -> list[Any]: ...
```

**영향 범위**: `services/erp_permissions.py` 등 typing import가 있는 파일들

---

## Sprint 7 — 관찰가능성 · 운영 품질 (P2)

### TD-7-1: `static/js/erp/measurement.js` 인라인 스타일 주입 제거

**문제**  
`cell.style.setProperty('background-color', color, 'important')` — JS에서 직접 인라인 스타일 주입.  
FOMS 규칙("인라인 스타일 금지") 위반.

**해결 방안**  
```css
/* erp-pro.css */
.manager-cell { background-color: var(--manager-bg-color, transparent) !important; }
```
```js
// 직접 style 대신 CSS variable 설정
cell.style.setProperty('--manager-bg-color', color);
```

**영향 파일**: `static/js/erp/measurement.js`, `static/css/erp-pro.css`

---

### TD-7-2: `window.ERPUtils` 가드 추가

**문제**  
`const { escapeHtml, setVisible } = window.ERPUtils` — ERPUtils가 undefined이면  
구조분해 시 TypeError 발생하여 페이지 기능 전체 중단.

**해결 방안**  
```js
// measurement.js, 다른 ERP 스크립트들
if (!window.ERPUtils) {
    console.error('[FOMS] ERPUtils not loaded. Check layout.html script order.');
    return;
}
const { escapeHtml, setVisible, setText } = window.ERPUtils;
```

**영향 파일**: `static/js/erp/measurement.js`, 기타 ERPUtils 의존 스크립트

---

### TD-7-3: `erp_shipment_dashboard.html` `<link>` in `{% block content %}` → `{% block head_extra %}`

**문제**  
`<link rel="stylesheet">` 태그가 `<body>` 내 `{% block content %}`에 위치.  
FOUC(Flash of Unstyled Content) 발생 가능.

**해결 방안**  
`layout.html`에 `{% block head_extra %}{% endblock %}` 추가 후 `<head>` 내에서 포함.

---

## 전체 로드맵 요약

```
현재 상태: ✅ 배포 가능 (CRITICAL 0건)
                    │
           ┌────────▼────────┐
           │   Sprint 4      │  데이터 무결성 + 쿼리 효율
           │   (3~4일)       │  TD-4-1, TD-4-2, TD-4-3
           └────────┬────────┘
                    │
           ┌────────▼────────┐
           │   Sprint 5      │  CSS/템플릿 클린업
           │   (2~3일)       │  TD-5-1 ~ TD-5-4
           └────────┬────────┘
                    │
           ┌────────▼────────┐
           │   Sprint 6      │  SQLAlchemy 2.0 마이그레이션
           │   (1주 이상)    │  TD-6-1, TD-6-2
           └────────┬────────┘
                    │
           ┌────────▼────────┐
           │   Sprint 7      │  관찰가능성 · 운영 품질
           │   (1~2일)       │  TD-7-1 ~ TD-7-3
           └─────────────────┘
```

---

## 즉시 행동 불필요 항목 (모니터링만)

| 항목 | 이유 |
|------|------|
| `cast(sd, String).ilike()` Seq Scan | 현재 주문 수 기준 성능 허용 범위 내 |
| `DISTINCT` vs `EXISTS` 서브쿼리 | 측정 가능한 성능 차이 없음 |
| Trigram 인덱스 실익 재검토 | 날짜 String 검색 패턴이 남아 있는 한 유지 |

---

*작성: GDM (Grand Develop Master) — 3차 전체 감리 기반*  
*다음 업데이트: Sprint 4 착수 전*
