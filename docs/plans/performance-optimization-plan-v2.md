# FOMS Production 성능 최적화 계획서 V2

**작성일:** 2026-03-09  
**기준:** `docs/plans/performance-optimization-plan.md` 재검토 후 소스 기준으로 V2 재작성  
**상태:** 소스 코드 1:1 더블체크 완료 / 실행 가능안만 남긴 수정본  
**목표:** Production 환경의 체감 성능을 개선하되, 페이지 의미와 데이터 노출 범위를 바꾸지 않는다.

---

## 1. V2에서 바로잡은 점

V1은 병목 진단 자체는 대체로 맞았지만, 일부 제안이 현재 코드의 의미를 바꾸거나 결과를 누락시킬 수 있었다.  
V2는 아래 원칙으로 다시 정리했다.

- 성능 개선이 **데이터 누락**으로 바뀌는 제안 제거
- **현재 쿼리 의미 보존**이 확인된 항목만 단기 실행안으로 유지
- 인덱스 추가 전에 **살아남을 쿼리 형태를 먼저 정리**
- `String CSV 날짜 + JSONB 내부 날짜` 문제는 **구조적 원인**으로 분리

---

## 2. 소스 기준 근본 원인 요약

### 2.1 요청 전역 공통 오버헤드

| ID | 근본 원인 | 소스 | 영향 |
|---|---|---|---|
| R-1 | 요청당 사용자 조회 중복 | `app.py:144-156`, `services/context_processors.py:43-52`, `services/context_processors.py:86-97` | 거의 모든 페이지 |
| R-2 | `menu_config.json` 매 요청 파일 I/O | `services/menu_config.py:6-14`, `services/context_processors.py:88` | 거의 모든 HTML 응답 |
| R-3 | Production에서도 `TEMPLATES_AUTO_RELOAD = True` | `app.py:99-106`, `app.py:121-123`, `app.py:414` | 거의 모든 HTML 응답 |
| R-4 | 전역 디버그 로그 잔존 | `templates/layout.html` 전역 39건, `templates/map_view.html` 6건 | 브라우저 렌더링/디버깅 비용 |

### 2.2 데이터/쿼리 구조 병목

| ID | 근본 원인 | 소스 | 영향 |
|---|---|---|---|
| R-5 | 날짜가 `String CSV`와 `JSONB`에 혼재 | `models.py:28`, `models.py:35`, `models.py:78`, `apps/erp_measurement_dashboard.py:54-71`, `apps/erp_shipment_page.py:68-81` | 실측/출고/지도/캘린더 |
| R-6 | `cast(structured_data, String).ilike(...)` 전역 사용 | `apps/erp_measurement_dashboard.py:48,141,156`, `apps/erp_shipment_page.py:115,312,313`, `apps/erp_as_page.py:32` | ERP Beta 검색 전반 |
| R-7 | 첨부파일 수 집계가 전체 테이블 `GROUP BY`로 반복 | `apps/erp_dashboard.py:67`, `apps/erp_production_page.py:63`, `apps/erp_construction_page.py:64` | ERP/생산/시공 대시보드 |
| R-8 | 실측 대시보드 과다 로드 + N+1 | `apps/erp_measurement_dashboard.py:163-171`, `apps/erp_measurement_dashboard.py:250-254` | 실측 대시보드 |
| R-9 | 출고 대시보드 분기별 후보 로드 비용 큼 | `apps/erp_shipment_page.py:159-189`, `apps/erp_shipment_page.py:268-334` | 출고 대시보드 |
| R-10 | 실측 동선 API가 Beta 주문을 과도하게 끌어옴 | `apps/api/erp_measurement.py:193-228` | 실측 동선 API |
| R-11 | 지도 API가 요청 중 동기 지오코딩 실행 | `apps/api/erp_map.py:512-569` | 지도 진입 시 치명적 |
| R-12 | nearby API가 넓은 후보군을 메모리로 끌고 옴 | `apps/api/orders.py:114-123`, `apps/api/orders.py:233-285` | 주변 주문 검색 |

---

## 3. 현재 코드와 충돌해서 제외한 제안

아래 항목은 V1에 있었지만, 그대로 구현하면 의미가 바뀌거나 누락을 만들 수 있어 V2 단기 실행안에서 제외한다.

1. 출고 대시보드 단일 날짜 분기에서 `.all()`을 `.limit(500).all()`로 바꾸는 안  
   이유: `apps/erp_shipment_page.py:317-320`에서 Python 후처리로 실제 날짜 매칭을 다시 하므로, 앞단 LIMIT은 결과 누락 위험이 있다.

