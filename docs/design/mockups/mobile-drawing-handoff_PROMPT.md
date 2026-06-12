# 구현 프롬프트 — 도면팀 ↔ 영업 모바일 협업 재설계

> 아래 전체를 그대로 다른 LLM(코딩 에이전트)에게 붙여넣어 사용하세요.
> 전제: 그 에이전트는 **FOMS 저장소 안에서** 파일을 읽고/수정/실행할 수 있습니다.

---

## 0. 역할과 목표

당신은 FOMS(가구 주문관리 ERP, **Flask 2.3 + Jinja2 + Bootstrap 5 + Vanilla JS + SQLAlchemy/PostgreSQL**)의 시니어 프론트엔드+백엔드 엔지니어다.
목표: **도면 작업실(Drawing Workbench)의 "도면팀 ↔ 담당 영업" 모바일 협업 UX/UI를 재설계 구현**한다.
시각·레이아웃·UX의 **단일 기준(Source of Truth)** 은 아래 목업 파일이다 — 반드시 브라우저로 열어 그대로 본 뒤 구현한다.

- 목업: `docs/design/mockups/mobile-drawing-handoff.html` (디자인 토큰: 같은 폴더 `_tokens.css`)
- 목업은 폰 프레임 3개로 구성: **A. 도면 작업 큐**, **B. 도면 핸드오프 상세(한 장)**, **C. 장 목록(인박스, 도면 많을 때)**, 그리고 하단에 설계 의도·다중 도면 처리·스트립 vs 리스트 결론이 글로 적혀 있다.
- 목업은 **시각·흐름 기준**이지 코드 템플릿이 아니다. `390px` 폰 프레임, `preview-label`, `role-note`, 인라인 CSS/SVG, 문자/이모지 아이콘은 검토용 표현이다. 실제 제품에는 복사하지 말고, 기존 컴포넌트 CSS/아이콘/반응형 셸로 재구현한다.

---

## 1. 절대 원칙 (하드 룰 — 위반 금지)

1. **착수 전 `AGENTS.md`와 `CLAUDE.md`를 읽고 그 규칙을 따른다.** 충돌 시 `AGENTS.md` 우선.
   - 이어서 `git status --short`와 `git diff -- <수정 후보 파일>`을 확인한다. 기존 dirty worktree·미완성 패치를 덮어쓰지 말고, 이미 구현된 조각은 file:line 근거로 "재사용/보강/수정" 분류부터 한다.
2. **근본 원인 → 근본 수정.** 증상 우회·하드코딩·`try/except: pass`·임시 미봉책 금지.
3. **기존 API·권한·데이터 모델을 그대로 재사용한다.** 이 작업은 **"모바일 표현(레이아웃/UX)만"** 새로 얹는 것이다.
   - **새 DB 컬럼/스키마 만들지 말 것.** "여러 도면(파일)"·"전달 회차"는 기존 `drawing_current_files` + `drawing_transfer_history`로 **표현만** 한다. **상태는 주문 단위(`drawing_status`) 1개** — 장별 상태/확정/차수는 만들지 않는다(§5.1).
   - **새 엔드포인트 만들지 말 것**(불가피하면 먼저 근거를 제시하고 승인받는다). §4의 기존 엔드포인트를 쓴다.
4. **데스크톱(≥992px) 및 비-cohort 사용자에게 영향 0.** 모든 신규 스타일/마크업은 모바일 v2 cohort + 모바일 미디어쿼리로 게이트한다(§3, §5 참고).
5. **인라인 스타일 금지.** 스타일은 `static/css/components/foms-drawing-mobile.css` 등 컴포넌트 CSS에. jQuery 금지(`querySelector`/`fetch`). 인라인 `<script>` 300줄 초과 시 별도 `.js` 분리.
   - 목업 HTML의 인라인 `<style>`/SVG/고정 폰 프레임은 구현 참고용이다. 실제 앱은 `body.erp-mobile-v2-layout` 아래에서 360~430px 모바일과 768px 태블릿에 맞게 유동 레이아웃으로 만든다. `width:390px` 같은 고정 컨테이너 금지.
   - 버튼·툴 아이콘은 기존 프로젝트 아이콘 체계(Font Awesome/Bootstrap icon/lucide 등 실제 설치된 것)로 렌더한다. `⬆`, `↩`, `✓`, `≣`, `⤢`, 이모지 파일 아이콘 같은 raw glyph를 제품 UI에 하드코딩하지 않는다.
