"""final_judge.py: judge for one customer-support reply at a time.

FROZEN CONFIGURATION (decided from hold-out runs logged in EXPERIMENTS.md): VARIANT "M" = majority vote of three
independent views of the same sanitised, whitelisted input (criterion + policy + customer message + ONE reply +
code-extracted number evidence), temperature 0, no few-shot examples:
  C  one-word holistic verdict                       (call 1)
  D  short commitment-by-commitment check, VERDICT   (call 2)
  A  claim audit with precision guard                (call 3, only when C and D disagree)
Code takes the majority; at most 3 calls per reply, 2 when C and D agree. Variants A/B/C/D alone are ablations.

Original design notes (claim-audit pipeline):

Recipe (see RECIPE.md):
  1. Code builds the judge input from a whitelist (criterion, policy, labelled examples, customer message, ONE reply),
     sanitises it, and extracts numbers as evidence (numbers in the reply that are / are not in the policy).
  2. Call 1 (AUDIT): the LLM splits the reply into commitments, quotes the matching policy text verbatim and answers
     narrow yes/no questions per commitment (number, dropped condition, certainty, scope, detail, direction) plus
     whether the criterion counts it as a violation. JSON, parsed leniently.
  3. Code keeps only flagged statements that are backed by evidence (quote really is in the reply, at least one
     concrete deviation). None left -> pass (1 call).
  4. Call 2 (VERIFY): an independent check of only the flagged statements. Confirmed as wrong_or_misleading AND
     violating the criterion -> fail; otherwise pass. Call 3 only if call 2's answer cannot be parsed.
  Precision guard: "incomplete but accurate" (the reply leaves out other policy information) is never a violation.
Nothing here names a criterion, edit type, language, policy clause or number: behaviour comes from the inputs.

Entry points used by run_judge.py: prepare(criterion, policy, dev_pairs) and judge(question, reply, lang, criterion,
policy). `lang` is accepted for the runner's signature but never used (the judge sees only the reply text).
No state carries between replies: per-reply data lives in local variables; module data is set once in prepare()
from criterion, policy and examples only. The only shared mutable thing is an append-only log file (never read).
"""
from __future__ import annotations

import difflib
import json
import os
import random
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request

REQUIRED_MODEL = "claude-haiku-4.5"
MAX_CALLS_PER_REPLY = 3
VARIANT = "M"  # FROZEN. M = lazy majority of C (one word), D (short reasoning) and the claim audit; <=3 calls Ablations kept for the recipe: A = audit+verify, B = A + holistic must agree, C = holistic only
MAX_EXAMPLE_GROUPS = 0  # FROZEN: examples made haiku over-strict on hold-out (see EXPERIMENTS.md); 0 = none
MAX_INPUT_CHARS = 6000          # cap absurd lengths
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

# Immutable after prepare(): derived only from criterion, policy and labelled examples.
_CTX: dict = {}
_log_lock = threading.Lock()


# --------------------------------------------------------------------------------------------- LLM transport
class BudgetExceeded(RuntimeError):
    pass


class _Budget:
    """Per-reply LLM call counter (a local object, never shared between replies)."""

    def __init__(self, limit: int = MAX_CALLS_PER_REPLY):
        self.limit, self.n = limit, 0

    def take(self) -> None:
        self.n += 1
        if self.n > self.limit:
            raise BudgetExceeded(f"more than {self.limit} LLM calls for one reply")


