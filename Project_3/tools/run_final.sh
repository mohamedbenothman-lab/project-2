#!/usr/bin/env bash
# 16:00 procedure. Usage: bash tools/run_final.sh HIDDEN_C1.jsonl HIDDEN_C2.jsonl   (from Project_3/)
set -euo pipefail
cd "$(dirname "$0")/.."; set -a; . ./.env; set +a
test "$JUDGE_LLM_MODEL" = "claude-haiku-4.5"
mkdir -p ../submission; cd starter_pack
for run in 1 2; do
  JUDGE_RUN_TAG=c1_run$run python3 run_judge.py --judge final_judge.py --pairs "$1" --criterion JUDGE1_CRITERION.md \
    --policy policy.md --dev dev_pairs.jsonl --workers "${WORKERS:-8}" --out ../../submission/criterion1_run$run.csv &
  JUDGE_RUN_TAG=c2_run$run python3 run_judge.py --judge final_judge.py --pairs "$2" --criterion surprise/CRITERION.md \
    --policy policy.md --dev surprise/dev_pairs.jsonl --workers "${WORKERS:-8}" --out ../../submission/criterion2_run$run.csv &
done
wait; wc -l ../../submission/*.csv