6. **정적 자산은 `?v=YYYYMMDDx` 쿼리로 캐시버스트**한다(변경한 css/js의 모든 로드 지점 버전 갱신).
7. **검증 없이는 "완료" 선언 금지.** §6 검증 단계 통과 필수.
8. 커밋은 **한글**로, Win11 인코딩 때문에 UTF-8 파일 저장 후 `git commit -F <파일>` 사용(`-m "한글"` 금지). `deploy`/`main` push **직전** `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual` 실행 → exit 0 확인. (push는 사용자가 지시할 때만)

---

## 2. 먼저 읽어 구조를 파악할 파일 (구현 전 필수 정독)

**템플릿(대시보드/큐)**
- `templates/drawing/workbench_dashboard.html`, `templates/drawing/partials/workbench_dashboard_body.html`
- `templates/drawing/partials/drawing_mobile_v2_gallery.html`, `drawing_mobile_controls.html`, `_mobile_filter_drawer.html`, `workbench_dashboard_macros.html`

**템플릿(상세/실행판)**
- `templates/drawing/workbench_detail.html`, `workbench_detail_fragment.html`, `templates/drawing/partials/workbench_detail_body.html`
  - ⚠️ 이 파일은 **데스크톱 실행판**(약 1900줄, 전달/수정/확정 모달 + JS 포함)이다. 모바일 협업 뷰는 **이걸 데스크톱까지 갈아엎지 말고**, 모바일 cohort에서만 새 표현을 보여주도록 추가/조건분기한다.

**CSS**
- `static/css/components/foms-drawing-mobile.css` (갤러리/§6.3 16:9 카드 — 도면은 `object-fit: contain` 권장)
- `static/css/components/foms-drawing-mobile-card.css` (큐 카드/썸네일/컨트롤)

**백엔드(데이터 계약·라우트·API)**
- `foms/web/drawing/workbench.py` — 라우트(`erp_drawing_workbench` blueprint, `url_prefix='/erp'`: 대시보드 `erp_drawing_workbench_dashboard`, 상세 `erp_drawing_workbench_detail`) **+ 행(row)·상세 컨텍스트 view-model을 실제로 만드는 곳**(`foms/services/erp_display.py`, `foms/services/order_event_display.py` 사용). "누구 차례·전달 회차·수정요청 대상 번호" 같은 파생값이 부족하면 **여기/서비스에서** 계산해 템플릿에 넘긴다(템플릿 로직 최소화).
- `foms/services/drawing_workbench_display.py` — ⚠️ **썸네일 노출(`drawing_thumb_enabled`)만** 담당. 데이터 계약 본체가 아님(혼동 금지).
- 도메인 데이터는 `order.structured_data` 안: `drawing_status`(주문 단위 1개), `drawing_current_files`(현재 도면 파일 배열, `key`로 식별), `drawing_transfer_history`(전달/수정요청 이력 = 회차·대상 번호의 출처).
- `foms/api/drawing/erp_orders_drawing.py`, `erp_orders_revision.py`, `erp_orders_draftsman.py` — 전달/수정/확정/담당 API
- `partials/shared/erp_mobile_shell.html`, `erp_sub_nav.html`, `partials/shared/erp_mobile_v2_tab_notice.html`

**테스트**
- `tests/domains/test_drawing_workbench_mobile.py`, `tests/visual/test_p1_mockup_structure.py`, `tests/visual/test_p1_mockup_png_gate.py`

---

## 3. 모바일 v2 cohort 게이트 (반드시 준수)

