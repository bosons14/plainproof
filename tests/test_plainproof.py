import asyncio
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from plainproof import aristotle_run, explain, quickcheck, translate
from plainproof.spec import ClaimSpec, Variable

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def two_odds(c_body="return ((a + b) % 2) == 0;"):
    return ClaimSpec(
        question="Is the sum of two odd numbers always even?",
        plain_restatement="Adding any two odd numbers gives an even number.",
        variables=[Variable("a", -999, 999), Variable("b", -999, 999)],
        c_function="int claim_holds(long long a, long long b) {\n"
                   "    if (a % 2 == 0 || b % 2 == 0) return 1;  /* only odd pairs matter */\n"
                   f"    {c_body}\n}}",
        title="Two odds",
    )


@pytest.mark.parametrize("name,verdict", [
    ("odd-sums-are-squares", "no-counterexample"),
    ("primes-formula", "counterexample"),
    ("goldbach", "no-counterexample"),
    ("triangle-handshakes", "no-counterexample"),
    ("overflow-demo", "overflow"),
])
def test_examples(name, verdict):
    spec = ClaimSpec.load(EXAMPLES / f"{name}.json")
    assert quickcheck.run(spec).verdict == verdict


def test_euler_counterexample_is_40():
    r = quickcheck.run(ClaimSpec.load(EXAMPLES / "primes-formula.json"))
    assert r.inputs == {"n": 40}


def test_two_variables_exhaustive():
    r = quickcheck.run(two_odds())
    assert r.verdict == "no-counterexample" and r.exhaustive and r.tried == 1999 * 1999


def test_two_variables_counterexample():
    r = quickcheck.run(two_odds("return ((a + b) % 4) == 0;"))
    assert r.verdict == "counterexample"
    a, b = r.inputs["a"], r.inputs["b"]
    assert a % 2 and b % 2 and (a + b) % 4


def test_sampling_hits_both_ends():
    spec = ClaimSpec(question="q", plain_restatement="n is below the top",
                     variables=[Variable("n", 0, 10**12)],
                     c_function="int claim_holds(long long n) { return n < 1000000000000LL; }")
    r = quickcheck.run(spec, budget=1000)
    assert r.verdict == "counterexample" and r.inputs == {"n": 10**12} and not r.exhaustive


def test_compile_error_reported():
    spec = two_odds("return oops;")
    r = quickcheck.run(spec)
    assert r.verdict == "error" and "compile" in r.detail


def test_spec_rejects_unsafe_code():
    with pytest.raises(ValueError):
        ClaimSpec(question="q", plain_restatement="x", variables=[Variable("n", 0, 1)],
                  c_function='int claim_holds(long long n) { system("rm -rf /"); return 1; }').validate()


def test_translate_parses_claude_reply(monkeypatch):
    reply = {
        "title": "Two odds", "can_encode": True, "why_not": "",
        "plain_restatement": "Adding two odd numbers gives an even number.",
        "variables": [{"name": "a", "min": -99, "max": 99, "meaning": "first"},
                      {"name": "b", "min": -99, "max": 99, "meaning": "second"}],
        "c_function": two_odds().c_function, "assumptions": ["negative numbers count too"],
        "fidelity_note": "Only numbers from -99 to 99.",
    }
    calls = []

    def fake(system, user, model=None, max_tokens=0):
        calls.append(user)
        # First reply is broken JSON, to exercise the retry.
        return "<spec>{not json</spec>" if len(calls) == 1 else f"<spec>{json.dumps(reply)}</spec>"

    monkeypatch.setattr(translate, "ask_claude", fake)
    spec = translate.translate("Is odd plus odd even?")
    assert spec.question == "Is odd plus odd even?" and len(spec.variables) == 2 and len(calls) == 2


def test_translate_cannot_encode(monkeypatch):
    monkeypatch.setattr(translate, "ask_claude", lambda *a, **k:
                        '<spec>{"can_encode": false, "why_not": "Circles need decimals."}</spec>')
    with pytest.raises(translate.CannotEncode, match="decimals"):
        translate.translate("Is pi irrational?")


def test_prompt_states_ranges_and_property():
    prompt = aristotle_run.build_prompt(two_odds())
    assert "-999 <= a <= 999 and -999 <= b <= 999" in prompt
    assert aristotle_run.PROPERTY_NAME in prompt and "counterexample" in prompt


def test_submit_uploads_only_claim_c(monkeypatch):
    import aristotlelib

    seen = {}

    async def fake_create(cls, prompt, tar_file_path=None, public_file_path=None,
                          agent_questions_setting=None, name=None):
        with tarfile.open(tar_file_path) as tar:
            seen["names"] = tar.getnames()
            member = next(m for m in tar.getmembers() if m.name.endswith("claim.c"))
            seen["claim"] = tar.extractfile(member).read().decode()
        seen.update(prompt=prompt, questions=agent_questions_setting, name=name)
        return SimpleNamespace(project_id="p-123", web_url=lambda: "https://example/p-123")

    monkeypatch.setattr(aristotlelib.Project, "create", classmethod(fake_create))
    pid, url = asyncio.run(aristotle_run.submit(two_odds()))
    assert pid == "p-123"
    assert [n for n in seen["names"] if n.endswith(".c")] and all("claim" in n for n in seen["names"])
    assert "Adding any two odd numbers" in seen["claim"]
    assert seen["questions"] == aristotlelib.AgentQuestionsSetting.DISABLED


def test_poll_collects_verdict(monkeypatch):
    import aristotlelib
    from aristotlelib.declaration import DeclarationEvidence, DeclarationStatus

    statuses = iter(["QUEUED", "IN_PROGRESS", "COMPLETE"])

    async def fake_resolve(cls, ref):
        return ref

    async def fake_tasks(self, limit=10, **kw):
        s = next(statuses)
        return [SimpleNamespace(status=aristotlelib.TaskStatus(s), output_summary="done")], None

    async def fake_decls(self, declaration_type=None):
        return [SimpleNamespace(name=aristotle_run.PROPERTY_NAME, status_name=DeclarationStatus.REFUTED.name,
                                evidence=DeclarationEvidence.COUNTEREXAMPLE, evidence_message="a=1, b=1",
                                description=None, failure_reason_name=None)]

    monkeypatch.setattr(aristotlelib.Project, "resolve_id", classmethod(fake_resolve))
    monkeypatch.setattr(aristotlelib.Project, "get_tasks", fake_tasks)
    monkeypatch.setattr(aristotlelib.Project, "get_declarations", fake_decls)
    ticks = []
    result = asyncio.run(aristotle_run.poll("p-123", interval=0, on_tick=lambda s, t: ticks.append(s)))
    assert ticks == ["QUEUED", "IN_PROGRESS", "COMPLETE"]
    p = result.main_property()
    assert p.status == "REFUTED" and p.evidence == "COUNTEREXAMPLE"
    text = explain.fallback(two_odds(), None, result)
    assert text.startswith("FALSE") and "a=1, b=1" in text


def test_prompt_command_matches_cli_submission(capsys):
    from plainproof.cli import main

    assert main(["prompt", str(EXAMPLES / "goldbach.json"), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    spec = ClaimSpec.load(EXAMPLES / "goldbach.json")
    assert out["prompt"] == aristotle_run.build_prompt(spec)
    assert out["files"]["claim.c"] == spec.claim_c_source()
    assert out["property_name"] == aristotle_run.PROPERTY_NAME