def _env() -> tuple[str, str, str, float]:
    base = os.environ.get("JUDGE_LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("JUDGE_LLM_API_KEY", "")
    model = os.environ.get("JUDGE_LLM_MODEL", "")
    if not base or not key:
        raise RuntimeError("set JUDGE_LLM_BASE_URL and JUDGE_LLM_API_KEY (load .env)")
    if model != REQUIRED_MODEL:
        raise RuntimeError(f"JUDGE_LLM_MODEL must be {REQUIRED_MODEL!r}, got {model!r}")
    return base, key, model, float(os.environ.get("JUDGE_LLM_TIMEOUT", "90"))


def _llm(prompt: str, budget: _Budget, max_tokens: int) -> str:
    """One logical LLM call (counts against the budget). Retries ONLY on transport failures."""
    budget.take()
    base, key, model, timeout = _env()
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0, "max_tokens": max_tokens}
    data = json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    retries = int(os.environ.get("JUDGE_LLM_MAX_RETRIES", "7"))
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(f"{base}/chat/completions", data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(f"LLM endpoint refused the key (HTTP {e.code})") from None
            if e.code not in (408, 429, 500, 502, 503, 504, 529) or attempt == retries:
                raise RuntimeError(f"LLM request failed with HTTP {e.code}") from None
            ra = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = min(float(ra), 60.0) if ra else min(2 ** attempt, 40.0) + random.random() * 2
            except ValueError:
                wait = min(2 ** attempt, 40.0) + random.random() * 2
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == retries:
                raise RuntimeError(f"LLM request failed: {type(e).__name__}") from None
            time.sleep(min(2 ** attempt, 40.0) + random.random() * 2)
    raise RuntimeError("unreachable")


# --------------------------------------------------------------------------------------------- code-only helpers
def _sanitise(text: str) -> str:
    """Neutralise tag-like markup so input text cannot close or open our tags; cap length."""
    text = unicodedata.normalize("NFC", str(text or ""))[:MAX_INPUT_CHARS]
    return re.sub(r"<(/?)([A-Za-z_])", lambda m: "‹" + m.group(1) + m.group(2), text)


_NUM = re.compile(r"(?<![\w])(\d+(?:[.,]\d+)?)")


def _numbers(text: str) -> list[str]:
    """Language-neutral numeral extractor (evidence only): '12', '12,5' -> '12.5'."""
    out = []
    for m in _NUM.finditer(text or ""):
        v = m.group(1).replace(",", ".")
        v = v.rstrip("0").rstrip(".") if "." in v else v
        if v not in out:
            out.append(v)
    return out


def _norm_tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s).casefold()
    return re.findall(r"\w+", s)


def _quote_in(quote: str, text: str) -> bool:
    """True if `quote` (an LLM-copied span) is really in `text` (lenient: token coverage or fuzzy block match)."""
    q, t = _norm_tokens(quote), _norm_tokens(text)
    if not q:
        return False
    ts = set(t)
    cover = sum(1 for w in q if w in ts) / len(q)
    if cover >= 0.8:
        return True
    sm = difflib.SequenceMatcher(None, " ".join(q), " ".join(t), autojunk=False)
    return sm.find_longest_match(0, len(" ".join(q)), 0, len(" ".join(t))).size >= 0.7 * len(" ".join(q))


def _parse_json(raw: str) -> dict | None:
    """Lenient JSON: strip fences, take the outermost {...}; tolerate trailing commas."""
    if not raw:
        return None
    s = re.sub(r"```(?:json)?", "", raw)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = s[start:end + 1]
    for cand in (blob, re.sub(r",\s*([}\]])", r"\1", blob)):
        try:
            v = json.loads(cand)
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            continue
    return None


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "yes", "y", "1", "fail")


