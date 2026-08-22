# AS 대시보드 status 독립화 (AS-AXIS-01) — 설계서

> 상태: **승인·구현 완료(스테이징 검증 완료, 운영 승격 대기)**. 실측으로 바뀐 설계 2건은 §11 에 기록.
> 계기: 2026-08-14 일괄 완료처리 사고 — AS 주문 55건이 AS 대시보드에서 증발.

## 1. 문제

AS 대시보드의 목록·카운트·지도 술어는 **`orders.status` 컬럼 단독**이다.

```python
# foms/services/as_dashboard_helpers.py:276
def _erp_as_incomplete_condition():
    return or_(Order.status == 'AS', Order.status == 'AS_RECEIVED',
               and_(Order.status == 'AS_COMPLETED', or_(Order.as_completed_date.is_(None),
                                                        Order.as_completed_date == '')))
```

그런데 `order.status` 는 이 코드베이스에서 **canonical 축이 아니다**. `as_cycle_service.py`
모듈 독스트링이 명시한다: AS 축의 정본은 `structured_data['as_lifecycle']` 이고,
`order.status` 는 `legacy_status_projection()`(AS > logistics > main)으로 **재계산되는 overlay
projection** 이다.

즉 지금 구조는 "정본은 as_lifecycle, 화면은 파생값 status 로 조회"다. 파생값을 아무나 덮으면
정본이 멀쩡해도 화면에서 사라진다 — 그게 8/14 사고의 구조적 원인이다. 일괄 변경 가드
(`as_overlay_status` 제외 규칙, 운영 `63737e91`)는 **한 경로를 막은 것**이지 구조를 고친 게 아니다.
status 를 쓰는 경로는 앞으로도 늘어난다(엑셀 임포트·백필·외부 연동).

## 2. 현 상태 실측 (운영 DB, 2026-08-17 조회)

| 항목 | 건수 |
|---|---|
| 전체 주문(미삭제) | 3,551 |
| `status` 가 AS 계열 | 566 |
| `structured_data.as_lifecycle` 보유 | **60** |
| AS status 인데 lifecycle 없음(레거시) | **506** |
| lifecycle 있는데 AS status 아님 | 0 |
| `as_received_date` 보유 | 528 |

읽는 방식은 이미 정합 헬퍼가 있다: `state_axes.read_as_status(order)` — lifecycle 우선, 없으면
legacy status 폴백. **문제는 이게 파이썬 함수라 SQL 술어로 못 쓴다는 것**이다(목록·카운트는 SQL).

`orders` 테이블에 `status` 단독 인덱스도 없다(현 인덱스 11종 중 status 전용 없음).

## 3. 설계 (권장안 A): AS 축 플랫 투영 컬럼

`erp_stage_code`·`erp_measurement_date` 와 **같은 계열**의 플랫 투영 컬럼을 하나 더 만든다.
이 저장소가 이미 쓰는 관례라 새 개념을 도입하지 않는다.

### 3.1 스키마

```sql
ALTER TABLE orders ADD COLUMN as_axis_status VARCHAR(16);  -- NULL = AS 이력 없음
CREATE INDEX ix_orders_as_axis_status ON orders (as_axis_status)
  WHERE as_axis_status IS NOT NULL;                        -- 부분 인덱스(AS 행만)
```

값 도메인은 `state_axes.AS_VALUES` 와 동일: `RECEIVED` / `IN_PROGRESS` / `COMPLETED`
(AS 이력 없음 = `NULL`, `NONE` 문자열 금지 — 부분 인덱스가 커진다).

### 3.2 쓰기(동기화) 지점

`sync_erp_flat_columns(order, structured_data)` 에 한 줄 추가:

```python
order.as_axis_status = derive_as_axis_status(order, structured_data)  # None|RECEIVED|IN_PROGRESS|COMPLETED
```

`derive_as_axis_status` 는 **읽기 SSOT 를 그대로 쓴다**:

1. `as_lifecycle` 이 있으면 `read_as_status()` 결과(NONE → None)
2. 없으면 legacy 유도: `status` 가 AS 계열이면 그 매핑, 아니면
   `as_completed_date` 있으면 `COMPLETED`, `as_received_date` 있으면 `RECEIVED`, 아니면 None

이 함수가 백필·동기화·테스트에서 공유되는 단일 유도 규칙이다(복제 금지).

### 3.3 백필

