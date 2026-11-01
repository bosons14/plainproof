---
name: ask
description: "This skill should be used when the user asks a yes/no question about whole numbers in everyday language and wants it checked or proved - \"is it always true that...\", \"does this formula always give a prime\", \"prove that the sum of two odd numbers is even\", \"check this number pattern\", \"is my maths trick right\" - or mentions plainproof or Aristotle for a maths question, or runs /plainproof:ask. Restates the claim in plain words, tests it locally for free, and optionally has Harmonic's Aristotle prove or refute it."
metadata:
  version: "0.1.0"
---

# plainproof: ask a maths question in plain English

The person may know no mathematical jargon. Everything you show them is plain sentences and real
numbers: no ∀, ∑, ≡, "mod", "theorem", "lemma", Lean or C unless they ask for it.

Aristotle (relaunched 27 Oct 2026) verifies **C code**, not pure maths. plainproof bridges the gap:
the claim becomes a C function `claim_holds(...)` that returns 1 when the claim is true, and
Aristotle proves it returns 1 for every input in a stated range. **You** do the translation here, so
no Anthropic API key is needed.

## Launcher

Run the CLI as `"${CLAUDE_PLUGIN_ROOT}/bin/plainproof"`. If that variable is empty, use `plainproof`
when it is on PATH, else find the launcher with
`find ~/.claude/plugins -path '*plainproof/bin/plainproof' -type f | head -1`.
It needs Python 3.10+ and a C compiler (`cc`, `gcc` or `clang`). Below, `PP` means that launcher.

## Procedure

1. **Decide whether it fits.** plainproof handles claims about whole numbers with 1 to 3 inputs:
   sums and patterns, divisibility, primes, remainders, counting, digit tricks, formulas.
   It does NOT handle real numbers, geometry, limits, or claims that need infinity in an essential
   way. If it doesn't fit, say so in one plain sentence, answer from what is known if you can, and
   offer a nearby whole-number question that does fit (e.g. "Is pi irrational?" doesn't fit; "Is
   every whole number from 1 to 1,000 a sum of four perfect squares?" does).

2. **Write the claim spec** to `plainproof-runs/<slug>.json` in the working directory:

   ```json
   {
     "title": "Two odd numbers",
     "question": "<the person's words, verbatim>",
     "plain_restatement": "Adding any two odd numbers gives an even number.",
     "variables": [
       {"name": "a", "min": -1000, "max": 1000, "meaning": "the first number"},
       {"name": "b", "min": -1000, "max": 1000, "meaning": "the second number"}
     ],
     "assumptions": ["negative numbers count too"],
     "fidelity_note": "Only numbers from -1,000 to 1,000 are covered.",
     "c_function": "int claim_holds(long long a, long long b) {\n    if (a % 2 == 0 || b % 2 == 0) return 1;\n    return (a + b) % 2 == 0;\n}"
   }
   ```

   Rules for a good spec (Aristotle will reject a sloppy one):
   - `plain_restatement` says EXACTLY what `claim_holds` tests, readable by a 14-year-old.
   - `c_function` defines `int claim_holds(long long v1, ...)`: one parameter per variable, in order.
     Pure integer arithmetic; helpers `static`; no I/O, `main`, malloc, recursion or floating point.
     Inputs outside the claim's scope (e.g. even numbers above) return 1 ("nothing to check").
   - **No overflow anywhere inside the ranges**: keep intermediates far below 9.2e18; write
     `d <= x / d`, not `d * d <= x`. Prefer modest ranges (hundreds to a few million) and short loops.
     Aristotle must reason about this code; simple beats clever.
   - Record every interpretation choice in `assumptions`; be honest in `fidelity_note` about what a
     finite range doesn't establish (and flag famous open problems like Goldbach or Collatz).

3. **Confirm with the person.** Show the plain restatement, the ranges and the assumptions as a short
   list, and ask "Is that what you meant?". Revise until they agree. Skip this only if they told you
   to just go ahead.

4. **Free quick test:** `PP check plainproof-runs/<slug>.json --check-only`.
   - **Counterexample** → the claim is false. Explain with the actual numbers, worked through by hand
     (e.g. "40×40 + 40 + 41 = 1681 = 41 × 41, so not prime"). Stop: no credits needed.
   - **Overflow** or **compile error** → fix the spec (smaller range, safer arithmetic) and rerun.
     Never send such a spec to Aristotle.
   - **No counterexample** → say it is strong evidence but not proof, then offer step 5.

5. **Proof by Aristotle (costs credits, typically tens of minutes)**: only after the person agrees.
   - Needs the SDK: `python3 -c "import aristotlelib"`; if missing, `pip install "aristotlelib>=3"`
     (add `--user` or use a venv as the environment requires).
   - Needs a key: `ARISTOTLE_API_KEY`, or a stored login. If neither, run `aristotle login` and
     pass on the link and code it prints; never ask the person to paste a key into the chat.
   - Start without blocking: `PP check plainproof-runs/<slug>.json --prove --no-wait`. It prints the
     run folder and a web link. Tell the person both, then follow it with
     `PP resume <run-folder>` (run in the background, or have the person ask you later; see the
     `resume` skill).

6. **Explain the verdict** from `<run-folder>/aristotle.json` and `quick.json`, in at most ~150 words:
   lead with the verdict; say exactly what was established and its range limit ("proved for every
   n from 0 to 100,000 — not beyond"); for a refutation, show the counterexample as a worked example;
   for a proof, give the everyday intuition for why it's true if there is a simple one; end with one
   natural follow-up question. Ignore `answer.md`'s fixed wording when you can say it better.

## Status meanings (aristotle.json)

| status | say |
|---|---|
| `PROVED` | Proved by a proof-checking computer, for every case in range. |
| `REFUTED` | False; `evidence`/`message` give the counterexample. |
| `FAILED` / `IN_PROGRESS` / run `OUT_OF_BUDGET` | No verdict yet. Report the reason plainly; offer to retry or narrow the range. |

## Examples bundled with the plugin

`PP examples` lists them; `PP check <path> --check-only` runs one. Euler's prime formula
(`primes-formula.json`) is a good demo: it fails at n = 40.
