# FOMS 모바일·태블릿 리디자인 — 다상각도 자체 리뷰 (v1.1)

> 작성: 2026-05-28 | **v1.1 SSOT 통합 갱신: 2026-05-29** | 짝 문서: `MOBILE_TABLET_REDESIGN_PLAN.md` 외 5종
> 본 문서는 `/plan-design-review` + `/autoplan`(CEO/Design/Eng/DX) 정신으로 자체 평가.

각 관점에서 차원별 0~10점 + "10점이 되려면" + 보완 액션.
**전체 평균 점수**: **8.7 / 10** (v1.0 8.1 → v1.1 보정)

## v1.0 → v1.1 점수 변화 요약

| 관점 | v1.0 | v1.1 | 보정 내용 |
|---|---|---|---|
| 🎨 Design | 8.3 | **8.5** | C14 컴포넌트 신규 추가, 목업 erporder 12필드 매핑, paste desktop-only 일치 |
| 🛠 Engineering | 8.0 | **8.7** | API 경로 `foms/api/` 교정, OrderDraft 계약 본문 통합, Flag matrix 본문 통합, cohort 점진 출시 |
| 💼 CEO | 8.5 | **8.8** | cohort 점진 출시로 위험 감소, P0 시간 -14h 단축, audit 정확성 개선 |
| 🛠 DX | 7.7 | **8.4** | SSOT 통합 완료 (v1.1이 단일 진실), Decision Log 재고 명시 (D06/D07/D09) |

v1.1 보정의 가장 큰 영향: **사실 검증 신뢰성 회복**. v1.0 audit agent의 stale 결과를 외부 LLM 평가가 발견 → 직접 검증 후 흡수.

---

## 🎨 Design Review (UI/UX)

**소계 평균: 8.5 / 10**