def _log(rec: dict) -> None:
    """Append-only signal log for offline re-tuning (git-ignored). Never read back by the judge."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"signals_{_CTX.get('run_tag', 'run')}.jsonl")
        line = json.dumps(rec, ensure_ascii=False)
        with _log_lock, open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------------------------- prepare (once)
def _select_examples(dev_pairs: list[dict]) -> list[dict]:
    """One labelled pair per group of examples, chosen deterministically (smallest case id per group).

    Groups are formed from whatever grouping field the example file provides, without naming any group; pairs whose
    label changes come first so the LLM sees what a violation looks like, then pairs whose label does not change.
    """
    groups: dict[str, list[dict]] = {}
    for p in dev_pairs:
        if not all(k in p for k in ("original", "edited", "original_label", "edited_label")):
            continue
        g = str(p.get("edit_type") or p.get("edit_family") or p.get("edited_label"))
        groups.setdefault(g, []).append(p)
    picks = []
    for g in sorted(groups):
        picks.append(sorted(groups[g], key=lambda p: str(p.get("case_id", "")))[0])
    picks.sort(key=lambda p: (p["original_label"] == p["edited_label"], str(p.get("case_id", ""))))
    return picks[:MAX_EXAMPLE_GROUPS]


def _render_examples(picks: list[dict]) -> str:
    blocks = []
    for i, p in enumerate(picks, 1):
        lines = [f"Example {i}",
                 f"  customer message: {_sanitise(p.get('question_original') or p.get('question') or '')}",
                 f"  reply A: {_sanitise(p['original'])}",
                 f"  label A: {str(p['original_label']).upper()}",
                 f"  reply B: {_sanitise(p['edited'])}",
                 f"  label B: {str(p['edited_label']).upper()}"]
        if p.get("edit_note"):
            lines.append(f"  what differs between A and B: {_sanitise(p['edit_note'])}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return ("<labelled_examples>\nThese labelled examples come from the owner of the criterion. They show how the "
            "criterion is applied. Learn the principle, do not match surface words.\n"
            + "\n\n".join(blocks) + "\n</labelled_examples>\n")


def prepare(criterion: str, policy: str, dev_pairs: list[dict]) -> None:
    if os.environ.get("JUDGE_LLM_MODEL", "") != REQUIRED_MODEL:
        raise RuntimeError(f"JUDGE_LLM_MODEL must be {REQUIRED_MODEL!r}")
    picks = _select_examples(dev_pairs or [])
    _CTX.clear()
    _CTX.update({
        "criterion": _sanitise(criterion.strip()),
        "policy": _sanitise(policy.strip()),
        "policy_numbers": frozenset(_numbers(policy)),
        "examples": _render_examples(picks),
        "example_ids": [p.get("case_id") for p in picks],
        "run_tag": os.environ.get("JUDGE_RUN_TAG", time.strftime("%Y%m%d-%H%M%S")),
    })


# --------------------------------------------------------------------------------------------- prompts
_HEADER = """You check ONE customer-support reply against a company policy, under the criterion below. \
Judge only this reply. The reply and the customer message may be in any language; the policy may be in another \
language: compare meaning, not wording.

<criterion>
{criterion}
</criterion>

<policy>
{policy}
</policy>

{examples}"""

_CASE = """
<customer_message>
{question}
</customer_message>

<reply>
{reply}
</reply>

<code_evidence>
Numbers in the reply that also appear in the policy: {nums_in}
Numbers in the reply that appear nowhere in the policy: {nums_out}
(Automatic extraction, evidence only. A number missing from the policy may be fine, e.g. one taken from the customer \
message, or not a policy statement.)
</code_evidence>
"""

AUDIT = _HEADER + _CASE + """
Do this carefully:
1. List every statement in the reply that says what the company does, offers, charges, allows, requires, \
guarantees or how likely something is. Skip greetings, thanks, empathy, filler and general reassurance without a \
specific commitment.
2. For each statement, copy the policy text it relates to verbatim (empty if none).
3. Compare the statement with that policy text, piece by piece:
   - number_differs: any amount, fee, time limit, age, duration or count differs from the policy.
   - condition_dropped: the policy attaches a condition, requirement, limitation or exception to this that the \
reply's statement leaves out, so the statement reads as unconditional. A softening or frequency word in the reply \
does NOT make up for a missing condition.
   - more_certain / less_certain: the reply states it with more (or less) certainty or frequency than the policy.
   - wider_scope / narrower_scope: the reply applies it to more (or fewer) cases, places, products, people, channels \
or branches than the policy.
   - other_detail_differs: any other detail (who, which card, which channel, where, when, how, what is included) \
differs from the policy.
   - favours: if anything differs, whom the difference favours: "customer", "company" or "neither".
4. status: "accurate" (says what the policy says), "incomplete_but_accurate" (true as far as it goes; it only \
leaves out OTHER information the policy also contains) or "wrong_or_misleading" (a customer who relies on this \
statement would be misled about what the policy provides: wrong value, a dropped condition that gates exactly what \
the statement asserts, more or less certainty, wider or narrower scope, a different detail). A reply never has to \
repeat the whole policy: not mentioning a rule, a fee, an option or a detail is NOT an error by itself.
5. violates_criterion: true only if status is "wrong_or_misleading" AND the criterion's own pass/fail definition and \
exclusions count that deviation, guided by the labelled examples. Most good replies have no violation at all.

Answer with JSON only, no prose:
{{"statements": [{{"reply_quote": "<verbatim span of the reply>", "policy_quote": "<verbatim policy text or empty>", \
"number_differs": false, "condition_dropped": false, "more_certain": false, "less_certain": false, \
"wider_scope": false, "narrower_scope": false, "other_detail_differs": false, "favours": "neither", \
"status": "accurate", "violates_criterion": false, "reason": "<max 20 words>"}}]}}"""

VERIFY = _HEADER + _CASE + """
A first reviewer flagged these statements of the reply:
{flagged}

