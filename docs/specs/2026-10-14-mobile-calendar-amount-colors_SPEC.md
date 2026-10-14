# 모바일 홈 달력 — 시공 금액별 칸 색 (회사 공통 설정) — SPEC

작성 2026-10-14. 등급: API(새 쓰기 라우트) + 화면. DB 스키마 변경 없음(기존 `system_settings` 키 하나).
선행: `docs/specs/2026-10-14-mobile-home-month-calendar_SPEC.md` (deploy `89e2c6301`, `1a780fc4c`).

## 1. 요청 (사용자 2026-10-14)

> 시공 금액에 따라 노란색, 분홍색 파스텔 색으로 지정할 수 있게 입력 메뉴를 추가해 줘 — 미니멀 디자인.
> 예) 2500 이상 노란색 파스텔, 3000 이상 분홍색 파스텔.

결정: **회사 전체 같이**, 바꾸는 사람은 **관리자·팀장**(승인 2026-10-14) — 한 번 정하면 모든 직원의 달력에 같은 색이 나온다.

## 2. 동작

- 달력 날짜 칸의 바탕색을 그날 **시공 출고가 합**(칸에 보이는 그 금액)으로 칠한다.
- 기준은 두 단계, 단위는 **만 원**:
  - 노랑(파스텔) — `yellow_from` 만 원 이상
  - 분홍(파스텔) — `pink_from` 만 원 이상 (노랑보다 우선)
- 기본값: 노랑 2,500만 이상 · 분홍 3,000만 이상 · **켜짐**. 끄면 색을 칠하지 않는다.
- 한쪽만 쓰고 싶으면 그 칸을 비운다(빈 칸 = 그 단계 없음).
- 오늘 칸·선택된 칸의 테두리, 지난 날 흐림은 그대로 둔다. 색은 바탕에만 들어간다.
- 범례 줄 오른쪽에 작은 색 점 두 개 `● 2,500만+ ● 3,000만+` 를 붙인다(켜져 있을 때만).

## 3. 입력 메뉴 (미니멀)

- 달력 머리 오른쪽에 톱니 아이콘 버튼(44px, `aria-label="칸 색 기준"`). **관리자(ADMIN)·팀장(MANAGER)에게만** 보인다.
- 누르면 작은 아래 시트:

```
칸 색 기준 (그날 시공 출고가 합)
● 노랑   [ 2500 ] 만원 이상
● 분홍   [ 3000 ] 만원 이상
[켜기/끄기 스위치]          [저장]
```

- 숫자 칸은 `inputmode="numeric"`, 0~100,000(만 원) 정수. 분홍이 노랑보다 작으면 저장 전 화면에서 막고
  "분홍 기준은 노랑 기준보다 커야 해요" 를 보여 준다(서버도 같은 검사).
- 저장하면 시트를 닫고 지금 보는 달을 다시 읽어 색을 바로 바꾼다.
- 다른 관리자가 먼저 저장했으면(버전 충돌) "다른 관리자가 먼저 바꿨어요. 새로 불러올게요" 후 최신 값으로 다시 연다.

## 4. 서버

### 4.1 저장 자리
- `SystemSetting` 키 `mobile_calendar_amount_colors` (새 표 없음).
- 값: `{"enabled": true, "yellow_from": 2500, "pink_from": 3000}` (만 원 정수 또는 null).
- 서비스 모듈 `foms/services/orders/calendar_amount_colors.py` — `reject_templates.py` 와 같은 모양:
  `load_colors(db)`, `colors_version(db)`, `sanitize_colors(value)`, `save_colors(db, value, if_match_version)`.
  낙관적 잠금(`SystemSetting.version`, `FOR UPDATE`), 영수증 표는 쓰지 않는다(되돌릴 수 있는 설정).

### 4.2 라우트
- 달력 페이로드(`_month_calendar`)에 `colors` 와 칸마다 `tone`(`"pink"|"yellow"|""`)을 실어 보낸다.
  판정은 서버 한 곳에서(화면이 금액 글자를 다시 읽어 비교하지 않는다).
- 읽기: `GET /erp/dashboard/calendar-colors` → `{colors, version}` (설정 시트가 열 때 버전을 받는다).
- 쓰기: `POST /erp/dashboard/calendar-colors` — `foms/web/orders/dashboard.py`, `@login_required` +
  `@role_required(["ADMIN", "MANAGER"])`. 본문 `{enabled, yellow_from, pink_from, settings_version}`.
  응답 `{'success','data':{version, colors},'error'}`. 400(값 오류)·409(버전 충돌, 현재 version 동봉).
- 감사: `SecurityLog` 행위 코드 `MOBILE_CALENDAR_COLORS_SAVE`, 표시 라벨 "모바일 달력 칸 색 기준 저장"
  (`foms/services/audit_message_display.py`).
- 하네스 등록(누락 시 smoke red): `foms_order_mutation_policy_manifest.json`·`foms_write_guard_manifest.json`
  에 `mode: guard`, `policy_id: STAFF_MUTATION`(반품 거부 상용구와 동일), `foms_audit_coverage_inventory.json` AUDITED.
- 캐시: 저장 뒤 타워·달력 캐시 슬라이스가 최대 300초 옛 색을 보여 줄 수 있다 → 캐시 지문에 설정 `version` 을 넣어
  저장 즉시 새 키가 되게 한다.

## 5. 바꿀 파일

| 파일 | 변경 |
|---|---|
| `foms/services/orders/calendar_amount_colors.py` (새) | 읽기·검증·저장 |
| `foms/services/orders/dashboard_control_tower.py` | 칸 `tone`, 달력 `colors` |
| `foms/web/orders/dashboard.py` | 쓰기 라우트, 캐시 지문 `colors_version` |
| `templates/orders/partials/dashboard_mobile_tower_calendar.html` | 칸 `is-tone-*`, 범례 점, 톱니(ADMIN) |
| `templates/orders/partials/dashboard_mobile_tower.html` | 설정 시트 마크업(ADMIN 만) |
| `static/js/foms/mobile-tower.js` | 시트 열기·검증·저장·충돌 처리 (300줄 넘으면 `mobile-tower-colors.js` 로 분리) |
| `static/css/contexts/orders/dashboard-control-tower.css` | 파스텔 2색(밝은·어두운 화면), 시트 |
| `foms/services/audit_message_display.py`, 하네스 manifest 3종 | 4.2 |
| 테스트 | 아래 |

색(토큰으로 둔다): 노랑 `#fef9c3`(어두운 화면 `rgba(250,204,21,.16)`), 분홍 `#fce7f3`(어두운 화면 `rgba(244,114,182,.16)`).
칸 글자(실측 파랑·시공 주황·금액 남색)와 대비 4.5:1 이상인 연한 값이다.

## 6. 검증

- 단위: 기준 판정(경계값 2,499/2,500/3,000만, 꺼짐, 한쪽 빈 칸), 값 검증(음수·문자·분홍<노랑 400),
  버전 충돌 409, ADMIN·MANAGER 아닌 계정 403, 감사 행 1건.
- 하네스: `test_auth_enforcement`·`test_write_guard`·`test_admin_audit_screen_readability_3` 통과.
- `pre_push_smoke.ps1` exit 0, 스테이징 7월 실데이터(하루 3,000만 넘는 날 다수)로 색 확인.

## 7. 하지 않는 것

- 사람마다 다른 기준, 3단계 이상, 색 고르기(노랑·분홍 고정).
