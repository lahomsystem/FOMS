# FOMS Brain — Lego-Ontology Explainable Design Plan (C-1-C11)

**작성일**: 2026-05-16
**목표**: 도면 → 아웃라인 인식 → 3D 변환 → 레고식 블록 분해 → 블록 라이브러리/온톨로지 → 클릭형 학습
**전제**: B0-B7 기반 자산은 존재하지만, C단계 착수 전 `C-1 Readiness Gate`로 실제 제품 계약을 재검증한다.

> 중요: 이 문서는 C단계 실행 계획이다. B단계의 코드 자산이 일부 구현되어 있어도, `/wdplanner-v2`의 preview/approve/save, 이미지·PDF PII, iframe postMessage, DesignCase/RAG 연결 계약이 green임을 C-1에서 확인하기 전에는 C1 구현으로 넘어가지 않는다.

---

## 0. 사용자 요구사항 (원문 매핑)

| # | 요구사항 | 핵심 동사 |
|---|----------|----------|
| **R1** | 도면 아웃라인 그대로 따서 3D 변환 → 내부 구조/파츠를 레고식 모듈로 변환·저장 (macro→micro, 치수 적용) | **외곽 인식 + 분해** |
| **R2** | 3D 변환 후 모든 파츠/통/라인을 레고 블럭으로 변환 → 치수·모양 변경 가능 (SketchUp식) | **블럭화 + 편집** |
| **R3** | 저장된 블럭을 불러와 조립 가능 (SketchUp식) → 없는 파츠는 직접 그리기 | **블록 라이브러리 + 스케치** |
| **R4** | 레고 블럭/파츠 관계를 온톨로지화 (AI 초안 작성 및 저장 → 재호출) | **온톨로지 학습** |
| **R5** | 3D 가구의 모든 부분 클릭 가능 → 사용자가 "왜 이렇게 설계됐는지" 설명 → FOMS 학습 → AI 직접 설계/지원 | **설명 기반 학습** |

---

## 1. 현재 코드 자산 (활용 가능)

### Frontend (`Add In Program/FOMSBrainDesigner/src/`)
| 파일 | 역할 | R1-5 활용도 |
|------|------|------------|
| `domain/ontologyTypes.ts` | DesignGraph v2 (Assembly/Module/Component) | R1, R2, R4 — 그대로 사용 |
| `domain/componentCatalog.ts` | Material + ComponentKindMeta (10종) | R2, R3 — 확장 |
| `domain/blockPlacement.ts` | LEGO_BLOCK_DEFS (6종 하드코딩) | R2, R3 — DB 기반 동적 로드로 교체 |
| `ui/LegoBlockPalette.tsx` | 블록 추가 팔레트 | R2, R3 — 라이브러리 UI 확장 |
| `ui/InspectorPanel.tsx` | 선택된 부재 편집 | R5 — annotation 필드 추가 |
| `ui/AIDesignPanel.tsx` | 자연어 → 설계 (LUI) | R4, R5 — 학습 결과 반영 |
| `stores/designerStore.ts` | Zustand 상태 + 명령 | R2-5 — saveAsBlock/loadFromLibrary 액션 추가 |

### Backend (`foms/services/designer/`)
| 파일 | 역할 | R1-5 활용도 |
|------|------|------------|
| `layout_graph_mapper.py` | Gemini → DesignGraph (B1 완료) | R1 — 아웃라인 폴리곤 처리 추가 |
| `gemini_provider.py` | Vision 추출 프롬프트 | R1, R4 — outline_polygon + block_ontology 항목 추가 |
| `ontology_mapper.py` | furniture_type 해석 + factory_params | R1 — 보조 |
| `design_case_memory.py` (PG-L1) | 승인된 케이스 저장 | R5 — explanation 필드 확장 |
| `design_retrieval.py` (PG-L2) | RAG 검색 | R4, R5 — 블록/설명 인덱싱 |
| `product_archetype_learning.py` (PG-L3) | 아키타입 마이닝 | R4 — 블록 패턴 발견 |
| `evolution.py` | 룰 후보 + 사람 승인 | R5 — 설명→룰 승격 |
| `vector_memory.py` | 임베딩 저장 | R4, R5 — 설명 임베딩 |
| `corrections.py` | 사용자 수정 기록 | R5 — explanation과 통합 |