2. 지방/자가실측 대시보드와 캘린더 API에 일괄 `limit(500)`를 넣는 안  
   이유: 현재 `templates/regional_dashboard.html`, `templates/self_measurement_dashboard.html`, `templates/calendar.html`에는 pagination 계약이 없다. 이건 최적화가 아니라 표시 누락이 될 수 있다.

3. 수도권 대시보드 8개 쿼리를 `created_at desc limit 500` 단일 쿼리로 합치는 안  
   이유: `apps/dashboards.py:185-241`의 각 카드가 서로 다른 조건과 정렬 의미를 가진다. 한 번에 합치면 의미 보존이 안 된다.

4. JSONB GIN 인덱스와 `@>`만으로 현재 날짜 검색을 바로 대체하는 안  
   이유: 현재 Beta 날짜는 `schedule.*.date`만이 아니라 `items[*].measurement_date`, `items[*].construction_date`에도 있고, 일부는 CSV 문자열이다. 단일 containment 전략으로는 충분하지 않다.

---

## 4. V2 실행 원칙

1. **동작 보존 우선**
   - 응답 형식, 카드 개수, 날짜 필터 의미, 페이지 노출 범위를 바꾸지 않는다.

2. **가짜 최적화 금지**
   - LIMIT으로 숨기는 방식, broad query 후 임의 축소, “인덱스만 추가하면 된다” 식의 계획은 금지한다.

3. **쿼리 구조 정리 후 인덱스**
   - 먼저 살아남을 쿼리를 정리하고, 그다음 인덱스를 추가한다.

4. **구조 문제는 구조로 푼다**
   - `String CSV 날짜 + JSONB 날짜`는 장기적으로 정규화해야 한다.

5. **모든 Phase는 측정 가능해야 한다**
   - 최소 `python -c "import app; print('APP_OK')"` 확인
   - 주요 페이지 로드 비교
   - 필요 쿼리 `EXPLAIN ANALYZE` 확인

---

## 5. Phase별 실행 계획

### Phase 0. 공통 요청 오버헤드 제거

**목적:** 모든 페이지에 누적되는 공통 낭비를 먼저 제거한다.  
**위험도:** 낮음  
**의미 변경:** 없음

#### 0-1. `g.current_user` 단일 조회로 통합

- 대상
  - `app.py:144-156`
  - `services/context_processors.py:43-52`
  - `services/context_processors.py:86-97`
- 수정 방향
  - `before_request`에서 사용자 객체를 한 번만 조회해 `g.current_user`에 저장
  - `inject_status_list`, `inject_menu`, 시공팀 제한 로직은 모두 `g.current_user`를 우선 사용
- 기대 효과
  - 요청당 User SELECT 2~3회 제거

#### 0-2. `menu_config.json` 모듈 캐시 도입

- 대상
  - `services/menu_config.py:6-14`
  - `services/context_processors.py:88`
  - `apps/admin.py:35-38`
- 수정 방향
  - `load_menu_config()`에 메모리 캐시 추가
  - 관리자 저장 시 캐시 무효화 또는 파일 mtime 기반 재로드
- 기대 효과
  - 모든 HTML 요청의 파일 접근 제거

#### 0-3. Template auto reload를 현재 앱 환경 규칙에 맞게 조건부화

- 대상
  - `app.py:99-106`
  - `app.py:121-123`
  - `app.py:414`
- 수정 방향
  - `FLASK_ENV` 문자열 하나만 보지 말고, 이미 쓰는 `_is_production`, `_is_railway` 기준에 맞춰 disable
  - 개발 환경 즉시 반영은 유지
- 기대 효과
  - Production 요청당 템플릿 mtime 체크 제거

#### 0-4. Production 디버그 로그 정리

- 대상
  - `templates/layout.html`의 전역 Socket.IO 로그 39건
  - `templates/map_view.html`의 로그 6건
- 수정 방향
  - 기본은 제거
  - 필요한 경우 `window.FOMS_DEBUG === true`에서만 출력
- 기대 효과
  - 브라우저 콘솔 직렬화 비용 제거

#### 0-5. 첨부파일 수 집계를 현재 화면 주문 ID 범위로 제한

- 대상
  - `apps/erp_dashboard.py:67`
  - `apps/erp_production_page.py:63`
  - `apps/erp_construction_page.py:64`
- 전제
  - `models.py:92`의 `order_attachments.order_id` 인덱스는 이미 있다.
- 수정 방향
  - 현재 화면에 표시할 주문 ID를 먼저 구한 뒤
  - `WHERE order_id IN (...) GROUP BY order_id`로 집계 범위를 제한
  - 세 대시보드 모두 같은 패턴으로 통일
