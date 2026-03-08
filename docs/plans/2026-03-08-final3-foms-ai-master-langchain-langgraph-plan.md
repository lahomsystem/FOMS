---
title: "FOMS AI 최종 마스터 계획서 v3 (Final3)"
date: 2026-03-08
status: FINAL3_MASTER_PLAN
consolidated_from:
  - 2026-03-08-claude-final-langchain-langgraph-master-plan.md (Claude)
  - 2026-03-08-final2-foms-ai-master-langchain-langgraph-plan.md (Codex)
---

# FOMS AI 최종 마스터 계획서 v3

## 0. 문서 성격

이 문서는 FOMS에 LangChain, LangGraph, LangSmith를 도입할 때 기준이 되는 단일 마스터 계획서다.

역할은 4가지다.

1. 아키텍처 원칙 고정
2. 단기, 중기, 장기 실행 순서 고정
3. 운영 가드레일과 금지선을 명문화
4. 구현팀이 바로 착수할 수 있는 수준의 로드맵 제공

이 문서는 아이디어 모음이 아니라 실제 실행 기준 문서다.

---

## 1. 최종 결론

FOMS는 LangChain과 LangGraph를 붙이기 좋은 상태다.

이유는 명확하다.

1. `structured_data` 기반 구조화 주문 원장(JSONB)이 이미 존재한다.
2. `OrderEvent`, `OrderTask` 중심의 추적 구조가 이미 존재한다.
3. `services/erp_policy.py`와 정책 JSON으로 결정론적 규칙이 이미 분리되어 있다.
4. `Redis + RQ` 기반 비동기 실행 인프라가 이미 있다.
5. 채팅, 첨부, 일정, 알림 데이터가 AI 보조 기능과 직접 연결된다.

단, 도입 방향은 하나로 제한한다.

> FOMS는 결정론적 ERP 엔진을 유지하고, AI는 그 위에 읽기, 요약, 분류, 초안 생성, 승인형 오케스트레이션을 담당하는 보조 계층으로만 붙는다.

---

## 2. 통합 원칙

### 2-1. 만장일치 원칙 (7항목)

| # | 원칙 | 적용 방식 |
|---|------|-----------|
| 1 | ERP 원장이 유일한 진실 원천 | 모든 최종 반영은 기존 DB/API 경로 통과 |
| 2 | `erp_policy.py` 룰셋 대체 금지 | LLM은 규칙 계산자가 아니라 해설자/추천자 |
| 3 | AI는 Sidecar 계층으로 격리 | `services/ai/`, `apps/api/ai/` 중심으로만 도입 |
| 4 | Read-Only → Draft → Human-Approved Write | 위험 단계별로만 진화 |
| 5 | 모든 AI 실행 추적 가능 | LangSmith + AI Run Log + OrderEvent 기록 |
| 6 | 운영 핵심 경로 deterministic fallback 필수 | AI 실패 시 기존 로직 동작 유지 |
| 7 | 장시간 그래프는 RQ Worker에서만 실행 | 웹 요청에서 직접 돌리지 않음 |

### 2-2. 절대 금지 (10항목)

| # | 금지 사항 | 이유 |
|---|----------|------|
| 1 | AI가 승인 없이 DB write 직접 수행 | ERP 원장 무결성 파괴 |
| 2 | AI가 `Order.status`, stage, approval, owner_team 최종 확정 | 사내 책임 소재 불명확 |
| 3 | AI가 금액, 정산, 예약금, 잔금의 최종 진실값 역할 수행 | 수학적 정확성 보장 불가 |
| 4 | 정책 엔진을 프롬프트로 대체 | 결정론적 규칙의 비결정론적 전환 |
| 5 | AI가 권한 판정 담당 | 보안 감사 체계 무력화 |
| 6 | 초기부터 Agentic RAG + Multimodal + 외부웹 + Write 동시 도입 | 복잡성 폭발, 디버깅 불능 |
| 7 | 웹 요청 안에서 장시간 LangGraph 실행 | 요청 타임아웃, UX 악화 |
| 8 | 근거 없는 추천을 UI에 확정값처럼 노출 | 사용자 오인 위험 |
| 9 | trace, prompt version, schema version 없이 운영 반영 | 장애 대응 불가 |
| 10 | deterministic fallback 없이 핵심 경로에 AI 의존 | 운영 안정성 파괴 |

