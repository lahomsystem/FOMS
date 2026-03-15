# FOMS Phase D 코드 리뷰 보고서

**리뷰일**: 2026-03-15  
**리뷰어**: code-reviewer 에이전트  
**범위**: Phase D (코드 품질 및 리팩토링) 변경 파일

---

## Findings

### [Severity: high] print 디버깅 잔존 (CLAUDE.md 위반)

- **파일**: `apps/api/erp_orders_revision.py:159-161`, `260-261`
- **근거**: `print(f"Request Revision Error: {e}")`, `print(traceback.format_exc())` 등이 except 블록 내에 존재. 프로젝트 규칙 "print 디버깅 없음" 위반.
- **영향**: 프로덕션 로그 오염, 민감 정보 노출 가능성.
- **권장 수정**: `logger.exception()` 또는 `logger.error(..., exc_info=True)`로 교체.

---

### [Severity: high] 에러 숨기기 (except Exception: pass)

- **파일**: `services/storage.py:246`, `apps/api/chat/routes.py:105`
- **근거**:
  - `storage.py`: `generate_thumbnail_from_storage_key` 내 "썸네일 이미 존재" 체크 실패 시 `except Exception: pass`로 무시.
  - `chat/routes.py`: `head_object`로 파일 크기 조회 실패 시 `except Exception: pass`로 무시.
- **영향**: 디버깅 어려움, 장애 추적 불가.
- **권장 수정**: `logger.debug()` 또는 `logger.warning()`으로 최소 로깅 후 fallback 처리. bare `pass` 제거.

---

### [Severity: medium] D-1 미적용: erp_orders_revision query().get() → Session.get()

- **파일**: `apps/api/erp_orders_revision.py:55`, `187`
- **근거**: `api_order_request_revision`, `api_order_request_revision_check`에서 `db.query(Order).filter(Order.id == order_id).first()` 사용. 동일 Blueprint 내 `api_drawing_request_revision`(272), `api_drawing_complete_revision`(338)은 `db.get(Order, order_id)` 사용.
- **영향**: D-1 일관성 미달, 단일 PK 조회 시 불필요한 query 오버헤드.
- **권장 수정**: `order = db.get(Order, order_id)`로 통일. (active_filter 필요 시 별도 검증 후 status/DELETED 체크)

---

### [Severity: medium] safeJsonFetch HTTP 에러 미검증

- **파일**: `static/js/erp/common_utils.js:14-21`
- **근거**: `res.json().catch(() => fallback)`만 사용. `res.ok` 또는 `res.status` 검증 없음. 4xx/5xx 시에도 fallback 반환하여 호출자가 실패를 인지하기 어려움.
- **영향**: 네트워크/서버 에러 시 사용자에게 잘못된 데이터 표시 가능.
- **권장 수정**: `if (!res.ok) return fallback;` 또는 `throw new Error(...)` 후 호출부에서 처리.

---

### [Severity: medium] ensure_path 중복 구현

- **파일**: `apps/api/orders.py:19-24`, `services/erp_utils.py:6-11`
- **근거**: `orders.ensure_path(parent, key)` (단일 키)와 `services.erp_utils.ensure_path(d, *keys)` (연쇄 키)가 별도 존재. orders.py는 15회 이상 ensure_path 호출.
- **영향**: 유지보수 이원화, 향후 동작 차이로 인한 버그 가능성.
- **권장 수정**: `orders.py`에서 `from services.erp_utils import ensure_path` 사용. 기존 `ensure_path(sd, 'shipment')` → `ensure_path(sd, 'shipment')` 호환. `ensure_path(schedule, 'construction')` 등 연쇄 호출은 `ensure_path(sd, 'schedule', 'construction')`로 통합 검토.

---

### [Severity: low] erp_orders_completion ensure_path 미사용

- **파일**: `apps/api/erp_orders_completion.py:189-195`
- **근거**: D-4 계획에 "ensure_path" 적용 대상으로 erp_orders_completion이 포함됐으나, `api_settlement_issue`는 `sd.get('settlement')` + 수동 dict 구성으로 처리.
- **영향**: D-4 완전 이행 여부 불명확. 기능상 문제 없으나 일관성 부족.
- **권장 수정**: `settlement = ensure_path(sd, 'settlement')` 등으로 정리하여 ensure_path 패턴 통일 (선택).