- 기대 효과
  - 전체 첨부 테이블 풀스캔형 집계 제거

#### Phase 0 검증

- `python -c "import app; print('APP_OK')"`
- ERP/생산/시공/실측/출고/지도 주요 화면 수동 로드
- 관리자 메뉴 수정 후 메뉴 반영 확인
- 브라우저 콘솔에서 layout/map_view 전역 디버그 로그 기본 비활성 확인

---

### Phase 1. 의미 보존형 대시보드/엔드포인트 정리

**목적:** 결과 집합을 바꾸지 않으면서, 과다 로드와 N+1을 줄인다.  
**위험도:** 중간  
**의미 변경:** 없음

#### 1-1. 실측 대시보드: `query`와 `base_query`는 유지, 로드 폭만 줄임

- 대상
  - `apps/erp_measurement_dashboard.py:92-171`
- 핵심 사실
  - `all_rows`는 날짜 필터가 적용된 `query` 기반
  - `panel_orders`는 날짜 필터 없는 `base_query` 기반
  - 둘은 역할이 다르므로 합치지 않는다.
- 수정 방향
  - `panel_orders`는 `load_only` 또는 필요한 컬럼만 가져오는 경량 로드로 축소
  - `extract_all_measurement_dates()`와 담당자 필터에 필요한 필드만 유지
  - `all_rows`도 동일하게 불필요한 대형 컬럼 로드를 피할 수 있는지 별도 검토
- 기대 효과
  - ORM 객체 생성 비용과 메모리 사용량 감소

#### 1-2. 실측 대시보드 N+1 제거

- 대상
  - `apps/erp_measurement_dashboard.py:250-254`
  - `services/erp_product_items.py`
- 수정 방향
  - 화면에 표시되는 주문 ID를 모은 뒤 제품 항목을 한 번에 배치 로드
  - `build_product_items_for_order(db, order)` 반복 호출을 배치 함수로 대체
- 기대 효과
  - 최대 수백 회 추가 SELECT 제거

#### 1-3. 출고 대시보드: 분기별 의미는 유지하고 폭만 줄임

- 대상
  - `apps/erp_shipment_page.py:159-189`
  - `apps/erp_shipment_page.py:268-334`
- 핵심 사실
  - `panel_orders`
  - 범위 검색
  - 단일 날짜 검색
  - 전체 기간 검색
  - 이 네 경로는 의미가 다르다.
- 수정 방향
  - `panel_orders`는 `extract_all_construction_dates()`와 배정 정보 계산에 필요한 필드만 경량 로드
  - 단일 날짜 분기(`291-320`)는 **앞단 LIMIT 추가 금지**
  - 전체 기간 분기(`324-334`)의 현재 `limit(500)`는 화면 계약을 확인한 뒤 유지 여부만 검토
- 기대 효과
  - 메모리 사용량 감소, 의미 보존

#### 1-4. 실측 동선 API Beta 과다 조회 수정

- 대상
  - `apps/api/erp_measurement.py:193-228`
- 현재 문제
  - 날짜 필터가 있을 때 Beta 쪽이 `structured_data.isnot(None)`만으로 넓게 잡힌다.
- 수정 방향
  - 레거시 주문은 SQL 날짜 필터 유지
  - Beta 주문은 별도 후보 쿼리로 분리
  - Beta 후보는 경량 컬럼만 읽고 `extract_all_measurement_dates()`와 동일 규칙으로 정확 매칭
  - 즉, broad OR 조건을 없애고 레거시/베타 흐름을 분리
- 기대 효과
  - 날짜 무관 Beta 대량 로드 제거

#### 1-5. `bulk_update` N+1 제거

- 대상
  - `apps/api/orders.py:775-817`
- 수정 방향
  - `for oid in order_ids` 반복 `.first()` 제거
  - `Order.id.in_(order_ids)` 한 번으로 배치 조회 후 메모리에서 매핑
- 기대 효과
  - 다중 선택 상태 변경 시 SELECT 수 급감

#### 1-6. 캘린더 API는 결과 수를 줄이지 말고 payload를 줄임

- 대상
  - `apps/api/orders.py:367-372`
  - `templates/calendar.html`
- 수정 방향
  - 기본 `limit=2000`은 UI 계약 확인 전까지 유지
  - 대신 FullCalendar에 실제 필요한 필드 중심으로 projection 축소 검토
  - `start/end` 범위가 항상 들어오는 호출 경로 기준으로 불필요 컬럼 제외
