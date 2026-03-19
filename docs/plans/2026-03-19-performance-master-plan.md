# FOMS 성능 향상 마스터 계획서

**작성일:** 2026-03-19  
**작성자:** GDM (Grand Develop Master) 총괄  
**기준:** 소스 코드 1:1 대조 + Railway 원격 환경 변수 실측 확인
**상태:** Phase 1 부분 완료 (2026-03-19 감리 반영)
**최종 감리:** 2026-03-19 GDM 4-agent 병렬 검증 완료
**선행 문서:**
- `docs/plans/performance-optimization-plan-v2.md` (Phase 0~4 원본)
- `docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md` (Phase A~V 원본)

---

## 1. 계획서 개요

### 1.1 배경

2026-03-19 기준 FOMS는 Railway 원격 환경에서 ERP 대시보드 초기 로딩 및 탭 전환 시 체감 지연이 발생한다.
최근 적용된 "상세 패널 서버 프리로드" 패치는 **상세 열기 속도**만 개선했고,
**초기 페이지 로드**와 **탭 전환 속도**에는 오히려 HTML payload 증가로 역효과가 있다.

### 1.2 목표

| 지표 | 현재 추정 | 목표 |
|------|-----------|------|
| 정적 파일 (CSS/JS/이미지) 재요청 | 매 요청마다 서버 왕복 (max-age=0) | 1년 캐시 (max-age=31536000) |
| ERP 프로세스 대시보드 초기 로드 | ~3-5초 (원격) | < 1.5초 |
| 실측 대시보드 초기 로드 | ~4-6초 (원격) | < 2초 |
| 생산/시공 대시보드 초기 로드 | ~3-5초 (원격) | < 1.5초 |
| 탭 전환 체감 | 1-3초 (네트워크 왕복) | < 1초 |
| 상세 패널 열기 | 즉시 (프리로드 완료) | 즉시 유지 |

### 1.3 핵심 원칙 (GDM Way)

1. **동작 보존 우선**: 화면 결과, 카드 수, 필터 의미, 노출 범위를 바꾸지 않는다.
2. **가짜 최적화 금지**: LIMIT으로 숨기는 방식, 무근거 축소 금지.
3. **구조 문제는 구조로 푼다**: 증상 우회(try/except: pass, 조건 회피) 절대 금지.
4. **측정 가능해야 한다**: 모든 Phase는 before/after 비교 가능.
5. **근본 원인 파악 → 근본 수정**: 증상만 덮는 수정 절대 금지.

### 1.4 Railway 원격 환경 실측 결과 (2026-03-19 확인)

```
RAILWAY_ENVIRONMENT = production
FLASK_ENV           = (미설정!!)
_is_production      = False  ← app.py:105
_is_railway         = True   ← app.py:127
```

**치명적 발견:**
- `WhiteNoise max_age=0` (정적 파일 캐시 0초 → 매 요청 서버 왕복)
- `WhiteNoise autorefresh=True` (파일 변경 감시 활성화 → 추가 I/O)
- `TEMPLATES_AUTO_RELOAD`는 `_is_railway` 덕에 올바르게 비활성화됨 (app.py:426)

---

## 2. 상세 실행 계획 (5개 Phase)

### Phase 구성 및 우선순위

| Phase | 명칭 | 위험도 | 체감 효과 | 예상 소요 |
|-------|------|--------|-----------|-----------|
| **Phase 0** | 환경 설정 즉시 수정 | 극저 | 극대 (정적 파일 캐시) | 30분 |
| **Phase 1** | 요청 공통 오버헤드 제거 | 낮음 | 중~대 (매 요청 절약) | 2시간 |
| **Phase 2** | 대시보드별 SQL/Python 최적화 | 중간 | 대 (초기 로드 단축) | 4시간 |
| **Phase 3** | 프론트엔드 payload/DOM 경량화 | 중간 | 대 (전송/렌더링 단축) | 3시간 |
| **Phase 4** | 인프라/DB 튜닝 | 낮음 | 중 (안정성 + 여유) | 2시간 |

**총 예상 소요:** ~11.5시간  
**실행 순서:** Phase 0 → 1 → 2 → 3 → 4 (순차, Phase 내 항목은 독립 가능)

---

## 3. 세부 실행 계획

---

### Phase 0. 환경 설정 즉시 수정 (체감 효과 극대, 위험도 극저)

> **단 한 줄의 환경변수 추가가 정적 파일 로딩 속도를 10배 이상 개선한다.**

#### 0-1. WhiteNoise Production 감지 수정 (치명적)

**근본 원인:**
```
app.py:105  _is_production = (os.environ.get('FLASK_ENV') == 'production')
```
Railway는 `RAILWAY_ENVIRONMENT=production`을 설정하지만 `FLASK_ENV`는 미설정.
따라서 `_is_production=False` → WhiteNoise `max_age=0`, `autorefresh=True`.

> **참고:** `app.py:127`의 `_is_railway`는 `RAILWAY_ENVIRONMENT` 존재 여부만 확인하므로 `True`이다.
> 이 변수는 `TEMPLATES_AUTO_RELOAD` 비활성화(app.py:426)에만 사용되며,
> WhiteNoise 설정에는 `_is_production`만 참조하므로 WhiteNoise 캐시 문제가 발생한다.

**수정 대상:** `app.py:105`

**수정 방향 (2가지 중 택 1):**

**(A) 코드 수정 (권장):**
```python
# Before
_is_production = (os.environ.get('FLASK_ENV') == 'production')

# After
_is_production = (
    os.environ.get('FLASK_ENV') == 'production'
    or os.environ.get('RAILWAY_ENVIRONMENT') == 'production'
)
```
이렇게 하면 `_is_production=True`가 되어:
- WhiteNoise `max_age=31536000` (1년 캐시)
- WhiteNoise `autorefresh=False` (파일 감시 비활성화)
- ProxyFix 활성화 (app.py:136)