### 2-3. 허용 범위 (7항목)

| # | 허용 범위 | 비고 |
|---|----------|------|
| 1 | 주문 텍스트 구조화 **초안** 생성 | Draft 상태, 사람 승인 후 저장 |
| 2 | 누락 필드 찾기 + 보충 제안 | Regex 결과 대비 LLM 보완 |
| 3 | 주문/채팅/이벤트/태스크 요약 | Read-Only |
| 4 | CS/AS **초안** 분류 + 팀 추천 | 자동 접수 금지, Draft만 |
| 5 | 위험 주문 브리핑 생성 | SLA 위반 감지 + 근본 원인 추론 |
| 6 | 내부 정책 질의응답 (RAG) | 출처(Citation) 필수 |
| 7 | 사람이 승인할 액션 초안 제시 | approve / reject / edit 3분기 |

---

## 3. FOMS 코드 시너지 맵

| FOMS 자산 | 현재 역할 | AI 시너지 | 시기 |
|-----------|----------|-----------|:----:|
| `models.Order.raw_order_text` | 자연어 주문 원문 저장 | 하이브리드 파서 입력 | 단기 |
| `models.Order.structured_data` (JSONB) | 구조화 주문 원장 | Pydantic structured output 1:1 매핑 | 단기 |
| `models.Order.structured_confidence` | 파싱 신뢰도 기록 | fallback 기준치, evaluator 기준 | 단기 |
| `OrderEvent` | 상태 변경 감사 로그 | AI 추천/적용 로그 기록 | 단기 |
| `OrderTask` | 후속 업무 추적 | AI draft task, 리스크 후속 추적 | 중기 |
| `services/erp_policy.py` (793줄) | 단계/팀/규칙 계산 | RAG 대상 (읽기만). AI 해설, 예외 탐지 | 단기 |
| `data/erp_policy.json` 외 JSON | SLA, 자동 규칙, 템플릿 | Policy RAG 소스 | 중기 |
| `apps/api/chat/` + `ChatMessage` | 주문 채팅 | 요약, commitment extraction, triage | 중기 |
| `apps/api/erp_orders_structured.py` | 구조화 데이터 API | AI Draft → 기존 PUT API로 안전 커밋 | 단기 |
| `erp_automation.py` (85줄) | 자동 태스크 생성 | AI Task 추천 Draft → 사람 승인 후 호출 | 중기 |
| `foms_address_converter.py` (481줄) | 주소 정규화 | LLM 클렌징 → Kakao fallback 강화 | 중기 |
| `services/jobs/queue.py` (Redis/RQ) | RQ Worker | LangGraph durable execution, 야간 배치 | 중기 |
| `models.Notification` + SocketIO | 알림 | AI 생성 메시지 → 기존 알림 채널 전송 | 중기 |
| `erp_policy.check_quest_approvals_complete()` | 퀘스트 승인 | LangGraph HITL interrupt ↔ Quest API | 장기 |
| `foms_map_generator.py` (28K) | 지도/경로 | Multi-Agent 일정 최적화 (연구 트랙) | 장기 |
| `apps/excel_import.py` (12K) | 엑셀 임포트 | 컬럼 자동 매핑 + 정합성 검증 | 장기 |
| `OrderAttachment` | 사진/도면 첨부 | 멀티모달 보조 (장기) | 장기 |

핵심 판단 3가지:
1. FOMS는 이미 AI 친화적 데이터 구조를 갖추고 있다.
2. 가장 큰 시너지는 정책 대체가 아니라 운영 보조 + 승인형 흐름이다.
3. 초기 성공 가능성이 가장 높은 영역은 주문 파싱, Order Copilot, CS/AS 초안, Daily Risk Briefing이다.

---

## 4. 목표 아키텍처

### 4-1. 역할 분리

**LangChain** — 모델 사용 런타임 SDK
1. LLM 호출 표준화
2. Structured Output (Pydantic)
3. Tool Binding
4. Retrieval (RAG)
5. 요약 / 분류 / 추출

**LangGraph** — 워크플로 오케스트레이터
1. 장기 실행 (Long-running)
2. 상태 저장 (Checkpointing)
3. 승인 대기 (Human-in-the-Loop)
4. 중단 / 재개 (Interrupt / Resume)
5. 병렬 분해 (Orchestrator-Worker)
6. Evaluator-Optimizer 루프

