# FOMS Production 성능 최적화 계획서

**작성:** Grand Develop Master — 4개 전문 에이전트 병렬 분석 기반
**분석일:** 2026-03-09
**더블체크:** 소스 코드 기준 교차 검증 완료 (2026-03-09)
**목표:** Production 환경 전반적 페이지 로딩 속도 개선, 주문 데이터 증가에 따른 선형 성능 저하 해결
**상태:** Phase 0~3 계획 수립 완료, 더블체크 반영 수정 완료, 실행 대기

---

## 1. 현상 정리

### 1.1 사용자 보고 증상
- Production 원격 환경에서 **전체적으로 페이지 로딩이 느림**
- 특히 **실측 대시보드**, **실측 대시보드 > 지도 진입** 시 극심
- 주문 데이터가 늘어날수록 전반적으로 점점 느려지는 추세

### 1.2 환경 정보
| 항목 | 값 |
|------|-----|
| 배포 환경 | Railway (Web x2, Worker x1) |
| 웹 서버 | Gunicorn gevent -w **2** --timeout **120** |
| DB | PostgreSQL 15+ (Railway 호스팅) |
| 캐시 | Redis (RQ Worker용, 페이지 캐시 없음) |

### 1.3 근본 원인 요약

4개 전문 에이전트(DB, 백엔드, 프론트엔드, 코드베이스 탐색)가 병렬 분석한 결과, 근본 원인은 **4가지 구조적 문제**로 수렴합니다:

| # | 근본 원인 | 영향 범위 |
|---|----------|----------|
| 1 | **DB 인덱스 부재 + 날짜 컬럼 타입 문제** — String 타입에 CSV 저장, ILIKE 패턴으로 검색 | 모든 쿼리 |
| 2 | **과도한 데이터 로딩** — LIMIT 없음/과다 + Python 레벨 필터링 | 모든 대시보드 |
| 3 | **매 요청 반복 비용** — User SELECT 최대 3회, 파일 IO, 템플릿 체크 | 모든 페이지 |
| 4 | **지도 동기 지오코딩** — 외부 API 최대 40건 블로킹 호출 | 지도 페이지 |

---

## 2. 전체 분석 결과

### 2.1 발견된 성능 이슈 총 18건

#### 심각도: Critical (4건)

| # | 이슈 | 파일:라인 | 상세 |
|---|------|----------|------|
| C-1 | **날짜 컬럼이 String + CSV 저장 + ILIKE 검색** | `models.py` (Order 모델) | `measurement_date`, `scheduled_date` 등이 `String` 타입으로 `"2026-03-09,2026-03-10"` CSV 형태 저장. 검색 시 `ILIKE '%2026-03-09%'` 사용 → **btree 인덱스로는 개선 불가** (중간 매칭). Boolean 컬럼(`is_erp_beta`, `is_regional` 등)도 저카디널리티(True/False 2값)라 단독 btree 인덱스 효과 제한적 |
| C-2 | **JSONB cast+ILIKE 풀스캔** | `erp_measurement_dashboard.py:141,156` / `erp_shipment_page.py:312,313` / `erp_as_page.py:32` | `cast(Order.structured_data, String).ilike('%날짜%')` 패턴이 JSONB 전체를 문자열로 변환 후 LIKE 검색. GIN 인덱스 활용 불가. 날짜 범위 31일 검색 시 OR 31개가 풀스캔 |
| C-3 | **지도 동기 지오코딩 40건** | `erp_map.py:512-569` | 좌표 없는 주문 최대 40건을 카카오 API로 동기 병렬 호출 (5스레드). 건당 0.5-2초 → 최악 16초 블로킹. Gunicorn 워커 2개 중 1개 점유 시 전체 서비스 50% 마비 |
| C-4 | **실측 동선 API Beta 과다 조회** | `erp_measurement.py:192-196` | 날짜 필터 시 `and_(Order.is_erp_beta == True, Order.structured_data.isnot(None))` 조건으로 **날짜 무관하게 모든 Beta 주문**을 끌어온 뒤, Python(228행)에서 날짜 재필터링. 데이터 증가 시 선형 악화 |

#### 심각도: High (5건)

| # | 이슈 | 파일:라인 | 상세 |
|---|------|----------|------|
| H-1 | **실측 대시보드 이중 쿼리** | `erp_measurement_dashboard.py:163,171` | 한 페이지 로드에 DB 쿼리 2번. **주의:** `query`(163행)는 날짜 필터 적용된 결과, `base_query`(171행)는 패널용 전체 기반. 날짜 필터 활성 시 두 쿼리의 대상 집합이 다름 → 단순 슬라이싱 통합 불가 |
| H-2 | **실측 대시보드 N+1 쿼리** | `erp_measurement_dashboard.py:250` | 300건 각각에 대해 `build_product_items_for_order(db, r)` 호출 = 최대 300회 추가 SELECT |
| H-3 | **출고 대시보드 다중 쿼리** | `erp_shipment_page.py:159,268,291,324` | `panel_orders`(159행)는 14일 패널 계산용, `all_candidates`(268,291,324행)는 날짜 범위/단일/전체에 따라 각각 다른 필터 조건 사용 → 단순 통합 불가, 개별 최적화 필요 |
| H-4 | **지방/자가실측 대시보드 LIMIT 없음** | `dashboards.py:54,288` | `base_query.order_by(Order.id.desc()).all()` — 제한 없이 전체 로드. 데이터 증가 시 선형으로 무한 느려짐 |
| H-5 | **매 요청 User SELECT 최대 3회** | `app.py:153` + `context_processors.py:49` + `context_processors.py:90` | `before_request`에서 1회, `inject_status_list`에서 1회, `inject_menu`에서 1회. ADMIN이면 추가 User 목록 쿼리까지. 매 HTTP 요청마다 최대 3~4회 User 테이블 조회 |

