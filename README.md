# plainproof

**Ask a question about numbers in plain English. Get a plain-English answer that a
proof-checking computer stands behind.**

```
$ plainproof ask "If I add up the first n odd numbers, do I always get a perfect square?"

── What will be checked ──────────────────────────────────────────────
  For every whole number n, 1 + 3 + 5 + ... (the first n odd numbers) equals n times n.
  • n from 0 to 100,000  (how many odd numbers are added)

Is that what you meant? Press Enter if yes, or type what to change:

── Quick test (free, on this computer) ───────────────────────────────
  Tried every one of 100,001 cases and the claim held each time.
  That is strong evidence, not a proof.

Ask Aristotle to PROVE it for every case in range? [y/N] y
  Aristotle is working on the proof … 23 min

── Answer ────────────────────────────────────────────────────────────
  Yes, and it is now proved ...
```

No formulas, symbols or proof language anywhere. You read and confirm a sentence; plainproof does the rest.

## How it works

```
your question ──► Claude restates it as one exact sentence + a tiny C function
                         │            (you confirm or correct the sentence)
                         ▼
                 Quick test: run it on up to 20 million cases locally (free, seconds)
                         │   ── a failing case? → answer is "No", shown with real numbers; stop.
                         ▼
                 Aristotle: prove the function says "true" for EVERY case in range
                         │   (or refute it with a counterexample)
                         ▼
                 Claude explains the verdict in everyday language, limits included
```

### Why C code?

On 27 Oct 2026 Harmonic relaunched Aristotle as a verifier for **code** (C, Verilog, and Rust where
enabled). The current SDK (`aristotlelib` 3.x) says outright that it no longer verifies pure
mathematics or hand-written Lean. So plainproof turns each maths claim into a short C function
`claim_holds(...)`, which returns 1 when the claim is true, and asks Aristotle to prove it always
returns 1 across the input range. That is a property of C code, which is the kind of thing Aristotle now proves.

## What it can and can't do

**Good fit:** claims about whole numbers. Sums and patterns, divisibility, primes, remainders,
counting (handshakes, arrangements, coins), digit tricks, number puzzles, checking a formula
someone sent you.

**Honest limits:**

- **A proof covers the stated range, not "all numbers".** "Proved for every n up to 100,000" is
  airtight inside that range and says nothing beyond it. plainproof always says which range.
- No real numbers, geometry, limits or infinity-based claims. The translator tells you when a
  question doesn't fit and suggests a nearby one that does.
- Up to three whole-number inputs per claim.
- Open problems (Goldbach, Collatz) can be checked across a range, which is a nice way to *see* why
  they are believed. Nothing finite settles them, and plainproof says so.
- Aristotle runs cost credits and take tens of minutes. The free quick test runs first, so a false
  claim never costs you a run.

## Use it inside Claude Code (plugin)

```text
/plugin marketplace add bosons14/plainproof
/plugin install plainproof@plainproof
```

The plugin also connects **Aristotle's hosted MCP server** (`https://aristotle.harmonic.fun/mcp`).
The first time a proof is needed, run `/mcp`, pick `aristotle`, choose **Authenticate** and sign in
with your Aristotle account. After that, Claude sends claims to Aristotle directly, with no SDK install or API key.
If the MCP route isn't available, the plugin falls back to the command-line SDK.

Then just ask Claude Code a question, e.g. *"Is it true that n² + n + 41 is always prime?"*, or run
`/plainproof:ask`. Inside Claude Code, Claude itself does the translating and explaining, so **no
Anthropic API key is needed**: only Python and a C compiler, plus an Aristotle sign-in for proofs. `/plainproof:resume` checks on a proof that is still running.

## Install the command-line tool

```bash
git clone https://github.com/bosons14/plainproof && cd plainproof
pip install -e .            # Python 3.10+, needs a C compiler (gcc or clang)
                            # (or run ./bin/plainproof without installing)
aristotle login             # once; or export ARISTOTLE_API_KEY=...
export ANTHROPIC_API_KEY=... # for translating questions and explaining answers
```

## Use

```bash
plainproof ask "Is the sum of two odd numbers always even?"
plainproof ask "Does n*n + n + 41 always give a prime?" --check-only   # free test only
plainproof ask "..." --prove --no-wait      # start the proof, come back later
plainproof resume plainproof-runs/<folder>  # pick up a run and explain it

plainproof examples                         # bundled claims
plainproof check examples/goldbach.json     # runs a saved claim (no Anthropic key needed)
plainproof check examples/odd-sums-are-squares.json --prove
```

Each run is saved under `plainproof-runs/<date>-<title>/`:

| file | what it is |
|---|---|
| `answer.md` | the plain-English answer |
| `spec.json` | the claim: restatement, ranges, assumptions, C function. Editable by hand |
| `claim.c` | exactly what was sent to Aristotle |
| `quick.json`, `aristotle.json` | raw verdicts |

`plainproof prompt spec.json [--json]` prints exactly what goes to Aristotle (prompt and `claim.c`),
for sending it through the MCP server or the web app yourself.

### Without a terminal: claude.ai

Add `https://aristotle.harmonic.fun/mcp` as a custom connector in claude.ai's connector settings and
sign in with Aristotle. Claude can then write the claim, send it to Aristotle and explain the result
right in the chat.

`--show-code` prints the C translation, if you're curious or want to double-check it.

## Trust: what you're relying on

1. **The translation.** Claude turns your words into the C function. The Aristotle proof is about
   that function. Read the "What will be checked" sentence carefully; it is the contract.
   `--show-code` shows the function itself.
2. **Aristotle's proof.** Once Aristotle reports PROVED, the result is machine-checked.
3. **The quick test** is evidence only. It can show a claim is false; it can never show it is true.

## Settings

| variable | default | purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | translation and explanations (without it, `check` still works and answers use fixed wording) |
| `PLAINPROOF_MODEL` | `claude-sonnet-5-5` | Claude model used |
| `ARISTOTLE_API_KEY` | from `aristotle login` | Aristotle access |

## Development

```bash
pytest -q tests   # 17 tests; the Aristotle and Claude calls are stubbed
```

MIT licence. Not affiliated with Harmonic or Anthropic.