**FOMS 기존 백엔드** — 진실의 원천 (변경 없음)
1. 정책 계산 (`DEFAULT_OWNER_TEAM_BY_STAGE`, Quest Rules)
2. 권한 판정
3. 상태 전이 (`check_quest_approvals_complete`)
4. 금액 계산
5. 최종 저장

### 4-2. 시스템 배치도

```
┌─────────────────────────────────────────────────────────────────┐
│                        FOMS + AI Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  FOMS Core (기존 유지 — 0줄 변경)                                │
│  ├─ Flask / SQLAlchemy / PostgreSQL                              │
│  ├─ ERP Policy Engine (erp_policy.py)                            │
│  ├─ Orders / Events / Tasks / Chat / Notifications               │
│  └─ Redis / RQ                                                   │
│                                                                  │
│  AI Sidecar Layer (신규)                                         │
│  ├─ services/ai/                                                 │
│  │   ├─ config.py       ← Feature Flag, Model Routing, Limits   │
│  │   ├─ providers.py    ← 모델 공급자 추상화 + retry/fallback   │
│  │   ├─ schemas.py      ← Pydantic (OrderDraft, CSTriage 등)    │
│  │   ├─ tools/          ← FOMS 데이터 안전 접근 Tool             │
│  │   ├─ chains/         ← LangChain 체인 (copilot, parser 등)   │
│  │   ├─ graphs/         ← LangGraph 워크플로우 정의              │
│  │   ├─ retrieval/      ← RAG 색인 + 검색                       │
│  │   └─ evals/          ← LangSmith 평가 데이터셋               │
│  └─ apps/api/ai/                                                 │
│      └─ routes.py       ← /api/ai/* 엔드포인트 Blueprint         │
│                                                                  │
│  Observability / Governance Layer (신규)                          │
│  ├─ LangSmith traces (모든 LLM 호출 추적)                       │
│  ├─ Feature Flags (기본값 OFF)                                   │
│  ├─ AI Run Log (실행 이력 기록)                                  │
│  ├─ Prompt/Schema Versioning                                     │
│  ├─ PII Redaction Policy                                         │
│  └─ Rollback Switches                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4-3. 핵심 Tool 목록

| Tool | 유형 | 설명 |
|------|:----:|------|
| `get_order_context` | Read | Order.structured_data 조회 |
| `get_order_events` | Read | OrderEvent 최근 N건 조회 |
| `get_order_tasks` | Read | OrderTask 미완료 건 조회 |
| `get_chat_context` | Read | ChatMessage 최근 요약 |
| `get_policy_context` | Read | 정책 JSON/코드 검색 |
| `save_structured_draft` | Draft | AI 초안을 Draft 상태로 저장 |
| `record_ai_suggestion` | Log | AI 추천/적용 결과를 OrderEvent에 기록 |

### 4-4. API 엔드포인트

| 엔드포인트 | 메서드 | 단계 |
|-----------|:------:|:----:|
| `/api/ai/order/<id>/copilot` | GET | 단기 |
| `/api/ai/parse-order` | POST | 단기 |
| `/api/ai/classify-cs` | POST | 단기 |
| `/api/ai/briefing/daily` | GET | 중기 |
| `/api/ai/policy/ask` | POST | 중기 |
| `/api/ai/chat/<id>/summary` | GET | 중기 |

---

## 5. 단기 계획 (0~6주)

단기 목표는 3가지다.

1. 운영에 무해한 AI 기반 공사
2. 즉시 체감 가능한 Read-Only 기능 출시
3. Low-Confidence 입력 보조의 안전한 MVP 확보

### Track A. 기반 공사 (Week 0)

**작업:**
1. `requirements.txt`에 AI 의존성 추가 (`langchain-core`, `langchain-openai`, `langgraph`, `pydantic`)
2. `services/ai/` 및 `apps/api/ai/` 스켈레톤 생성
3. Provider Key 등록 (`OPENAI_API_KEY` 등)
4. LangSmith tracing 연동 (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`)
5. Feature Flag 기본값 `off` (`data/erp_policy.json`에 `"ai": {"enabled": false}`)
6. Prompt/Schema version 기록 구조 마련
7. `AI_RUN_LOG` 로깅 구조 설계
8. PII Redaction 규칙 정리 (이름→이니셜, 연락처→마스킹)
9. Timeout, Retry, Recursion Limit 기본값 확정

