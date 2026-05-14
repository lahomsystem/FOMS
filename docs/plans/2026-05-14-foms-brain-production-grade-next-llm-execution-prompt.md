# FOMS Brain Production-Grade Product — Next LLM Execution Prompt
> 작성일: 2026-05-14 | 용도: 다음 LLM/Cursor Agent가 FOMS Brain을 제품급으로 구현하기 위한 실행 프롬프트

아래 프롬프트를 다음 LLM에게 그대로 전달한다.

```text
너는 FOMS 프로젝트의 senior product implementation agent다.

목표:
docs/plans/2026-05-14-foms-brain-production-grade-product-plan.md 를 기준으로 FOMS Brain을 실제 제품급으로 구현하라.

중요한 현실 인식:
기존 Design Kernel V1 / Post-V1은 “커널 및 backend seed”다.
사용자가 요구한 제품은 월 50~100장 학습용 첨부 도면 이미지/PDF를 실제로 이해하고,
원본 도면 위 overlay로 검수하고,
SketchUp desktop-like workbench에서 레고 블럭처럼 직접 설계하거나,
AI에게 요청해 자동 설계하고,
correction과 도면 corpus를 학습 후보로 만들고,
replay + human approval 후 ontology/design reasoning rule을 승격하는 제품이다.

절대 규칙:
1. fake extractor만으로 제품 완료라고 말하지 마라.
2. 첨부 도면 fixture corpus 없이 제품 완료라고 말하지 마라.
3. Gemini API 단일 모델 라우팅 결정 없이 PG-B4~B7을 구현하지 마라.
4. scorecard algorithm 없이 “95%/90% 정확도”를 주장하지 마라.
5. Vision/LUI 결과를 validator/human review 없이 project version으로 저장하지 마라.
6. AI가 production ontology rule을 자동 승격하지 마라.
7. UI를 SketchUp desktop-like로 재작성할 때 design system과 visual regression baseline 없이 진행하지 마라.
8. 기존 /wdplanner를 제거하지 마라.
9. FOMS Flask modular monolith + static add-in 경계를 유지하라.
10. ERP/order route regression이 있으면 즉시 중단하고 원인을 보고하라.

반드시 먼저 할 일:

STEP 0 — Source Truth 확인
- docs/AI_STATUS.md 읽기
- docs/harness/policy/DECISIONS.md에서 foms-brain 결정 확인
- docs/ARCHIVE_INDEX.md에서 foms-brain 계획 확인
- docs/plans/2026-05-13-foms-brain-design-kernel-v1-execution-plan.md 읽기
- docs/plans/2026-05-14-foms-brain-post-v1-roadmap-plan.md 읽기
- docs/plans/2026-05-14-foms-brain-production-grade-product-plan.md 끝까지 읽기
- 실제 소스 확인:
  - foms/services/designer/*
  - foms/services/designer/factories/*
  - foms/api/designer/*
  - foms/persistence/designer/*
  - Add In Program/FOMSBrainDesigner/src/*
  - tests/domains/test_designer_*.py

STEP 1 — 제품급 Gap Matrix 작성
다음 형식으로 gap matrix를 작성하라.

- 계획 항목
- 기대 파일
- 실제 파일 존재 여부
- 실제 동작 여부
- fixture/test 존재 여부
- 판정: done / partial / missing
- 필요한 조치

partial은 done이 아니다.

STEP 2 — 사용자 결정 필요사항을 확인하라
다음 사용자 결정사항은 이미 주어졌다. run record에 그대로 기록하라.

1. 도면은 학습용 corpus다.
2. 궁극 목표 1: 사용자가 기본장/커스텀장을 레고 블럭처럼 직접 설계한다.
3. 궁극 목표 2: AI가 도면을 학습해 도면 설계 전문 AI가 되고, 사용자 설계를 보조하거나 요청만으로 자동 설계한다.
4. 학습 도면 처리량: 월 50~100장.
5. 고객명/전화/주소 수집은 내부 학습용으로 허용된다.
6. expected JSON은 AI 초안 생성 후 사용자가 승인/수정한다.
7. UI 기준은 SketchUp desktop이다.
8. 직접 설계 UX와 자동 설계 AI를 둘 다 1급 목표로 둔다.
9. OCR 단독이 아니라 Gemini API를 통합적으로 사용한다.
10. Claude/Codex는 사용하지 않는다. Gemini가 전체 통합 담당/최종 판단자다.
11. API 비용은 실제 발생량 기준으로 추적한다.
12. 고객명/전화/주소는 외부 유출 금지다. Gemini API payload는 pseudonymized/redacted 값만 사용한다.

아직 확인이 필요한 것은 API key를 어떤 환경변수/secret 경로로 제공할지뿐이다.

STEP 3 — PR/세션 단위로 실행
한 세션에서 전체 PG-B0~PG-B13을 끝내려고 하지 마라.
아래 순서로 분할 실행한다.

PR-1 / Session-1:
- PG-B0 Reality Reset + Product Contract Freeze

PR-2 / Session-2:
- PG-B0A Gemini Provider POC + Scorecard Definition

PR-3 / Session-3:
- PG-B2 Drawing Attachment Corpus + Fixture Harness

PR-4 / Session-4:
- PG-B10 Furniture Type UI Integration

PR-5 / Session-5:
- PG-B1 White SketchUp-Like Workbench Shell

PR-6+:
- PG-B3~B13, 계획서 순서에 따라 별도 PR/세션

STEP 4 — Batch별 구현 요약

PG-B0:
- 제품급 미완성 상태를 문서/test로 명확히 고정
- fake extractor를 제품 완료로 표시 금지
- product-grade contract tests 추가

PG-B0A:
- Gemini 단일 모델 POC
- 5장 대표 fixture로 POC
- cost/latency/accuracy 기록
- scorecard algorithm 구현
- red/black dimension CV POC 기록

PG-B1:
- white SketchUp-like workbench shell 구현
- design system markdown 작성
- visual regression baseline 추가

PG-B2:
- 17장 drawing fixture manifest 생성
- expected JSON AI 초안 + 사용자 승인 상태 기록
- extraction scorecard runner 구현

PG-B3:
- drawing artifact/page/extraction/candidate persistent data model 구현
- intake는 project version을 만들지 않음

PG-B3A:
- PII redaction + model payload builder 구현
- raw 고객명/전화/주소는 내부 보존
- Gemini payload에는 CUSTOMER_001/PHONE_001/ADDRESS_001 형태만 전송
- provider request/response log에 raw PII 금지

PG-B4:
- template classifier + Gemini model router 구현
- real provider env-gated
- Korean parts table score 별도 측정

PG-B5:
- parts table parser 구현
- [SR]/[EP]/[DOOR]/[마이다]/[옷봉]/보조목 parsing
- fixture item recall >= 90%

PG-B6:
- dimension/view geometry parser 구현
- red/black dimension + line detection은 CV candidates와 multimodal AI text/geometry blocks merge
- W/D/H extraction >= 95%

PG-B7:
- ontology mapper + candidate graph builder
- no candidate auto-approved
- unresolved_fields 정확히 표시

PG-B8:
- drawing review overlay UI
- original drawing + bbox + extracted fields + candidate diff
- user correction -> CorrectionDelta

PG-B9:
- product-grade editor tools
- select/move/dimension/split module tools
- undo/redo
- validator bypass 금지

PG-B10:
- frontend factory selector
- wardrobe/shoe_rack/kitchen_base/kitchen_wall UI 연결

PG-B11:
- correction clusterer + evidence-backed rule candidates
- replay against fixture corpus
- fail_count > 0 blocks promotion

PG-B12:
- performance/security/observability
- bundle analysis before size target enforcement
- upload type/size restrictions
- PII redaction

PG-B13:
- full QA/canary/release closeout
- 17 fixtures processed
- extraction scorecard evidence
- white workbench screenshot evidence

STEP 5 — 검증

공통:
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_designer_* -q
Set-Location "Add In Program\\FOMSBrainDesigner"; npm run build

제품급 추가:
- drawing fixture manifest tests
- extraction scorecard tests
- Gemini provider POC report
- visual regression screenshot tests
- performance tests
- staging browser QA

완료 조건:
- 17 fixture drawings registered and approved
- Gemini layout extraction scorecard generated
- parts table recall >= 90%
- W/D/H extraction >= 95%
- white SketchUp-like workbench screenshot evidence
- overlay review UI evidence
- 0 invalid project versions saved
- no auto promotion of ontology
- active ontology invariant exists

최종 보고:
1. 구현 요약
2. 계획서 대비 1:1 체크리스트
3. 변경 파일 inventory
4. 검증 명령/결과
5. scorecard 결과
6. screenshot/QA evidence
7. 남은 범위
8. 커밋/푸시 여부
```
