# Phase 4 다음 단계 계획서 (GDM 더블체크 후)

> **기준일**: 2026-02-16  
> **목표**: apps/erp.py 500줄 이하로 점진 분리, 한 번에 1개 모듈, 단계마다 기동 검증

---

## 1. GDM 더블체크 결과 (최신) — 2026-02-17

| 항목 | 결과 | 비고 |
|------|------|------|
| **현재 브랜치** | feature/erp-split-shipment-settings | Phase 4-3 미커밋(erp_measurement.py 등) |
| **앱 기동** | `from app import app` → APP_OK | DB 초기화·Admin 확인 정상 |
| **apps/erp.py** | **3,350줄, 25개 라우트** | 4-1~4-5c 분리 반영 (GDM 더블체크 2026-02-17) |
| **분리된 Blueprint** | + erp_orders_quick_bp, **erp_orders_drawing_bp** | app.py 등록 완료 |
| **DB 인덱스** | 무효 인덱스 없음 | 중복/미사용 인덱스 있음(wdcalculator 등), Phase 4와 무관 |
| **deploy 상태** | Phase 4-1까지 반영 | 4-2·4-3·4-4는 feature 브랜치 |

### erp.py 잔여 블록 (라우트 기준, 25라우트)

| 블록 | 라우트 수 | 분리 난이도 | 비고 |
|------|-----------|-------------|------|
| 대시보드(페이지) | 7 | 중 | erp_dashboard, drawing_workbench, measurement, shipment, as |
| 주문 API | 18 | 상 | **4-5c 완료** drawing-gateway-upload → erp_orders_drawing_bp. 잔여: request-revision, 도면/생산/시공/AS 등 |

---

## 2. 다음 단계 우선순위

| 순서 | 단계 | 작업 | 활용 자원 | 산출물 |
|------|------|------|-----------|--------|
| **0** | **배포 정리** | feature/erp-split-shipment-settings → deploy 머지·푸시 | Shell, Git | deploy에 Phase 4-2 반영, DEPLOY_NOTES.md 갱신 |
| **1** | **Phase 4-3** | 실측 API 분리 (measurement/update, measurement/route) | ✅ 완료 (2026-02-17) | apps/api/erp_measurement.py (erp_measurement_bp) |
| **2** | **Phase 4-4** | 지도/주소/유저 API 분리 | ✅ 완료 (2026-02-17) | apps/api/erp_map.py (erp_map_bp) 4라우트 |
| **3** | **Phase 4-5a** | 주문 Quick API (quick-search, quick-info, quick-status) | ✅ 완료 (2026-02-17) | apps/api/erp_orders_quick.py (erp_orders_quick_bp) |
| **4** | **Phase 4-5b** | 도면 전달/취소 (transfer-drawing, cancel-transfer) | ✅ 완료 (2026-02-17) | apps/api/erp_orders_drawing.py |
| **5** | **Phase 4-5c** | 도면 창구 업로드 (drawing-gateway-upload) | ✅ 완료 (2026-02-17) | erp_orders_drawing_bp에 추가 |
| **6** | **Phase 4-5d~** | 주문 API 잔여 (request-revision, 도면·생산·시공·AS 등) | 점진 분리 | erp.py 500줄 이하 |
| **7** | **선택** | app.py 300줄 이하, AI/카카오 정리 | - | 슬림다운 최종 목표 |

---

## 3. Phase 4-3 상세 (실측 API)

- **대상 라우트**: `POST /api/erp/measurement/update/<order_id>`, `GET /api/erp/measurement/route`
- **예상 규모**: ~200줄 내외 (measurement/route가 긴 편일 수 있음)
- **의존성**: get_db, Order, erp_edit_required, can_edit_erp, services 등
- **절차**: 브랜치 feature/erp-split-measurement → Blueprint 생성 → erp.py에서 해당 2라우트 제거 → 기동·린트 검증 → 단위 커밋

---

## 4. 활용 자원 체크리스트

| 구분 | 자원 | 용도 |
|------|------|------|
| Rules | 02-architecture, 06-safe-changes | Blueprint 패턴, 한 번에 1개 모듈, 브랜치·단위 커밋 |
| MCP | sequential-thinking, postgres, context7 | 분리 전략, DB 영향 없음 확인, Flask 문서 |
| Agents | python-backend, code-reviewer | 구현·검증 |
| 문서 | docs/plans/2026-02-16-app-slim-down.md, DEPLOY_NOTES.md | 계획·배포 내용(쉬운 한글) |

---

## 5. 배포 시 필수

- Phase 4-2 반영 후 **docs/DEPLOY_NOTES.md**에 다음 내용 추가 (쉬운 한글):
  - **뭘 했나요?** 출고 설정(시공 시간·도면 담당자·시공자·현장 주소)을 설정하는 코드를 별도 모듈로 분리했습니다.
  - **사용자 입장?** 화면·기능 동일합니다.
  - **개발자 입장?** `services/erp_shipment_settings.py`, `apps/api/erp_shipment_settings.py`로 분리되어 erp.py가 더 짧아졌습니다.

---

---

## 6. GDM 가용자원 동원 체크리스트 (다음계획 착수 시)

| 순서 | 자원 | 활용 내용 |
|------|------|-----------|
| 1 | **Rules** | 02-architecture(Blueprint·services), 06-safe-changes(브랜치·1개 모듈·단위 커밋) |
| 2 | **MCP** | sequential-thinking(분리 전략), postgres(DB 영향 없음), context7(Flask 문서) |
| 3 | **Agents** | python-backend(구현), code-reviewer(검증), devops-deploy(머지·푸시) |
| 4 | **문서** | docs/plans/2026-02-16-app-slim-down.md, phase4-next-steps.md, DEPLOY_NOTES.md |
| 5 | **절차** | 배포 정리(4-2 머지·DEPLOY_NOTES 갱신) → Phase 4-3(실측 API) → 4-4(지도·주소·유저) |

*이 계획서는 GDM 더블체크 후 작성되었으며, 다음 단계 진행 시 이 문서를 기준으로 실행하면 됩니다.*