**성공 조건:**
1. AI 기능 비활성화 상태에서 운영 영향 없음
2. Tracing, Timeout, Retry, Redaction 작동
3. 장애 시 Feature Flag로 즉시 OFF 가능
4. 실패해도 기존 기능이 그대로 동작

### Track B. Read-Only Order Copilot (Week 1~2)

```
[사용자] "이 주문 분석해줘" 클릭
    │
    ▼
[Flask] GET /api/ai/order/<id>/copilot
    │
    ▼
[services/ai/tools/]
    ├─ get_order_context(order_id)       ← Order.structured_data
    ├─ get_order_events(order_id)        ← OrderEvent 최근 10건
    ├─ get_order_tasks(order_id)         ← OrderTask 미완료 건
    └─ get_chat_context(order_id)        ← ChatMessage 최근 요약
    │
    ▼
[services/ai/chains/copilot.py]
    LangChain: System Prompt + Context → LLM → 구조화 응답
    │
    ▼
[응답 JSON]
{
  "summary": "실측 완료, 도면 대기, 고객은 오전 방문 선호",
  "next_actions": ["도면팀 확인 필요", "48시간 SLA 확인"],
  "risks": ["최근 3일 이벤트 없음, 일정 확정 전 고객 요청 2건"],
  "sources": ["structured_data.workflow.stage", "OrderEvent#234"]
}
```

**제약:**
1. DB Write 완전 차단 (조회 Tool만 등록)
2. 응답 시간 목표: < 3초
3. Source citation 없는 응답은 노출 금지
4. 모든 호출은 LangSmith에 자동 추적

**KPI:**
| 지표 | 측정 방법 | 목표 |
|------|----------|:----:|
| Copilot 응답 시간 | API 응답 latency | < 3초 |
| Source citation 포함률 | citation 필드 채움 비율 | 95%+ |
| 재질문율 | 1회 질문으로 충분한 비율 | 80%+ |
| 오류 제보 건수 | 사용자 피드백 | 주당 < 3건 |

### Track C. Hybrid Order Parser (Week 3~4)

```
[원본 텍스트 입력]
    │
    ▼
[erp_order_text_parser.py] 기존 Regex 파싱
    │
    ├─ confidence == "high" (score ≥ 4) → 기존 결과 그대로 반환
    │
    └─ confidence == "low"/"medium" (score < 4)
        │
        ▼
    [Validator] 누락/불일치 필드 판정
        │
        ▼
    [services/ai/chains/parser.py] 필요한 필드만 LLM 보충
        │
        ├─ Pydantic Schema(OrderDraftSchema) 기반 LLM 추출
        ├─ 기존 Regex 결과와 병합 (Regex 우선, LLM 보충)
        └─ 최종 Confidence 재계산
        │
        ▼
    [기존 결과 vs AI 보충 결과] 비교 UI
        │
        ├─ [AI 결과 적용] → 기존 PUT API + OrderEvent 기록
        └─ [무시] → 기존 결과 유지
```

**제약:**
1. 기존 Parser 폐기 금지
2. AI 출력 즉시 저장 금지
3. 비교 UI 없는 자동 반영 금지
4. Low Confidence 결과는 항상 수동 검토
5. AI 보충 필드는 UI에서 명확히 표시

**KPI:**
| 지표 | 측정 방법 | 목표 |
|------|----------|:----:|
| Low-confidence 개선율 | AI 보충 전후 confidence 비교 | 40%+ 감소 |
| 필드 정확도 | 샘플 50건 대비 검증 | 93%+ |
| AI Draft 승인율 | 사용자가 "적용" 누른 비율 | 70%+ |
| 잘못된 보충 비율 | 오류 필드 / 전체 보충 필드 | < 10% |

### Track D. CS/AS Draft Triage (Week 5~6)

```
CS 접수 텍스트 → LLM 분류 → 팀 라우팅 + 긴급도 설정
                    │
                    ├─ "시공 불량" → 시공팀 + HIGH + 사진 요청
                    ├─ "제품 하자" → 생산팀 + MEDIUM + 교체 프로세스
                    ├─ "치수 오류" → 도면팀 + HIGH + 실측 재확인
                    ├─ "일정 변경" → 출고팀 + LOW + 캘린더 업데이트
                    └─ "기타 문의" → CS팀 + LOW + 담당자 배정
```