**(B) 환경변수 추가:**
Railway 서비스 변수에 `FLASK_ENV=production` 추가.
→ 코드 변경 없이 동일 효과.

**기대 효과:**
- CSS/JS/이미지 첫 로드 후 브라우저 캐시 → 이후 요청 0ms
- 현재는 매 페이지 전환마다 Bootstrap(~200KB), Font Awesome(~100KB), erp-pro.css, flatpickr 등 모두 재요청
- CDN 리소스 제외, 자체 정적 파일만 ~500KB+ 절약/페이지

**검증:**
```bash
# 변경 전 (현재)
curl -sI https://lahom-production.up.railway.app/static/css/erp-pro.css | grep -i cache
# → Cache-Control: max-age=0  (또는 없음)

# 변경 후
# → Cache-Control: max-age=31536000, public
```

---

#### 0-2. DB 커넥션 풀 사이즈 조정

**근본 원인:**
```
db.py:62  pool_size=20, max_overflow=20  (총 40 커넥션 가능)
```
Railway 무료/소규모 플랜의 PostgreSQL은 동시 커넥션 제한이 있다.
Gunicorn gevent worker 2개 기준으로 `pool_size=5, max_overflow=5`가 적정.

> **계산:** gevent worker는 동시 greenlet 수만큼 커넥션을 점유할 수 있다.
> `worker_connections=1000`(기본값) × 2워커 = 이론상 2000개 greenlet이지만,
> 실제로는 `pool_size × workers = max 동시 커넥션`이므로:
> - 현재: `20 × 2 = 40` (+ max_overflow 40 = 최대 **80** 커넥션 가능)
> - 수정 후: `5 × 2 = 10` (+ max_overflow 10 = 최대 **20** 커넥션)
> Railway PostgreSQL 소규모 플랜 제한(~20~50)에 맞출 수 있다.

**수정 대상:** `db.py:61-65`

**수정:**
```python
# Before
engine_args.update({
    'pool_size': 20,
    'max_overflow': 20,
    'pool_recycle': 1800,
})

# After
engine_args.update({
    'pool_size': 5,
    'max_overflow': 5,
    'pool_recycle': 1800,
})
```

**기대 효과:**
- DB 커넥션 자원 절약 → 커넥션 대기(timeout) 위험 감소
- 메모리 절약 (커넥션당 ~5MB)

**검증:**
- `python -c "from db import engine; print(engine.pool.status())"`

---

### Phase 1. 요청 공통 오버헤드 제거

> **모든 페이지에 누적되는 공통 낭비를 제거한다.**

#### 1-1. User 중복 조회 제거

**근본 원인:**
`app.py:150-154`에서 `g.current_user`를 이미 설정하지만,
각 대시보드 라우트에서 `get_user_by_id(session.get('user_id'))`를 다시 호출한다.

**영향 범위:**

| 파일 | 라인 | 호출 수 | 상태 |
|------|------|---------|------|
| `apps/erp_dashboard.py` | 41 | 1 | 미완료 |
| `apps/erp_production_page.py` | 45, 191 | 2 | 미완료 |
| `apps/erp_construction_page.py` | 45, 165 | 2 | 미완료 |
| `apps/erp_measurement_dashboard.py` | 149 | 1 | 미완료 |
| `apps/erp_as_page.py` | 207 | 1 | 미완료 |
| `apps/erp_shipment_page.py` | (라우트 내) | 1 | **DONE** (2026-03-19) |
| `apps/api/notifications.py` | (5곳) | 5 | **DONE** (2026-03-19) |
| `apps/erp_drawing_workbench.py` | 30, 209 | 2 | 미완료 |
| `apps/api/erp_shipment_settings.py` | 31, 85 | 2 | 미완료 |

> **감리 메모 (2026-03-19):** `erp_shipment_page.py`와 `notifications.py`는 이번 세션에서 완료.
> `erp_production_page.py`와 `erp_construction_page.py`는 라우트당 2회 호출이므로 주의.
> `erp_drawing_workbench.py`와 `api/erp_shipment_settings.py`도 영향 범위에 포함.

**수정 방향:**
```python
# Before (각 라우트마다)
current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None

# After (각 라우트마다)
from flask import g
current_user = g.current_user
```

**기대 효과:** 요청당 User SELECT 1~2회 제거 (6개 대시보드 × 매 요청)

**검증:**
- grep으로 `get_user_by_id` 호출이 라우트 함수에서 제거되었는지 확인
- `g.current_user`가 `None`인 경우 login_required 데코레이터가 먼저 차단하므로 안전

---

#### 1-2. 공휴일 데이터 메모리 캐시

**근본 원인:**
`services/business_calendar.py:42-47`의 `get_holidays_kr()`와
`apps/erp_measurement_dashboard.py:25-33`의 `_load_holidays_for_year()`가
매 호출마다 JSON 파일을 디스크에서 읽는다.

**수정 대상:**
- `services/business_calendar.py` — 모듈 레벨 딕셔너리 캐시 추가
- `apps/erp_measurement_dashboard.py:25-33` — 자체 `_load_holidays_for_year` 제거, `business_calendar.get_holidays_kr` 사용
- `apps/erp_shipment_page.py:33-46` — **동일 함수 중복 구현** 발견 (감리 추가), 제거 필요
- `apps/api/erp_measurement.py:24` — `erp_measurement_dashboard`에서 import하여 사용 중 → 경로 변경 필요

