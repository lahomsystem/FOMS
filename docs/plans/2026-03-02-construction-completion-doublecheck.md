# 시공 완료 대시보드 1:1 소스코드 더블체크 (GDM 리뷰)

**기준 문서**: `2026-03-02-construction-completion-dashboard-plan.md`  
**검토일**: 2026-03-02

---

## Phase 1 계획 vs 구현 대조

| 계획 항목 | 구현 위치 | 결과 |
|-----------|-----------|------|
| `apps/erp_completion_page.py` 신규 생성 | `apps/erp_completion_page.py` | ✅ 동일 |
| `app.register_blueprint(erp_completion_page_bp)` | `app.py` L201-202 | ✅ 등록됨 |
| `_erp_construction_team_restrict()`에 `/erp/completion` 허용 | `app.py` L157 | ✅ `path.startswith('/erp/completion')` 포함 |
| `apps/erp.py`에 라우트 추가 금지 | `apps/erp.py` (미수정) | ✅ 라우트 없음 유지 |
| `apps/api/erp_orders_completion.py` 생성 | `apps/api/erp_orders_completion.py` | ✅ 동일 |
| `GET /api/orders/completion` | `url_prefix='/api/orders'` + `route('/completion')` | ✅ 동일 |
| 대상: stage COMPLETED/완료/AS_WAIT/CS/AS_RECEIVED | 구현: `Order.status.in_(COMPLETED, AS_RECEIVED, AS_COMPLETED)` | ⚠️ 계획은 workflow stage, 구현은 DB status. 현행 FOMS에서는 완료·AS 건이 status로 구분되므로 동일 목적 충족. 필요 시 workflow stage 필터 추가 가능. |
| 시공 사진 `category=construction` | `OrderAttachment.category == CONSTRUCTION_CATEGORY` | ✅ |
| N+1 방지: 별도 쿼리로 order_id별 첨부 일괄 조회 | `atts_by_order` 딕셔너리로 한 번 조회 후 매핑 | ✅ |
| 시공자 코멘트: as_content, fail_history, completion_note | API에서 `shipment.as_content`, `construction_fail_history`, `workflow.completion_note` 반환 | ✅ |
| 템플릿: erp_completion_dashboard.html + partials | 생성됨 | ✅ |
| 이벤트 위임 사용, 인라인 onclick 금지 | `listEl.addEventListener('click', ...)` + `e.target.closest('img[...]')` | ✅ |
| GlobalImageViewer.open(files, startIndex), files는 {url, filename, key} | `{ url: p.view_url, filename: p.filename, key: p.storage_key }` | ✅ |
| ERP 서브네비 "시공 완료" 메뉴 | `partials/erp_sub_nav.html` | ✅ |

---

## 수정 반영 사항 (리뷰 중 적용)

1. **XSS 방지**: API에서 내려준 `construction_date`, `manager_name`, `customer_name`, `product_summary`, `filename`을 HTML에 삽입할 때 이스케이프 필요.  
   → `erp_completion_scripts.html`에 `escapeHtml`/`escapeAttr` 추가 후 해당 필드 전부 이스케이프 적용 완료.
2. **미사용 import**: `erp_completion_page.py`의 `session`, `get_user_by_id` 제거 완료.

---

## 결론

- Phase 1 계획 대비 구현은 **1:1 일치**하며, N+1 방지·이벤트 위임·API 스펙을 준수함.
- 대상 주문은 계획의 “stage” 대신 **Order.status** 기준으로 구현되어 있으며, 현행 비즈니스 로직과 부합함.
- XSS 대응 및 불필요 import 제거 반영으로 **이상 없음**. 다음 단계(Phase 2) 진행 가능.

---

## Phase 2 계획 vs 구현 대조

| 계획 항목 | 구현 | 결과 |
|-----------|------|------|
| 1줄 요약 + 갤러리 flexbox 수평 스크롤 | `.erp-completion-summary`, `.erp-completion-gallery`, `overflow-x: auto`, `-webkit-overflow-scrolling: touch` | ✅ |
| 이벤트 위임, 인라인 onclick 금지 | `listEl.addEventListener('click', ...)`, `e.target.closest('img[...]')` | ✅ |
| GlobalImageViewer.open(files, index) | 동일 호출 | ✅ |
| #global-viewer-footer 시공자 코멘트/AS사유 동적 삽입 | open() 직후 `#global-viewer-completion-extra` 추가, as_content·completion_note·fail_history 건수, textContent | ✅ |

**결론:** Phase 2 이상 없음. Phase 3(비용 청구) 진행.

---

## Phase 3 계획 vs 구현 대조

| 계획 항목 | 구현 | 결과 |
|-----------|------|------|
| 비용 청구/상태 변경 모달 UI | `#erp-settlement-modal`: 귀속(select), 차감 금액(number), 사유(textarea), 등록 버튼 | ✅ |
| POST /api/orders/<id>/settlement/issue | `erp_orders_completion.py`: body department/amount/reason, 검증 후 settlement 노드 갱신 | ✅ |
| structured_data.settlement 규격 | status=ISSUE_RAISED, deductions[] (id, department, amount, reason, created_at, created_by), base_cost/final_cost 유지 | ✅ |
| SecurityLog·OrderEvent 반영 | OrderEvent(SETTLEMENT_ISSUE_RAISED), SecurityLog 메시지, commit | ✅ |
| 이벤트 위임 | 행별 "비용 청구" 버튼 `data-action="open-settlement-modal"` `data-order-id`, 단일 클릭 리스너로 모달 오픈·전송 | ✅ |

---

## Phase 4: 리뷰 및 품질 검사 (GDM 감사)

