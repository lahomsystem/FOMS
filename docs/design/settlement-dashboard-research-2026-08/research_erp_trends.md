# ERP 재무/정산 대시보드 UX·기능 딥리서치 (2024-2026)

조사 범위: NetSuite, Odoo 17/18, SAP S/4HANA Embedded Analytics, Microsoft Dynamics 365 Finance,
QuickBooks/Xero, 더존 Amaranth 10, 이카운트, 경리나라, 네이버 스마트스토어 정산, 카페24, 최신 SaaS
대시보드 디자인 트렌드(bento grid, KPI hero, drill-down, progressive disclosure).

---

## 1. KPI 카탈로그 표

정산/재무 대시보드에 공통으로 등장하는 KPI를 카테고리별로 정리했다.

| 카테고리 | KPI | 정의/계산 | 주로 쓰는 제품 |
|---|---|---|---|
| 매출 | 총매출(Gross Revenue) | 기간 내 전체 매출 합계 | 전 제품 공통 |
| 매출 | 순매출(Net Revenue) | 매출 − 환불/반품/할인 | 카페24, Xero, QuickBooks |
| 매출 | 누적 매출(Cumulative Revenue) | 기간 시작부터의 누적 합 | NetSuite, Power BI 리포트팩 |
| 매출 | 전기 대비 증감률 | 전월/전년 동기 대비 % | 전 제품 공통(카페24 "전 기간 대비 증감률") |
| 수익성 | 매출총이익률(Gross Profit Margin) | (매출−매출원가)/매출 | NetSuite Profitability KPI |
| 수익성 | 순이익률(Net Profit Margin) | 순이익/매출 | NetSuite |
| 유동성 | 유동비율(Current Ratio) | 유동자산/유동부채 | NetSuite Liquidity KPI |
| 유동성 | 당좌비율(Quick Ratio) | (유동자산−재고)/유동부채 | NetSuite |
| 현금흐름 | 현금 잔고(Cash Position) | 은행 실시간 잔고 | Xero Business Snapshot, 경리나라(전 은행 연동 자금일보) |
| 현금흐름 | 현금흐름 예측(7일/30일) | 미결제 인보이스·청구서 기반 예측 | Xero Cash Flow Forecasting |
| 수금 | 미수금 잔액(AR Balance) | 매출 − 수금 | 이카운트(거래처별채권), 경리나라(AI 자동 미수금 잔액) |
| 수금 | 채권 회전율(AR Turnover) | 매출/평균매출채권 | NetSuite Efficiency KPI |
| 수금 | DSO(매출채권회수기간) | (평균매출채권/매출)×기간일수 | NetSuite, Salesforce, HighRadius, 자동화 대시보드 30~40% 단축 사례 보고 |
| 수금 | AR Aging(연체 구간별 미수금) | Current/1-30/31-60/61-90/91+일 버킷 | QuickBooks A/R Aging Summary, NetSuite AR Dashboard |
| 수금 | 연체 위험 점수(Delinquency Risk Score) | 과거 결제 패턴 기반 예측 점수 | 최신 AR SaaS(예: HighRadius류) |
| 지급 | 매입채무회전기간(DPO) | (평균매입채무/매출원가)×기간일수 | 현금흐름 대시보드 공통 KPI |
| 정산(커머스) | 정산 예정 금액 | 구매확정/반품완료+1영업일 기준 회차별 입금 예정 | 네이버 스마트스토어 정산관리 |
| 정산(커머스) | 수수료 내역(결제/매출연동/쿠폰분담/반품차감) | 정산내역 컬럼 클릭 시 항목별 펼침 | 네이버 스마트스토어 |
| 정산(커머스) | 정산예정금(멀티쇼핑몰 통합) | 여러 쇼핑몰 합산 | 카페24 AI 정산관리 도구 |
| 운영 | 구매건수/전환수 증감 | 방문→구매 전환 추이 | 카페24 매출 분석 |
| 결산 | Close 진행률(Task 상태) | 마감 태스크·조정(reconciliation) 완료율 | BlackLine/FloQast류 결산 대시보드 |

---

## 2. 시각화 패턴 목록