**수정:**
```python
# services/business_calendar.py
_holidays_cache: dict[int, set[str]] = {}

def get_holidays_kr(year: int) -> Set[str]:
    if year in _holidays_cache:
        return _holidays_cache[year]
    loaded = _load_holidays_json(year)
    if loaded is not None:
        _holidays_cache[year] = loaded
        return loaded
    result = _generate_holidays_kr(year)
    _holidays_cache[year] = result
    return result
```

**기대 효과:** 연간 1회 파일 I/O → 이후 0ms (딕셔너리 룩업)

---

#### 1-3. 전역 디버그 console.log 제거

**근본 원인:** `templates/layout.html`에 39건 이상의 console.log/warn 호출이 프로덕션에서도 실행된다.

**수정 방향:**
```javascript
// Before
console.log('[FOMS] ...');

// After (FOMS_DEBUG가 false면 출력 안 함)
if (window.FOMS_DEBUG) console.log('[FOMS] ...');
```
또는 프로덕션 빌드에서 완전 제거.

**기대 효과:** 브라우저 콘솔 직렬화 비용 제거, 보안상 내부 정보 노출 차단

---

### Phase 2. 대시보드별 SQL/Python 최적화

> **각 대시보드 라우트의 과다 조회 + Python 후처리를 DB 수준에서 해결한다.**

#### 2-1. ERP 프로세스 대시보드 (erp_dashboard.py)

**현재 문제:**
```python
# apps/erp_dashboard.py:56
_q = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True))
# ... 필터 적용 후 ...
# :397 부근
orders = _q.order_by(Order.created_at.desc()).limit(1000).all()
```
- `limit(1000)` 후 Python에서 **stage 필터** + enrichment 수행
- `attach_order_detail_payloads(db, paginated_orders)` → 표시 주문 전체의 structured_data + attachments를 HTML에 주입

> **감리 정정 (2026-03-19):** mine 필터는 이미 SQL화 완료.
> `erp_dashboard.py:72-83`에서 `cast(Order.structured_data, String).ilike()` + `Order.manager_name.ilike()`로
> SQL WHERE 조건으로 적용 중. Python 후처리가 아님.
> 단, **stage 필터는 여전히 Python 인메모리** (line 85 주석: "파이프라인 단계별 모두 카운트를 위해 인메모리에서 수행").

**수정 방향:**
1. **stage 필터를 SQL WHERE로 이동** (현재 Python `if f_stage:` 조건 — 인메모리 카운트 목적이나 비효율)
2. ~~mine 필터를 SQL WHERE로 이동~~ → **이미 SQL화 완료 (정정)**
3. **SQL 수준 페이지네이션** → `OFFSET/LIMIT` 적용 후 `attach_order_detail_payloads` 호출
4. **전체 건수는 `COUNT(*)` 별도 쿼리** (가벼운 집계)
5. **stage별 카운트는 별도 `GROUP BY` 쿼리로** (인메모리 카운트 대체)

**수정 전/후 비교:**
```
Before: 1000행 로드 → Python stage 필터 + 카운트 → paginate → detail preload
After:  SQL stage 필터 + OFFSET/LIMIT → 20~50행 로드 + stage별 COUNT 쿼리 → detail preload
```

**기대 효과:** ORM 객체 생성 1000 → 20~50개, 메모리/CPU 95% 절감

---

#### 2-2. 생산 대시보드 (erp_production_page.py)

**현재 문제:**
```python
# apps/erp_production_page.py:52-57
_q = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True))
stage_col = cast(Order.structured_data['workflow']['stage'], String)
base_stages = ['"고객컨펌"', '"생산"', '"시공"', ...]
_q = _q.filter(stage_col.in_(base_stages))
# ... limit(1000).all() 후 Python enrichment
```
- `limit(1000)` 후 Python enrichment 수행
- `attach_order_detail_payloads` → 전체 주문의 payload HTML 주입

> **감리 정정 (2026-03-19):** stage 필터와 mine 필터 모두 이미 SQL화 완료.
> - stage: `stage_col.in_(base_stages)` (line 55-57) — SQL WHERE로 적용
> - mine: `cast(Order.structured_data, String).ilike()` (line 78-90) — SQL WHERE로 적용
> - 남은 문제는 `limit(1000)` + Python enrichment + `attach_order_detail_payloads`

**수정 방향:**
- **SQL 수준 페이지네이션** 도입 (OFFSET/LIMIT → 20~50행)
- ~~mine/stage 필터 SQL화~~ → **이미 완료 (정정)**
- `attach_order_detail_payloads` 범위를 페이지네이션 후 행에만 적용

**기대 효과:** ORM 객체 생성 1000 → 20~50개

---

#### 2-3. 시공 대시보드 (erp_construction_page.py)

**현재 문제:**
```python
# apps/erp_construction_page.py:53-58
orders = (
    db.query(Order)
    .filter(Order.active_filter(), Order.is_erp_beta.is_(True))
    .order_by(Order.created_at.desc())
    .limit(300).all()
)
if mine_only and user:
    orders = [o for o in orders if is_order_mine_for_user(o, user)]
```
- **페이지네이션 없음** → 300행 전체를 한 번에 로드
- `attach_order_detail_payloads` → 300행 전체의 payload HTML 주입 (수 MB)
- Python `mine` 필터 후 실제 표시 건수는 일부

**수정 방향:**
1. **서버 페이지네이션 도입** (per_page=50)
2. **mine 필터 SQL화** (시공팀 배정 조건을 JSONB 쿼리로)
3. **step_stats 집계를 SQL로** (현재 Python 루프 집계)

