"""회사 지식 의미 찾기 벡터 백필 — 관리자 스크립트(사장님 D114). **기본은 모의 실행**(넣을 항목 수 · 어림 돈만 — 부르지 않음 · 돈 0).

- 근원(``--source``): ``brain_item``(회사 지식 항목 — 반영 · 정체 유형 · 보기 범위 ``price`` · ``admin`` 밖 항목의 이름 · 다른 이름 ·
  위 낱말 · 글 앞부분) · ``chatbot_question``(물어보기 가린 질문) · ``cs_case``(상담 사례 — 가린 손님 질문 + 가린 직원 답, 사례
  기억과 같은 가림 검사에 하나라도 걸리면 건너뜀 · 설정 ``cs_case_embeddings_enabled`` 가 켜져 있어야 함, 처음 끔). 처음 값은
  ``brain_item`` + ``chatbot_question``. 모든 근원에서 개인정보 꼴 · 계좌 같은 번호가 보이는 글은 보내지 않는다.
- ``--apply`` 를 줘야 Voyage AI 를 부르고 표에 넣는다. 그때도 설정 '의미 찾기' 켬 · 열쇠 env ``VOYAGE_API_KEY`` · 의미 찾기 하루 돈
  상한 · 벡터 표(pgvector)가 모두 있어야 한다(아니면 까닭 코드만 내고 끝).
- **켜기 전 사장님 확인**: 개인정보 처리방침 국외 이전 항목에 Voyage AI(상담 글 포함)를 올린 뒤에(원장 · 설계서 사장님 확인
  목록). 상담 초안의 비슷한 사례 고르기는 이 벡터를 아직 쓰지 않는다(따로 평가 뒤).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/brain_embed_backfill.py
    python scripts/maintenance/brain_embed_backfill.py --apply --limit 3000
    python scripts/maintenance/brain_embed_backfill.py --source cs_case            # 상담 사례 — 모의 실행
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)

from tools.cron.brain_embed import run  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="회사 지식 의미 찾기 벡터 백필(기본: 모의 실행 — 돈 0)")
    parser.add_argument("--apply", action="store_true", help="실제로 부르고 넣는다(돈이 든다)")
    parser.add_argument("--limit", type=int, default=5000, help="근원마다 한 번에 다룰 줄 상한")
    parser.add_argument("--source", action="append", choices=("brain_item", "chatbot_question", "cs_case"),
                        help="근원(여러 번 줄 수 있음 — 처음 값 brain_item + chatbot_question)")
    args = parser.parse_args(argv)
    summary = run(apply=args.apply, limit=max(1, args.limit), sources=tuple(args.source) if args.source else None)
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if "error" in summary else 0


if __name__ == "__main__":
    sys.exit(main())
