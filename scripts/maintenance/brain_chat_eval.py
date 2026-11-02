"""회사 지식 물어보기 평가 묶음 실행기 — 질문마다 기대 항목 키를 단 **실행되는 시험**(설계서 11절 · 7.7 · 사장님 D105).

저장소에는 합성 묶음만 있다(``tests/support/brain_chat_eval_set.py`` — 30 + 10, 시험이 가짜 모델로 돌린다). 실제 묶음(정답은
사장님 · 팀장 — 손님 정보 없음)은 학습 폴더(저장소 밖)에 두고 이 스크립트로 돌린다::

    python scripts/maintenance/brain_chat_eval.py --set C:/Users/USER/foms-cs-learning/<묶음>.jsonl --retrieval-only
    python scripts/maintenance/brain_chat_eval.py --set <묶음>.jsonl              # 두뇌까지(돈 — 챗봇 돈 줄 · 상한 안)
    python scripts/maintenance/brain_chat_eval.py --set <묶음>.jsonl --store --apply   # 관문 ④ 재료로 설정에 넣기

- ``--retrieval-only``: 모델을 부르지 않는다(돈 0) — 기대 항목이 쓸 수 있는 후보에 드는지(찾기 맞힘)와 지식에 없는 질문에 후보가
  없는지만 센다.
- 기본: 답하는 길(:func:`foms.services.brain.chat_answer.answer_masked` — 가림 → 보기 범위 안 찾기 → 두뇌 → 코드 확인)을 그대로 돈다
  (기록 · 사람 상한은 쓰지 않는다). 묻는 사람은 질문의 ``role`` · ``team``(보기 범위 시험).
- 내보내는 것은 점수와 틀린 질문 id 뿐이다(질문 · 답 글 없음). 판 1 완료 기준(맞힘 80% · 근거 없는 답 0 · 지식에 없는 질문 모두
  '모름')을 못 넘으면 exit 2.
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)

EXIT_OK, EXIT_FAILED = 0, 2


def answer_fn(session, *, retrieval_only: bool, client=None):
    """질문 → {unknown, evidence} — 가림을 먼저(가림 검사에 걸리면 '모름')."""
    from foms.services.brain.chat_answer import ChatError, answer_masked
    from foms.services.brain.chat_retrieve import retrieve
    from foms.services.brain.chat_settings import read_chat_settings
    from foms.services.brain.scope import Viewer
    from foms.services.cs_agent.masking import leak_counts, mask
    from foms.services.datetime_kst import now_kst

    cfg = read_chat_settings(session)

    def answer(question):
        masked = mask(question.q)
        if any(leak_counts(masked).values()):
            return {"unknown": True, "evidence": []}
        viewer = Viewer(0, question.role, question.team or "", True)
        now = now_kst()
        if retrieval_only:
            found = retrieve(session, viewer, masked, today=now.date())
            keys = [c.key for c in found.usable]
            return {"unknown": not keys, "evidence": keys}
        try:
            verified, _retrieval, _model = answer_masked(session, viewer, masked, cfg=cfg, now=now, client=client)
        except ChatError as exc:
            return {"unknown": True, "evidence": [], "error": exc.code}
        return {"unknown": verified.unknown, "evidence": verified.evidence}

    return answer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="회사 지식 물어보기 평가 묶음 실행")
    parser.add_argument("--set", required=True, help="평가 질문 파일(JSON 목록 · 한 줄에 하나)")
    parser.add_argument("--retrieval-only", action="store_true", help="모델 없이 찾기만(돈 0)")
    parser.add_argument("--store", action="store_true", help="관문 ④ 재료로 설정에 넣기(--apply 와 같이)")
    parser.add_argument("--apply", action="store_true", help="--store 를 실제로 쓴다")
    args = parser.parse_args(argv)

    from app import app
    from db import db_session
    from foms.services.brain.eval_set import load_file, run_eval, store_questions

    questions = load_file(args.set)
    with app.app_context():
        try:
            if args.store:
                count = store_questions(db_session, questions)
                if args.apply:
                    db_session.commit()
                else:
                    db_session.rollback()
                print(json.dumps({"stored": count, "applied": bool(args.apply)}, ensure_ascii=False))
                return EXIT_OK
            score = run_eval(questions, answer_fn(db_session, retrieval_only=args.retrieval_only))
            db_session.rollback()
        finally:
            db_session.remove()
    print(json.dumps({"mode": "retrieval" if args.retrieval_only else "answer", **score.as_dict()}, ensure_ascii=False))
    return EXIT_OK if score.passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
