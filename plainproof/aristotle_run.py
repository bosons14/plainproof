"""Send a claim to Aristotle and bring back its verdict.

Aristotle proves properties of C code. plainproof uploads one file, claim.c, and asks for one
property: claim_holds returns 1, without any undefined behaviour, for every input in range.
Runs cost credits and usually take tens of minutes.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .spec import ClaimSpec

PROPERTY_NAME = "claim_holds_everywhere"
TERMINAL = {"COMPLETE", "COMPLETE_WITH_ERRORS", "OUT_OF_BUDGET", "FAILED", "CANCELED"}


def build_prompt(spec: ClaimSpec) -> str:
    args = ", ".join(v.name for v in spec.variables)
    return (
        f"claim.c defines `int claim_holds({spec.signature_args()})`.\n\n"
        f"Verify exactly one property, named `{PROPERTY_NAME}`:\n"
        f"for every input with {spec.ranges_c()}, the call claim_holds({args}) terminates, has no undefined "
        f"behaviour (no signed integer overflow, no division by zero, no out-of-bounds access), and returns 1.\n\n"
        f"If the property does not hold, refute it with a concrete counterexample input.\n"
        f"These ranges are the only assumptions; do not add others and do not ask questions.\n\n"
        f"Background in plain English (what the function is meant to check): {spec.plain_restatement}"
    )


@dataclass
class PropertyResult:
    name: str
    status: str
    evidence: str | None = None
    message: str | None = None
    description: str | None = None
    failure_reason: str | None = None


@dataclass
class AristotleResult:
    project_id: str
    web_url: str
    run_status: str
    summary: str | None = None
    properties: list[PropertyResult] = field(default_factory=list)

    def main_property(self) -> PropertyResult | None:
        for p in self.properties:
            if p.name == PROPERTY_NAME:
                return p
        return self.properties[0] if self.properties else None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _require_sdk():
    try:
        import aristotlelib  # noqa: F401
    except ImportError as e:
        raise RuntimeError('Install the Aristotle SDK: pip install "aristotlelib>=3"') from e


async def submit(spec: ClaimSpec, name: str | None = None) -> tuple[str, str]:
    """Create the Aristotle project; returns (project_id, web_url)."""
    _require_sdk()
    from aristotlelib import AgentQuestionsSetting, Project

    with tempfile.TemporaryDirectory(prefix="plainproof-upload-") as tmp:
        folder = Path(tmp) / "claim"
        folder.mkdir()
        (folder / "claim.c").write_text(spec.claim_c_source())
        project = await Project.create_from_directory(
            prompt=build_prompt(spec),
            project_dir=folder,
            agent_questions_setting=AgentQuestionsSetting.DISABLED,
            name=(name or spec.title or "plainproof claim")[:80],
        )
    return project.project_id, project.web_url()


async def poll(project_id: str, interval: float = 30.0, timeout: float = 4 * 3600,
               on_tick=None) -> AristotleResult:
    """Wait for the latest run to end, then collect the property verdicts."""
    _require_sdk()
    from aristotlelib import Project
    from aristotlelib.project import project_web_url

    project_id = await Project.resolve_id(project_id)
    # A Project object only needs its id for these calls.
    project = Project.model_construct(project_id=project_id)
    started = time.monotonic()
    status = "UNKNOWN"
    summary = None
    while True:
        tasks, _ = await project.get_tasks(limit=1)
        if tasks:
            status = tasks[0].status.value
            summary = tasks[0].output_summary
        if on_tick:
            on_tick(status, time.monotonic() - started)
        if status in TERMINAL:
            break
        if time.monotonic() - started > timeout:
            break
        await asyncio.sleep(interval)

    props = []
    from aristotlelib.declaration import DeclarationType
    for d in await project.get_declarations(DeclarationType.PROPERTY):
        props.append(PropertyResult(
            name=d.name, status=d.status_name,
            evidence=d.evidence.name if d.evidence is not None else None,
            message=d.evidence_message, description=d.description,
            failure_reason=d.failure_reason_name,
        ))
    return AristotleResult(project_id, project_web_url(project_id), status, summary, props)
