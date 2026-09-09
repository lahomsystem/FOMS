# 고객 공유 링크 UX 개편 — 계약서·도면 (2026-08-31)

브랜치: `session/kakaoshare` (worktree `c:\tmp\foms-s-kakaoshare`, base `origin/deploy` = ea55440f)

## 배경 (사용자 보고)

ERP 주문 상세 > 카톡 알림 발송 메뉴가 고객에게 보내는 공유 링크 3종(도면 / 계약서 / 도면+계약서)에서:

- 계약서 링크(`/s/<token>`, kind=estimate)가 **ERP 계약서 폼과 전혀 다른 밋밋한 표**로 보인다.
  품목표 오른쪽 "금액" 칸이 화면 밖으로 잘린다.
- 하단 "견적서 저장·인쇄 (PDF)" 버튼이 **아무 반응도 없다** (카카오톡 인앱 브라우저에서 `window.print()` 미지원 추정).

## 사용자 결정 (2026-08-31)

1. 계약서 저장 = **이미지(PNG) 저장** — ERP 견적서 탭 "이미지 저장"과 동일 방식. `window.print()` 대체.
2. 도면 일괄 저장 = **ZIP 1파일** + 개별 1장씩 목록 유지 + 인앱 브라우저 안내 병행
   (iOS 사파리/크롬은 zip 을 파일 앱에 저장 가능. 카톡 인앱 브라우저만 불확실 → 개별 저장 폴백).
3. 계약서 세부내용 = **ERP 계약서 폼 그대로** (사업자정보·인감·계약번호·품목표·결제정보·법적문구).

## 불변 계약 (깨면 안 되는 것)

- **D6 동결**: 계약서 렌더 소스는 발급 시점 스냅샷(`OrderShareToken.snapshot`)뿐. 주문 라이브 재조회 금지.
- **스냅샷 화이트리스트**: `order_share.build_estimate_snapshot()` 밖의 필드를 템플릿이 참조하면 안 된다.
  새 필드가 필요하면 빌더에 **명시 추가**(타 브랜드 계좌·내부 플래그 유출 금지).
- **주문 격리**: 도면 파일 수집은 `_collect_drawing_files()` allow-list(`_is_drawing_key`) 경유만.
- **fail-closed**: storage_type 이 r2/s3 아니면 503. presign 전멸도 503(조용한 빈 화면 금지).
- **비로그인 페이지**: ERP 셸/로그인 컨텍스트 없음. Bootstrap·jQuery 없음. 자체 CSS/JS 만.
- 인라인 `style=` 속성 금지. CSS는 `static/css/orders/` 파일로. `?v=` 핀 범프 필수.
- presigned URL 수명 300초 — 만료 안내(`[data-share-expiry-note]`) 동작 유지.

## 작업 분할 (병렬)

| T | 제목 | 소유 파일 | 완료 기준 |
|---|------|-----------|-----------|
| T1 | 계약서 페이지를 ERP 계약서 폼 그대로 | `templates/orders/partials/share_estimate_body.html`, `templates/orders/share_estimate_view.html`, `templates/orders/share_bundle_view.html`, 신규 `static/css/orders/foms-share-contract.css`, 신규 `static/js/orders/share-contract.js` | 아래 T1 완료 기준 |
| T2 | 도면 일괄 저장(ZIP) + 다운로드 섹션 정리 | `foms/api/share.py`, `templates/orders/partials/share_drawing_body.html`, `static/css/orders/foms-share-view.css`, `static/js/orders/share-view.js` | 아래 T2 완료 기준 |
| T3 | 신규 라우트/자산 계약 조사 + iOS·Android 제약 정리 | (읽기 전용) | 결론 파일 산출 |

## T1 완료 기준

- [ ] `/s/<token>` (kind=estimate) 가 ERP `erp-est-doc` 과 같은 구성으로 렌더된다:
      상단 컬러바 · 로고 · 계약번호 · 사업자정보(+인감) · 고객정보 · 안내문구 ·
      계약 내용 표(품명/규격/색상/수량/금액) · 결제정보 + 합계(출고가/예약금/할인/잔금) · 작성일자 + 법적문구
