# Submission: Project 3 – Judge the Judge

## Authors
**Team name:** <TEAM NAME>

**Project:** Project 3: Judge the Judge – a recipe for building LLM judges you can trust

## Problem and approach
Customer-support judges let meaning-changing edits through (the starting judge catches 7% of dropped conditions) and
sometimes reject harmless rewrites. We built a judge that looks at one reply at a time and runs unchanged on any
criterion. Code builds the prompt from a fixed whitelist of inputs: criterion, policy, customer message and the ONE
reply. It never sees the lang tag, ids or the twin reply. Code also neutralises markup inside the inputs, adds
language-neutral number evidence (numbers in the reply that are / are not in the policy), enforces a per-reply call
budget and makes the final decision deterministically at temperature 0.
We compared several LLM strategies on a grouped hold-out (cases from source replies not used as examples) and kept
the only one that beat the baseline on BOTH criteria. Full recipe: `starter_pack/RECIPE.md`; every run:
`starter_pack/EXPERIMENTS.md`.

Assumption: the construction labels are correct (every original is a good reply).

## Models and why
| Model | Open-weight or closed | Where it runs | Main metric(s) | Cost and time per item | Chosen? |
| --- | --- | --- | --- | --- | --- |
| claude-haiku-4.5 | closed | SIXT OpenAI-compatible endpoint | combined, kappa, consistency | 1 call per reply, ~0.1 s per reply wall time at 8 workers | yes (required) |

Settings: temperature 0, one-word answer (max 8 tokens), no few-shot examples, max 3 calls per reply (enforced).

## Results
Hold-out (grouped by source_id). Baseline = starting judge on the same cases.

| | Criterion 1 combined | catch | keep | kappa | Surprise combined | catch | keep |
|---|---|---|---|---|---|---|---|
| Baseline | 0.754 | 0.656 | 0.887 | 0.652 | 0.586 | 0.533 | 0.650 |
| **Ours (frozen)** | **0.789** | 0.678 | 0.943 | 0.714 | **0.596** | 0.550 | 0.650 |
| Claim audit (ablation) | 0.816 | 0.689 | 1.000 | 0.771 | 0.241 | 0.150 | 0.608 |
| OR(ours, audit) (ablation) | 0.872 | – | – | – | 0.528 | – | – |

Hidden test runs (two runs per criterion): `submission/criterion{1,2}_run{1,2}.csv`.
Run-to-run consistency on the hidden runs: <FILL IN from `score.py run1.csv pairs --repeat run2.csv` if labels are
released, else the share of identical verdicts>.

What did not work and limits: few-shot pairs made haiku over-strict, so good originals failed. The structured claim
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