- 모바일 v2 표면은 `erp_mobile_v2_enabled` 플래그로 게이트된다(템플릿에서 `{% if erp_mobile_v2_enabled %}`). 페이지를 모바일 v2 셸에 넣으려면 보통 **3곳(layout / layout_head / 페이지)의 동일 게이트**를 통과해야 한다 — 기존 도면 대시보드가 어떻게 통과하는지 그대로 따른다.
- 데스크톱/태블릿엔 기존 표(`d-none d-lg-block`), 모바일엔 새 카드/리스트(`d-lg-none`) — 현재 `workbench_dashboard_body.html`의 표↔모바일카드 분기 패턴을 유지·확장한다.
- 모바일 전용 CSS는 `body.erp-mobile-v2-layout` + `@media (max-width: 991.98px)` 또는 `.d-lg-none`로 한정한다.
- 상세 진입 URL은 **기존 라우트** `/erp/drawing-workbench/<order_id>`를 유지한다. 새 엔드포인트 금지.
  - 도면 2개 이상 + `drawing_key` 없음 + 모바일 v2 cohort → 표면 C(목록)를 먼저 렌더.
  - 도면 1개 또는 `?drawing_key=<file.key>` 있음 → 표면 B(상세)를 렌더.
  - `?tab=timeline|requests|compare`, `event_id`, `target_no`는 기존 의미를 유지한다. 도면 선택 상태는 URL/query 또는 `data-*`로만 관리하고 DB에 저장하지 않는다.
  - **deep-link 예외**: `event_id` 또는 `target_no`가 있으면 목록(C)보다 해당 이력/대상 도면 상세(B)를 우선한다. 알림 링크가 목록 화면에 막히면 안 된다.
  - `drawing_key`가 현재 `drawing_current_files`에 없으면 빈 상세를 렌더하지 말고, multi-file이면 목록(C)+"선택한 도면을 찾을 수 없음" 안내, single-file이면 유일한 도면(B)으로 normalize한다.

---

## 4. 재사용할 기존 API (새로 만들지 말 것)

| 동작 | 엔드포인트 | 비고 |
|---|---|---|
| 도면 전달 | `POST /api/orders/<id>/transfer-drawing` | body: `{mode: APPEND\|REPLACE\|REPLACE_ALL, replace_target_keys[], note, files[], is_retransfer?}`. **주문 단위**. `REPLACE`는 `replace_target_keys`; `target_drawing_keys`는 수정요청 전용이다. |
| 도면 전달용 파일 업로드 | 기존 `workbench_detail_body.html`의 transfer upload 흐름 재사용: fallback `POST /api/orders/<id>/attachments`, 직접업로드 `/api/upload/session` → PUT → `/api/orders/<id>/attachments/complete` | 이후 `transfer-drawing`에 `files[]` 전달. |
| 수정요청 첨부 업로드(게이트웨이) | `POST /api/orders/<id>/drawing-gateway-upload` (직접업로드 시 `/api/upload/session` → PUT → `/api/orders/<id>/drawing-gateway/complete`) | 수정요청 이력 말풍선 첨부용. 전달용 파일 업로드와 섞지 말 것. |
| 수정 요청 | `POST /api/orders/<id>/request-revision` | body: `{note, files[], target_drawing_keys[]}`. 도면 여러 개면 **번호(key) 지정 필수**(단일은 `target_drawing_key`). 결과: **주문 상태 → RETURNED** + 이력에 `target_drawing_numbers` 기록 |
| 수정요청 반영 토글 | `POST /api/orders/<id>/request-revision-check` | |
| 수령 확정 | `POST /api/orders/<id>/confirm-drawing-receipt` | **주문 단위**(장 인자 없음). body: `{emergency_override, override_reason}`(선택). 장별 확정 같은 건 없음 |
| 전달 취소 | `POST /api/orders/<id>/cancel-transfer` | |
| 도면 담당 변경 | `POST /api/orders/<id>/assign-draftsman` · 일괄 `POST /api/orders/batch-assign-draftsman` | 도면팀만 |
| 도면팀 사용자 | `GET /erp/api/users?team=DRAWING` | |
| structured_data | `GET /api/orders/<id>/structured` | |

> 모든 응답은 `{success, data/message}` 형식. 호출 전 `data.success` 검증 + try/catch 필수.

---

## 5. 구현 범위 — 목업의 3개 표면 + 도메인 규칙