`tools/ops/backfill_as_axis_status.py` (기존 backfill 도구 관례: 배치·재시작 가능·dry-run 기본).
대상 506 + 60 = 566행 수준이라 단발 배치로 끝난다. 검증 쿼리는 "as_axis_status IS NULL 인데
AS 흔적(as_received_date·as_log·as_lifecycle) 보유" = 0 이어야 한다.

### 3.4 술어 교체 범위

| 위치 | 현재 | 변경 후 |
|---|---|---|
| `as_dashboard_helpers._erp_as_incomplete_condition` | `Order.status` OR 3종 | `as_axis_status IN ('RECEIVED','IN_PROGRESS')` OR (`COMPLETED` AND 완료일 공란) |
| `as_dashboard_helpers._erp_as_completed_condition` | `status='AS_COMPLETED' AND 완료일` | `as_axis_status='COMPLETED' AND 완료일` |
| `map_snapshot.build_as_incomplete_map_query` | 위 조건 재사용 | 그대로(재사용이 계약) |
| `dashboard_counts`·`personal_board`·`calendar` AS 카운트 | status 술어 | 같은 헬퍼 경유로 통일 |

AS 탭 내부 버킷(`visit_confirmed`/`pending`/`unassigned`/`paid_unconfirmed`)은 `shipment.*`
JSONB 술어라 이번 변경과 무관하다.

### 3.5 롤아웃 (3단)

1. **컬럼+동기화+백필 배포** — 술어는 아직 status. 이 시점에 두 값이 어긋나는 행이 0인지
   드리프트 감사(`tools/ops/audit_as_axis_drift.py`, 읽기 전용)로 확인.
2. **술어 스위치** — 헬퍼 2개를 `as_axis_status` 로 교체. 탭 카운트·지도 건수·목록이 스위치
   전후로 동일해야 한다(스테이징 실측 비교 표를 근거로 남긴다).
3. **가드 유지** — 8/14 일괄 변경 가드는 그대로 둔다. status 를 덮어도 AS 목록은 안 흔들리지만,
   status 는 여전히 다른 화면(주문 대시보드 단계 배지)의 표시값이라 사용자 혼란은 남는다.

## 4. 대안과 기각 사유

| 안 | 내용 | 기각 사유 |
|---|---|---|
| B | `as_lifecycle` JSONB 표현식 인덱스로 직접 술어 | hot path 목록/카운트가 JSONB 경로 비교 + 레거시 506행은 lifecycle 자체가 없어 **폴백 OR 조건이 또 status 로 돌아온다**(구조 문제 미해결). 프로젝트 성능 규율(JSONB 술어 인덱스 없이 금지)과도 마찰 |
| C | `order_as_cycles` 테이블 활성화 후 조인 | 운영 테이블이 **0행**(dual-write 미가동). STATE-AS-01 후속 배치 의존이라 이 사고 대응이 남의 일정에 묶인다. 나중에 C 로 가더라도 A 의 투영 컬럼은 그 조인 결과를 담는 캐시로 그대로 쓰인다 |
| D | 아무것도 안 하고 가드만 유지 | status 를 쓰는 새 경로가 생길 때마다 같은 사고가 반복된다. 가드는 알려진 2경로만 막는다 |

## 5. 계약 테스트 (신규)

1. `derive_as_axis_status` 유도 규칙 단위 — lifecycle 우선, 레거시 폴백 4갈래, AS 흔적 없으면 None
2. 동기화 — AS 접수/완료/재접수 API 호출 뒤 `as_axis_status` 가 `read_as_status` 와 일치
3. **사고 재현 회귀** — AS 주문의 `status` 를 강제로 `COMPLETED` 로 덮어도 AS 대시보드 목록·탭
   카운트에서 사라지지 않는다(이 테스트가 이번 작업의 존재 이유)
4. 탭↔지도 건수 1:1 유지(기존 `test_as_map_snapshot.py` 계약 연장)
5. 드리프트 0 — 픽스처 전 행에서 컬럼값 == `read_as_status` 파생값

## 6. 성능 기준

- AS 대시보드 TTFB: 스위치 전후 스테이징 3회 중앙값 비교, **회귀 금지**(현 예산 dTTFB 168 유지)
- `EXPLAIN` 에서 Seq Scan 없음(부분 인덱스 사용 확인)
- perf-gate AS 경로 green

## 7. 마이그레이션 규율

- Alembic autogenerate 후 수동 검토 + `downgrade()` 포함
- 마이그레이션 파일은 **상수 동결**: `models` live import 금지(과거 리비전 소급 오염 방지)
- PG 레인에서 baseline create_all + stamp + 전체 upgrade 왕복 검증