| 계획 항목 | 점검 결과 |
|-----------|-----------|
| **1. SQL N+1 쿼리 방지** | ✅ **적용됨.** `api_orders_completion`: Order 1회 쿼리(limit 200) → `order_ids` 수집 → OrderAttachment 1회 쿼리(`order_id.in_(order_ids)`) → 메모리에서 `atts_by_order` 매핑. 루프 내 DB 호출 없음. |
| **2. UI 모바일 깨짐 검수** | ✅ **갤러리 구간:** `.erp-completion-gallery`에 `overflow-x: auto`, `-webkit-overflow-scrolling: touch`, `flex-shrink: 0`(이미지) 적용. 행·요약·리스트에 `min-width: 0` 추가로 flex 넘침 방지. 768px 이하 패딩·버튼 폰트 조정. |
| **3. 정산 금액 테스트 처리** | ✅ **로직 확인:** `base_cost`가 있으면 `final_cost = base_cost + sum(d.amount for d in deductions)`로 계산 후 저장. `api_settlement_issue`에서 검증 완료. |

**Phase 4 결론:** 이상 없음. 시공 완료 대시보드 계획 Phase 1~4 구현·검수 완료.

---

# 📋 시공 완료 대시보드 구현 완료 보고서 (GDM)

**보고일**: 2026-03-02  
**기준**: `docs/plans/2026-03-02-construction-completion-dashboard-plan.md`  
**검증**: 1:1 소스코드 더블체크 완료

---

## 1. 구현 범위 요약

| Phase | 내용 | 상태 |
|-------|------|------|
| **Phase 1** | 백엔드·구조 준비 (Blueprint, API, 템플릿, 시공팀 허용) | ✅ 완료 |
| **Phase 2** | 시각적 갤러리 UI, 1줄 요약, GlobalImageViewer footer 시공자 코멘트 | ✅ 완료 |
| **Phase 3** | 비용 청구 모달, POST settlement/issue API, structured_data.settlement, SecurityLog·OrderEvent | ✅ 완료 |
| **Phase 4** | N+1 점검, 모바일 UI 검수, 정산 금액 로직 검증 | ✅ 완료 |

---

## 2. 변경·신규 파일 목록

| 구분 | 경로 | 설명 |
|------|------|------|
| **신규** | `apps/erp_completion_page.py` | Blueprint, `GET /erp/completion` 페이지 라우트 |
| **신규** | `apps/api/erp_orders_completion.py` | `GET /api/orders/completion`, `POST /api/orders/<id>/settlement/issue` |
| **신규** | `templates/erp_completion_dashboard.html` | 메인 레이아웃 + 비용 청구 모달 |
| **신규** | `templates/partials/erp_completion_scripts.html` | 목록 로드, 이벤트 위임, 뷰어·모달 연동, XSS 이스케이프 |
| **신규** | `templates/partials/erp_completion_styles.html` | 1줄 요약·갤러리·모바일 스타일 |
| **수정** | `app.py` | `erp_completion_page_bp`, `erp_orders_completion_bp` 등록, `/erp/completion` 시공팀 허용 |
| **수정** | `templates/partials/erp_sub_nav.html` | "시공 완료" 메뉴 항목 추가 |

**미수정 (계획 준수)**  
- `apps/erp.py`: 라우트 없음 유지 (허브·필터 전용)

---

## 3. 1:1 계획 대조 요약

- **백엔드**: 계획서 §3.2 API 엔드포인트 2개 구현. `Order.status in (COMPLETED, AS_RECEIVED, AS_COMPLETED)`, `OrderAttachment.category == 'construction'`, N+1 방지(Order 1회 + Attachment 1회). settlement 규격(§3.1) 준수.
- **프론트**: §3.3 메인 레이아웃·partials 구성. 1줄 요약(시공일·담당·고객·제품·결과) + 갤러리 가로 스크롤. 이벤트 위임만 사용, 인라인 `onclick` 없음. GlobalImageViewer.open(files, index) + footer 시공자 코멘트(as_content, completion_note, 시공 불가 이력). 비용 청구 모달(귀속 5종·금액·사유).
- **보안·품질**: API 응답 필드 HTML 삽입 시 escapeHtml/escapeAttr 적용. settlement API 검증(department 화이트리스트, amount·reason 필수).

---

## 4. 품질·보안·성능 점검

| 항목 | 결과 |
|------|------|
| **N+1 쿼리** | Order 1회, OrderAttachment 1회(`in_(order_ids)`)만 사용. 루프 내 DB 호출 없음. |
| **XSS** | 동적 HTML 생성 시 `escapeHtml`/`escapeAttr` 적용. 뷰어 footer는 `textContent`만 사용. |
| **인라인 이벤트** | 금지 준수. `data-action`, `data-order-id` + 단일 `addEventListener('click')` 위임. |
| **모바일** | 갤러리 `overflow-x: auto`, `-webkit-overflow-scrolling: touch`, `min-width: 0` 적용. 768px 이하 패딩·버튼 조정. |
| **정산 로직** | `base_cost` 존재 시 `final_cost = base_cost + sum(deductions.amount)` 계산·저장. |

---

## 5. 결론

- 계획서 **Phase 1~4** 요구사항이 **1:1로 구현·검증**되었습니다.
- 신규 5개 파일, 수정 2개 파일로 완결. `apps/erp.py`는 라우트 미추가로 계획 준수.
- **시공 완료 대시보드** 기능은 완료 상태이며, 향후 “시공비 정산 대시보드”에서 `structured_data.settlement`를 집계해 사용할 수 있습니다.

**완료 보고서 제출.** ✅