- [ ] 품목표가 좁은 화면에서 **잘리지 않는다**(가로 스크롤 컨테이너 + 스크롤 가능 시각 신호, 또는 모바일 카드 전환)
- [ ] 계좌번호 **복사 버튼** — `navigator.clipboard` 우선, 실패 시 `textarea + execCommand('copy')` 폴백. 복사 후 "복사됨" 표시
- [ ] **PNG 저장 버튼** — html2canvas lazy-load(CDN, `wizard.js` 패턴 복제, perf G2 준수) → `<a download>` blob 저장.
      실패 시 조용히 죽지 말고 안내 문구 표면화
- [ ] `window.print()` 단독 의존 제거 (PC는 인쇄 버튼을 보조로 남겨도 됨)
- [ ] bundle 페이지(`share_bundle_view.html`)도 같은 본문 파셜을 쓴다 — 사본 금지
- [ ] 파셜 단독 렌더에도 UndefinedError 안 남(자기 지역 변수 자체 생성 — 기존 규약 유지)
- [ ] 스냅샷에 없는 필드 참조 0건. 필요하면 `build_estimate_snapshot` 에 명시 추가하고 근거 기록

## T2 완료 기준

- [ ] `GET /s/<token>/drawings.zip` — 토큰 검증 체인 동일(404/410/503), 도면 전체를 zip 스트리밍
- [ ] 파일명 한글 안전(RFC 5987 `filename*=UTF-8''...`), zip 내부 항목명 중복 시 번호 부여
- [ ] 용량 가드: 총 바이트 상한 초과 시 503 + 안내(무한 메모리 금지)
- [ ] 열람 페이지 다운로드 섹션 UI 정리 — 일괄 저장 버튼(주) + 개별 저장 목록(부)
- [ ] 카카오톡 인앱 브라우저(UA `KAKAOTALK`) 감지 시 "다른 브라우저로 열기" 안내 한 줄
- [ ] 감사 로그 1건(`record_file_access`) — 기존 열람 경로와 같은 규약
- [ ] bundle 페이지에서도 같은 섹션이 나온다

## T3 산출물

`docs/harness/evidence/2026-08-31-share-route-contracts.md` — 신규 GET 라우트가 통과해야 하는
계약(write_guard manifest / audit coverage / 감사 라벨 / 자산 ?v 핀 테스트 / ci.yml 등재) 목록과
iOS·Android 인앱 브라우저 다운로드 제약 정리.

## 진행 상태 (검증 완료 2026-08-31)

- T1 DONE — 계약서 폼 재구성·계좌 복사·PNG 저장 (`share_estimate_body.html`, `foms-share-contract.css`, `share-contract.js`)
- T2 DONE — ZIP 일괄 저장 라우트 + 다운로드 섹션 UI (`foms/api/share.py`, `share_drawing_body.html`)
- T3 DONE — `docs/harness/evidence/2026-08-31-share-route-contracts.md`
- CEO 교차검수 DONE — 조건부 승인, 지적 S1~S5 전부 반영
- **deploy DONE** — `72e16e1b`, CI 4/4 green
- **운영 승격 DONE** — PR #208 머지(production `a6175cd7`), 검사 4/4 pass. 운영 자산 실서빙 확인(`foms-share-contract.css` 200 · `export-clone` 규칙 존재 · `share-contract.js` 에 `EXPORT_WIDTH = 700`·`toDataURL`). **잔여 = 실기기(iOS·Android 카톡 인앱) 확인**

### 총괄이 직접 잡아 고친 것 (T1~T3 산출물의 결함)

