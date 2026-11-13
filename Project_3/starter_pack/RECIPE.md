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
Kept: one holistic call on the sanitised whitelist prompt with number evidence, no few-shot examples, temperature 0,
1 call per reply.

## Step 4. Verify
Hold-out = dev cases from sources not used for examples (grouped by source_id).

| Criterion 1 (hold-out, 77 cases) | combined | catch | keep |
|---|---|---|---|
| Baseline | 0.754 | 0.656 | 0.887 |
| Ours | 0.789 | 0.678 | 0.943 |

## Surprise criterion
Nothing changed but the inputs (`--criterion surprise/CRITERION.md --dev surprise/dev_pairs.jsonl`).

| Surprise (hold-out, 31 cases) | combined | catch | keep |
|---|---|---|---|
| Baseline | 0.586 | 0.533 | 0.650 |
| Ours, recipe unchanged | 0.596 | 0.550 | 0.650 |

## What did not work
- Few-shot pairs: haiku became over-strict and failed good originals (orig pass fell to 0.42-0.55).
- The claim audit won on criterion 1 (0.816, keep 1.000) but lost badly on the surprise criterion (0.241): with
  "errors in both directions" it treats omissions as errors. Its OR with the holistic call reached 0.872 on
  criterion 1 but 0.528 on the surprise one. Next step would be calibrating the audit's omission threshold from the
  examples' original replies at start-up.
- Lesson: a rule written into a prompt is a hypothesis; every one we added had to be measured on both criteria.