### DB Models (`foms/persistence/designer/models.py`)
| 모델 | 역할 | 변경 필요 |
|------|------|----------|
| `DesignerProject` / `Version` | 설계 버전 | 없음 |
| `DesignerExtractionCandidate` | 추출 후보 (B2 완료) | 없음 |
| `DesignerDesignCase` | 승인 케이스 (PG-L1) | `explanation_json` 추가 |
| `DesignerCorrection` | 수정 델타 | `rationale_text` 추가 |
| `DesignerOntologyVersion` | 룰 온톨로지 | 없음 (block ontology는 신규) |

### 갭 분석 (신규 필요)
- **외곽선 추출**: Gemini 프롬프트에 `outline_polygon` 항목 + rect/L/T/U/irregular 등 다양한 레이아웃 처리
- **블록 라이브러리 DB**: `DesignerReusableBlock` 모델 신규
- **블록 온톨로지 DB**: `DesignerBlockOntologyVersion` + `DesignerBlockOntologyRelation` 모델 신규 (블록-블록 관계)
- **설명 기반 학습**: `DesignerComponentExplanation` 모델 신규
- **2D 스케치 → 3D 익스트루드**: 신규 컴포넌트 + API
- **Annotation API**: `/api/designer/explanations`

---

## 2. 하드 계약 (절대 금지/필수)

다음은 모든 Phase에서 깨지면 안 되는 계약:

- ❌ **AI auto-promotion 금지**: 블록 라이브러리/온톨로지 등록은 **반드시 사람 승인** 거친다 (B5 계약 동일)
- ❌ **Production Railway push 금지**: 사용자 명시 승인 없이 production 브랜치 푸시 안 함
- ❌ **LangGraph 직접 design_json 변경 금지**: 검증자 우회 금지 (B3 계약 동일)
- ❌ **PII 누설 금지**: 설명 텍스트도 PII 레닥션 거친 후 학습 저장
- ❌ **빈 그래프 저장 금지**: components.length === 0 인 케이스는 project version으로 승격 불가
- ❌ **승인 전 학습 자산 RAG 사용 금지**: `ReusableBlock`, `ComponentExplanation`, `BlockOntologyRelation`은 승인 전에는 AI prompt/RAG/active ontology에 들어가지 않는다.
- ❌ **wildcard postMessage 금지**: C단계 write action은 same-origin 확인 + ack 기반 성공 표시 + CSRF/session fetch 계약을 통과해야 한다.
- ❌ **이미지/PDF 내부 PII 무정책 전송 금지**: OCR/image redaction 불가 시 explicit block 또는 명시적 제한 정책을 C-1에서 확정한다.
- ✅ **모든 신규 모델은 Alembic 마이그레이션 + downgrade 포함**
- ✅ **모든 신규 API는 `{success, data, error}` 응답 형식**
- ✅ **structured_data(JSONB) 수정은 copy.deepcopy + flag_modified**
- ✅ **각 Phase 끝에 `python -c "import app; print('APP_OK')"` 통과**

---

## 3. Phase 분해 (C-1-C11)

### Phase C-1 — Readiness Gate & B-Contract Audit
**기간**: 0.5-1일
**목적**: C단계가 기대하는 B단계 계약이 실제 코드/브라우저 흐름에서 동작하는지 확인

검증 대상:
1. 도면 업로드 → `DesignerExtractionCandidate` persist → 3D preview candidate 생성
2. `ui_state.can_preview_3d`, `can_approve`, `can_save_design_case`가 서로 분리되어 계산·표시됨
3. preview 가능 상태와 approve/save 가능 상태가 UI에서 섞이지 않음
4. iframe `postMessage`가 same-origin 확인, 성공/실패 ack, 성공 toast 지연 표시 계약을 지킴
5. 이미지/PDF 내부 PII 정책이 Gemini 전송 전에 실행되거나 명시적으로 차단됨
6. 승인된 project version만 `DesignerDesignCase`와 RAG/Archetype으로 들어감
7. `learning_upload`, `qa_test`, `generic` 같은 source-only hint만으로 rule candidate가 생성되지 않음

산출물:
- `docs/plans/c-phase-readiness-audit.md`
- C단계 allowed write set 확정:
  - Backend: `foms/services/designer/*`, `foms/persistence/designer/models.py`, `foms/api/designer/*`, `migrations/*`
  - Frontend: `Add In Program/FOMSBrainDesigner/src/domain/*`, `stores/designerStore.ts`, `canvas/DesignerCanvas.tsx`, `canvas/CabinetScene.tsx`, `ui/*`
  - Docs/tests: `docs/plans/*`, `tests/domains/test_designer_*`