| # | 결함 | 고친 방법 |
|---|------|-----------|
| 1 | PNG 저장이 `toBlob` + `blob:` 우선 — iOS WKWebView 는 `blob:` 을 `<a download>` href 로 못 써서(WebKit 216918) **원래 신고된 무반응이 그대로 재발** | `toDataURL` 1순위로 뒤집음. 계약 테스트가 소스 순서를 고정 |
| 2 | PNG 저장이 **화면 노드를 그대로 캡처** — 폰에서 저장하면 1단 모바일 레이아웃이 그림이 된다("기존 계약서를 그대로 다운로드" 위반) | ERP `_buildExportClone` 패턴 복제. 700px 오프스크린 클론 + html2canvas `windowWidth: 700`. 실측 산출물 1400×2090 |
| 3 | `share_estimate_view.html` 만 옛 `?v=` 핀 — SW `staticCacheFirst` 가 그 페이지만 옛 CSS 서빙 | 핀 통일 + **드리프트 검출 테스트 신설**(저장소에 없던 게이트, 뮤테이션으로 빨강 확인) |
| 4 | 할인 줄 노출 — 출고가에 이미 흡수된 값이라 고객이 두 번 빼는 것으로 읽는다 | ERP 읽기전용 요약과 같은 규칙으로 숨김. 양성 대조군을 둔 테스트 |
| 5 | ZIP 이 **일부만 담긴 채 200** 으로 나갔다(3건 중 1건). 버튼은 "전체 저장 (N개)" | `packed < len(collected)` 면 503 + 개별 저장 안내 |
| 6 | `word-break: break-word` 가 치수를 숫자 중간에서 끊었다(`2400x2400x600` → `240`/`0` 오독) | `overflow-wrap: break-word`(정말 안 들어갈 때만) + 규격 열 확대. 금액칸은 여전히 화면 안(실측 right 359 < 390) |
| 7 | 2공장 로고가 ERP 폼과 다른 파일(`lahom-logo.png`) | ERP `data-factory2-src` 와 같은 `lahom-logo-en.png` |
| 8 | iOS 사파리(인앱 아님)에서 비동기 다운로드가 막히면 회복 경로 없음 | 터치 단말이면 성공 여부와 무관하게 폴백 이미지 노출 |
| 9 | 터치 타깃 미달(복사 22px·저장 42px), 저대비 `#888`/`#999` | 히트 영역 44px(겉모양 유지: `::after` 오버레이), 버튼 46px, `#6b7280` |
| 10 | 고객 화면에 ERP 내부 낱말 노출("좌우 스와이프로 **승인**", "(lightbox)", "16:9") | 갤러리 파셜에 `share_mode` opt-in 플래그(ERP 화면 무변경) |
| 11 | 구 견적서 CSS 116줄 사문화 | 삭제 |

### 검증 (총괄이 직접 실행)

- `python -c "import app; print('APP_OK')"` → `APP_OK`
- `pytest tests/domains/test_order_share_view.py tests/domains/test_order_share_api.py tests/contracts tests/performance/test_perf_regression_guard.py tests/domains/test_failopen_inventory.py tests/domains/test_write_guard.py tests/domains/test_audit_coverage_inventory.py` → **179 passed**
- 로컬 dev 실브라우저(gstack browse) 실측:
  - 390px: 금액칸 오른쪽 끝 359 < 뷰포트 390(잘림 없음), 규격 1줄, 가로 넘침 0
  - PNG 저장: html2canvas 로드 → `계약서_○○_2026-08-31.png` 다운로드, **1400×2090(=700px 문서 ×2)**, 클론 잔재 0, 콘솔 에러 0
  - 카톡 UA: 폴백 패널 노출 + PNG 실제 표시 / 데스크톱 UA: 폴백 숨김
  - 계좌 복사: "복사됨" 1.5초 후 복원, 히트 영역 44px·겉모양 42×22
  - 도면 페이지: `도면 전체 저장 (N개 · ZIP)` 주 버튼 + 접힌 `하나씩 저장`

### 후속 — 도면 미리보기 크기·버튼 (사용자 지적 2026-08-31)

운영 확인 중 지적: PC 에서 미리보기가 우표만 하게 작고, 저장 버튼이 화면 폭을 다 먹는다. '도면 미리보기' 글자는 뺄 것.

- 미리보기 격자를 `repeat(auto-fit, minmax(min(100%, 300px), 1fr))` 로 — 장수에 따라 알아서 나뉜다.
  실측: PC 1440px 1장 = 카드 460×648(이미지 원본 비율), 2장 = 355×266 나란히 / 모바일 390px 1장 = 358×505, 2장 = 358×269 세로 적층.
- 1장뿐이면 비율 고정을 풀고(`aspect-ratio: auto`) 이미지 폭에 카드를 맞춘다 — 세로 도면 옆에 흰 카드가 넓게 남지 않는다.
  presign 만료로 이미지가 안 뜰 때 카드가 0 으로 접히지 않게 `min-width/min-height: 160px` 하한.
