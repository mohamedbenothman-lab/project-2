# 1-minute talk script (one line per slide)

1. **Title.** "We built a recipe for LLM judges that has to work on a criterion it has never seen. Same code, only the
   inputs change. On held-out cases it beats the starting judge on both criteria, and two runs agree 100%."
2. **Diagnose.** "The starting judge misses 93% of dropped conditions and half of the 'usually becomes always' edits, and
   it rejects good replies. The key insight: a catch only counts if the original passes, so a false alarm on a good
   reply costs as much as a miss."
3. **Recipe.** "Code does what code can do exactly: a whitelist so the judge sees one reply and nothing else, sanitised
   inputs, number evidence, an enforced call budget and logs. On the LLM side we measured three strategies, with and
   without examples, and decided in advance to keep only what beats the baseline on BOTH criteria."
4. **Results.** "That rule picked the simplest one: 0.754 to 0.789 and 0.586 to 0.596, with better keep and kappa. Our
   claim audit was the best on the first criterion, up to 0.87, but it collapsed on the surprise one, so we did not ship it."
5. **Lessons.** "Few-shot examples made the model over-strict, and the audit treated omissions as errors. A rule in a
   prompt is a hypothesis: you have to measure it on criteria you did not design for. Next we would calibrate the audit
   from the example originals, so its gain carries over."
