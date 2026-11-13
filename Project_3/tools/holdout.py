"""Write the pairs whose source_id is NOT used by the judge's selected examples (honest hold-out score).
Usage: python3 tools/holdout.py PAIRS DEV OUT   (run from Project_3/)"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "starter_pack"))
import final_judge as fj
pairs, dev, out = sys.argv[1:4]
P = [json.loads(l) for l in open(pairs, encoding="utf-8") if l.strip()]
D = [json.loads(l) for l in open(dev, encoding="utf-8") if l.strip()]
used = {p["source_id"] for p in fj._select_examples(D)}
keep = [p for p in P if p["source_id"] not in used]
with open(out, "w", encoding="utf-8") as f:
    for p in keep: f.write(json.dumps(p, ensure_ascii=False) + "\n")
print(f"{len(keep)}/{len(P)} cases kept; example sources excluded: {sorted(used)}")