수락 기준:
- C1 착수 전 blocker가 0건이거나, 남은 blocker가 C1 범위 안에서 root-cause fix로 처리 가능하다고 명시됨
- `APP_OK`
- 관련 smoke/test 명령과 결과가 audit 문서에 기록됨

### Phase C0 — Contract Freeze & Migration Spec
**기간**: 0.5일
**목적**: 신규 DB 스키마/API 형식 동결, 변경 영향도 분석

산출물:
- `docs/plans/c-phase-contract.md` (이 문서의 부속)
- 신규 모델 스펙:
  - `DesignerReusableBlock`
  - `DesignerReusableBlockVersion` 또는 `geometry_schema_version` 계약
  - `DesignerBlockOntologyVersion`
  - `DesignerBlockOntologyRelation`
  - `DesignerComponentExplanation`
  - `DesignerOutlinePolygon` 또는 `design_graph.assembly.custom_props.outline_polygon` 저장 계약
- 신규 API 스펙 (아래 8.x 항목)
- 기존 `DesignGraph` 호환성 검증 — schema_version 변경 여부 결정 (v2 유지 권장)
- approval/audit 공통 컬럼 계약: `status`, `approved_by_user_id`, `approved_at`, `rejected_by_user_id`, `rejected_at`, `source_type`, `source_id`, `created_by_user_id`

수락 기준:
- 신규 모델 컬럼 타입/제약/FK/인덱스/JSON schema 명세 완료
- 모든 API의 request/response 예시 JSON 작성
- 승인 전 데이터가 RAG/active ontology에 들어가지 않는 query contract 작성
- migration split 순서와 rollback/downgrade 전략 작성
- `APP_OK` + 기존 1438 테스트 통과

---

### Phase C1 — Outline Polygon Detection (R1 기반)
**기간**: 2일
**목적**: 도면에서 외곽 폴리곤 추출 (rect/L/T/U/irregular 등 다양한 레이아웃 인식)

작업:
1. `gemini_provider.py` 프롬프트 확장 — `design_understanding.outline_polygon`:
   ```json
   {
     "outline_polygon": {
       "view": "front|side|top",
       "vertices_mm": [[0,0], [2288,0], [2288,1880], [1376,1880], [1376,2225], [0,2225]],
       "shape_type": "rect|L_shape|T_shape|U_shape|irregular",
       "confidence": 0.9
     }
   }
   ```
2. `outline_polygon_validator.py` 신규 — 폴리곤 닫힘/자가교차/최소면적 검증
3. `layout_graph_mapper.py` 통합 — outline_polygon이 있으면 site_size 대신 폴리곤 기반 module 배치
4. 단위 테스트 10개 (rect/L/T/U + invalid 케이스)
5. Gemini 미반환 시 처리 계약:
   - 자동 추측으로 성공 처리하지 않는다.
   - `blocking_reasons`에 `outline_polygon_missing` 또는 `outline_polygon_invalid:*`를 남긴다.
   - 사용자가 수동 polygon 확정 UI로 보정할 수 있는 후속 경로를 열어둔다.
6. 대표 레이아웃 fixture 세트:
   - rect: 일반 일자 수납장/붙박이장
   - L_shape: ㄱ자/코너형 수납
   - T_shape: 중앙 돌출 또는 보조 라인 결합형
   - U_shape: 양측 날개 또는 ㄷ자형 배치
   - irregular: 보·기둥·배관·벽체 간섭으로 생긴 비정형 외곽

수락 기준:
- 대표 fixture별 `shape_type`이 올바르게 분류되고 `vertices_mm`가 실제 외곽 순서대로 추출됨
- "수납장 — 박재완.png" 도면은 L자 회귀 fixture로 유지하며 `shape_type: "L_shape"`와 vertices 6개 이상 추출
- 기존 단순 rect 도면도 회귀 없음 (B1 32개 테스트 통과 유지)
- invalid/self-intersect polygon은 project version/design case로 승격 불가
- outline polygon이 없어도 기존 rect-only 후보는 기존 계약대로 preview/approve gate를 유지

---