### 5.1 핵심 개념 — ⚠️ **주문 단위 v1**(데이터 현실에 정확히 맞춤)
- **상태는 주문에 1개**: `structured_data.drawing_status` (예: `TRANSFERRED`=확정대기, `RETURNED`=수정요청됨, `CONFIRMED`=완료, 그 외 작업/대기). **장별 독립 상태는 존재하지 않는다.**
- **"여러 장" = 도면 파일 여러 개**(`drawing_current_files`, `key`로 식별). 번호는 배열 순번(1번·2번…)일 뿐, 각자 다른 상태를 갖지 않는다.
- **"차수" = 주문 전달 회차**: `drawing_transfer_history`에서 파생(1차 전달·2차 전달…). **장별 v1/v2 같은 필드 없음.** "이전 전달본 vs 최신 전달본" 비교는 detail context의 `prev_transfer`/`latest_transfer`(주문 단위)를 쓴다.
- **"누구 차례"는 주문의 `drawing_status` 하나에서 파생**:
  - `TRANSFERRED` → **영업 확인 차례** · `RETURNED` → **도면팀 수정 차례** · (도면 미전달/작업중) → **도면팀 작업 차례** · `CONFIRMED` → **완료**
- **전달·확정·상태는 모두 주문 단위.** **단, 수정요청만 도면 번호 타깃 가능**(`target_drawing_keys`→`target_drawing_numbers`로 "2번 대상" 기록). 즉 "2번 도면 고쳐줘"는 되지만 "2번만 확정"은 v1에 **없다**.
- 🚫 **금지**: 장별 상태기계·장별 확정·장별 차수 필드를 새로 만들지 말 것. (그건 백엔드 신규 프로젝트이며 이 작업의 범위가 아님)

### 5.2 표면 A — 도면 작업 큐 (목업 프레임 A)
- 모바일 큐 카드에 **"● 내 차례 N건"** 그룹을 맨 위에, 그 아래 "상대 차례" 그룹.
- 카드 = 도면 썸네일(`object-fit: contain`, 전체 보임) + **"누구 차례 · 경과일" 리본** + 칩(도면 N장 / 미확인 / 지연 / 내 할 일) + 1탭 액션(상태별: 확정·수정요청 또는 도면전달). 버튼 안 아이콘은 raw glyph가 아니라 기존 아이콘 컴포넌트로 표시한다.
- 기존 `erp-drawing-mobile-card` 마크업/네비게이션(데이터-href, 담당자 모달)·`drawing_mobile_controls.html` 필터를 유지·확장.

### 5.3 표면 C — 도면 목록(골라보기) (목업 프레임 C) — **도면 파일 여러 개의 진입**
- 상세 진입 시 **도면 파일이 2개 이상이면 이 목록을 먼저** 보여준다. **1개면 목록 생략, 바로 표면 B**.
- 구성: **주문 상태 배너 1개**("영업 확인 차례 — 도면 6장 · 도면팀 N차 전달") → **도면 파일 행 리스트**(골라 보는 용도) → 하단 `＋ 도면 추가 전달`.
- 행 = 썸네일 + `N번` + 이름 + 최근 회차/메모(+ 최근 수정요청 대상이면 `수정 반영`/`수정요청 대상` 칩). 행 탭 → 같은 라우트의 `?drawing_key=<file.key>`로 표면 B(그 도면).
- 행의 `수정 반영`/`수정요청 대상` 칩은 **최근 이력·타깃 안내**일 뿐 상태 배지가 아니다. `progress`, `2/6 확정`, 장별 필터처럼 보이는 UI는 만들지 않는다.
- 🚫 **장별 상태 배지·진행률(2/6 확정)·장별 필터(내차례/수정중/확정) 만들지 말 것** — 상태는 주문 1개다. 목록은 어디까지나 "여러 도면을 빠르게 훑고 골라 보는" 용도.
- (왜 스트립 아니고 리스트인가: 도면 5~6개+에서 가로 스트립은 4번째부터 화면 밖에 숨음 → 한눈에 못 봄. 리스트가 정답. 목업 하단 결론 참조.)

