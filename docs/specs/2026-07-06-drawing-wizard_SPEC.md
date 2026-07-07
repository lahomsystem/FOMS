# 도면 작업실 "도면 마법사" (Drawing Wizard) Spec
> 작성일: 2026-07-06 | 상태: ✅ 완료 (P1/P2/P3 구현·검증·QA 종료 — 2026-07-06) | 작성: Claude (Advisor)
> 구현 노트: '기타' 값 셀은 샘플 대조 결과 검정(스펙 §6의 빨강 표기에서 정정). asset 이미지는 `asset-raw` same-origin 프록시로 로드(운영 R2 redirect의 html2canvas 오염 방지 — §9 리스크의 실측 해법).

## 0. 배경 — 레거시 워크플로우 대체

현행(포토샵 수작업):
1. 스케치업으로 도면 제작 → 캡처
2. 포토샵에서 고정 양식(PSD)을 열어 고객정보·제품정보·발주사 로고·도면 제작자를 일일이 타이핑
3. 캡처 이미지를 빈 공간에 붙여넣고 치수 텍스트를 수동 입력
4. PNG로 내보내 도면 작업실에서 "도면 전달"

신규(도면 마법사):
1. 도면 작업실 상세 → **[도면 마법사]** 버튼 → 전용 에디터 페이지
2. 주문 데이터 기반 **자동 채움** (고객정보/제품정보/로고/제작자)
3. 스케치업 캡처를 **Ctrl+V 붙여넣기** → 드래그 이동·리사이즈
4. 자유 텍스트 박스 (추가/수정/이동/색상/크기) — 치수·컷리스트 입력
5. PNG 내보내기(다운로드) 또는 **원클릭 도면 전달**(기존 transfer-drawing SSOT 재사용)
6. 편집 상태는 주문에 저장 → **언제든 다시 열어 재편집** (포토샵 대비 핵심 우위)

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
- `/erp/drawing-workbench/<order_id>/wizard` 독립 전체 페이지(데스크톱 전용 에디터).
- 스테이지(도면 시트)는 **기존 PSD 양식과 시각적으로 동일한 HTML/CSS 복제본** (§6 지오메트리).
- 상단: 도면팀/생산팀 체크리스트 헤더(체크박스 클릭 토글) + 우상단 페이지 박스.
- 중앙: 자유 배치 영역 (텍스트 박스 + 붙여넣은 이미지).
- 하단: 고객/제품 정보 표 (셀 값 인라인 편집 가능, 자동 채움 지원) + 발주사 로고 + DREW 서명.