**제약:**
1. 자동 접수 금지 — Draft recommendation만 제공
2. 책임 판정(누구 잘못인지) 자동화 절대 금지
3. 최종 owner/team/state 반영은 사람 승인 필수

**KPI:**
| 지표 | 측정 방법 | 목표 |
|------|----------|:----:|
| Triage 시간 감소 | 접수~분류 완료 시간 비교 | 50%+ 감소 |
| 재분류 비율 | 사람이 분류를 바꾼 비율 | < 20% |
| 초안 활용률 | AI 초안을 참고한 비율 | 70%+ |

---

## 6. 중기 계획 (7~14주)

중기 목표는 3가지다.

1. 채팅과 정책 검색을 AI가 읽기 좋게 연결
2. LangGraph를 배치와 승인형 흐름에 붙일 준비 완료
3. 운영 브리핑과 사내 지식 질의의 반복 비용 절감

### Track E. Chat Summary + Commitment Extraction (Week 7~8)

| 기능 | 설명 | 활용처 |
|------|------|--------|
| 1페이지 요약 | 긴 채팅 → 핵심 3~5줄 | 아침 브리핑, 인수인계 |
| 미결 사항 추출 | "아직 답변 안 한 고객 질문 2건" | 업무 누락 방지 |
| 약속/일정 추출 | "4월 2일까지 타일 샘플 보내기로 함" | 일정 변경 Draft 제안 |
| 감성 분석 | 고객 불만 / 만족 / 중립 | CS 긴급도 판단 보조 |

**KPI:** 인수인계 준비 시간 감소, 누락 약속사항 발견율

### Track F. Policy/Rule RAG Assistant (Week 9~10)

**RAG 색인 대상:**
- `data/erp_policy.json`, `data/erp_quest_templates.json`, `data/erp_task_templates.json`
- `services/erp_policy.py` (주석 포함)
- `docs/context/DECISIONS.md`, incident 및 운영 가이드

**답변 형식 예시:**
> "정책 엔진(`erp_policy.py:248~261`)에 따르면, 도면 SLA는 **48시간(영업일 기준)**입니다."

**제약:**
1. 내부 직원용만 허용
2. 출처 없는 답변 금지
3. 정책 우회 답변 금지
4. 정책 결정권은 여전히 기존 엔진에 있음

**KPI:** 정책 질문 응답 시간 감소, citation 포함률, 운영팀 정답률 평가

### Track G. Daily Risk Briefing (Week 11~12)

```
[RQ 스케줄러] 매일 03:00 AM
    │
    ▼
[LangGraph: Daily Risk Scanner]
    ├─ Node 1: 도면 SLA 48시간 초과 위험 주문 조회
    ├─ Node 2: 시공 D-3 임박 + 미확정 주문 조회
    ├─ Node 3: 긴급 플래그 + owner_team 미지정 주문 조회
    ├─ Node 4: 각 건의 ChatMessage 맥락 수집 (왜 지연되는지)
    ├─ Node 5: LLM이 근본 원인 추론 + 우선순위 정렬
    └─ Node 6: 브리핑 문서 생성 → Notification 발송
```

**출력 예시:**
```
[오늘의 리스크 브리핑 — 3건]
🔴 주문#1234: 도면 SLA 4시간 남음. "고객 타일 색상 미결정"이 원인.
   → 추천: CS팀에서 색상 확정 요청 콜
🟡 주문#5678: 시공 D-2 임박. 생산 출고 미완료.
   → 추천: 생산팀 출고 상태 확인 필요
🟡 주문#9012: 긴급 발주인데 owner_team 미지정.
   → 추천: CS팀 즉시 담당자 배정
```

**KPI:** 브리핑 유용성 평가, 위험 주문 선제 대응률, Graph 실패율/재개 성공률

### Track H. Address/Excel Assist (Week 13~14)

1. 비표준 주소 LLM 정규화 제안 → Kakao API fallback 유지
2. 엑셀 비표준 컬럼명 자동 매핑 제안
3. 전화번호, 날짜, 금액 형식 정합성 점검

**제약:** 자동 적용 금지. 사용자가 승인해야 반영.

---

## 7. 장기 계획 (15주~9개월)

장기 목표는 `설명 가능한 승인형 오케스트레이션`이다. 자동화가 아니라 통제 가능한 반자동화가 목표다.

### Track I. Stage Guardian Graph

