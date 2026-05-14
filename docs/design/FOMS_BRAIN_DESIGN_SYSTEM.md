# FOMS Brain AX Designer — Design System

> PG-B1: White SketchUp-Like Workbench Shell
> 작성: 2026-05-14 | 버전: 1.0

## 1. 디자인 원칙

1. **White-First**: 캔버스와 크롬은 흰색/밝은 회색. 어두운 ERP add-in과 완전히 구별.
2. **SketchUp-inspired**: 상단 툴바 + 좌측 팔레트 + 우측 트레이의 3-panel 레이아웃.
3. **Dimension-forward**: 치수 정보는 항상 visible. mm 단위 명시.
4. **Status-driven**: 검증 상태(유효/오류)가 항상 상단에 표시.

## 2. 색상 토큰

| 토큰 | 값 | 용도 |
|---|---|---|
| `canvasBg` | `#f0f0f0` | 3D 캔버스 배경 |
| `canvasGrid` | `#d8d8d8` | 그리드 선 |
| `toolbarBg` | `#e8e8e8` | 상단 툴바 / 좌측 팔레트 |
| `toolbarBorder` | `#c8c8c8` | 크롬 테두리 |
| `panelBg` | `#f5f5f5` | 우측 트레이 / 패널 |
| `panelBorder` | `#ddd` | 패널 테두리 |
| `surfaceWhite` | `#ffffff` | 카드 / 입력 배경 |
| `textPrimary` | `#1a1a1a` | 본문 텍스트 |
| `textSecondary` | `#555` | 보조 텍스트 |
| `textMuted` | `#888` | 힌트 / 라벨 |
| `accent` | `#5a67d8` | 선택 / 강조 (FOMS 브랜드 퍼플) |
| `accentLight` | `#ebedff` | 호버 / 선택 배경 |
| `valid` | `#38a169` | 유효 (초록) |
| `invalid` | `#e53e3e` | 오류 (빨강) |
| `warning` | `#d69e2e` | 경고 (노랑) |
| `dimensionRed` | `#e53e3e` | 현장 제약 치수 |
| `dimensionBlack` | `#1a1a1a` | 컴포넌트 치수 |

## 3. 레이아웃

```
┌─────────────────────────────────────────────────────────┐
│  TopToolBar (h: 40px)                                   │
│  [Brand] [Sep] [저장] [Sep] [W×H×D] [Sep] [뷰 탭] [유효/오류] │
├──┬─────────────────────────────────────────┬────────────┤
│  │                                         │            │
│L │  ModulePanel                            │  Right     │
│e │  (w: 200px)                             │  Property  │
│f │                                         │  Tray      │
│t │            DesignerCanvas               │  (w: 240px)│
│  │              (3D / 2D 뷰)               │            │
│P │                                         │  [속성][명령]│
│a │                                         │            │
│l │                                         │            │
│e │                                         │            │
│  │                              [트리 패널]  │            │
│4 │                              (w: 180px) │            │
│4 │                              (접을 수 있음)│            │
├──┴─────────────────────────────────────────┴────────────┤
│  StatusBar (h: 24px)  도구 | 뷰 | 목록 | AI | 프로젝트명 │
└─────────────────────────────────────────────────────────┘
```

## 4. 타이포그래피

| 토큰 | 크기 | 용도 |
|---|---|---|
| `sizeXS` | 10px | 섹션 헤더, 상태 바 |
| `sizeSM` | 11px | 트레이 필드, 툴 라벨 |
| `sizeMD` | 12px | 일반 패널 텍스트 |
| `sizeLG` | 13px | 브랜드명, 중요 값 |

폰트: `-apple-system, "Segoe UI", "Noto Sans KR", sans-serif`

## 5. 컴포넌트

### TopToolBar
- 높이: 40px
- 배경: `toolbarBg`
- 좌: 브랜드 + 가구 유형 배지
- 중앙: 저장 버튼 + 치수 표시 + 뷰 모드 탭
- 우: 유효/오류 상태 + 프로젝트명

### LeftToolPalette
- 폭: 44px
- 아이콘 버튼: 36×36px, 5px 라운드
- 도구: 선택(S) / 이동(M) / 치수(D) / 모듈분할(X) / 선반(L) / 도어(O) / 컷아웃(C)
- 하단: 도면 업로드 버튼 (accent 색상)

### RightPropertyTray
- 폭: 240px
- 섹션: 선택된 컴포넌트 | 가구 조립체 | 설계 검증
- 탭: 속성 / 명령 / 모듈

### ModulePanel
- 폭: 200px
- 가구 유형 2×2 그리드 선택기 (PG-B10)
- 치수 / 통 수 / 도어 타입 / EP/SR 편집

## 6. 상태 표현

| 상태 | 색상 | 표현 |
|---|---|---|
| 선택됨 | `accent` (#5a67d8) | 테두리 + 배경 tint |
| 호버 | `accentLight` | 배경만 |
| 유효 | `valid` (#38a169) | 초록 점 + 텍스트 |
| 오류 | `invalid` (#e53e3e) | 빨강 점 + 오류 목록 |
| 경고 | `warning` (#d69e2e) | 노랑 텍스트 |

## 7. 치수선 색상

- 빨강 (`#e53e3e`): 현장 제약 / 최대 허용 치수
- 검정 (`#1a1a1a`): 컴포넌트 실제 치수
- 파랑 (`#3182ce`): 참조 / 모듈 경계
- 퍼플 (`#5a67d8`): 선택된 치수 핸들

## 8. 변경 이력

| 날짜 | 버전 | 변경 |
|---|---|---|
| 2026-05-14 | 1.0 | PG-B1 초기 디자인 시스템 (white workbench) |
