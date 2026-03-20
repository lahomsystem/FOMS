# FOMS 대규모 데이터 검색·필터 아키텍처 개선 계획 (대형 ERP 스타일 정렬)

**작성일**: 2026-03-20
**작성자**: Claude Code (python-backend agent)
**상태**: DRAFT

---

## 0. 코드 대조 후 개정 메모

### 0.1 이번 개정에서 추가하는 것

이 문서는 초안 대비 아래 3가지를 보강한다.

1. **실행 가능한 개정안**: 실제 코드와 어긋난 영향 범위·가정·예시 SQL을 수정한다.
2. **우선순위 재정렬**: 메인 ERP 대시보드뿐 아니라 동일 패턴 화면과 집계 왜곡까지 포함해 즉시/단기/중기 순서를 다시 잡는다.
3. **단계별 체크리스트**: 착수 전 확인, 회귀 테스트, 운영 전 확인 항목을 추가한다.
4. **대형 ERP 스타일 정렬 기준**: FOMS가 목표로 삼을 운영/이력/검색/첨부 처리 방식을 명시한다.

### 0.2 이번 코드 대조로 확인된 핵심 사실

- `apps/erp_dashboard.py`의 문제는 목록 필터뿐 아니라 `kpis`, `step_stats`, `total_orders`, `total_pages`도 `limit(1000)` 이후 데이터 기준이라는 점이다.
- `apps/erp_measurement_dashboard.py`(`limit(500)`), `apps/erp_construction_page.py`(`limit(300)`)도 같은 클래스의 리스크를 가진다.
- `apps/erp_production_page.py`는 이미 SQL stage filter, SQL count, OFFSET/LIMIT를 사용하므로 선행 레퍼런스로 삼을 수 있다.
- 첨부/멀티미디어는 `order_id` 기준 별도 조회/열람 경로가 있어 **주문만 찾으면 열람은 가능**하다. 그러나 **미디어 자체 검색**은 현재 없고, 초안에도 포함되지 않았다.

### 0.3 범위 재정의

- **1순위**: `apps/erp_dashboard.py` 검색 정확도 + 집계 정확도 복구
- **2순위**: 동일 패턴인 `apps/erp_measurement_dashboard.py`, `apps/erp_construction_page.py` 점검/개선
- **3순위**: 장기적으로 주문 검색과 첨부/미디어 메타데이터 검색을 분리한 검색 아키텍처 설계
- **4순위**: 운영 화면과 과거 이력 조회를 분리한 **대형 ERP 스타일**로 UX/데이터 경계를 재정의

---

## 1. 현재 문제 정의

### 1.1 핵심 증상

`apps/erp_dashboard.py` 기준 현재 구조:

```
DB 쿼리 (limit 1000)
    ↓
Python 인메모리 enriched 변환 (stage, alerts 계산)
    ↓
Python 인메모리 필터 (f_stage / f_urgent / f_has_alert / f_alert_type / f_team)
    ↓
Python 인메모리 정렬 (measurement_date / construction_date)
    ↓
Python 인메모리 페이지네이션 (per_page=50)
```

**문제**: DB에 1001번째 이후 데이터는 Python 파이프라인에 전달되지 않는다.
Python 필터·정렬·페이지네이션은 이미 잘린 1000건 기준으로만 동작한다.

### 1.2 실제 영향 범위 (코드 대조 기준)

| 파일 | 현재 상한 | 실제 영향 |
|------|-----------|----------|
| `apps/erp_dashboard.py` | 1000 | 메인 ERP 대시보드. 목록 필터, 상단 KPI, 단계 타일, 페이지네이션 모두 영향 |
| `apps/erp_measurement_dashboard.py` | 500 | 실측 대시보드 목록. 날짜 검색 후에도 상한 존재 |
| `apps/erp_construction_page.py` | 300 | 시공 대시보드 목록/타일/KPI 정확도 영향 |
| `apps/api/erp_measurement.py` | 1500 | 실측 요약 패널 전용 |
| `apps/api/orders.py` (`/orders`) | 100~5000 | 캘린더 이벤트 API. limit 기반이며 서버 페이지네이션 없음 |
| `apps/api/orders.py` (`/orders/nearby`) | 2500 | 가까운 시공 후보 탐색용. 자동완성 검색 후보가 아님 |
| `apps/api/personal_board.py` | 500 / 300 | 보드 전체가 아니라 일부 helper 쿼리 상한 |

가장 시급한 파일은 `apps/erp_dashboard.py`다. 다만 대규모 누적 상황에서 같은 구조적 리스크를 가진
`apps/erp_measurement_dashboard.py`, `apps/erp_construction_page.py`도 같은 트랙에서 관리해야 한다.

### 1.3 추가 확인: 상단 타일/KPI도 이미 잘린 데이터 기준

`apps/erp_dashboard.py`에서 `kpis`, `step_stats`, `total_orders`, `total_pages`는 모두
`orders = _q.limit(1000).all()` 이후 만들어진 `light_enriched`/`filtered` 기준이다.

즉 현재 구조의 문제는 단순히 **"필터 결과가 잘린다"**가 아니라,

- 단계 타일이 전체 활성 ERP Beta 건수를 반영하지 못하고
- KPI 뱃지가 최근 1000건 샘플 기준으로 왜곡되며
- 페이지 수도 전체 결과가 아니라 잘린 결과 기준으로 계산된다는 점이다.

따라서 `f_stage`/`f_urgent` SQL화만으로는 절반만 해결된다. 집계 쿼리 분리가 즉시 필요하다.

### 1.4 왜 지금은 문제가 적은가

현재 FOMS ERP Beta 주문은 수백 건 수준이다. limit(1000) 이내에 전체 데이터가
들어오므로 실질적 누락은 없다. 그러나 수만 건 규모로 성장하면 구조적 결함이
표면화된다.

### 1.5 인메모리 필터 분류

```
f_q           → 이미 SQL WHERE (safe)
mine          → 이미 SQL WHERE (safe)
f_stage       → 인메모리: structured_data['workflow']['stage'] 읽기
f_urgent      → 인메모리: structured_data['flags']['urgent'] 읽기
f_has_alert   → 인메모리: urgent OR drawing_overdue OR D-day 중 하나
f_alert_type  → 인메모리: measurement_d4 / construction_d3 / production_d2
f_team        → 인메모리: get_required_approval_teams_for_stage() 호출
```

D-day 계산(`measurement_d4`, `construction_d3`, `production_d2`)은
`services.business_calendar.business_days_until()`을 Python에서 호출한다.
이 함수는 공휴일 JSON을 참조하므로 SQL로 직접 이식 불가능하다.