```
[사용자: "DRAWING → CONFIRM 변경" 요청]
    │
    ▼
[LangGraph: Stage Guardian]
    ├─ Node 1: 현재 structured_data 조회
    ├─ Node 2: 퀘스트 승인 여부 검사 (check_quest_approvals_complete)
    ├─ Node 3: 필수 일정/파일/담당자 존재 검사
    │
    ├─ (모두 통과) → Node 4: 이유 설명 + 변경 실행 제안
    │                          └─ interrupt() → 사람 최종 승인 대기
    │                                              └─ 승인 시 기존 PUT API 호출
    │
    └─ (미통과)  → Node 4: 부족한 조건 설명
                           └─ "도면팀 승인이 아직 없습니다."
```

**핵심 원칙:**
1. AI가 stage를 최종 결정하지 않는다
2. AI는 검증과 승인 흐름만 orchestration 한다
3. 기존 전이 규칙은 정책 엔진이 계속 계산한다

### Track J. Controlled Write Actions (쓰기 거버넌스)

1. Tool Execution Node 전에 `interrupt_before=["tool_execution"]` 세팅
2. LLM이 호출하기로 결정한 수정 Tool + 페이로드를 UI에 표시
3. 사용자가 **[승인 / 거절 / 파라미터 수정]** 3분기 중 선택
4. 승인 후 기존 FOMS API를 통한 쓰기만 실행
5. 모든 실행은 감사 로그 필수

**적용 후보:** AI 파싱 초안 반영, Task Draft 생성, 알림 초안 발송, Stage Transition 실행

### Track K. 멀티 에이전트 주문서 분해

```
[전체 주문서 텍스트]
    │
    ▼
[Orchestrator Node] → 공간/품목 단위로 하위 작업 분할
    │
    ├─ [Worker 1: 방1 붙박이장]  ──┐
    ├─ [Worker 2: 주방 싱크대]    ──┤── 병렬 실행
    └─ [Worker 3: 거실장]        ──┘
    │
    ▼
[Evaluator Node] 누락/충돌 필드 재검증
    │
    ▼
[Reducer Node] 결과 통합 → structured_data Draft 생성
    │
    ▼
[HITL Node] interrupt() → 사용자 최종 확인 후 DB 저장 승인
```

### Track L. Schedule Optimization Research (연구 트랙)

| 에이전트 | 역할 | 입력 | 출력 |
|----------|------|------|------|
| 수요분석 Agent | 주간 주문량 예측 | 과거 주문 패턴 | 예상 건수/지역 분포 |
| 지리최적화 Agent | 방문 경로 최적화 | 주소 좌표 목록 | 최적 방문 순서 + 이동시간 |
| 자원배정 Agent | 인력/장비 매칭 | 팀원 가용성, 스킬 | 인원별 일정 배정안 |
| 조율 Agent | 충돌 해소 | 3개 Agent 결과 | 최종 일정표 (Draft) |

**원칙:** 연구 트랙으로만 시작. 운영 투입 전 별도 성능 검증 필수. 초기에는 추천만 제공.

### Track M. Multimodal Quality Assistant / 기타

1. 실측 사진 묶음 요약, 도면 기반 품질 체크 보조 (자동 판정 금지)
2. 자동 고객 커뮤니케이션 초안, 대시보드 자연어 질의
3. 외부 웹 정보 참고형 보조 (출처와 조회 시각 기록 필수)

---

## 8. 비용·리스크·ROI

### 8-1. 비용 추정 원칙

비용은 계획 단계에서 보수적으로 봐야 한다. 아래 모든 수치는 **가정치(Estimate)**이며 확정 예산이 아니다. 정확한 금액은 파일럿 실제 사용량으로 재산정한다.

| 단계 | 월 비용 (가정) | 비고 |
|------|:----------:|------|
| 단기 | $10~30 | Read-Only, Parser fallback 중심 |
| 중기 | $40~135 | 브리핑, 요약, RAG 추가 |
| 장기 | $70~305 | Graph, Multimodal, Optimization 포함 |

### 8-2. ROI 예상 (월 100건 기준, 가정치)

> 아래 절감률은 타 시스템 사례 기반 **추정치**이며, FOMS 실제 운영 후 재산정이 필수다.