### Phase C2 — Outline → 3D Extrusion (R1 micro)
**기간**: 2일
**목적**: 다양한 외곽 폴리곤 → 3D 어셈블리 (depth로 익스트루드)

작업:
1. `foms/services/designer/outline_to_3d.py` 신규 — 폴리곤 + depth → Assembly + ep/sr/base 자동 생성
2. rectilinear 레이아웃 처리: rect/L/T/U를 사각형 모듈 N개로 자동 분할 (오토파티션 알고리즘)
3. irregular 레이아웃 처리: 안정적으로 분할 가능한 축정렬 polygon은 자동 분할하고, 불가능하면 `partition_requires_manual_confirmation`으로 차단
4. `LayoutMappingResult.design_graph.assembly`에 `outline_polygon` 필드 추가 (custom_props로)
5. Frontend `DesignerCanvas.tsx` / `CabinetScene.tsx`에 폴리곤 기반 렌더 분기 (현재 rect/module box 중심)
6. partition report 저장:
   ```json
   {
     "outline_partition": {
       "algorithm": "rectilinear_partition_v1",
       "source_polygon_id": "outline_...",
       "module_rects": [{"x": 0, "y": 0, "width": 1376, "height": 2225}],
       "warnings": []
     }
   }
   ```

수락 기준:
- rect/L/T/U 대표 폴리곤 → N개 사각 모듈로 자동 분할되어 3D 렌더
- irregular 폴리곤은 자동 분할 가능/수동 확정 필요 상태가 명확히 구분됨
- 치수 자동 적용 (각 모듈의 width/height/depth)
- 화면에서 박스 윤곽이 도면 외곽선과 시각적으로 일치
- partition 실패 시 빈 그래프 저장 금지 + 명시적 blocking reason 반환

---

### Phase C3 — ReusableBlock Model + Save-from-Selection (R2)
**기간**: 2일
**목적**: 사용자가 선택한 컴포넌트/모듈을 재사용 블록으로 저장

DB 신규:
```python
class DesignerReusableBlock(Base):
    __tablename__ = "designer_reusable_blocks"
    id, block_key (uniq), label_ko, category (panel/module/assembly),
    geometry_json (components/relations),
    parameters_json (조정 가능 변수: width_range, height_range...),
    geometry_schema_version, status (draft/approved/rejected/retired),
    created_by_user_id, source_design_case_id, approved_by_user_id, approved_at,
    auto_generated, usage_count, tags_json, created_at, updated_at
```

작업:
1. Alembic 마이그레이션 `designer_c3_reusable_block`
2. `foms/services/designer/block_library.py` 신규:
   - `save_block_from_components(component_ids, label, ...)` — geometry 추출 + 정규화
   - `list_blocks(category, tags)`, `get_block(id)`, `instantiate_block(id, at_position)`
3. API `/api/designer/blocks/` 4개 (save/list/get/instantiate)
4. Frontend `designerStore.saveSelectionAsBlock(label)` + InspectorPanel에 "블록으로 저장" 버튼
5. Frontend `BlockLibraryPanel.tsx` 신규 (좌측 패널)

수락 기준:
- 선택 → 저장 → 라이브러리에 표시 → 새 위치에 인스턴스화 흐름 동작
- block_key 중복 시 422 반환
- AI 초안은 `auto_generated=True`, `status=draft`로만 생성 가능
- `status=approved` 블록만 라이브러리 기본 목록/RAG 후보/AI 조립 후보에 노출
- 사용자 수동 저장 블록도 승인 전에는 active reusable asset으로 쓰지 않는다

---

### Phase C4 — SketchUp-Style Block Library UI (R3)
**기간**: 3일
**목적**: 블록 라이브러리 + 드래그앤드롭 조립

작업:
1. `BlockLibraryPanel.tsx` 카테고리별 그룹 + 미리보기 썸네일 (캔버스 미니 렌더)
2. 드래그앤드롭으로 3D 캔버스에 배치 (R3F + react-dnd)
3. 인스턴스화 후 InspectorPanel에서 파라미터 조정 (block.parameters_json 기반)
4. "현재 선택 → 블록으로 저장" / "라이브러리에서 추가" 양방향 동작
5. 블록 인스턴스 ID 추적 — design_graph.components[i].custom_props.from_block_id

