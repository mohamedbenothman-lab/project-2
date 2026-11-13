# EXPERIMENTS (every number here comes from a logged run)

## Kit facts (verified by reading the code)
- (a) Runner hands the judge: `judge(question, reply, lang, criterion, policy)`; `prepare(criterion, policy, dev_pairs)` once. Our judge ignores `lang`.
- (b) `run_judge.py --judge FILE --pairs P --criterion C --policy policy.md --out OUT [--dev D] [--workers N] [--isolate]`. Already parallel (ThreadPool, default 5 workers); each distinct (lang, question, reply) judged once, shuffled. No extra wrapper needed.
- (c) Labelled examples at hidden-test time: whatever is passed with `--dev` (criterion 1: `dev_pairs.jsonl`; criterion 2: `surprise/dev_pairs.jsonl`). Hidden cases carry no labels.
- (d) `dev_pairs_fast.jsonl` = 119-case stratified subset of the 226 (3 per edit type x language).
- (e) Original criterion text: `JUDGE1_CRITERION.md`. Surprise: `surprise/CRITERION.md` (policy correctness, errors in BOTH directions).

## Baseline (precomputed, baseline_report.txt): combined 0.697, catch 0.592, keep 0.847
Failure taxonomy (diagnose.py): condition_removal missed 93% (all languages); hedge_removal missed 50%;
false alarms on sentence_reorder 27%, filler 20%, translation 17%, opener 13%. Number/policy-detail errors mostly caught.
=> The judge does not compare each commitment with its policy rule; it misses omitted conditions and certainty shifts.

## Runs