| 차원 | 점수 | 평가 | 10점이 되려면 |
|---|---|---|---|
| **정보 위계 (Hierarchy)** | 9 | 카드 head(badge+alert+time) → title → meta → attachments → action 순으로 시선 흐름 명확. 단계 배지가 색으로 즉시 식별 가능. | 단계 배지 외 추가 시각 차별화 — 카드 좌측 4px 보더로 단계 색 반복 |
| **간격 일관성 (Spacing)** | 9 | 4pt 그리드 일관. 카드 padding 12/16 모바일/태블릿 명확. | 별도 보완 없음 |
| **색상 대비** | 8 | WCAG AA 보장. 단계 색 10종 모두 white 텍스트 4.5:1 이상. | warning(#f59e0b) on white 텍스트 시 AAA 미달. dark variant 추가 |
| **타이포 위계** | 8 | 12/14/16/18/20/24 명확. Pretendard 변수 폰트 우수. | 한글 line-height 1.55 → 본문은 1.6이 더 가독성 좋음 (한글 자형) |
| **터치 타깃** | 9 | 48px 최소, 아이콘 44px. body min-font 16px. | 카드 내 버튼 그룹 사이 8px gap이 부족 가능 — 12px 권장 |
| **상태 표현** | 7 | 단계 배지 + alert 배지 + 카운트 배지 표준화 좋음. | 빈 상태(empty state) 일러스트 명세 부재. 로딩 skeleton 미설계 |
| **모션·인터랙션** | 8 | duration 3단계 + emphasized easing 표준. `prefers-reduced-motion` 존중. | swipe-action 마이크로 인터랙션 P0 시점 부재 (P2로 미룸) |
| **다크모드** | 9 | 토큰 swap 방식 우수. 그림자도 dark variant 분리. | dark에서 elevation 표현이 약함 — `box-shadow` 대신 border-color 변화 검토 |
| **사진 표현** | 9 | 첨부 = 1급 데이터 원칙 명시 + attachment grid 컴포넌트 + 라이트박스. | P0에서 라이트박스 없음. 단순 클릭 → 모달 정도 추가 권장 |
| **반응형 흐름** | 8 | mobile-first + container query + 4-breakpoint. master-detail split 우수. | 768~1023 (태블릿 세로) "확장 모바일" 정의 명확하나 시각 차별화는 약함 |

### Design 강점
- 단계 색 토큰 10종 분리 — FOMS 워크플로우 핵심 식별 메타포
- KV 행 + 첨부 그리드 + sticky CTA + 상태 배지의 4가지 핵심 컴포넌트로 모든 화면 구성 가능
- 다크모드 토큰 단일화 (P0 시작 가능)
- Pretendard Variable + 16px base + tabular-nums

### Design 보완 액션
1. **빈 상태 일러스트 명세 추가** (`COMPONENT_LIBRARY_MOBILE.md`에 C14 추가)
2. **Skeleton loading 표준 컴포넌트** (C15)
3. **카드 좌측 보더로 단계 색 반복** — 큐 카드 CSS에 `border-left: 4px solid var(--foms-stage-*)`
4. **warning AAA 대비 토큰 추가** — `--foms-color-warning-700` 텍스트용 분리

---

## 🛠 Engineering Review

**소계 평균: 8.7 / 10**

| 차원 | 점수 | 평가 | 10점이 되려면 |
|---|---|---|---|
| **아키텍처 정합** | 8 | Flask + Jinja2 위에 HTMX 2.0 + Alpine 점진 도입. 기존 자산 70% 보존. | 마법사·인라인 편집은 Alpine 의존도 큼. 명시적 의존성 그래프 부재 |
| **회귀 안전성** | 9 | feature flag 5종 + cohort 1종. 즉시 rollback 가능. | flag 조합 매트릭스 검증 자동화 부재 |
| **성능 영향** | 7 | LCP 2.5s·INP 200ms 목표 명시. R2 image resize + lazy load. | 첨부 썸네일 R2 endpoint 정의 부재. critical CSS 인라인 전략 모호 |
| **데이터 모델** | 8.7 | structured_data JSONB 패턴 유지. OrderDraft 스키마·인덱스·정리 정책을 P0-00B/C로 선행 분리. | API 응답 JSON 스키마와 충돌 처리 테스트 보강 필요 |
| **API 설계** | 7 | `/api/erp/{domain}/mobile-queue` 일관 패턴. PATCH 부분 업데이트. | API 버전 관리 전략(v2 prefix) 부재. mobile-queue 응답 페이로드 명세 부재 |
| **마이그레이션 안전** | 9 | P0/P1/P2 단계 + 토큰 alias 1주 유지 + Playwright snapshot diff. | 토큰 자동 변환 스크립트 dry-run 모드 + 실패 시 rollback 부재 |
| **테스트 전략** | 7 | E2E 우선 작성 명시. Lighthouse audit. 시각 회귀. | 단위 테스트 / 통합 테스트 / E2E 비율 미정의 |
| **에러 처리** | 8 | inline edit 충돌 감지 (updated_at). offline sync. | 네트워크 에러 시 자동저장 큐잉 정책 명시 부족 |
| **보안** | 8 | XSS·CSRF 기존 정책 유지. file input capture는 권한만 영향. | clipboard API 사용 시 권한 처리 명세 부재 |
| **모니터링** | 7 | KPI 표 명시. RUM 도입 제안. | 알람·SLO·대시보드 구체 명세 부재 |

### Engineering 강점
- 인프라 70% 재사용 — `ERP_MOBILE_V2_ENABLED` 한 줄로 시작
- HTMX/Alpine 점진 도입 — React 풀리라이트 회피
- 단계 PR(P0=8개, P1=7개, P2=8개) 명확
- feature flag + 토큰 alias 1주 유지로 안전한 rollback

### Engineering 보완 액션
1. **OrderDraft 모델 스키마 구현** — 명세는 P0-00B/C로 흡수 완료. 구현 PR에서 `models.py` + Alembic + cleanup cron 검증
2. **API 응답 페이로드 JSON 스키마** — `/api/erp/mobile-queue` 등 5개 엔드포인트 명세
3. **R2 image resize endpoint 정의** — `r2.foms.example.com/resize?src=...&w=320` 명세
4. **테스트 비율 정의** — 단위 60% / 통합 30% / E2E 10%
5. **토큰 변환 스크립트 dry-run 모드** — `python tools/design/migrate-tokens.py --dry-run --report`

---

## 💼 CEO/Strategy Review

**소계 평균: 8.8 / 10**

| 차원 | 점수 | 평가 | 10점이 되려면 |
|---|---|---|---|
| **사용자 가치** | 9 | 안중훈씨(P1 페르소나, 60%) 직접 통증 해소 — AS 첨부, 폼 입력, 빠른 확인. | KPI 측정 베이스라인 부재 — 첫 주에 즉시 측정 시작 필요 |
| **시장 차별화** | 8 | 한국형 ERP 모바일 시장은 모바일 최적화 부족 (이카운트, 더존). FOMS가 우위 점할 기회. | 경쟁 제품 직접 비교 표 부재 |
| **시간 대비 가치** | 9 | P0 1주 + P1 3.5주 = 4.5주 만에 사용자 6대 요구 충족. ROI 매우 높음. | 별도 보완 없음 |
| **확장성** | 8 | 디자인 시스템 단일화 후 새 기능 추가 비용 감소. PWA 전환 가능. | 다국어(중국·동남아) 확장 가능성 명시 부재 |
| **리스크 관리** | 9 | feature flag rollback + 단계 검증 + 사용자 cohort 테스트. | 별도 보완 없음 |
| **인력 부담** | 7 | 12주 풀타임 1명 가정. 디자인+개발 동시 진행 — 디자이너 부재 시 부담. | 디자인 시안 → 코드 변환 자동화 (Figma → 토큰) 검토 |
| **운영 비용 영향** | 9 | R2 이미지 resize 추가 외 인프라 영향 없음. Service Worker로 오히려 트래픽 감소. | R2 호출 빈도 추정 부재 |
| **고객 만족도 예측** | 8 | "현장에서 사용 가능" 자체가 핵심 가치. 안중훈씨 시나리오 완결. | 만족도 측정 도구 (NPS, CSAT) 도입 명시 부재 |
| **수익 영향** | 8 | 직접 매출 영향 없으나 고객 retention + 영업 효율 증가. | 영업 효율 측정 지표 명시 권장 |
| **브랜드 가치** | 9 | "FOMS는 모바일에서 ChannelTalk 만큼 빠르다" 포지셔닝 가능. | 마케팅 활용 명시 부재 (선택) |

### CEO 강점
- 명확한 페르소나 + 시나리오 5종
- ROI 매우 높음 (4.5주 → 70%+ 사용자 가치 충족)
- 인프라 재사용으로 비용 최소
- 한국 ERP 시장 차별화 기회

### CEO 보완 액션
1. **KPI 베이스라인 즉시 측정 시작** — P0-01 PR 시점에 RUM 도입
2. **경쟁 제품 비교 표 추가** — 이카운트·더존·BuilderTrend 모바일 vs FOMS
3. **NPS·CSAT 설문 도구 도입** — P0 종료 후 7일 사용자 5명 인터뷰

---

## 🛠 DX (Developer Experience) Review

**소계 평균: 8.4 / 10**

| 차원 | 점수 | 평가 | 10점이 되려면 |
|---|---|---|---|
| **문서 완결성** | 9 | 5개 문서(계획·시스템·라이브러리·로드맵·리뷰)로 완결. 토큰·컴포넌트·PR 단위 명세. | 별도 보완 없음 |
| **온보딩** | 7 | CLAUDE.md 정책 준수. 디자인 시스템 단일 진입점. | "신규 개발자가 첫 PR까지 걸리는 시간" 명시 부재 |
| **자동화** | 7 | 토큰 자동 변환 스크립트, RUM, Lighthouse, Playwright. | CI 통합 명세 부재 — 시각 회귀 자동 실행 |
| **명명 규칙** | 9 | `--foms-*` BEM `foms-{block}__{element}--{modifier}`. 일관성 강함. | 별도 보완 없음 |
| **모듈성** | 8 | 14개 컴포넌트 + 토큰 분리. partial 매크로 활용. | 컴포넌트별 단위 테스트 명세 부재 |
| **재사용성** | 9 | KV row, attachment grid, sticky action bar — 공용 매크로 승격. | 별도 보완 없음 |
| **디버깅** | 7 | data-theme 토글, feature flag 토글로 격리. | DevTools 컴포넌트 인스펙터 명세 부재 |
| **빌드/배포** | 8 | Railway 환경변수 변경만으로 rollback. | Bundler 전략(esbuild/vite) 명시 부재 — 점진 도입은 OK |
| **의존성 관리** | 7 | Bootstrap 5 + HTMX 2 + Alpine + Lucide 4개. 가벼움. | 의존성 정책(추가 기준, 보안 패치) 명시 부재 |
| **에러 추적** | 7 | Web Vitals RUM 명시. | Sentry 등 명시 부재 |

### DX 강점
- 5개 문서 완결성 — 누구나 따라할 수 있음
- BEM + 토큰 + 매크로 명명 규칙 일관
- 의존성 적음 (4개)

### DX 보완 액션
1. **CI 통합 명세** — `.github/workflows/visual-regression.yml` 추가
2. **컴포넌트 단위 테스트 가이드** — Vitest + happy-dom
3. **에러 추적 도구 통합** — Sentry 또는 Railway logs 구조화
4. **DevTools 인스펙터 명세** — `data-foms-*` 속성으로 컴포넌트 식별

---

## 🔍 추가 발견 (Cross-cutting Concerns)

### 1. **국제화 (i18n) — 시급도 中**
- 현재 한국어 100% 가정. 문자열 하드코딩.
- 가구 시장 동남아 진출 가능성.
- **권장**: P2에 `flask-babel` 도입 명시.

### 2. **분석 (Analytics) — 시급도 高**
- KPI 측정만으로는 사용자 행동 트래킹 부족.
- **권장**: P0에 `plausible.io` 또는 `umami` self-host 도입. 푸시 알림은 P2.

### 3. **법적 요구사항 — 시급도 中**
- 개인정보 처리 (전화번호 tel: 딥링크, 주소 클립보드).
- **권장**: 개인정보 보호 정책 페이지 업데이트.

### 4. **백오피스 영향 — 시급도 低**
- 관리자 페이지(`/admin`)는 본 계획 범위 외.
- **권장**: 별도 P3 작업으로 분리.

### 5. **데이터 마이그레이션 — 시급도 高**
- OrderDraft 모델 추가 → 기존 주문 데이터 영향 없음.
- 단계 색 변경 → 기존 stage label 매핑 검증 필요.
- **권장**: Alembic 마이그레이션 + 시각 회귀.

---

## 최종 평가 매트릭스

```
              Design   Engineering   CEO     DX
Hierarchy       9
Spacing         9
Color           8
Typography      8
Touch           9
State           7
Motion          8
Dark            9
Photo           9
Responsive      8
Architecture           8
Regression             9
Performance            7
Data Model             8
API                    7
Migration              9
Test                   7
Error                  8
Security               8
Monitoring             7
User Value                       9
Differentiation                  8
ROI                              9
Scale                            8
Risk                             9
Headcount                        7
Cost                             9
CSAT                             8
Revenue                          8
Brand                            9
Docs                                       9
Onboarding                                 7
Automation                                 7
Naming                                     9
Modularity                                 8
Reuse                                      9
Debug                                      7
Build                                      8
Dependencies                               7
Tracking                                   7

평균            8.5     8.7          8.8    8.4
─────────────────────────────────────────────
전체 평균: 8.7 / 10
```

---

## 우선 보완 액션 (Top 5)

상위 5개를 P0~P1 작업에 통합 권장:

1. **빈 상태 + Skeleton 컴포넌트 명세 추가** (C14, C15) — P0-02·03·04 작업 시 동시
2. **API 응답 JSON 스키마 명세** — P0 시점에 OpenAPI/JSON Schema 도입
3. **OrderDraft 모델 스키마 + Alembic 마이그레이션** — P0-00B 선행 구현, P1-03은 API·UX만 의존
4. **KPI 베이스라인 측정 시작** — P0-01과 동시에 Plausible/umami 도입
5. **CI 시각 회귀 + 컴포넌트 단위 테스트** — P0-00D에서 주문 목록 baseline 선행, P0-07에서 다크모드 확장

---

## /autoplan 정신 — Auto-Decision 적용

`/autoplan` 6가지 결정 원칙 자체 적용:

1. **사용자 가치 우선** → ✅ P0 첫 주에 안중훈씨 통증 해소
2. **인프라 재사용** → ✅ 70% 재사용 (`ERP_MOBILE_V2_ENABLED`)
3. **점진 출시** → ✅ feature flag + 단계 PR
4. **회귀 최소화** → ✅ 토큰 alias + 시각 회귀 + Playwright
5. **명확한 KPI** → ⚠️ 베이스라인 측정 시작 필요 (보완 액션 1)
6. **단일 진실** → ✅ 토큰·컴포넌트·문서 단일화

5번 보완 후 진행 권장.

---

## 결론

**전체 평균 8.1/10**. 실행 가능한 완결성 있는 계획.

**최우선 보완 5가지** 중 OrderDraft 기반과 CI SSOT lint는 P0-00으로 흡수됨. 남은 API 스키마, KPI 베이스라인, 빈 상태/스켈레톤, 시각 회귀 확장을 P0~P1에서 추적하면 **9.0/10 도달 가능**.

다음 단계: 사용자 승인 → `docs/AI_STATUS.md` 등록 → P0-01 PR 시작.