#### 심각도: Medium (6건)

| # | 이슈 | 파일:라인 | 상세 |
|---|------|----------|------|
| M-1 | **첨부파일 전체 GROUP BY (3곳 반복)** | `erp_dashboard.py:67` / `erp_production_page.py:63` / `erp_construction_page.py:64` | `SELECT order_id, COUNT(*) FROM order_attachments GROUP BY order_id` — WHERE 없이 전체 테이블 집계가 **3개 대시보드에서 동일하게 반복** |
| M-2 | **bulk_update N+1 쿼리** | `orders.py:775-817` | `for oid in order_ids: db.query(Order).filter(Order.id == oid).first()` — 50건 선택 시 50번 SELECT |
| M-3 | **캘린더 API 2000건 전체 필드 로드** | `orders.py:327-478` | 기본 limit 2000, structured_data JSONB 포함 전체 필드 로드. FullCalendar는 현재 화면 범위만 필요 |
| M-4 | **nearby 검색 2500건 로드** | `orders.py:114-316` | 2500건 전체 로드 후 Python으로 주소 토큰 유사도 계산 + 5건에 대해 카카오 API 2단계 호출 |
| M-5 | **수도권 대시보드 8중 쿼리** | `dashboards.py:185-241` | 같은 base_query에서 상태별 7-8개 독립 쿼리 실행 |
| M-6 | **전역 console.log 대량 잔존** | `layout.html:424-553` (39건) + `map_view.html:1107-1123` (7건) | Socket.IO 디버그 로그가 **layout.html 전역**에 39건, map_view에 7건. Production 전체 페이지에서 직렬화 비용 발생 |

#### 심각도: Low (3건)

| # | 이슈 | 파일:라인 | 상세 |
|---|------|----------|------|
| L-1 | **menu_config 매 요청 파일 IO** | `context_processors.py:88` / `menu_config.py:6-14` | 모든 HTML 응답 렌더링마다 `menu_config.json` 파일 읽기(`os.path.exists` + `open`). Railway NFS 환경에서는 로컬보다 느림 |
| L-2 | **TEMPLATES_AUTO_RELOAD=True (Production)** | `app.py:414` | Production에서도 매 요청마다 모든 템플릿 파일의 mtime 확인 |
| L-3 | **인라인 JS 캐싱 불가** | `partials/erp_beta_js.html` (**2,319줄**) / `partials/erp_construction_scripts.html` (**1,681줄**) | 인라인 `<script>`로 매 페이지 요청마다 전송. 브라우저 캐싱 불가. CLAUDE.md 300줄 규칙 위반 |

---

### 2.2 추가 발견 (코드 품질/규칙 위반)

| # | 이슈 | 파일:라인 | 상세 |
|---|------|----------|------|
| Q-1 | **copy.deepcopy 미사용 (코드 냄새)** | `erp_measurement.py:127-161` | structured_data 수정 시 `copy.deepcopy` 없이 원본 참조를 직접 수정. 단, 161행에서 `order.structured_data = structured_data` 재할당 + 164행에서 `flag_modified` 호출하므로 **실무적 버그는 아님**. CLAUDE.md 규칙과 불일치하는 코드 냄새 수준 |
| Q-2 | **format_date 루프 내부 재정의** | `erp_map.py:472-479` | `def format_date()` 함수가 `for order in orders:` 루프 안에서 매 반복마다 재정의 |
| Q-3 | **지도 CDN 버전 불일치** | `map_view.html:10-13` | Bootstrap 5.1.3 / Font Awesome 6.0.0 사용 (layout.html은 5.3.0-alpha1 / 6.4.0). 캐시 히트율 0 |
| Q-4 | **erp_map.py 날짜 필터 로직 중복** | `erp_map.py:100-138` vs `erp_map.py:296-332` | `api_map_data`와 `api_generate_map` 두 함수에 동일한 날짜 필터 빌드 로직이 완전 복제 |

---

## 3. 영향 범위 분석

### 3.1 페이지별 성능 병목 매핑

