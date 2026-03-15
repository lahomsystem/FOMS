# Phase A 실행 완료 보고서

**실행일**: 2026-03-15
**계획서**: docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md
**목표**: 데이터 무결성/트랜잭션 버그 즉시 수정

---

## 실행 요약

| 항목 | 상태 | 수정 내용 |
|------|------|-----------|
| **A-1** | ✅ 완료 | JSONB `flag_modified` 누락 3곳 추가 + `copy.deepcopy` 적용 |
| **A-2** | ✅ 완료 | `erp_policy.py` `current_stage` → `stage` 키 수정 |
| **A-3** | ✅ 확인 | `erp_orders_completion.py` 이미 올바른 패턴 (회귀 없음) |
| **A-4** | ✅ 완료 | `except: pass` 제거, `logger.warning` 로깅 추가 |

---

## A-1: JSONB 변경 감지 누락

### 수정 파일
- `apps/api/erp_orders_drawing.py`
- `apps/api/erp_orders_revision.py`

### 변경 사항
1. **api_order_transfer_drawing**
   - `import copy`, `flag_modified` 추가
   - `s_data = copy.deepcopy(order.structured_data)` (dict → deepcopy)
   - `order.structured_data = s_data` 후 `flag_modified(order, 'structured_data')` 추가

2. **api_order_cancel_transfer**
   - `s_data = copy.deepcopy(order.structured_data or {})` (dict → deepcopy)
   - `order.structured_data = s_data` 후 `flag_modified(order, 'structured_data')` 추가

3. **api_order_request_revision**
   - `s_data = copy.deepcopy(order.structured_data or {})` (dict → deepcopy)
   - `order.structured_data = s_data` 후 `flag_modified(order, 'structured_data')` 추가

### 검증 포인트
- [ ] 도면 전달 후 `drawing_transfer_history` DB 저장 확인
- [ ] 전달 취소 후 `drawing_current_files`, `drawing_status` 복원 확인
- [ ] 수정 요청 후 `drawing_transfer_history` DB 저장 확인

---

## A-2: 팀 권한 검사 키 오류

### 수정 파일
- `services/erp_policy.py`

### 변경 사항
```python
# Before
current_stage = order.structured_data['workflow'].get('current_stage')

# After
current_stage = order.structured_data['workflow'].get('stage')
```

### 검증 포인트
- [ ] STAFF 사용자 기준 단계별 수정 허용/차단이 정책과 일치하는지 확인

---

## A-3: 잘못된 세션 롤백 (회귀 확인)

### 확인 결과
- `apps/api/erp_orders_completion.py` 145~257행
- `db = None` 초기화 → `db = get_db()` in try → `except`에서 `if db is not None: db.rollback()`
- **새 세션 호출 없음** → 이미 올바른 패턴

---

## A-4: 무음 실패 제거

### 수정 파일
- `apps/api/erp_orders_structured.py`
- `apps/api/erp_orders_blueprint.py`

### 변경 사항
1. **erp_orders_structured.py**
   - `import logging`, `logger = logging.getLogger(__name__)` 추가
   - `_record_build_step` rollback 실패: `except Exception: pass` → `logger.warning(..., exc_info=True)`
   - URGENT_CHANGED, MEASUREMENT_DATE_CHANGED, CONSTRUCTION_DATE_CHANGED, OWNER_TEAM_CHANGED 이벤트 기록 실패: `pass` → `logger.warning`
   - draft meta clear, session clear 실패: `pass` → `logger.warning`
   - draft create rollback 실패: `pass` → `logger.warning`

2. **erp_orders_blueprint.py**
   - `import logging`, `logger` 추가
   - Blueprint complete rollback 실패: `except Exception: pass` → `logger.warning`

### 검증 포인트
- [ ] 부가 이벤트 실패 시 서버 로그에서 원인 추적 가능
- [ ] 정상 저장이 이벤트 실패 때문에 불필요하게 깨지지 않음

---

## 자동 검증 결과

- `python -c "import app; print('APP_OK')"` → **성공**
- `pytest -q` → **5 passed**
- Lint → **에러 없음**

---

## GDM 감리 보완 (2026-03-15)

- **api_blueprint_complete**: `db = get_db()` in except → `db = None` + `if db is not None: db.rollback()` 패턴으로 수정
- **api_order_transfer_drawing**: rollback 실패 시 `except: pass` → `logger.warning` 추가

---

## 다음 단계

1. **수동 검증**: Phase V-3 핵심 시나리오 (도면 전달/취소/수정요청, 완료처리 실패, structured save)
2. **Phase B**: B-2, B-3, B-4 즉시 착수 가능
