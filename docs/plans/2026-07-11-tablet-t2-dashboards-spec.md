# 태블릿 T2 — 대시보드 목업 정합 구현 Spec (2026-07-11)

선행: T0+T1a 배포 완료(`2026-07-10-tablet-shell-t0-implementation-spec.md`). 목업 v8 = artifact `1f9d4a9b` (사용자 최종 확정: **태블릿 가로 = PC 인터페이스 최대 반영 + 터치 융합**, 카드형 큐 마스터 폐기).

## 방향 통일 (구현 원칙)

태블릿 가로(코호트, 992+ landscape coarse — fine 포함 992–1365)의 대시보드 = **legacy PC 표면(`.foms-shell-desktop-only`)을 그대로 쓰되 4개 융합 레이어를 얹는다**:
1. **터치 보정 레이어** — 그리드 행 ≥48px, 버튼/입력 ≥44px, 필터 컨트롤 터치화, 체크박스 상시 노출. 순수 CSS(`@media` 매트릭스 조합), 페이지 마크업 무변경.
2. **요약 타일** — 프로세스맵/경보를 목업의 큰 타일 스트립으로(태블릿 조합에서만 스타일 전환, 데이터 동일).
3. **사이드 시트** — 그리드 행 탭 → 우측 380~420px 시트에 기존 모바일 카드 상세/edit fragment 로드(신규 API 없음). 모달·페이지 이동 대체.
4. **특수형 2종** — 실측: 좌 고객 리스트(300px)+우 ERP Order 편집(기존 edit fragment) / 생산: read-model 3버킷 칸반(제작대기/제작중/제작완료).

split shell(카드 마스터, /erp/dashboard)은 당분간 공존 — 잔여 페이지 배선 후 컨트롤타워도 그리드+보정형으로 전환 판단(백로그).

## 실행 단위
- **W9** `static/css/foundation/foms-tablet-landscape.css`(신규): 터치 보정 레이어. 대상 = 9 대시보드의 legacy 표면. 로드 = foms-mobile-surfaces.css @import(+부모 ?v 체인 범프). 조건 = `((min-width:992px) and (orientation:landscape) and (pointer:coarse))` 중심 — fine 992–1365는 split 밴드라 legacy 은닉/fallback 규칙과 정합 검토 후 포함 여부 결정·명기.
- **W10** 사이드 시트: `static/js/foms/tablet-side-sheet.js` + `static/css/components/foms-tablet-side-sheet.css` + 최소 배선(행 클릭 위임 — 컨트롤타워 legacy 그리드·시공·생산 3페이지 우선). 기존 fragment 인프라(`/api/foms/fragment/order/<id>/edit`) 재사용, idempotent 가드(G4), defer(G1).
- **W11** 요약 타일: 프로세스맵 카드의 태블릿 조합 스타일 전환(마크업 무변경 우선, 불가피 시 최소 추가).
- **W12** 실측 특수형 / **W13** 생산 칸반: 페이지 템플릿+CSS+(칸반은 read-model 버킷 소비 — 서버 무변경, display 데이터 재사용).
- 각 단위: 계약 테스트 추가, APP_OK+스위트, 캐시버스터 체인 전체 범프(교훈), Advisor 검증 후 커밋·push·staging 실측.

## 경계
context_processors·서버 라우트·quest 엔진 수정 금지(칸반도 표시 전용). 타 세션(v3 셸) 파일 불가침. `orientation: portrait` 토큰은 foms-split-view.css에서만 금지(가드) — 신규 파일은 표시 opt-in 용도로 사용 가능하나 W5 전례(주석 명기) 따름.

---

## 실행 결과 (2026-07-11 완료, deploy 커밋 4건)

| 커밋 | 단위 |
|---|---|
| `7c5f072d` T2-α | 터치 보정 레이어(foms-tablet-landscape.css) + 사이드 시트(tablet-side-sheet.js/css — 행 탭→400px 비차단 시트, orders·construction·production 공통 그리드) |
| `d63d0211` T2-β | 요약 타일(프로세스맵 카드화·경보 4-타일 그리드, CSS-only) |
| `75496088` T2-γ | 실측 특수형(좌 고객 리스트 300px + 우 ERP Order fragment 상시 패널, rows 재사용) + 생산 칸반(read-model 3버킷 Jinja 그룹핑, 열 이동=start/complete API) + fragment-loader 공용 추출 |
| `e653748e` W14 | 울트라 재검토 결함 7건 봉합 — JS/CSS 게이트 SSOT(`--foms-tablet-ui` 마커 파생), 필터 16px ID 특이도, 시트 col-md 평탄화, 스크립트 src dedupe, 이중 디스패치 제거, 외부클릭 닫기 제거, 데드 규칙 정리 |

staging 검증: 신규 자산 전부 서빙·게이트 마커 ready·콘솔 0·기존 매트릭스 무회귀(1180 fine=split/desktop 정상, 특수형·칸반·시트는 coarse 전용이라 실기기에서 발현). 격리 worktree 스모크 250 passed × 3회. CI green.

## 백로그 (잔여 페이지 — 조사 완료, 착수 판단 대기)

시트/터치 그리드 계약(`#erp-grid tr.erp-main-row[data-order-id]`) 미충족 6페이지 실사 결과:
1. **AS**: 셀렉터 확장으로 가능(`.erp-pro-table-wrapper tbody tr[data-order-id]`) — 최소 확장 후보 1순위.
2. **출고**: data-order-id 있으나 자체 폭 게이트(1365.98 모바일 UI)가 992–1365를 선점 — T2 게이트 통합과 함께.
3. **이력**: 본행에 data-order-id 자체가 없음(속성 추가 필요) + 기존 chevron 확장 행과 상호작용 설계 필요.
4. **도면 워크벤치**: data-href 행 내비게이션과 충돌 — 별도 UX 판단(dw-* 클래스 패밀리, 타일도 미적용).
5. **완료**: 카드 리스트(비그리드) — 시트 부적용, 현행 유지.
6. 실측은 T2-γ 특수형이 대체(기존 chevron 확장은 desktop 표면에 잔존 — coarse에선 특수형이 소유).
+ 페이지네이션 특성상 칸반은 현재 페이지 범위만 표시(무한스크롤 비범위) · 칸반 낙관 갱신 비범위 · /erp/dashboard split 카드 마스터의 그리드 전환 여부는 실사용 피드백 후 결정.