**기대 효과:** 300행 → 50행, HTML payload 6배 감소

---

#### 2-4. 실측 대시보드 (erp_measurement_dashboard.py)

**현재 문제:**
```python
# apps/erp_measurement_dashboard.py:153
all_rows = query.options(selectinload(Order.schedule_dates)).order_by(Order.id.desc()).limit(500).all()
```
- `limit(500)` 후 Python mine 필터
- `panel_orders` 별도 쿼리 (2주 범위)
- `build_product_items_for_orders(db, rows)` → N+1 개선된 배치 로드
- 템플릿에서 숨겨진 detail row에 이미지 URL 포함 (큰 DOM)

**수정 방향:**
1. 이미 `OrderScheduleDate` JOIN으로 개선된 상태 → 유지
2. **hidden detail row의 이미지를 lazy-load로 전환** (Phase 3에서 상세)
3. **mine 필터 SQL화**

**기대 효과:** 500행 유지하되 HTML DOM 크기 대폭 축소 (Phase 3 연계)

---

#### 2-5. `cast(structured_data, String).ilike()` 검색 개선

**현재 문제:**
대부분의 대시보드 검색에서 `cast(Order.structured_data, String).ilike(f'%{q}%')` 사용.
→ PostgreSQL이 전체 JSONB를 문자열로 변환 후 LIKE 탐색 (풀스캔)

> **감리 정정 (2026-03-19):** 시공 대시보드(`erp_construction_page.py`)는 이 패턴을 사용하지 않음.
> 시공 대시보드 검색은 별도 구현 또는 미구현 상태 → 영향 범위에서 제외.

**영향 범위:**

| 파일 | 라인 | 비고 |
|------|------|------|
| `apps/erp_dashboard.py` | 68 | 검색 + mine 필터 양쪽에서 사용 |
| `apps/erp_production_page.py` | 74, 85-88 | 검색 + mine 필터 양쪽에서 사용 |
| `apps/erp_measurement_dashboard.py` | 48-49 | 검색에서 사용 |
| `apps/erp_as_page.py` | 32 | 검색에서 사용 |
| ~~`apps/erp_construction_page.py`~~ | - | **미사용 (제외)** |

**수정 방향 (단계적):**
1. **즉시:** 검색어가 비어있을 때 JSONB cast 자체를 건너뛰도록 가드 (현재 구현됨)
2. **중기:** 자주 검색하는 필드(담당자명, 시공자명 등)를 JSONB 경로 추출 후 개별 ILIKE
3. **장기:** 검색 전용 컬럼 또는 tsvector 인덱스 도입

```python
# 중기 개선 예시 (structured_data 전체 cast 대신 경로별 검색)
from sqlalchemy import func
manager_name = func.jsonb_extract_path_text(Order.structured_data, 'parties', 'manager', 'name')
worker_name = func.jsonb_extract_path_text(Order.structured_data, 'parties', 'construction_workers')
or_(
    Order.customer_name.ilike(term),
    Order.manager_name.ilike(term),
    manager_name.ilike(term),
    worker_name.cast(String).ilike(term),
)
```

**기대 효과:** JSONB 전체 문자열화 제거 → 인덱스 활용 가능 경로 확보

---

### Phase 3. 프론트엔드 payload/DOM 경량화

> **서버가 보내는 HTML 크기와 브라우저가 처리하는 DOM 노드 수를 줄인다.**

#### 3-1. 상세 프리로드 payload 경량화

**현재 문제:**
```html
<!-- templates/partials/erp_dashboard_grid.html -->
<script type="application/json" id="order-detail-preload-{{ o.id }}">
  {{ o.detail_payload|tojson }}
</script>
```
- `detail_payload`에 `structured_data` 전체 + attachments 전체 메타데이터 포함
- 50행 × 평균 5KB/행 = ~250KB 추가 HTML (gzip 전)
- 시공 대시보드는 300행 = ~1.5MB 추가

**수정 방향:**
1. **페이지네이션 적용 후 프리로드 범위 축소** (Phase 2 연계)
2. **structured_data에서 상세에 필요한 필드만 추출**:
   - `schedule`, `items`, `parties`, `workflow.stage`, `checklist` 등 실제 사용 필드만
   - `workflow` 전체 히스토리, `timeline` 등 불필요 필드 제외
3. **attachments에서 thumbnail_key, download_url 등 상세 열기 전까지 불필요한 필드 제거**

**수정 예시 (services/erp_order_detail.py):**
```python
def _slim_structured_data(sd: dict) -> dict:
    """상세 패널에 실제 필요한 필드만 추출."""
    return {
        'schedule': sd.get('schedule', {}),
        'items': sd.get('items', []),
        'parties': sd.get('parties', {}),
        'workflow': {'stage': (sd.get('workflow') or {}).get('stage')},
        'checklist': sd.get('checklist', {}),
        'shipment': sd.get('shipment', {}),
    }
```

**기대 효과:** payload 50~70% 축소

---

#### 3-2. 실측 대시보드 hidden detail row 이미지 lazy-load

**현재 문제:**
```html
<!-- templates/erp_measurement_dashboard.html -->
<tr class="measurement-detail-row" id="detail-{{ r.id }}" style="display:none;">
  ...
  <img src="{{ photo.view_url }}" alt="{{ photo.filename }}">
  ...
</tr>
```
- `display:none`인 행에도 이미지 URL이 포함되어 브라우저가 사전 로드 시도
- 300행 × 평균 3장 = 900개 이미지 URL이 DOM에 존재

