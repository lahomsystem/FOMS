# 도면 마법사 v2 — 양식 충실도 + Konva 주석 엔진 + Apple 스타일 UX Spec
> **3라운드 갱신(dff10365)**: §2 지오메트리는 v3 실측치로 대체됨 — 외곽 (40,40)-(1440,1000) 3px, 페이지 박스 (1374,40)-(1440,89) 외곽 밀착, 표=외곽 3변 공유+상단선 y899, 열 40|123|211|310|399|728|820|1227|1330|1440(C/D 주소라벨 89), 행 899/924/949/974/1000, 헤더 (48,43)·행간 26, DREW 18px. 로고 규칙: '라홈'→lahom, 그 외 전부→haud('없음' 폐지). 빈곳 더블클릭 텍스트 생성 제거(세그 버튼+Ctrl+클릭만). 로고 팝업 race는 450ms 억제 창으로 수정.
> 작성일: 2026-07-06 | 상태: ✅ 완료 (D/E/F 구현·검증·통합 QA 종료 — 2026-07-06) | 작성: Claude (Advisor)
> 구현 노트: Konva 9.3.22 vendored(171KB). 앱바는 grid `minmax(0,1fr) auto minmax(max-content,1fr)`(우측 겹침 구조적 차단, 1500px↓ 세그 아이콘-only). 도형 그리기 mouseup은 window 캡처 리스너(캔버스 밖 release 엣지 해결). rect/ellipse는 hit용 극미세 fill(rgba 0,0,0,0.001)+hitStrokeWidth 12. 내보내기 = html2canvas(폼)+Konva toCanvas(pixelRatio 2) 오프스크린 합성 — 실물 PNG 검증 완료.
> v1: `2026-07-06-drawing-wizard_SPEC.md`. 이번 라운드 정답 기준 = **김유성/KIM HANBI 샘플** (A4 300dpi 3508×2480).

## 0. 사용자 피드백 → 작업 매핑
| # | 피드백 | 해법 |
|---|--------|------|
| 1 | 바깥 테두리 없음, 선 색/두께 불일치 | §2 지오메트리 v2 (시트 외곽 검정 테두리, 표 검정 그리드) |
| 2 | 폰트 불일치 | §2.5 폰트 스택/크기/자간 재정의 |
| 3 | 에디터 UX/UI 애플 스타일 | §4 Apple HIG 크롬 리디자인 |
| 4 | Ctrl+클릭 → 그 자리 텍스트 | §3 Konva 상호작용 |
| 5 | 도형(네모/원/화살표) + 텍스트 입력·이동 개선 → 전문 라이브러리 | §3 **Konva.js** 주석 엔진 교체 |
| 6 | 로고 바깥 테두리 제거 | §2.4 |

## 1. 파일 범위
| 파일 | 변경 |
|------|------|
| `static/vendor/konva.min.js` (신규) | Konva 9.x vendored (unpkg에서 1회 다운로드, 버전 주석 명기) |
| `static/js/drawing/wizard.js` | 자유 객체 레이어를 Konva Stage로 전면 교체 (§3). 폼 셀/저장/전달/시트 로직은 유지 |
| `static/css/contexts/drawing/wizard.css` | §2 양식 지오메트리 v2 + §4 Apple 크롬 |
| `templates/drawing/wizard.html` | 양식 마크업 v2(외곽 테두리·헤더), 툴바 v2(도형 메뉴·세그먼트), konva script 태그(defer, 로컬) |
| `foms/api/drawing/wizard.py` | PUT validator 확장: 신규 객체 타입 rect/ellipse/arrow/line + rotation/stroke 필드 (§3.4) |
| `tests/domains/test_drawing_wizard_api.py` | 신규 타입 검증 테스트 추가 |

**불변**: 저장 키(`drawing_wizard`)·낙관잠금·64KB 캡·asset-raw 프록시·전달 플로우·defaults.

## 2. 양식 지오메트리 v2 (스테이지 1478×1040 — 새 샘플 정규화)
- **시트 외곽 테두리**: (40,38)–(1436,997), **검정 3px**. 이 안이 콘텐츠 영역.
- **헤더**: 별도 박스 없음(외곽 테두리 안 좌상단에 텍스트만). 시작 (52,50), 두 줄, 줄높이 30px:
  - `도면팀 : ☐현장확인 ☐더블체크 ☐발주확인`
  - `생산팀 : ☐생산확인 ☐유리,거울 ☐조명 ☐손잡이 ☐부자재`
  - 22px bold, letter-spacing 1.5px, 체크박스 17px(검정 1.5px 테두리, 체크 시 ✓).
