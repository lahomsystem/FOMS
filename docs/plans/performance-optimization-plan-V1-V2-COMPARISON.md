# FOMS 성능 최적화 계획서 V1 vs V2 초정밀 비교 분석

**분석일:** 2026-03-09  
**분석자:** Grand Develop Master (가용 자원 동원)  
**방법론:** 1:1 소스코드 대조 + 문서 구조 비교 + 제안 충돌 검증

---

## Executive Summary

| 구분 | V1 | V2 |
|------|-----|-----|
| **총 줄 수** | 716줄 | 489줄 |
| **문서 성격** | 상세 실행 계획 (코드 스니펫 포함) | 원칙·제외 사유 중심의 실행 가능안 |
| **이슈 분류** | C/H/M/L/Q 18건 + 추가 발견 | R-1~R-12 12건 (근본 원인 중심) |
| **Phase 구조** | Phase 0~4 (5단계) | Phase 0~4 (5단계, 내용 재구성) |
| **제외된 제안** | 없음 (모두 실행안) | 4건 명시적 제외 |
| **핵심 차이** | "최적화 우선" | "동작 보존 우선, 가짜 최적화 금지" |

---

## 1. 문서 구조 1:1 비교

### 1.1 메타데이터

| 항목 | V1 | V2 |
|------|-----|-----|
| 제목 | FOMS Production 성능 최적화 계획서 | FOMS Production 성능 최적화 계획서 **V2** |
| 작성 | Grand Develop Master — 4개 전문 에이전트 병렬 분석 | (작성일만) |
| 기준 | 더블체크 소스 코드 교차 검증 | V1 재검토 후 소스 기준 V2 재작성 |
| 목표 | 페이지 로딩 속도 개선, 선형 성능 저하 해결 | **체감 성능 개선 + 페이지 의미·데이터 노출 범위 불변** |
| 상태 | Phase 0~3 계획 수립 완료, 실행 대기 | 소스 1:1 더블체크 완료 / **실행 가능안만** 남긴 수정본 |

### 1.2 섹션 매핑

| V1 섹션 | V2 섹션 | 비고 |
|---------|---------|------|
| 1. 현상 정리 | (없음) | V2는 "V2에서 바로잡은 점"으로 대체 |
| 2. 전체 분석 결과 (18건) | 2. 소스 기준 근본 원인 (12건) | 분류 체계 완전 변경 |
| 3. 영향 범위 분석 | (축소) | Phase별로 통합 |
| 4. 개선 원칙 | 4. V2 실행 원칙 | V2가 5개 원칙으로 강화 |
| 5. Phase별 실행 계획 | 5. Phase별 실행 계획 | 구조 유사, 내용 대폭 수정 |
| 6. 예상 효과 요약 | (없음) | V2는 "구현 우선순위"로 대체 |
| 7. 성공 기준 | 7. 성공 기준 | 유사 |
| 8. 더블체크 이력 | (없음) | V2는 "제외한 제안"으로 대체 |
| 9. 참조 | 9. 참조 소스 | 유사 |

---

## 2. 이슈 분류 체계 비교

### 2.1 V1: C/H/M/L/Q 5단계

| 등급 | 건수 | 대표 |
|------|------|------|
| Critical | 4 | C-1 날짜 String+CSV, C-2 JSONB cast+ILIKE, C-3 동기 지오코딩, C-4 Beta 과다 조회 |
| High | 5 | H-1~H-5 |
| Medium | 6 | M-1~M-6 |
| Low | 3 | L-1~L-3 |
| Quality | 4 | Q-1~Q-4 |

### 2.2 V2: R-1~R-12 단일 체계