### 5.4 표면 B — 도면 핸드오프 상세 (목업 프레임 B) — **주문 단위**
1. **"누구 차례" 리본** — 주문 상태 1개에서 파생(예: `영업 확인 차례 · 도면팀 2차 전달 · 2일째 대기`). 색: 내 차례=호박, 상대=파랑, 완료=초록.
2. **도면 뷰어** — `object-fit: contain`으로 **전체 도면** 크게. 같은 주문의 **도면 파일들 사이 좌우 스와이프**(도면 1/N). 전체화면·핀치 확대는 기존 `GlobalImageViewer`/lightbox 재사용. "이전 전달본 vs 최신 전달본" 비교는 `prev_transfer`/`latest_transfer`(주문 단위).
   - 뷰어 chrome에는 앱 차원의 `도면팀 확인`/`생산팀 확인`/체크박스를 만들지 않는다. 그런 문구가 업로드된 도면 이미지 안에 있으면 파일 내용일 뿐, FOMS 상태 UI로 해석하지 않는다.
3. **도면 페이저** — `‹ 도면 1/6 · 거실장 › · ≣목록` 으로 목록 안 거치고 옆 도면 이동.
4. **제작 자료(접힘)** — 제품정보(제품명·규격 W/D/H·색상·손잡이 등)+실측 이미지. 데이터는 `order.structured_data`/`product_items`/`common_measure_photos`에서.
5. **대화 스레드** — 전달/수정요청을 **말풍선**으로 시간순(도면팀 왼쪽·영업 오른쪽). 태그: `도면 전달 · N차` / `수정 요청 · N번(이름) 대상`(번호 타깃 표시) + 첨부 + 작성자/시각. 데이터는 `drawing_transfer_history`/`revision_requests`(**주문 단위 단일 스레드**).
6. **역할·상태 맞춤 액션 바(하단 고정)** — 주문 상태로 주 버튼 1개 결정:
   - 영업 & `TRANSFERRED` → **`✓ 수령 확정`**(주, 주문 단위) + `↩ 수정요청`(번호 선택 가능)
   - 도면팀 & `RETURNED`/작업 차례 → **`⬆ 도면 전달`**(주, 전달 모달)
   - `CONFIRMED` → 액션 비활성/`전달 취소`(권한 있을 때)
   - **표시(라벨/주버튼)만 상태·역할로 스왑하고, 실제 실행 가능 여부는 기존 `can_transfer`/`can_request_revision`/`can_confirm_receipt`/`can_cancel_transfer`/`can_open_transfer` 플래그가 최종 권위**(권한 로직 재구현 금지).

> 역할(도면팀 vs 영업)은 `current_user`의 팀으로 판별하되, **액션 노출/실행은 기존 `can_*` 플래그가 최종 권위**다. 라벨/주버튼만 상태·역할로 스왑한다.

---

## 6. 권장 구현 순서 + 단계별 검증

각 단계마다: **현 상태 감사 → 구현 → 검증 → (사용자 승인 시) 커밋.** 한 번에 다 갈아엎지 말 것.