수락 기준:
- 라이브러리에 등록된 블록을 드래그하여 캔버스에 추가 가능
- 같은 블록을 여러 번 인스턴스화 가능 (각 인스턴스 독립 편집)
- block_id가 design_graph 메타데이터에 저장됨

---

### Phase C5 — Freehand Sketch Tool (R3)
**기간**: 3일
**목적**: 라이브러리에 없는 파츠를 직접 그려 블록화

작업:
1. `SketchCanvas.tsx` 신규 — 2D 평면 모드(상면/정면/측면) 토글, 선/사각형/원/폴리곤 도구
2. `sketch_to_block.ts` — 2D 스케치 → ExtrusionSpec (vertices + depth) → Component 변환
3. "스케치 → 블록 저장" 흐름 (C3 reusable_blocks에 저장)
4. 단순 도형(rect/circle)뿐 아니라 자유 폴리곤도 지원 — Three.js `ExtrudeGeometry`

수락 기준:
- 사용자가 정면뷰에서 임의 다각형 그림 → 깊이 입력 → 3D 박스 생성
- 그린 블록을 라이브러리에 저장 가능
- 기존 도형(rect)도 회귀 없음

---

### Phase C6 — Block Ontology Model (R4)
**기간**: 2일
**목적**: 블록 간 관계 온톨로지 (contains/attaches_to/aligned_with)

DB 신규:
```python
class DesignerBlockOntologyVersion(Base):
    __tablename__ = "designer_block_ontology_versions"
    id, version_key, status (draft/active/retired), created_at, approved_by_user_id, approved_at

class DesignerBlockOntologyRelation(Base):
    __tablename__ = "designer_block_ontology_relations"
    id, ontology_version_id, relation_key,
    from_block_key, to_block_key, relation_type, params_json,
    evidence_case_ids_json, evidence_count,
    replay_report_json, status (candidate/approved/rejected/promoted),
    created_at, approved_by_user_id, approved_at
```

작업:
1. Alembic 마이그레이션 `designer_c6_block_ontology`
2. `foms/services/designer/block_ontology_service.py`:
   - `infer_ontology_from_case(design_case_id)` — 케이스에서 블록 인스턴스/위치 분석 → 관계 추출
   - `propose_ontology_relations(min_evidence=3)` — N개 이상 케이스에서 반복되는 관계 후보
   - `approve_relation(relation_id)` — 사람 승인 시에만 active로 승격
3. API 3개 (propose/list/approve)
4. `block_ontology` 룰을 design_understanding.block_ontology_draft로 Gemini 프롬프트에 포함 (AI 초안 작성)

수락 기준:
- 3개 이상 케이스에서 반복되는 관계만 후보로 생성 (B5 evidence gate 동일)
- 사람 승인 없이는 active 온톨로지 변경 불가
- Gemini가 block_ontology_draft 항목 채워서 반환
- relation 단위 승인/거절/재검증이 가능해야 하며, JSON 배열 전체를 한 번에 active로 덮어쓰지 않는다
- replay 실패 relation은 approved/promoted 불가

---

### Phase C7 — Component Explanation Schema (R5)
**기간**: 1.5일
**목적**: 컴포넌트별 "왜 이렇게 설계되었는가" 설명 저장

DB 신규:
```python
class DesignerComponentExplanation(Base):
    __tablename__ = "designer_component_explanations"
    id, design_case_id (FK), component_id_in_graph (str — uuid in design_graph),
    explanation_text (Text, PII-redacted),
    rationale_category (constraint/preference/customer_request/codified_rule),
    confidence (float), created_by_user_id,
    embedding_id (FK to designer_embeddings), usage_count,
    status (draft/approved/rejected/retired),
    approved_by_user_id, approved_at, created_at
```

작업:
1. Alembic 마이그레이션 `designer_c7_component_explanation`
2. `foms/services/designer/explanation_service.py`:
   - `save_explanation(component_id, text, ...)` — PII 레닥션 + 임베딩 생성
   - `list_explanations_by_case(case_id)`, `search_explanations(query, top_k=10)`
3. API 2개: `POST /api/designer/explanations`, `GET /api/designer/explanations/search?q=...`
4. PII 레닥션은 기존 `pii_redactor.py` 재사용