| ID | 근본 원인 | V1 대응 |
|----|----------|---------|
| R-1 | 요청당 사용자 조회 중복 | H-5 |
| R-2 | menu_config 매 요청 파일 I/O | L-1 |
| R-3 | TEMPLATES_AUTO_RELOAD | L-2 |
| R-4 | 전역 디버그 로그 | M-6 |
| R-5 | 날짜 String CSV + JSONB 혼재 | C-1 |
| R-6 | cast(structured_data, String).ilike | C-2 |
| R-7 | 첨부파일 전체 GROUP BY | M-1 |
| R-8 | 실측 대시보드 과다 로드 + N+1 | H-1, H-2 |
| R-9 | 출고 대시보드 분기별 후보 로드 | H-3 |
| R-10 | 실측 동선 API Beta 과다 | C-4 |
| R-11 | 지도 동기 지오코딩 | C-3 |
| R-12 | nearby API 넓은 후보군 | M-4 |

**소스 검증 결과:**
- `app.py:144-156` — before_request, get_user_by_id ✅
- `services/context_processors.py:43-52`, `86-97` — inject_status_list, inject_menu ✅
- `app.py:414` — TEMPLATES_AUTO_RELOAD = True ✅
- `templates/layout.html` — console.log **39건** (V1/V2 일치) ✅
- `templates/map_view.html` — console.log **6건** (V1 "7건"은 오기, V2 정확) ✅
- `erp_map.py:512-569` — sync_batch, _SYNC_GEOCODE_MAX=40 ✅

---

## 3. V2에서 제외한 4가지 제안 (소스 검증)

### 3.1 출고 단일 날짜 분기 `.limit(500)` 추가

| 항목 | 내용 |
|------|------|
| V1 제안 | Phase 2-3b: 단일 날짜 검색(291행) `.all()` → `.limit(500).all()` |
| V2 제외 이유 | `erp_shipment_page.py:317-320`에서 Python 후처리 `extract_all_construction_dates(order)`로 실제 날짜 매칭. 앞단 LIMIT 시 **결과 누락** |
| 소스 검증 | ✅ **타당** — 319-321행 `for order in all_candidates: if selected_date in extract_all_construction_dates(order)` 패턴 확인. LIMIT 500이면 501번째 이후 매칭 주문 누락 |

### 3.2 지방/자가실측/캘린더 일괄 `limit(500)`

| 항목 | 내용 |
|------|------|
| V1 제안 | Phase 2-5: dashboards.py `limit(500)` 추가, Phase 2-8: 캘린더 limit 500 |
| V2 제외 이유 | pagination 계약 없음. `regional_dashboard.html`, `self_measurement_dashboard.html`, `calendar.html`에 페이지네이션 없음 → **표시 누락** |
| 소스 검증 | ✅ **타당** — templates에 pagination UI 없음 |

### 3.3 수도권 대시보드 8중 쿼리 → 단일 쿼리 통합

| 항목 | 내용 |
|------|------|
| V1 제안 | Phase 2-9: `all_metro = base_query.limit(500).all()` 후 Python `defaultdict` 분류 |
| V2 제외 이유 | `dashboards.py:185-241` 각 카드가 **서로 다른 조건·정렬** 사용. `urgent_candidates`(measurement_date.asc), `measurement_alerts`(measurement_date.asc), `pre_candidates`(다른 or_ 조건), `installation_candidates`(scheduled_date.asc), `as_orders`(AS_RECEIVED), `hold_orders`(ON_HOLD), `normal_orders`(limit 20), `completed_orders`(limit 50, completion_date.desc) |
| 소스 검증 | ✅ **타당** — 8개 쿼리가 서로 다른 `filter`, `order_by`, `limit` 사용. 단일 쿼리로 합치면 의미 보존 불가 |

### 3.4 JSONB GIN 인덱스 + `@>` 단독 대체

| 항목 | 내용 |
|------|------|
| V1 제안 | Phase 1 JSONB GIN 인덱스, Phase 2-7 `@>` containment 연산자 |
| V2 제외 이유 | Beta 날짜가 `schedule.*.date`뿐 아니라 `items[*].measurement_date`, `items[*].construction_date`에도 있고, 일부 CSV 문자열. **단일 containment로 부족** |
| 소스 검증 | ✅ **타당** — structured_data 구조가 복잡, 단일 경로 검색으로 커버 불가 |