- **Phase 0 — 현재 상태 감사 + Scope Lock**: `git status --short`, 대상 파일 diff, `workbench_dashboard_body.html`/`workbench_detail_body.html`/CSS의 기존 모바일 구현을 먼저 확인한다. 이미 있는 썸네일·필터·액션 바·JS를 중복 구현하지 말고, 누락/회귀 위험만 file:line으로 잠근다. 특히 모바일 상세의 기존 하단 액션 바가 non-cohort 모바일에 노출되는지 확인하고, 보강 시 반드시 `erp_mobile_v2_enabled`/`body.erp-mobile-v2-layout`로 게이트한다.
- **Phase 1 — 큐(표면 A) 재설계**: `workbench_dashboard_body.html` 모바일 카드 + `foms-drawing-mobile-card.css`. (내 차례 그룹, 누구차례 리본, 썸네일 contain, 1탭 액션)
- **Phase 2 — 도면 목록(표면 C)**: 도면 파일이 여러 개면 상세 진입을 목록(골라보기)으로. view-model은 **`foms/web/drawing/workbench.py`/서비스**에서 주문 상태·파일 목록·회차·수정요청 대상 번호를 계산(장별 상태 만들지 말 것). 1개면 바로 상세.
- **Phase 3 — 핸드오프 상세(표면 B)**: 모바일 cohort에서 모바일 협업 뷰(데스크톱 `workbench_detail_body`는 분기로 보존). 뷰어·도면 페이저·대화 스레드·역할/주문상태 액션 바. 전달/수정/확정은 기존 모달·엔드포인트 재사용.
  - 신규 JS를 기존 `workbench_detail_body.html`의 긴 inline `<script>`에 계속 붙이지 말 것. `static/js/foms/drawing-handoff.js` 같은 별도 파일로 분리하고, 필요한 데이터는 `<script type="application/json">` 또는 `data-*`로 넘긴다.
  - 신규 CSS는 `static/css/components/foms-drawing-mobile.css` 또는 새 컴포넌트 CSS에 둔다. 기존 inline `<style>`을 만지는 경우, touched rule은 가능한 한 컴포넌트 CSS로 이동한다.

**검증(각 Phase 공통):**
1. `python -c "import app; print('APP_OK')"` → `APP_OK`
2. (해당 시) Jinja 컴파일·`node --check <변경 js>`
3. `python -m pytest tests/domains/test_drawing_workbench_mobile.py tests/visual/test_p1_mockup_structure.py tests/visual/test_p1_mockup_png_gate.py -q` → 전부 pass.
   - `mobile-drawing-handoff.html`은 신규 목업이므로 기존 visual 계약이 이 파일을 아직 모르면, `test_p1_mockup_structure.py`/`test_p1_mockup_png_gate.py`에 도면 핸드오프 A/B/C selector 계약을 추가한다.
   - `tests/domains/test_drawing_workbench_mobile.py`에 detail route 계약을 추가한다: multi-file+no `drawing_key` → 목록(C), valid `drawing_key` → 상세(B), invalid `drawing_key` → user-visible 안내, `event_id`/`target_no` deep-link → 상세(B) 우선, non-cohort/desktop → 기존 상세 유지.
4. **UI/CSS/템플릿 변경 → 비주얼**: win32 `python -m pytest tests/visual --update-snapshots -q` → 변경 PNG 눈으로 확인 후 커밋 → push 직전 `scripts/ops/pre_push_smoke.ps1 -Visual` exit 0.
5. 실기기/모바일 폭에서 **도면팀·영업 두 역할 + 1장/다중장 + 각 상태(전달/수정요청/확정)** 시나리오 수동 확인.
6. gstack browse 또는 Cursor browser MCP로 360×780, 390×844, 430×932, 768, 1280 폭 스모크를 남긴다(로컬 setup 전이면 미도입으로 보고 수동 브라우저 근거를 남긴다). 실제 앱 DOM/스크린샷에는 `preview-label`, `role-note`, 고정 390px 프레임이 없어야 한다. non-cohort/desktop에서는 신규 표면·하단 액션 바가 보이지 않아야 한다.

---

## 7. 하지 말 것 (안티패턴)

- 데스크톱 실행판(`workbench_detail_body.html`의 ≥992px 표현)을 모바일 위해 깨뜨리기.
- blueprint 이름/`url_prefix`/등록 순서 변경(Wave 2 freeze).
- 새 DB 컬럼·새 엔드포인트·새 권한 로직 추가(기존 재사용).
- **장별 상태/장별 확정/장별 차수(v1·v2) 만들기** — 상태는 주문 1개다(v1 범위 밖). 목록은 골라보기 용도일 뿐.
- 인라인 스타일/`JSON.parse('{{ ... }}')`(→ `data-*` + 안전 파서).
- 목업 HTML/CSS/SVG를 제품 코드에 그대로 복붙하기. 목업의 프레임·검토 라벨·문자 아이콘은 구현 산출물이 아니다.
- cohort 게이트 우회로 데스크톱/비대상에 모바일 표면 노출.
- 에러 무시(`try/except: pass`, 빈 catch), 로그 없는 실패.