### 1.6 멀티미디어(첨부) 관련 실제 상태

- 현재 첨부 열람은 `OrderAttachment` + `/api/orders/<order_id>/attachments` + `/api/files/view|download` 경로로 동작한다.
- 대시보드는 **현재 페이지 주문 id 집합**에 대해서만 `order_attachments` count/preload를 수행한다.
- 따라서 **"검색 결과 누락"**과 **"첨부 열람 불가"**는 같은 문제가 아니다.
- 다만 **첨부 filename/category/file_type 기반 검색**, **미디어 자체 검색**, **첨부가 많은 주문의 상세 preload 최적화**는 별도 과제다.

---

## 2. 단계별 실행 계획

### Phase A: SQL 전환 가능한 필터 즉시 이동

#### A-0. step_stats / KPI 집계 쿼리 분리

**목표**: 상단 타일과 KPI가 `limit(1000)` 샘플이 아니라 전체 활성 ERP Beta 주문 기준으로 계산되게 한다.

**문제**:
- 현재 `apps/erp_dashboard.py`는 목록용 쿼리에서 잘린 1000건으로 `kpis`, `step_stats`를 계산한다.
- 주문 1001건을 넘는 순간 상단 숫자 자체가 왜곡된다.

**대상 파일**: `apps/erp_dashboard.py`

**수정 방향**:
1. 목록 쿼리와 별도로 집계용 base query를 둔다.
2. 단계별 카운트는 SQL `GROUP BY` 또는 최소한 `order_by(None)` 기반 별도 집계 쿼리로 분리한다.
3. KPI(`urgent`, `measurement_d4`, `construction_d3`, `production_d2`)는 집계 전용 경로로 계산한다.
4. `apps/erp_production_page.py`의 SQL count / OFFSET-LIMIT 구조를 레퍼런스로 사용한다.

**기대 효과**:
- 데이터 1000건 초과 시에도 타일/KPI가 전체 기준으로 정확해진다.
- 이후 목록 필터 SQL화와 페이지네이션 개선의 기반이 생긴다.

**난이도**: 중간.

#### A-1. f_stage → JSONB SQL WHERE

**목표**: DB에서 직접 걸 수 있는 필터 2개를 SQL WHERE로 이동.
인메모리 처리 비용을 줄이고 limit 문제를 부분 해소.

`erp_production_page.py`에 이미 확립된 패턴:

```python
stage_col = cast(Order.structured_data['workflow']['stage'], String)
_q = _q.filter(stage_col.in_(['"고객컨펌"', '"CONFIRM"']))
```

`erp_dashboard.py`에 동일 패턴 적용. 단, 대시보드는 AS접수/AS처리를
'AS처리' 버킷으로 묶는 로직이 있으므로 매핑 테이블을 먼저 정의한다.

**매핑 설계** (`STAGE_SQL_FILTER_MAP`):

```python
STAGE_SQL_FILTER_MAP: dict[str, list[str]] = {
    '주문접수': ['"주문접수"', '"RECEIVED"'],
    '실측':    ['"실측"', '"MEASURE"'],
    '도면':    ['"도면"', '"DRAWING"'],
    '고객컨펌': ['"고객컨펌"', '"CONFIRM"'],
    '생산':    ['"생산"', '"PRODUCTION"'],
    '시공':    ['"시공"', '"CONSTRUCTION"'],
    'CS':      ['"CS"'],
    '완료':    ['"완료"', '"COMPLETED"', '"AS완료"', '"AS_COMPLETED"'],
    'AS처리':  ['"AS접수"', '"AS처리"', '"AS_RECEIVED"', '"AS"'],
}
```

**주의**: step_stats(파이프라인 상단 카운트 타일)는 전체 데이터를 기반으로
집계해야 한다. f_stage SQL 필터 적용 쿼리는 목록 표시에만 사용하고,
카운트 타일용 집계는 f_stage 없이 별도 집계 쿼리를 수행한다.

**대상 파일**: `apps/erp_dashboard.py`

**수정 방향**:
1. `STAGE_SQL_FILTER_MAP` 상수를 `services/erp_policy.py`에 추가
2. `erp_dashboard()` 내부 SQL 쿼리 빌드 시 f_stage가 있으면 JSONB cast filter 추가
3. 인메모리 `filtered` 루프의 f_stage 블록 제거
4. 인메모리 f_stage 정렬은 그대로 유지 (SQL ORDER BY로 이동은 Phase B)

**기대 효과**: limit 1000 내에서 f_stage 필터가 누락되던 문제 해소.
DB가 stage별로 결과를 줄여주므로 limit 의미도 stage별 1000건으로 개선.

**난이도**: 낮음. `erp_production_page.py` 패턴 그대로 이식.

**동작 보존 원칙**:
- AS접수/AS처리 → 'AS처리' 버킷 매핑은 SQL 필터 내 배열로 표현
- step_stats 카운트는 반드시 f_stage 필터 미적용 쿼리 기준 유지

---

#### A-2. f_urgent → JSONB SQL WHERE

urgent 플래그는 `structured_data['flags']['urgent']` 단순 JSONB 경로다.

```python
from sqlalchemy import cast, String
urgent_col = cast(Order.structured_data['flags']['urgent'], String)
_q = _q.filter(urgent_col == 'true')
```

PostgreSQL JSONB에서 boolean은 `'true'` 문자열로 캐스팅된다.
`NULL` 케이스(키 없음)는 `== 'true'` 비교 시 자동으로 제외되므로 안전하다.

**주의**:
- 데이터 계약이 JSON boolean(`true/false`)만 보장되면 위 비교로 충분하다.
- 과도기 데이터에 `'1'`, `1`, `'TRUE'` 등이 섞일 가능성이 있으면 비교값을 더 넓게 잡는 별도 검증이 필요하다.

**⚠️ 구현 전 필수 확인 (감리 결과 반영)**:
- Python `_erp_get_urgent_flag()`는 `bool()` 변환을 사용하므로 `True`, `1`, `"1"`, `"TRUE"` 등 모두 truthy로 처리한다.
- SQL `cast(..., String) == 'true'`는 JSON boolean `true`만 매칭한다. `1`, `"true"` 문자열 저장 시 `'1'` 또는 `'"true"'`로 cast되어 매칭 실패한다.
- **구현 착수 전 운영 DB에서 `flags.urgent` 실제 저장값을 샘플링**하여 데이터 계약을 확정한 뒤 SQL 비교 조건을 결정해야 한다.
- 만약 혼합 형태가 발견되면: `urgent_col.in_(['true', '"true"', '1', '"1"'])` 같은 넓은 비교를 사용한다.

**대상 파일**: `apps/erp_dashboard.py`