---

## 4. Phase별 1:1 비교

### Phase 0: 공통 오버헤드

| 단계 | V1 | V2 | 차이 |
|------|-----|-----|------|
| 0-1 | g.current_user 캐시 | g.current_user 단일 조회 | 동일 |
| 0-2 | menu_config 모듈 캐시 | menu_config 모듈 캐시 + **관리자 저장 시 캐시 무효화** | V2가 admin.py:35-38 추가 |
| 0-3 | `FLASK_ENV != 'production'` | **_is_production, _is_railway 기준** | V2가 app.py 99-106, 121-123 반영. V1은 FLASK_ENV만 사용 |
| 0-4 | 첨부파일 COUNT 범위 제한 | 동일 | 동일 |
| 0-5 | console.log FOMS_DEBUG 래핑 | 동일 (map_view 6건으로 정정) | V2가 map_view 건수 정확 |

**V2 0-3 검증:** app.py에 `_is_production`, `_is_railway` 이미 존재. V1의 `os.environ.get('FLASK_ENV') != 'production'`만으로는 Railway staging 등에서 부족할 수 있음. V2 제안이 더 정확.

### Phase 1: DB/쿼리 최적화

| V1 단계 | V2 단계 | 차이 |
|---------|---------|------|
| Phase 1: 인덱스 추가 | Phase 1: **의미 보존형 대시보드 정리** | **순서 교체** |
| Phase 2: 쿼리 최적화 | Phase 1에 통합 | V2는 "쿼리 정리 → 인덱스" 순서 |

| 항목 | V1 | V2 |
|------|-----|-----|
| 실측 query/base_query | with_entities 경량화 | load_only 또는 경량 로드, **합치지 않음** | 동일 원칙 |
| 실측 N+1 | 배치 로드 | 배치 로드 | 동일 |
| 출고 단일 날짜 LIMIT | `.limit(500)` 추가 | **금지** | V2 제외 |
| 출고 panel_orders | with_entities | load_only/경량 | 동일 |
| 실측 동선 API Beta | JSONB 경로 연산자 | **레거시/Beta 분리**, 별도 후보 쿼리 | V2가 더 보수적 |
| bulk_update N+1 | IN 절 배치 | 동일 | 동일 |
| 지방/자가실측 LIMIT | limit(500) | **제외** | V2 제외 |
| 캘린더 API | limit 500, 최대 1000 | **limit 유지**, payload projection만 | V2 제외 |
| 수도권 8중 쿼리 | 단일 쿼리 통합 | **제외** | V2 제외 |
| JSONB cast→경로 | Phase 2-7 | Phase 4로 이동 (구조 정상화) | V2가 장기화 |

### Phase 2: 인덱스 (V1) vs Phase 2: 인덱스 (V2)

| V1 Phase 1 인덱스 | V2 Phase 2 인덱스 |
|------------------|-------------------|
| pg_trgm GIN (measurement_date, scheduled_date) | **선택적** trigram, pg_trgm 사용 가능 시만 |
| Composite partial (erp_beta, regional, self_measurement) | 동일 (부분 인덱스 3종) |
| JSONB GIN | **지금 추가 금지** |
| received_date btree | V2에서 언급 없음 |
| **즉시 추가** | **쿼리 정리 후** 추가 |

### Phase 3: 지도

| 항목 | V1 | V2 |
|------|-----|-----|
| 동기 지오코딩 제거 | 완전 제거, enqueue만 | 동일 | 동일 |
| format_date 루프 밖 | 동일 | 동일 |
| 날짜 필터 중복 제거 | _build_map_date_filter | 동일 | 동일 |
| CDN 버전 통일 | map_view → layout과 통일 | V2에서 Phase 3에 미포함 (암묵적) |
| nearby API | 2500→500 축소 | **후보군 정의 개선**, LIMIT만 낮추기 금지 | V2가 보수적 |

### Phase 4: 추가 개선

