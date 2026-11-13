"""Majority of three verdict CSVs: python combine3.py A.csv B.csv C.csv OUT.csv"""
import csv, sys
rd = lambda p: {r["case_id"]: r for r in csv.DictReader(open(p, encoding="utf-8"))}
X = [rd(p) for p in sys.argv[1:4]]
maj = lambda vs: "fail" if vs.count("fail") >= 2 else "pass"
with open(sys.argv[4], "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(["case_id", "original", "edited"])
    for cid in sorted(X[0]):
        w.writerow([cid, maj([x[cid]["original"] for x in X]), maj([x[cid]["edited"] for x in X])])
