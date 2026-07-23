# 모바일 ERP secnav 정리 계획
> 상태: 승인됨 | 결정: 마지막 섹션도 secnav 바로 아래 정렬

## 목표
- 반복 패치된 secnav를 HTML·CSS·JS 각 한 책임으로 축소한다.
- 접힌 섹션은 완전히 열린 뒤 한 번만 이동한다.
- 마지막 `접수`도 secnav 아래에 정렬하고, 필요한 여유는 섹션 아래에만 만든다.

## 구조
| 영역 | 책임 |
|---|---|
| `erp_order_tab_mobile.html` | secnav와 섹션을 같은 부모의 형제로 둔다. wrapper 제거 |
| `foms-form-field.css` | sticky 표시, 기본 하단 액션바 여유, JS가 주입하는 tail 변수만 사용 |
| `erp-order-shared.js` | collapse `shown` 뒤 좌표를 계산해 한 번만 `scrollTo` |

## 제거
- `.erp-mobile-secnav-slot`
- `scroll-margin` 기반 점프 보정
- `450ms` timeout fallback
- `behavior: 'smooth'`
- 상시 `scroll-margin + 4rem` 하단 여백

## 검증
1. 구조 계약: wrapper·smooth·timeout 없음, tail 변수와 한 번의 좌표 스크롤 존재.
2. 390×844 브라우저: 발주·접수 클릭 뒤 target top = secnav bottom + 8px(±2px).
3. 스크롤 중 secnav top = header bottom(±2px).
4. `APP_OK`, ERP form contracts, performance guard.