**수정 방향**:
1. **운영 DB `flags.urgent` 값 형태 샘플링** (구현 전 필수)
2. SQL 쿼리 빌드 시 `f_urgent == '1'` 이면 JSONB cast filter 추가 (샘플링 결과에 맞는 비교 조건 사용)
3. 인메모리 `filtered` 루프의 f_urgent 블록 제거

**기대 효과**: limit 이후 urgent 주문 누락 방지.

**난이도**: 낮음.

---

#### A-3. 실측/시공 화면 동일 패턴 점검

**목표**: 메인 ERP 대시보드만 고치고 같은 구조의 다른 화면을 방치하는 일을 막는다.

**대상 파일**:
- `apps/erp_measurement_dashboard.py`
- `apps/erp_construction_page.py`

**확인 항목**:
1. 현재 limit 상한이 목록/타일/KPI/페이지네이션에 어떤 영향을 주는지 확인
2. 메인 대시보드와 동일하게 SQL 필터 선적용 + 집계 분리 + 페이지네이션 전환 필요 여부 판단
3. 메인 대시보드 개편 후에도 사용자가 체감하는 "과거 주문 안 보임" 문제가 다른 화면에서 재발하지 않게 한다

**산출물**:
- 각 화면별 현재 한계와 개선 필요 여부를 표로 정리
- 메인 대시보드 개편과 같은 스프린트에 포함할지, 별도 Phase로 뺄지 결정

**난이도**: 중간.

---

### Phase B: D-day 날짜 컬럼 정규화

**목표**: `measurement_d4`, `construction_d3`, `production_d2` 필터를
SQL WHERE로 이동하기 위한 정규화 컬럼 도입.

#### B-1. 문제 분석

`_erp_alerts()`는 Python에서 `business_days_until(date, today)`를 호출한다.
이 함수는 `data/holidays_kr_{year}.json`을 읽어 공휴일을 포함한 영업일을 계산한다.
PostgreSQL에는 공휴일 정보가 없으므로 SQL로 완전히 이식 불가능하다.

**근사치 접근 (달력일 기반, 연휴 안전 마진 포함)**:
- 영업일 4일 → 달력일 cutoff **12일** (추석/설 최대 6일 연속 연휴 + 전후 주말 조합 시 최악 케이스 커버)
- 영업일 3일 → 달력일 cutoff **10일**
- 영업일 2일 → 달력일 cutoff **8일**

> **감리 결과 반영**: 초안의 `days=5~6`은 일반 주말만 포함한 근사치였다.
> 추석/설 연휴(최대 6일 연속 비영업일) + 전후 주말 조합 시 영업일 4일이 달력일 10~11일까지 늘어난다.
> cutoff가 짧으면 1단계 SQL 후보군에서 누락된 주문은 2단계 Python 정밀 필터로도 복구 불가능하다.
> 따라서 cutoff를 넉넉하게 잡고(후보군이 약간 넓어지는 비용), 2단계에서 정밀 필터링한다.

근사치 SQL 필터로 "후보군"을 DB에서 추출하고,
Python에서 정밀 business_days 계산으로 최종 확정한다.
(2단계 필터 패턴)

#### B-2. Order 모델 컬럼 추가

`models.py`에 정규화 컬럼 2개 추가:

```python
# ERP Beta 실측·시공 일정 정규화 컬럼 (D-day SQL 필터용)
erp_measurement_date = Column(String(10), nullable=True, index=True)   # YYYY-MM-DD
erp_construction_date = Column(String(10), nullable=True, index=True)  # YYYY-MM-DD
```

**기존 컬럼과의 차이**:
- `measurement_date`: 레거시 주문 포함, 다양한 형식 혼재
- `erp_measurement_date`: ERP Beta 주문 전용, YYYY-MM-DD 정규화 보장
- `scheduled_date`: 레거시/비ERP 시공일
- `erp_construction_date`: ERP Beta 주문 전용, YYYY-MM-DD 정규화 보장

#### B-3. 컬럼 동기화 시점

두 가지 방식 중 트리거 방식 채택:

**방식**: ERP Beta 주문 단계 변경 또는 일정 수정 시 동기화

```python
# services/erp_sync_columns.py (신규)
def sync_erp_date_columns(order, structured_data: dict) -> None:
    """ERP Beta 주문의 정규화 날짜 컬럼을 structured_data와 동기화.

    호출 시점: 단계 변경, 일정 수정 API 완료 후 db.commit() 전.

    Args:
        order: Order 모델 인스턴스
        structured_data: order.structured_data dict (이미 수정 완료된 상태)
    """
    if not getattr(order, 'is_erp_beta', False):
        return
    schedule = (structured_data.get('schedule') or {})
    meas_raw = (schedule.get('measurement') or {}).get('date')
    cons_raw = (schedule.get('construction') or {}).get('date')
    order.erp_measurement_date = _normalize_to_yyyymmdd(meas_raw)
    order.erp_construction_date = _normalize_to_yyyymmdd(cons_raw)
```

기존 `_normalize_date_to_yyyymmdd()`(`services/erp_display.py`)를 import해서 재사용.

#### B-4. D-day SQL 필터 (2단계)

```python
# Phase 1: DB 후보군 추출 (달력일 근사치, 연휴 안전 마진 포함)
if f_alert_type == 'measurement_d4':
    cutoff = (today_kst + datetime.timedelta(days=12)).isoformat()  # 영업일 4일 → 달력일 12일 (추석/설 연휴 대비)
    _q = _q.filter(
        Order.erp_measurement_date.isnot(None),
        Order.erp_measurement_date >= today_kst.isoformat(),
        Order.erp_measurement_date <= cutoff
    )
elif f_alert_type == 'construction_d3':
    cutoff = (today_kst + datetime.timedelta(days=10)).isoformat()  # 영업일 3일 → 달력일 10일
    _q = _q.filter(
        Order.erp_construction_date.isnot(None),
        Order.erp_construction_date >= today_kst.isoformat(),
        Order.erp_construction_date <= cutoff
    )
elif f_alert_type == 'production_d2':
    cutoff = (today_kst + datetime.timedelta(days=8)).isoformat()  # 영업일 2일 → 달력일 8일
    _q = _q.filter(
        Order.erp_construction_date.isnot(None),
        Order.erp_construction_date >= today_kst.isoformat(),
        Order.erp_construction_date <= cutoff,
        stage_col.notin_(['"CONSTRUCTION"', '"시공"'])  # production_d2 조건: 시공 단계 제외
    )

# Phase 2: Python 정밀 필터 (인메모리, 후보군이 소규모)
# 기존 _erp_alerts() 호출로 measurement_d4/construction_d3/production_d2 재확인
# 1단계에서 넉넉하게 잡은 후보군 중 실제 영업일 기준 초과 건을 제거
```