수락 기준:
- 설명 텍스트의 customer_name/phone/address가 자동 마스킹됨
- 임베딩이 designer_embeddings 테이블에 저장되어 코사인 유사도 검색 가능
- 같은 case의 같은 component_id에 대해 여러 설명 누적 가능 (버전닝)
- `status=approved` explanation만 C9 RAG 컨텍스트로 사용 가능
- draft explanation은 작성자/관리자 검토 UI에서는 보이지만 AI prompt에는 들어가지 않음

---

### Phase C8 — Clickable 3D + Annotation UI (R5)
**기간**: 2일
**목적**: 3D 화면에서 컴포넌트 클릭 → 설명 입력 UI

작업:
1. `InspectorPanel.tsx`에 "설계 의도" 섹션 추가 — textarea + 카테고리 선택
2. 저장 시 `/api/designer/explanations` 호출 + 기존 explanations 목록 표시
3. 우측에 "이 부분과 비슷한 설계 의도" 패널 — explanation 검색으로 유사 케이스 표시
4. 키보드 단축키 `E` — 선택된 컴포넌트의 설명 편집

수락 기준:
- 컴포넌트 클릭 → InspectorPanel에 explanation textarea 표시
- 저장 후 같은 컴포넌트 재선택 시 explanation 로드됨
- "유사 설명" 패널에 임베딩 유사도 기반 결과 3-5개 표시

---

### Phase C9 — Explanation-Augmented Retrieval (R5)
**기간**: 1.5일
**목적**: AI 설계 시 explanation을 RAG 컨텍스트로 활용

작업:
1. `design_retrieval.py`에 `build_explanation_rag_context()` 추가 — 사용자 요청 텍스트로 explanation 검색 → Gemini 프롬프트에 주입
2. `langgraph_workflows.py`의 `design_assist_graph`에 `explanation_retrieval` 노드 추가
3. AIDesignPanel에서 "참고된 설명" 카드 표시 (어떤 explanation이 사용됐는지 표시)
4. 학습 루프: 사용자가 AI 제안을 승인 → 그 explanation의 `usage_count++`
5. retrieval filter:
   - `ComponentExplanation.status == approved`
   - linked `DesignerDesignCase`가 approved project version 기반
   - prompt payload는 PII-free sanitized projection만 사용

수락 기준:
- 사용자 자연어 입력 → AI가 관련 explanation 3-5개를 retrieval로 참고
- "참고된 설명" UI에서 어떤 케이스/컴포넌트의 explanation이 사용됐는지 명시
- explanation이 없을 때도 정상 동작 (graceful)
- retrieval 실패는 silent success가 아니라 warning/report로 남김
- draft/rejected explanation이 prompt에 들어가지 않는 테스트 통과

---

### Phase C10 — Test Coverage + Performance Contract
**기간**: 2일
**목적**: B7 수준의 운영 안정성 확보

작업:
1. 신규 모델/관계/API에 대한 도메인 테스트 60개+ 추가
2. 성능 계약 (p95):
   - outline_polygon validator/partition < 100ms (Gemini 호출 시간 제외)
   - Gemini outline extraction latency/cost는 별도 metric으로 기록
   - sketch_to_block extrusion < 50ms
   - explanation search (top 5) < 200ms
   - block library load (100개) < 150ms
3. 보안 테스트: PII 레닥션이 explanation에서도 동작 (test_explanation_pii_security.py)
4. CI 통합: 기존 1438 + 신규 60 = 1500+ 테스트 통과
5. approval-gate 테스트:
   - draft block/explanation/relation은 RAG/active UI에 노출되지 않음
   - wildcard postMessage가 남아 있으면 frontend security test 실패

수락 기준:
- 전체 테스트 1500+ 통과
- 모든 성능 p95 계약 통과
- PII 보안 테스트 통과
- APP_OK

---

### Phase C11 — Documentation + Railway Staging Smoke
**기간**: 1일
**목적**: 운영 인계 + Railway deploy 브랜치 검증 (production은 사용자 승인 필요)

작업:
1. `docs/architecture/lego-ontology-design-explainable.md` 통합 문서
2. `docs/AI_STATUS.md` 갱신 — C-1-C11 완료 상태 기록
3. `docs/AI_CHANGELOG.md` 각 Phase 항목 추가
4. Railway deploy 브랜치 푸시 → 마이그레이션 적용 확인 → 핵심 흐름 4종 smoke
   - 도면 업로드 → 외곽 인식 → 3D 로드
   - 컴포넌트 선택 → 블록 저장 → 라이브러리 호출
   - 컴포넌트 클릭 → 설명 입력 → 저장
   - AI 패널 자연어 입력 → explanation RAG → 후보 생성

