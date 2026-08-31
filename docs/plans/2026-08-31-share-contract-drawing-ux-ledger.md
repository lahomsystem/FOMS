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

### 남은 미검증 (실기기 없음 — 사용자 확인 필요)

1. 카카오톡 인앱에서 `Content-Disposition: attachment` zip 이 실제로 파일로 남는가 (개별 저장 폴백도 같은 메커니즘이라 함께 실패할 수 있다)
2. iOS 카카오톡 UA 에 `KAKAOTALK` 리터럴이 들어가는가 (틀리면 인앱 안내가 안 뜬다 — 다만 터치 폴백이 덮는다)
3. 1~3MB dataURL 이 인앱 웹뷰에서 저장·표시되는가
4. `html2canvas` CDN 이 인앱 웹뷰에서 로드되는가 (15초 타임아웃 후 안내는 뜬다)
5. 200MB zip 이 Railway 타임아웃 안에 완주하는가

### 대표 결정 필요

- 품목 `option_detail`(상세옵션)은 스냅샷에 있으나 화면에 없다. **ERP 계약서 폼도 안 그린다** — "ERP 폼 그대로" 결정과는 일치하지만, "세부내용"이 이걸 뜻했다면 미충족.