1. **KPI 히어로 카드(4~6개, 화면 상단 80~120px)** — 숫자 + 추세 화살표(%) + 스파크라인, 스크롤 없이 한 화면에.
2. **Sparkline 내장 카드** — 카드 레벨 필터를 그대로 따라가는 네이티브 스파크라인(Power BI 2026 신규 Card visual 권장 패턴).
3. **드릴다운(요약→거래 원장)** — KPI/변동값 클릭 → 해당 원인 거래 리스트로 이동. 기본은 숨겨두고 클릭 시에만 노출(progressive disclosure).
4. **기간 토글(일/주/월) + 비교 드롭다운** — "이전 기간/전월 동기/전년 동기" 비교, 우측 상단 링크형 토글이 일반적.
5. **누적선(Cumulative Area Chart) vs 순증(Bar/Line)** — 누적은 영역차트로 성장 크기 강조, 순증(일별 변동)은 막대/선으로 구분 표시. 7일/30일 이동평균을 얹어 노이즈 완화.
6. **AR Aging 버킷 컬럼차트** — Current/1-30/31-60/61-90/91+ 구간을 시간순 막대로 배치, 클릭 시 거래처별 리스트.
7. **DSO 트렌드 라인 + 목표선** — 현재 DSO, 30일 추세, 목표 대비 비교를 한 위젯에.
8. **현금흐름 예측 롤링 라인차트** — 실제 vs 예측(다음 7/30/90일) 비교, 결제 위험 점수 오버레이.
9. **Bento Grid 레이아웃** — 비대칭 카드 크기로 정보 밀도·시각적 위계 조절(2026년 ProductHunt 상위 SaaS 67%가 채택). KPI, 퍼널, 최근 활동을 한 그리드에 혼합 배치.
10. **조건부 서식(임계값 색상)** — 매출채권 연체 심화 시 카드 배경/뱃지 색이 단계적으로 진해짐. 색만이 아니라 화살표/부호로 이중 신호(색약 대응).
11. **거래처별 채권 현황 테이블** — 매출/수금/잔액을 거래처 행으로 나열(이카운트 채권 현황 보고서 패턴).
12. **정산 상태 배지(Reconciled/Disputed/Failed/Awaiting)** — 마켓플레이스 정산 대사(payout reconciliation) 대시보드 공통 패턴.
13. **결산 진행률 체크리스트 위젯** — Close 태스크 상태를 칸반/체크리스트로, 예외(anomaly) 자동 플래그.
14. **다크모드 대응** — 순검정(#000) 대신 네이비 계열(#0f172a류) 배경, WCAG AA 4.5:1 대비 유지, 표면별 elevation으로 레이어 구분.
15. **역할 기반 대시보드(Role-based)** — 영업/재무/경영진별로 노출 KPI를 다르게 구성(SAP Fiori, NetSuite 역할별 대시보드).

---

## 3. 제품별 주목할 UI 특징

- **NetSuite**: KPI Scorecard 포틀릿으로 여러 KPI를 기간(월/분기/년)별로 나란히 비교. AI 에이전트가 이상치를 과거 패턴과 자동 대조해 플래그. Financial Ratios Scorecard(유동비율·당좌비율 등)를 Trial Balance 권한 사용자에게 기본 제공.
- **Odoo 18**: 회계 대시보드 리디자인 — 필터 기반 색상 구분 비교, 리포트에 새 날짜 선택기(기간 전환 용이), 예산 대비 실적 비교에 "이론값" 컬럼 추가.
- **SAP S/4HANA Embedded Analytics**: HANA 인메모리 DB가 트랜잭션(OLTP)과 분석(OLAP)을 같은 시스템에서 동시 처리 → 별도 BW 없이 실시간 드릴다운. Fiori 앱에 역할별로 임베드.
- **Dynamics 365 Finance**: Power BI 연동이 핵심 — 2026년 8월 기준 Finance/Sales/Inventory/AP/AR/Purchasing용 사전 구축 다페이지 Power BI 리포트팩이 신규 출시(Cosmos). 거버넌스된 데이터 모델 기반.
- **QuickBooks**: Home/Business overview/Cash flow 탭 구조. Cash flow 탭에 당월 예정/완료 인보이스 그래프 + 연체 리스트. 대시보드 프리셋(Profitability/Cash flow/AR/Revenue)을 선택 후 KPI·기간 커스터마이즈.
- **Xero**: Business Snapshot이 매출·비용·수익성·현금 포지션을 한 화면에. 대시보드에서 은행 잔고, 미결제 인보이스, 예정 청구서를 즉시 노출. Cash forecasting은 기존 인보이스/청구서/반복결제 기반 7~30일 예측.
- **더존 Amaranth 10**: 재무제표를 관리 목적별로 다양한 포맷으로 재구성 가능(공개 UI 스크린샷 정보는 제한적, 회계·세무·인사·영업물류 통합 프로세스 강조).
- **이카운트**: "거래처별채권" 메뉴가 판매(매출)와 회계(수금)를 통합 — 매출−수금=채권잔액 공식을 화면에서 바로 확인. 채권 현황 보고서는 조회기간 매출/수금/잔액을 거래처별 표로 제공.
- **경리나라**: 다중 사업자 매출/매입/자금현황 통합 대시보드, 전 은행 연동 실시간 자금일보, AI가 자동 정리하는 미수금 잔액을 한 페이지에서 조회.
- **네이버 스마트스토어**: 정산관리 > 정산내역에서 일반정산/빠른정산 구분 + 회차별 입금 예정일 표시. 수수료 컬럼 클릭 시 결제수수료/매출연동/쿠폰분담/반품차감이 항목별로 펼쳐지는 인라인 드릴다운(아코디언) 패턴이 특징적.
- **카페24**: 통계 대시보드가 매출/상품/고객 분석 3분류, 1시간 주기 갱신. 매출액 위젯에 전기간 대비 증감 %를 항상 병기. AI 정산관리 도구로 멀티쇼핑몰 정산예정금을 한 화면 통합.

---

## 4. 가구 주문 ERP 정산 대시보드에 넣을 구체 요소 추천 15개

1. **상단 KPI 히어로 4~5장(당월 매출/수금/미수금 잔액/DSO/현금 잔고)** — 스크롤 없이 한눈에 파악, 업계 공통 패턴이자 FOMS 워크플로(주문→시공→CS)의 재무 병목을 즉시 노출.
2. **일/주/월 매출 토글 + 전기 대비 증감 %** — 가구는 시공 일정 기반이라 주 단위 변동이 크므로, 주간 토글이 특히 유효(카페24·QuickBooks 공통 패턴).
3. **누적 매출 영역차트 + 순증 막대 오버레이** — 월 목표 대비 누적 진행률과 일별 변동을 동시에 보여줘, 영업 목표 관리에 직결.
4. **AR Aging 버킷(Current/1-30/31-60/61-90/91+) 컬럼차트** — 예약금만 받고 잔금 미수인 주문을 구간별로 조기 포착, 시공 후 미수금 방치 리스크를 줄임.
5. **거래처(고객)별 채권 현황 테이블(매출-수금=잔액)** — 이카운트 패턴 차용, 반복 거래처(대리점/거래처)가 있는 가구 ERP에 적합.
6. **잔금 미수 주문 드릴다운** — AR Aging 카드 클릭 시 해당 주문 리스트로 즉시 이동(주문번호·시공완료일·잔금액), FOMS 주문 스테이지와 자연 연결.
7. **입금 마감 경과 자동 알림(알림톡/이메일)** — 국내 중소 ERP 실무 표준 패턴, 수금 담당자가 매번 수동 체크하지 않도록.
8. **현금흐름 7일/30일 예측 라인차트** — 자재 발주·시공비 지출과 잔금 수금 타이밍이 어긋나는 가구업 특성상, 단기 현금 예측이 실질적 가치가 큼.
9. **채널별(직접판매/네이버/기타 마켓) 매출·수수료 분해 위젯** — 네이버 정산 아코디언 패턴 차용, 채널 수수료가 순매출에서 얼마나 빠지는지 투명화.
10. **정산 상태 배지(정산완료/정산예정/미정산/보류)** — 마켓플레이스 정산 대사 패턴, 특히 네이버 워크벤치와 연계된 정산 흐름 가시화에 적합.
11. **조건부 서식 임계값 색상 + 이중 신호(화살표/부호)** — 미수금 심화 단계를 색+아이콘 이중 인코딩으로, 색약 사용자 및 다크모드 대응.
12. **역할 기반 뷰(경영진/영업/수금담당)** — 경영진은 KPI 요약, 수금담당은 AR Aging+거래처 리스트 중심으로 같은 데이터를 다르게 노출.
13. **Bento Grid 기반 카드 배치(크기 비대칭)** — 매출 추이(큰 카드) + 미수금 요약(중간) + 알림 리스트(작은 카드)를 하나의 그리드로 정보 밀도와 스캔성 확보.
14. **드릴다운 기본 숨김 + 클릭 시 노출(progressive disclosure)** — FOMS 대시보드가 이미 방대한 주문 데이터를 다루므로, 상세 원장은 클릭 전까지 접어둬야 인지 부하가 낮음.
15. **다크모드 지원(네이비 배경 + WCAG AA 대비)** — 태블릿/PC 병행 사용 환경(FOMS 태블릿 도면 리뷰 등 기존 자산과 통일감), 장시간 응대하는 CS/영업 담당자 눈 피로 감소.

---

## 5. 미래 기능 후보

- **자동 정산 마감(Automated Period Close)** — BlackLine/FloQast류처럼 마감 태스크 체크리스트 + 조정(reconciliation) 자동 매칭 + 예외 자동 플래그. FOMS 월별 매출/수금 마감을 반자동화할 여지.
- **채널 수수료 정산 자동 대사(Channel Fee Reconciliation)** — 네이버/카페24 등 채널 정산 내역을 주문 원장과 라인 단위로 자동 매칭, 차이(수수료 오류·반품 차감 누락) 자동 검출.
- **현금흐름 예측(AI 기반, 7/30/90일)** — 과거 결제 패턴과 진행 중인 시공 일정(잔금 예정일)을 결합해 향후 현금 포지션을 예측, 자재 발주 타이밍 의사결정에 연결.
- **연체 위험 예측 스코어(Delinquency Risk Score)** — 거래처별 과거 결제 이력 기반으로 고위험 미수금을 사전 경고, 수금 우선순위 자동 정렬.
- **AI 이상치 자동 플래그** — 매출/수금 패턴이 과거 대비 비정상적으로 이탈할 때 자동 알림(NetSuite AI 에이전트 패턴).
- **역할별 대시보드 개인화(저장 가능한 커스텀 뷰)** — 사용자가 KPI 카드 배치·필터를 저장, 재방문 시 유지.
- **드릴다운 감사 추적(Audit Trail) 통합** — KPI에서 원장까지 클릭 이동 시, 누가 언제 데이터를 수정했는지까지 한 번에 확인(SOX/내부통제 대응 확장).
- **멀티채널 통합 정산 대시보드** — 직접판매 + 네이버 + (향후) 추가 채널의 정산 예정/완료를 단일 화면에서 조회(카페24 AI 정산관리 도구 벤치마크).

---

## 참고 출처(Sources)

- [Financial Dashboard Examples You Should Use in 2026 (With KPIs) | Supaboard](https://supaboard.ai/blog/financial-dashboard-examples)
- [Power BI KPI Visuals & Dashboard Cards: Enterprise Guide 2026](https://www.epcgroup.net/power-bi-kpi-visuals-dashboard-guide-2026)
- [Dashboard UI Design Principles & Best Practices Guide 2026](https://www.designstudiouiux.com/blog/dashboard-ui-design-guide/)
- [30 Financial Metrics and KPIs to Measure Success in 2026 | NetSuite](https://www.netsuite.com/portal/resource/articles/accounting/financial-kpis-metrics.shtml)
- [NetSuite Applications Suite - KPI Scorecards](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/chapter_N610592.html)
- [NetSuite Applications Suite - Financial Ratios Scorecard](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N624824.html)
- [Odoo 18: What's New? Overview of Features and Highlights](https://www.confianzit.com/cit-blog/odoo-18-new-features/)
- [🔝 Highly Impactful Features of Odoo 18 Accounting](https://www.serpentcs.com/blog/odoo-guide-378/odoo-18-accounting-features-608)
- [SAP S/4HANA Embedded Analytics for Finance: Apps, Architecture, and Implementation Tips](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/sap-s-4hana-embedded-analytics-for-finance-apps-architecture-and/ba-p/14141273)
- [Real-time analytics with S/4HANA Embedded Analytics](https://www.orbisusa.com/en-us/sap-consulting/business-analytics/s4hana-embedded-analytics.html)
- [Dynamics 365 Finance Reporting with Power BI](https://erpsoftwareblog.com/2026/06/how-can-power-bi-reports-improve-dynamics-365-finance-reporting/)
- [Cosmos Launches Six Pre-Built Power BI Report Packs for Microsoft Dynamics 365 Business Central](https://www.globenewswire.com/news-release/2026/08/24/3349850/0/en/cosmos-launches-six-pre-built-power-bi-report-packs-for-microsoft-dynamics-365-business-central.html)
- [AR aging report: What it is & how to use | QuickBooks Blog](https://quickbooks.intuit.com/r/payments/accounts-receivable-aging-report/)
- [Best Accounts Receivable Dashboard Examples & Templates for 2026](https://www.vertaccount.com/blog/best-accounts-receivable-dashboard-examples-templates-for-2026/)
- [An Overview of Your Data with Business Snapshots | Xero UK](https://www.xero.com/uk/accounting-software/analytics/snapshot/)
- [Cash Flow Forecasting Software for your Small Business | Xero US](https://www.xero.com/us/accounting-software/analytics/forecasting/)
- [Amaranth 10 구성도 - 더존](https://www.douzone.com/product/amaranth10.jsp)
- [이카운트 ERP : 매입/매출 자금 계획 한눈에 보는 방법 | 중원랩스](https://jungwonconsulting.com/55)
- [이카운트 ERP 컨설팅 : 채권 관련 장부 총정리](https://jungwonconsulting.com/82)
- [경리나라 - 나무위키](https://namu.wiki/w/%EA%B2%BD%EB%A6%AC%EB%82%98%EB%9D%BC)
- [정산관리 시스템 추천: 거래처 미수금·수금·정산 마감 관리 기준 — StackCube](https://blog.stackcube.io/ko/settlement-management-system)
- [네이버 스마트스토어 정산 보는 법 | 대시판다](https://www.dashpanda.io/blog/naver-settlement-explained)
- [카페24 Help Center - 매출 분석](https://support.cafe24.com/hc/ko/articles/48101224773401-%EB%A7%A4%EC%B6%9C-%EB%B6%84%EC%84%9D)
- [카페24 Help Center - 통계 알아보기](https://support.cafe24.com/hc/ko/articles/7750499636761-%ED%86%B5%EA%B3%84-%EC%95%8C%EC%95%84%EB%B3%B4%EA%B8%B0)
- [Designing Bento Grids That Actually Work: A 2026 Practical Guide - SaaSFrame Blog](https://www.saasframe.io/blog/designing-bento-grids-that-actually-work-a-2026-practical-guide)
- [Bento Grid Dashboard Design: Complete Guide 2026](https://www.orbix.studio/blogs/bento-grid-dashboard-design-aesthetics)
- [Accounts Receivable (AR) Dashboard: Benefits, Examples & Tips | NetSuite](https://www.netsuite.com/portal/resource/articles/accounting/accounts-receivable-ar-dashboard.shtml)
- [Accounts Receivable Aging: Definition, Calculation & SQL | Metabase](https://www.metabase.com/metrics/accounts-receivable-aging/)
- [Aging Bucket: Essential Guide | Emagia](https://www.emagia.com/resources/glossary/aging-bucket/)
- [Cash flow dashboard: How to manage multi-entity liquidity | Intuit](https://intuit.com/enterprise/blog/financials/cash-flow-dashboard)
- [Days Sales Outstanding (DSO) | Formula + Calculator - Wall Street Prep](https://www.wallstreetprep.com/knowledge/days-sales-outstanding-dso/)
- [Revenue dashboard - FastSpring](https://developer.fastspring.com/docs/revenue-dashboard)
- [Ultimate Guide to Revenue Data Visualization - growth-onomics](https://growth-onomics.com/ultimate-guide-to-revenue-data-visualization/)
- [Top Financial Close Software Tools for 2026 | Abacum](https://www.abacum.ai/blog/financial-close-software)
- [Top 10 Best Financial Close Automation Software in 2026 - ChatFin](https://chatfin.ai/blog/top-10-best-financial-close-automation-software-in-2026/)
- [Marketplace Settlement Reconciliation: Multi-Channel Guide - VersaCloud ERP](https://www.versaclouderp.com/blog/how-to-reconcile-marketplace-settlements-across-multiple-sales-channels/)
- [Reconcile Marketplace Payouts vs Orders: 5 Steps [Guide]](https://ustechautomations.com/resources/blog/automate-reconcile-marketplace-payouts-against-order-ledgers-2026)
- [Admin Dashboard Design Examples for 2026: Dark Mode & KPI - Fanruan](https://www.fanruan.com/en/blog/top-admin-dashboard-design-ideas-inspiration)
- [Fintech Websites Dark Mode Examples: 15 Stunning Designs to Inspire You in 2026](https://usatechtrend.com/fintech-websites-dark-mode-examples-15-stunning-designs-to-inspire-you-in-2026/)
