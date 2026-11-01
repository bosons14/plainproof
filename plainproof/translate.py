"""Plain-English question -> ClaimSpec, using Claude (the Anthropic API).

The person never has to see a formula. Claude writes:
  * a plain restatement of exactly what will be tested (the person confirms it),
  * the whole-number inputs and their ranges,
  * a small, overflow-safe C function claim_holds(...).
"""

from __future__ import annotations

import json
import os
import re

from .spec import ClaimSpec

DEFAULT_MODEL = os.environ.get("PLAINPROOF_MODEL", "claude-sonnet-5-5")

SYSTEM = """You turn everyday questions about numbers into a precise, testable claim, for people who do not
speak mathematical jargon. The claim will be checked by running a C program and then formally verified by
Aristotle, a tool that proves facts about C code.

Rules for your output:
1. plain_restatement: one or two sentences a 14-year-old understands. No symbols like ∀, ∑, ≡, mod, |, ^
   unless the person used them. Say "for every whole number n from 1 to 1,000" rather than quantifier lingo.
   It must say EXACTLY what claim_holds tests, nothing more.
2. variables: 1 to 3 whole-number inputs (C long long). Pick ranges that (a) make the claim meaningful,
   (b) keep every intermediate value far below 9,000,000,000,000,000,000 so nothing overflows, and
   (c) keep a brute-force check under ~20 million cases and a loop inside claim_holds short. Prefer
   modest ranges (hundreds to a few million) over huge ones. Give each a plain `meaning`.
3. c_function: C11 source defining `int claim_holds(long long a, long long b, ...)` with exactly one
   parameter per variable, in order, returning 1 if the claim holds for those inputs and 0 otherwise.
   Pure arithmetic only: no I/O, no main(), no malloc, no recursion, no floating point unless the
   claim is genuinely about decimals (avoid it if you can). Helper functions must be `static`.
   Arrange arithmetic so it cannot overflow inside the stated ranges (e.g. test d <= x / d, not d*d <= x).
   Keep it short and readable: Aristotle has to reason about it.
4. assumptions: every interpretation choice you made (e.g. "counting starts at 1", "0 is not prime").
5. fidelity_note: be honest about what a finite check over these ranges does NOT establish
   (e.g. "only numbers up to 100,000 are covered", or "this is a famous open problem; no finite check
   settles it").
6. If the question cannot be expressed as a whole-number claim (e.g. it is about geometry with real numbers,
   limits, infinity in an essential way, or it is not a yes/no claim), set can_encode to false and explain
   why_not in plain words, suggesting a nearby question that CAN be checked.

Reply with ONLY a JSON object inside <spec></spec> tags, with keys:
title, can_encode, why_not, plain_restatement, variables (list of {name, min, max, meaning}),
c_function, assumptions (list of strings), fidelity_note."""


class CannotEncode(Exception):
    """The question doesn't fit plainproof's whole-number mould; the message says why in plain words."""


def _client():
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Install the Anthropic SDK: pip install anthropic") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Set ANTHROPIC_API_KEY so plainproof can translate your question. "
            "(Or write a claim spec by hand and run `plainproof check spec.json`.)"
        )
    return anthropic.Anthropic()


def ask_claude(system: str, user: str, model: str = DEFAULT_MODEL, max_tokens: int = 4000) -> str:
    response = _client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


def _extract_json(text: str) -> dict:
    m = re.search(r"<spec>(.*?)</spec>", text, re.S)
    raw = m.group(1) if m else text
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    return json.loads(raw)


def translate(question: str, feedback: str | None = None, previous: ClaimSpec | None = None,
              model: str = DEFAULT_MODEL) -> ClaimSpec:
    """Turn a question into a spec. `feedback` and `previous` revise an earlier attempt."""
    user = f"Question: {question}"
    if previous is not None and feedback:
        user += (
            f"\n\nYour previous attempt:\n<spec>{previous.to_json()}</spec>\n\n"
            f"Revise it. Feedback: {feedback}"
        )
    last_error = None
    for _ in range(3):
        text = ask_claude(SYSTEM, user if last_error is None else
                          user + f"\n\nYour last reply was rejected: {last_error}. Fix that.", model=model)
        try:
            data = _extract_json(text)
            if not data.get("can_encode", True):
                raise CannotEncode(data.get("why_not") or "This question isn't a whole-number claim.")
            data["question"] = question
            return ClaimSpec.from_dict(data)
        except CannotEncode:
            raise
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            last_error = str(e)
    raise RuntimeError(f"Could not get a usable translation: {last_error}")
