# 1-minute talk script (one line per slide)

1. **Title.** "We built a recipe for LLM judges that has to work on a criterion it has never seen. Same code, only the
   inputs change. On held-out cases it beats the starting judge on both criteria, and two runs agree 100%."
2. **Diagnose.** "The starting judge misses 93% of dropped conditions and half of the 'usually becomes always' edits, and
   it rejects good replies. The key insight: a catch only counts if the original passes, so a false alarm on a good
   reply costs as much as a miss."
3. **Recipe.** "Code does what code can do exactly: a whitelist so the judge sees one reply and nothing else, sanitised
   inputs, number evidence, an enforced call budget and logs. The LLM part is a vote of three independent views: a
   one-word verdict, a short check of each commitment, and a claim audit that is only called when the first two disagree."
4. **Results.** "0.754 to 0.835 on the original criterion and 0.586 to 0.621 on the surprise one, and two runs agree 100%.
   Each view alone lost on one criterion; only the vote won on both."
5. **Lessons.** "Few-shot examples made the model over-strict, and the audit treated omissions as errors. A rule in a
   prompt is a hypothesis: you have to measure it on criteria you did not design for. Next we would calibrate the audit
   from the example originals, so its gain carries over."