```
┌─────────────────────────────────────┐
│ 모든 페이지 (매 요청)                │
│ H-5: User SELECT 최대 3회           │
│ L-1: menu_config 파일 IO            │
│ L-2: TEMPLATES_AUTO_RELOAD          │
│ M-6: console.log 39건 (layout)      │
│ 예상 낭비: 요청당 40-65ms            │
└──────────────┬──────────────────────┘
               │
     ┌─────────┴─────────────────────────────────────────┐
     │                    │                    │          │
     ▼                    ▼                    ▼          ▼
┌──────────┐       ┌──────────┐       ┌──────────┐  ┌──────────┐
│ 실측      │       │ 출고/시공  │       │ ERP 메인  │  │ 지방/수도권│
│ 대시보드   │       │ 대시보드   │       │ 대시보드   │  │ 대시보드   │
│           │       │           │       │           │  │           │
│ C-1,C-2   │       │ C-1,C-2   │       │ C-1,M-1   │  │ C-1,H-4   │
│ C-4,H-1   │       │ H-3       │       │           │  │ M-5       │
│ H-2       │       │           │       │           │  │           │
│           │       │           │       │           │  │           │
│ 병목:     │       │ 병목:     │       │ 병목:     │  │ 병목:     │
│ 2쿼리+    │       │ 다중쿼리+  │       │ 전체      │  │ LIMIT     │
│ N+1+      │       │ 1500건    │       │ GROUP BY  │  │ 없음      │
│ JSONB풀스캔│       │ JSONB풀스캔│       │ 300건루프  │  │ 전체로드   │
└─────┬──────┘       └──────────┘       └──────────┘  └──────────┘
      │
      ▼
┌──────────┐
│ 지도 페이지 │
│           │
│ C-3       │
│           │
│ 병목:     │
│ 동기 지오코딩│
│ 최대 40건  │
│ 16초 블로킹│
└──────────┘
```

### 3.2 데이터 증가 영향도

| 현재 주문 수 | 예상 주문 수 (6개월 후) | 영향받는 이슈 | 예상 악화 |
|------------|---------------------|------------|----------|
| ~500건 | ~1,500건 | C-1, H-1, H-3, H-4, C-4 | 쿼리 시간 3배 |
| ~500건 | ~3,000건 | C-2 (JSONB 풀스캔) | 쿼리 시간 6배 |
| 첨부파일 증가 | 첨부파일 3배 | M-1 (전체 GROUP BY x3곳) | 집계 시간 3배 |

---

## 4. 개선 원칙

### 4.1 GDM 원칙 적용
- **단순화 우선:** 캐시 레이어 추가보다 **불필요한 쿼리/데이터 로딩 제거** 우선
- **오컴의 면도날:** DB에서 할 수 있는 일은 DB에서 (Python 루프 필터링 → SQL WHERE)
- **구조적 의심:** 같은 패턴(1500건 풀로드 + Python 필터)이 3곳에서 반복 → 패턴 자체를 교정
- **근본 수정:** 인덱스 추가 등 근본 원인 제거 (쿼리 결과 캐싱 같은 우회책은 후순위)

### 4.2 안전 원칙
- **Phase별 독립 커밋**: 각 Phase를 별도 커밋으로 분리, 롤백 용이하게
- **기존 동작 보존**: API 응답 형식, 페이지 레이아웃 변경 없음
- **검증 후 다음 단계**: 각 Phase 완료 후 `python -c "import app; print('APP_OK')"` 확인
- **DB 마이그레이션**: `alembic revision --autogenerate` 후 수동 검토, `downgrade()` 포함

### 4.3 더블체크에서 확인된 주의사항
- **btree 인덱스는 `ILIKE '%...%'` 중간 매칭에 무효** → trigram 또는 expression index 필요
- **Boolean 저카디널리티 컬럼 단독 인덱스 효과 제한** → composite/partial index로 설계
- **실측/출고 대시보드의 query와 base_query는 역할이 다름** → 단순 슬라이싱 통합 불가
- **수정안은 현재 코드의 의미를 정확히 보존해야 함** → 각 Phase에서 코드 의미 분석 후 구현

---

## 5. Phase별 실행 계획

### Phase 0: Easy Wins (위험도: 낮음, 예상 효과: 모든 페이지 -40~80ms)

**목적:** 코드 변경 최소, 위험도 낮은 즉시 적용 가능한 개선

| 단계 | 작업 | 파일 | 변경 내용 | 예상 효과 |
|------|------|------|----------|----------|
| 0-1 | **g 객체 User 캐시** | `app.py`, `services/context_processors.py` | `before_request`에서 `g.current_user = get_user_by_id(uid)` 한 번만 로드. `inject_status_list`(49행), `inject_menu`(90행), `_erp_construction_team_restrict`(153행) 모두 `g.current_user` 참조로 변경 | 모든 요청 -10~30ms (DB SELECT 3회 → 1회) |
| 0-2 | **menu_config 모듈 레벨 캐시** | `services/menu_config.py` | `_menu_cache = None` 전역 변수로 최초 1회만 파일 읽기. 이후 메모리에서 반환 | 모든 요청 -5~20ms |
| 0-3 | **TEMPLATES_AUTO_RELOAD 조건부** | `app.py:414` | `app.config['TEMPLATES_AUTO_RELOAD'] = os.environ.get('FLASK_ENV') != 'production'` | 모든 요청 -5~15ms |
| 0-4 | **첨부파일 COUNT 범위 제한 (3곳)** | `erp_dashboard.py:65-71`, `erp_production_page.py:63`, `erp_construction_page.py:64` | `SELECT ... FROM order_attachments WHERE order_id = ANY(:ids) GROUP BY order_id` — 현재 표시 중인 주문 id만 대상. **3개 대시보드 모두 동일 수정** | 각 대시보드 -50~200ms |
| 0-5 | **Production console.log 정리** | `templates/layout.html:424-553`, `templates/map_view.html:1107-1123` | layout.html 전역 39건 + map_view 7건을 `if (window.FOMS_DEBUG)` 조건부로 래핑 또는 제거 | 직렬화 비용 제거 |