**수정 방향:**
```html
<!-- Before -->
<img src="{{ photo.view_url }}" alt="{{ photo.filename }}">

<!-- After -->
<img data-src="{{ photo.view_url }}" alt="{{ photo.filename }}" class="lazy-detail-img">
```
```javascript
// detail row 열릴 때 lazy-load
chevron.addEventListener('click', function() {
    // ... 기존 토글 로직 ...
    if (!isOpen) {
        detailRow.querySelectorAll('img.lazy-detail-img[data-src]').forEach(function(img) {
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
        });
    }
});
```

**기대 효과:** 초기 DOM에서 이미지 요소 제거 → 렌더링 속도 향상, 네트워크 요청 감소

---

#### 3-3. layout.html 전역 JS 로드 최적화

**현재 문제:**
`templates/layout.html`에서 모든 페이지에 로드하는 JS:
- jQuery (CDN, ~90KB gzip)
- html2canvas (CDN, ~60KB gzip)
- Socket.IO client (CDN, ~25KB gzip)
- flatpickr + locale (CDN, ~20KB gzip)

대부분의 페이지에서 jQuery/html2canvas/Socket.IO는 사용하지 않는다.

**수정 방향 (단계적):**
1. **즉시:** jQuery가 필요 없는 페이지에서 `{% block extra_js %}` 패턴으로 조건부 로드
2. **중기:** html2canvas를 사용하는 페이지(화면 캡처)에서만 로드
3. **장기:** Socket.IO는 채팅 페이지에서만 로드 (현재 `SOCKETIO_CLIENT_ENABLED` 플래그 활용)

**기대 효과:** 미사용 JS ~170KB gzip 절약/페이지 (첫 로드 + 캐시 미스 시)

---

#### 3-4. 알림 폴링 통합

**현재 문제:**
- `layout.html`: 전역 알림 뱃지 폴링 (`/api/notifications/status` 60초 간격)
- 각 대시보드 스크립트: 로컬 알림 뱃지 폴링 (별도 타이머)
- 두 시스템이 중복으로 동일 엔드포인트를 호출

**수정 방향:**
- 전역 알림 시스템 하나로 통합
- 로컬 대시보드 스크립트에서 중복 폴링 제거
- 전역 폴링 결과를 이벤트로 전파 (`CustomEvent` 또는 콜백)

**기대 효과:** 네트워크 요청 50% 감소, 서버 부하 절감

---

### Phase 4. 인프라/DB 튜닝

> **서버와 DB 수준의 설정을 원격 환경에 최적화한다.**

#### 4-1. pg_stat_statements 설치

**현재 문제:**
Railway PostgreSQL에 `pg_stat_statements` 확장이 미설치.
→ 실제 가장 느린 쿼리를 식별할 수 없음.

**수정:**
```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

**기대 효과:** 실측 기반 쿼리 최적화 가능 (현재는 코드 추정에 의존)

---

#### 4-2. Partial Index 추가 (OrderScheduleDate)

> **감리 정정 (2026-03-19):** `models.py:116`에 복합 인덱스
> `idx_order_schedule_dates_composite (kind, date, order_id)` **이미 존재**.
> 아래 Partial Index는 복합 인덱스가 커버하지 못하는 특정 kind별 조회를 최적화하는 추가 인덱스이다.
> `pg_stat_statements` 설치(Phase 4-1) 후 실제 쿼리 플랜 EXPLAIN 비교하여 필요성 판단 필요.

**현재 상태:** 복합 인덱스 `(kind, date, order_id)` 존재. kind별 Partial Index는 미존재.

**추가 대상 (필요성 검증 후):**
```sql
CREATE INDEX CONCURRENTLY ix_osd_measurement_date
ON order_schedule_dates (date, order_id)
WHERE kind = 'measurement';

CREATE INDEX CONCURRENTLY ix_osd_construction_date
ON order_schedule_dates (date, order_id)
WHERE kind = 'construction';

