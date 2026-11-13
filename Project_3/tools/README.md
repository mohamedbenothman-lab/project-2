# tools (stdlib only, run from `Project_3/`)

| file | what |
|---|---|
| `run.py` | `smoke` (creates `.env`, one test call), `eval1` / `eval2` (hold-out score vs baseline), `final C1 C2` (the 4 submission CSVs) |
| `final.bat` | Windows one-click for the 16:00 runs: runs `run.py final`, checks the 4 CSVs, commits and pushes them |
| `holdout.py` | writes the grouped hold-out: dev cases whose `source_id` is not among the default example pairs' sources |
| `combine.py`, `combine3.py` | offline OR / AND / majority of verdict CSVs (no LLM), used for the ablations in `EXPERIMENTS.md` |
| `why.py` | summary of the newest `logs/signals_*.jsonl` (verdicts, calls per reply, flagged statements) |

Ablations: every variant in `EXPERIMENTS.md` (A, B, C, D, M) is implemented in `starter_pack/final_judge.py`; the
frozen one is selected by the `VARIANT` constant (`"M"`). To reproduce an ablation, copy the file and change the constant.
