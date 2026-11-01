---
name: resume
description: "This skill should be used when the user asks how a plainproof or Aristotle maths proof is going, whether it finished, \"what did Aristotle say\", or wants the answer to a proof started earlier, or runs /plainproof:resume. Follows a run in plainproof-runs/ to its end and explains the verdict in plain language."
metadata:
  version: "0.1.0"
---

# plainproof: check on a proof

1. **Find the run.** Runs live in `plainproof-runs/<date>-<title>/` in the working directory; one that
   went to Aristotle holds `aristotle_project.txt`. If the person didn't say which, take the newest
   such folder and name its title so they can correct you.

2. **Follow it.** Run `"${CLAUDE_PLUGIN_ROOT}/bin/plainproof" resume <run-folder>` (find the launcher
   as the `ask` skill describes if the variable is empty). It polls every 30 seconds until the run
   ends and writes `aristotle.json` and `answer.md`. Runs often take tens of minutes: run it in the
   background and tell the person roughly where it stands, rather than blocking the conversation.
   Stopping the wait does not stop Aristotle.

3. **Explain the verdict** as the `ask` skill's step 6 describes: verdict first, the exact range it
   covers, a worked counterexample if refuted, the everyday intuition if proved, one follow-up idea.
   No jargon.

4. **No verdict** (`FAILED`, `OUT_OF_BUDGET`, `CANCELED`, or the property never registered): say so
   plainly with the reason from `aristotle.json`, and offer to narrow the range or simplify
   `claim_holds` in `spec.json` and try again. Don't start a new paid run without the person's go-ahead.
