# FOMS Brain AX Designer V2 — 구현 실행 기록
> 날짜: 2026-05-13 | 상태: ✅ MVP 완료 | 계획서: `2026-05-13-foms-brain-ax-designer-blueprint-v2-implementation-map.md`

---

## 1. 구현 파일 Inventory

### Backend (Flask)

| 파일 | 역할 |
|---|---|
| `foms/web/designer/__init__.py` | designer_bp 노출 |
| `foms/web/designer/routes.py` | `/wdplanner-v2` 라우트 3개 |
| `foms/api/designer/__init__.py` | API blueprint 노출 |
| `foms/api/designer/projects.py` | GET/POST /api/designer/projects, POST /versions |
| `foms/api/designer/validation.py` | POST /api/designer/validate |
| `foms/api/designer/ai_runs.py` | POST/GET /ai-runs, POST /resume |
| `foms/api/designer/ontology.py` | GET /api/designer/ontology/current |
| `foms/persistence/designer/__init__.py` | persistence surface |
| `foms/persistence/designer/models.py` | 7개 ORM 모델 |
| `foms/persistence/designer/repositories.py` | DB 쿼리 함수 |
| `foms/services/designer/__init__.py` | services surface |
| `foms/services/designer/schemas.py` | Pydantic 요청/응답 스키마 |
| `foms/services/designer/defaults.py` | 기본 design JSON 팩토리 |
| `foms/services/designer/validator.py` | MVP 하드룰 검증기 |
| `foms/services/designer/langgraph_workflows.py` | Design Assist Graph (fake-mode) |
| `foms/services/designer/corrections.py` | correction log 헬퍼 |
| `foms/services/designer/bom.py` | BOM 생성 stub |
| `foms/services/designer/vector_memory.py` | pgvector 임베딩 서비스 stub |
| `foms/services/designer/evolution.py` | rule candidate 진화 stub |
| `foms/platform/blueprints.py` | designer 5개 blueprint 등록 추가 |
| `migrations/versions/designer_ax_initial.py` | 7개 테이블 초기 migration |
| `migrations/versions/designer_pgvector.py` | pgvector extension + embedding 컬럼 |
| `migrations/env.py` | designer models import 추가 |
| `templates/designer/wdplanner_v2.html` | iframe wrapper 페이지 |
| `templates/designer/wdplanner_v2_setup.html` | 빌드 미완성 시 안내 페이지 |
| `templates/partials/shared/layout_nav.html` | FOMS Brain 메뉴 추가 |

### Frontend Add-in

| 파일 | 역할 |
|---|---|
| `Add In Program/FOMSBrainDesigner/package.json` | 의존성 (R3F, Drei, Zustand) |
| `Add In Program/FOMSBrainDesigner/index.html` | SPA 진입점 |
| `Add In Program/FOMSBrainDesigner/vite.config.ts` | outDir → `static/designer` |
| `Add In Program/FOMSBrainDesigner/tsconfig.json` | TypeScript 설정 |
| `Add In Program/FOMSBrainDesigner/src/main.tsx` | React 마운트 |
| `Add In Program/FOMSBrainDesigner/src/App.tsx` | 루트 레이아웃 |
| `Add In Program/FOMSBrainDesigner/src/api/client.ts` | FOMS API 클라이언트 |
| `Add In Program/FOMSBrainDesigner/src/canvas/DesignerCanvas.tsx` | R3F Canvas + 조명 + OrbitControls |
| `Add In Program/FOMSBrainDesigner/src/canvas/CabinetScene.tsx` | 부재 메시 + Gizmo 통합 |
| `Add In Program/FOMSBrainDesigner/src/canvas/DimensionLines.tsx` | 치수선 (W/H/D 색상 구분) |
| `Add In Program/FOMSBrainDesigner/src/canvas/SelectionGizmo.tsx` | 선택 부재 바운딩박스 + 라벨 |
| `Add In Program/FOMSBrainDesigner/src/domain/designTypes.ts` | TypeScript 타입 정의 |
| `Add In Program/FOMSBrainDesigner/src/domain/defaultCabinet.ts` | 기본 캐비닛 설계 데이터 |
| `Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts` | Zustand 글로벌 상태 |
| `Add In Program/FOMSBrainDesigner/src/ui/InspectorPanel.tsx` | 치수 편집 + 부재 선택 정보 |
| `Add In Program/FOMSBrainDesigner/src/ui/AIPanel.tsx` | AI 실행/폴링/interrupt UI |
| `Add In Program/FOMSBrainDesigner/src/ui/ValidationPanel.tsx` | 검증/저장 게이트 UI |
| `static/designer/index.html` | 빌드 산출물 (iframe 서빙) |
| `static/designer/assets/index-*.js` | 번들 (Three.js + R3F 포함) |

