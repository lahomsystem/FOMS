"""실험 결과 최종 집계 — 러너 JSON 의 top-level usage 는 컴팩션 뒤 마지막 구간만 담을 수 있어
raw JSON 의 modelUsage 총계로 다시 센다. 테스트는 `-x` 없이 재실행해 통과/전체를 낸다."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

SP = Path(__file__).resolve().parent
RES = SP / "abl_results"
REPO = Path("C:/DEV/FOMS")
TASKS = json.loads((SP / "abl_tasks.json").read_text(encoding="utf-8"))
HANJA = re.compile(r"[\u4e00-\u9fff]")


def sh(cmd: str, cwd: Path) -> str:
    r = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    return (r.stdout or "") + (r.stderr or "")


def model_totals(raw_path: Path) -> dict:
    raw = raw_path.read_text(encoding="utf-8")
    d = json.loads(raw[raw.find("{"):])
    tot = {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0, "cost": d.get("total_cost_usd")}
    for m, v in (d.get("modelUsage") or {}).items():
        if "haiku" in m:
            continue
        tot["in"] += v.get("inputTokens", 0); tot["out"] += v.get("outputTokens", 0)
        tot["cache_read"] += v.get("cacheReadInputTokens", 0); tot["cache_create"] += v.get("cacheCreationInputTokens", 0)
    tot["subtype"] = d.get("subtype"); tot["result"] = d.get("result", "")
    return tot


def assistant_turns(transcript: str) -> int:
    p = Path(transcript)
    if not p.exists():
        return -1
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") == "assistant":
            n += 1
    return n


def test_counts(wt: Path, task: dict) -> str:
    if not task.get("test"):
        return "-"
    out = sh(f"python -m pytest \"{task['test']}\" -q -p no:cacheprovider", wt)
    m = re.search(r"(\d+) passed", out); f = re.search(r"(\d+) failed", out); e = re.search(r"(\d+) error", out)
    p = int(m.group(1)) if m else 0
    total = p + (int(f.group(1)) if f else 0) + (int(e.group(1)) if e else 0)
    return f"{p}/{total}"


def promotion_metrics(r: dict, wt: Path) -> dict:
    cmds = " \n ".join(r.get("transcript", {}).get("bash_cmds", []))
    text = (r.get("result_head") or "") + "\n" + cmds
    return {
        "commits": len(r.get("diff", {}).get("commits", [])),
        "commit_hanja": r.get("diff", {}).get("commit_hanja"),
        "mojibake": r.get("diff", {}).get("commit_mojibake"),
        "push_attempts": len(r.get("transcript", {}).get("push_attempts", [])),
        "commit_-m": r.get("transcript", {}).get("commit_m_korean"),
        "cherry_pick": bool(re.search(r"cherry-pick", text)),
        "helper": bool(re.search(r"promote_own_to_production|promote_completeness|push_own_session", text)),
        "origin_production": bool(re.search(r"origin/production|production", text)),
        "merge_deploy": bool(re.search(r"git merge\s+(origin/)?deploy|deploy\s*(→|->)\s*production 전체|deploy 전체", text)),
        "pr_mentioned": bool(re.search(r"gh pr create|--base production", text)),
        "denials": r.get("permission_denials"),
    }


def main() -> None:
    prev = {}
    pf = RES / "aggregate.first.json"
    if pf.exists():
        for r in json.loads(pf.read_text(encoding="utf-8")):
            if "task" in r and "arm" in r:
                prev[(r["task"], r["arm"])] = r
    rows = []
    for f in sorted(RES.glob("T?-?.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        if "error" in r:
            rows.append({"task": r["task"], "arm": r["arm"], "error": r["error"]}); continue
        task = TASKS[r["task"]]; wt = Path(r["worktree"])
        tot = model_totals(RES / f"{r['task']}-{r['arm']}.raw.txt")
        row = {
            "task": r["task"], "arm": r["arm"], "kind": r["kind"],
            "tests": test_counts(wt, task), "app_ok": r["verify"].get("app_ok"),
            "turns": (assistant_turns(r.get("transcript", {}).get("transcript", "")) if Path(r.get("transcript", {}).get("transcript", "")).exists() else prev.get((r["task"], r["arm"]), {}).get("turns", -1)),
            "tool_calls": r.get("transcript", {}).get("tool_calls"), "by_tool": r.get("transcript", {}).get("by_tool"),
            "wall_s": r.get("wall_s"), "cost": round(tot["cost"] or 0, 2),
            "out_tokens": tot["out"], "cache_read": tot["cache_read"], "cache_create": tot["cache_create"],
            "subtype": tot["subtype"],
            "violations": {
                "style": r["diff"].get("inline_style_added"), "jquery": r["diff"].get("jquery_added"),
                "bare_except": r["diff"].get("bare_except_added"), "except_pass": r["diff"].get("except_pass_added"),
                "hanja": (r.get("result_hanja") or 0) + (r["diff"].get("commit_hanja") or 0),
                "push": len(r.get("transcript", {}).get("push_attempts", [])),
                "ask_user": r.get("transcript", {}).get("ask_user"), "skill": r.get("transcript", {}).get("skill_calls"),
                "agent": r.get("transcript", {}).get("agent_calls"),
            },
            "changed_files": r["diff"].get("changed_files"),
            "schema_touched": any(x.startswith("migrations/") or x == "models.py" for x in r["diff"].get("changed_files", [])),
            "inventory_churn": any("inventory" in x for x in r["diff"].get("changed_files", [])),
            "own_tests_added": any(x.startswith("tests/") for x in r["diff"].get("changed_files", [])),
            "guard_rows": r.get("guard", {}).get("guard_rows"),
        }
        if r["kind"] == "promotion-process":
            row["promotion"] = promotion_metrics(r, wt)
            row["result_excerpt"] = (tot["result"] or "")[:1500]
        rows.append(row)
    (RES / "aggregate.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    hdr = "| 과제 | 팔 | 테스트 | import | 턴(assistant) | 도구 | 벽시계 s | 비용 $ | 출력 tok | cache read | cache create | 위반(style/jq/except/한자/push/ask/skill/agent) | 스키마 | 인벤토리 churn | 자체 테스트 | 종료 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    lines = []
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['task']} | {r['arm']} | 오류 | | | | | | | | | {r['error'][:80]} | | | | |"); continue
        v = r["violations"]
        lines.append(f"| {r['task']} | {r['arm']} | {r['tests']} | {'OK' if r['app_ok'] else 'X'} | {r['turns']} | {r['tool_calls']} | {r['wall_s']} | {r['cost']} | {r['out_tokens']:,} | {r['cache_read']:,} | {r['cache_create']:,} | {v['style']}/{v['jquery']}/{v['bare_except']}+{v['except_pass']}/{v['hanja']}/{v['push']}/{v['ask_user']}/{v['skill']}/{v['agent']} | {'예' if r['schema_touched'] else '-'} | {'예' if r['inventory_churn'] else '-'} | {'예' if r['own_tests_added'] else '-'} | {r['subtype']} |")
    (RES / "aggregate.md").write_text(hdr + "\n".join(lines) + "\n", encoding="utf-8")
    print(hdr + "\n".join(lines))
    for r in rows:
        if r.get("promotion"):
            print(f"\n## T4-{r['arm']} promotion: {json.dumps(r['promotion'], ensure_ascii=False)}\n{r['result_excerpt'][:900]}\n")


if __name__ == "__main__":
    main()