수락 기준:
- Railway deploy에서 4종 흐름 모두 동작
- C단계 마이그레이션 모두 적용 성공
- production push는 **사용자 명시 승인 후에만**

---

## 4. 우선순위 (사용자 가치 기준)

| 순위 | Phase | 사용자 가치 | 이유 |
|------|-------|------------|------|
| 0 | C-1+C0 | 필수 — C단계 착수 가능 여부 확정 | B계약 미검증 상태에서 C1을 시작하면 PII/승인/RAG 오염 가능 |
| 1 | C1+C2 | 즉각 — 다양한 레이아웃 도면이 정확히 3D로 변환됨 | L자뿐 아니라 rect/T/U/비정형까지 외곽 기반 설계 대응이 현재 가장 큰 미해결 문제 |
| 2 | C3+C4 | 큰 — 재사용 가능한 부품 라이브러리 구축 시작 | 누적 자산화 효과 |
| 3 | C7+C8 | 중대 — 설계 의도 학습 시작 | 장기 AX 핵심 자산 |
| 4 | C9 | 큰 — AI 설계 정확도 향상 시작 | C7-8의 가치 실현 |
| 5 | C6 | 중 — 블록 관계 자동 학습 | 블록과 승인 케이스가 쌓인 뒤 가치 상승 |
| 6 | C5 | 중 — SketchUp 수준 자유도 | 고급 사용자 대상, 코어 learning loop 이후 진행 권장 |

권장 실행 순서:

```text
C-1 -> C0 -> C1+C2 MVP -> C3+C4 -> C7+C8 -> C9 -> C6 -> C5 -> C10 -> C11
```

---

## 5. 위험 요소 & 완화

| 위험 | 영향 | 완화 |
|------|------|------|
| B단계 preview/approve/save 계약 미검증 | C단계 학습 자산 오염 | C-1 Readiness Gate에서 blocker 0건 확인 전 C1 금지 |
| Gemini의 outline_polygon 미반환 (현재 layout_graph도 못 채움) | C1 정확도 ↓ | 자동 성공 처리 금지 + blocking reason + 사용자 폴리곤 수동 확정 UI |
| 블록 라이브러리 누적 시 검색 성능 저하 | C3+ UX 저하 | 카테고리 인덱스 + Postgres GIN(tags_json) + 페이지네이션 |
| 이미지/PDF 내부 PII가 Gemini로 전송됨 | 법적/보안 | OCR/image redaction 또는 explicit block 정책을 C-1/C0에서 확정 |
| Explanation PII 누설 | 법적/규정 | C7에서 기존 pii_redactor 재사용 + prompt projection 보안 테스트 필수 |
| 사용자가 잘못된 설명을 입력 → 학습 오염 | RAG 품질 ↓ | draft 기본 + 승인된 explanation만 RAG 사용 + 사용량 기반 신뢰도 |
| wildcard postMessage로 외부 origin write action 가능 | 보안/데이터 손상 | same-origin check + CSRF/session fetch + ack 기반 UI |
| 3D 렌더 폴리곤 처리 복잡도 (L/T/U/irregular) | C2 일정 ↑ | 1차부터 rect/L/T/U 대표 fixture를 지원하고, irregular는 자동 분할 가능/수동 확정 필요 상태를 명확히 분리 |

---

## 6. 비-목표 (이번 계획 범위 밖)

- 도면 → 외곽 인식의 컴퓨터비전 직접 구현 (Gemini에 위임 유지)
- 다중 사용자 동시 편집 (CRDT/OT)
- 모바일 터치 최적화
- 외부 CAD 파일(IGES/STEP) 임포트/익스포트
- 음성 인식 LUI

---

## 7. 추정 일정

| Phase | 일정 (영업일) | 누적 |
|-------|--------------|------|
| C-1 | 0.5-1 | 0.5-1 |
| C0 | 0.5 | 1-1.5 |
| C1 | 2 | 3-3.5 |
| C2 | 2 | 5-5.5 |
| C3 | 2 | 7-7.5 |
| C4 | 3 | 10-10.5 |
| C7 | 1.5 | 11.5-12 |
| C8 | 2 | 13.5-14 |
| C9 | 1.5 | 15-15.5 |
| C6 | 2 | 17-17.5 |
| C5 | 3 | 20-20.5 |
| C10 | 2 | 22-22.5 |
| C11 | 1 | 23-23.5 |

