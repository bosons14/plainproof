"""Verdicts back into everyday language.

With ANTHROPIC_API_KEY set, Claude writes the explanation (including Aristotle's own notes,
which can be technical). Without it, plainproof falls back to fixed wording.
"""

from __future__ import annotations

import os

from .aristotle_run import AristotleResult
from .quickcheck import QuickResult
from .spec import ClaimSpec

SYSTEM = """You explain results from a maths-checking tool to someone with no mathematical training.
Write at most 180 words, in short plain sentences. No formulas, no Lean, no C, no words like
"theorem", "lemma", "quantifier", "undefined behaviour", "formal verification" (say "checked by a
proof-checking computer" instead). Lead with the verdict in one sentence. Then say in plain words what
exactly was established and, crucially, its limits (the ranges checked; that a finite range is not
"all numbers"). If there is a counterexample, show it as a worked example with real numbers. If the
proof succeeded, give the everyday intuition for WHY it is true, if there is a simple one. End with one
suggestion for a natural next question to try."""


def _status_line(result: AristotleResult | None) -> str:
    if result is None:
        return "not sent to Aristotle"
    p = result.main_property()
    if p is None:
        return f"run ended {result.run_status} with no verdict recorded"
    return f"{p.status}" + (f" ({p.evidence})" if p.evidence else "") + (
        f", reason {p.failure_reason}" if p.failure_reason else "")


def fallback(spec: ClaimSpec, quick: QuickResult | None, result: AristotleResult | None) -> str:
    parts = []
    p = result.main_property() if result else None
    if p is not None and p.status == "PROVED":
        parts.append(
            f"PROVED. A proof-checking computer confirmed: {spec.plain_restatement} "
            f"This is guaranteed for {spec.ranges_plain()}, with no exceptions in that range."
        )
    elif p is not None and p.status == "REFUTED":
        parts.append("FALSE. The proof checker found a case where the claim breaks.")
        if p.message:
            parts.append(f"Its note: {p.message}")
    elif result is not None:
        parts.append(f"No final answer from Aristotle (status: {_status_line(result)}).")
    if quick is not None:
        parts.append(quick.plain(spec))
    if spec.fidelity_note:
        parts.append(f"Keep in mind: {spec.fidelity_note}")
    return "\n\n".join(parts)


def explain(spec: ClaimSpec, quick: QuickResult | None, result: AristotleResult | None,
            model: str | None = None) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return fallback(spec, quick, result)
    from .translate import DEFAULT_MODEL, ask_claude

    p = result.main_property() if result else None
    facts = [
        f"Person's question: {spec.question}",
        f"Exact claim tested: {spec.plain_restatement}",
        f"Inputs covered: {spec.ranges_plain()}",
        f"Interpretation choices: {'; '.join(spec.assumptions) or 'none'}",
        f"Limits of the translation: {spec.fidelity_note or 'none stated'}",
        f"Quick local test: {quick.plain(spec) if quick else 'not run'}",
        f"Aristotle verdict: {_status_line(result)}",
    ]
    if p is not None:
        if p.message:
            facts.append(f"Aristotle's note: {p.message}")
        if p.description:
            facts.append(f"Aristotle's description: {p.description}")
    if result is not None and result.summary:
        facts.append(f"Aristotle's run summary: {result.summary[:3000]}")
    try:
        return ask_claude(SYSTEM, "\n".join(facts), model=model or DEFAULT_MODEL, max_tokens=800).strip()
    except Exception:  # explanation is a nicety; never lose the verdict over it
        return fallback(spec, quick, result)