## 8. 비범위

- `order.status` 자체의 퇴역(= main/AS 축 완전 분리)은 STATE-AS-01/STATE-OVERLAY-01 소관
- AS 버킷·비용 판정·타임라인 로직 무변경
- 모바일/태블릿 AS 표면의 표시 문자열 변경 없음

## 9. 리스크

| 리스크 | 완화 |
|---|---|
| 백필 유도 규칙이 레거시 일부를 잘못 분류 | 1단계에서 드리프트 감사 + 표본 수동 확인, 스위치는 그 다음 배포 |
| 동기화 누락 경로(플랫 컬럼을 안 거치는 write) | `sync_erp_flat_columns` 미경유 write 를 인벤토리 게이트로 확인(기존 state/mutation writer 인벤토리 재사용) |
| 탭 카운트 미세 변동 | 스위치 전후 실측 비교표를 승인 근거로 남김 |

## 10. 예상 작업량

3단 롤아웃 기준 반나절~하루(`**B` 등급). 1단(컬럼·동기화·백필·감사)과 2단(술어 스위치)은
별도 배포로 나눈다.


## 11. 구현 중 실측으로 바뀐 설계 (2026-08-17~18)

### 11.1 날짜 폴백 제거 (사용자 결정)

§3.2 의 유도 규칙 2번 "완료일/접수일 흔적" 갈래를 **뺐다**. 스테이징 백필 후 구/신 술어를
비교하니 미완료 54→67, 완료 362→373 으로 늘었고, 늘어난 건 전부 `as_received_date` 만 남고
status 는 완료로 운영되던 옛 주문(운영 18건, 3~5월, AS 이벤트 0)이었다. 날짜로 유도하면 그
시절 종결된 건이 AS 대시보드에 되살아난다 → 2026-08-17 사용자 결정으로 화면 무변동을 택했다.

제거 후 재백필 결과: 구/신 술어 건수 **완전 일치**(대시보드 조건 기준 미완료 53/53,
완료 426/426, 영업·택배 3/3, 집합 차이 0).

### 11.2 "투영은 암묵적으로 지우지 않는다" 규약 (실측으로 발견)

2단 배포 후 스테이징에서 사고를 재현해 보니 레거시 AS 주문은 **여전히 사라졌다**. 원인은
일괄 상태변경이 `sync_erp_flat_columns` 를 지나는데, `as_lifecycle` 이 없는 행은 유도 근거가
status 뿐이라 status 를 덮은 뒤 재유도하면 `None` → 투영까지 삭제된 것이다.

수정: 동기화는 **유도값이 나올 때만 갱신하고, 없으면 기존 값을 보존한다**. AS 축은 한번
생기면 사라지지 않는다(종료도 `COMPLETED` 라는 값이다). 재현 테스트
`test_legacy_as_order_survives_bulk_complete_api` 가 이 경로 전체를 잠근다.

### 11.3 곁가지 근본 수정

`blueprint_projection._legacy_orders` 가 전체 컬럼을 SELECT 해서, 새 컬럼 추가만으로 alembic
체인 왕복(`blueprint_00` downgrade)이 깨졌다. 마이그레이션이 앱 서비스를 재사용하는 한 그
쿼리는 그 시점 스키마에만 의존해야 하므로 `load_only` 로 3컬럼만 읽게 고쳤다.

### 11.4 스테이징 최종 검증 (2026-08-18)

| 항목 | 결과 |
|---|---|
| 구/신 술어 건수 | 53/53 · 426/426 · 3/3 (화면 표시값과 일치) |
| 드리프트 감사 | 507건 검사, 불일치 0 · 투영 누락 0 |
| 사고 재현(가드 우회 강제 완료) | status=COMPLETED 로 덮인 뒤에도 **AS 완료 탭 유지**, `as_axis_status='COMPLETED'` |
| PG 레인 | 737 green (체인 왕복 + `ix_orders_as_axis_status` 인덱스 가드) |

### 11.5 doctor 보강

복구 도구가 **자기 복구 기록을 사고 증거로 삼는** 결함이 이 검증 중 드러났다(창 안에 이전
복구가 있으면 그 복구의 before 를 원래 값으로 오인 → 복구가 no-op). `detail.restore=true`
감사행과 `mode='restore'` 이벤트를 증거에서 제외하도록 고쳤다.
