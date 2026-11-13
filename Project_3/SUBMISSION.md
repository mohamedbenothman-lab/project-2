# Submission: Team Tougypt – Project 3: Judge the Judge

## Authors
**Team name:** Tougypt

**Project:** Project 3: Judge the Judge – a recipe for building LLM judges you can trust

## Problem and approach
Customer-support judges let meaning-changing edits through (the starting judge catches 7% of dropped conditions) and
sometimes reject harmless rewrites. We built a judge that looks at one reply at a time and runs unchanged on any
criterion. Code builds the prompt from a fixed whitelist of inputs: criterion, policy, customer message and the ONE
reply. It never sees the lang tag, ids or the twin reply. Code also neutralises markup inside the inputs, adds
language-neutral number evidence (numbers in the reply that are / are not in the policy), enforces a per-reply call
budget and makes the final decision deterministically at temperature 0.
We compared several LLM strategies on a grouped hold-out (cases from source replies not used as examples). Each single
strategy lost on one criterion, so the frozen judge takes a majority vote of three independent views: a one-word
verdict, a short commitment-by-commitment check, and a claim audit with a precision guard. The audit is only called
when the first two disagree. It beats the baseline on BOTH criteria. Full recipe: `starter_pack/RECIPE.md`; every run:
`starter_pack/EXPERIMENTS.md`.

Assumption: the construction labels are correct (every original is a good reply).

## Models and why
| Model | Open-weight or closed | Where it runs | Main metric(s) | Cost and time per item | Chosen? |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4.5 | closed | SIXT OpenAI-compatible endpoint | combined, kappa, consistency | 2 calls per reply (3 when the first two disagree) | yes (required) |

Settings: temperature 0, no few-shot examples, max 3 calls per reply (enforced in code).

## Results
Hold-out (grouped by source_id). Baseline = starting judge on the same cases.

| | Criterion 1 combined | catch | keep | kappa | Surprise combined | catch | keep |
|---|---|---|---|---|---|---|---|
| Baseline | 0.754 | 0.656 | 0.887 | 0.652 | 0.586 | 0.533 | 0.650 |
| **Ours (frozen: majority vote)** | **0.835** | 0.789 | 0.887 | 0.746 | **0.621** | – | – |
| One-word holistic only (ablation) | 0.789 | 0.678 | 0.943 | 0.714 | 0.596 | 0.550 | 0.650 |
| Reasoning only (ablation) | 0.716 | 0.600 | 0.887 | 0.593 | 0.674 | 0.700 | 0.650 |
| Claim audit (ablation) | 0.816 | 0.689 | 1.000 | 0.771 | 0.241 | 0.150 | 0.608 |
| OR(ours, audit) (ablation) | 0.872 | – | – | – | 0.528 | – | – |

Hidden test runs (two runs per criterion): `submission/criterion{1,2}_run{1,2}.csv`.
Run-to-run consistency (two runs, surprise hold-out, `score.py --repeat`): same verdict 1.000, kappa 1.000 (n=46
replies). Hidden test runs: 291 + 311 cases, same verdict in run 1 and run 2 for 100% of cases on both criteria.

What did not work and limits: every single strategy lost on one criterion; few-shot pairs made haiku over-strict, so good originals failed. The structured claim
audit was the best method on criterion 1 but treated omissions as errors under the surprise criterion. The hold-outs
are small (80 and 46 replies, 4–5 sources), so gaps of about 0.01 are within noise.

## How to run
Python 3.11+, stdlib only. Environment variables (names only): `JUDGE_LLM_BASE_URL`, `JUDGE_LLM_API_KEY`,
`JUDGE_LLM_MODEL=claude-haiku-4.5`, stored in `Project_3/.env` (git-ignored).
```
git clone -b project-3 https://github.com/mohamedbenothman-lab/project-2 && cd project-2/Project_3
python tools/run.py smoke          # creates .env interactively, one test call
python tools/run.py eval1          # criterion 1 hold-out vs baseline
python tools/run.py eval2          # surprise criterion hold-out vs baseline
python tools/run.py final <criterion1 cases.jsonl> <criterion2 cases.jsonl>   # 4 submission CSVs
```
Or directly: `python run_judge.py --judge final_judge.py --pairs <cases> --criterion <criterion.md> --policy policy.md
--dev <examples.jsonl> --out <out.csv>` from `starter_pack/`.

## Demo
`submission/slides.pdf`

## Next steps
Calibrate the claim audit's omission threshold at start-up from the example originals (all labelled pass), so the
audit's criterion-1 gain (0.816–0.872) carries over to criteria that count errors in both directions. Validate on
more source replies. SIXT could use the recipe as a release gate for chatbot changes, with the JSONL signal log as an
audit trail.
