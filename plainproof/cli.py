"""plainproof: ask number questions in plain English; get them tested, then proved or refuted by Aristotle.

    plainproof ask "Is the sum of two odd numbers always even?"
    plainproof check examples/goldbach.json            # no AI needed, free
    plainproof check examples/odd-sums-are-squares.json --prove
    plainproof resume plainproof-runs/<run-folder>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import textwrap
import time
from dataclasses import asdict
from pathlib import Path

from . import __version__, explain, quickcheck
from .spec import ClaimSpec, slugify

RUNS_DIR = Path("plainproof-runs")
WIDTH = 88


def say(text: str = "", indent: str = "") -> None:
    for para in text.split("\n"):
        print(textwrap.fill(para, WIDTH, initial_indent=indent, subsequent_indent=indent) if para else "")


def heading(text: str) -> None:
    print(f"\n── {text} " + "─" * max(0, WIDTH - len(text) - 4))


def confirm(question: str, default: bool, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return default
    hint = "Y/n" if default else "y/N"
    answer = input(f"{question} [{hint}] ").strip().lower()
    return default if not answer else answer.startswith("y")


def show_spec(spec: ClaimSpec, show_code: bool = False) -> None:
    heading("What will be checked")
    say(spec.plain_restatement, "  ")
    print()
    for v in spec.variables:
        say(f"• {v.plain_range()}" + (f"  ({v.meaning})" if v.meaning else ""), "  ")
    for a in spec.assumptions:
        say(f"• Assuming {a[0].lower() + a[1:] if a else a}", "  ")
    if spec.fidelity_note:
        print()
        say(f"Note: {spec.fidelity_note}", "  ")
    if show_code:
        heading("Translation for the computer (claim.c)")
        print(textwrap.indent(spec.c_function.strip(), "  "))


def new_run_dir(spec: ClaimSpec) -> Path:
    path = RUNS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(spec.title or spec.question)}"
    path.mkdir(parents=True, exist_ok=True)
    spec.save(path / "spec.json")
    (path / "claim.c").write_text(spec.claim_c_source())
    return path


def finish(run_dir: Path, spec: ClaimSpec, quick, result) -> None:
    heading("Answer")
    text = explain.explain(spec, quick, result)
    say(text, "  ")
    md = [f"# {spec.title or 'Claim'}", "", f"**Question:** {spec.question}", "",
          f"**Claim tested:** {spec.plain_restatement}", "", f"**Inputs:** {spec.ranges_plain()}", "",
          "## Answer", "", text, ""]
    if result is not None:
        md += [f"Aristotle project: {result.web_url}", ""]
    (run_dir / "answer.md").write_text("\n".join(md))
    print()
    say(f"Saved to {run_dir}/ (answer.md, spec.json, claim.c)", "  ")


def run_quick(spec: ClaimSpec, run_dir: Path):
    heading("Quick test (free, on this computer)")
    q = quickcheck.run(spec)
    (run_dir / "quick.json").write_text(json.dumps(asdict(q), indent=2))
    say(q.plain(spec), "  ")
    if q.verdict == "error":
        say(q.detail, "    ")
    return q


def run_aristotle(spec: ClaimSpec, run_dir: Path, wait: bool):
    from . import aristotle_run

    heading("Sending to Aristotle for a proof")
    say("This uses Aristotle credits and usually takes tens of minutes.", "  ")
    project_id, url = asyncio.run(aristotle_run.submit(spec))
    (run_dir / "aristotle_project.txt").write_text(project_id + "\n")
    say(f"Started. Follow it in the browser: {url}", "  ")
    if not wait:
        say(f"Check back any time with: plainproof resume {run_dir}", "  ")
        return None
    return poll_aristotle(project_id, run_dir)


def poll_aristotle(project_id: str, run_dir: Path):
    from . import aristotle_run

    friendly = {"QUEUED": "waiting for a free slot", "IN_PROGRESS": "working on the proof",
                "COMPLETE": "finished", "COMPLETE_WITH_ERRORS": "finished, partly",
                "OUT_OF_BUDGET": "stopped: ran out of budget", "FAILED": "stopped by an error",
                "CANCELED": "cancelled"}

    def tick(status: str, elapsed: float) -> None:
        mins = int(elapsed // 60)
        print(f"\r  Aristotle is {friendly.get(status, status.lower())} … {mins} min", end="", flush=True)

    try:
        result = asyncio.run(aristotle_run.poll(project_id, on_tick=tick))
    except KeyboardInterrupt:
        print()
        say(f"Stopped waiting (Aristotle keeps going). Resume with: plainproof resume {run_dir}", "  ")
        return None
    print()
    (run_dir / "aristotle.json").write_text(result.to_json())
    return result


def cmd_ask(args) -> int:
    from .translate import CannotEncode, translate

    question = " ".join(args.question).strip()
    if not question:
        question = input("What would you like to know? ").strip()
    say("Turning your question into something a computer can check …")
    try:
        spec = translate(question)
        while True:
            show_spec(spec, args.show_code)
            if args.yes or not sys.stdin.isatty():
                break
            print()
            fix = input("Is that what you meant? Press Enter if yes, or type what to change: ").strip()
            if not fix:
                break
            say("Revising …")
            spec = translate(question, feedback=fix, previous=spec)
    except CannotEncode as e:
        heading("This one can't be checked this way")
        say(str(e), "  ")
        return 2
    return proceed(spec, args)


def cmd_check(args) -> int:
    spec = ClaimSpec.load(args.spec)
    show_spec(spec, args.show_code)
    return proceed(spec, args)


def proceed(spec: ClaimSpec, args) -> int:
    run_dir = new_run_dir(spec)
    quick = run_quick(spec, run_dir)
    result = None
    if quick.verdict == "counterexample":
        say("No proof needed: a single failing case settles it. (No Aristotle credits spent.)", "  ")
    elif quick.verdict in ("overflow", "error"):
        say("Fix this before asking for a proof: Aristotle would reject it for the same reason.", "  ")
        if quick.verdict == "error":
            return 1
    elif args.check_only:
        pass
    elif args.prove or confirm("Ask Aristotle to PROVE it for every case in range?", False, args.yes):
        result = run_aristotle(spec, run_dir, wait=not args.no_wait)
        if result is None and args.no_wait:
            return 0
    finish(run_dir, spec, quick, result)
    return 0


def cmd_resume(args) -> int:
    target = Path(args.target)
    if target.is_dir():
        run_dir = target
        project_id = (run_dir / "aristotle_project.txt").read_text().strip()
    else:
        project_id = args.target
        run_dir = RUNS_DIR / f"resume-{project_id[:8]}"
        run_dir.mkdir(parents=True, exist_ok=True)
        if not (run_dir / "spec.json").exists():
            raise SystemExit("Pass the run folder (it holds the claim) rather than a bare project id.")
    spec = ClaimSpec.load(run_dir / "spec.json")
    quick_path = run_dir / "quick.json"
    quick = quickcheck.QuickResult(**json.loads(quick_path.read_text())) if quick_path.exists() else None
    result = poll_aristotle(project_id, run_dir)
    finish(run_dir, spec, quick, result)
    return 0


def cmd_examples(args) -> int:
    here = Path(__file__).resolve().parent.parent / "examples"
    for f in sorted(here.glob("*.json")):
        s = ClaimSpec.load(f)
        say(f"{f.relative_to(Path.cwd()) if f.is_relative_to(Path.cwd()) else f}", "")
        say(s.question, "    ")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="plainproof", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"plainproof {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--prove", action="store_true", help="send to Aristotle without asking")
        sp.add_argument("--check-only", action="store_true", help="only the free local test")
        sp.add_argument("--no-wait", action="store_true", help="start the proof and return; resume later")
        sp.add_argument("--show-code", action="store_true", help="also show the C translation")
        sp.add_argument("-y", "--yes", action="store_true", help="accept the translation and every prompt")

    a = sub.add_parser("ask", help="ask a question in plain English (needs ANTHROPIC_API_KEY)")
    a.add_argument("question", nargs="*")
    common(a)
    a.set_defaults(fn=cmd_ask)

    c = sub.add_parser("check", help="check a saved claim spec (no AI needed)")
    c.add_argument("spec")
    common(c)
    c.set_defaults(fn=cmd_check)

    r = sub.add_parser("resume", help="wait for, and explain, an Aristotle run started earlier")
    r.add_argument("target", help="the run folder under plainproof-runs/")
    r.set_defaults(fn=cmd_resume)

    e = sub.add_parser("examples", help="list the bundled example claims")
    e.set_defaults(fn=cmd_examples)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print()
        return 130
    except RuntimeError as err:
        say(f"Error: {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