- 기대 효과
  - 누락 없이 응답 크기 축소

#### Phase 1 검증

- 날짜 필터 있는/없는 실측 대시보드 결과 개수 비교
- 출고 대시보드 범위/단일 날짜/전체 기간 결과 개수 비교
- 실측 동선 API 응답 건수와 실제 지도 표시 건수 비교
- 다중 선택 상태 변경 기능 정상 동작 확인

---

### Phase 2. 인덱스는 남는 쿼리에만 추가

**목적:** 쿼리 구조를 정리한 뒤 실제로 의미 있는 인덱스만 추가한다.  
**위험도:** 낮음~중간  
**의미 변경:** 없음

#### 2-1. 바로 추가 가능한 인덱스

다음은 현재 패턴과 충돌이 적고, 의미 보존이 쉬운 후보들이다.

1. 부분 인덱스: 지방 대시보드용
   - 조건 예시: `status <> 'DELETED' AND is_regional = true`
   - 정렬 축 예시: `id DESC`

2. 부분 인덱스: 자가실측 대시보드용
   - 조건 예시: `status <> 'DELETED' AND is_self_measurement = true`
   - 정렬 축 예시: `id DESC`

3. 부분 인덱스: ERP Beta 활성 주문용
   - 조건 예시: `status <> 'DELETED' AND is_erp_beta = true`
   - 용도: Beta 중심 패널/검색 후보 축소

4. 선택적 trigram 인덱스
   - 대상: `measurement_date`, `scheduled_date`
   - 전제: `pg_trgm` 사용 가능 + 실제 `ILIKE '%...%'`가 계속 남는 경우만
   - 주의: 이건 `String CSV 날짜`의 완전한 해결책이 아니다. 임시 완화책이다.

#### 2-2. 지금 추가하면 안 되는 인덱스

1. JSONB GIN 인덱스를 “현재 날짜 검색 해법”으로 바로 도입
2. 저카디널리티 boolean 단독 인덱스
3. 쿼리 구조가 아직 바뀔 예정인 곳에 선행 인덱스 남발

#### 2-3. 인덱스 검증 방식

- 각 인덱스는 추가 전/후 `EXPLAIN ANALYZE` 비교
- Railway PostgreSQL에서 `pg_trgm` 사용 가능 여부 사전 확인
- Alembic 마이그레이션에 `downgrade()` 포함

---

### Phase 3. 지도 및 무거운 API 정리

**목적:** 사용자가 가장 느리다고 체감하는 지도/근접 검색 병목을 제거한다.  
**위험도:** 중간  
**의미 변경:** 없음

#### 3-1. 지도 API에서 동기 지오코딩 제거

- 대상
  - `apps/api/erp_map.py:512-569`
- 수정 방향
  - 요청 중 `sync_batch`로 카카오 API를 직접 때리지 않음
  - 좌표 없는 주문은 `pending` 상태로 즉시 반환
  - 백그라운드 큐 `enqueue_geocode_order_address`에 전부 위임
  - 이미 있는 map polling(`templates/map_view.html`)은 그대로 활용
- 기대 효과
  - 지도 첫 진입 응답 시간 급감
  - Gunicorn 워커 블로킹 해소

#### 3-2. 지도 API 내부 코드 정리

- 대상
  - `apps/api/erp_map.py`
- 수정 방향
  - `format_date()` 루프 밖으로 이동
  - 중복된 날짜 필터 빌더를 공통 함수로 추출
- 기대 효과
  - 유지보수성 개선, 반복 비용 제거

#### 3-3. nearby API는 “2500 -> 500” 식 축소 대신 후보군 정의를 개선

- 대상
  - `apps/api/orders.py:114-123`
  - `apps/api/orders.py:233-285`
- 수정 방향
  - 반환 계약은 계속 최종 5건 유지
  - 하지만 첫 후보군은 필요한 컬럼만 읽도록 축소
  - 날짜/상태 기반 SQL 조건을 먼저 다듬고, 주소 기반 SQL prefilter를 추가할 수 있는지 검토
  - `2500` 상수는 후보군 질이 개선된 뒤에만 재평가
- 금지
  - 근거 없이 LIMIT만 낮추는 것

#### Phase 3 검증

- 지도 첫 진입 시간 비교
- 좌표 없는 주문이 비동기 후 갱신되는지 확인
- nearby 결과 Top 5 정합성 비교

---

### Phase 4. 날짜 검색 구조 정상화

**목적:** 현재 성능 문제의 가장 깊은 원인인 `String CSV 날짜 + JSONB 내부 날짜` 구조를 정리한다.  
**위험도:** 높음  
**의미 변경:** 없음  
**성격:** 구조 개선 / 중장기

