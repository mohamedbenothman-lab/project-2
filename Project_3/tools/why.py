"""Short summary of the latest signal log: python tools/why.py [TAG]  (from Project_3/)"""
import glob, json, os, sys
files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "logs", f"signals_{sys.argv[1] if len(sys.argv) > 1 else '*'}.jsonl")), key=os.path.getmtime)
recs = [json.loads(l) for l in open(files[-1], encoding="utf-8")]
n = len(recs); fails = [r for r in recs if r["verdict"] == "fail"]
print(f"{os.path.basename(files[-1])}: {n} replies, {len(fails)} fail, avg calls {sum(r['calls'] for r in recs)/n:.2f}, "
      f"audit unparsed {sum(not r['audit_parsed'] for r in recs)}, flagged {sum(r['n_flagged']>0 for r in recs)}")
for r in fails[:12]:
    for a in r["audit"]:
        if a.get("violates_criterion"):
            print("-", str(a.get("status")), "|", str(a.get("reason"))[:110])