### Tests

| 파일 | 커버 영역 |
|---|---|
| `tests/domains/test_designer_routes.py` | route 200/302, setup fallback |
| `tests/domains/test_designer_projects_api.py` | CRUD, invalid 차단 |
| `tests/domains/test_designer_validator.py` | 모든 하드룰 검증 |
| `tests/domains/test_designer_ai_runs.py` | fake-mode run, interrupt, approve, reject |
| `tests/contracts/runtime/test_designer_blueprint_registration.py` | blueprint 등록 contract |

---

## 2. 검증 명령/결과

```powershell
# APP 임포트 검증
python -c "import app; print('APP_OK')"
# → APP_OK ✅

# 전체 designer 테스트
pytest tests/domains/test_designer_routes.py `
       tests/domains/test_designer_projects_api.py `
       tests/domains/test_designer_validator.py `
       tests/domains/test_designer_ai_runs.py `
       tests/contracts/runtime/test_designer_blueprint_registration.py -v
# → 23 passed, 1 skipped ✅

# Frontend 빌드
Set-Location "Add In Program\FOMSBrainDesigner"
npm run build
# → ✓ 629 modules transformed, static/designer/index.html 생성 ✅
```

---

## 3. DB 테이블 (7개)

```
designer_projects
designer_project_versions
designer_ontology_versions
designer_ai_runs
designer_corrections
designer_rule_candidates
designer_embeddings
```

Alembic down_revision 체인:
```
add_orders_erp_stage_updated_at
  └─ designer_ax_initial
       └─ designer_pgvector
```

---

## 4. API 엔드포인트 (9개)

| Method | URL | 역할 |
|---|---|---|
| GET | /api/designer/projects | 목록 |
| POST | /api/designer/projects | 생성 (기본 design 자동 버전 생성) |
| GET | /api/designer/projects/:id | 상세 |
| POST | /api/designer/projects/:id/versions | 버전 저장 (validator gate) |
| POST | /api/designer/validate | 검증만 (저장 없음) |
| POST | /api/designer/ai-runs | LangGraph run 생성 |
| GET | /api/designer/ai-runs/:id | run 상태 조회 |
| POST | /api/designer/ai-runs/:id/resume | interrupt approve/reject |
| GET | /api/designer/ontology/current | 활성 ontology 규칙 |

---

## 5. 남은 작업 (MVP 이후)

| 작업 | 우선순위 | 비고 |
|---|---|---|
| PDF/JPG 도면 vision extraction | 중 | B2 계획서 §2 MVP 제외 항목 |
| BOM 고도화 (재료비, 재단표) | 중 | `bom.py` stub 상태 |
| ontology evolution 자동화 | 낮 | `evolution.py` stub, 인간 승인 필수 |
| 실제 LLM 연동 (parse_intent) | 중 | DESIGNER_AI_FAKE=0 모드 완성 |
| pgvector 실제 임베딩 모델 연결 | 낮 | DESIGNER_FAKE_EMBEDDING=0 모드 |
| CNC/DXF 도면 출력 | 낮 | MVP 제외 |

---

## 6. 기존 `/wdplanner` 교체 조건

기존 `/wdplanner`(WDPlanner V1)를 `/wdplanner-v2`(FOMS Brain AX Designer)로 교체하려면 다음 조건을 모두 충족해야 한다:

1. **기능 등가성**: V1에서 동작하는 3D 설계 + BOM 생성이 V2에서도 동일하게 동작
2. **AI 실제 연동**: `DESIGNER_AI_FAKE=0` 모드에서 안정적 실행 (LLM API 연동 완료)
3. **pgvector 운영**: Railway PostgreSQL에 pgvector extension 설치 완료
4. **사용자 수용 테스트**: 실제 사용자 최소 5건 설계 저장 + 검증 통과
5. **ERP regression 없음**: 기존 주문/도면/시공 워크플로우에 영향 없음 확인

교체 시에는 `/wdplanner` route를 `/wdplanner-v2`로 리다이렉트하고, 구 V1 코드는 별도 브랜치로 보존한다.

---

## 7. Stop Rule 준수 확인

| Rule | 상태 |
|---|---|
| `/wdplanner` 제거하지 않음 | ✅ |
| Next.js/Supabase 미도입 | ✅ |
| FOMS main DB 단일 source | ✅ |
| validator 없이 version 저장 없음 | ✅ `persist_result` 이중 가드 |
| invalid design 저장 없음 | ✅ 422 + 그래프 내 차단 |
| pgvector 실패 시 명시적 RuntimeError | ✅ |
| ERP route regression 없음 | ✅ blueprint 등록 순서 유지 |
