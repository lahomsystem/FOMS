"""평가 질문 묶음 — **질문마다 기대 항목 키를 단 실행되는 시험**(설계서 11절 · 7.7 · 사장님 D105 · 조사 '규격 비교' 다음 7).

질문 꼴(JSON 한 줄씩 또는 목록 — :func:`parse_questions`)::

    {"id": "q01", "q": "질문 글", "expect": ["항목 키", ...], "layer": "common", "role": "ADMIN", "team": null}

- ``expect`` 가 비면 '지식에 없는 질문'(답은 '모름 + 누구에게'여야 한다). 키가 여럿이면 하나라도 근거에 있으면 맞힘.
- ``role`` · ``team`` 은 묻는 사람(보기 범위 시험 — 처음 값 ADMIN). 정답은 만든 이가 아닌 사람(사장님 · 팀장 — 11절 F11-5)이 단다.
- 저장소에는 **합성 묶음만** 둔다(``tests/support/brain_chat_eval_set.py`` — 30 + 10). 실제 묶음은 학습 폴더(저장소 밖)에 두고
  ``scripts/maintenance/brain_chat_eval.py`` 로 돌린다. 관문 ④(평가 묶음 재시험 — :mod:`.ai_gates`)가 쓰는 묶음은 ADMIN 이 그
  스크립트로 설정 :data:`EVAL_KEY` 에 넣은 것이다(질문 글 · 키뿐 — 손님 정보 없음).

:func:`score_run` 은 답 결과들을 판 1 완료 기준으로 센다: 답할 질문 맞힘 80% 이상 · 근거 없는 답 0 · 지식에 없는 질문 모두 '모름'.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from foms.services.brain.constants import KEY_RE, LAYERS

EVAL_KEY = "brain_eval_set"
PASS_RATE = 0.8
MAX_QUESTIONS = 500


@dataclass(frozen=True)
class EvalQuestion:
    """평가 질문 하나."""

    qid: str
    q: str
    expect: tuple[str, ...] = ()
    layer: Optional[str] = None
    role: str = "ADMIN"
    team: Optional[str] = None

    @property
    def answerable(self) -> bool:
        """지식에 답이 있는 질문인가."""
        return bool(self.expect)


class EvalSetError(ValueError):
    """평가 묶음 꼴이 틀렸다 — 줄 번호 · 칸 이름만 싣는다."""


def _one(raw: Mapping[str, Any], line: int) -> EvalQuestion:
    """한 줄 검사."""
    q, expect = raw.get("q"), raw.get("expect", [])
    if not isinstance(q, str) or not q.strip() or len(q) > 500:
        raise EvalSetError(f"{line}: q")
    if not isinstance(expect, list) or not all(isinstance(k, str) and KEY_RE.fullmatch(k) for k in expect):
        raise EvalSetError(f"{line}: expect")
    layer = raw.get("layer")
    if layer is not None and layer not in LAYERS:
        raise EvalSetError(f"{line}: layer")
    role = str(raw.get("role") or "ADMIN").upper()
    if role not in ("ADMIN", "MANAGER", "STAFF", "VIEWER"):
        raise EvalSetError(f"{line}: role")
    team = raw.get("team")
    return EvalQuestion(qid=str(raw.get("id") or f"q{line:03d}")[:40], q=q.strip(), expect=tuple(expect), layer=layer,
                        role=role, team=str(team).upper() if team else None)


def parse_questions(data: Any) -> list[EvalQuestion]:
    """목록(dict) · JSON 글(목록 또는 한 줄에 하나) → 질문들. 틀리면 :class:`EvalSetError`."""
    if isinstance(data, str):
        text = data.strip()
        rows = json.loads(text) if text.startswith("[") else [json.loads(x) for x in text.splitlines() if x.strip()]
    elif isinstance(data, Mapping):
        rows = data.get("questions") or []
    else:
        rows = list(data or [])
    if len(rows) > MAX_QUESTIONS:
        raise EvalSetError("too_many")
    out = [_one(row if isinstance(row, Mapping) else {}, i + 1) for i, row in enumerate(rows)]
    ids = [q.qid for q in out]
    if len(set(ids)) != len(ids):
        raise EvalSetError("duplicate_id")
    return out


def stored_questions(session: Any) -> list[EvalQuestion]:
    """설정 :data:`EVAL_KEY` 에 넣은 묶음(없거나 틀리면 빈 목록 — 관문 ④는 '준비 안 됨')."""
    from models import SystemSetting

    row = session.get(SystemSetting, EVAL_KEY)
    if row is None or not row.setting_value:
        return []
    try:
        return parse_questions(row.setting_value)
    except (EvalSetError, ValueError):
        return []


def store_questions(session: Any, questions: Iterable[EvalQuestion]) -> int:
    """묶음을 설정에 넣는다(통째로 바꿈 · 커밋은 부르는 쪽). 넣은 수."""
    from sqlalchemy.orm.attributes import flag_modified

    from models import SystemSetting

    rows = [{"id": q.qid, "q": q.q, "expect": list(q.expect), "layer": q.layer, "role": q.role, "team": q.team}
            for q in questions]
    row = session.get(SystemSetting, EVAL_KEY)
    if row is None:
        row = SystemSetting(setting_key=EVAL_KEY, setting_value={"questions": rows},
                            description="회사 지식 평가 질문 묶음(질문 · 기대 항목 키) — 설계서 11절 · D105")
        session.add(row)
    else:
        row.setting_value = {"questions": rows}
        flag_modified(row, "setting_value")
        row.version = int(row.version or 1) + 1
    session.flush()
    return len(rows)


@dataclass
class EvalScore:
    """한 번 돌린 점수."""

    answerable: int = 0
    hit: int = 0
    unanswerable: int = 0
    unknown_ok: int = 0
    unsupported: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        """답할 질문 맞힘 비율."""
        return self.hit / self.answerable if self.answerable else 1.0

    @property
    def passed(self) -> bool:
        """판 1 완료 기준 — 맞힘 80% 이상 · 근거 없는 답 0 · 지식에 없는 질문 모두 '모름'."""
        return self.hit_rate >= PASS_RATE and self.unsupported == 0 and self.unknown_ok == self.unanswerable

    def as_dict(self) -> dict[str, Any]:
        """보고용(질문 id 만 — 질문 글 없음)."""
        return {"answerable": self.answerable, "hit": self.hit, "hit_rate": round(self.hit_rate, 3),
                "unanswerable": self.unanswerable, "unknown_ok": self.unknown_ok, "unsupported": self.unsupported,
                "passed": self.passed, "misses": self.misses}


def judge_one(question: EvalQuestion, result: Mapping[str, Any]) -> tuple[bool, bool]:
    """답 결과 하나 → (맞음, 근거 없는 답). 결과 꼴: ``{"unknown": bool, "evidence": [키 ...]}``."""
    evidence = [e for e in (result.get("evidence") or []) if isinstance(e, str)]
    unknown = bool(result.get("unknown"))
    unsupported = not unknown and not evidence
    if not question.answerable:
        return unknown, unsupported
    return (not unknown and bool(set(evidence) & set(question.expect))), unsupported


def score_run(pairs: Iterable[tuple[EvalQuestion, Mapping[str, Any]]]) -> EvalScore:
    """(질문, 답 결과)들 → 점수."""
    score = EvalScore()
    for question, result in pairs:
        ok, unsupported = judge_one(question, result)
        score.unsupported += int(unsupported)
        if question.answerable:
            score.answerable += 1
            score.hit += int(ok)
        else:
            score.unanswerable += 1
            score.unknown_ok += int(ok)
        if not ok:
            score.misses.append(question.qid)
    return score


def load_file(path: str) -> list[EvalQuestion]:
    """파일(JSON 목록 · 한 줄에 하나 · ``{"questions": [...]}``) → 질문들."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read().strip()
    if text.startswith("{") and '"questions"' in text[:200]:
        return parse_questions(json.loads(text))
    return parse_questions(text)


def run_eval(questions: Iterable[EvalQuestion], answer: Any) -> EvalScore:
    """질문마다 ``answer(question) -> {"unknown", "evidence"}`` 를 불러 점수를 센다(답 길은 부르는 쪽이 고른다)."""
    return score_run((q, answer(q)) for q in questions)