- 저장 버튼 52px 전폭 → **340×44**(터치 하한 유지, 가운데 정렬). 모바일에서는 컨테이너 폭에 맞춰 328×44.
- **함정**: 공유 페이지에는 CSS 리셋이 없어 기본이 `content-box` 다 — `max-width: 340px` 이 패딩만큼 커져 실측 380px 로 나왔다. `.foms-share-dl` 하위에 `box-sizing: border-box` 를 걸어 교정.
- 재정의는 전부 `.foms-share-view` 스코프. 공용 `foms-drawing-mobile.css`(ERP 큐 카드 하한 140px)는 손대지 않았고 계약 테스트가 그걸 고정한다.
- '도면 미리보기' 머리줄과 중복 안내 문구는 `share_mode` 에서만 제거(ERP 화면 무변경, 계약 테스트 2건).
- 자산 핀 `20260831a` → `20260831b`.

### 후속 2 — 인쇄 버튼·CI 승격 (2026-08-31)

- **계약서 인쇄 버튼을 폰에서 감춤**(`90d465e3`, PR #211). 카톡 인앱 웹뷰에는 인쇄 구현이 없어
  눌러도 안 되는 버튼이 정상 경로인 척한다 — 최초 신고와 같은 모양. 마크업은 남기고
  599.98px 이하에서만 `display: none`(PC 는 정상 동작하므로 유지). 실측 390px none / 1280px block.
  자산 핀 `20260831b` → `20260831c`.

- **운영 승격 PR 이 11~16분 걸리던 이유 해결**(PR #210, production `284dba11`).
  **CI 단축 5건이 전부 deploy 에만 있고 production 에는 하나도 없었다.** 승격 PR 은 production
  기준으로 체크아웃해 돌기 때문에 옛 `conftest.py`(PBKDF2 60만회)·옛 `ci.yml`(단일 프로세스)로
  6,800여 개를 돌고 있었다.
  - 근거: `git show origin/production:tests/conftest.py | grep -c PBKDF2` → 0 (deploy 5),
    production `ci.yml` 에 `--dist loadfile` 부재, `pytest.ini` 자체 부재
  - 승격한 5건: PBKDF2 완화 · pytest.ini SSOT · 병렬 실행(+순서 의존 2건 수정) ·
    PRAGMA 누출 수정 · 스키마 세션화. 전부 테스트·CI 설정 파일만 건드린다
  - 의존 1건(`pytest.ini`) 누락은 `test_ptc_physical_exactness` 가 잡았다(`missing_from_repo=['pytest.ini']`)
  - 실측: 승격 트리 전체 스위트 **6821 passed / 106초**, PR #210 자신의 `test` 잡 **2분 54초**(전 11분 30초)
  - **교훈**: CI 자체를 고친 커밋은 운영 트리에 없으면 운영 관문이 계속 옛 속도로 돈다.
    `project_promotion_pr_skipped_main_suite` 와 같은 축의 함정이다.

### 후속 3 — 모바일 일괄 저장을 '합본 사진 1장'으로 (사용자 지시 2026-08-31)

지시: "모바일에선 zip 을 빼자. iOS 호환도 체크하고, 사진 오른쪽 상단 아이콘으로도 저장되게. PDF 는 당장은 하지 마."

- **왜 ZIP 이 모바일에서 못 쓰는가**: 압축을 풀어야 하고, 사진첩에 안 들어가고, 인앱 웹뷰는 다운로드를 무시하는 사례가 있다. 반면 **이미지 롱프레스 저장은 다운로드 권한이 필요 없어** 인앱에서도 산다.
- 신설 `GET /s/<token>/drawings-sheet.png` — 도면 **이미지만** 세로로 이어붙인 PNG 1장. 검증 체인은 `_resolve_share_target` 재사용, 파일 수집은 `_collect_drawing_files`(주문 격리 승계), 한 장이라도 못 읽으면 503(ZIP 과 같은 규칙), 감사는 `FILE_DOWNLOAD` 재사용, `record_view` 미호출.
- 기본 inline(화면에 떠야 롱프레스가 된다), `?download=1` 이면 attachment.
- **픽셀 예산 16MP** — 총괄이 40MP 에서 낮췄다. 40MP 는 RGB 로 펼치면 약 120MB 라 아이폰 인앱 웹뷰가 디코딩에 실패할 수 있다. 저장소가 이미 쓰는 iOS 상한(`share-contract.js` `MAX_CANVAS_PIXELS`)과 같은 값으로 맞추고 계약 테스트로 묶었다.
- 예산 초과는 **거절이 아니라 축소** — 거절하면 고객에게 받을 길이 남지 않는다.
- 투명 PNG 는 흰 배경에 alpha 합성(그냥 `convert('RGB')` 하면 투명부가 검게 나온다).
- UI: 모바일=합본 주 버튼(ZIP 감춤) / PC=ZIP(합본 감춤). 분기는 **CSS 599.98px** — UA 스니핑 금지.
  단 합본 버튼이 실제로 있을 때만 ZIP 을 감춘다 — PDF 만 있는 주문에서 둘 다 사라지면 폰에 일괄 저장 수단이 없어진다(음성 대조군 테스트).
- 카드 우상단 저장 아이콘(선형 SVG, 32×32 겉모양 + 히트 44px). 카드가 `<button>` 이라 `<a>` 중첩 금지 → 형제로 두고 래퍼로 겹친다. `share_mode` 안에서만 렌더(ERP 무변경).
- URL 짝짓기는 인덱스 대조 대신 서버가 카드 dict 에 `download_url` 을 직접 싣는다(presign 일부 실패 시 엉뚱한 파일 방지).
- 자산 핀 `20260831c` → `20260831d`(share-view 계열만; contract 자산은 무변경이라 `c` 유지).
- 검증: APP_OK · 180 passed(계약 테스트 23건 신규) · pre_push_smoke exit 0 ·
  실브라우저 실측(모바일 390px 합본 flex/ZIP none·아이콘 32×32 히트 44px / PC 1280px ZIP flex·합본 none / `<button>` 안 `<a>` 중첩 0건).
- **PDF 는 합치지 않는다**(사용자 명시). '하나씩 저장' 목록에서 받는다.

### 후속 4 — 계약서 라이브 반영 (사용자 지시 2026-09-01)

지시: "도면은 실시간 반영되는데 계약서는 금액을 바꿔도 최초 것이 pinned 돼 있다. 실시간 반영으로 바꿔라."

**D6 동결을 뒤집은 결정이다.** 발급 시점 스냅샷을 얼려 두던 규칙(금액 문서라 그렇게 잡았다)을 라이브로 바꿨다.

- `_live_estimate_snapshot(row, order)` 신설 — estimate·bundle 두 경로가 같이 쓴다.
  **유출 차단은 유지**: 라이브 주문 값을 템플릿에 직접 넘기지 않고 `build_estimate_snapshot`
  화이트리스트를 열람할 때마다 다시 태운다(타 브랜드 계좌·내부 플래그는 키 자체가 안 생긴다).
- 날짜 두 축 분리 — 라이브로 바꾸면서 새로 생기는 함정 두 개를 막는다:
  - `issued_date` = 주문 `structured_updated_at`(KST). 오늘 날짜를 박으면 **아무것도 안 바뀐
    계약서의 날짜가 매일 굴러간다**.
  - `contract_no_date` = **발급 시점 고정**. 계약번호가 발행일에서 나오므로 여기까지 라이브면
    고객이 들고 있는 번호가 날마다 달라진다.
- 폴백: 라이브 재구성이 `SnapshotTooLargeError` 면 발급본 사용(빈 화면보다 낫다).
  라이브도 저장본도 없으면 503(빈 계약서·도면만 보여주기 금지).
- 저장 스냅샷 없는 링크가 이제 503 대신 정상 렌더된다. 발급 스냅샷은 계약번호 고정·폴백용으로 계속 저장.
- 화면 문구: "…기준으로 발행된 내용입니다" → "…기준 계약 내용입니다. 변경되면 이 화면에도 반영됩니다."
- 동결 강제 계약 테스트 4건을 라이브 계약으로 뒤집고, 계약번호 고정·폴백·양쪽 부재 503 신규 3건.
- 검증: APP_OK · 214 passed · pre_push_smoke exit 0 · deploy `240dad29a` CI 4/4 green.
- **운영 반영 완료** — PR #235(합본 사진 `54936d3f` 동반 승격), production `77fd9354e`, 검사 4/4 pass.

**의도된 부작용(기록)**: 고객이 어제 본 금액이 오늘 다르게 보일 수 있다. 계약서에 법적 효력 문구가 있는 문서라, 발급 이력 보존은 별도 작업으로 남는다(이번 범위 밖 — 사용자에게 고지함).

### 남은 미검증 (실기기 없음 — 사용자 확인 필요)

1. 카카오톡 인앱에서 `Content-Disposition: attachment` zip 이 실제로 파일로 남는가 (개별 저장 폴백도 같은 메커니즘이라 함께 실패할 수 있다)
2. iOS 카카오톡 UA 에 `KAKAOTALK` 리터럴이 들어가는가 (틀리면 인앱 안내가 안 뜬다 — 다만 터치 폴백이 덮는다)
3. 1~3MB dataURL 이 인앱 웹뷰에서 저장·표시되는가
4. `html2canvas` CDN 이 인앱 웹뷰에서 로드되는가 (15초 타임아웃 후 안내는 뜬다)
5. 200MB zip 이 Railway 타임아웃 안에 완주하는가

### 대표 결정 필요

- 품목 `option_detail`(상세옵션)은 스냅샷에 있으나 화면에 없다. **ERP 계약서 폼도 안 그린다** — "ERP 폼 그대로" 결정과는 일치하지만, "세부내용"이 이걸 뜻했다면 미충족.

### 후속 5 — 계약서 열람 이력 보존 (SHARE-HIST-00, 2026-09-01)

후속 4 가 남긴 "의도된 부작용"(고객이 어제 본 금액이 안 남는다)을 메운다.
설계·결정: `docs/specs/2026-09-01-share-contract-view-history-design.md`.
브랜치 `session/sharehist`(워크트리 `c:\tmp\foms-s-sharehist`, base `origin/deploy`).

**사용자 결정**: 새 원장 테이블 / 고객이 **열람할 때만** 기록 / 주문 볼 수 있는 직원 전부 열람 / 영구 보존.

- `order_field_changes` 로 대신하지 않은 이유: 그쪽은 **주문 값**의 변경 이력이다. 계약서 표면에는
  회사정보·계좌(발주사 판정 1벌)·화이트리스트 버전·발급 시점 고정 계약번호가 함께 들어가 재생(replay)
  결과가 당시 화면과 달라진다. 그래서 **열람 시점 렌더 dict 그대로** 남긴다.
- 신설 `order_share_snapshots`(마이그레이션 `sharehist_00`, down_revision `naverdisp_00`).
  **FK 없음**(감사 원장 규약 — 주문 hard purge 가 증거를 지우면 안 된다).
  **UNIQUE 없음** — `(share_token_id, content_hash)` 를 묶으면 금액 A→B→A 되돌림의 세 번째 상태가
  첫 행에 흡수돼 시간축이 무너진다. 중복 판정은 **그 토큰의 최신 행과만** 한다(계약 테스트로 3행 고정).
- 적재는 `foms/services/order_share_history.py`, 호출은 열람 경로 2곳(estimate·bundle).
  **호출 순서 규칙**: 이력 적재 → 실패 시 `rollback`+`logger.error` → `record_view` → `commit`.
  반대로 두면 적재 실패의 rollback 이 열람 횟수 증가까지 되돌린다.
- `_live_estimate_snapshot` 반환형을 `(dict, source)` 로 넓혔다 — 폴백으로 발급본이 뜬 화면도
  고객이 본 화면이므로 남기되 `source='stored'` 로 구별한다("왜 옛 금액이 떴나"의 답).
- 직원 조회 2개(GET, `_SHARE_ROLES`): `/api/share/history/<share_id>`(요약만 — 스냅샷 원문은 목록에
  안 싣는다) + `/api/share/history/<snapshot_id>/page`(고객 템플릿 그대로 렌더, ERP 는 **새 탭**으로 연다
  → ERP 셸에 공유 전용 CSS 를 안 끌어들인다). `/api` 아래 HTML 페이지가 되는 어색함은 감수했다 —
  새 블루프린트·디렉토리는 네임스페이스 닫힌집합 게이트를 건드린다.
- 감사 `SHARE_HISTORY_VIEWED` + `audit_message_display` 라벨 등재(미등재 시 CI red — 기존 함정).
- 고객 경로 무변경: 배너는 `history_meta is defined` 분기 안에만 있고 음성 대조군 테스트가 고정한다.
- **핀 함정**: `erp-share.js` 를 고치면 `test_share_trace_assets_pinned_together` 가 alimtalk trace
  자산과 **같은 핀**을 요구한다 — `erp-alimtalk-trace.js/.css` 까지 `20260901a`→`20260901b` 동반 범프.
  계약서 CSS 는 배너 규칙이 추가돼 `20260831c`→`20260901a`(estimate·bundle 두 템플릿).
- 모달 목록 행에 버튼이 셋(기록·회수·상태)이 되어 좁은 폭에서 넘친다 → 라벨을 자르는 대신 `flex-wrap`.

**검증(직접 실행)**
- `python -c "import app; print('APP_OK')"` → `APP_OK` / `python -m alembic heads` → `sharehist_00` 단일 head
- 신규 `tests/domains/test_order_share_history.py` **16 passed**(A→B→A 3행·폴백 source·적재 실패 200·
  drawing 0행 음성 대조군·목록에 스냅샷 원문 부재·권한 2종·감사 1행·고객 화면 배너 부재)
- 공유 계열 + UI 계약 **261 passed**, 게이트(contracts·failopen·write_guard·audit coverage·auth·state) **174 passed**
- `python tools/harness/failopen_scan.py` 재생성(574 broad / 0 unclassified)
- **PG 레인 전수 735 passed**(PG17 신규 클러스터 5441 — 기존 `c:\tmp\foms-pglane` 는 데이터 파일 손상으로
  `CREATE DATABASE` 가 `base/1/4171` 없음으로 죽는다. `initdb` 로 새로 만들어야 한다).
  `test_migration_chain` 통과 = models↔마이그레이션 지문 일치
- `pre_push_smoke.ps1` exit 0
- 실브라우저(gstack browse, 로컬 렌더): 390px 배너 358×121·가로 넘침 0 / 1280px 배너 700 문서 720,
  계약서 본문·계좌 복사·저장 버튼 무변경. 검증용 임시 주문 2914 는 삭제했다.

**남은 일**: 운영 승격(PR) — 승격 시 마이그레이션 1건이 함께 간다.

**운영 반영 완료(2026-09-01)** — PR #237 머지, production `b1ed7bff`. 검사 4/4 pass.
승격 시 충돌 2건은 이렇게 풀었다: `test_alimtalk_ui_contract.py` 는 **production 쪽 구현이 더
엄격**(자산 이름 기준)이라 그대로 두고 핀 리터럴만 `20260901a`→`b`, failopen 인벤토리는 생성물이라
승격 트리에서 재생성. 승격 트리에서 **전체 스위트 8038 passed** 직접 실행(승격 PR 은 본 스위트를
안 도는 구멍이 있다). 운영 확인: `erp-share.js?v=20260901b` 실서빙 + 운영 DB `order_share_snapshots`
존재·`alembic_version=sharehist_00`.
무관 기존 red 1건 기록: `test_erp_order_edit_mobile_form.py::test_edit_erp_order_ships_responsive_form_mounts_for_cohort`
는 **깨끗한 origin/production 체크아웃에서도 빨강**이다(이 작업이 만든 것이 아니다).

**실서버 확인(2026-09-01, claude_master)**

- **스테이징 E2E(쓰기 포함)**: 가상 주문 `CLAUDE-TEST-share-hist`(더미 010-0000-0000) 생성 →
  계약서 링크 발급 → 비로그인 열람(1,000,000) → 금액 변경 → 재열람(1,400,000) →
  **이력 2행**(각 행이 자기 금액 보존) → 그 시점 화면 200(배너 표시·옛 금액 표시·**새 금액 누출 0**) →
  주문 soft delete 정리. 함정: `/add` 의 ERP 경로는 `create_mode=ERP_ORDER` 이고 **ADMIN 은
  `sales_owner_id`(활성 SALES) 지정이 필수**다(UI 에는 그 입력칸이 없어 폼 흉내로는 안 만들어진다).
- **운영(읽기 전용, 계정 해제→확인→재잠금)**: 배포 직후 **실고객 열람 1건이 이미 원장에 쌓여 있었다**
  (`order_share_snapshots` 1행, share 17, `source=live`). 직원 이력 목록 200(스냅샷 원문 미포함 확인),
  그 시점 화면 200(배너·계약 내용), **열람 전 링크는 0행**(음성 대조군), 주문 편집 화면에
  `erp-share-history`·"고객이 본 내용"·`erp-share.js?v=20260901b` 모두 실림.
  운영 쓰기는 하지 않았다(감사 `SHARE_HISTORY_VIEWED` 1건은 허용 잔여물). 계정 재잠금 완료.
