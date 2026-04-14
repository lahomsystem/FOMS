# FOMS — `foms/` product namespace

## 목적

Flask 앱의 **canonical runtime tree** (`foms/web`, `foms/api`, `foms/services`, `foms/platform`, …)에 대한 사람/AI용 **내비게이션 진입점**이다. 레거시 등록 경로는 `apps/`에 남아 있으며, 신규 구현은 이 트리 우선이다 (controlling spec §2.4).

## 주요 모듈 (요약)

| 영역 | 역할 |
|------|------|
| `foms/platform/` | 앱 팩토리, **blueprint 등록** (`blueprints.py`가 live registry truth), HTTP/Socket.IO 부트스트랩 |
| `foms/web/` | Jinja/HTML 페이지 Blueprint의 canonical 위치 |
| `foms/api/` | JSON·API·webhook route의 canonical 위치 |
| `foms/services/` | 도메인 정책·오케스트레이션 |

## 읽기 순서

1. 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
2. Live blueprint 순서: `foms/platform/blueprints.py` (`register_blueprints`)
3. **FR20 로컬 README 앵커** (bounded context별 단일 진입점):
   - Measurement: `foms/web/measurement/README.md`
   - Orders API: `foms/api/orders/README.md`
4. 레거시 Flask 등록 경로: `apps/` (전환기; Wave 2에서 adapter/alias 계약 고정)

## 금지 / 주의 의존성

- `foms/*`에서 `backups/`, `Add In Program/`, `SCheduler/` 등 **quarantine** 트리로의 runtime import 금지 (spec §2.5).
- `apps/`는 **overlay** — 새 장기 비즈니스 로직의 기본 위치로 삼지 않는다 (spec §1.2 FR5).
- 구조 작업 시 blueprint **이름·`url_prefix`·등록 순서**는 별도 승인 없이 바꾸지 않는다 (Wave 2 freeze).

## 관련 기록

- Wave 2 truth map: `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md`
- `src/`: non-product / tooling-adjacent — `src/README.md` 참고 (Wave 1 분류).
