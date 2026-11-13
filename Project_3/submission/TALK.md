# Talk script: Team Tougypt (about 2 minutes, ~25 s per slide)

## Slide 1: The problem
"Customer-support chatbots are checked by AI judges. Look at reply B: it sounds fine, but it drops 'as long as the car
is not reserved', so it promises something the company can't always keep. The starting judge says both replies are
fine; it catches only 7% of these dropped conditions. We built a judge that catches them, works on a criterion it had
never seen, and gives the same verdict every time: 0.754 to 0.835, 0.586 to 0.621 on the surprise criterion, and
100% agreement between two runs."

## Slide 2: Diagnose
"First we measured where the starting judge fails: 93% of dropped conditions and half of the 'usually becomes always'
edits slip through, and it wrongly rejects harmless rewrites like reordering or translation. Two insights shaped
everything. One: the score only counts a catch if the good original passes, so a false alarm costs as much as a miss.
Two: the hidden test has edit types we never saw, so we hard-coded nothing: no edit types, no keywords, no policy
numbers, no languages."

## Slide 3: How it works
"Code does what code can do exactly. It builds the input from a whitelist, so the judge sees one reply and nothing else,
neutralises markup, checks every number against the policy and enforces the call budget. Then two independent views
of the reply: a one-word verdict, and a short check of every commitment against the policy. If they agree, we are done
after two calls. If they disagree, a detailed claim audit breaks the tie; it only counts a problem if the quote is
really in the reply and the statement is wrong, not just incomplete. Code takes the majority."

## Slide 4: How we got there
"We didn't get there on the first try, and this table is the honest path. Our first, very detailed judge rejected 58%
of good replies. Adding example pairs made it worse: the model started hunting for differences. Each simpler view won
on one criterion and lost on the other: the audit was best on the first, the reasoning check was best on the surprise.
We decided in advance to keep only what wins on BOTH, and only the majority of the three did."

## Slide 5: Result and lessons
"On held-out cases: 0.754 to 0.835 on the original criterion, catch from 0.656 to 0.789, and 0.586 to 0.621 on the
surprise criterion, with the same code. Two runs agree 100%, at two calls per reply. The main lesson: a rule written into
a prompt is only a hypothesis, so measure it on criteria you didn't design for. Next we'd run the exact three-way vote,
which reached 0.88 offline. Thank you."
