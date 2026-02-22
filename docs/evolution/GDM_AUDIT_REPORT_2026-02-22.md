# 🏥 FOMS 개발 건강 진단 보고서

**작성일**: 2026-02-22  
**작성주체**: GDM (Grand Develop Master)  
**참조**: GDM_EXECUTION_PLAN §1.1, explore-codebase·code-reviewer·database-specialist 병렬 진단 결과 종합

---

## 전체 점수: 62/100

| 구분 | 건수 | 요약 |
|------|------|------|
| 긴급 🔴 | 3 | 보안 이슈(API 키, bare except, SQL 주입 가능성) |
| 개선 권장 🟡 | 15+ | 품질·성능·DB·프론트엔드 개선 |
| 양호 🟢 | 7 | 아키텍처·Blueprint·대부분 API 응답 양호 |

**판정**: 운영 가능하나, 긴급 3건을 우선 해결한 뒤 단계적 개선을 권장합니다.

---

## 긴급 (🔴)

### 1. 하드코딩된 API 키 (보안)
- **위치**: `map_config.py`, `SCheduler/config.py`, `apps/api/address.py`
- **문제**: Kakao REST API 키가 코드에 직접 적혀 있음
- **영향**: 코드 유출 시 무단 사용·과금·제한 위험
- **조치**: `os.environ.get('KAKAO_REST_API_KEY')` 등 환경변수로 변경

### 2. Bare except 사용 (보안·디버깅)
- **위치**: `apps/auth.py:48`, `web_migration.py`, `simple_backup_system.py`, `safe_schema_migration.py`
- **문제**: `except:` 로 모든 예외를 잡아 원인 파악·복구가 어려움
- **조치**: `except Exception as e:` 로 변경하고 `logger.exception(...)` 로깅

### 3. SQL Injection 가능성 (보안)
- **위치**: `safe_schema_migration.py:65` – f-string으로 컬럼명/타입 조합
- **문제**: `column_name`, `column_type` 이 외부 입력이면 DB 조작 위험
- **조치**: 화이트리스트로 허용 컬럼만 허용하거나 SQLAlchemy DDL 사용

---

## 개선 권장 (🟡)

### 품질
- **print 디버깅**: `attachments.py`, `erp_map.py`, `erp_orders_structured.py`, `chat/routes.py`, `storage.py` 등 다수 → `logging` 모듈로 전환
- **DEBUG print**: `notifications.py:198` – 운영 노출 위험, 제거 또는 플래그 연동
- **app.py 라우트**: `/favicon.ico`, `/__build` 등 유틸 라우트 → 별도 Blueprint 분리

### 프론트엔드
- **fetch 에러 처리 미흡**: `quick-status-change.js`, `measurement.js` – `res.ok` 확인·사용자 오류 메시지 표시
- **인라인 스타일 과다**: `layout.html`, `map_view.html` 등 → CSS 클래스로 이전
- **layout.html 1,534줄**: 800줄 기준 초과 → `partials/` 분리 검토

### API
- **응답 형식 불일치**: `erp_map.py`, `erp_measurement.py` – `error` vs `message` → `{success, data, error}` 표준화

### DB
- **flag_modified 누락**: `erp_orders_drawing.py`, `erp_orders_structured.py` – `structured_data` 수정 시 `flag_modified(order, 'structured_data')` 추가
- **인덱스 누락**: `Order.received_date`, `measurement_date`, `is_erp_beta` – 날짜/필터 쿼리용
- **N+1 위험**: 대시보드·목록 API에 `selectinload`/`joinedload` 적용 검토

### 파일 크기 (규칙 초과)
- **Python 500줄 초과**: 9개 (최대 `coding_research_center.py` 1,223줄)
- **HTML 800줄 초과**: 18개 (최대 `wdcalculator_scripts.html` 3,309줄)
- **app.py 395줄**: 목표 300줄 미달성

---

## 양호 (🟢)

- **Blueprint 구조**: 도메인별 Blueprint로 잘 분리됨
- **API 응답 형식**: 대부분 `{success, data, message}` 패턴 준수
- **SECRET_KEY**: 환경변수 사용, 프로덕션 미설정 시 예외 발생 (안전)
- **N+1**: `erp_dashboard` 등 배치 조회·dict 매핑으로 최소화
- **XSS**: Jinja2 autoescaping, `escapeHtml()` 사용
- **DB 연결**: `DATABASE_URL` 정규화, pool 설정 적절
- **Phase C·D 완료**: geocode, Direct R2 업로드 기반 구축

---

## Phase 1~4 개선 로드맵 (비전문가용)

### Phase 1: 안정화 (현재 작동 코드 보호)
1. **API 키 환경변수화** – 코드에 적힌 카카오 키를 시스템 설정으로 옮김
2. **bare except 수정** – 오류 원인 파악이 가능하도록 `except Exception` + 로깅으로 변경
3. **safe_schema_migration SQL 보안** – 허용된 컬럼만 쓰도록 제한
4. **flag_modified 추가** – 도면·구조 API에서 JSONB 변경 시 반드시 호출

→ **목표**: 보안·데이터 안정성 확보

### Phase 2: 품질 개선 (유지보수 용이)
1. **print → logging 전환** – 운영 로그 형식 통일
2. **fetch 에러 처리** – 화면에서 “저장 실패” 등 사용자에게 알림
3. **app.py 유틸 라우트 분리** – favicon, __build 등을 별도 Blueprint로 이동
4. **API 응답 형식 통일** – `error`/`message` 중 하나로 표준화

→ **목표**: 로그·에러 처리 일관성, 코드 정리

### Phase 3: 성능·DB 고도화
1. **Order 인덱스 추가** – `received_date`, `measurement_date`, `is_erp_beta`
2. **N+1 최소화** – 대시보드·목록 API에 `selectinload` 적용
3. **대형 파일 분리** – 500줄 초과 Python, 800줄 초과 HTML 우선 분할

→ **목표**: 조회 속도 개선, 대형 파일 유지보수 용이

### Phase 4: 확장·진화
1. **app.py 300줄 이하** – 초기화/Blueprint 등록 모듈화
2. **layout.html partial 분리** – 1,500줄→800줄 이하로 분할
3. **Phase D 프론트엔드** – 첨부 업로드 UI를 session→PUT→complete 흐름으로 전환
4. **Railway 배포** – Phase C·D 변경 반영 후 원격 검증

→ **목표**: 장기 유지보수·신규 기능 확장 기반 마련

---

## 검증 결과 (GDM §5)

- [x] `python -c "import app; print('OK')"` 통과
- [x] pytest 7 passed
- [x] explore-codebase, code-reviewer, database-specialist 병렬 진단 완료
- [ ] postgres MCP 쿼리 성능 분석 (세션 내 미호출)

---

## 다음 권장 액션

1. **즉시**: 긴급 3건 처리 (API 키, bare except, SQL injection)
2. **단기**: flag_modified 2파일 수정, print→logging 1차 전환
3. **중기**: Order 인덱스 추가, fetch 에러 처리
4. **배포**: Phase C·D 반영 후 Railway 푸시 및 원격 검증
