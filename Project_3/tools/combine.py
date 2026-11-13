"""Combine two verdict CSVs case by case: python combine.py or|and A.csv B.csv OUT.csv (offline, no LLM)."""
import csv, sys
mode, a, b, out = sys.argv[1:5]
def rd(p): return {r["case_id"]: r for r in csv.DictReader(open(p, encoding="utf-8"))}
A, B = rd(a), rd(b)
def f(x, y): return ("fail" if "fail" in (x, y) else "pass") if mode == "or" else ("fail" if x == y == "fail" else "pass")
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["case_id", "original", "edited"])
    for cid in sorted(A):
        w.writerow([cid, f(A[cid]["original"], B[cid]["original"]), f(A[cid]["edited"], B[cid]["edited"])])
