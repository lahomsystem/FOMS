# 파일 정리 및 다음 착수 계획표

> **기준일**: 2026-02-18  
> **목적**: app.py SLIM-035 보류 후, **파일 정리**를 우선 착수하고 이후 작업 순서를 명확히 함  
> **원칙**: 한 번에 한 단위씩, 삭제·이동 전 사용처 확인

---

## 1. app.py SLIM-035 보류

| 항목 | 내용 |
|------|------|
| **ID** | SLIM-035 |
| **상태** | **보류** (일단 중단) |
| **목표** | app.py 319줄 → 300줄 이하 (선택 사항) |
| **비고** | 필요 시 `docs/plans/2026-02-18-app-slim-task-plan.md` 참조하여 재개 |

---

## 2. 다음 착수: 파일 정리 (Phase 1)

### 2.1 정리 대상 유형

| 유형 | 설명 | 검증 |
|------|------|------|
| **중복·폐기 문서** | 같은 내용의 진행 문서, 이미 계획서로 대체된 md | Git 이력 있으므로 삭제 가능 |
| **임시·로컬 전용** | `config/local*`, `*.tmp`, 테스트용 덤프 | .gitignore 확인 후 미추적 파일만 정리 |
| **미사용 스크립트** | import/호출처 없는 스크립트 | grep로 참조 확인 후 판단 |
| **빈 디렉터리** | 의미 없이 남은 빈 폴더 | 필요 시 제거 |

### 2.2 파일 정리 테스크 (우선순위순)

| ID | 작업 | 대상/기준 | 산출물 | 검증 |
|----|------|-----------|--------|------|
| **CLEAN-001** | docs 내 중복·폐기 문서 점검 | docs/, docs/plans/, docs/context/, docs/evolution/ | 삭제·아카이브 목록 | 링크 깨짐 없음 |
| **CLEAN-002** | .cursor/artifacts 미사용/중복 아티팩트 점검 | .cursor/artifacts/, archive/ | 유지/삭제 목록 | GDM·계획 참조에 영향 없음 |
| **CLEAN-003** | .gitignore 정리 | config/local*, *.log, __pycache__ 등 | .gitignore 갱신 | 불필요 추적 파일 없음 |
| **CLEAN-004** | scripts/ 사용처 확인 | scripts/*.py, *.ps1 | 사용 중 목록 / 미사용 후보 | app·cron·CI에서 참조 여부 |
| **CLEAN-005** | 루트·임시 파일 점검 | *.tmp, *.bak, 테스트용 SQL/JSON | 삭제 목록 | 서비스·배포와 무관 |

### 2.3 실행 시 주의

- **삭제 전**: `grep` 또는 검색으로 참조처 확인
- **문서 삭제**: 다른 md에서 링크하는지 확인 후 진행
- **config/**: 로컬 설정은 .gitignore로 제외, 샘플만 저장소에 유지

---

## 3. 파일 정리 후 다음 작업 (Phase 2)

GDM 감사 2026-02-18 권장 순서 및 기타 항목.

| 순서 | ID | 작업 | 비고 |
|------|-----|------|------|
| 1 | CLEAN-001~005 | 파일 정리 실행 | 본 계획 §2 |
| 2 | NEXT-001 | order_pages.py 500줄 이하 분리 | edit_order 등 별도 Blueprint/모듈 검토 (GDM 감사 권장) |
| 3 | NEXT-002 | 대형 템플릿 partial 분리 | calculator.html, erp_production_dashboard, erp_construction_dashboard, chat_scripts 등 (800줄 이하 목표) |
| 4 | NEXT-003 | 핵심 API·주문 상태 변경 pytest 도입 | 단계적 확대 (GDM 감사 권장) |
| 5 | NEXT-004 | db_admin 등 스크립트 비밀번호 환경변수화 | scripts/db_admin.py 등 (GDM 감사 권장) |
| 6 | NEXT-005 | AI 분석 툴 (apps/api/ai.py) | 선택 |
| 7 | NEXT-006 | 카카오 알림톡 (apps/api/kakao.py) | 선택 |

**참조**: `docs/evolution/GDM_AUDIT_2026-02-18.md` (다음 액션 표)

---

## 4. 검증 체크리스트 (매 CLEAN 완료 후)

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] `python app.py` → 서버 기동
- [ ] 삭제한 파일 경로를 참조하는 문서·코드 없음 (grep 확인)
- [ ] docs/CURRENT_STATUS.md 갱신 (상태 변경 시)
- [ ] TASK_REGISTRY 갱신 (CLEAN-001~005 등록·완료 시)

---

## 5. 진행 상태 (갱신용)

| ID | 상태 | 완료일 | 비고 |
|----|------|--------|------|
| SLIM-035 | 보류 | - | app.py 300줄 이하, 필요 시 재개 |
| CLEAN-001 | 대기 | - | docs 중복·폐기 문서 |
| CLEAN-002 | 대기 | - | .cursor/artifacts |
| CLEAN-003 | 대기 | - | .gitignore |
| CLEAN-004 | 대기 | - | scripts/ 사용처 |
| CLEAN-005 | 대기 | - | 루트·임시 파일 |
| NEXT-001~006 | 대기 | - | Phase 2 (파일 정리 후) |

---

## 6. 관련 문서

- **app.py 슬림**: `docs/plans/2026-02-18-app-slim-task-plan.md` (SLIM-035 보류)
- **erp.py 분리**: `docs/plans/2026-02-17-erp-split-plan.md` (완료)
- **GDM 감사**: `docs/evolution/GDM_AUDIT_2026-02-18.md`
- **현재 상태**: `docs/CURRENT_STATUS.md`
