"""Cross-platform driver (Windows/macOS/Linux, stdlib only). Run from Project_3/:

    python tools/run.py smoke                 # creates/loads .env, one tiny call, latency + model
    python tools/run.py eval1                 # criterion 1: hold-out score, ours vs baseline
    python tools/run.py eval2                 # surprise criterion: baseline vs ours on hold-out
    python tools/run.py final C1.jsonl C2.jsonl   # 16:00: 4 runs -> ../submission/criterion{1,2}_run{1,2}.csv
Options: WORKERS env var (default 8).
"""
from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Project_3
SP = os.path.join(ROOT, "starter_pack")
ENV = os.path.join(ROOT, ".env")
PY = sys.executable
WORKERS = os.environ.get("WORKERS", "8")


def load_env() -> None:
    vals = {}
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    if not vals.get("JUDGE_LLM_BASE_URL") or not vals.get("JUDGE_LLM_API_KEY"):
        print("Creating .env (git-ignored).")
        vals["JUDGE_LLM_BASE_URL"] = input("JUDGE_LLM_BASE_URL: ").strip().rstrip("/")
        vals["JUDGE_LLM_API_KEY"] = getpass.getpass("JUDGE_LLM_API_KEY (hidden): ").strip()
        vals["JUDGE_LLM_MODEL"] = "claude-haiku-4.5"
        save_env(vals)
    vals.setdefault("JUDGE_LLM_MODEL", "claude-haiku-4.5")
    os.environ.update(vals)
    os.environ["PYTHONIOENCODING"] = "utf-8"
    assert os.environ["JUDGE_LLM_MODEL"] == "claude-haiku-4.5", "JUDGE_LLM_MODEL must be claude-haiku-4.5"


def save_env(vals: dict) -> None:
    with open(ENV, "w", encoding="utf-8", newline="\n") as f:
        for k in ("JUDGE_LLM_BASE_URL", "JUDGE_LLM_API_KEY", "JUDGE_LLM_MODEL"):
            f.write(f"{k}={vals.get(k, '')}\n")


def _ping(base: str) -> tuple[int, str, float]:
    payload = {"model": os.environ["JUDGE_LLM_MODEL"], "messages": [{"role": "user", "content": "Say OK"}],
               "temperature": 0, "max_tokens": 5}
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(payload).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {os.environ['JUDGE_LLM_API_KEY']}",
                                          "Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read().decode())
        return 200, f"model={body.get('model')} answer={body['choices'][0]['message']['content']!r}", time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200].decode(errors="replace"), time.time() - t


def smoke() -> None:
    base = os.environ["JUDGE_LLM_BASE_URL"].rstrip("/")
    code, info, dt = _ping(base)
    if code == 404 and not base.endswith("/v1"):
        code2, info2, dt2 = _ping(base + "/v1")
        if code2 == 200:
            base, code, info, dt = base + "/v1", code2, info2, dt2
            os.environ["JUDGE_LLM_BASE_URL"] = base
            save_env(dict(os.environ))
            print("Base URL needed /v1; .env updated.")
    print(f"HTTP {code} in {dt:.2f}s  {info}")
    if code != 200:
        sys.exit(1)


def sh(*args: str) -> None:
    print(">", " ".join(os.path.basename(a) if a == PY else a for a in args), flush=True)
    subprocess.run(list(args), cwd=SP, check=True)


def holdout(pairs: str, dev: str, out: str) -> None:
    sh(PY, os.path.join(ROOT, "tools", "holdout.py"), pairs, dev, out)


def run_judge(judge: str, pairs: str, crit: str, dev: str | None, out: str, tag: str) -> list[str]:
    os.environ["JUDGE_RUN_TAG"] = tag
    cmd = [PY, "run_judge.py", "--judge", judge, "--pairs", pairs, "--criterion", crit, "--policy", "policy.md",
           "--workers", WORKERS, "--out", out]
    if dev:
        cmd += ["--dev", dev]
    return cmd


def eval1() -> None:
    holdout("dev_pairs.jsonl", "dev_pairs.jsonl", "ho1.jsonl")
    t = time.time()
    sh(*run_judge("final_judge.py", "ho1.jsonl", "JUDGE1_CRITERION.md", "dev_pairs.jsonl", "ho1.csv", "eval1"))
    print(f"wall time {time.time() - t:.0f}s")
    sh(PY, "score.py", "ho1.csv", "ho1.jsonl", "--baseline", "baseline_dev_verdicts.csv")
    sh(PY, "diagnose.py", "ho1.csv", "ho1.jsonl")


def eval2() -> None:
    holdout(os.path.join("surprise", "dev_pairs.jsonl"), os.path.join("surprise", "dev_pairs.jsonl"), "ho2.jsonl")
    crit = os.path.join("surprise", "CRITERION.md")
    if not os.path.exists(os.path.join(SP, "ho2_base.csv")):
        sh(*run_judge("baseline_judge.py", "ho2.jsonl", crit, None, "ho2_base.csv", "eval2_base"))
    t = time.time()
    sh(*run_judge("final_judge.py", "ho2.jsonl", crit, os.path.join("surprise", "dev_pairs.jsonl"), "ho2.csv", "eval2"))
    print(f"wall time {time.time() - t:.0f}s")
    print("--- baseline on surprise hold-out"); sh(PY, "score.py", "ho2_base.csv", "ho2.jsonl")
    print("--- ours on surprise hold-out"); sh(PY, "score.py", "ho2.csv", "ho2.jsonl", "--baseline", "ho2_base.csv")


def final(c1: str, c2: str) -> None:
    c1, c2 = os.path.abspath(c1), os.path.abspath(c2)
    sub = os.path.join(os.path.dirname(ROOT), "submission")
    os.makedirs(sub, exist_ok=True)
    jobs = []
    for run in (1, 2):
        for n, pairs, crit, dev in ((1, c1, "JUDGE1_CRITERION.md", "dev_pairs.jsonl"),
                                    (2, c2, os.path.join("surprise", "CRITERION.md"),
                                     os.path.join("surprise", "dev_pairs.jsonl"))):
            out = os.path.join(sub, f"criterion{n}_run{run}.csv")
            env = dict(os.environ, JUDGE_RUN_TAG=f"final_c{n}_run{run}")
            cmd = [PY, "run_judge.py", "--judge", "final_judge.py", "--pairs", pairs, "--criterion", crit,
                   "--policy", "policy.md", "--dev", dev, "--workers", os.environ.get("FINAL_WORKERS", "5"), "--out", out]
            jobs.append((out, subprocess.Popen(cmd, cwd=SP, env=env)))
    t = time.time()
    bad = [out for out, p in jobs if p.wait() != 0]
    print(f"wall time {time.time() - t:.0f}s")
    for out, _ in jobs:
        print(out, "OK" if out not in bad else "FAILED")
    if bad:
        sys.exit("some runs failed: rerun them one by one")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    load_env()
    cmd = sys.argv[1]
    if cmd == "smoke":
        smoke()
    elif cmd == "eval1":
        eval1()
    elif cmd == "eval2":
        eval2()
    elif cmd == "final" and len(sys.argv) == 4:
        final(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