**검증:**
- [ ] `python -c "import app; print('APP_OK')"` 성공
- [ ] 각 대시보드 정상 로드 확인 (데이터 변경 없음)
- [ ] Socket.IO 알림 기능 정상 동작 확인 (console.log 제거 후)

---

### Phase 1: DB 인덱스 추가 (위험도: 낮음, 예상 효과: 특정 쿼리 30-50% 개선)

**목적:** 현재 쿼리 패턴에 맞는 인덱스 설계로 DB 부하 감소

> **더블체크 반영:** 단순 btree가 아닌, 실제 쿼리 패턴에 맞는 인덱스 종류를 선택합니다.
> `ILIKE '%...%'` 패턴에는 btree가 무효하므로, `pg_trgm` trigram 인덱스 또는
> composite/partial 인덱스를 사용합니다.

| 단계 | 작업 | 파일 | 변경 내용 |
|------|------|------|----------|
| 1-1 | **인덱스 설계** | (설계 문서) | 현재 쿼리 패턴 분석 후 인덱스 종류 결정 |
| 1-2 | **Order 모델에 인덱스 추가** | `models.py` | `__table_args__`에 인덱스 정의 |
| 1-3 | **Alembic 마이그레이션 생성** | `migrations/versions/xxx_add_performance_indexes.py` | 수동 검토 필수 |
| 1-4 | **downgrade() 작성** | 동일 파일 | 모든 인덱스/확장 DROP 포함 |

**인덱스 설계 상세 (쿼리 패턴 기반):**

```python
from sqlalchemy import Index, text

__table_args__ = (
    # ──────────────────────────────────────────────
    # 1) Composite partial index: ERP Beta 전용 쿼리 최적화
    #    거의 모든 ERP 대시보드가 is_erp_beta=True + status != DELETED 조합 사용
    #    저카디널리티 Boolean은 단독 btree 대신 composite partial로 효과 극대화
    # ──────────────────────────────────────────────
    Index('ix_orders_erp_beta_active', 'status', 'created_at',
          postgresql_where=text("is_erp_beta = true AND deleted_at IS NULL")),

    # 2) Partial index: 지방 주문 대시보드용
    Index('ix_orders_regional_active', 'status',
          postgresql_where=text("is_regional = true AND status != 'DELETED'")),

    # 3) Partial index: 자가실측 대시보드용
    Index('ix_orders_self_measurement_active', 'status',
          postgresql_where=text("is_self_measurement = true AND status != 'DELETED'")),

    # ──────────────────────────────────────────────
    # 4) 날짜 컬럼: String + ILIKE '%date%' 패턴 대응
    #    btree는 ILIKE '%...%'에 무효 → pg_trgm GIN 인덱스 사용
    #    ※ pg_trgm 확장이 필요: CREATE EXTENSION IF NOT EXISTS pg_trgm
    # ──────────────────────────────────────────────
    Index('ix_orders_measurement_date_trgm', 'measurement_date',
          postgresql_using='gin',
          postgresql_ops={'measurement_date': 'gin_trgm_ops'}),
    Index('ix_orders_scheduled_date_trgm', 'scheduled_date',
          postgresql_using='gin',
          postgresql_ops={'scheduled_date': 'gin_trgm_ops'}),

    # 5) 일반 btree: 등가 비교(=, >=, <=)에 사용되는 컬럼
    Index('ix_orders_received_date', 'received_date'),

    # ──────────────────────────────────────────────
    # 6) JSONB GIN 인덱스: structured_data 내부 경로 검색 최적화
    #    cast(structured_data, String).ilike() 대신
    #    structured_data->'schedule'->'measurement'->>'date' 경로 검색 시 활용
    # ──────────────────────────────────────────────
    Index('ix_orders_structured_data_gin', 'structured_data',
          postgresql_using='gin'),
)
```

**Alembic 마이그레이션에 포함할 사전 작업:**
```python
def upgrade():
    # pg_trgm 확장 활성화 (trigram 인덱스 전제조건)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # 이후 인덱스 생성...
```

**예상 효과 (쿼리 패턴별):**

