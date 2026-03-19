# AS 출고 대시보드 날짜/내용 회귀 수정 Spec
> 작성일: 2026-03-19 | 상태: 🟡 승인대기

## 1. What — 무엇을 수정하는가

### 1.1 최종 결과물
- AS 대시보드에서 `AS 방문일`을 저장하면 출고 대시보드가 해당 날짜 하단에 AS 주문을 표시한다.
- 출고 대시보드의 AS 내용은 HTML 태그 코드가 아니라 읽을 수 있는 텍스트로 표시된다.
- 기존 시공일/출고 집계는 유지하되, AS 방문일이 다시 `시공일` 경로를 오염시키지 않는다.

### 1.2 기능 요구사항
1. 출고 대시보드에서 **AS 주문은 `construction`이 아니라 `as_visit` 날짜**를 기준으로 패널 집계/날짜 클릭 목록/검색 자동 이동이 동작해야 한다.
2. **일반 주문은 기존처럼 `construction` 날짜**를 기준으로 유지해야 한다.
3. `services/order_date_sync.py`는 **ERP Beta 여부와 무관하게** `structured_data.schedule.as_visit.date`가 있으면 `OrderScheduleDate.kind='as_visit'`를 생성할 수 있어야 한다.
4. 기존 `scripts/backfill_phase4_dates.py`를 그대로 사용해 **이미 `structured_data.schedule.as_visit.date`가 저장된 주문들**의 `as_visit` read model을 재생성할 수 있어야 한다.
5. 출고 대시보드의 AS 내용은 **sanitize된 rich HTML 저장 계약은 유지**하되, 출고 화면에서는 **태그 제거된 plain text 요약**으로 렌더링한다.
6. 출고 대시보드에서 AS로 취급하는 상태 집합은 하나의 규칙으로 통일한다. 기본 범위는 `AS`, `AS_RECEIVED`, `AS_COMPLETED`로 본다.
7. `13fc566`에서 제거한 "AS 방문일 → 시공일 동기화"는 되돌리지 않는다.

### 1.3 예외/제약 조건
- `AS 방문일`이 비어 있는 AS 주문은 출고 대시보드 날짜 패널/목록에서 제외한다.
- `scheduled_date` 또는 `schedule.construction.date`에 AS 방문일을 다시 기록하지 않는다.
- 현재 미커밋 상태인 `apps/erp_as_page.py` 사용자 변경과 충돌하지 않도록 수정 범위를 분리한다.
- DB 스키마 마이그레이션은 하지 않는다. `OrderScheduleDate.kind`가 문자열 컬럼이므로 `as_visit` 추가는 애플리케이션 레벨 변경으로 처리한다.
- 이번 수정은 **출고 대시보드의 날짜 선택/노출 문제 해결**이 목표이며, 기존 AS 주문의 `construction` read model 정리(오염 제거)는 별도 범위로 둔다.
- `remaining_panel_dates`의 인력/용량 계산은 이번 변경에서 건드리지 않는다. 즉, 날짜 집계/행 노출만 수정하고 capacity 패널은 현행 유지한다.

## 2. How — 어떻게 수정하는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `services/order_date_sync.py` | `schedule.as_visit.date`를 `OrderScheduleDate(kind='as_visit')`로 정규화 |
| `apps/erp_shipment_page.py` | AS 주문/일반 주문의 날짜 기준을 분리하는 조회 로직 및 패널 집계/목록 필터 정리 |
| `services/as_content_safety.py` | sanitize된 AS HTML을 출고 화면용 plain text로 변환하는 공통 helper 추가 |
| `templates/erp_shipment_dashboard.html` | raw HTML 대신 plain text 요약 필드 출력 |
| `tests/test_shipment_dashboard_regression.py` | 날짜 정규화/AS 내용 변환/출고 대시보드 날짜 선택 규칙 회귀 테스트 추가 |

