# FOMS Phase 4 날짜 검색 구조 정상화 Spec
> 작성일: 2026-03-09 | 상태: 🟢 승인됨 (진행중)

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
현재 `Order.measurement_date`, `Order.scheduled_date`의 CSV 문자열과 ERP Beta 기능의 `JSONB` 형태(`structured_data.schedule...`, `structured_data.items...`)로 흩어져 있는 날짜 데이터를 단일 정규화 테이블인 `order_schedule_dates`로 분리하여 통합 관리합니다. 이를 통해 느리고 부정확한 텍스트 기반 LIKE 검색(예: `cast(structured_data, String).ilike`)을 완전 제거하고, 빠르고 정확한 날짜 기반 인덱스 쿼리가 가능해집니다.

### 1.2 기능 요구사항
1. 새로운 독립 테이블 `order_schedule_dates` 생성
2. `orders` 테이블에 CRUD가 발생할 때마다, 해당 주문에 있는 모든 날짜 데이터를 파싱하여 추출하고 신규 테이블에 동기화(upsert/replace)하는 메커니즘 구축
3. 실측/시공/출고/지도 등 모든 날짜 검색 대시보드의 기존 SQLAlchemy 필터 로직을 새로운 테이블에 JOIN 하는 방식으로 교체
4. 과거 데이터 전체를 신규 테이블로 밀어넣는 "데이터 백필(Backfill)" 마이그레이션 스크립트 작성 (안전하게 중단/재작업이 가능하도록 Idempotent하게 구성)

### 1.3 예외/제약 조건
- 기존 컬럼(`measurement_date`, `scheduled_date` 등)과 JSONB 데이터는 삭제하지 않고 **읽기 전용이나 원본 보존용**으로 그대로 둡니다. (문제 발생 시 롤백 보장)
- 검색 성능 보장을 위해 `order_schedule_dates` 테이블은 `(kind, date, order_id)` 복합 인덱스를 가집니다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `models.py` | `OrderScheduleDate` 클래스 추가 및 `Order` 모델과 1:N 관계(`dates`) 설정 |
| `services/order_date_sync.py` (신규) | 주어진 `Order` 객체에서 모든 날짜를 추출해 `OrderScheduleDate` 레코드들을 갱신하는 공통 함수 구현 |
| `apps/api/erp_measurement.py`, `apps/api/erp_map.py`, `apps/api/orders.py`, `apps/erp_shipment_page.py`, `apps/erp_measurement_dashboard.py` | 기존 `cast/ilike`/`.like` 등 텍스트 검색 쿼리를 `OrderScheduleDate` 조인 쿼리로 변경 |
| `scripts/backfill_phase4_dates.py` (신규) | 전체 기존 `Order`들의 날짜를 파싱해 일괄 INSERT 처리하는 백필 스크립트 |

### 2.2 아키텍처 방향
- **데이터 흐름:** 사용자가 문서를 저장(Update) -> 파일/DB 저장이 일어날 때 마지막 단계로 `sync_order_dates(order_id)` 함수를 호출하여 뷰잉용 날짜 테이블을 별도 세팅 (CQRS 관점의 Read Model 분리).
- **왜 Event Listener(Trigger)를 쓰지 않는가:** JSONB 파싱이나 CSV 콤마 분리 등 Python 레벨의 복잡한 정규화 로직이 들어가므로 DB Trigger보다 App Application 레이어의 Sync 함수가 안전하고 테스트하기 좋습니다. -> **변경사항: SQLAlchemy의 Event Listener(before_flush)를 활용하여 투명한 동기화 처리 적용 완료**

### 2.3 의존성 및 영향 범위
- **조회 성능:** 텍스트 풀스캔, 인덱스 패스 불가 쿼리들이 명시적인 `JOIN + Index Range Scan`으로 바뀌므로 실측/출고 대시보드의 로딩 시간이 극단적으로 줄어듭니다.
- **영향:** 거의 모든 검색 기능(Beta 활성, 일반 활성 모두)이 신규 테이블로 전환됩니다. 마이그레이션 도중 누락되는 날짜 포맷이 없도록 정규표현식 및 파서(Parser)를 고도화해야 합니다.

## 3. Steps — 실행 단계
- [x] Step 1: `models.py`에 `OrderScheduleDate` 테이블 정의 (`id`, `order_id`, `kind`, `date`, `source`, `item_index`) 및 DB 인덱스 설계 반영
- [x] Step 2: 통합 날짜 파서 및 동기화기 `services/order_date_sync.py` 작성 + 테스트 코드로 검증
- [x] Step 3: 백필 스크립트 작성 및 로컬 개발 환경에서 전체 Migration 실행 후 개수 통계 검증
- [x] Step 4: 주문 정보 저장 API(Update, Insert, ERP Beta 등)에 Step 2의 동기화 함수 연동 적용 (`app_init.py`의 `before_flush`로 중앙 집중화 적용 완료)
- [x] Step 5: (일부) 각 대시보드의 기존 SQLAlchemy `get_query()` 필터를 신규 JOIN 쿼리로 교체 (동작 1:1 보존 검증 병행) - *`erp_measurement_dashboard.py`, `erp_shipment_page.py` 완료*
- [ ] Step 6: 나머지 API들 (`erp_map.py`, `erp_measurement.py`) 필터 교체

## 4. 검증 기준
- [ ] `python -c "import app"` 통과 및 테이블 속성 정상 생성
- [ ] Phase 4 마이그레이션 전/후의 `실측/시공/지도/출고` 대시보드 리스트의 목록이 100% 동일함 증명
- [ ] `EXPLAIN ANALYZE` 시 더 이상 `cast(structured_data AS varchar)`와 같은 병목 오버헤드가 없음을 확인

## 5. 참고 자료
- 기 수립된: `docs/plans/performance-optimization-plan-v2.md` Phase 4 전략 
- 근본 문제: CSV로 여러 날짜를 저장하는 기존 관습 + JSONB 도입으로 인한 계층 중복 조회 부담