| 영역 | 현재 수동 시간 | AI 적용 후 | 절감률 (추정) | 월 절감 (추정) |
|------|:---------:|:--------:|:-----:|:----------:|
| 주문 텍스트 파서 | 3~5분/건 | 5초 | ~95% | ~6시간 |
| 주소 정규화 실패 | 10~15분/건 | 1분 | ~90% | ~3시간 |
| CS 분류 + 라우팅 | 5~10분/건 | 즉시 | ~95% | ~2시간 |
| 채팅 요약 | 10~15분/건 | 30초 | ~95% | ~3시간 |
| 주문 상태 파악 | 2~3분/건 | 즉시 | ~95% | ~4시간 |
| 일정 배정 | 30~60분/일 | 5분 | ~85% | ~15시간 |
| **합계** | | | | **~33시간/월 (추정)** |

### 8-3. 주요 리스크

| 리스크 | 심각도 | 대응 방안 |
|--------|:------:|-----------|
| LLM 환각(Hallucination) | 🔴 | Structured Output + Validator + HITL 승인 |
| 개인정보 유출 | 🔴 | PII Redaction, 최소 정보만 전송 |
| 과도한 자동화 욕심 | 🔴 | Read → Draft → Write 단계 고정 |
| 규칙 엔진과 AI 제안 충돌 | 🟡 | 정책 엔진 결정이 항상 우선 |
| LLM 비용 급등 | 🟡 | GPT-4o-mini 우선, 캐싱, Usage Quota |
| 모델 지연으로 UX 악화 | 🟡 | RQ 비동기 + 기존 로직 Fallback |
| 운영팀 신뢰 상실 | 🟡 | Source citation 필수, 오류율 투명 공개 |
| Prompt/Schema 버전 미관리 | 🟡 | 버전 기록 없으면 운영 반영 금지 |
| API 키 노출 | 🔴 | 환경변수만 사용, 코드 하드코딩 금지 |

---

## 9. KPI 및 성공 기준

### 9-1. 단기 KPI (0~6주)

| KPI | 측정 방법 | 목표 |
|-----|----------|:----:|
| Copilot 응답 시간 | API latency | < 3초 |
| Copilot source citation 포함률 | citation 필드 비율 | 95%+ |
| Parser low-confidence 개선율 | AI 보충 전후 비교 | 40%+ 감소 |
| Hybrid Parser 정확도 | 샘플 50건 검증 | 93%+ |
| AI Draft 승인율 | "적용" 클릭 비율 | 70%+ |
| CS Triage 시간 감소 | 접수~분류 시간 | 50%+ 감소 |
| Feature Flag OFF 시 회귀 없음 | 기능 비활성화 테스트 | 100% |

### 9-2. 중기 KPI (7~14주)

| KPI | 측정 방법 | 목표 |
|-----|----------|:----:|
| 브리핑 유용성 평가 | 팀장 주관 평가 (5점) | 4.0+ |
| 정책 질의 응답 시간 감소 | 질문~답변 시간 | 70%+ 감소 |
| Policy RAG 정답률 | 30건 샘플 평가 | 85%+ |
| Daily Briefing 활용률 | 열람 비율 | 80%+ |
| Graph 실패율 / 재개 성공률 | 실행 로그 | 실패 <5%, 재개 95%+ |

### 9-3. 장기 KPI (15주~)

| KPI | 측정 방법 | 목표 |
|-----|----------|:----:|
| Stage transition 누락 조건 탐지율 | 가드레일 탐지 건수 | 80%+ |
| 승인형 Write 오탐률 | 잘못된 Write 제안 비율 | < 5% |
| 복합 주문 파싱 누락률 | 멀티에이전트 검증 | 50%+ 감소 |
| 승인형 Write 무사고 비율 | 사고 건수 | 99.5%+ |
| 멀티모달 보조 실무 채택률 | 사용 비율 | 측정 시작 |

---

## 10. 운영 가드레일 (12항목)