First reviewers flag far too much. Calibrate: good replies (and replies labelled PASS in any examples above) also \
paraphrase the policy and leave parts of it out (other rules, fees, options, procedural steps, details that are \
implied by the customer's situation). Bad replies contain a statement that, taken at face value, tells the \
customer something the policy does not support (see "what differs" in each example).

For each flagged statement:
- copy the policy rule it relates to, verbatim;
- write what the reply leads the customer to believe;
- decide which KIND of gap it is: "wrong_or_misleading" = the statement itself is wrong (a wrong value; a \
condition that decides whether the stated thing applies at all is dropped, so the statement becomes unconditional; \
more or less certainty; wider or narrower scope; a different detail), or "incomplete_but_accurate" = the kind good replies \
also have (detail left out, different wording, context implied), or "accurate";
- violates_criterion: true only for "wrong_or_misleading" gaps that the criterion's own definition and exclusions \
count.

Answer with JSON only:
{{"checks": [{{"id": 1, "policy_rule": "<verbatim>", "customer_believes": "<paraphrase>", \
"gap": "<short>", "status": "accurate", "violates_criterion": false}}]}}"""

REASONED = _HEADER + _CASE + """
Check the reply against the policy before answering. Briefly (at most 6 short lines): list each specific commitment \
in the reply (amounts, conditions, certainty, scope, details) and whether the policy supports it as stated. Then \
apply the criterion, including its exclusions.
End with one final line, exactly: VERDICT: PASS or VERDICT: FAIL"""


def _final_word(raw: str) -> str | None:
    m = re.findall(r"VERDICT\W*(PASS|FAIL)", raw.upper())
    if m:
        return m[-1]
    m = re.findall(r"\b(PASS|FAIL)\b", raw.upper())
    return m[-1] if m else None


HOLISTIC = _HEADER + _CASE + """
Apply the criterion to this reply. Answer with exactly one word: PASS or FAIL."""

TIEBREAK = _HEADER + _CASE + """
Two reviewers disagree about whether these statements of the reply violate the criterion:
{flagged}

For each statement, first write what a customer reading ONLY this reply would reasonably believe they are entitled \
to or will get, then write what the policy actually provides for that situation (quote it), then say whether the \
gap is a violation by the criterion's own definition and exclusions. Leaving out other information is never a gap; \
only being misled is.

Answer with JSON only:
{{"checks": [{{"id": 1, "customer_believes": "<...>", "policy_provides": "<verbatim>", \
"status": "accurate", "violates_criterion": false}}]}}"""


# --------------------------------------------------------------------------------------------- judge
_DEVIATIONS = ("number_differs", "condition_dropped", "more_certain", "less_certain", "wider_scope",
               "narrower_scope", "other_detail_differs")


def _whitelist_input(question: str, reply: str) -> dict:
    """The ONLY per-reply fields that reach a prompt (structural R2): customer message and the reply text."""
    reply_s = _sanitise(reply)
    nums = _numbers(reply)
    pol = _CTX["policy_numbers"]
    return {
        "question": _sanitise(question) or "(none)",
        "reply": reply_s,
        "nums_in": ", ".join(n for n in nums if n in pol) or "none",
        "nums_out": ", ".join(n for n in nums if n not in pol) or "none",
        "criterion": _CTX["criterion"], "policy": _CTX["policy"], "examples": _CTX["examples"],
    }


def _flag_list(items: list[dict]) -> str:
    return "\n".join(f'{i}. "{_sanitise(s.get("reply_quote", ""))}" (reviewer reason: '
                     f'{_sanitise(str(s.get("reason", "")))[:200]})' for i, s in enumerate(items, 1))


def _misleading(d: dict) -> bool:
    """Precision guard: a violation needs an explicit wrong_or_misleading status (incomplete != wrong)."""
    st = str(d.get("status", "")).strip().lower()
    return _truthy(d.get("violates_criterion")) and ("wrong" in st or "mislead" in st)


def _confirmed(parsed: dict | None) -> bool | None:
    if not parsed or not isinstance(parsed.get("checks"), list):
        return None
    return any(isinstance(c, dict) and _misleading(c) for c in parsed["checks"])


def judge(question: str, reply: str, lang: str, criterion: str, policy: str) -> str:  # noqa: ARG001 (lang unused)
    if not _CTX:
        prepare(criterion, policy, [])
    budget = _Budget()
    inp = _whitelist_input(question, reply)
    rec: dict = {"variant": VARIANT, "reply_sha": __import__("hashlib").sha256(reply.encode()).hexdigest()[:12],
                 "nums_in": inp["nums_in"], "nums_out": inp["nums_out"]}

    if VARIANT == "M":
        # majority of three independent views, evaluated lazily inside the 3-call budget:
        # C (one-word holistic) and D (short reasoning) first; only if they disagree does the claim audit decide.
        wc = _llm(HOLISTIC.format(**inp), budget, max_tokens=8).strip().strip("*.`'\" ").upper()
        vc = "pass" if wc.startswith("PASS") else "fail"
        wd = _final_word(_llm(REASONED.format(**inp), budget, max_tokens=500))
        vd = "fail" if wd == "FAIL" else "pass"
        rec.update(c=vc, d=vd)
        if vc == vd:
            verdict = vc
        else:
            p1 = _parse_json(_llm(AUDIT.format(**inp), budget, max_tokens=1800))
            stmts = p1.get("statements") if p1 else None
            stmts = stmts if isinstance(stmts, list) else []
            flagged = [x for x in stmts if isinstance(x, dict) and _misleading(x)
                       and any(_truthy(x.get(k)) for k in _DEVIATIONS)
                       and _quote_in(str(x.get("reply_quote", "")), reply)]
            rec["audit_flagged"] = len(flagged)
            verdict = "fail" if flagged else "pass"
        rec.update(verdict=verdict, calls=budget.n)
        _log(rec)
        return verdict

    if VARIANT == "D":
        raw = _llm(REASONED.format(**inp), budget, max_tokens=500)
        word = _final_word(raw)
        verdict = "fail" if word == "FAIL" else "pass"
        rec.update(reasoned=word, verdict=verdict, calls=budget.n, unparsed=word is None)
        _log(rec)
        return verdict

    if VARIANT == "C":
        word = _llm(HOLISTIC.format(**inp), budget, max_tokens=8).strip().strip("*.`'\" ").upper()
        verdict = "pass" if word.startswith("PASS") else "fail"
        rec.update(holistic=word[:10], verdict=verdict, calls=budget.n)
        _log(rec)
        return verdict

    # Call 1: audit
    raw1 = _llm(AUDIT.format(**inp), budget, max_tokens=1800)
    p1 = _parse_json(raw1)
    stmts = p1.get("statements") if p1 else None
    rec["audit_parsed"] = stmts is not None
    if not isinstance(stmts, list):
        stmts = []
        rec["audit_raw"] = raw1[:500]
    # precision guard: a flag counts only if its quote is really in the reply and a concrete deviation is named
    flagged = [s for s in stmts if isinstance(s, dict) and _misleading(s)
               and any(_truthy(s.get(k)) for k in _DEVIATIONS)
               and _quote_in(str(s.get("reply_quote", "")), reply)]
    rec["audit"] = [{k: s.get(k) for k in ("reply_quote", "status", "violates_criterion", "reason", *_DEVIATIONS, "favours")}
                    for s in stmts if isinstance(s, dict)]
    rec["n_flagged"] = len(flagged)

    if not flagged:
        verdict = "pass"
    else:
        flag_txt = _flag_list(flagged)
        c2 = _confirmed(_parse_json(_llm(VERIFY.format(flagged=flag_txt, **inp), budget, max_tokens=1500)))
        rec["verify"] = c2
        if c2 is not True:
            verdict = "pass"  # not confirmed (or unreadable): the precision guard keeps the reply
        elif VARIANT == "B":
            # third, independent holistic check (sees no findings); all three must agree to fail
            word = _llm(HOLISTIC.format(**inp), budget, max_tokens=8).strip().strip("*.`'\" ").upper()
            rec["holistic"] = word[:10]
            verdict = "pass" if word.startswith("PASS") else "fail"
        else:
            verdict = "fail"
    rec["verdict"], rec["calls"] = verdict, budget.n
    _log(rec)
    return verdict
