# FOMS Brain — Product-Grade Status

> 작성일: 2026-05-14 | 세션: PG-B0 Reality Reset
> 갱신: 각 PG-B* 완료 시 이 파일을 업데이트한다.

## 요약

**현재 상태: ❌ NOT PRODUCT-GRADE**

Design Kernel V1 + Post-V1 seed는 "커널 및 backend seed"다.
아래 gate 중 하나라도 `false`이면 제품 완료를 선언하지 않는다.

## Gate 체크리스트

| Gate ID | 설명 | 담당 Batch | 상태 |
|---|---|---|---|
| gemini_provider_implemented | Gemini API 단일 모델 어댑터 구현 + POC 5장 검증 | PG-B0A | ❌ MISSING |
| extraction_scorecard_implemented | precision/recall/field_score scorecard 알고리즘 구현 | PG-B0A | ❌ MISSING |
| fixture_corpus_17_drawings | 17장 drawing fixture manifest 등록 + expected JSON 사용자 승인 | PG-B2 | ❌ MISSING |
| pii_redactor_implemented | 고객명/전화/주소 pseudonymization + Gemini payload 분리 | PG-B3A | ❌ MISSING |
| drawing_artifact_db_model | DrawingArtifact/Page/Extraction/Candidate 영구 DB 모델 | PG-B3 | ❌ MISSING |
| parts_table_parser_recall_90 | [SR]/[EP]/[DOOR]/[마이다] 등 parts table recall >= 90% | PG-B5 | ❌ MISSING |
| dimension_parser_wdh_95 | W/D/H extraction >= 95% (CV + multimodal merge) | PG-B6 | ❌ MISSING |
| overlay_review_ui | 원본 도면 위 bbox + extracted fields + candidate diff UI | PG-B8 | ❌ MISSING |
| white_workbench_shell | SketchUp desktop-like 흰색 workbench + design system | PG-B1 | ❌ MISSING |
| factory_selector_ui | wardrobe/shoe_rack/kitchen_base/kitchen_wall frontend 연결 | PG-B10 | ❌ MISSING |
| correction_clusterer_implemented | correction clustering + evidence-backed rule candidates | PG-B11 | ❌ MISSING |
| no_auto_ontology_promotion | 자동 온톨로지 승격 금지 invariant | (기존 계약) | ✅ 계약 존재 |

**통과 gate: 1 / 12**

## 현재 실제 구현 수준

```text
✅ schema v2 ontology (ontology_types.py, ontologyTypes.ts)
✅ wardrobe assembly factory
✅ shoe_rack factory (backend seed)
✅ kitchen factory (backend seed)
✅ formula engine (deterministic)
✅ constraint engine (deterministic)
✅ command engine (preview/apply seed)
✅ correction delta (shape + DB model seed)
✅ rule candidate / evolution seed
✅ vision_types.py (VisionInput, DesignGraphCandidate shape)
✅ vision_extractor.py (fake extractor + provider interface)
✅ 118+ designer domain tests passing

❌ Gemini API 실제 연결 없음 — fake_extractor only
❌ 17장 도면 fixture corpus 없음
❌ extraction scorecard 없음
❌ drawing overlay review UI 없음
❌ white SketchUp-like workbench 없음
❌ PII redaction 없음
❌ parts table parser 없음
❌ dimension parser (real) 없음
❌ correction clusterer 없음
```

## 제품급 완료 조건 (PG-B13 closeout 기준)

- [ ] 17 fixture drawings registered and approved
- [ ] Gemini layout extraction scorecard generated
- [ ] parts table recall >= 90%
- [ ] W/D/H extraction >= 95%
- [ ] white SketchUp-like workbench screenshot evidence
- [ ] overlay review UI evidence
- [ ] 0 invalid project versions saved
- [ ] no auto promotion of ontology
- [ ] active ontology invariant exists

## 세션별 실행 계획 (PR 분할)

| PR | 세션 | 범위 | 상태 |
|---|---|---|---|
| PR-1 | Session-1 | PG-B0 Reality Reset + Product Contract Freeze | ✅ 이번 세션 |
| PR-2 | Session-2 | PG-B0A Gemini Provider POC + Scorecard Definition | 🔜 다음 |
| PR-3 | Session-3 | PG-B2 Drawing Attachment Corpus + Fixture Harness | ⏳ 대기 |
| PR-4 | Session-4 | PG-B10 Furniture Type UI Integration | ⏳ 대기 |
| PR-5 | Session-5 | PG-B1 White SketchUp-Like Workbench Shell | ⏳ 대기 |
| PR-6+ | Session-6+ | PG-B3~B13 계획서 순서 | ⏳ 대기 |

## 다음 세션 (PR-2 / PG-B0A) 시작 조건

1. Gemini API key 환경변수 이름 사용자 확인 (예: `GEMINI_API_KEY` or `GOOGLE_API_KEY`)
2. 5장 대표 fixture 이미지/PDF 경로 또는 R2 URL 확인
3. `tests/fixtures/drawings/` 디렉터리 생성
4. `foms/services/designer/gemini_provider.py` 신규 구현
5. cost/latency/accuracy POC 리포트 생성
