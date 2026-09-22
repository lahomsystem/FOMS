"""ablation v2 2단계 실험 러너 — 팔 3개(A 현행 / B 최소 / C 무규칙) × 과제 4개.

지시서 §7 을 그대로 구현한다. 각 (과제, 팔) 마다 격리 워크트리 + 격리 CLAUDE_CONFIG_DIR 에서
`claude -p` 를 1회 돌리고 JSON 사용량·트랜스크립트·diff·테스트로 §7.4 지표를 뽑는다.
결과는 스크래치패드 `abl_results/<T>-<arm>.json` 과 `abl_results/ledger.md` 에 즉시 기록한다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("C:/DEV/FOMS")
SP = Path(__file__).resolve().parent
RESULTS = SP / "abl_results"
DRAFTS = REPO / "docs/plans/2026-09-09-harness-ablation-v2-drafts"
HOME_CLAUDE = Path(os.path.expanduser("~")) / ".claude"
MODEL = "claude-fable-5-1[1m]"
MAX_TURNS = 60
MAX_BUDGET = 15.0
RUN_TIMEOUT = 45 * 60
HANJA = re.compile(r"[\u4e00-\u9fff]")

DENY_EXTRA = ["Bash(git push*)", "Bash(gh pr create*)", "Bash(gh pr merge*)", "Bash(git remote set-url*)"]


def sh(cmd: str, cwd: Path | str = REPO, timeout: int = 600, env: dict | None = None) -> tuple[int, str]:
    """셸 명령 실행(문자열 결과). cmd.exe 의 `^` 함정을 피하려고 `~1` 표기를 쓴다."""
    r = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def slug_for(path: Path) -> str:
    """Claude Code 프로젝트 슬러그: `C:/tmp/abl-T1-A` → `C--tmp-abl-T1-A`."""
    s = str(path).replace("\\", "/")
    drive, rest = s.split(":/", 1)
    return f"{drive.upper()}--" + rest.replace("/", "-")


def make_cfg(arm: str) -> Path | None:
    """팔 B/C 용 격리 CLAUDE_CONFIG_DIR 을 만든다. A 는 None(실제 ~/.claude)."""
    if arm == "A":
        return None
    cfg = Path(f"C:/tmp/abl-cfg-{arm}")
    cfg.mkdir(parents=True, exist_ok=True)  # 기존 트랜스크립트(projects/) 보존
    shutil.copy(HOME_CLAUDE / ".credentials.json", cfg / ".credentials.json")
    settings = {
        "permissions": {"defaultMode": "bypassPermissions"},
        "skipDangerousModePermissionPrompt": True,
        "effortLevel": "xhigh",
        "model": MODEL,
        "enabledPlugins": {"caveman@caveman": False, "ponytail@ponytail": False,
                            "superpowers@claude-plugins-official": False},
    }
    (cfg / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    trust = {"projects": {str(REPO).replace("\\", "/"): {"hasTrustDialogAccepted": True}}}
    for t in ("T1", "T2", "T3", "T4"):
        trust["projects"][f"C:/tmp/abl-{t}-{arm}"] = {"hasTrustDialogAccepted": True}
    (cfg / ".claude.json").write_text(json.dumps(trust, indent=2), encoding="utf-8")
    if arm == "B":
        (cfg / "CLAUDE.md").write_text(_read(DRAFTS / "CLAUDE.global.md.proposed"), encoding="utf-8")
    return cfg


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def prepare_worktree(task_id: str, task: dict, arm: str) -> Path:
    """과제 base 커밋의 격리 워크트리를 만들고 팔별 규칙 파일·훅을 적용한다."""
    wt = Path(f"C:/tmp/abl-{task_id}-{arm}")
    sh(f"git worktree remove --force {wt}")
    base = task["base"]
    rc, out = sh(f"git worktree add -q --detach {wt} {base}")
    if rc:
        raise RuntimeError(f"worktree add 실패: {out[:300]}")
    # push 물리 차단: 워크트리 전용 hooksPath(pre-push 가 항상 실패)
    hooks = Path("C:/tmp/abl-hooks")
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-push").write_text("#!/bin/sh\necho 'ABL: push disabled' >&2\nexit 1\n", encoding="utf-8")
    sh("git config extensions.worktreeConfig true", cwd=wt)
    sh(f"git config --worktree core.hooksPath {hooks.as_posix()}", cwd=wt)
    settings_path = wt / ".claude" / "settings.json"
    settings = json.loads(_read(settings_path))
    if arm == "A":
        pass
    elif arm == "B":
        (wt / "CLAUDE.md").write_text(_read(DRAFTS / "CLAUDE.md.proposed"), encoding="utf-8")
        settings = json.loads(_read(DRAFTS / "settings.json.proposed"))
        settings.pop("_comment", None)
    elif arm == "C":
        (wt / "CLAUDE.md").unlink()
        settings = {"env": settings.get("env", {}), "permissions": {"deny": list(settings["permissions"]["deny"])}}
    settings.setdefault("permissions", {}).setdefault("deny", [])
    for d in DENY_EXTRA:
        if d not in settings["permissions"]["deny"]:
            settings["permissions"]["deny"].append(d)
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    # 팔 A: 실제 메모리를 워크트리 슬러그 아래로 복사(현행 재현)
    if arm == "A":
        mem_dst = HOME_CLAUDE / "projects" / slug_for(wt) / "memory"
        if mem_dst.exists():
            shutil.rmtree(mem_dst)
        shutil.copytree(HOME_CLAUDE / "projects" / "c--DEV-FOMS" / "memory", mem_dst)
    return wt


def run_claude(wt: Path, prompt: str, cfg: Path | None, model: str = MODEL, max_turns: int = MAX_TURNS) -> tuple[dict, str, float]:
    """claude -p 1회. (결과 JSON, 원문, 소요초)."""
    env = dict(os.environ)
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(k, None)
    if cfg:
        env["CLAUDE_CONFIG_DIR"] = str(cfg)
    pfile = wt / ".abl_prompt.txt"
    pfile.write_text(prompt, encoding="utf-8")
    cmd = (f"claude -p \"$(cat .abl_prompt.txt)\" --output-format json --max-turns {max_turns} "
           f"--max-budget-usd {MAX_BUDGET} --model \"{model}\" --effort xhigh < /dev/null")
    t = time.time()
    r = subprocess.run(["bash", "-lc", cmd], cwd=str(wt), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT, env=env)
    dur = time.time() - t
    raw = (r.stdout or "").strip()
    pfile.unlink(missing_ok=True)
    start = raw.find("{")
    data = {}
    if start >= 0:
        try:
            data = json.loads(raw[start:])
        except json.JSONDecodeError:
            data = {"_parse_error": raw[:500]}
    if r.stderr:
        data["_stderr_tail"] = r.stderr[-800:]
    return data, raw, dur


def transcript_stats(cfg: Path | None, wt: Path, session_id: str) -> dict:
    """트랜스크립트 jsonl 에서 도구 호출·Bash 명령·Skill·AskUserQuestion 을 센다."""
    base = (cfg or HOME_CLAUDE) / "projects" / slug_for(wt)
    f = base / f"{session_id}.jsonl"
    out = {"transcript": str(f), "found": f.exists(), "tool_calls": 0, "by_tool": {}, "bash_cmds": [],
           "skill_calls": 0, "ask_user": 0, "agent_calls": 0, "push_attempts": [], "commit_m_korean": 0}
    if not f.exists():
        return out
    for line in _read(f).splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name", "?")
            out["tool_calls"] += 1
            out["by_tool"][name] = out["by_tool"].get(name, 0) + 1
            inp = block.get("input") or {}
            if name == "Skill":
                out["skill_calls"] += 1
            elif name == "AskUserQuestion":
                out["ask_user"] += 1
            elif name == "Agent":
                out["agent_calls"] += 1
            elif name == "Bash":
                cmd = str(inp.get("command", ""))
                out["bash_cmds"].append(cmd[:200])
                if re.search(r"git\s+push|gh\s+pr\s+(create|merge)", cmd):
                    out["push_attempts"].append(cmd[:200])
                if re.search(r"git\s+commit[^\n]*-m\s*[\"'][^\"']*[가-힣]", cmd):
                    out["commit_m_korean"] += 1
    return out


def diff_stats(wt: Path, base: str) -> dict:
    """워크트리 변경분(미커밋 + base 이후 커밋)에서 규칙 위반을 센다."""
    _, added_uncommitted = sh("git diff -U0 -- . ':!CLAUDE.md' ':!.claude/settings.json'", cwd=wt)
    _, added_committed = sh(f"git log {base}..HEAD -p -U0 --format=", cwd=wt)
    added = "\n".join(l for l in (added_uncommitted + added_committed).splitlines() if l.startswith("+") and not l.startswith("+++"))
    _, commits = sh(f"git log {base}..HEAD --format=%h%x09%s", cwd=wt)
    _, bodies = sh(f"git log {base}..HEAD --format=%B", cwd=wt)
    _, status = sh("git status --porcelain", cwd=wt)
    return {
        "commits": [c for c in commits.splitlines() if c.strip()],
        "commit_hanja": len(HANJA.findall(bodies)),
        "commit_mojibake": bool(re.search(r"[\ufffd]|ì|ë|í", bodies)),
        "inline_style_added": len(re.findall(r'style="', added)),
        "jquery_added": len(re.findall(r"\$\(", added)),
        "bare_except_added": len(re.findall(r"^\+\s*except\s*:", added, re.M)),
        "except_pass_added": len(re.findall(r"^\+\s*except[^\n]*:\s*pass\s*$", added, re.M)),
        "changed_files": [l[3:] for l in status.splitlines() if l.strip() and l[3:] not in ("CLAUDE.md", ".claude/settings.json")],
        "merge_in_log": "Merge" in commits,
    }


def verify(wt: Path, task: dict) -> dict:
    """실제 수정 커밋의 테스트를 복사해 실행 + import app."""
    out = {}
    if task.get("test"):
        test = task["test"]
        (wt / test).parent.mkdir(parents=True, exist_ok=True)
        rc, content = sh(f"git show {task['fix_sha']}:{test}")
        (wt / test).write_text(content, encoding="utf-8")
        rc, o = sh(f"python -m pytest \"{test}\" -q -x -p no:cacheprovider", cwd=wt, timeout=600)
        tail = [l for l in o.strip().splitlines() if l.strip()][-1:]
        out["test_pass"] = (rc == 0)
        out["test_tail"] = tail[0][:160] if tail else ""
    rc, o = sh("python -c \"import app; print('APP_OK')\"", cwd=wt, timeout=300)
    out["app_ok"] = "APP_OK" in o
    return out


def guard_log_rows(wt: Path) -> dict:
    """워크트리 안 가드 로그(훅이 있는 팔만)."""
    f = wt / "docs/harness/logs/SHELL_GUARD_LOG.md"
    if not f.exists():
        return {"guard_rows": 0}
    rows = [l for l in _read(f).splitlines() if l.startswith("| 20")]
    return {"guard_rows": len(rows), "guard_tail": [r[:160] for r in rows[-5:]]}


def run_one(task_id: str, task: dict, arm: str, cfg: Path | None, model: str = MODEL, max_turns: int = MAX_TURNS, suffix: str = "") -> dict:
    """과제 1 × 팔 1 실행 후 지표 dict 반환."""
    wt = prepare_worktree(task_id, task, arm)
    base_sha = sh(f"git rev-parse {task['base']}", cwd=wt)[1].strip()
    data, raw, dur = run_claude(wt, task["prompt"], cfg, model, max_turns)
    (RESULTS / f"{task_id}-{arm}{suffix}.raw.txt").write_text(raw, encoding="utf-8")
    usage = data.get("usage", {}) or {}
    res = {
        "task": task_id, "arm": arm, "kind": task["kind"], "worktree": str(wt), "base_sha": base_sha[:9],
        "session_id": data.get("session_id"), "subtype": data.get("subtype"), "is_error": data.get("is_error"),
        "num_turns": data.get("num_turns"), "duration_ms": data.get("duration_ms"), "wall_s": round(dur),
        "cost_usd": data.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "cache_read": usage.get("cache_read_input_tokens"), "cache_create": usage.get("cache_creation_input_tokens"),
        "result_hanja": len(HANJA.findall(str(data.get("result", "")))),
        "result_head": str(data.get("result", ""))[:600],
        "permission_denials": data.get("permission_denials"),
        "stderr_tail": data.get("_stderr_tail"),
    }
    if data.get("session_id"):
        res["transcript"] = transcript_stats(cfg, wt, data["session_id"])
    res["diff"] = diff_stats(wt, base_sha)
    res["verify"] = verify(wt, task)
    res["guard"] = guard_log_rows(wt)
    return res


def ledger_row(r: dict) -> str:
    t = r.get("transcript", {})
    v = r.get("verify", {})
    d = r.get("diff", {})
    ok = "-" if "test_pass" not in v else ("PASS" if v["test_pass"] else "FAIL")
    return (f"| {r['task']} | {r['arm']} | {ok} | {'OK' if v.get('app_ok') else 'X'} | {r.get('num_turns')} | "
            f"{t.get('tool_calls','-')} | {r.get('input_tokens')}/{r.get('output_tokens')}/{r.get('cache_read')} | "
            f"{r.get('cost_usd')} | {r.get('wall_s')}s | push {len(t.get('push_attempts',[]))} · 한자 {r.get('result_hanja')}+{d.get('commit_hanja')} · "
            f"style {d.get('inline_style_added')} · jq {d.get('jquery_added')} · except {d.get('bare_except_added')}+{d.get('except_pass_added')} · -m한글 {t.get('commit_m_korean')} | "
            f"skill {t.get('skill_calls')} · agent {t.get('agent_calls')} | ask {t.get('ask_user')} | {r.get('subtype')} |")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="T1,T2,T3,T4")
    ap.add_argument("--arms", default="A,B,C")
    ap.add_argument("--keep-worktrees", action="store_true")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-turns", type=int, default=MAX_TURNS)
    ap.add_argument("--suffix", default="")
    args = ap.parse_args(argv)
    tasks = json.loads(_read(SP / "abl_tasks.json"))
    RESULTS.mkdir(exist_ok=True)
    ledger = RESULTS / "ledger.md"
    if not ledger.exists():
        ledger.write_text("| 과제 | 팔 | 테스트 | import | 턴 | 도구호출 | 토큰 in/out/cache | 비용$ | 벽시계 | 규칙 위반 | 스킬·에이전트 | 질문 | 종료 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    cfgs = {arm: make_cfg(arm) for arm in args.arms.split(",")}
    for task_id in args.tasks.split(","):
        for arm in args.arms.split(","):
            out = RESULTS / f"{task_id}-{arm}{args.suffix}.json"
            if out.exists():
                print(f"skip {task_id}-{arm} (있음)"); continue
            print(f"=== run {task_id}-{arm} {time.strftime('%H:%M:%S')}", flush=True)
            try:
                r = run_one(task_id, tasks[task_id], arm, cfgs[arm], args.model, args.max_turns, args.suffix)
            except Exception as e:  # noqa: BLE001 — 실험 러너는 한 실행 실패가 나머지를 막지 않게 기록만 한다
                r = {"task": task_id, "arm": arm, "error": repr(e)[:500]}
            out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
            with ledger.open("a", encoding="utf-8") as fh:
                fh.write(ledger_row(r) + "\n")
            print(ledger_row(r), flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