| # | 가드레일 | 비고 |
|---|---------|------|
| 1 | 모든 Write는 기존 FOMS 서비스/API 경유 | AI가 직접 SQL 실행 금지 |
| 2 | Feature Flag 기본값은 OFF | 배포 후 수동 활성화 |
| 3 | Prompt/Schema 버전 기록 | 변경 이력 추적 가능 |
| 4 | 모든 Run Trace 기록 (LangSmith) | Input/Output/지연/비용 |
| 5 | 민감정보 Redaction | 이름→이니셜, 연락처→마스킹 |
| 6 | Low Confidence는 자동 적용 금지 | 사람 승인 필수 |
| 7 | 운영 핵심 경로는 Deterministic Fallback 확보 | AI 실패 시 기존 로직 동작 |
| 8 | Graph Recursion Limit + Timeout 필수 | 무한 루프/비용 폭발 방지 |
| 9 | Human Approval 없는 Write 금지 | 모든 쓰기는 승인 후 실행 |
| 10 | 비용 모니터링 + Usage Quota | 월 한도 초과 시 알림 |
| 11 | Historical Dataset 기반 평가 먼저 | 운영 전 과거 샘플 50~100건 품질 검증 |
| 12 | 운영 반영 전 Sandbox/Pilot 필수 | 프로덕션 직배포 금지. pilot → 평가 → 릴리스 |

---

## 11. Sprint 즉시 착수 순서

### Sprint 1 (Week 0~2)
1. AI 의존성 추가 (`requirements.txt`)
2. `services/ai/` 스켈레톤 생성
3. LangSmith, Trace, Feature Flag 준비
4. PII Redaction 규칙 구현
5. **Read-Only Order Copilot API** 구현
6. 주문 상세/ERP Beta UI에 Copilot Panel 추가

### Sprint 2 (Week 3~4)
1. **Hybrid Parser MVP** 구현
2. Validator + Draft Compare UI
3. AI Suggestion Log (`OrderEvent` 연동)
4. Parser Evaluation Dataset 구축 (샘플 50~100건)

### Sprint 3 (Week 5~6)
1. **CS/AS Draft Triage** 구현
2. Timeout, Retry, Fallback 정리
3. Feature Flag 기준 정리
4. **중간 평가 보고** 및 중기 착수 판단

---

## 12. 최종 정리

```
┌──────────────────────────────────────────────────────────────────────┐
│                   FOMS AI 최종 마스터 플랜 v3 (Final3)                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [단기 0~6주] Track A~D                                              │
│  ├─ ✅ 기반 공사 (LangChain + LangSmith + Feature Flag + Redaction) │
│  ├─ ✅ Read-Only Order Copilot (요약/분석, citation 필수)           │
│  ├─ ✅ Hybrid Parser (Validator + LLM 보충, 비교 UI)               │
│  └─ ✅ CS/AS Draft Triage (분류 + 팀 추천, 자동 접수 금지)         │
│                                                                      │
│  [중기 7~14주] Track E~H                                             │
│  ├─ ✅ 채팅 요약 + 약속사항 추출 + 감성 분석                        │
│  ├─ ✅ Policy/Rule RAG (사내 정책 검색, citation 필수)              │
│  ├─ ✅ Daily Risk Briefing (LangGraph 야간 배치)                    │
│  └─ ✅ Address/Excel Assist (자동 적용 금지)                        │
│                                                                      │
│  [장기 15주~9개월] Track I~M                                         │
│  ├─ ✅ Stage Guardian Graph (단계 전환 가드레일)                    │
│  ├─ ✅ Controlled Write Actions (approve/reject/edit 3분기)         │
│  ├─ ✅ 멀티 에이전트 주문서 분해 (Evaluator 포함)                   │
│  ├─ ✅ 일정 최적화 (연구 트랙으로만 시작)                           │
│  └─ ✅ Multimodal Quality / 고객 커뮤니케이션 초안                  │
│                                                                      │
│  [절대 금지 10항목]                                                  │
│  └─ ❌ ERP 룰 LLM 대체 / 무승인 DB 변경 / 금액 AI 계산            │
│     ❌ 근거 없는 추천 확정값 노출 / trace 없이 운영 반영            │
│                                                                      │
│  [거버넌스]                                                          │
│  ├─ 운영 가드레일 12항목 (pilot/sandbox 필수 포함)                  │
│  ├─ KPI 3단계 (단기/중기/장기, 목표 수치 포함)                      │
│  └─ Write 거버넌스: approve / reject / edit 3분기                   │
│                                                                      │
│  핵심 설계 사상:                                                     │
│  "FOMS의 정책, 승인, 상태, 금액은 끝까지                            │
│   결정론적 백엔드가 지키고, AI는 그 위에서                           │
│   읽기, 해석, 요약, 초안 생성, 승인형 오케스트레이션을               │
│   담당하는 방향으로만 진화한다."                                     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

> 이 문서를 FOMS AI 도입의 `final3` 단일 마스터 계획서로 사용한다.
