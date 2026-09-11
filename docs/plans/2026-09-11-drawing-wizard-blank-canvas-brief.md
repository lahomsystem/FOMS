# 도면 마법사 백지 로딩 — 조사·수정 브리프 (초안, CEO 가 고쳐도 된다)

## 증상 (사용자 보고 + 총괄 실측)
영업 담당자가 도면 수정요청을 한 뒤, 도면 담당자가 도면 마법사에 들어가면 **기존에 저장했던
도면이 안 뜨고 백지가 뜬다.**

재현 대상: 운영 주문 **5177**(임인경, 양산지사)
화면: `https://lahom-production.up.railway.app/erp/drawing-workbench/5177/wizard`

## 총괄이 이미 확정한 사실 (다시 조사하지 말 것)

1. `structured_data['drawing_wizard']` 는 **살아 있다**. 시트 2장, `updated_at = 2026-09-11 00:00:54`,
   `updated_by = 38`, `updated_by_name = '이시영'`(영업 담당자).
2. 두 시트 모두 **`objects: []`** — 캔버스 오브젝트만 비었다. `form`(고객명·연락처·색상·체크박스 등)과
   `product_index` 는 정상이다. 그래서 화면에 하단 표·시트 탭·제품 목록은 나오고 그림만 없다.
3. `drawing_current_files` 에는 **2026-09-10 00:04 에 내보낸 PNG 2장**이 남아 있다
   (`orders/5177/drawing_wizard/exports/20260910_0004*.png`). 그 시점에는 그림이 있었다.
4. `drawing_status = RETURNED`.
5. **운영 전체에서 `drawing_wizard` 키를 가진 주문은 5177 한 건뿐이다.** 이 사실의 의미(마법사 상태가
   원래 거의 저장되지 않는지, 기능이 최근인지)는 아직 모른다 — 조사 대상이다.
6. 서버 PUT `/<order_id>/drawing-wizard`([foms/api/drawing/wizard.py:647](foms/api/drawing/wizard.py))
   는 REV-00 행 잠금 + `base_updated_at` stale 409 + `_project_wizard_state` 화이트리스트로
   방어돼 있다. 다만 **클라이언트가 빈 `objects` 를 보내면 그대로 저장된다** — 서버는 빈 캔버스 저장을
   막지 않는다(사용자가 지웠을 수도 있으므로 그 자체는 설계대로일 수 있다).

## 핵심 질문
**09-10 00:04 에 그림이 있던 상태가, 09-11 00:00:54 이시영 저장에서 `objects: []` 로 덮인 경로가 무엇인가.**

## 앵커 (경로:행)
- 서버 상태 GET: `foms/api/drawing/wizard.py:551` `api_get_drawing_wizard`
- 서버 상태 PUT: `foms/api/drawing/wizard.py:647` `api_put_drawing_wizard`
- projection: 같은 파일 `_project_wizard_state`
- pending 서비스: `foms/services/orders/drawing_wizard_pending.py`
- 클라이언트: `static/js/drawing/wizard.js` (핀 `?v=` 는 `templates/drawing/wizard.html`)
- 마법사 페이지 라우트: `foms/web/drawing/wizard.py`
- 워크벤치 상세(수정요청 탭 `?tab=requests`): `foms/web/drawing/workbench.py:768`

## 조사 갈래 (병렬)

### A. 클라이언트 로딩·저장
`static/js/drawing/wizard.js` 에서:
- 서버 `state.sheets[].objects` 를 캔버스로 복원하는 경로. 복원 실패 시 어떻게 되는가(빈 캔버스로 계속 가는가).
- 저장 payload 를 만드는 경로. **로딩이 끝나기 전/실패한 뒤에도 저장이 나갈 수 있는가.**
- 자동저장이 있는가. 있다면 트리거와 가드.
- `objects` 가 비어도 저장을 보내는가. 사용자가 "지운 것"과 "못 불러온 것"을 구분하는가.

### B. 서버 저장·로딩 경로
- `_project_wizard_state` 가 `objects` 를 떨구거나 비울 수 있는 입력이 있는가.
- GET 이 `objects` 를 빼고 주는 조건(용량 캡·pending·versions 분리 등)이 있는가.
- 크기 제한(1 MiB body cap 등)에 걸려 `objects` 가 잘려 나가는 경로가 있는가.
- `drawing_wizard_pending` 이 상태를 대체·초기화하는 경로가 있는가.

### C. 수정요청 경로와 실제 행위 추적
- 워크벤치 `?tab=requests` 에서 영업이 "도면 수정요청"을 누르면 무엇이 실행되는가.
  그 경로가 `drawing_wizard` 를 건드리는가(RETURNED 전이 포함).
- 운영 감사 원장에서 주문 5177 의 2026-09-10 ~ 09-11 행위를 시간순으로 뽑아
  **누가 무엇을 눌렀고 `DRAWING_WIZARD_SAVED` 가 언제 찍혔는지** 확인한다. 읽기 전용 조회만 한다.
  접속 DSN: `C:\Users\USER\AppData\Local\Temp\claude\c--DEV-FOMS\c58dbabc-9401-4908-81bd-23f7618d8c2d\scratchpad\prodlink\dburl.txt`
  표: `access_logs(action, detail, timestamp, user_id)`.

## 워커 공통 규칙
- 작업 트리는 `C:\tmp\foms-s-dwfix` 다. 매 명령을 `pwd` 로 시작해 확인한다.
- **git 명령 금지**(commit·push·checkout·stash 전부). 총괄이 한다.
- CRLF 보존: 파일을 파이썬으로 쓸 때 `newline="\n"` 로 쓰고, 기존 줄끝을 바꾸지 않는다.
- 운영 DB 는 **읽기 전용**. UPDATE/INSERT/DELETE 금지.
- 채널톡·알림톡 실제 발송 금지.
- 조사 단계 워커는 **파일을 수정하지 않는다**. 결론과 근거(경로:행, 코드 인용)만 낸다.

## 검증 명령
- `python -c "import app; print('APP_OK')"`
- `python -m pytest tests/domains -q -k "wizard or drawing"`
- `python -m pytest tests/domains -q` (통합 검증자만)
- `powershell -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1` (총괄만)

## 함정
- `static/js/drawing/wizard.js` 를 고치면 `templates/drawing/wizard.html` 의 `?v=` 핀을 올려야 한다.
  핀을 못박은 테스트가 있다: `grep -rn "?v=20260910a" tests/` 결과를 소유권 표에 넣을 것.
- `docs/AI_STATUS.md` 상단 40줄 4,000자 예산은 테스트가 강제한다 — 총괄만 만진다.
- 이 트리에는 다른 세션의 미커밋 변경이 넘어오지 않았다. 메인 체크아웃과 혼동하지 말 것.