| 쿼리 패턴 | 인덱스 종류 | Before | After |
|----------|-----------|--------|-------|
| `is_erp_beta == True AND status != 'DELETED'` | Partial composite | Full Scan | Index Scan |
| `is_regional == True AND status != 'DELETED'` | Partial | Full Scan | Index Scan |
| `measurement_date.ilike('%2026-03-09%')` | pg_trgm GIN | Full Scan | GIN Scan |
| `scheduled_date.ilike('%2026-03-09%')` | pg_trgm GIN | Full Scan | GIN Scan |
| `structured_data @> {...}` | JSONB GIN | Full Scan | GIN Scan |
| `received_date == '2026-03-09'` | btree | Full Scan | Index Scan |

**주의사항:**
- `pg_trgm` 확장이 Railway PostgreSQL에서 사용 가능한지 사전 확인 필요
- 사용 불가 시 btree 인덱스 + 쿼리 패턴 변경(정확한 날짜 매칭)으로 대체
- GIN 인덱스는 INSERT/UPDATE 시 약간의 오버헤드 발생 (현재 쓰기 부하 수준에서는 무시 가능)

**검증:**
- [ ] `alembic upgrade head` 성공
- [ ] `alembic downgrade -1` 롤백 테스트
- [ ] `EXPLAIN ANALYZE`로 주요 쿼리의 Index Scan 전환 확인
- [ ] 실측 대시보드, ERP 대시보드, 지방 대시보드 정상 로드

---

### Phase 2: 쿼리 최적화 (위험도: 중간, 예상 효과: 대시보드별 50-70% 개선)

**목적:** 과도한 데이터 로딩과 Python 레벨 필터링 최적화

> **더블체크 반영:** 실측/출고 대시보드의 `query`와 `base_query`는 역할이 다릅니다.
> `query`는 날짜 필터 적용 결과, `base_query`는 패널 집계용 전체 기반.
> 단순 슬라이싱 통합은 불가하며, 각각의 의미를 보존한 최적화가 필요합니다.

#### 2-1. 실측 대시보드 패널 쿼리 경량화

**현재 코드 구조 (의미 분석):**
```python
# erp_measurement_dashboard.py
base_query = db.query(Order).filter(Order.status != 'DELETED', ...)  # 104행
query = base_query  # 날짜 필터 전 동일

# 날짜 필터 적용 (124~158행) → query에만 적용, base_query는 변경 없음
if use_range:
    query = query.filter(or_(*date_conditions))
elif use_single_day:
    query = query.filter(or_(*date_conditions))

# 163행: query (날짜 필터 적용됨) → 테이블 표시용
all_rows = query.order_by(Order.id.desc()).limit(500).all()

# 171행: base_query (날짜 필터 없음) → 14일 패널 집계용
panel_orders = base_query.order_by(Order.id.desc()).limit(1500).all()
```

**핵심:** `query ≠ base_query` (날짜 필터 유무 차이). 단순 슬라이싱으로 합칠 수 없음.

**개선 방안 (의미 보존):**
```python
# 방안 A: panel 집계를 경량 쿼리로 전환 (ORM 객체 대신 필요 컬럼만)
panel_data = (
    base_query
    .with_entities(Order.id, Order.measurement_date, Order.is_erp_beta, Order.structured_data,
                   Order.is_self_measurement)
    .order_by(Order.id.desc())
    .limit(1500)
    .all()
)
# → ORM 객체 생성 비용 절약, structured_data 외 컬럼 전송량 감소

# 방안 B: 패널 집계를 DB 집계 쿼리로 전환 (가장 효율적, 구현 복잡)
# measurement_date가 CSV 형태라 DB 레벨 GROUP BY가 어려움
# → 방안 A가 현실적
```

**파일:** `apps/erp_measurement_dashboard.py`
**예상 효과:** panel 쿼리 메모리 사용량 ~50% 감소 (전체 ORM → 5컬럼)

#### 2-2. 실측 대시보드 N+1 쿼리 제거

**현재 문제:**
```python
# erp_measurement_dashboard.py:250 — 최대 300회 추가 SELECT
for r in rows:
    r.product_items = build_product_items_for_order(db, r)
```

**개선 방안:**
```python
# 한 번에 배치 로드
order_ids = [r.id for r in rows]
all_attachments = (
    db.query(OrderAttachment)
    .filter(OrderAttachment.order_id.in_(order_ids))
    .all()
)
att_by_order = {}
for att in all_attachments:
    att_by_order.setdefault(att.order_id, []).append(att)

for r in rows:
    r.product_items = build_product_items_from_cache(r, att_by_order.get(r.id, []))
```

**파일:** `apps/erp_measurement_dashboard.py`, `services/erp_product_items.py`
**예상 효과:** N+1 (300회) → 1회 배치 쿼리

#### 2-3. 출고 대시보드 개별 최적화

> **더블체크 반영:** 출고 대시보드는 실측과 구조가 다릅니다.
> `panel_orders`(159행)는 14일 패널+잔여 인력 계산용,
> `all_candidates`(268,291,324행)는 날짜 범위/단일/전체 3가지 분기.
> 단순 통합이 아닌 개별 경량화가 안전합니다.