#### 4-1. 왜 이 Phase가 필요한가

현재는 아래가 동시에 존재한다.

- `orders.measurement_date` 문자열 CSV
- `orders.scheduled_date` 문자열 CSV
- `structured_data.schedule.measurement.date`
- `structured_data.schedule.construction.date`
- `structured_data.items[*].measurement_date`
- `structured_data.items[*].construction_date`

이 구조 때문에:

- 정확한 SQL 날짜 필터링이 어렵고
- `cast(JSONB, String).ilike(...)` 같은 비싼 우회가 생기고
- 화면별 helper 함수가 서로 다른 경로를 뒤져야 한다.

#### 4-2. 권장 구조

`order_schedule_dates` 같은 보조 정규화 테이블을 신설한다.

예시 컬럼:

- `id`
- `order_id`
- `kind` (`measurement` / `construction`)
- `date`
- `source` (`legacy_column` / `beta_schedule` / `beta_item`)
- `item_index` nullable

#### 4-3. 동기화 방식

1. 레거시 주문 저장 시 동기화
2. ERP Beta `structured_data` 저장 시 동기화
3. 초기 마이그레이션으로 기존 주문 전체 백필

#### 4-4. 이 Phase 완료 후 가능한 것

1. 실측/출고/지도의 날짜 SQL 필터를 정확한 `=` / range 조회로 전환
2. `cast(structured_data, String).ilike(...)` 제거
3. `order_schedule_dates(kind, date, order_id)` 인덱스로 정확한 날짜 탐색
4. 일부 대시보드 통합/단순화 재검토

---

## 6. 구현 우선순위

### 바로 착수

1. Phase 0 전체
2. Phase 1-2 실측 대시보드 N+1 제거
3. Phase 1-4 실측 동선 API Beta 과다 조회 수정
4. Phase 3-1 지도 동기 지오코딩 제거

### 착수 전 추가 설계 필요

1. Phase 2 인덱스 상세 설계
2. Phase 3-3 nearby 후보군 축소 방식
3. Phase 4 날짜 정규화 테이블 설계 및 백필 전략

### 지금 하면 안 됨

1. 단일 날짜 출고 검색 앞단 LIMIT 추가
2. pagination 없는 화면에 일괄 LIMIT 추가
3. JSONB GIN만으로 날짜 검색을 끝내려는 설계
4. 수도권 대시보드 8중 쿼리의 무리한 단일 쿼리 통합

---

## 7. 성공 기준

1. 실측/출고/지도 주요 화면의 결과 개수와 의미가 기존과 동일할 것
2. 요청당 중복 사용자 조회 제거가 확인될 것
3. 메뉴 파일 I/O가 요청당 발생하지 않을 것
4. 첨부파일 수 집계가 현재 화면 주문 범위로 제한될 것
5. 지도 진입 시 동기 지오코딩 대기가 없어질 것
6. `python -c "import app; print('APP_OK')"` 성공
7. DB 마이그레이션은 `upgrade` / `downgrade` 모두 가능할 것

---

## 8. 검증 체크리스트

### 공통

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] Railway staging 또는 동등 환경에서 주요 페이지 smoke test

### 실측

- [ ] 날짜 필터 없음 / 단일 날짜 / 범위 날짜 결과 건수 비교
- [ ] 패널 수치와 테이블 목록의 의미 일치 확인

### 출고

- [ ] 범위 / 단일 날짜 / 전체 기간 분기별 결과 건수 비교
- [ ] AS 포함 로직과 담당자 필터 유지 확인

### 지도

- [ ] 좌표 없는 주문 포함 상태에서도 첫 응답이 빠르게 끝나는지 확인
- [ ] 비동기 좌표 채움 후 지도 갱신 확인

### 첨부

- [ ] ERP / 생산 / 시공 대시보드 첨부 개수 일치 확인

---

## 9. 참조 소스

- `app.py`
- `services/context_processors.py`
- `services/menu_config.py`
- `models.py`
- `apps/erp_measurement_dashboard.py`
- `apps/erp_shipment_page.py`
- `apps/api/erp_measurement.py`
- `apps/api/erp_map.py`
- `apps/api/orders.py`
- `apps/erp_dashboard.py`
- `apps/erp_production_page.py`
- `apps/erp_construction_page.py`
- `apps/dashboards.py`
- `templates/layout.html`
- `templates/map_view.html`
- `templates/calendar.html`
- `templates/regional_dashboard.html`
- `templates/self_measurement_dashboard.html`

