"""A "claim spec": one everyday-language maths claim, turned into a small C function.

Aristotle (since its October 2026 relaunch) verifies C, Verilog and Rust code, not pure maths.
So plainproof restates a claim as a C function `claim_holds(...)` that returns 1 when the claim
is true for the given whole numbers, and asks Aristotle to prove it returns 1 for every input
in a stated range. The spec is the bridge between the two worlds, saved as JSON so a run can be
reviewed, edited by hand, re-checked and resumed.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

C_INT_MIN = -(2**63)
C_INT_MAX = 2**63 - 1
MAX_VARIABLES = 3


@dataclass
class Variable:
    name: str
    min: int
    max: int
    meaning: str = ""

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,15}", self.name):
            raise ValueError(f"Variable name {self.name!r} must be a short lowercase C identifier")
        if self.min > self.max:
            raise ValueError(f"Variable {self.name}: min {self.min} is above max {self.max}")
        if self.min < C_INT_MIN or self.max > C_INT_MAX:
            raise ValueError(f"Variable {self.name}: range must fit in a 64-bit signed integer")

    def plain_range(self) -> str:
        return f"{self.name} from {self.min:,} to {self.max:,}"


@dataclass
class ClaimSpec:
    question: str
    """What the person asked, in their own words."""
    plain_restatement: str
    """The exact claim being tested, in plain words, with no symbols the person didn't use."""
    variables: list[Variable]
    c_function: str
    """C source defining `int claim_holds(long long v1, ...)`, one parameter per variable, in order."""
    assumptions: list[str] = field(default_factory=list)
    fidelity_note: str = ""
    """What is lost in translation, e.g. "only checks numbers up to 1,000,000"."""
    title: str = ""

    def validate(self) -> None:
        if not self.variables:
            raise ValueError("A claim needs at least one whole-number variable")
        if len(self.variables) > MAX_VARIABLES:
            raise ValueError(f"At most {MAX_VARIABLES} variables are supported")
        names = [v.name for v in self.variables]
        if len(set(names)) != len(names):
            raise ValueError("Variable names must be distinct")
        for v in self.variables:
            v.validate()
        if not re.search(r"\bint\s+claim_holds\s*\(", self.c_function):
            raise ValueError("c_function must define `int claim_holds(...)`")
        if re.search(r"\bmain\s*\(", self.c_function):
            raise ValueError("c_function must not define main(); plainproof writes its own")
        for banned in ("system(", "fopen(", "exec", "fork(", "socket(", "#include <unistd.h>"):
            if banned in self.c_function:
                raise ValueError(f"c_function may not use {banned!r}: it must be pure arithmetic")

    def signature_args(self) -> str:
        return ", ".join(f"long long {v.name}" for v in self.variables)

    def ranges_plain(self) -> str:
        return "; ".join(v.plain_range() for v in self.variables)

    def ranges_c(self) -> str:
        return " and ".join(f"{v.min} <= {v.name} <= {v.max}" for v in self.variables)

    def search_space(self) -> int:
        total = 1
        for v in self.variables:
            total *= v.max - v.min + 1
        return total

    # ---- persistence -------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "ClaimSpec":
        data = dict(data)
        data["variables"] = [Variable(**v) for v in data["variables"]]
        known = cls.__dataclass_fields__.keys()
        spec = cls(**{k: v for k, v in data.items() if k in known})
        spec.validate()
        return spec

    @classmethod
    def load(cls, path: Path | str) -> "ClaimSpec":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: Path | str) -> None:
        Path(path).write_text(self.to_json() + "\n")

    def claim_c_source(self) -> str:
        """claim.c as it goes to Aristotle: a plain-English header, then the function."""
        header = [
            "/*",
            " * plainproof claim",
            f" * Question:  {self.question}",
            f" * Claim:     {self.plain_restatement}",
            f" * Inputs:    {self.ranges_plain()}",
        ]
        for a in self.assumptions:
            header.append(f" * Assume:    {a}")
        header.append(" *")
        header.append(" * claim_holds(...) returns 1 exactly when the claim is true for those inputs.")
        header.append(" */")
        return "\n".join(header) + "\n\n" + self.c_function.strip() + "\n"


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "claim"