**개선 방안:**
```python
# 2-3a: panel_orders를 경량 쿼리로 전환 (2-1과 동일 패턴)
panel_data = (
    panel_query
    .with_entities(Order.id, Order.scheduled_date, Order.is_erp_beta, Order.structured_data)
    .order_by(Order.id.desc())
    .limit(1500)
    .all()
)

# 2-3b: 단일 날짜 검색(291행)에서 LIMIT 없는 .all() → .limit(500) 추가
# 현재: .order_by(Order.id.desc()).all()
# 개선: .order_by(Order.id.desc()).limit(500).all()
```

**파일:** `apps/erp_shipment_page.py`

#### 2-4. 실측 동선 API Beta 과다 조회 수정

> **더블체크 반영:** 원래 계획서에서 누락된 병목입니다.

**현재 문제:**
```python
# erp_measurement.py:192-196
query = query.filter(
    or_(
        and_(Order.measurement_date.isnot(None), Order.measurement_date != '',
             Order.measurement_date.ilike(f'%{date_filter}%')),
        and_(Order.is_erp_beta == True, Order.structured_data.isnot(None))
        #                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        # 날짜 무관하게 모든 Beta 주문을 끌어옴!
    )
)
```

**개선 방안:**
```python
# Beta 주문도 날짜 기반으로 좁히기
query = query.filter(
    or_(
        and_(Order.measurement_date.isnot(None), Order.measurement_date != '',
             Order.measurement_date.ilike(f'%{date_filter}%')),
        and_(Order.is_erp_beta == True,
             Order.structured_data.isnot(None),
             # JSONB 경로 연산자로 정확한 날짜 매칭
             or_(
                 Order.structured_data['schedule']['measurement']['date'].astext.contains(date_filter),
                 Order.measurement_date.ilike(f'%{date_filter}%')
             ))
    )
)
```

**파일:** `apps/api/erp_measurement.py`
**예상 효과:** Beta 전체 조회 → 날짜 매칭 Beta만 조회

#### 2-5. 지방/자가실측 대시보드 LIMIT 추가

**현재 문제:**
```python
# dashboards.py:54 — LIMIT 없음
all_regional_orders = base_query.order_by(Order.id.desc()).all()
# dashboards.py:288 — LIMIT 없음
all_orders = base_query.order_by(Order.id.desc()).all()
```

**개선 방안:**
```python
all_regional_orders = base_query.order_by(Order.id.desc()).limit(500).all()
all_orders = base_query.order_by(Order.id.desc()).limit(500).all()
```

**파일:** `apps/dashboards.py`
**예상 효과:** 데이터 증가 시 무한 느려짐 방지. 500건 캡으로 안정적 응답 시간 보장

#### 2-6. bulk_update N+1 → IN 절 배치

**현재 문제:**
```python
# orders.py:775-817
for oid in order_ids:
    order = db.query(Order).filter(Order.id == oid).first()  # N번 쿼리
```

**개선 방안:**
```python
valid_ids = [int(oid) for oid in order_ids if str(oid).isdigit()]
orders_map = {o.id: o for o in db.query(Order).filter(Order.id.in_(valid_ids)).all()}
for oid in valid_ids:
    order = orders_map.get(oid)
    if not order:
        continue
    # ... 기존 로직 동일
```

**파일:** `apps/api/orders.py`
**예상 효과:** 50건 선택 시 50 SELECT → 1 SELECT

#### 2-7. JSONB cast+ILIKE → JSONB 경로 연산자 전환

**현재 문제:**
```python
# erp_measurement_dashboard.py:141
erp_beta_date_likes = [cast(Order.structured_data, String).ilike(f'%{d}%') for d in range_dates[:31]]
# erp_measurement_dashboard.py:156
and_(Order.is_erp_beta == True, cast(Order.structured_data, String).ilike(f'%{selected_date}%'))
```

**개선 방안 (단기 — JSONB 경로 연산자):**
```python
# 기존: cast(structured_data, String).ilike('%날짜%')
# 개선: JSONB 경로 연산자로 정확한 필드만 검색
and_(
    Order.is_erp_beta == True,
    or_(
        # 대표 실측일
        Order.structured_data['schedule']['measurement']['date'].astext.contains(selected_date),
        # 항목별 실측일은 배열이라 경로 연산자로 직접 접근 어려움
        # → measurement_date 컬럼 동기화를 강화하여 JSONB 검색 최소화
        Order.measurement_date.ilike(f'%{selected_date}%')
    )
)
```

**개선 방안 (중기 — GIN 인덱스 + containment 연산자):**
```python
# Phase 1에서 JSONB GIN 인덱스 추가 후
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
Order.structured_data.op('@>')(
    cast({"schedule": {"measurement": {"date": selected_date}}}, PG_JSONB)
)
```

**파일:** `apps/erp_measurement_dashboard.py`, `apps/erp_shipment_page.py`, `apps/erp_as_page.py`
**예상 효과:** JSONB 전체 텍스트 캐스팅 → 필드 지정 검색. GIN 인덱스 활용 시 극적 개선

#### 2-8. 캘린더 API limit 축소

**현재 문제:**
```python
# orders.py:327 — 기본 2000건, 전체 필드
limit_raw = request.args.get('limit', '2000')
```

