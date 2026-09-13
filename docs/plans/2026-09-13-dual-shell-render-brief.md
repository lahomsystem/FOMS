# PC 화면 아래 모바일 큐가 같이 뜬다 — 조사·수정 브리프 (초안, CEO 가 고쳐도 된다)

## 증상 (사용자 보고 + 총괄 실측)
도면 작업실에서 **영업 담당자가 도면 수령 확정**을 한 뒤, ERP 대시보드로 돌아오면
**데스크톱 표 아래에 모바일 큐 화면이 통째로 같이 렌더된다.**

- 화면 URL: `https://lahom-production.up.railway.app/erp/dashboard?focus_order=5177&open_quest=true`
- 사용자가 붙여준 실제 DOM 최상단: `<div data-foms-mobile-queue-chunk="">`
  그 안에 `긴급 · 오늘 처리 필요` 섹션 + `foms-queue-card-v2` 카드가 수십 장.
- 데스크톱 표(페이지네이션 `총 1352건 (1/28페이지)`)는 정상으로 위에 있다.

## 총괄이 이미 확정한 사실 (다시 조사하지 말 것)

1. 끼어든 마크업의 정체는 **모바일 무한스크롤 청크**다.
   생산자: `templates/orders/partials/dashboard_mobile_v2_chunk.html:1`
   (`<div data-foms-mobile-queue-chunk data-next-page=... data-total-pages=...>`)
2. 그 청크를 내보내는 자리는 [foms/web/orders/dashboard.py:479](foms/web/orders/dashboard.py) 다:
   ```python
   if mobile_v2 and request.args.get('mobile_chunk') == '1':
       _chunk = render_template('orders/partials/dashboard_mobile_v2_chunk.html', **_mobile_ctx)
       response = make_response(_chunk)
       apply_erp_shell_fragment_headers(response, request)
       return response
   ```
   즉 **`mobile_v2` 이고 `?mobile_chunk=1` 일 때만** 청크를 돌려준다.
3. 그 청크를 DOM 에 꽂는 유일한 소비자는
   [static/js/foms/mobile-queue-scroll.js:50](static/js/foms/mobile-queue-scroll.js) 이다
   (`doc.querySelector('[data-foms-mobile-queue-chunk]')`).
4. 같은 `data-foms-mobile-queue-chunk` 를 쓰는 곳이 하나 더 있다:
   `templates/drawing/partials/workbench_mobile_queue_chunk.html:3` (도면 작업실).
   **증상이 "도면 작업실에서 수령 확정한 뒤"에 난다는 점과 이어질 수 있다.**
5. 셸 판정은 `resolve_shell_variant_cached(uid)` → `is_mobile_v2_shell(...)`
   ([foms/web/orders/dashboard.py:413-414](foms/web/orders/dashboard.py)) 이고,
   같은 파일 `_has_drill` 에 **`request.args.get('focus_order')` 가 포함돼 있다**
   (드릴이 걸리면 타워 대신 큐로 전환).
6. 셸 변형은 **사용자 코호트 기반**이다(UA 기반이 아니다). 이 점이 "PC 인데 모바일이 나온다"의
   열쇠일 수 있다 — 확인은 조사 몫.

## 핵심 질문
**데스크톱 셸로 렌더된 페이지에 모바일 청크가 어떻게 들어갔는가.**
세 갈래 중 어디인가 — ① 서버가 한 응답에 둘 다 넣었다 ② 데스크톱 페이지의 JS 가 모바일
청크를 가져다 붙였다 ③ 수령 확정 후 이동/새로고침 경로가 잘못된 응답을 재사용했다.

## 조사 갈래 (병렬)

### A. 서버 렌더 경로
- `/erp/dashboard` 가 한 응답에 데스크톱 본문과 모바일 청크를 **함께** 낼 수 있는 경로가 있는가?
- `mobile_v2` 판정과 `template_name`(`dashboard.html` vs `dashboard_main.html`) 조합을 전수로 따져라.
- `wants_erp_shell_tab_body(request)` 가 언제 참인가? 프래그먼트 요청과 전체 페이지 요청이
  섞이면 어떤 마크업이 나가는가?