| V1 Phase 4 | V2 Phase 4 |
|------------|------------|
| Gunicorn gzip, 정적 캐시, 인라인 JS 외부화, summary 캐시, 날짜 정규화 | **날짜 검색 구조 정상화** (order_schedule_dates 테이블) |

**V2 Phase 4는 완전히 재정의됨.** V1의 "추가 개선"은 V2에서 흩어짐. V2 Phase 4는 **구조적 원인** 해결에 집중.

---

## 5. 소스 라인 번호 정확도

| 문서 | 위치 | V1 | V2 | 실제 |
|------|------|-----|-----|------|
| app.py before_request | 153 | 153 | 144-156 | 139, 144, 153 ✅ |
| context_processors | 49, 90 | 49, 90 | 43-52, 86-97 | 43, 49, 86, 90 ✅ |
| TEMPLATES_AUTO_RELOAD | 414 | 414 | 99-106, 121-123, 414 | 414 ✅ |
| layout.html console.log | 424-553, 39건 | 39건 | 39건 | 39건 ✅ |
| map_view.html console.log | 1107-1123, 7건 | 7건 | 6건 | **6건** (V2 정확) |
| erp_map sync_batch | 512-569 | 512-569 | 512-569 | 515-569 ✅ |
| erp_shipment 단일 날짜 | 291행 | 291 | 291-320 | 289-321 ✅ |
| dashboards 수도권 | 185-241 | 185-241 | 185-241 | 186-241 ✅ |

---

## 6. 핵심 철학 차이

| 원칙 | V1 | V2 |
|------|-----|-----|
| 최우선 | 개선 효과 극대화 | **동작 보존** |
| LIMIT 사용 | 데이터 증가 대비 적극 활용 | **가짜 최적화**로 간주, pagination 계약 없으면 금지 |
| 쿼리 통합 | 가능하면 단일 쿼리로 | **의미가 다르면 통합 금지** |
| 인덱스 | 설계 후 즉시 추가 | **쿼리 정리 후** 추가 |
| 구조 문제 | Phase 4 "날짜 정규화"로 언급 | **Phase 4 전면 재정의**, order_schedule_dates 테이블 설계 |

---

## 7. 권장 실행 순서 (GDM 종합)

### 즉시 착수 (V2 기준 + 소스 검증)

1. **Phase 0 전체** — 위험도 낮음, 효과 확실
2. **Phase 1-2** 실측 N+1 제거
3. **Phase 1-4** 실측 동선 API Beta 과다 조회
4. **Phase 3-1** 지도 동기 지오코딩 제거

### 착수 전 추가 설계

1. Phase 2 인덱스 상세 (pg_trgm Railway 지원 여부)
2. Phase 3-3 nearby 후보군 개선 방식
3. Phase 4 order_schedule_dates 설계 및 백필

### 금지 (V2 명시)

1. 출고 단일 날짜 앞단 LIMIT
2. pagination 없는 화면 일괄 LIMIT
3. JSONB GIN만으로 날짜 검색 대체
4. 수도권 8중 쿼리 무리한 통합

---

## 8. 결론

- **V1**: 4개 에이전트 병렬 분석 기반, 상세 실행 계획. 일부 제안이 **데이터 누락·의미 변경** 위험이 있음.
- **V2**: 소스 1:1 더블체크 후 **실행 가능안만** 유지. "동작 보존 우선, 가짜 최적화 금지" 원칙으로 4건 제외.
- **소스 검증**: V2 제외 사유 4건 모두 **타당**. V1의 map_view 7건 → 6건 오기 정정.
- **실행 권고**: **V2를 기준**으로 Phase 0부터 순차 진행. V1의 상세 코드 스니펫은 참고용으로 활용.

---

## 9. 참조

- `docs/plans/performance-optimization-plan.md` (V1)
- `docs/plans/performance-optimization-plan-v2.md` (V2)
- `.cursor/agents/grand-develop-master.md`
- 소스 검증: app.py, services/context_processors.py, apps/erp_shipment_page.py, apps/dashboards.py, apps/api/erp_map.py
