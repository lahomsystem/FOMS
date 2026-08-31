# 정산 대시보드 목업 진행 원장 (2026-08-31)

요청: 날짜별 출고가 기준 정산 대시보드 신설 — ERP 딥리서치 + 재무 raw data 기반 + 페르소나별 요구 + 세련된 디자인 + 직관적 시각화 + 3버전 목업 → 브라우저 표시. 멀티에이전트 병렬, CEO 총괄.

산출물 위치: `docs/design/mockups/settlement-dashboard-v{1,2,3}-*.html` (자기완결 HTML, 외부 CDN 금지)

## Tasks

| T | 내용 | 완료 기준 | 상태 |
|---|------|-----------|------|
| T1 | ERP 정산 대시보드 트렌드 리서치 (웹) | scratchpad/research_erp_trends.md 5섹션 | DONE (본문 검수) |
| T2 | FOMS 재무 raw data 인벤토리 (+로컬 DB 집계) | scratchpad/research_foms_finance_data.md 5섹션 | DONE (로컬 DB는 QA 시드 10건뿐 — 규모는 가정치, 운영 실측은 후속) |
| T3 | 이해관계자 페르소나 데이터 요구 | scratchpad/research_personas.md 4섹션 | DONE (FINANCE_MUTATION 정책·completion_dashboard 재사용 근거 확보) |
| T4 | CEO 종합 → 디자인 브리프 작성 | scratchpad/design_brief.md (공통 데이터셋·버전별 방향) | DONE |
| T5 | 목업 V1 (경영진 요약) 빌드 | 파일 존재 + 차트 렌더 + dataviz 검증 | DONE (43KB, 팔레트 PASS, 외부요청 0) |
| T6 | 목업 V2 (경리/수금 실무) 빌드 | 파일 존재 + 차트 렌더 + dataviz 검증 | DONE (57KB, 그리드 31행 — aging 27건 정합 우선, 팔레트 PASS) |
| T7 | 목업 V3 (분석 스테이션) 빌드 | 파일 존재 + 차트 렌더 + dataviz 검증 | DONE (50KB, 다크 팔레트 PASS, 원가/마진 단어 0) |
| T8 | CEO 리뷰 + 수정 반영 | 3파일 리뷰 판정 기록 | DONE — 헤드리스 스크린샷 3장 직접 검수: 렌더 정상, 수치 정합(214.3M/38.72M/aging/차감440만/담당자합=100%), 수정 불요. 소소: V3 금액 표기 스타일(₩2.143억)이 V1(2억 1,430만)과 상이 — 비교 목업 허용 |
| T9 | 브라우저 표시 + 한글 보고 | Start-Process 3건 + SendUserFile | DONE |

| T10 | V3 라이트 버전 (사용자 요청 "v3도 밝은 화면으로") | settlement-dashboard-v3-analytics-light.html + 라이트 팔레트 PASS | DONE (50KB, 색만 107줄 변경·콘텐츠 동일, 라이트 팔레트 PASS, 스크린샷 검수) |
| T11 | V1 수정 2건 (사용자 요청): 메인 차트 막대 전환(8월=막대·7월=회색 라인 유지, 누적=영역 유지) + V3식 기간 필터바 이식(사용자 제공 마크업, 라이트 CSS 번안, 실동작 배선) | V1 파일 갱신 + 렌더 콘솔 0 + 스크린샷 검수 | DONE (스크린샷 검수: 막대+비교라인·filterbar knob 토글 확인) |

사용자 피드백(2026-08-31): 3버전 모두 긍정, V3 라이트 변형 요청. 다음 단계 답변 "1. v1" = 목업 고치기(옵션 1) 해석 — V1 선호 신호로 추정, 라이트 완성 후 재확인.

| T12 | 색상 획일성 연구 (사용자: "금액구간별로 달리 할지 / 단조로움 어떻게 할지 디자인 스킬로 연구") | scratchpad/color_study.md (전략 4+·CEO 추천) + docs/design/mockups/settlement-color-study.html 비교 보드 (전략 A금액램프/B지표계열색/C강조/D표면층위) | DONE — 판정: A(금액구간 램프)는 aging처럼 구간=의미 단위일 때만 합법, 매출 막대 적용은 안티패턴(높이가 이미 금액 인코딩). CEO 추천 = B(지표 계열별 색: 매출=파랑·미수=주황 램프·수금=아쿠아·위험=빨강 status) + D(카드 가족 틴트) 병행. 팔레트 6세트 검증 PASS. 스크린샷 검수 완료 |

| T13 | 색상 전략 적용 (사용자 확정: B+D + 매출 막대 금액구간 다이내믹 — A 안티패턴 경고에도 명시 선택). 대상 = 최신 목업 2개(V1 수정본·V3 라이트), "최초 3개 제외" 해석: V2·V3 다크 보존(원본 V1은 이미 수정본으로 대체됨) | 두 파일 적용 + 팔레트 검증 + 스크린샷 검수 | DONE — V1·V3 라이트 모두 적용, 램프 검증 PASS, 외부 참조 0, 스크린샷 직접 검수 완료(금액구간 파랑 램프+범례·주황 aging·아쿠아 수금·가족 틴트 확인), 브라우저 표시·SendUserFile 완료 |

| T14 | 실구현 진입 (사용자 선택) — RPI: 스펙 작성 중. 리서치 5파일을 docs/design/settlement-dashboard-research-2026-08/ 로 보존 완료 | docs/specs/2026-08-31-settlement-dashboard_SPEC.md 존재 + 사용자 승인 대기 | DONE — 12절·마일스톤 4(M1 집계+파리티 테스트/M2 권한+API/M3 템플릿+차트/M4 성능 실측)·열린 질문 6. 검증: 정책 SSOT 실위치=order_mutation_policy.py(페르소나 문서 인용 오류를 스펙이 정정, grep 재확인 완료)·GET 전용이라 manifest 2종 등재 불요(M2에서 게이트 실행 재확인). **사용자 승인 대기** |

| T15 | 스펙 사용자 승인 (2026-08-31) + 운영 읽기전용 실측 1회 허용 | 스펙 상태줄 갱신 | DONE — 본 세션(목업+스펙) 종결 |

**다음 세션 재개 지시(구현)**: `**C 정산 대시보드 구현 — 스펙 docs/specs/2026-08-31-settlement-dashboard_SPEC.md(승인됨·운영 실측 허용) 기준. 순서: Q1·Q2 운영 읽기전용 실측(project_production_live_diagnosis_recipe 절차) → M1 집계 서비스부터. 구현용 progress ledger 신규 작성.`
목업 5파일·리서치 5파일·스펙·원장은 아직 미커밋 — 구현 세션 첫 커밋에 포함할 것.

## 후속 미결
- 운영 DB 실규모(월 건수·금액) 미실측 — 목업 수치는 가정치. 실제 구현 전 운영 읽기전용 1회 조회 권장.
- 실제 구현 시: 신규 read-only 정책(SETTLEMENT_DASHBOARD_READ) 신설 필요(기존 policy는 mutation 전용, GET 미게이트), completion_dashboard 200건 캡 우회한 SQL 집계 필요.

## 결정 사항
- 목업은 docs 산출물 — 운영 코드 아님, RPI 게이트 비대상. 인라인 스타일 금지 규칙은 운영 템플릿용이나, 목업은 자기완결 단일 파일 관례(기존 mockups와 동일)를 따른다.
- 차트: 외부 CDN 없이 인라인 SVG/JS. dataviz 스킬 절차(색은 마지막, validate_palette.js) 적용.
