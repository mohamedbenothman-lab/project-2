"""final_judge.py: claim-audit judge for one customer-support reply at a time.

Recipe (see RECIPE.md):
  1. Code builds the judge input from a whitelist (criterion, policy, labelled examples, customer message, ONE reply),
     sanitises it, and extracts numbers as evidence (numbers in the reply that are / are not in the policy).
  2. Call 1 (AUDIT): the LLM splits the reply into commitments, quotes the matching policy text verbatim and answers
     narrow yes/no questions per commitment (number, dropped condition, certainty, scope, detail, direction) plus
     whether the criterion counts it as a violation. JSON, parsed leniently.
  3. Code keeps only flagged statements that are backed by evidence (quote really is in the reply, at least one
     concrete deviation). None left -> pass (1 call).
  4. Call 2 (VERIFY): an independent check of only the flagged statements. Confirmed -> fail.
     Call 3 (TIE-BREAK, only when calls 1 and 2 disagree): a third, differently framed check; majority decides.
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
MAX_EXAMPLE_GROUPS = 9          # at most one example pair per label-change group, deterministic choice
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
    return "\n\n".join(blocks) if blocks else "(none provided)"


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

<labelled_examples>
These labelled examples come from the owner of the criterion. They show how the criterion is applied. Learn the \
principle, do not match surface words.
{examples}
</labelled_examples>
"""

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
4. violates_criterion: apply the criterion's own pass/fail definition and exclusions literally to this statement, \
guided by the labelled examples. Mark true only for a concrete deviation you can name.

Answer with JSON only, no prose:
{{"statements": [{{"reply_quote": "<verbatim span of the reply>", "policy_quote": "<verbatim policy text or empty>", \
"number_differs": false, "condition_dropped": false, "more_certain": false, "less_certain": false, \
"wider_scope": false, "narrower_scope": false, "other_detail_differs": false, "favours": "neither", \
"violates_criterion": false, "reason": "<max 20 words>"}}]}}"""

VERIFY = _HEADER + _CASE + """
A first reviewer says these statements of the reply violate the criterion:
{flagged}

Check each one independently; the first reviewer may be right or wrong. For each statement:
- copy the complete policy rule it relates to, verbatim;
- write exactly what the reply commits the company to in that statement (include any condition it keeps);
- list the concrete differences between the two (a condition or limitation the policy attaches but the reply drops \
counts as a difference; a policy rule the reply does not talk about at all does not);
- decide whether, by the criterion's own definition and exclusions, those differences make the reply fail.

Answer with JSON only:
{{"checks": [{{"id": 1, "policy_rule": "<verbatim>", "reply_commits_to": "<paraphrase>", \
"differences": ["<difference>"], "violates_criterion": false}}]}}"""

TIEBREAK = _HEADER + _CASE + """
Two reviewers disagree about whether these statements of the reply violate the criterion:
{flagged}

For each statement, first write what a customer reading ONLY this reply would reasonably believe they are entitled \
to or will get, then write what the policy actually provides for that situation (quote it), then say whether the \
gap is a violation by the criterion's own definition and exclusions.

Answer with JSON only:
{{"checks": [{{"id": 1, "customer_believes": "<...>", "policy_provides": "<verbatim>", \
"violates_criterion": false}}]}}"""


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


def _confirmed(parsed: dict | None) -> bool | None:
    if not parsed or not isinstance(parsed.get("checks"), list):
        return None
    return any(isinstance(c, dict) and _truthy(c.get("violates_criterion")) for c in parsed["checks"])


def judge(question: str, reply: str, lang: str, criterion: str, policy: str) -> str:  # noqa: ARG001 (lang unused)
    if not _CTX:
        prepare(criterion, policy, [])
    budget = _Budget()
    inp = _whitelist_input(question, reply)
    rec: dict = {"reply_sha": __import__("hashlib").sha256(reply.encode()).hexdigest()[:12],
                 "nums_in": inp["nums_in"], "nums_out": inp["nums_out"]}

    # Call 1: audit
    raw1 = _llm(AUDIT.format(**inp), budget, max_tokens=1800)
    p1 = _parse_json(raw1)
    stmts = p1.get("statements") if p1 else None
    rec["audit_parsed"] = stmts is not None
    if not isinstance(stmts, list):
        stmts = []
        rec["audit_raw"] = raw1[:500]
    # precision guard: a flag counts only if its quote is really in the reply and a concrete deviation is named
    flagged = [s for s in stmts if isinstance(s, dict) and _truthy(s.get("violates_criterion"))
               and any(_truthy(s.get(k)) for k in _DEVIATIONS)
               and _quote_in(str(s.get("reply_quote", "")), reply)]
    rec["audit"] = [{k: s.get(k) for k in ("reply_quote", "violates_criterion", "reason", *_DEVIATIONS, "favours")}
                    for s in stmts if isinstance(s, dict)]
    rec["n_flagged"] = len(flagged)

    if not flagged:
        verdict = "pass"
    else:
        flag_txt = _flag_list(flagged)
        p2 = _parse_json(_llm(VERIFY.format(flagged=flag_txt, **inp), budget, max_tokens=1500))
        c2 = _confirmed(p2)
        rec["verify"] = c2
        if c2 is True:
            verdict = "fail"
        else:
            # calls 1 and 2 disagree (or call 2 unreadable): third, differently framed check; majority of three
            p3 = _parse_json(_llm(TIEBREAK.format(flagged=flag_txt, **inp), budget, max_tokens=1200))
            c3 = _confirmed(p3)
            rec["tiebreak"] = c3
            verdict = "fail" if c3 is True else "pass"
    rec["verdict"], rec["calls"] = verdict, budget.n
    _log(rec)
    return verdict