`production_d2` 후보군은 날짜 조건뿐 아니라 `workflow.stage != 'CONSTRUCTION'`
조건도 함께 고려해야 한다. 후보 SQL에서 stage 조건을 같이 줄여야 Python 2차 확인 비용이 더 작아진다.

2단계 필터 덕분에 인메모리 처리 대상이 전체가 아니라 근사 후보군으로 축소된다.

**대상 파일**:
- `models.py`: 컬럼 추가
- `services/erp_sync_columns.py`: 동기화 유틸 신규 생성
- `apps/api/erp_orders_structured.py` 등 단계 변경 API: sync 호출 추가
- `apps/erp_dashboard.py`: 2단계 필터 적용
- Alembic 마이그레이션 파일 신규 생성

**기대 효과**:
- measurement_d4 / construction_d3 / production_d2 필터 시
  실질적으로 처리할 Python 인메모리 데이터가 대폭 감소
- 수만 건 중 D-day 해당 주문은 수십~수백 건 수준

**난이도**: 중간.
- 마이그레이션 필요 (신규 컬럼)
- 기존 데이터 백필 스크립트 필요 (1회성 실행)
- 동기화 호출 누락 시 데이터 불일치 위험 → 모든 일정 수정 경로 점검 필요

**백필 스크립트 예시** (`scripts/backfill_erp_date_columns.py`):
```python
# 전체 ERP Beta 주문 대상 erp_measurement_date / erp_construction_date 일괄 갱신
# 1회성 실행, 배포 직후 Railway 콘솔에서 수동 실행
```

---

### Phase C: 팀 필터(f_team) SQL화

**목표**: f_team 필터를 SQL JSONB 경로 검색으로 이동.

#### C-1. 현재 로직

```python
# apps/erp_dashboard.py:343-348
if f_team and not is_admin:
    quest = r.get('current_quest')
    if not quest:
        continue
    if f_team not in get_required_approval_teams_for_stage(r.get('stage')):
        continue
```

`get_required_approval_teams_for_stage(stage)`는 단계별 필수 승인 팀을 반환하는
정책 함수다. 단계에 따라 `['SALES']`, `['DRAWING']`, `['CS', 'SALES']` 등 반환.

#### C-2. SQL 접근법

팀 필터의 의미: "f_team이 해당 주문 단계의 필수 승인 팀에 포함되는가"

이를 SQL로 표현하면 단계별 필수 팀 목록이 정적 매핑이므로:

```python
# f_team에 해당하는 stage 코드 목록을 역산
# ⚠️ 감리 결과 반영: erp_quest_templates.json 실제 엔트리 기준으로 수정
STAGES_REQUIRING_TEAM: dict[str, list[str]] = {
    'SALES':       ['"실측"', '"MEASURE"', '"고객컨펌"', '"CONFIRM"'],
    'DRAWING':     ['"도면"', '"DRAWING"'],         # ⚠️ 아래 주의사항 참고
    'PRODUCTION':  ['"생산"', '"PRODUCTION"'],
    'CONSTRUCTION': ['"시공"', '"CONSTRUCTION"'],    # ⚠️ 아래 주의사항 참고
    'CS':          ['"주문접수"', '"RECEIVED"', '"CS"', '"완료"', '"COMPLETED"', '"AS"'],
    # ❌ AS_RECEIVED, AS_COMPLETED는 erp_quest_templates.json에 엔트리 없음
    #    → get_required_approval_teams_for_stage() 가 [] 반환
    #    → 현재 Python 필터에서도 이 단계들은 어떤 팀에도 매칭되지 않음
    #    → SQL 역산에 포함하면 동작이 변경되므로 제외
}

if f_team and not is_admin:
    target_stages = STAGES_REQUIRING_TEAM.get(f_team, [])
    if target_stages:
        stage_col = cast(Order.structured_data['workflow']['stage'], String)
        _q = _q.filter(stage_col.in_(target_stages))
    else:
        # 알 수 없는 팀 → 결과 없음
        _q = _q.filter(text('1=0'))
```

**주의 1 — CS 오버라이드**: `get_required_approval_teams_for_stage()`가 동적 로직(orderer 이름 기반
CS 오버라이드 등)을 포함하므로 역산이 완전하지 않을 수 있다.
라홈 orderer CS 오버라이드 케이스는 인메모리 2차 확인으로 보완한다.

**주의 2 — quest_exists 조건 (감리 결과 반영)**:
- 현재 `apps/erp_dashboard.py`의 `f_team`은 단순 stage 매핑이 아니라 `current_quest/quest_exists`가
  false면 제외한다.
- **DRAWING, CONSTRUCTION 단계는 light pass에서 `quest_exists = False` 강제 처리**되므로,
  현재 Python f_team 필터에서 이 단계 주문은 항상 제외된다.
- SQL로 stage만 넓히면 현재 동작과 결과 집합이 달라진다.
- 따라서 Phase C는 **동작 보존**보다 먼저 **제품 의도 확정**이 필요하다:
  - 의도 A: "DRAWING/CONSTRUCTION 단계도 f_team 필터에 포함되어야 한다" → quest_exists 강제 제거 + SQL 역산 적용
  - 의도 B: "현재 동작이 맞다 (DRAWING/CONSTRUCTION은 f_team에서 제외)" → SQL 역산에서도 제외 유지

**주의 3 — AS_RECEIVED/AS_COMPLETED 템플릿 미존재 (감리 결과 반영)**:
- `erp_quest_templates.json`에 `AS_RECEIVED`, `AS_COMPLETED` 엔트리가 없다.
- `get_required_approval_teams_for_stage('AS접수')`는 `[]`를 반환한다.
- 현재 Python 필터에서도 이 단계들은 어떤 팀에도 매칭되지 않는다.
- SQL 역산에 CS로 포함시키면 동작이 변경되므로, **현재 계획서에서는 제외**한다.
- 향후 제품 의도 확정 시 AS접수/AS완료가 CS 팀 소관이라면 quest 템플릿을 먼저 추가해야 한다.

**대상 파일**:
- `services/erp_policy.py`: `STAGES_REQUIRING_TEAM` 상수 추가
- `apps/erp_dashboard.py`: SQL 필터 적용 + 인메모리 CS 오버라이드 보완 유지

**기대 효과**: 팀 필터 시 DB가 해당 단계 주문만 반환하여 limit 문제를 줄인다.

**난이도**: 중간~높음.
- CS 오버라이드 + quest 존재 조건 + DRAWING/CONSTRUCTION 의미를 함께 검증해야 함

---