---

### [Severity: low] API 응답 형식 일부 불일치

- **파일**: 여러 API Blueprint
- **근거**: 규칙 "API 응답 형식 통일 `{success, data, error}`"인데, 일부는 `{success, message}`만 사용. (예: erp_orders_as, erp_orders_construction)
- **영향**: 클라이언트 파싱 시 `error` 키 부재로 통일된 에러 처리 어려움.
- **권장 수정**: 에러 응답 시 `error` 키 추가 또는 기존 `message`를 `error`로 매핑하는 클라이언트 규칙 명시.

---

## Open Questions

1. **Order.active_filter() vs db.get()**: `db.get(Order, order_id)`는 `active_filter()`를 적용하지 않음. erp_orders_revision의 request-revision/request-revision-check에서 삭제된 주문 접근을 막아야 한다면, `db.get()` 후 `order.status == "DELETED"` 등 별도 검사 필요. 현재 다른 D-1 적용 엔드포인트(erp_orders_as 등)는 `order.status == "DELETED" or order.deleted_at is not None` 체크를 수행함.
2. **erp_orders_structured / erp_shipment_settings의 db.query 사용**: `Order.active_filter()`가 필요한 경우 `db.get()`으로 대체 불가. 해당 파일들의 query 사용은 D-1 예외로 보는 것이 타당한지 확인 필요.
3. **orders.ensure_path 시그니처**: `ensure_path(parent, key)` vs `ensure_path(d, *keys)`. orders.py의 `ensure_path(parties, 'customer')` 등은 2단계까지만 사용. `services.erp_utils.ensure_path`로 통합 시 기존 호출부 수정 범위 확인 필요.

---

## Residual Risks

1. **Phase D 미변경 파일**: erp_orders_blueprint, quest, events, wdcalculator, erp_map 등 D-1/print/except 패턴이 있는 파일은 이번 리뷰 범위 외이나, 동일 규칙 위반 가능성 있음.
2. **프론트엔드 fetch 에러 처리**: common_utils.js 외 ERP 대시보드 인라인 스크립트에서 `fetch` 사용 시 `data.success` 검증 여부는 개별 템플릿 확인 필요.
3. **템플릿 800줄 초과**: erp_dashboard_styles.html(1735줄), erp_dashboard_scripts_core.html(313줄) 등. styles는 D-8 CSS 클래스 추가로 인한 증가로 추정. partial 분리 계획은 별도 검토 필요.

---

## 긍정적 평가 (준수 사항)

- **D-1**: erp_orders_as, erp_orders_construction, erp_orders_confirm, erp_orders_cs, erp_orders_production, erp_orders_revision(일부)에서 `db.get(Order, order_id)` 적용.
- **D-2**: erp_orders_structured의 `_handle_stage_transition`, `_record_structured_events` 등 책임 분리 적절.
- **D-4**: erp_orders_as에 `ensure_path` 적용, services/erp_utils.py 신규 생성.
- **D-5**: constants.py에 DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES 등 상수화.
- **D-6**: erp_shipment_settings에 logger 사용.
- **D-7**: storage.get_file_type public API화, chat/routes, attachments 등에서 호출.
- **D-8**: erp-toast-container, erp-col-resizer 등 CSS 클래스 정리.
- **Blueprint 패턴**: app.py 직접 수정 없이 Blueprint 유지.
- **structured_data 수정**: copy.deepcopy + flag_modified 패턴 준수.

---

## 보고 요약 (System 4)

| 항목 | 내용 |
|------|------|
| **무엇을 발견했는가** | print 디버깅 2건, except Exception: pass 2건, D-1 미적용 2건, safeJsonFetch HTTP 미검증, ensure_path 중복, API 응답 형식 일부 불일치 |
| **무엇을 작업/수정했는가** | 읽기 전용 리뷰 수행. 코드 수정 없음. |
| **왜 그런 결정을 내렸는가** | code-reviewer 에이전트는 "크로스 체킹" 역할로 한정되며, 직접 코딩을 수행하지 않음. 발견 사항은 GDM/사용자에게 보고하여 python-backend 등 해당 에이전트가 수정하도록 함. |