CREATE INDEX CONCURRENTLY ix_osd_as_visit_date
ON order_schedule_dates (date, order_id)
WHERE kind = 'as_visit';
```

**기대 효과:** 날짜 기반 대시보드 JOIN 속도 향상

---

#### 4-3. 불필요한 인덱스 정리

**현재 상태:** 이전 Phase C에서 추가한 인덱스와 기존 인덱스 중 중복 가능성 확인 필요.

**수정 방향:**
1. `pg_stat_user_indexes`에서 미사용 인덱스 식별
2. 중복 인덱스 제거
3. Alembic 마이그레이션으로 추적

---

#### 4-5. Notifications 테이블 인덱스 추가 (감리 추가)

> **발견일:** 2026-03-19 세션에서 발견. 기존 계획서에 미반영이었음.

**근본 원인:**
`notifications` 테이블의 `target_user_id`, `target_type` 컬럼에 인덱스가 없음.
뱃지 API (`/api/notifications/status`)가 매 60초 이 테이블을 풀스캔.

**수정:**
```sql
CREATE INDEX CONCURRENTLY ix_notifications_target_user_id ON notifications (target_user_id);
CREATE INDEX CONCURRENTLY ix_notifications_target_type ON notifications (target_type);
```

**Alembic 마이그레이션 필요:** Yes (Phase 4 실행 시 함께 진행)

**기대 효과:** 뱃지 API 응답 ~2초 → <100ms

---

#### 4-4. Gunicorn 워커 설정 검토

**현재:**
```
Procfile: gunicorn -k gevent -w 2 --timeout 120
```

**검토 사항:**
- Railway 컨테이너의 실제 CPU/메모리 제한 확인
- `--worker-connections` 미설정 (gevent 기본 1000)
- `--timeout 120` → 과도하게 길 수 있음 (60초로 단축 검토)

---

## 4. 전체 > 세부 스케일링

### 4.1 레이어별 병목 지도

```
┌─────────────────────────────────────────────────────────────────┐
│ 브라우저 (Client)                                                │
│ ├─ [P0-1] 정적 파일 캐시 없음 (max-age=0) ★★★ 치명적          │
│ ├─ [P3-2] 이미지 900개 사전 로드 (display:none)                 │
│ ├─ [P3-3] 미사용 JS 170KB 로드 (jQuery/html2canvas/SocketIO)   │
│ ├─ [P3-4] 알림 폴링 중복                                        │
│ └─ [P1-3] console.log 39건 직렬화                                │
├─────────────────────────────────────────────────────────────────┤
│ 네트워크 (Transfer)                                              │
│ ├─ [P3-1] 프리로드 payload 과대 (시공 300행 = ~1.5MB)           │
│ └─ [P0-1] 정적 파일 매번 재전송 (캐시 없음)                     │
├─────────────────────────────────────────────────────────────────┤
│ 앱 서버 (Flask/Gunicorn)                                         │
│ ├─ [P1-1] User SELECT 중복 (요청당 2~3회)                       │
│ ├─ [P1-2] 공휴일 JSON 파일 I/O (매 호출)                        │
│ ├─ [P2-1~4] 과다 조회 + Python 필터 (1000/300/500행)            │
│ └─ [P2-5] JSONB 전체 문자열화 검색                               │
├─────────────────────────────────────────────────────────────────┤
│ 데이터베이스 (PostgreSQL)                                        │
│ ├─ [P0-2] 커넥션 풀 과대 (80 가능, 실제 필요 20)  ← 감리 정정  │
│ ├─ [P4-1] pg_stat_statements 미설치                              │
│ ├─ [P4-2] Partial Index 검토 (복합 인덱스 존재) ← 감리 정정     │
│ └─ [P4-5] notifications 인덱스 누락 (NEW)  ← 감리 추가          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 대시보드별 병목 상세

#### ERP 프로세스 대시보드 (`/erp/dashboard`)

| 구간 | 병목 | Phase | 심각도 |
|------|------|-------|--------|
| SQL | `limit(1000)` 후 Python 필터 | P2-1 | 높음 |
| SQL | `cast(structured_data, String).ilike()` | P2-5 | 중간 |
| Python | `get_user_by_id()` 중복 | P1-1 | 낮음 |
| HTML | detail preload payload (~250KB) | P3-1 | 중간 |
| 브라우저 | 정적 파일 재요청 | P0-1 | 치명 |

#### 실측 대시보드 (`/erp/measurement`)

| 구간 | 병목 | Phase | 심각도 |
|------|------|-------|--------|
| SQL | `limit(500)` + 2쿼리 (all_rows + panel_orders) | P2-4 | 중간 |
| Python | holiday JSON 파일 I/O | P1-2 | 낮음 |
| HTML | hidden detail row + 이미지 URL 900건 | P3-2 | 높음 |
| 브라우저 | 정적 파일 재요청 | P0-1 | 치명 |

#### 생산 대시보드 (`/erp/production/dashboard`)

| 구간 | 병목 | Phase | 심각도 |
|------|------|-------|--------|
| SQL | `limit(1000)` 후 Python 필터 | P2-2 | 높음 |
| HTML | detail preload payload | P3-1 | 중간 |
| 브라우저 | 정적 파일 재요청 | P0-1 | 치명 |

#### 시공 대시보드 (`/erp/construction/dashboard`)

| 구간 | 병목 | Phase | 심각도 |
|------|------|-------|--------|
| SQL | `limit(300)` 페이지네이션 없음 | P2-3 | 높음 |
| Python | mine 필터 Python 루프 | P2-3 | 중간 |
| HTML | 300행 전체 preload (~1.5MB) | P3-1 | 높음 |
| 브라우저 | 정적 파일 재요청 | P0-1 | 치명 |

#### 출고 대시보드 (`/erp/shipment`)

| 구간 | 병목 | Phase | 심각도 | 상태 |
|------|------|-------|--------|------|
| ~~SQL~~ | ~~panel+rows 이중 쿼리~~ | ~~P1~~ | ~~높음~~ | **DONE** (쿼리 병합) |
| ~~Python~~ | ~~`get_user_by_id()` 중복~~ | ~~P1-1~~ | ~~낮음~~ | **DONE** (g.current_user) |
| 브라우저 | 정적 파일 재요청 | P0-1 | 치명 | 미시작 |

#### AS 대시보드 (`/erp/as`)

| 구간 | 병목 | Phase | 심각도 |
|------|------|-------|--------|
| SQL | `cast(structured_data, String).ilike()` 검색 | P2-5 | 중간 |
| 브라우저 | 정적 파일 재요청 | P0-1 | 치명 |

---

## 5. 원격 환경에서 확실히 빨라지는 항목 (증거 기반)

> 이하 항목은 **코드 분석 + 환경 변수 실측**으로 확실히 효과가 있음이 입증된다.

### 5.1 확정 효과 (증거 확보됨)