**총 ~23-24 영업일 (≈ 5주)**. C1+C2를 먼저 단독 출시(MVP)하되, C-1/C0 gate 통과 후에만 시작한다.

---

## 8. API 신규 명세 (요약)

| Endpoint | 메서드 | 용도 |
|----------|--------|------|
| `/api/designer/blocks` | POST | 선택 → 블록 저장 |
| `/api/designer/blocks` | GET | 목록 (filter by category/tags) |
| `/api/designer/blocks/<id>` | GET | 상세 |
| `/api/designer/blocks/<id>/instantiate` | POST | 새 위치에 인스턴스화 |
| `/api/designer/explanations` | POST | 컴포넌트 설명 저장 |
| `/api/designer/explanations/search` | GET | 임베딩 유사도 검색 |
| `/api/designer/block-ontology/propose` | POST | 관계 후보 제안 (사람 승인 전) |
| `/api/designer/block-ontology/relations` | GET | 관계 후보/승인 관계 목록 |
| `/api/designer/block-ontology/<id>/approve` | POST | 사람 승인 (active 승격) |
| `/api/designer/block-ontology/<id>/reject` | POST | 관계 후보 거절 |

모든 응답: `{success, data, error}` 형식.

API 공통 계약:
- write API는 로그인 세션 + CSRF 검증을 통과해야 한다.
- active/RAG 조회 API는 `status=approved` 또는 `status=active` 데이터만 기본 반환한다.
- draft/rejected 데이터는 관리자/검토 화면에서만 명시 옵션으로 조회한다.
- 중복/검증 실패는 400/409/422 중 하나로 안정된 error code를 반환한다.

---

## 9. 데이터 흐름 (R1-R5 통합)

```
[1] 도면 업로드
      ↓ Gemini Vision (outline_polygon + layout_graph + block_ontology_draft 요청)
[2] layout_graph_mapper + outline_to_3d
      ↓ DesignGraph v2 (외곽 폴리곤 기반 모듈 + 컴포넌트)
[3] 3D 편집기 로드 (graph-first)
      ↓ 사용자가 컴포넌트 클릭 → InspectorPanel
[4] (R2) 치수/모양 수정  → DesignerCorrection 기록
    (R3) "블록으로 저장" → DesignerReusableBlock 생성
    (R5) "설계 의도 입력" → DesignerComponentExplanation + 임베딩
      ↓ 사용자/관리자 승인 후 active 학습 자산으로 승격
[5] design_case_memory (PG-L1)
      ↓ 누적
[6] (R4) block_ontology_service.propose_ontology_relations
    (R5) design_retrieval.build_explanation_rag_context
      ↓ 후속 AI 설계 요청 시
[7] AI Design Panel — approved explanation + approved block library + active ontology만 RAG로 사용
      ↓
[8] AI가 그린 초안 → 사용자가 다시 검토/수정 → loop
```

---

## 10. Definition of Done (전체)

- ✅ C-1 Readiness Gate 통과 + audit 문서 작성
- ✅ 신규 DB 모델/관계 + Alembic up/down + `APP_OK`
- ✅ 신규 API + `{success, data, error}` 형식 + 단위 테스트
- ✅ Frontend 컴포넌트 6개+ 추가 (BlockLibraryPanel, SketchCanvas, ExplanationEditor 등)
- ✅ 1500+ 테스트 통과 (기존 1438 + 신규 ~60)
- ✅ 성능 p95 계약 4종 통과
- ✅ PII 보안 테스트 통과
- ✅ same-origin postMessage + CSRF/session fetch write contract 통과
- ✅ draft/rejected block/explanation/ontology relation이 RAG/active UI에 노출되지 않음
- ✅ Railway deploy 브랜치 smoke 4종 통과
- ✅ Production push는 **사용자 명시 승인 후에만**
- ✅ 문서: AI_STATUS.md, AI_CHANGELOG.md, 통합 아키텍처 문서

---

**Plan Owner**: nathan
**Reviewers**: (TBD — 코드 리뷰어 + 보안 리뷰어 지정)
**시작 조건**: 사용자가 본 계획서 승인 + C-1 Readiness Gate 우선 시작 합의