---

## 8. 산출물(예상 변경 파일)

- `templates/drawing/partials/workbench_dashboard_body.html` (모바일 큐 카드)
- `templates/drawing/partials/` 신규/수정 (장 목록·핸드오프 상세 partial — 모바일 cohort 한정)
- `static/css/components/foms-drawing-mobile.css`, `foms-drawing-mobile-card.css` (+ 캐시버스트)
- 필요 시 모바일 협업 JS 1개(예: `static/js/foms/drawing-handoff.js`) — 도면 전환/스레드/액션 위임
- `foms/web/drawing/workbench.py`(+서비스) — 주문 단위 view-model 파생값(상태/회차/수정요청 대상 번호 — **데이터만**, 권한/저장 로직 불변)
- 대응 테스트 추가/갱신

**완료 정의**: 목업 A/B/C와 시각·흐름이 일치 + **상태는 주문 단위** + 데스크톱 무영향 + 기존 전달/수정/확정 동작 그대로 + 위 검증 전부 통과.

---

## 9. 디자인 리뷰 잠금(`/plan-design-review`)

**초기 디자인 완성도:** 7.1/10. 흐름·정보 위계는 좋지만, 목업 전용 표현과 실제 제품 UI의 경계가 약해 구현자가 복붙/장별 상태/고정 폭을 만들 위험이 있었다.

**수정 후:** 8.8/10. 남은 리스크는 실제 구현 후 브라우저 시각 QA 영역이다.

**What already exists — 재사용할 것**
- `_tokens.css`의 FOMS 색/타입/간격/터치타깃 토큰.
- 기존 모바일 v2 셸, `erp-drawing-mobile-card`, `drawing_mobile_controls.html`, `GlobalImageViewer`/lightbox, 기존 `can_*` 권한 플래그.
- 기존 도면 전달/수정/확정 모달과 API. 디자인은 표현을 바꿀 뿐 실행 계약은 바꾸지 않는다.

**NOT in scope**
- 새 디자인 시스템/DESIGN.md 작성.
- 새 도면 상태 모델, 장별 확정, 장별 진행률.
- 새 아이콘 라이브러리 도입. 이미 설치된 아이콘 체계만 사용한다.
- 새 gstack 디자인 변형 생성. 이 작업의 기준 시안은 `mobile-drawing-handoff.html`이다.

**디자인 구현 태스크**
- [ ] **T1 (P1, human: ~1h / CC: ~10min)** — detail/list UI — 목업 전용 요소(`preview-label`, `role-note`, 390px frame, raw glyph icons)를 실제 템플릿에 넣지 않는다.
- [ ] **T2 (P1, human: ~1h / CC: ~10min)** — drawing file list — `수정 반영`/`수정요청 대상` 칩을 이력 안내로만 렌더하고 장별 상태/진행률로 확장하지 않는다.
- [ ] **T3 (P1, human: ~1h / CC: ~10min)** — viewer chrome — 앱 차원의 도면팀/생산팀 체크 UI를 만들지 않고, 업로드 이미지 안 문구와 FOMS 상태 UI를 분리한다.
- [ ] **T4 (P2, human: ~1h / CC: ~10min)** — responsive QA — 360/390/430/768/1280 폭에서 텍스트 겹침, 하단 액션 바, 터치타깃, non-cohort 노출 여부를 캡처로 확인한다.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR | 주문 단위 v1 유지, 기존 API 재사용, Phase 0 감사 보강 |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | - | not run |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 4 issues found, 0 critical gaps, prompt patched |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR | score 7.1/10 -> 8.8/10, 5 design decisions, 0 unresolved |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | - | not needed |

- **ENG:** deep-link precedence, invalid `drawing_key`, transfer-vs-revision upload endpoints, separate JS/CSS, detail route tests added to the implementation contract.
- **DESIGN:** mockup-vs-production boundary, raw icon ban, no per-sheet status, responsive smoke widths, viewer chrome state separation added.
- **UNRESOLVED:** 0
- **VERDICT:** CEO + ENG + DESIGN CLEARED. Ready for implementation; run live `/design-review` after code lands.