- `dashboard_mobile_v2_body.html:117-119` 가 데스크톱 본문에서도 include 되는 조건이 있는가?
- `apply_erp_shell_fragment_headers` 가 붙인 헤더가 캐시와 어떻게 작용하는가(같은 URL 로 청크가
  캐시돼 전체 페이지 자리에 재사용될 수 있는가).

### B. 클라이언트 주입 경로
- `static/js/foms/mobile-queue-scroll.js` 전문을 읽어라. **이 스크립트가 데스크톱 셸에서도
  로드되는가?** 로드되면 어떤 조건에서 `?mobile_chunk=1` 을 부르고 어디에 붙이는가?
- 붙일 대상 컨테이너가 없을 때 어떻게 되는가(문서 끝에 append 하는가)?
- 도면 작업실의 `workbench_mobile_queue_chunk.html` 을 쓰는 스크롤 스크립트와 같은 코드를
  공유하는가? 도면 작업실에서 켜진 리스너가 대시보드로 이동한 뒤에도 살아 있을 수 있는가
  (ERP 셸이 SPA 식 탭 전환을 한다면 특히).
- 셸 v3/v2 에서 이 스크립트가 실리는지 여부를 자산 목록으로 확인하라.

### C. 수령 확정 → 대시보드 복귀 동선 재현
- 도면 작업실에서 **수령 확정** 버튼을 누르면 무엇이 실행되고 어디로 이동하는가?
  (`foms/api/drawing/erp_orders_draftsman.py:336` 부근이 서버, 버튼은
  `templates/drawing/partials/workbench_detail_body.html`)
- 이동 URL 에 `focus_order`·`open_quest` 가 어떻게 붙는가? 전체 페이지 이동인가 프래그먼트인가?
- **스테이징에서 실제로 재현하라.** `claude_master` 로 로그인해
  `/erp/dashboard?focus_order=<id>&open_quest=true` 를 데스크톱 UA 로 받아
  응답 HTML 에 `data-foms-mobile-queue-chunk` 가 들어 있는지 확인한다.
  들어 있으면 서버 경로(A), 없으면 클라이언트 주입(B)이다. **이 한 번이 갈래를 가른다.**
  스테이징 자격증명: `C:\Users\USER\.claude\projects\c--DEV-FOMS\secrets\claude_master.json`
  (`username` 은 최상위, `staging.base`·`staging.password`). 로그인은 `POST /login` 폼, CSRF 없음.
  실제 발송·운영 쓰기 금지.

## 워커 공통 규칙
- 작업 트리는 `C:\tmp\foms-s-dualshell` 다. 매 명령을 `pwd` 로 확인한다.
- **git 명령 금지**(commit·push·checkout·stash 전부). 총괄이 한다.
- 운영 DB·운영 화면은 **읽기 전용**. 쓰기 금지. 스테이징은 읽기 위주, 필요한 최소 쓰기만.
- 채널톡·알림톡 실제 발송 금지.
- 파일은 파이썬으로 쓸 때 `newline="\n"`.
- 조사 단계 워커는 파일을 수정하지 않는다. 결론과 근거(경로:행, 코드·HTML 인용)만 낸다.
- 추측을 사실처럼 쓰지 마라.

## 검증 명령
- `python -c "import app; print('APP_OK')"`
- `node --check static/js/foms/mobile-queue-scroll.js` (JS 를 고쳤다면 필수 — pre_push_smoke 는 JS 구문을 안 본다)
- `python -m pytest tests/domains -q -k "dashboard or mobile or shell"`
- `python -m pytest tests/domains -q` (통합 검증자만)

## 함정
- 셸 변형은 **사용자 코호트**로 정해진다. UA 로 판정한다고 가정하지 마라.
- `static/js/**` 를 고치면 그 자산의 `?v=` 핀을 올려야 하고, 핀을 못박은 테스트가 있을 수 있다
  (`grep -rn "mobile-queue-scroll" templates/ tests/`).
- `docs/AI_STATUS.md` 상단 40줄 4,000자 예산은 테스트가 강제한다 — 총괄만 만진다.
- 대시보드는 hot path 다. 쿼리를 늘리는 수정은 금지(성능 가드가 막는다).
