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
All runs: claude-haiku-4.5, temperature 0, run by the team on the official run_judge.py/score.py.
Hold-out = dev cases whose source_id is NOT among the sources of the 9 default example pairs
(criterion 1: 77/226 cases, 80 replies; surprise criterion: 31/73 cases, 46 replies). Baseline on the same hold-out:
criterion 1 = 0.754 (from baseline_dev_verdicts.csv), surprise = 0.586 (fresh baseline run, ho2_base.csv).

| run | config | criterion 1 combined | surprise combined | surprise original-pass |
|---|---|---|---|---|
| V1 | audit -> verify -> tie-break, 9 example pairs | not run | 0.401 | 0.419 |
| V2 | + "incomplete but accurate is not a violation" guard, verify decides | not run | 0.350 | 0.452 |
| V3-B | example-anchored verify + holistic must agree, 9 examples | not run | 0.376 | 0.548 |
| V3-C | holistic one-word call, 9 examples | not run | 0.376 | 0.548 |
| V3-A | audit + anchored verify, 9 examples | not run | 0.350 | 0.419 |
| B, 0 examples | | 0.686 (catch 0.543, keep 1.000, condition_removal 0.000) | 0.244 | 0.677 |
| **C, 0 examples (FROZEN)** | one call, sanitised whitelist prompt + number evidence | **0.789** (catch 0.678, keep 0.943, kappa 0.714) | **0.596** (catch 0.550, keep 0.650) | 0.677 |
| A, 0 examples | audit + verify | 0.816 (catch 0.689, keep 1.000, kappa 0.771) | 0.241 | 0.581 |
| OR(C, A) offline from CSVs | fail if either fails | 0.872 (orig pass 0.948) | 0.528 | 0.581 |

Findings
- Few-shot pairs with "what differs" notes made haiku hunt for differences: good originals failed (orig pass 0.42-0.55).
- The structured claim audit (A) is the best single method on criterion 1 (keep 1.000) but on the surprise criterion
  ("errors in both directions") it flags omissions in good replies as errors and misses edits.
- Decision rule (stated in advance): keep a change only if it beats the baseline on BOTH criteria -> C, 0 examples.
- Caveat: hold-outs are small (80 / 46 replies, 4 / 5 sources), so differences of ~0.01 are within noise.

## Consistency
Two runs of the frozen judge on the surprise hold-out: same verdict 1.000, kappa 1.000 (n=46 replies).
Re-runs of eval1/eval2 at 15:31-15:33 reproduced 0.789 / 0.596 exactly.
