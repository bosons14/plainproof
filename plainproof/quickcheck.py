"""Free, instant local check: compile the claim and try it on many inputs before spending credits.

Testing can find a counterexample but can never prove a claim; that is what Aristotle is for.
The harness is built with the undefined-behaviour sanitizer, so an arithmetic overflow, which
would make Aristotle refuse the claim, is caught here and reported with the input that caused it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .spec import ClaimSpec

DEFAULT_BUDGET = 20_000_000
"""Most inputs tried locally; beyond it, plainproof samples evenly across the range, ends included."""


@dataclass
class QuickResult:
    verdict: str
    """"no-counterexample", "counterexample", "overflow" or "error"."""
    tried: int = 0
    exhaustive: bool = False
    inputs: dict[str, int] = field(default_factory=dict)
    detail: str = ""

    def plain(self, spec: ClaimSpec) -> str:
        where = ", ".join(f"{k} = {v:,}" for k, v in self.inputs.items()) or "some input"
        if self.verdict == "no-counterexample":
            how = "every one of" if self.exhaustive else "an even spread of"
            return (
                f"Tried {how} {self.tried:,} cases ({spec.ranges_plain()}) and the claim held each time. "
                "That is strong evidence, not a proof."
            )
        if self.verdict == "counterexample":
            return f"The claim is FALSE. It fails when {where}."
        if self.verdict == "overflow":
            return (
                f"The calculation got too big for the computer's numbers at {where}. "
                "Shrink the range, or let the translator rewrite the arithmetic to stay small."
            )
        return f"The local check could not run: {self.detail}"


def _steps(spec: ClaimSpec, budget: int) -> list[int]:
    """A stride per variable so the number of cases stays within budget."""
    if spec.search_space() <= budget:
        return [1] * len(spec.variables)
    per_dim = max(2, int(budget ** (1 / len(spec.variables))))
    return [max(1, (v.max - v.min) // (per_dim - 1)) for v in spec.variables]


def build_harness(spec: ClaimSpec, steps: list[int]) -> str:
    vs = spec.variables
    globals_ = "\n".join(f"static volatile long long cur_{v.name};" for v in vs)
    report_fmt = " ".join(f"{v.name}=%lld" for v in vs)
    report_args = ", ".join(f"cur_{v.name}" for v in vs)
    lines = [
        "#include <signal.h>",
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <unistd.h>",
        '#include "claim.c"',
        globals_,
        "static void on_abort(int sig) {",
        "    (void)sig;",
        f'    fprintf(stdout, "OVERFLOW {report_fmt}\\n", {report_args});',
        "    fflush(stdout);",
        "    _exit(3);",
        "}",
        "int main(void) {",
        "    signal(SIGABRT, on_abort);",
        "    signal(SIGILL, on_abort);",
        "    signal(SIGFPE, on_abort);",
        "    unsigned long long tried = 0;",
    ]
    indent = "    "
    for v, step in zip(vs, steps):
        # Walk by stride, then make sure the top of the range is visited too.
        lines.append(
            f"{indent}for (long long {v.name} = {v.min}LL, done_{v.name} = 0; !done_{v.name}; ) {{"
        )
        indent += "    "
        lines.append(f"{indent}cur_{v.name} = {v.name};")
    call_args = ", ".join(v.name for v in vs)
    lines += [
        f"{indent}if (!claim_holds({call_args})) {{",
        f'{indent}    printf("COUNTEREXAMPLE {report_fmt}\\n", {call_args});',
        f"{indent}    return 1;",
        f"{indent}}}",
        f"{indent}tried++;",
    ]
    for v, step in reversed(list(zip(vs, steps))):
        lines += [
            f"{indent}if ({v.name} == {v.max}LL) done_{v.name} = 1;",
            f"{indent}else if ({v.max}LL - {v.name} < {step}LL) {v.name} = {v.max}LL;",
            f"{indent}else {v.name} += {step}LL;",
        ]
        indent = indent[:-4]
        lines.append(f"{indent}}}")
    lines += ['    printf("OK %llu\\n", tried);', "    return 0;", "}"]
    return "\n".join(lines) + "\n"


def _parse_inputs(spec: ClaimSpec, tokens: list[str]) -> dict[str, int]:
    out = {}
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = int(v)
    return {v.name: out[v.name] for v in spec.variables if v.name in out}


def run(spec: ClaimSpec, budget: int = DEFAULT_BUDGET, timeout: float = 120.0) -> QuickResult:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if compiler is None:
        return QuickResult("error", detail="no C compiler found (install gcc or clang)")
    steps = _steps(spec, budget)
    exhaustive = all(s == 1 for s in steps)
    with tempfile.TemporaryDirectory(prefix="plainproof-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "claim.c").write_text(spec.claim_c_source())
        (tmp_path / "harness.c").write_text(build_harness(spec, steps))
        exe = tmp_path / "harness"
        build = subprocess.run(
            [compiler, "-std=c11", "-O2", "-fsanitize=undefined", "-fno-sanitize-recover=all",
             "-o", str(exe), str(tmp_path / "harness.c"), "-lm"],
            capture_output=True, text=True,
        )
        if build.returncode != 0:
            return QuickResult("error", detail="the C translation does not compile:\n" + build.stderr[-2000:])
        try:
            env = dict(os.environ, UBSAN_OPTIONS="abort_on_error=1:halt_on_error=1:print_stacktrace=0")
            proc = subprocess.run([str(exe)], capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return QuickResult("error", detail=f"checking took longer than {timeout:.0f}s; try a smaller range")
    out = proc.stdout.strip().splitlines()
    last = out[-1] if out else ""
    tokens = last.split()
    if last.startswith("OK"):
        return QuickResult("no-counterexample", tried=int(tokens[1]), exhaustive=exhaustive)
    if last.startswith("COUNTEREXAMPLE"):
        return QuickResult("counterexample", inputs=_parse_inputs(spec, tokens[1:]), exhaustive=exhaustive)
    if last.startswith("OVERFLOW"):
        return QuickResult("overflow", inputs=_parse_inputs(spec, tokens[1:]), detail=proc.stderr[-1000:])
    if "runtime error" in proc.stderr:
        return QuickResult("overflow", detail=proc.stderr[-1000:])
    return QuickResult("error", detail=(proc.stderr or proc.stdout)[-2000:] or f"exit code {proc.returncode}")
