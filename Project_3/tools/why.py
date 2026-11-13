"""Summary of the newest signal log: python tools/why.py   (from Project_3/)"""
import glob, json, os
files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "logs", "signals_*.jsonl")), key=os.path.getmtime)
recs = [json.loads(l) for l in open(files[-1], encoding="utf-8")]
n = len(recs); fails = [r for r in recs if r["verdict"] == "fail"]
print(f"{os.path.basename(files[-1])}: {n} replies, {len(fails)} fail, avg calls {sum(r['calls'] for r in recs)/n:.2f}, "
      f"flagged {sum(r.get('n_flagged', 0) > 0 for r in recs)}, verify-confirmed {sum(r.get('verify') is True for r in recs)}")
for r in fails[:10]:
    for a in r.get("audit", []):
        if a.get("violates_criterion"):
            print("-", a.get("status"), "|", str(a.get("reason"))[:110])