### Phase D: 장기 아키텍처 — 플랫 컬럼 전략

**목표**: 수만 건 규모에서 모든 필터·정렬·검색을 SQL로 처리.
인메모리 파이프라인 완전 제거.

#### D-1. 전체 인메모리 파이프라인 제거 조건

인메모리 파이프라인을 완전히 제거하려면:

1. **enriched 딕셔너리 생성 비용 제거**: `_erp_alerts()`, 퀘스트 조회 등을
   모두 SQL에서 수행하거나 정규화 컬럼으로 미리 계산해야 함
2. **step_stats 집계를 SQL GROUP BY로 전환**: 현재 Python 루프 기반
3. **페이지네이션을 DB OFFSET/LIMIT으로 전환**: 현재 `filtered[(page-1)*50:page*50]`
   방식은 인메모리 pagination이므로 전체 limit 내에서만 동작

#### D-2. 플랫 컬럼 추가 목록 (Order 모델)

| 컬럼명 | 타입 | 의미 | 동기화 시점 |
|--------|------|------|-------------|
| `erp_stage_code` | String(30) | workflow.stage 정규화 코드 | 단계 변경 시 |
| `erp_urgent` | Boolean | flags.urgent | urgent 수정 시 |
| `erp_measurement_date` | String(10) | schedule.measurement.date | 일정 수정 시 |
| `erp_construction_date` | String(10) | schedule.construction.date | 일정 수정 시 |
| `erp_drawing_updated_at` | DateTime | workflow.stage_updated_at (DRAWING/CONFIRM) | 단계 변경 시 |
| `erp_owner_team_code` | String(20) | 책임 팀 코드 | 단계 변경 시 |

#### D-3. step_stats SQL 집계

```sql
SELECT
    structured_data->'workflow'->>'stage' AS stage,
    COUNT(*) AS cnt
FROM orders
WHERE is_erp_beta = TRUE AND status != 'DELETED' AND deleted_at IS NULL
GROUP BY stage;
```

플랫 컬럼 도입 후:

```sql
SELECT erp_stage_code, COUNT(*) AS cnt
FROM orders
WHERE is_erp_beta = TRUE AND status != 'DELETED' AND deleted_at IS NULL
GROUP BY erp_stage_code;
```

#### D-4. 완전 서버사이드 페이지네이션

```python
# 총 건수 (COUNT 쿼리)
total_count = _q.count()

# 실제 데이터 (OFFSET + LIMIT)
orders = _q.order_by(Order.erp_stage_code, Order.id.desc()) \
           .offset((page - 1) * per_page) \
           .limit(per_page) \
           .all()
```

limit(1000) 완전 제거 가능. DB가 모든 필터·정렬·페이지네이션을 처리.

#### D-5. 플랫 컬럼 동기화 일관성 보장

모든 structured_data 수정 경로에서 `sync_erp_flat_columns(order, sd)` 호출이 필수.
누락 시 데이터 불일치. 후크 또는 SQLAlchemy event listener 방식 검토:

```python
# SQLAlchemy ORM event로 자동 동기화 (실험적)
from sqlalchemy import event

@event.listens_for(Order.structured_data, 'set')
def on_structured_data_set(target, value, oldvalue, initiator):
    if isinstance(value, dict) and getattr(target, 'is_erp_beta', False):
        sync_erp_flat_columns(target, value)
```

단, ORM event는 `flag_modified()` 패턴과 충돌 가능성이 있으므로
명시적 함수 호출 방식이 더 안전하다.

#### D-6. tsvector 전문 검색 (선택적)

f_q 텍스트 검색이 현재 `cast(Order.structured_data, String).ilike('%...%')` 방식이다.
수만 건에서 ILIKE 전체 스캔은 느리다. 장기 해결책:

```sql
ALTER TABLE orders ADD COLUMN erp_search_tsv tsvector;
CREATE INDEX idx_orders_erp_tsv ON orders USING gin(erp_search_tsv);
```

`erp_search_tsv`는 고객명, 전화, 주소, 담당자 등을 합친 tsvector 컬럼.
structured_data 변경 시 PostgreSQL trigger 또는 애플리케이션 레벨 갱신.

**난이도**: 높음. 장기 과제.

---

### Phase M: 첨부/멀티미디어 검색 별도 트랙

**목표**: 주문 검색과 별개로 첨부/미디어 메타데이터를 검색 가능한 구조로 분리한다.

#### M-1. 현재 상태

- 첨부는 `OrderAttachment` 테이블에 저장되지만, 현재 검색은 `orders` 중심이다.
- 첨부는 `order_id`를 알 때 목록/열람이 가능하지만, `filename`, `category`, `file_type`, `created_at`,
  `storage_key` 기준 검색 API는 없다.
- 대시보드는 현재 페이지 주문들에 대해 `detail_payload`로 첨부 전체를 preload한다.

#### M-2. 장기 개선 방향

1. `OrderAttachment` 메타데이터 검색 API를 별도 설계한다.
2. 주문 검색 결과에는 첨부 개수/대표 썸네일/최종 업로드 시각 같은 요약 필드만 둔다.
3. 상세 패널 첨부 목록은 필요 시 lazy-load로 전환해 payload 폭증을 막는다.
4. 이미지/동영상/도면/AS 첨부는 카테고리 필터 가능한 구조를 유지한다.

**대상 파일**:
- `models.py` (`OrderAttachment`)
- `apps/api/attachments.py`
- `services/erp_order_detail.py`
- `templates/partials/erp_dashboard_grid.html`
- `templates/partials/erp_dashboard_scripts_detail_dom.html`

**기대 효과**:
- 주문 검색과 미디어 검색을 분리할 수 있다.
- 첨부가 많은 주문에서도 화면 payload를 제어하기 쉽다.

**난이도**: 중간.

---

### Phase H: 운영 화면 / 과거 이력 Inquiry 분리

**목표**: FOMS를 "모든 과거 데이터를 한 화면에서 다 본다" 방식이 아니라,
대형 ERP처럼 **운영 화면(active)** 과 **과거 이력 조회(history inquiry)** 를 분리하는 구조로 전환한다.

#### H-1. 대형 ERP 스타일의 핵심 원칙

1. 메인 운영 화면은 **현재 처리 중인 주문** 또는 **최근 기간 주문** 중심이다.
2. 과거 완료 주문/장기 보존 데이터는 **별도 inquiry 화면**에서 조회한다.
3. inquiry 화면은 read-only 중심이며, 강한 필터(order_id, 고객명, 전화, 기간, 상태 등)를 요구한다.
4. 저장 검색(saved query) 또는 자주 쓰는 필터 preset을 둘 수 있다.
5. 첨부/미디어는 inquiry에서도 열람 가능하되, 기본은 lazy-load/read-only로 둔다.