| # | 항목 | 근거 | 예상 절감 | 상태 |
|---|------|------|-----------|------|
| 1 | WhiteNoise max-age 수정 | Railway `FLASK_ENV` 미설정 실측 확인 → `max_age=0` | 탭 전환마다 500KB+ 정적 파일 재요청 제거 | 미시작 |
| 2 | User SELECT 중복 제거 | 9개 파일에서 직접 쿼리 확인 (감리 정정: 6→9개) | 요청당 1~2 DB 왕복 제거 | **부분 완료** (2/9) |
| 3 | 시공 대시보드 페이지네이션 | `limit(300)` + preload 전체 주입 코드 확인 | HTML 1.5MB → 200KB | 미시작 |
| 4 | 공휴일 캐시 | 파일 I/O 코드 3곳 확인 (감리 추가: shipment 포함) | 요청당 파일 읽기 제거 | 미시작 |
| 5 | DB 풀 사이즈 조정 | `pool_size=20` 코드 확인, Gunicorn 2워커 확인 | 커넥션 자원 절약 | 미시작 |
| 6 | 출고 쿼리 병합 (2→1) | panel+rows 이중 쿼리 확인 → 파생으로 통합 | DB 왕복 50% 제거 | **DONE** |
| 7 | Notifications 인덱스 추가 | `target_user_id` 인덱스 미존재 확인 | 뱃지 API 2s → <100ms | 미시작 |

### 5.2 높은 확률 효과 (코드 분석 기반)

| # | 항목 | 근거 | 예상 절감 |
|---|------|------|-----------|
| 6 | 프로세스/생산 SQL 페이지네이션 | `limit(1000)` + Python 필터 코드 확인 | ORM 객체 95% 감소 |
| 7 | 프리로드 payload 경량화 | `services/erp_order_detail.py` 전체 structured_data 주입 확인 | payload 50~70% 축소 |
| 8 | 실측 이미지 lazy-load | `display:none` 행에 img src 확인 | 초기 DOM 크기 감소 |

### 5.3 효과 검증 필요 (pg_stat_statements 설치 후)

| # | 항목 | 전제 |
|---|------|------|
| 9 | JSONB 검색 개선 | 실제 검색 빈도/비용 측정 후 우선순위 결정 |
| 10 | Partial Index 추가 | 실제 쿼리 플랜 EXPLAIN 비교 후 |

---

## 6. GDM 클린코드 및 성능향상 준수 사항

### 6.1 GDM 코딩 규칙 준수 체크리스트

| 규칙 | 적용 |
|------|------|
| 함수 50줄 이하, 한 가지 역할 | 신규/수정 함수 모두 적용 |
| docstring 필수 (목적, 파라미터, 반환값) | 신규/수정 함수 모두 적용 |
| 타입 힌트 필수 (신규 함수) | 적용 |
| API 응답 형식 통일 `{'success', 'data', 'error'}` | 기존 형식 유지 |
| JSONB 수정 시 `copy.deepcopy` + `flag_modified` | 적용 |
| 인라인 스타일 금지 | CSS 클래스 사용 |
| jQuery 사용 금지 | Vanilla JS 사용 |
| 인라인 script 300줄 초과 시 분리 | 확인 후 분리 |
| 템플릿 800줄 초과 시 partial 분리 | 확인 후 분리 |

### 6.2 GDM 성능 규칙 준수 체크리스트

| 규칙 | 적용 |
|------|------|
| N+1 쿼리 금지 (배치 로드 또는 JOIN) | 확인 |
| 불필요 DB 호출 제거 | User 중복 조회, 공휴일 I/O |
| SQL 수준 필터링 우선 (Python 후처리 최소화) | mine 필터, stage 필터 SQL화 |
| 인덱스는 살아남을 쿼리에만 추가 | Phase 4-2 |
| LIMIT으로 숨기는 방식 금지 | 페이지네이션으로 대체 |

### 6.3 변경 검증 프로토콜

모든 Phase 완료 후 다음 검증을 수행한다:

```
1. python -c "import app; print('APP_OK')"
2. 주요 페이지 smoke test (6개 대시보드 + 지도)
3. 결과 건수 비교 (수정 전/후 동일)
4. ReadLints 확인 (신규 lint 없음)
5. Railway deploy 브랜치 배포 후 원격 검증
6. 정적 파일 Cache-Control 헤더 확인
7. docs/AI_STATUS.md 갱신
```

### 6.4 롤백 계획

| Phase | 롤백 방법 |
|-------|-----------|
| Phase 0 | 환경변수 제거 또는 코드 revert (1줄) |
| Phase 1 | `g.current_user` → `get_user_by_id()` 복원 |
| Phase 2 | SQL 필터 제거, Python 필터 복원 |
| Phase 3 | payload 경량화 제거, 전체 structured_data 복원 |
| Phase 4 | 인덱스 DROP, 풀 사이즈 복원 |

---

## 7. 2026-03-19 세션 실행 결과

### 7.1 완료된 작업 (Phase 1 부분)

| # | 작업 | 파일 | 커밋 | 효과 |
|---|------|------|------|------|
| 1 | **출고 대시보드 쿼리 병합** (2→1) | `apps/erp_shipment_page.py` | `c10ea5d` | panel_orders에서 rows를 파생, DB 왕복 50% 제거 |
| 2 | **출고 대시보드 `g.current_user` 전환** | `apps/erp_shipment_page.py` | 동일 | User SELECT 1회 제거 |
| 3 | **시공팀 직접 리다이렉트** | `apps/auth.py:237-241` | 동일 | 이중 리다이렉트(referrer→restrict→shipment) 제거 |
| 4 | **notifications `g.current_user` 전환** (5곳) | `apps/api/notifications.py` | 동일 | User SELECT 5회 제거 |
| 5 | **login_required `g.current_user` 활용** | `apps/auth.py:100-121` | 동일 | 매 요청 중복 User SELECT 제거 |

### 7.2 발견된 추가 병목 (계획서 미반영이었던 항목)

#### 7.2.1 Notifications 인덱스 누락

`notifications` 테이블에 `target_user_id`와 `target_type` 컬럼 인덱스가 없음.
→ 뱃지 API (`/api/notifications/status`)가 매 60초 풀스캔 발생.

