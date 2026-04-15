# Legacy mobile / WDPlanner-adjacent prototype (repo-root `src/` retired)

**Physical location (SFC-B11D, 2026-04-15):** 이 트리는 저장소 루트에 있던 `src/`를
`Add In Program/WDPlanner/legacy-mobile-prototype/`로 옮긴 것이다. Flask 런타임 import 경로와 무관하다.

---

# 비(非) Flask 제품 트랙

이 디렉터리는 **FOMS Flask modular monolith 런타임(`app:app`)과 별도**인 TypeScript/React Native 스타일 소스다.

## 판정 (Wave 1 — W1-B2)
- **역할:** WDPlanner / 모바일 견적 UI 등 **별도 클라이언트 실험·프로토타입** (저장소 내 `Add In Program/WDPlanner` 존재와 성격 정렬).
- **분류:** **non-product track / tooling-adjacent**. canonical product tree는 `foms/`, `apps/`, `templates/`, `static/`이다.
- **성장 규칙:** Flask 앱의 신규 도메인 로직·API·템플릿 소스로 사용하지 않는다. 여기서 시작한 코드가 제품 경로로 들어갈 경우 **명시적 이관 계획** 없이 루트 `src/`만 늘리지 않는다.

## 포함물 (요약)
- `AppNavigator.tsx`, `screens/*` — 화면 네비게이션
- `core/calc.ts` — 계산 로직 스케치
- `db/*`, `types/*`, `seed/*` — 로컬 DB/타입/시드 실험

## 운영자 메모
- Python import 경로나 `app.py` 부트스트랩과 **연결되지 않는다**.
- 빌드/배포 파이프라인은 저장소 기본 Railway Flask 배포와 **분리**되어 있다고 본다.