### 2.2 아키텍처 방향
- **날짜 쪽**: 이미 승인된 Phase 4 날짜 정규화 구조(`order_schedule_dates`)를 확장한다. 즉, 새 문제를 기존 레거시 컬럼 오염으로 덮지 않고 `Read Model`을 보강한다.
- **내용 표시 쪽**: 저장 계약은 `sanitize_as_content_html()` 유지, 소비 계약은 화면별로 분리한다. AS 대시보드는 rich HTML, 출고 대시보드는 plain text 요약으로 간다.
- **재사용 기준**: `docs/specs/foms-phase4-date-normalization-spec.md`의 정규화 구조를 따르고, `scripts/backfill_phase4_dates.py`를 재사용한다.

### 2.3 의존성 및 영향 범위
- **영향 화면**: `/erp/shipment` (직접 영향), 특히 날짜 패널/단일일·기간 목록/검색 자동 이동
- **백필 필요**: 이미 저장된 `structured_data.schedule.as_visit.date`는 코드 수정만으로는 `order_schedule_dates`에 자동 반영되지 않으므로 백필 실행 필요
- **백필 범위 주의**: `scripts/backfill_phase4_dates.py`는 AS 전용이 아니라 `order_schedule_dates` 전체 재계산 스크립트다. 따라서 배포 후 전 프로세스가 새 코드로 올라간 상태에서 실행해야 한다.
- **보안 영향**: 출고 대시보드는 `safe` 렌더 대신 plain text로 표시하므로 HTML/XSS 노출 면에서 더 보수적임
- **비영향 범위**: AS 대시보드 rich HTML 저장/렌더링, `13fc566`의 오염 차단 정책, 현재 사용자 미커밋 변경

## 3. Steps — 실행 단계
- [ ] Step 1: `tests/test_shipment_dashboard_regression.py`에 failing tests 작성
- [ ] Step 2: `services/order_date_sync.py`에 `as_visit` 정규화 추가
- [ ] Step 3: `apps/erp_shipment_page.py`의 패널 집계/목록 조회/자동 날짜 이동을 AS/일반 주문 기준으로 분리
- [ ] Step 4: `services/as_content_safety.py`에 plain text 변환 helper 추가
- [ ] Step 5: `templates/erp_shipment_dashboard.html`이 plain text 요약을 출력하도록 변경
- [ ] Step 6: `/erp/shipment` 통합 테스트와 helper 테스트를 함께 통과시킴
- [ ] Step 7: 새 코드 배포 후 `order_schedule_dates` 백업 → dry-run → 실제 백필 실행
- [ ] Step 8: 테스트/스모크/감리 결과를 문서화

## 4. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `pytest tests/test_shipment_dashboard_regression.py -q` 통과
- [ ] 로그인 상태에서 `/erp/shipment?date=<AS방문일>` 조회 시 해당 AS 주문이 해당 날짜에 표시됨
- [ ] `/erp/shipment?date_from=<from>&date_to=<to>`에서도 AS 주문이 `as_visit` 기준으로만 포함됨
- [ ] 출고 대시보드에서 AS 내용 HTML 태그가 그대로 보이지 않음
- [ ] 배포 후 `python scripts/backup_order_schedule_dates.py` 실행
- [ ] 배포 후 `python scripts/backfill_phase4_dates.py --dry-run --order-id <영향 주문 ID> --verbose` 결과에서 `as_visit` diff 확인
- [ ] 배포 후 `python scripts/backfill_phase4_dates.py --verbose` 적용이 실패 없이 종료

## 5. 참고 자료
- 기존 결정: `docs/specs/foms-phase4-date-normalization-spec.md`
- 관련 더블체크: `docs/plans/2026-03-04-multiple-dates-plan-GDM-doublecheck.md`
- 관련 감리: `docs/evolution/ERP_BETA_SAVE_FLOW_GDM_AUDIT_2026-03-16.md`
- 관련 분석: `docs/evolution/2026-03-16-FILTER-2-MISSING-ANALYSIS-REPORT.md`