- **페이지 박스(우상)**: (1368,44)–(1434,92), 검정 3px 테두리, `-` 30px bold 중앙.
- **하단 표**: (40,897)–(1436,997). **외곽 검정 2.5px, 내부 그리드 검정 1px** (빨강 프레임 폐지).
  - 행: A 897–922, B 922–947, C 947–972, D 972–997 (각 25px).
  - A/B 열 x 경계: 40 | 118 | 207 | 310 | 400 | 724 | 820 | 1226 | 1330 | 1436
    - A: `시공일자 | 고객명 | 연락처 | 제품명 | {product} | 현장규격 | {spec} | 영 업 담 당 | {sales}`
    - B: `{date} | {customer} | {phone} | 색 상 | {color}(빨강) | 시공자수 | {w300} | 담당연락처 | {mphone}`
  - C/D 열 x 경계: 40 | 92 | 310 | 400 | 724 | 820 | 1226 | 1436
    - `주 소`(2행) | 주소값(2행) | C:`손잡이`/D:`서 랍` | C:{handle}(빨강)/D:{drawer}(빨강) | `기타`(2행) | {misc}(2행, 검정) | 로고(2행)
  - 셀 폰트 13px, 라벨 bold. 값 강조색 유지(색상/손잡이/서랍 = #c92a2a).
- **로고 셀**: 테두리 **없음** — 이미지 contain 중앙만 (`.dws-logo-box` border 제거).
- **DREW**: 외곽 테두리 아래 우측 정렬, (…–1436, 1002–1030), `DREW : {drew}` 16px bold.
- **자유 주석 영역**: 외곽 테두리 안 전체(헤더~표 위가 주 사용처, 제한은 두지 않음).

### 2.5 폰트
- 스테이지 전역: `"Malgun Gothic","맑은 고딕","Dotum","돋움",sans-serif`.
- 헤더만 자간 1.5px로 샘플의 각진 인상 재현. 최종 크기/자간은 Advisor가 샘플 PNG 오버레이 대조로 캘리브레이션(±10% 조정 허용).

## 3. Konva 주석 엔진 (자유 객체 레이어 교체)
### 3.1 구조
- `#dws-objects` div 제거 → `#dws-anno`(absolute inset 0) 안에 `Konva.Stage(1478×1040)` + 단일 Layer + `Konva.Transformer`.
- **폼 이벤트 투과**: Stage 빈 영역 mousedown 시 — shape 미적중이고 그리기 모드 아니면 `container.style.pointerEvents='none'` → `document.elementFromPoint`로 아래 폼 요소 focus/click 재전달 → 복원. (폼 셀 편집 공존의 핵심.)
- 줌: 기존 CSS scale 유지(스테이지 wrapper 통째) — Konva는 논리 좌표 고정, 포인터 좌표만 zoom 역보정.

### 3.2 객체 타입 (Konva 노드 매핑)
| state type | Konva | 속성 |
|------------|-------|------|
| text | Konva.Text | x,y,w(width),text,size(fontSize),color(fill),bold(fontStyle),align,rotation |
| image | Konva.Image | x,y,w,h,key(src=asset-raw 프록시),rotation |
| rect | Konva.Rect | x,y,w,h,stroke,strokeWidth(1/2/3),rotation, fill 없음(투명) |
| ellipse | Konva.Ellipse | x,y(중심 아님—좌상단 기준으로 통일 변환),w,h,stroke,strokeWidth,rotation |
| arrow | Konva.Arrow | points[x1,y1,x2,y2],stroke,strokeWidth,pointerLength/Width 고정 |
| line | Konva.Line | points,stroke,strokeWidth |
- 기존 v1 저장 상태(text/image) 무손실 로드(속성 기본값 보충). 스키마 버전 v:1 유지(additive).

### 3.3 상호작용 (전문가급 — 피드백 5 해결)
- 클릭 선택 → Transformer(모서리+회전 핸들). 드래그 이동. Shift 다중선택은 v2 범위 밖.
- **텍스트 더블클릭 → textarea 오버레이 인라인 편집** (Konva 표준 패턴: 노드 절대좌표×zoom 위치, blur/Esc 커밋, 빈 텍스트=삭제). 편집 중 Transformer 숨김.
- **Ctrl+클릭(빈 곳) → 해당 좌표 텍스트 생성+즉시 편집** (피드백 4). 더블클릭(빈 곳)도 동일 유지.
- 도형 그리기: 툴바 도형 선택(사각형/원/화살표/선) → 스테이지 드래그로 1회 그리기 → 자동으로 선택 모드 복귀. Esc=취소.
- 스타일 미니바(선택 시): 색 3종(검/빨/파)·선굵기 1/2/3(도형)·크기/굵기/정렬(텍스트)·삭제. 회전은 Transformer 핸들.
- Delete/Backspace 삭제, 화살표 1px(Shift 10px), Ctrl+Z/Y undo/redo(직렬화 스냅샷 방식 유지).
- 커서: 이동 grab/이동중 grabbing/그리기 crosshair.

### 3.4 서버 검증 확장 (`foms/api/drawing/wizard.py`)
- `type` 허용: `('text','image','rect','ellipse','arrow','line')`.
- 공통 optional: `rotation` 숫자(-360~360).
- rect/ellipse: x,y,w,h 기존 범위 규칙. `stroke` `#rrggbb`, `strokeWidth` in (1,2,3).
- arrow/line: `points` = 숫자 4개 리스트(각 -2000~4000), stroke/strokeWidth 동일.
- 기존 text/image 규칙 불변. 테스트: 신규 타입 정상/이상 케이스.

### 3.5 내보내기 합성
- (a) Transformer 해제+선택 해제 → (b) html2canvas(**폼 레이어만**, scale 2) → (c) offscreen 2956×2080 canvas에 폼 draw → (d) `konvaStage.toCanvas({pixelRatio:2})` draw(위) → toBlob PNG. 다운로드/전달 동일.
- Konva 이미지 노드는 asset-raw same-origin이므로 taint 없음.

## 4. 에디터 크롬 — Apple HIG 스타일 (피드백 3)
- **배경**: 캔버스 영역 `#f5f5f7`(라이트), 시트 그림자 부드럽게(`0 10px 40px rgba(0,0,0,.12)`).
- **툴바**: 상단 고정, 반투명 화이트 `rgba(255,255,255,.82)` + `backdrop-filter: blur(20px) saturate(180%)`, 하단 1px `rgba(0,0,0,.08)`. 높이 52px. 좌: 제목(15px 600)+주문 부제(13px, #86868b). 중앙: 도구 **세그먼트 컨트롤**(선택/텍스트/도형▾/이미지 — iOS segmented: 회색 트랙 `#e8e8ed` 위 흰 pill 슬라이드). 우: undo/redo 아이콘 버튼(SVG), 줌 컨트롤, `저장`(파랑 `#0071e3` filled pill, dirty 시 점 표시), `내보내기 ▾`(secondary pill).
- **버튼**: pill(radius 980px), 13px 500, padding 7px 14px; secondary = `#f5f5f7` bg + `#1d1d1f` text, hover `#e8e8ed`; 아이콘 버튼 32px 원형 hover `#0000000a`. FontAwesome 금지 — 인라인 SVG(스트로크 1.5px, SF Symbols 풍).
- **시트 탭**: 필 형태 탭바(밝은 배경), 활성=흰 pill+그림자, 비활성=텍스트 `#6e6e73`. `+` 원형 버튼.
- **미니 툴바**: 플로팅 캡슐(radius 12px, blur 반투명 다크 `rgba(30,30,32,.85)`, 흰 아이콘/스와치) — iWork 컨텍스트 바 느낌.
- **다이얼로그(전달)**: macOS 시트 — radius 14px, 흰 배경, 타이틀 15px 600, 입력 radius 8px + `#d2d2d7` 1px, 포커스 파랑 링, 버튼 우하단(취소=plain, 전달=파랑 filled). backdrop `rgba(0,0,0,.35)`.
- **토스트**: 하단 중앙 캡슐, 다크 blur, 13px.
- **폰트(에디터 크롬만)**: `-apple-system,"SF Pro Text","Segoe UI Variable","Segoe UI",sans-serif`. 시트 내부는 §2.5 유지(산출물 충실도).
- 라이트 단일 테마. 애니메이션: 120–180ms ease-out(탭 전환·팝업·토스트).

## 5. 검증
- [ ] APP_OK + 위저드 pytest(신규 타입 포함) + 워크벤치 회귀 + perf guard green
- [ ] node --check wizard.js
- [ ] gstack browse E2E: 선택/이동/리사이즈/회전, ctrl+클릭 텍스트, 도형 4종 그리기, 텍스트 편집, 저장→재로드 복원(신규 타입 왕복), 내보내기 PNG에 폼+주석 합성 확인
- [ ] Advisor: 렌더 PNG vs 김유성 샘플 나란히 대조(외곽 테두리·표 검정 그리드·폰트 인상)
- [ ] v1 저장 상태(스테이징 주문) 로드 호환

## 6. 리스크
| 리스크 | 완화 |
|--------|------|
| Konva 캔버스가 폼 클릭 차단 | §3.1 elementFromPoint 재전달 패턴 + 폼 셀 E2E 확인 |
| 기존 v1 상태 호환 | additive 스키마 + 로더 기본값 보충 + 스테이징 3981 실데이터 확인 |
| html2canvas+Konva 합성 어긋남 | 동일 논리좌표(1478×1040)·scale 2 통일, 시각 검수 |
| vendored konva 용량(~330KB) | 위저드 페이지 전용 defer 로드(전역 아님) — perf guard 대상 아님 |