**개선 방안:**
```python
limit_raw = request.args.get('limit', '500')
limit = max(100, min(limit, 1000))  # 최대 1000으로 제한
```

**파일:** `apps/api/orders.py`

#### 2-9. 수도권 대시보드 8중 쿼리 → 단일 쿼리 + Python 분류

**현재 문제:** `dashboards.py:185-241`에서 동일 base_query로 8개 독립 쿼리

**개선 방안:**
```python
# 한 번에 로드
all_metro = base_query.order_by(Order.created_at.desc()).limit(500).all()

# Python에서 상태별 분류
from collections import defaultdict
by_status = defaultdict(list)
for o in all_metro:
    by_status[o.status].append(o)

urgent_candidates = [o for o in by_status.get('MEASURED', []) if ...]
# ... 기존 분류 로직 유지
```

**파일:** `apps/dashboards.py`
**예상 효과:** DB 쿼리 8회 → 1회

**Phase 2 검증:**
- [ ] 각 대시보드 정상 로드 (데이터 정합성 확인)
- [ ] API 응답 형식 변경 없음 확인
- [ ] 날짜 필터 있을 때/없을 때 모두 테스트
- [ ] `python -c "import app; print('APP_OK')"` 성공

---

### Phase 3: 지도 최적화 (위험도: 중간, 예상 효과: 지도 진입 10초+ → 1초 이하)

#### 3-1. 동기 지오코딩 제거 → 완전 비동기

**현재 문제:**
```python
# erp_map.py:512-569
_SYNC_GEOCODE_MAX = 40      # 요청당 최대 40건 동기
_SYNC_GEOCODE_PARALLEL = 5   # 5스레드 병렬 → 최악 16초 블로킹
```

**개선 방안:**
```python
# 동기 지오코딩 완전 제거
# 좌표 없는 주문은 geocode_status='pending' 상태로 즉시 반환
# 백그라운드 큐(enqueue_geocode_order_address)만 사용

# 이미 map_view.html:988-1053에 자동 갱신 폴링 로직 구현됨
# → 동기 지오코딩 없이도 15초 후 자동으로 좌표 업데이트

# 변경: sync_batch 처리 블록 전체를 enqueue로 교체
for order, addr, ctx in to_geocode:
    enqueue_geocode_order_address(order.id)
    order.geocode_status = 'pending'
if to_geocode:
    db.commit()
```

**파일:** `apps/api/erp_map.py:512-569`
**예상 효과:** 지도 API 응답 시간 10-16초 → 0.5-1초

#### 3-2. format_date 루프 밖으로 이동

**현재 문제:** `erp_map.py:472-479`에서 `def format_date()` 가 for 루프 안에 위치

**개선 방안:** 함수 정의를 루프 바깥(`api_generate_map` 함수 시작부)으로 이동

**파일:** `apps/api/erp_map.py`

#### 3-3. 날짜 필터 로직 중복 제거

**현재 문제:** `api_map_data`(100-138)와 `api_generate_map`(296-332) 동일 로직 복제

**개선 방안:**
```python
def _build_map_date_filter(query, date_filter, dashboard):
    """지도 API 공통 날짜 필터 빌드"""
    # 기존 로직을 헬퍼 함수로 추출
    ...
    return query
```

**파일:** `apps/api/erp_map.py`

#### 3-4. 지도 CDN 버전 통일

**현재 문제:** `map_view.html`이 `layout.html`과 다른 Bootstrap/Font Awesome 버전 로드

**개선 방안:** CDN 버전을 layout.html과 통일 (5.3.0-alpha1 / 6.4.0)

**파일:** `templates/map_view.html`

**Phase 3 검증:**
- [ ] 지도 페이지 정상 로드 (좌표 있는 주문 즉시 표시)
- [ ] 좌표 없는 주문이 15초 후 자동 갱신되는지 확인
- [ ] Gunicorn 워커 블로킹 없음 확인

---

### Phase 4: 추가 개선 (장기, 선택적)

| 단계 | 작업 | 상세 |
|------|------|------|
| 4-1 | **Gunicorn gzip 미들웨어** | Flask-Compress 또는 WhiteNoise 적용. JSON/HTML 응답 50-70% 크기 감소 |
| 4-2 | **정적 파일 캐시 헤더** | `Cache-Control: max-age=31536000` (해시 기반 버스팅) |
| 4-3 | **인라인 JS 외부화** | `erp_beta_js.html` (2,319줄) → `static/js/erp_beta.js` 분리. 브라우저 캐싱 가능 |
| 4-4 | **실측 summary API 캐시** | Redis 60초 캐시 적용 (폴링 빈도 대비 DB 부하 감소) |
| 4-5 | **날짜 컬럼 정규화 (장기)** | `measurement_date` String CSV → 별도 date 테이블 or PostgreSQL Array 타입. btree 인덱스 활용 가능. 대규모 마이그레이션 필요 |

---

## 6. 예상 효과 요약

### 6.1 Phase별 예상 개선 효과