#### H-2. FOMS 적용 방향

**운영 화면 (`/erp/dashboard`, `/erp/measurement`, `/erp/construction/dashboard`)**:
- 기본은 active dataset 중심
- 예: 미완료 상태 + 최근 N개월 완료/AS 주문만 기본 노출
- 인라인 수정/버튼/작업 큐 중심

**과거 이력 Inquiry 화면 (신규)**:
- 예: `/erp/history`
- 전체 ERP Beta 주문 + 필요 시 레거시 주문까지 read-only 조회
- 최소 1~2개 이상의 필터를 요구하여 무차별 full scan을 막음
- 고객/전화/주소/주문번호/담당자/상태/기간/첨부 유무 기준 검색
- export/print/read-only 상세 열람에 적합한 컬럼 구성

#### H-3. 기대 효과

- 메인 운영 화면이 대량 과거 데이터 때문에 오염되지 않는다.
- 사용자는 "작업할 주문"과 "과거 이력 찾기"를 다른 화면에서 명확히 구분한다.
- 대형 ERP의 운영 UX에 더 가까워진다.
- 추후 archive/retention 정책을 붙이기 쉬워진다.

#### H-4. 대상 파일

- `apps/erp_dashboard.py`
- `apps/erp_measurement_dashboard.py`
- `apps/erp_construction_page.py`
- 신규 inquiry 페이지/Blueprint (`apps/api/...` 또는 `apps/...`)
- 관련 템플릿 및 필터 UI

**난이도**: 중간~높음.

---

## 3. 실행 우선순위 및 일정

| Phase | 내용 | 우선순위 | 예상 난이도 | 데이터 규모 임계점 |
|-------|------|----------|------------|------------------|
| A-0 | ERP 메인 타일/KPI 집계 분리 | 즉시 | 중간 | 1001건~ |
| A-1 | `f_stage` SQL 전환 | 즉시 | 낮음 | 1001건~ |
| A-2 | `f_urgent` SQL 전환 (운영 DB 샘플링 선행) | 즉시 | 낮음~중간 | 1001건~ |
| A-3 | 실측/시공 화면 동일 패턴 점검 | 즉시 | 중간 | 300건~ |
| M | 첨부/멀티미디어 검색 범위 정의 + preload 최적화 | 단기 | 중간 | 첨부 누적 증가 시 |
| B | D-day 컬럼화 + 2단계 필터 | 중기 | 중간 | 3000건~ |
| H | 운영 화면 / 과거 이력 Inquiry 분리 | 중기 | 중간~높음 | 5000건~ |
| C | `f_team` SQL 전환 (제품 의도 확정 후) | 중기 | 중간~높음 | 1001건~ |
| D | 플랫 컬럼 전략 + 완전 SQL | 장기 | 높음 | 10000건~ |

---

## 4. 위험도 및 동작 보존 원칙

### 4.1 위험 요소

| 위험 | 설명 | 완화 방법 |
|------|------|----------|
| 집계 왜곡 지속 | 목록만 고치고 `kpis`/`step_stats`를 별도 분리하지 않으면 상단 숫자는 계속 잘못됨 | Phase A-0를 최우선으로 수행 |
| step_stats 집계 누락 | f_stage SQL 필터가 카운트 타일에도 적용되면 다른 단계 0으로 표시 | 집계용 쿼리와 목록용 쿼리를 분리 |
| 동기화 누락 | 플랫 컬럼이 structured_data와 불일치 | 모든 수정 API 경로 점검 + 주기적 일관성 검증 쿼리 |
| AS 버킷 매핑 오류 | AS접수/AS처리가 'AS처리' 버킷으로 합쳐지는 로직을 SQL로 잘못 표현 | `STAGES_REQUIRING_TEAM` + `STAGE_SQL_FILTER_MAP` 상수 단위 테스트 |
| JSONB cast NULL | `structured_data['flags']['urgent']` 키 없으면 NULL → cast 비교 결과 예측 | `== 'true'` 비교 시 NULL은 자동 제외되므로 안전. 단, **구현 전 운영 DB 샘플링으로 데이터 형태 확정 필수** |
| f_urgent 데이터 계약 | Python `bool()`은 `1`/`"TRUE"` 등도 truthy 처리하지만 SQL `== 'true'`는 JSON boolean만 매칭 | 운영 DB 샘플링 후 비교 조건 결정. 혼합 형태 시 `IN ('true', '1', ...)` 사용 |
| f_team CS 오버라이드 | orderer 이름 기반 CS 오버라이드 로직이 SQL 단순 매핑에서 누락 | SQL 1차 필터 후 인메모리 2차 CS 오버라이드 확인 유지 |
| f_team quest_exists 강제 | DRAWING/CONSTRUCTION은 light pass에서 `quest_exists=False` 강제 → f_team 필터에서 항상 제외됨 | SQL 역산 전 제품 의도 확정 필수 (현행 유지 vs 변경) |
| f_team AS 단계 미매칭 | AS_RECEIVED/AS_COMPLETED는 quest 템플릿에 없어 `[]` 반환 → 어떤 팀에도 매칭 안 됨 | SQL 역산에서도 제외 유지. 변경 시 quest 템플릿 먼저 추가 |
| D-day 연휴 false negative | 달력일 cutoff가 짧으면 추석/설 연휴 시 후보군 누락 → 2단계로도 복구 불가 | cutoff를 넉넉히 설정 (영업일 4일 → 달력일 12일) |
| 상세 payload 비대화 | 첨부가 많은 주문에서 `detail_payload` JSON이 과도하게 커질 수 있음 | 첨부 lazy-load 또는 대표 메타데이터만 preload |

### 4.2 동작 보존 원칙

1. **카운트 타일은 항상 `limit` 미적용 전체 활성 ERP Beta 기준**:
   각 단계 badge 숫자가 필터 여부와 무관하게 실제 전체 건수를 표시해야 한다.
2. **AS 버킷 병합 논리 유지**: `AS접수`, `AS처리` → 'AS처리' 타일로 합산,
   `AS완료` → '완료' 타일로 합산하는 로직을 SQL 매핑에서도 동일하게 표현.
3. **기존 JSONB cast 패턴 재사용**: `erp_production_page.py`의 검증된 패턴을 그대로 이식,
   새로운 JSONB 접근 방식 도입 금지.
4. **flag_modified + deepcopy 패턴 유지**: 플랫 컬럼 동기화 추가 시에도
   structured_data JSONB 수정 패턴은 기존 방식 그대로 유지.

---

## 5. 검증 방법

### 5.1 Phase A 검증