### 1.2 기능 요구사항
1. **자동 채움**: 페이지 최초 로드(저장 상태 없을 때) 시 서버 계산 defaults로 폼 셀 채움. "자동 채움" 버튼으로 언제든 재적용(확인 후 덮어씀).
2. **이미지 붙여넣기**: 문서 레벨 paste 이벤트 → 클립보드 이미지 blob → 에셋 업로드 API → 스테이지 중앙 배치. 파일 선택 버튼도 제공(같은 경로). 드래그 이동, 코너 핸들 리사이즈(기본 비율 고정, Shift=자유), Delete 삭제.
3. **텍스트 박스**: 툴바 [텍스트] 버튼 또는 스테이지 더블클릭 → 생성. 더블클릭 인라인 편집(contenteditable, 멀티라인). 드래그 이동. 속성: 크기(14/17/20/24/28px), 색(#000/#e03131/#1c62d6), 굵기, 정렬(좌/중). 컷리스트 프리셋 버튼([SR]/[EP]/[DOOR]/[옷봉] 제목 블록 원클릭 생성).
4. **폼 셀 편집**: 하단 표의 값 셀·페이지 박스·DREW는 클릭하여 직접 수정(입력 필드). 레이아웃(라벨·칸 구조)은 고정.
5. **로고**: manager_name 규칙 자동 선택(하우드→`haud-logo.png`, 라홈→`lahom-logo.png`, 그 외 없음) + 로고 셀 클릭 시 [하우드/라홈/없음] 선택.
6. **저장/불러오기**: 시트 상태 JSON을 `structured_data['drawing_wizard']`에 저장(PUT). 재진입 시 그대로 복원. 다중 시트(최대 10장, 탭 전환/추가/이름변경/삭제).
7. **내보내기**: html2canvas(scale=2)로 PNG 생성 → (a) 다운로드 `도면_<고객명>_<주문ID>_<시트명>.png`, (b) **도면 전달**: 기존 `/drawing-gateway-upload` 업로드 → 기존 `/transfer-drawing` 호출(메모 입력, APPEND/전체교체 선택). 권한·알림·히스토리는 기존 API가 SSOT. **전달 대상은 현재 시트 1장** (여러 장은 반복 전달, v1 단순화). 내보내기 직전 줌을 1.0으로 리셋 후 캡처, 완료 후 복원(transform 왜곡 방지).
8. **Undo/Redo**: 스냅샷 스택(50), Ctrl+Z/Ctrl+Y. 화살표 키 1px(Shift 10px) 이동.
9. **줌**: 화면 폭 맞춤 기본, 50–150% 컨트롤(내보내기 품질과 무관 — 스테이지 논리 좌표 고정).
10. **미저장 이탈 가드**: dirty 상태 beforeunload 경고 + 저장 버튼 dirty 표시.
11. **읽기 전용 모드**: `can_save=false`(비참여자) → 편집 툴바 비활성 + 상단 안내 배너("열람 전용 — 도면 담당자만 편집 가능"). 열람은 허용.
12. **선택 객체 플로팅 미니 툴바**: 텍스트 선택 시 [크기▾/색 3버튼/B/정렬/삭제], 이미지 선택 시 [비율고정 토글/삭제]. 별도 사이드 패널 없음.

### 1.3 예외/제약 조건
- **데스크톱 전용** (스케치업 워크플로우 자체가 데스크톱). 모바일 접근 시 안내 문구 + 목록 복귀 링크. 모바일 v2 핸드오프 UI에는 진입점을 추가하지 않는다.
- 저장 권한: `is_drawing_workbench_participant(user, order)` 또는 ADMIN. 열람(GET)은 login_required(작업실 상세와 동일).
- 상태 JSON 서버측 캡: 직렬화 64KB 초과 시 400 (이미지 base64 인라인 금지 — 반드시 에셋 key 참조).
- 에셋 업로드: 이미지 확장자만(png/jpg/jpeg/webp/gif), 10MB 캡, 경로 `orders/<id>/drawing_wizard/assets/`. **OrderAttachment 행 생성 안 함** (도면창구 업로드 선례와 동일: R2-only, 상태 JSON이 참조). 삭제 GC는 v1 범위 밖(부채로 기록).
- 낙관적 충돌: PUT에 `base_updated_at` 포함, 서버 저장본과 불일치 시 409 → 클라이언트 "다시 불러오기/덮어쓰기" 선택. (ERP 탭복귀 clobber 사건 교훈.)
- `structured_data` 수정은 반드시 `copy.deepcopy` + `flag_modified` 패턴.
- 기존 도면 전달/수정요청/워크벤치 UI·API **무변경** (버튼 1개 추가 제외).
- 신규 첨부 category 추가 금지(4종 whitelist 유지).
- 텍스트는 항상 plain text: contenteditable paste 시 `text/plain`만 삽입, 렌더는 `textContent` 주입(HTML 삽입 금지 — XSS 차단).
- 상태 검증에서 image key가 `data:`로 시작하면 400 (base64 인라인 차단 이중 방어).
- v1 범위 밖(명시 defer): 기존 전달본 이미지를 위저드로 불러와 주석, 치수선(선+화살표) 도구, PDF 내보내기, 모바일 편집, 에셋 GC, 시트별 품목 선택 자동채움(items[0] 고정).

## 2. How — 어떻게 만드는가

### 2.1 수정/신규 파일
| 파일 | 변경 |
|------|------|
| `foms/web/drawing/wizard.py` (신규) | 페이지 라우트 `GET /erp/drawing-workbench/<int:order_id>/wizard`. 기존 `erp_drawing_workbench_bp`에 라우트 추가(모듈 분리). 주문 로드→404 가드→`templates/drawing/wizard.html` 렌더. 컨텍스트: order_id, 고객명, can_save, config JSON용 최소 데이터 |
| `foms/web/drawing/__init__.py` | 기존 workbench import **다음 줄에** `from foms.web.drawing import wizard  # noqa: F401` 추가(라우트 attach side-effect; wizard.py는 workbench에서 bp import — 순환 없음). 기존 `__all__` 불변 |
| `foms/api/drawing/wizard.py` (신규) | `erp_orders_drawing_wizard_bp` (url_prefix `/api/orders`): GET/PUT `/<id>/drawing-wizard`, POST `/<id>/drawing-wizard/asset` |
| `foms/api/drawing/__init__.py` | 신규 bp export |
| `foms/platform/blueprints.py` | 신규 bp import+register (기존 drawing 계열 블록 옆) |
| `foms/services/drawing_wizard_defaults.py` (신규) | `build_wizard_defaults(order, sd, current_user) -> dict` 순수 함수 (§4 매핑) |
| `templates/drawing/wizard.html` (신규) | 독립 페이지(shared/layout 미사용). 스테이지 양식 마크업 + 툴바 + config `<script type="application/json">` + CSS/JS 링크(defer) |
| `templates/drawing/partials/workbench_detail_body.html` | 헤더 액션에 `[도면 마법사]` 버튼 1개(`target="_blank"`) 추가 (다른 변경 금지) |
| `static/js/drawing/wizard.js` (신규) | 에디터 전체(IIFE, 전역 오염 금지, `defer`) |
| `static/css/contexts/drawing/wizard.css` (신규) | 에디터 + 양식 지오메트리 CSS |
| `tests/domains/test_drawing_wizard_api.py` (신규) | API 계약 테스트 |
| `tests/domains/test_drawing_wizard_page.py` (신규) | 페이지/템플릿 계약 테스트 |
| `tests/domains/test_drawing_wizard_defaults.py` (신규) | defaults 매핑 단위 테스트 |

### 2.2 아키텍처 방향 (기존 패턴 준수)
- **스테이지 = DOM 에디터** (absolute-positioned div/img) + **html2canvas 내보내기**. html2canvas는 `static/js/measurement/image-export.js`의 `ensureHtml2canvas()` lazy-load 패턴 복제(클릭 시 1회 CDN 로드 — perf guard G2 합치, 기존 승인 선례).
- 스테이지 논리 크기 **1478×1040px 고정** (A4 landscape 비율 1.421≈1.414), CSS `transform: scale()` 줌. 내보내기는 scale=2 (2956×2080).
- 설정 전달: `<script type="application/json" id="drawing-wizard-config">` + `JSON.parse(textContent)` (workbench_detail_body.html:1214 패턴 동일). `JSON.parse('{{ x|tojson }}')` 금지 준수.
- 업로드: 에셋은 전용 multipart 엔드포인트(서버 경유 — 클립보드 blob 단건, 단순 우선). 내보내기 PNG 전달은 **기존** `/api/orders/<id>/drawing-gateway-upload` → `/api/orders/<id>/transfer-drawing` 재사용(신규 백엔드 0).
- JSONB 저장: deepcopy+flag_modified, 키 `drawing_wizard` 단일 소유(다른 키 불변 유지).
- API 응답 `{'success': ..., 'data'/'message'}` 통일.
- 페이지는 ERP shell fragment가 아님(새 탭 독립 문서) → G4 idempotency 비해당. `<script defer>` (G1).

### 2.3 의존성 및 영향 범위
- DB 마이그레이션 **불필요** (JSONB 키 추가만).
- 기존 도면 대시보드/상세 read-model: `drawing_wizard` 키를 읽지 않음 → 영향 없음. structured_data 행 크기 +최대 64KB — 대시보드 hydrate가 행 전체를 읽으므로 캡을 반드시 서버에서 강제.
- 알림/권한/히스토리: transfer-drawing 재사용으로 변경 없음.
- 캐시: 페이지 저장은 대시보드 슬라이스에 영향 없는 필드지만, transfer는 기존 API가 스스로 무효화.

## 3. Steps — 실행 단계 (순차)
- [ ] **P1 백엔드**: defaults 서비스 + API 3종 + 페이지 라우트 + 빈 템플릿 골격 + 테스트 (Worker A)
- [ ] **P2 프론트**: wizard.html 양식 마크업 + wizard.css 지오메트리 + wizard.js 에디터 전부 (Worker B)
- [ ] **P3 통합**: workbench 버튼, 전달 통합 E2E, 계약 테스트 마감, 문서 (Worker C 또는 B 연장)
- [ ] Advisor 1:1 diff 리뷰 + gstack browse QA + full inspection

## 4. 자동 채움 매핑 (defaults — 서버 계산 SSOT)
| 폼 키 | 소스 | 비고 |
|-------|------|------|
| `construction_date` | `sd.schedule.construction.date` → `_normalize_date_to_yyyymmdd` per 콤마 항목 → `M월 D일` 조인, 폴백 `order.erp_construction_date` | 워크벤치 `_resolve_construction_date_display` 규칙 재사용 후 한글 포맷 |
| `customer_name` | `sd.parties.customer.name` | |
| `phone` | `sd.parties.customer.phone` → `format_phone_filter` | |
| `address` | `sd.site.address_full` 폴백 `address_main` | |
| `product_name` | `items[*].product_name` 비어있지 않은 것 " / " 조인 | items = `sd.items`/`products`/`product_items` (build_product_items_for_order 규칙) |
| `color` | `items[0].color` | 기본값 '상담'이면 빈칸 |
| `site_spec` | `items[0]`: `width×depth×height` (셋 다 있으면), 아니면 `spec` 원문 | width 등은 `spec_width` 폴백 규칙 동일 |
| `spec_w300` | `item_spec_w300_display(items[0])` (`foms/services/erp_template_filters.py`) | 시공자수. spec_rows 합산 SSOT 재사용 |
| `handle` | `items[0].handle` ('상담'→빈칸) | |
| `drawer` | `items[0].internal` ('상담'→빈칸) | 양식 라벨 '서랍' |
| `misc` | `items[0].misc` ('상담'→빈칸), 비면 `items[0].option_detail` 폴백 | |
| `sales_manager` | `sd.parties.manager.name` 폴백 `order.manager_name` | |
| `manager_phone` | `sd.parties.manager.phone` 없으면 `-` | |
| `logo` | manager_name에 '하우드'→`haud`, '라홈'→`lahom`, 그 외 `none` | transfer-drawing 알림 라우팅 규칙과 동일 문자열 규칙 |
| `drew` | `current_user.name` | 편집 가능 |
| `page_no` | `-` | 우상단 박스 |
| `checks` | 전부 false | 헤더 체크박스 8개 |

('상담' = ERP 폼 기본 placeholder 값 — defaults에서 제외해 빈칸 유지.)

## 5. 상태 스키마 (`structured_data['drawing_wizard']`)
```json
{
  "v": 1,
  "updated_at": "2026-07-06 12:00:00",
  "updated_by": 123,
  "updated_by_name": "홍길동",
  "sheets": [
    {
      "id": "s-a1b2c3",
      "name": "도면 1",
      "form": { "construction_date": "7월 9일", "customer_name": "서으뜸", "phone": "9263-9140",
        "address": "대구 희망로 24길 24, 수성 효성해링턴 101-1101", "product_name": "여단이 붙박이장",
        "color": "클린화이트", "site_spec": "3500×620×2300", "spec_w300": "11.7",
        "handle": "피닉스바 아이보리", "drawer": "657*6", "misc": "멀티탭 고객 준비",
        "sales_manager": "김성일 실장", "manager_phone": "-", "logo": "haud",
        "drew": "CHOI SANGYONG", "page_no": "-",
        "checks": {"d_site": false, "d_double": false, "d_order": false,
                    "p_prod": false, "p_glass": false, "p_light": false, "p_handle": false, "p_etc": false} },
      "objects": [
        {"id": "o-1", "type": "text", "x": 340, "y": 95, "w": 220, "text": "[SR]\n60*2440 =2",
         "size": 20, "color": "#000000", "bold": false, "align": "left"},
        {"id": "o-2", "type": "image", "x": 90, "y": 420, "w": 620, "h": 360,
         "key": "orders/4213/drawing_wizard/assets/xxx.png", "natural_w": 1240, "natural_h": 720}
      ]
    }
  ]
}
```
- 서버 검증: `v==1`, sheets ≤ 10, objects/sheet ≤ 200, 직렬화 ≤ 64KB, image key는 `orders/<order_id>/drawing_wizard/` 접두사 필수(타 주문 참조 차단), text ≤ 2000자.
- 색상은 3종 팔레트 외 값 거부(서버는 형식 `#rrggbb`만 검증 — 팔레트는 UI 제약).

## 6. 양식 지오메트리 (샘플 4213 도면 실측 — 스테이지 1478×1040 기준)
> Worker는 샘플 이미지를 볼 수 없음. 아래 수치가 구현 기준. 최종 시각 검수는 Advisor가 샘플과 대조.

- **시트**: 1478×1040 흰 배경. 폰트 스택 `"Malgun Gothic","맑은 고딕",sans-serif`.
- **헤더 박스(좌상)**: (10,8)–(1240,64), 검정 2px 테두리. 두 줄, 좌패딩 10px, 굵게 20px, 줄간 균등:
  - `도면팀 : ☐현장확인 ☐더블체크 ☐발주확인`
  - `생산팀 : ☐생산확인 ☐유리,거울 ☐조명 ☐손잡이 ☐부자재`
  - 체크박스는 클릭 토글(☐/☑ — 14px 정사각 테두리 + 체크표시로 렌더).
- **페이지 박스(우상)**: (1346,8)–(1468,64) (우측 가장자리 = 표 우측선 정렬), 검정 2px 테두리, 중앙 굵게 28px, 기본 `-`.
- **자유 영역**: y 70–800 (전면 자유 배치 허용; 텍스트/이미지 z-order는 텍스트 상위).
- **하단 표**: (10,808)–(1468,978), **빨강(#e03131) 5px 외곽**, 내부 검정 1px 그리드. 4행 구조:
  - 행 높이: A 36px, B 36px, C 44px, D 44px (합 160 = 표 내부 높이; 빨강 5px 테두리 제외).
  - **A/B행 9컬럼 폭(px, 합 1458 = 표 내부 폭)**: 118, 150, 152, 96, 252, 112, 292, 110, 176
    (x 경계: 10, 128, 278, 430, 526, 778, 890, 1182, 1292, 1468)
    - A행: `시공일자 | 고객명 | 연락처 | 제품명 | {product_name} | 현장규격 | {site_spec} | 영 업 담 당 | {sales_manager}`
    - B행: `{construction_date} | {customer_name} | {phone} | 색 상 | {color}(빨강) | 시공자수 | {spec_w300} | 담당연락처 | {manager_phone}`
    - 라벨 셀 = 연회색 배경 없음(흰 배경, 검정 텍스트, 중앙 정렬, 15px 굵게), 값 셀 = 중앙 정렬 15px.
  - **C/D행 7셀(폭 합 1458)**: `주 소`(54, 2행 span) | 주소값(366, 2행 span, 좌정렬 최대 2줄) | C: `손잡이`(96)/D: `서 랍`(96) | C: {handle}(빨강)/D: {drawer}(빨강) (252) | `기타`(112, 2행 span) | {misc}(292, 2행 span) | 로고 셀(286, 2행 span, 이미지 contain 중앙, 내부 빨강 2px 테두리 박스)
  - C/D 열 x 경계는 A/B와 수직 정렬: 10, 64(주소 라벨), 430, 526, 778, 890, 1182, 1468 — 제품명/현장규격 열 경계와 일치.
- **DREW 라인**: 표 아래 우측 정렬, (…–1468, 982–1008), `DREW : {drew}` 굵게 18px.
- 값 강조색: color/handle/drawer/misc 값 셀은 빨강(#c92a2a 계열) — 샘플 관행. (셀 단위 고정 스타일, 사용자 변경 불가 — 단순화.)
- **내보내기 검증**: PNG 산출물에서 표·헤더 위치가 스테이지와 1:1 (html2canvas 클론 대상 = 스테이지 노드 단독).

## 7. API 계약
1. `GET /api/orders/<id>/drawing-wizard` (login_required)
   → `{success, data: {state: <저장본|null>, defaults: {...}, can_save: bool, customer_name, order_id}}`
2. `PUT /api/orders/<id>/drawing-wizard` (participant/ADMIN)
   body `{state: {...}, base_updated_at: "..."|null}`
   → 검증(§5) → 409(충돌: `{success:false, error:'conflict', server_updated_at, server_updated_by_name}`) | 200 `{success, data:{updated_at}}`
3. `POST /api/orders/<id>/drawing-wizard/asset` (participant/ADMIN, multipart `file`)
   → 이미지 검증 → `storage.upload_file(file, filename, f"orders/{id}/drawing_wizard/assets")` → `{success, data:{key, view_url, natural_w?, natural_h?}}` (natural 치수는 클라이언트가 Image 로드로 획득해도 됨 — 서버 생략 가능)
4. 전달: 기존 API 재사용(신규 없음).

## 8. 검증 기준 (완료 정의)
- [ ] `python -c "import app; print('APP_OK')"`
- [ ] 신규 pytest 3파일 전부 green + `pytest tests/domains/test_drawing_workbench_*` 회귀 green
- [ ] `pytest tests/contracts/runtime/foms_namespace_surface_tests.py` green (신규 웹/API 모듈이 namespace 계약 위반하지 않음)
- [ ] 페이지 200 OK + config JSON 파싱 계약
- [ ] PUT 권한(비참여자 403), 캡(65KB 400), 충돌(409), 타 주문 key 거부(400) 테스트
- [ ] perf guard: `pytest tests/performance/test_perf_regression_guard.py` green (defer/G2)
- [ ] gstack browse QA: 로그인→위저드 열기→자동채움 확인→텍스트 추가→저장→재로드 복원→(로컬 한계 내) 내보내기 경로 스모크
- [ ] 스테이지 렌더 스크린샷 vs 샘플 도면 시각 대조 (Advisor)
- [ ] AI_STATUS/AI_CHANGELOG 갱신

## 9. 리스크 및 완화
| 리스크 | 완화 |
|--------|------|
| html2canvas 렌더 편차(폰트/보더) | 스테이지 CSS를 명시값만 사용(상속 최소화), 내보내기 후 시각 검수. CDN 실패 시 에러 토스트+재시도 |
| structured_data 비대화 | 64KB 서버 캡 + 이미지 key 참조 강제 |
| 동시 편집 유실 | base_updated_at 409 + 클라 선택 UI |
| 에셋 고아 객체 | v1 GC 없음(문서화된 부채). 경로 격리로 후속 배치 정리 용이 |
| 전역 CSS 간섭 | 독립 페이지(레이아웃 미상속) + `dws-` 접두 클래스 명시 스타일 |
| 붙여넣기 브라우저 호환 | Chrome/Edge 기준(사내 표준). paste 미지원 시 파일 버튼 폴백 상존 |

## 10. 참고
- 업로드 선례: `foms/api/drawing/erp_orders_drawing.py` (gateway upload/complete — OrderAttachment 미생성 R2-only 선례)
- html2canvas lazy 패턴: `static/js/measurement/image-export.js:6-35`
- config JSON 패턴: `templates/drawing/partials/workbench_detail_body.html:1214-1218`
- 자수 SSOT: `foms/services/erp_template_filters.py` `item_spec_w300_display`
- 로고 자산: `static/images/haud-logo.png`, `static/images/lahom-logo.png`
