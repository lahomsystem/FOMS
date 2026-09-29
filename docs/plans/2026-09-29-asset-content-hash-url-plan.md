# 화면 파일(CSS·JS) 버전 자동 표시 — 계획 (시범: 주문 화면 한 파일)

- 작성 2026-09-29 · 기준 `origin/deploy` · 상태: **승인(2026-09-29, 한 파일 시범) → 구현(deploy)**
- 근거: 언어 이전 분석 보고서 ⑧ 권고 3 — 앞단 fix 수정의 27.1% 가 버전 핀(`?v=날짜`)만 바꾸는 일이었다.

## 0. 쉬운 요약

지금은 CSS·JS 파일을 고칠 때마다 템플릿의 `?v=20260929a` 같은 번호를 **사람이 손으로** 올린다. 깜빡하면 폰·PC 가 옛 파일을 계속 쓰고, 부모·자식 파일 번호가 어긋나는 사고가 반복됐다. 이 계획은 **파일 내용에서 번호를 자동으로 만드는 도우미**(`asset_url`)를 만들고, 주문 화면 공용 조각 한 파일(`templates/orders/partials/erp_order_js.html`, 자산 37개)에만 먼저 써 본다. 4주 뒤 손 번호 수정이 줄었는지 재고 나머지로 넓힐지 정한다.

## 1. 확인한 사실

| 항목 | 사실 | 출처 |
|---|---|---|
| 지금 방식 | `{{ url_for('static', filename='X') }}?v=YYYYMMDD<글자>` — 템플릿 73개에 352개, JS 로더 안 19개, CSS `@import` 60개 | 조사 2026-09-29 |
| 도우미 | 없음(0건) | `grep asset_url` |
| 파일 제공 | WhiteNoise. `?v=` 가 붙은 css/js 는 미들웨어가 `max-age=86400`(하루), 없으면 `no-cache` | `foms/platform/app_factory.py:120-164` |
| 서비스 워커 | `/static/` css·js 는 **쿼리까지 포함한 URL** 로 캐시 | `static/sw.js` |
| 빌드 | 자산 빌드 단계 없음(파일 그대로 제공). predeploy 는 따로 도는 컨테이너라 거기서 만든 목록은 웹 컨테이너에 안 닿는다 | `Dockerfile`, `predeploy.sh` |
| 시범 파일 | `erp_order_js.html` 자산 37개(CSS 13·JS 24), **`@import` 쓰는 CSS 없음**. 주문 추가·수정·상세 분할·상세 조각 4곳이 포함 | 조사 |

## 2. 설계

- **도우미** `asset_url(path)` → `url_for('static', filename=path) + "?v=" + 내용 해시 앞 12자리`.
  - 해시는 프로세스마다 처음 쓸 때 계산해 기억(파일 내용이 같으면 두 워커·두 컨테이너가 같은 값). 개발 모드(`DEBUG`)에서는 파일 수정 시각이 바뀌면 다시 계산.
  - URL 모양을 `?v=` 로 유지 → 하루 캐시 미들웨어·서비스 워커를 **고치지 않아도 된다**.
  - 없는 파일: 시험·개발에서는 즉시 오류(오타를 바로 잡음), 운영에서는 경고 로그 + 쿼리 없는 URL(화면은 뜬다).
  - 등록: Jinja 전역, `foms/services/context_processors.py` 의 `mark` 옆.
- **시범 범위**: `erp_order_js.html` 37개만 `{{ asset_url('…') }}` 로. 이미지 4개(버전 없음)는 그대로.
- **알려진 부작용**: 37개 중 14개는 다른 템플릿에서도 날짜 핀으로 불린다 → 시범 기간엔 같은 파일이 두 URL(두 캐시 칸)로 받아질 수 있다. 하루 캐시라 비용이 작아 시범 동안 받아들인다(확대 때 해소).

## 3. 시험

- 새 `tests/contracts/assets/test_asset_manifest.py`: 임시 static 폴더에서 ① 한 바이트 바꾸면 URL 이 바뀐다 ② 내용이 같으면 URL 이 같다 ③ 없는 파일은 시험 모드에서 오류 ④ 렌더된 `erp_order_js.html` 의 37개 URL 이 모두 `?v=<12자리 16진>` 이고 파일 내용 해시와 맞다.
- 기존 시험 중 이 파일의 날짜 핀을 글자로 박아 둔 것들(`test_erp_order_shared_form_scripts.py`, `test_naver_dock*.py`, `test_erp_add_order_autosave.py`, `test_send_trace.py`, `test_attachment_preview_fullscreen.py` 등)을 "도우미가 만든 URL 을 쓴다"는 단언으로 바꾼다. 템플릿 전체에서 `?v=날짜` 모양을 요구하는 시험(`test_admin_override_ui.py` 등)은 도우미 호출도 허용하도록 고친다 — 뜻이 약해지지 않게 음성 대조를 둔다.

## 4. 측정 (4주 뒤)

`git log --since=<전환일> --no-merges -p -U0 -- templates static` 로 "`?v=` 만 바뀐 수정" 수를 전환 전 4주와 비교. 줄었으면 확대 계획(나머지 템플릿 → JS 로더 → CSS `@import` 는 부모 해시에 자식 해시를 섞는 방식)을 세운다.

## 5. 되돌리기

템플릿 한 파일과 도우미 등록 되돌리기. 캐시 동작은 같은 `?v=` 규칙이라 사용자 쪽 영향 없음.

## 6. 부수 정리

낡은 설명 고치기: `static/css/foundation/erp-pro.css:3`·`foms-mobile-surfaces.css:3`("1시간" → 하루), `docs/guides/NETWORK_EDGE_TAIL_FIX.md:16`.

## 6-1. 구현 기록 (2026-09-29)
- `foms/services/asset_urls.py`(`asset_url`, 프로세스 캐시·DEBUG 수정 시각 감시·시험/개발 모드 없는 파일 오류·운영 경고 후 쿼리 없는 URL), Jinja 전역 등록. `erp_order_js.html` 37개 전환.
- 계약 `tests/contracts/assets/test_asset_manifest.py`(14 — 한 바이트 → URL 변경, 같은 내용 → 같은 URL, 없는 파일, 렌더된 37개가 실제 파일 해시와 일치, 해시 URL 에도 하루 캐시, 음성 대조). 날짜 핀을 글자로 박던 시험 13개를 "내용 해시 URL" 단언으로(기대값은 `tests/support/asset_urls.py` 가 구현을 거치지 않고 hashlib 로 계산).
- 알려진 부작용: `static/js/foms/fragment-loader.js` 는 쿼리까지 포함한 URL 로 "이미 실행한 스크립트" 를 가려서, 날짜 핀으로 이미 실린 공용 스크립트 14개가 편집 조각에서 한 번 더 받아지고 실행된다. 확인한 스크립트는 중복 실행 방지(`__FOMS_*_BOUND`)가 있거나 전역 객체만 정의 — 동작 문제 없음, 확대 때 사라짐.
- 해시는 파일 바이트 기준이라 윈도우(CRLF)와 리눅스(LF) 값이 다르다(환경 안에서는 일관).
- 검증: 전체 11234 passed, visual 계약 39 passed. 구현은 격리 작업 폴더의 에이전트가 하고 diff·시험을 직접 확인한 뒤 반영.

## 7. 사용자가 정할 것

1. 이 계획대로 시범 진행 여부.
2. 공용 자산 14개를 시범 때 다른 템플릿까지 함께 바꿀지(권장: 시범에선 안 바꿈 — 범위를 작게).