```python
# 검증 쿼리: DB와 Python 필터 결과 일치 확인
# 임시 엔드포인트 또는 Flask shell에서 실행

# SQL 필터 결과
sql_result = db.query(Order).filter(
    Order.active_filter(),
    Order.is_erp_beta.is_(True),
    cast(Order.structured_data['workflow']['stage'], String).in_(['"실측"', '"MEASURE"'])
).count()

# 인메모리 필터 결과 (기존 방식)
all_orders = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True)).all()
memory_result = sum(1 for o in all_orders if _erp_get_stage(o, o.structured_data or {}) == '실측')

assert sql_result == memory_result, f"불일치: SQL={sql_result}, Memory={memory_result}"
```

**주의**:
- 실제 검증은 `_erp_get_stage()`의 원시 단계값이 아니라 대시보드의 **버킷 규칙**
  (`AS접수`/`AS처리` → `AS처리`, `AS완료` → `완료`)까지 반영해야 한다.
- 즉 검증 코드도 대시보드와 동일한 stage bucket 함수를 공유하는 방식이 가장 안전하다.

### 5.2 Phase B 검증

```python
# 백필 후 일관성 확인
inconsistent = db.execute(text("""
    SELECT id,
           structured_data->'schedule'->'measurement'->>'date' AS sd_meas,
           erp_measurement_date,
           structured_data->'schedule'->'construction'->>'date' AS sd_cons,
           erp_construction_date
    FROM orders
    WHERE is_erp_beta = TRUE
      AND deleted_at IS NULL
      AND (
        (structured_data->'schedule'->'measurement'->>'date') != erp_measurement_date
        OR
        (structured_data->'schedule'->'construction'->>'date') != erp_construction_date
      )
    LIMIT 20
""")).fetchall()
assert len(inconsistent) == 0, f"동기화 불일치 {len(inconsistent)}건"
```

### 5.3 Phase D 검증

- 페이지네이션: page=1~N 전체 순회 시 중복/누락 없이 전체 건수와 일치하는지 확인
- 필터 조합: f_stage + f_urgent + f_alert_type 복합 필터 결과를 Phase A/B 방식과 비교

### 5.4 기능 회귀 테스트 체크리스트

- [ ] 단계 타일 클릭 → 해당 단계 주문만 표시
- [ ] 긴급 필터 → urgent 플래그 있는 주문만 표시
- [ ] D-day 필터 → 해당 영업일 내 주문만 표시 (공휴일 포함 확인)
- [ ] 팀 필터 → 해당 팀 담당 단계 주문만 표시
- [ ] 카운트 타일 → 필터와 무관하게 전체 단계별 건수 표시
- [ ] AS접수/AS처리 → 'AS처리' 타일 집계
- [ ] AS완료 → '완료' 타일 집계
- [ ] 페이지 이동 → 올바른 건수, 중복 없음

### 5.5 착수 전 체크리스트

- [ ] 현재 운영/스테이징 기준 `apps/erp_dashboard.py`의 단계 타일 수치 스냅샷 확보
- [ ] 대표 검색어 5개(고객명, 전화, 주소, 담당자, 오래된 주문 번호) 결과 스냅샷 확보
- [ ] 라홈 orderer + CS 오버라이드 사례 주문 확보
- [ ] 첨부가 많은 주문(사진/영상 다수) 3건 이상 샘플 확보
- [ ] `apps/erp_measurement_dashboard.py`, `apps/erp_construction_page.py` 현재 상한값과 체감 증상 기록

### 5.6 운영 전 체크리스트

- [ ] 단계 타일 수치가 별도 집계 쿼리와 일치
- [ ] `page=1..N` 순회 시 중복/누락 없이 전체 건수와 맞음
- [ ] `q + stage`, `q + urgent`, `stage + alert_type` 복합 필터가 재현 가능
- [ ] 첨부 미리보기, 다운로드, 썸네일 로드가 기존처럼 동작
- [ ] 첨부 많은 주문에서 상세 열기 시 payload/로딩 시간이 허용 범위인지 확인
- [ ] 실측/시공 대시보드가 메인 대시보드와 다른 기준으로 silently 누락되지 않는지 확인

---

## 6. 대형 ERP 벤치마크 (웹 조사)

### 6.1 SAP 계열