**영향:**
- 뱃지 API 응답 ~2초 (인덱스 추가 시 <100ms 예상)
- 전역 폴링(layout.html) + 대시보드별 중복 폴링 = 분당 2~4회 풀스캔

**수정 방향:** Alembic 마이그레이션으로 인덱스 추가
```sql
CREATE INDEX CONCURRENTLY ix_notifications_target_user_id ON notifications (target_user_id);
CREATE INDEX CONCURRENTLY ix_notifications_target_type ON notifications (target_type);
```

**Phase 배정:** Phase 4에 추가 (4-5번으로)

#### 7.2.2 출고 대시보드 `load_only` 오류 수정

초기 배포 시 `Order.order_number`를 `load_only`에 포함했으나 해당 컬럼이 모델에 존재하지 않아 500 에러 발생.
→ 즉시 제거 후 재배포 (`c10ea5d` 후속 커밋)

**교훈:** `load_only`에 컬럼 추가 시 반드시 `models.py` 대조 확인 필요.

---

## 8. 실행 타임라인 (권장)

| 일차 | 작업 | Phase | 상태 |
|------|------|-------|------|
| ~~Day 1 오후~~ | ~~출고 g.current_user + 쿼리 병합 + switch redirect + notifications~~ | ~~P1 부분~~ | **DONE** (2026-03-19) |
| Day 1 오전 | WhiteNoise 수정 + DB풀 조정 + deploy/production 배포 | P0 | 미시작 |
| Day 1 오후 | 나머지 User 중복 제거 (7파일) + 공휴일 캐시 + console.log 정리 | P1 잔여 | 미시작 |
| Day 2 오전 | 시공 대시보드 페이지네이션 + 프로세스 대시보드 stage SQL화 | P2-1, P2-3 | 미시작 |
| Day 2 오후 | 생산 대시보드 페이지네이션 + 프리로드 payload 경량화 | P2-2, P3-1 | 미시작 |
| Day 3 오전 | 실측 이미지 lazy-load + 알림 통합 | P3-2, P3-4 | 미시작 |
| Day 3 오후 | pg_stat_statements + notifications 인덱스 + Partial Index 검토 + 검증 | P4 | 미시작 |

---

## 9. 성공 기준

| 지표 | 측정 방법 | 목표 |
|------|-----------|------|
| 정적 파일 Cache-Control | `curl -sI .../static/css/erp-pro.css` | `max-age=31536000` |
| 탭 전환 정적 파일 전송 | 브라우저 Network 탭 | 0 bytes (304 or cache) |
| 시공 대시보드 HTML 크기 | `curl -s .../erp/construction/dashboard \| wc -c` | < 300KB (현재 ~1.5MB+) |
| 요청당 User SELECT | 코드 grep | 0회 (g.current_user만) |
| `python -c "import app"` | Shell | `APP_OK` |
| 대시보드 결과 건수 | 수정 전/후 비교 | 동일 |

---

## 10. 참조 소스 (전체 목록)

### 백엔드
- `app.py` — WhiteNoise, ProxyFix, g.current_user, TEMPLATES_AUTO_RELOAD
- `db.py` — 커넥션 풀 설정
- `Procfile`, `start.sh` — Gunicorn 설정
- `apps/erp_dashboard.py` — 프로세스 대시보드
- `apps/erp_production_page.py` — 생산 대시보드
- `apps/erp_construction_page.py` — 시공 대시보드
- `apps/erp_measurement_dashboard.py` — 실측 대시보드
- `apps/erp_as_page.py` — AS 대시보드
- `apps/erp_shipment_page.py` — 출고 대시보드
- `services/erp_order_detail.py` — 프리로드 payload 생성
- `services/business_calendar.py` — 공휴일 로드
- `services/context_processors.py` — 전역 컨텍스트
- `services/app_init.py` — 앱 초기화

### 프론트엔드
- `templates/layout.html` — 전역 레이아웃 (JS/CSS 로드, 알림)
- `templates/erp_measurement_dashboard.html` — 실측 hidden detail rows
- `templates/partials/erp_dashboard_grid.html` — 프리로드 script 태그
- `templates/partials/erp_production_filters_grid.html` — 프리로드 script 태그
- `templates/partials/erp_construction_filters_grid.html` — 프리로드 script 태그
- `templates/partials/erp_dashboard_scripts_detail_dom.html` — 상세 패널 JS
- `templates/partials/erp_production_scripts.html` — 생산 상세 JS
- `templates/partials/erp_construction_scripts.html` — 시공 상세 JS
- `static/js/erp/measurement.js` — 실측 상세 토글/정렬

### 설정/인프라
- Railway 환경변수 (`RAILWAY_ENVIRONMENT=production`, `FLASK_ENV` 미설정)
- `data/holidays_kr_*.json` — 공휴일 데이터

---

*이 문서는 GDM(Grand Develop Master) 감독 하에 작성되었으며,*
*모든 수정은 RPI 프로토콜(Research-Plan-Implement)에 따라 실행합니다.*
*사용자 승인 없이 코드 변경을 시작하지 않습니다.*

---
**감리 이력:**
- 2026-03-19: GDM 4-agent 병렬 감리 (explore-codebase × code-reviewer × database-specialist × python-backend)
  - 부정확 3건 정정 (Phase 2-1 mine필터, Phase 2-2 stage/mine필터, Phase 4-2 복합인덱스)
  - 누락 4건 추가 (Phase 1-2 shipment 공휴일, Phase 2-5 시공 제외, Phase 4-5 notifications 인덱스, 영향범위 확대)
  - Phase 1 부분 완료 기록 (출고 쿼리 병합, g.current_user 5건, switch redirect)
