# Our recipe for building an LLM judge

## Step 1. Diagnose
`diagnose.py` on the baseline: it misses 93% of dropped conditions and 50% of certainty shifts ("usually" -> "always"),
and false-rejects 13-27% of harmless edits (reorder, filler, translation, opener). Cost drivers: dropped conditions,
certainty shifts, false alarms on originals. Since catch only counts when the ORIGINAL passes, false rejects on good
replies are as expensive as misses.

## Step 2. Split: rules vs. LLM
Code (no LLM): an input whitelist (criterion, policy, customer message, ONE reply; never the lang tag, ids or twin),
sanitising (tags inside inputs neutralised, length capped), a language-neutral number extractor whose output is
evidence in the prompt (numbers in the reply that are / are not in the policy), a per-reply call budget (max 3,
enforced), lenient parsing, a JSONL signal log for offline re-tuning, and a deterministic decision.
No rule hard-fails a reply: every candidate rule (e.g. "a number not in the policy") also fires on legitimate replies.

## Step 3. Improve the LLM part
Tried (all logged in EXPERIMENTS.md): a claim audit (each commitment vs. verbatim policy quote, yes/no deviation
flags), an independent verify call, an "incomplete but accurate is not an error" precision guard, example-anchored
calibration, a holistic agreement gate, few-shot pairs, and an OR of audit and holistic.
Kept: a majority vote of three independent views of the same whitelisted input, no few-shot examples, temperature 0:
C = one-word holistic verdict, D = short commitment-by-commitment check ending in VERDICT, A = claim audit with a
precision guard (flag only if the quote is really in the reply, a concrete deviation is named and the statement is
"wrong or misleading", not merely incomplete). C and D run first; the audit is called only when they disagree, so the
vote costs 2 calls per reply, 3 at most. Each view alone loses on one criterion; their majority wins on both.

## Step 4. Verify
Hold-out = dev cases from sources not used for examples (grouped by source_id).

| Criterion 1 (hold-out, 77 cases) | combined | catch | keep |
|---|---|---|---|
| Baseline | 0.754 | 0.656 | 0.887 |
| Ours | 0.835 | 0.789 | 0.887 |

## Surprise criterion
Nothing changed but the inputs (`--criterion surprise/CRITERION.md --dev surprise/dev_pairs.jsonl`).

| Surprise (hold-out, 31 cases) | combined | catch | keep |
|---|---|---|---|
| Baseline | 0.586 | 0.533 | 0.650 |
| Ours, recipe unchanged | 0.621 | – | – |

## What did not work
- Any single strategy: holistic one-word (0.789 / 0.596), reasoning (0.716 / 0.674), claim audit (0.816 / 0.241).
- Few-shot pairs: haiku became over-strict and failed good originals (orig pass fell to 0.42-0.55).
- The claim audit won on criterion 1 (0.816, keep 1.000) but lost badly on the surprise criterion (0.241): with
  "errors in both directions" it treats omissions as errors. Its OR with the holistic call reached 0.872 on
  criterion 1 but 0.528 on the surprise one. Next step would be calibrating the audit's omission threshold from the
  examples' original replies at start-up.
- Lesson: a rule written into a prompt is a hypothesis; every one we added had to be measured on both criteria.
