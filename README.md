# Team Tougypt · Project 3: Judge the Judge (SIXT Hackathon 2026)

A reusable recipe for an LLM judge of customer-support replies on `claude-haiku-4.5`. It judges one reply at a time,
has nothing criterion-specific in code, and runs unchanged on the surprise criterion.

**Start here: [`Project_3/SUBMISSION.md`](Project_3/SUBMISSION.md)** (approach, results, how to run).

| | Original criterion | Surprise criterion |
|---|---|---|
| Starting judge (hold-out) | 0.754 | 0.586 |
| **Our frozen judge (hold-out)** | **0.835** | **0.621** |

Run-to-run consistency: 1.000 (46 replies, two runs).

| What | Where |
|---|---|
| Frozen judge (code freeze 16:00) | [`Project_3/starter_pack/final_judge.py`](Project_3/starter_pack/final_judge.py) |
| Recipe (one page) | [`Project_3/starter_pack/RECIPE.md`](Project_3/starter_pack/RECIPE.md) |
| Every run and decision | [`Project_3/starter_pack/EXPERIMENTS.md`](Project_3/starter_pack/EXPERIMENTS.md) |
| Hidden-test results | `Project_3/submission/criterion{1,2}_run{1,2}.csv` |
| Slides | [`Project_3/submission/slides.pdf`](Project_3/submission/slides.pdf) |
| Helper scripts | [`Project_3/tools/`](Project_3/tools/README.md) |
| Original project brief and starter kit | [`Project_3/README.md`](Project_3/README.md), `Project_3/starter_pack/` |
