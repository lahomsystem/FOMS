# 밖에서 불러오는 스크립트·스타일에 무결성(SRI) 표시 — SPEC (2026-10-20)

## 목적
화면이 CDN 에서 스크립트·스타일을 불러오는데 "파일이 바뀌지 않았는지" 확인하는 표시(SRI `integrity`)가 한 곳도 없다. CDN 파일이 바뀌면(사고·탈취) 그 코드가 FOMS 화면에서 로그인한 직원 권한으로 그대로 돈다. flatpickr 는 버전도 없어 그날의 최신판을 받는다.

## 지금 구조(2026-10-20 전수)
| 파일 | 위치 | 버전 |
|---|---|---|
| socket.io 4.5.4 | `layout_head.html`·`drawing/wizard.html`·`measurement/map_view.html` | 고정 |
| bootstrap 5.3.0-alpha1 JS·CSS | `layout_scripts.html`·`layout_head.html`·`partner/layout.html` | 고정 |
| bootstrap 5.1.3 JS·CSS | `map_view.html` | 고정 |
| flatpickr JS·ko·CSS | `layout_scripts.html`·`layout_head.html` | **없음**(받는 판 4.6.13) |
| font-awesome 6.4.0 / 6.0.0 CSS | `layout_head.html`·`partner/layout.html` / `map_view.html` | 고정 |
| pretendard v1.3.9 CSS | `layout_head.html`·`admin/naver_workbench.html` | 고정 |
| html2canvas 1.4.1 | JS 6곳이 필요할 때 `createElement('script')` | 고정 |
| 카카오 지도 SDK·카카오 공유 SDK·다음 우편번호 | 지도 3곳·`erp-share.js`·주문 마법사 | 서비스 SDK |

서비스워커(`static/sw.js`)는 다른 출처 요청을 가로채지 않는다(`url.origin !== self.location.origin` 이면 return) — SRI 와 부딪히지 않는다.

## 변경
1. flatpickr 세 주소를 `flatpickr@4.6.13/dist/...` 로 고정. 고정 주소 파일이 지금 받는 파일과 바이트가 같음을 확인했다(동작 변화 없음).
2. 위 표의 버전 고정 파일 태그에 `integrity="sha384-…"` + `crossorigin="anonymous"`. 해시는 각 주소를 두 번 받아 같은지 확인한 뒤 계산했다(bootstrap 5.1.3 은 공식 문서 해시와 일치). 모든 CDN 이 `Access-Control-Allow-Origin: *` 를 준다.
3. html2canvas 로더 6곳: `s.src` 뒤에 `s.integrity`·`s.crossOrigin = 'anonymous'`.
4. 서비스 SDK 3종은 키·시점마다 내용이 달라 SRI 를 붙일 수 없다 — 테스트에서 이름으로만 예외.

## 건드리지 않는 것
- 파일을 우리 서버로 옮기기(자체 호스팅)·bootstrap 시험판(alpha1) 정식판 교체 — 화면 회귀 확인이 따로 필요하다.
- 보안 헤더 CSP 의 script-src 제한(별건).

## 검증
- 헤드리스 Chromium 에 12개 파일을 같은 해시로 실었을 때 전부 로드(bootstrap·io·flatpickr·ko·html2canvas 전역 확인, 스타일 6개), 일부러 틀린 해시 1개만 막힘(음성 대조군).
- 새 테스트 `tests/domains/test_external_assets_sri.py`: 템플릿의 외부 스크립트·스타일 태그는 SRI 필수(서비스 SDK 제외), 버전 없는 jsdelivr npm 주소 금지, html2canvas 로더는 integrity 설정. 수정 전 코드에서 3건 실패.
- `tests/performance/test_shared_layout_defer_contract.py` 의 flatpickr 주소를 고정 주소로 갱신.