| Phase | 작업량 | 위험도 | 예상 개선 |
|-------|-------|--------|----------|
| **Phase 0** | 작음 (5파일 수정) | 낮음 | 모든 페이지 -40~80ms |
| **Phase 1** | 작음 (마이그레이션 1건) | 낮음 | 특정 쿼리 30-50% (인덱스 종류에 따라 상이) |
| **Phase 2** | 중간 (9파일 수정) | 중간 | 대시보드별 50-70% 개선 |
| **Phase 3** | 중간 (3파일 수정) | 중간 | 지도 진입 10초 → 1초 |
| **Phase 4** | 선택적 | 낮음~높음 | 추가 20-30% |

### 6.2 페이지별 예상 응답 시간

| 페이지 | 현재 (추정) | Phase 0+1 후 | Phase 2 후 | Phase 3 후 |
|--------|-----------|-------------|-----------|-----------|
| 실측 대시보드 | 2-4초 | 1.5-3초 | 0.5-1.5초 | - |
| 지도 진입 | 5-16초 | 4-15초 | - | 0.5-1초 |
| ERP 메인 대시보드 | 1-3초 | 0.8-2초 | 0.5-1초 | - |
| 출고 대시보드 | 2-4초 | 1.5-3초 | 0.5-1.5초 | - |
| 지방 대시보드 | 1-3초 (증가중) | 0.8-2초 | 0.5-1초 (캡) | - |
| 수도권 대시보드 | 1-3초 | 0.8-2초 | 0.5-1초 | - |

> **주의:** Phase 1 인덱스 효과는 `pg_trgm` 확장 사용 가능 여부에 따라 달라집니다.
> 사용 불가 시 ILIKE 쿼리 개선은 Phase 2의 JSONB 경로 연산자 전환에 의존합니다.

---

## 7. 성공 기준

- [ ] **실측 대시보드** 1.5초 이내 로드 (현재 2-4초)
- [ ] **지도 진입** 1초 이내 로드 (현재 5-16초)
- [ ] 주문 데이터 3,000건에서도 **대시보드 2초 이내** 응답
- [ ] API 응답 형식, 페이지 레이아웃 **변경 없음** (기존 동작 100% 보존)
- [ ] `python -c "import app; print('APP_OK')"` 성공
- [ ] Alembic downgrade 롤백 테스트 통과

---

## 8. 더블체크 이력

### 2026-03-09 소스 기준 교차 검증

더블체크에서 발견된 문제와 반영 내용:

| 지적 사항 | 판정 | 반영 내용 |
|----------|------|----------|
| btree 인덱스가 ILIKE '%...%'에 무효 | **타당** | Phase 1 인덱스 설계를 pg_trgm GIN + partial composite로 재설계 |
| Boolean 저카디널리티 단독 인덱스 효과 제한 | **타당** | composite partial index로 변경 |
| 실측 대시보드 query≠base_query, 슬라이싱 불가 | **타당** | Phase 2-1을 경량 쿼리(with_entities)로 변경, 통합 제거 |
| 출고 대시보드도 단순 통합 불가 | **타당** | Phase 2-3을 개별 경량화로 변경 |
| erp_measurement.py:196 Beta 과다 조회 누락 | **타당** | C-4로 추가, Phase 2-4로 수정안 추가 |
| copy.deepcopy 과장 | **타당** | Q-1 설명을 "코드 냄새" 수준으로 하향 |
| console.log 범위: layout.html 39건 | **타당** | M-6로 승격, Phase 0-5에 layout 포함 |
| GROUP BY 3곳 반복 | **타당** | M-1에 3곳 명시, Phase 0-4에 3곳 모두 수정 |
| 줄수 오차 (2,125 → 2,319줄) | **타당** | L-3 실제 줄수로 정정 |
| Phase 1 기대 효과 과장 | **타당** | 예상 효과를 "특정 쿼리 30-50%"로 보수적 조정 |

---

## 9. 참조

- `docs/AI_STATUS.md` — 프로젝트 현재 상태
- `docs/context/DECISIONS.md` — 기술/아키텍처 결정 기록
- `models.py` — Order 모델 (인덱스 추가 대상)
- `apps/erp_measurement_dashboard.py` — 실측 대시보드 (핵심 최적화 대상)
- `apps/api/erp_measurement.py` — 실측 동선 API (Beta 과다 조회 수정 대상)
- `apps/api/erp_map.py` — 지도 API (동기 지오코딩 제거 대상)
- `apps/erp_dashboard.py` — ERP 메인 대시보드
- `apps/erp_production_page.py` — 생산 대시보드 (첨부파일 GROUP BY)
- `apps/erp_construction_page.py` — 시공 대시보드 (첨부파일 GROUP BY)
- `apps/dashboards.py` — 수도권/지방 대시보드
- `apps/erp_shipment_page.py` — 출고 대시보드
- `apps/api/orders.py` — 캘린더/nearby/bulk API
- `app.py` — before_request, TEMPLATES_AUTO_RELOAD
- `services/context_processors.py` — inject_status_list, inject_menu
- `services/menu_config.py` — 메뉴 설정 파일 로드
- `templates/layout.html` — 전역 Socket.IO console.log (39건)
- `templates/map_view.html` — 지도 페이지 console.log (7건)
