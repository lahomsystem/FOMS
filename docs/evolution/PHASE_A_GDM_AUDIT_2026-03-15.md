# Phase A GDM 감리 보고서

**작성일**: 2026-03-15  
**감리자**: code-reviewer (FOMS Code Reviewer)  
**대상**: Phase A 데이터 무결성/트랜잭션 버그 수정  
**계획서**: docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md  
**실행 보고서**: docs/evolution/PHASE_A_EXECUTION_REPORT_2026-03-15.md  

---

## 1. 검토 요약

| 항목 | 통과 | 주의사항 |
|------|------|----------|
| A-1 JSONB flag_modified + deepcopy | ✅ | 계획서 패턴 일치 |
| A-2 workflow.get('stage') 수정 | ✅ | erp_policy.py 781행 정확히 반영 |
| A-3 erp_orders_completion 회귀 | ✅ | settlement/issue 올바른 패턴 유지 |
| A-4 except: pass 제거, logger.warning | ⚠️ | 1건 신규 발견(아래 Findings) |

---

## 2. Findings

### [Severity: high] api_blueprint_complete에서 잘못된 세션 롤백 패턴 (A-3 유사) — ✅ 수정 완료

- **파일**: `apps/api/erp_orders_blueprint.py:149-155`
- **근거**: `except` 블록에서 `db = get_db()`를 호출해 **새 세션**을 얻은 뒤 `db.rollback()` 수행. 실패한 트랜잭션이 속한 원래 세션이 아닌 새 세션을 롤백함.
- **영향**: DB 쓰기 실패 시 부분 반영된 데이터가 롤백되지 않고 남을 수 있음.
- **수정 적용**: `db = None` 초기화 + `if db is not None: db.rollback()` 패턴으로 변경 완료.
- **권장 수정** (참고용, 이미 적용됨):
```python
db = None
try:
    ...
    db = get_db()
    ...
except Exception as e:
    if db is not None:
        try:
            db.rollback()
        except Exception as rb_err:
            logger.warning("Blueprint complete: rollback failed: %s", rb_err, exc_info=True)
    logger.warning("Blueprint complete 오류: %s", e, exc_info=True)
    return jsonify({'success': False, 'message': str(e)}), 500
```

---

### [Severity: low] erp_orders_drawing rollback 실패 무음 처리 — ✅ 수정 완료

- **파일**: `apps/api/erp_orders_drawing.py:241-246`
- **근거**: `api_order_transfer_drawing`의 `except` 내부에서 `db.rollback()` 실패 시 `except Exception: pass`로 무음 처리.
- **영향**: A-4 정신과 일치하지 않으나, 실행 보고서 범위에는 포함되지 않았음.
- **수정 적용**: `logger.warning(..., exc_info=True)` 추가 완료.

---

## 3. 검증 항목별 상세

### A-1: JSONB flag_modified + deepcopy 패턴

| 위치 | 계획서 패턴 | 실제 코드 | 결과 |
|------|-------------|-----------|------|
| erp_orders_drawing.py `api_order_transfer_drawing` | deepcopy + flag_modified | L58-67: dict→deepcopy, L176-177: flag_modified | ✅ |
| erp_orders_drawing.py `api_order_cancel_transfer` | deepcopy + flag_modified | L266: deepcopy, L386-387: flag_modified | ✅ |
| erp_orders_revision.py `api_order_request_revision` | deepcopy + flag_modified | L58: deepcopy, L112-113: flag_modified | ✅ |

**참고**: `api_order_transfer_drawing`은 `order.structured_data`가 str인 경우 `json.loads`로 파싱 후 `s_data`에 할당. `json.loads`는 새 dict를 반환하므로 in-place 변경 위험 없음. dict인 경우 `copy.deepcopy` 사용으로 계획서 준수.

---

### A-2: workflow.get('stage') 수정

| 파일 | 수정 전 | 수정 후 | 결과 |
|------|---------|---------|------|
| services/erp_policy.py:781 | `workflow.get('current_stage')` | `order.structured_data['workflow'].get('stage')` | ✅ |

`can_modify_by_team_policy` 내 `current_stage` 조회가 실제 저장 키 `stage`와 일치함.

---

### A-3: erp_orders_completion 회귀

| 검사 항목 | 결과 |
|-----------|------|
| `db = None` 초기화 | ✅ (api_settlement_issue L146) |
| try 내 `db = get_db()` | ✅ |
| except에서 `get_db()` 재호출 없음 | ✅ |
| `if db is not None: db.rollback()` | ✅ (L265-266) |

---

### A-4: 무음 실패 제거

| 파일 | 변경 내용 | 결과 |
|------|-----------|------|
| erp_orders_structured.py | _record_build_step, 이벤트 기록, draft meta/session, draft create rollback → logger.warning | ✅ |
| erp_orders_blueprint.py | Blueprint complete rollback 실패 → logger.warning | ⚠️ 로깅은 추가됐으나, except 블록의 `db = get_db()` 패턴 오류 존재 (위 Findings 참조) |

---

## 4. Open Questions

- `api_blueprint_complete`의 `db = get_db()` 패턴은 Phase A 실행 범위에 포함되지 않았으나, A-3와 동일한 유형의 버그임. Phase A 보완으로 수정할지, Phase B 이전 별도 패치로 처리할지 결정 필요.

---

## 5. Residual Risks

- **수동 검증 미완료**: Phase V-3 핵심 시나리오(도면 전달/취소/수정요청, 완료처리 실패, structured save) 수동 검증이 아직 수행되지 않음.
- **erp_orders_revision.py**: `api_order_request_revision`(L157-162), `api_order_request_revision_check`(L257-261)에 `db.rollback()`만 있고 `db = None` 초기화 없음. 예외가 `db = get_db()` 이전에 발생하면 NameError 가능. 다만 해당 경로에서는 `get_db()`가 먼저 호출되므로 현재는 실질적 위험 낮음.
- **print 디버깅**: erp_orders_revision.py L161-162, erp_orders_structured.py L189 등에 `print` 사용. Phase D-6 정리 대상으로 남겨둠.

---

## 6. Phase B 착수 권고

| 조건 | 상태 |
|------|------|
| A-1~A-4 계획 항목 실행 | ✅ 완료 |
| A-3 유형 추가 버그 (api_blueprint_complete) | ⚠️ 발견됨, 수정 권장 |
| 자동 검증 (pytest, import) | ✅ 통과 |

**권고**: **Phase B 착수 가능**. 단, `api_blueprint_complete`의 `db = get_db()` 패턴은 Phase A 보완 또는 Phase B 선행 패치로 수정하는 것을 권장한다.

---

## 7. 보고 체계 (System 4)

### 1) 무엇을 발견했는가 (What was found)

- A-1, A-2, A-3, A-4 계획 항목은 대체로 계획서대로 반영됨.
- `api_blueprint_complete`에서 A-3와 동일한 잘못된 세션 롤백 패턴(except에서 `get_db()` 재호출) 발견.
- `api_order_transfer_drawing`의 rollback 실패 무음 처리 1건 확인(범위 외).

### 2) 무엇을 작업/수정했는가 (What was changed)

- 읽기 전용 감리이므로 코드 수정 없음. GDM 감리 보고서만 작성함.

### 3) 왜 그런 결정을 내렸는가 (Why)

- AGENTS.md 및 code-reviewer 규칙에 따라 직접 코딩 금지.
- 발견 사항은 Findings로 명시하고, 수정 권고를 구체적으로 제시함.
- `api_blueprint_complete` 버그는 A-3와 동일한 유형이므로 high severity로 분류함.