- SAP HANA의 **Data Aging**은 데이터를 `HOT`/`COLD`로 구분하고, 기본 트랜잭션 접근은 현재 데이터 중심으로 읽는다. 오래된 데이터는 별도 온도 제어 또는 별도 읽기 경로가 필요하다.  
  출처: [SAP ABAP Keyword Documentation - Data Aging in SAP HANA](https://help.sap.com/doc/abapdocu_753_index_htm/7.53/en-US/abenhana_data_aging.htm)
- SAP의 **ADK(Data Archiving)** 는 대량 데이터를 DB에서 제거하되 보고용으로는 유지한다. 쓰기 → 외부 저장(선택) → DB 삭제의 3단계가 기본이다.  
  출처: [SAP Help - Data Archiving with Archive Development Kit (ADK)](https://help.sap.com/doc/saphelp_nw74/7.4.16/en-US/4d/8c7807910b154ee10000000a42189e/content.htm?no_cache=true)

### 6.2 Oracle 계열

- Oracle Order Management는 **Order Organizer**에서 다중 탭, 다중 조건, 저장된 검색(saved query), 운영 단위(Operating Unit) 기준 검색을 제공한다.  
  출처: [Oracle Order Management User's Guide - Order Inquiry](https://docs.oracle.com/cd/E18727-01/doc.121/e13408/T335476T429678.htm)
- Oracle Receivables의 **Archive and Purge**는 온라인에서 더 이상 필요 없는 과거 거래를 archive table / file로 옮기고, 성능을 위해 live DB에서 purge한다. purge 전 검증, chain 일관성 확인, 백업 확인을 요구한다.  
  출처: [Oracle Receivables User Guide - Archive and Purge](https://docs.oracle.com/cd/E26401_01/doc.122/f10570/T355475T385615.htm)

### 6.3 Microsoft Dynamics 365 계열

- Dynamics 365 Finance and Operations는 archive job으로 **live table → history table → long-term retention** 구조를 사용한다. 과거 데이터는 read-only inquiry, OData API, Advanced Find 등 제한된 경로로 접근한다.  
  출처: [Microsoft Learn - Archive data in Dynamics 365 finance and operations apps with Dataverse](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/sysadmin/archive-data)
- Dataverse long-term retention은 **active / inactive / deleted** 3단계 수명주기를 전제로 하며, read-only retained data를 OData, Power Automate, Advanced Find로 제공한다.  
  출처: [Microsoft Learn - Dataverse long term data retention overview](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-retention-overview)
- 참고: Dynamics F&O archive 경로는 현재 **attachments 미지원**이라고 명시한다. 이는 첨부/미디어를 주문 본문과 별도 트랙으로 다뤄야 함을 시사한다.  
  출처: 동일 Microsoft Learn 문서

### 6.4 FOMS에 주는 시사점

1. **운영 데이터와 과거 데이터는 분리 관리**한다. 대형 ERP는 “모든 과거 데이터를 항상 메인 화면에서 full scan”하지 않는다.
2. **검색 가능한 필드는 정규화**한다. 대형 ERP는 저장된 쿼리, 운영 단위, 상태, 날짜, 고객, 단계 같은 typed field 중심으로 검색한다.
3. **이력/보존 데이터는 read-only inquiry 성격**으로 분리하는 경우가 많다.
4. **첨부/미디어는 별도 메타데이터와 저장소 전략**으로 다루며, 본문 주문 검색과 완전히 같은 방식으로 처리하지 않는다.

### 6.5 FOMS가 채택할 "대형 ERP 스타일" 정의

FOMS에서 말하는 **대형 ERP 스타일**은 아래와 같이 정의한다.

1. **운영 화면과 이력 화면 분리**
   메인 대시보드는 active 주문 중심, 과거 전체 조회는 inquiry 전용 화면으로 분리
2. **서버 주도 검색**
   필터, 정렬, 카운트, 페이지네이션을 서버/DB가 담당
3. **정규화된 검색 필드 우선**
   상태, 단계, 날짜, 고객, 담당자, 팀, 긴급 여부 같은 typed field 기반 검색
4. **첨부는 별도 도메인**
   주문 검색과 첨부 검색을 구분하고, 첨부는 메타데이터 + lazy-load 중심으로 관리
5. **이력 데이터는 read-only 성격**
   과거 주문 조회는 열람/감사/출력 중심, 운영 수정 흐름과 분리
6. **일관된 화면 규칙**
   메인/실측/시공/생산 화면이 서로 다른 검색 철학을 가지지 않도록 통일

### 6.6 FOMS 현재 스타일의 부합도 평가

| 항목 | 현재 상태 | 대형 ERP 스타일 부합도 |
|------|-----------|------------------------|
| 워크플로우 단계/도메인 모델 | `structured_data.workflow`, quest, 팀 승인 등 존재 | **부분 부합** |
| 메인 화면 검색/정렬/페이지네이션 | 일부 SQL + 일부 Python 인메모리 + hard limit | **불부합** |
| 상단 KPI/타일 집계 | 잘린 데이터 기준 집계 | **불부합** |
| 운영 화면 vs 과거 이력 분리 | 현재 사실상 미분리 | **불부합** |
| 첨부 저장/열람 경로 분리 | `OrderAttachment` + 파일 API 분리 존재 | **부분 부합** |
| 첨부/미디어 검색 체계 | 메타데이터 검색 부재 | **불부합** |
| 화면 간 일관성 | 메인/실측/시공이 서로 다른 상한과 처리 방식 사용 | **불부합** |

**총평**:
- 현재 FOMS는 **중소형 ERP Beta 스타일**에는 가깝다.
- 그러나 **대형 ERP 스타일과는 아직 부분 부합 수준**이다.
- 특히 데이터 관리 관점에서는 `도메인 모델`은 어느 정도 맞지만,
  `검색`, `집계`, `active/history 분리`, `미디어 검색`, `화면 일관성`은 아직 미달이다.

---

## 7. 관련 파일 목록

| 파일 | 변경 Phase | 변경 유형 |
|------|-----------|----------|
| `apps/erp_dashboard.py` | A-0, A, B, C, D | 수정 |
| `apps/erp_measurement_dashboard.py` | A-3 | 점검/수정 후보 |
| `apps/erp_construction_page.py` | A-3 | 점검/수정 후보 |
| `apps/erp_production_page.py` | 참고 | 선행 레퍼런스 |
| `services/erp_policy.py` | A, C | 상수 추가 |
| `models.py` | B, D | 컬럼 추가 |
| `services/erp_sync_columns.py` | B, D | 신규 생성 |
| `apps/api/erp_orders_structured.py` | B, D | 동기화 호출 추가 |
| `apps/api/attachments.py` | M | 첨부 검색/열람 API 확장 후보 |
| `apps/api/files.py` | M | 파일 열람 경로 유지 |
| `services/erp_order_detail.py` | M | detail preload / lazy-load 후보 |
| `migrations/versions/xxxx_add_erp_date_columns.py` | B | 신규 마이그레이션 |
| `scripts/backfill_erp_date_columns.py` | B | 신규 백필 스크립트 |
| `migrations/versions/xxxx_add_erp_flat_columns.py` | D | 신규 마이그레이션 |

---

## 8. 결론

현재 limit(1000) 문제는 **Phase A-0 + Phase A (집계 분리 + f_stage/f_urgent SQL 전환)** 까지
묶어야 단기간에 정확도 문제를 실질적으로 줄일 수 있다. 코드 변경 범위가 상대적으로 좁고
`erp_production_page.py`에 검증된 패턴이 있어 즉시 적용 가능하다.

현재 FOMS 스타일은 **대형 ERP 스타일에 완전 부합하지 않는다**. 정확히는
**도메인/워크플로우 모델은 일부 부합하지만, 검색/집계/이력 분리/첨부 검색은 미부합** 상태다.

Phase B는 마이그레이션이 필요하지만 D-day 필터 정확도와 성능 모두
개선되므로 3000건 규모 도달 전 완료 목표로 계획한다.

대형 ERP 스타일을 목표로 한다면, 단순히 메인 대시보드 필터를 SQL화하는 것만으로는 부족하다.
반드시 **Phase H(운영 화면 / 과거 이력 Inquiry 분리)** 를 함께 가져가야 한다.

Phase C는 팀 필터의 현재 의미(`quest_exists`, CS 오버라이드, DRAWING/CONSTRUCTION 처리)를
먼저 고정한 뒤 진행해야 한다. 그렇지 않으면 "개선"이 아니라 동작 변경이 될 수 있다.

멀티미디어 검색/대용량 첨부 최적화는 별도 Phase M으로 분리한다. 현재는 **열람 경로는 존재하지만,
검색 체계는 부재**하기 때문이다.

장기적으로는 Phase D(플랫 컬럼 + 완전 SQL + 검색 전용 컬럼/tsvector)로 가야 한다. 이는
대형 ERP들이 공통으로 택하는 방향과도 일치한다. 운영 화면은 active data 중심, 과거/보존 데이터는
별도 inquiry/retention 전략으로 분리하는 것이 맞다.
