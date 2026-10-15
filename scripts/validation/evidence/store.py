"""Where a session record lives, and what it is forbidden to contain.

Part 1 of the evidence system: one record per study, carrying the eight facts a claim about
clinical value needs — case, time, skill, alias, draft, review, approval, export. Everything
else in this package reads from here.

The one non-negotiable is PHI. A draft is patient text the moment it is about a patient, and
this repository is public. So:

- **Text is not stored by default.** A record carries lengths, counts, similarity and SHA-256
  prefixes of section content. A hash prefix identifies a change without revealing a word, and
  that is enough for every measure in `evidence.edits`.
- **A store inside the repository is refused**, by the same rule `run-cases.py` applies to case
  files (`docs/product/RADIOLOGY_WORKFLOW.md`'s PHI discipline). Writing clinical text into a
  git tree is the one mistake that cannot be fixed by a revert.
- **`allow_text` exists** for a department that has decided, on its own machine, to keep drafts
  for a study. It requires an explicit path outside the tree *and* an explicit flag, and the
  record then says so, so that an aggregate can be filtered by whether it was ever built from
  text.
- **A stub answer is labelled, never laundered.** `provenance.stub` is carried on every record
  and refused by every reporting path that claims to describe care
  (`docs/safety/CLINICAL_SAFETY.md` §5).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "fk-evidence-session/1"
STAGES = ("received", "drafted", "checked", "reviewed", "approved", "exported")


class StoreError(RuntimeError):
    """Raised for a path or a record that would create a privacy or provenance incident."""


def sha_prefix(text: str, length: int = 12) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:length]


def inside_repo(path: Path) -> bool:
    """True when `path` sits in a working tree. Deliberately conservative.

    Resolved against `git rev-parse --show-toplevel` when git is available, and against the
    package's own location when it is not, because a measurement tool that silently writes
    patient text into a public repository is the failure mode this whole module exists to
    prevent.
    """
    candidate = path.expanduser().resolve()
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        root = ""
    if root:
        return candidate.is_relative_to(Path(root).resolve())
    return candidate.is_relative_to(Path(__file__).resolve().parents[3])


@dataclass
class Provenance:
    #: Empty by default because a record may exist before anyone knows which skill answered —
    #: a draft request that never reached the Gateway still needs to be countable.
    skill: str = ""
    alias: str = ""
    model: str = ""
    capability: str = ""
    prompt_version: str = ""
    profile: str = ""
    attempts: int = 1
    degraded: bool = False
    stub: bool = False
    gateway_request_id: str = ""
    taxonomy_version: int = 1

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SessionRecord:
    """One study, from request to export. The eight facts, and nothing that identifies a patient.

    `case_ref` is an opaque reference the department can resolve offline. It must not be a
    name, an MRN, an accession number or any other identifier that would let a leaked
    aggregate be re-identified — the same discipline `docs/product/GOLDEN_DATASET.yaml:19`
    states for case ids.
    """

    case_ref: str
    site: str
    actor_label: str
    role: str
    started_at: str
    stages: dict[str, str] = field(default_factory=dict)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    engine: dict[str, Any] = field(default_factory=dict)
    edit: dict[str, Any] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    scores: dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=Provenance)
    text_stored: bool = False
    schema: str = SCHEMA

    def stage_seconds(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        stamps = {k: v for k, v in self.stages.items() if v}
        ordered = [s for s in STAGES if s in stamps]
        for index in range(len(ordered) - 1):
            a, b = ordered[index], ordered[index + 1]
            try:
                first = datetime.fromisoformat(stamps[a])
                second = datetime.fromisoformat(stamps[b])
            except ValueError:
                out[f"{a}_to_{b}"] = None
                continue
            out[f"{a}_to_{b}"] = round((second - first).total_seconds(), 2)
        return out

    def time_to_final(self) -> float | None:
        if "received" not in self.stages or "approved" not in self.stages:
            return None
        try:
            start = datetime.fromisoformat(self.stages["received"])
            end = datetime.fromisoformat(self.stages["approved"])
        except ValueError:
            return None
        return round((end - start).total_seconds(), 2)

    def as_dict(self) -> dict:
        return {
            "schema": self.schema,
            "case_ref": self.case_ref,
            "site": self.site,
            "actor_label": self.actor_label,
            "role": self.role,
            "started_at": self.started_at,
            "stages": dict(self.stages),
            "stage_seconds": self.stage_seconds(),
            "time_to_final_seconds": self.time_to_final(),
            "sections": dict(self.sections),
            "engine": dict(self.engine),
            "edit": dict(self.edit),
            "labels": list(self.labels),
            "scores": dict(self.scores),
            "provenance": self.provenance.as_dict(),
            "text_stored": self.text_stored,
        }


def record_sections(
    sections: dict[str, str], include_text: bool = False
) -> dict[str, dict[str, Any]]:
    """Lengths and hashes per section. Words only when the caller has accepted the consequence.

    `chars`, `words` and `sha12` support every quantity the metrics need: typing volume,
    structure coverage, and whether a later version differs. Nothing downstream needs the
    text, and needing it would be a design smell worth arguing about before enabling.
    """
    out: dict[str, dict[str, Any]] = {}
    for key, value in sections.items():
        text = value or ""
        entry = {
            "chars": len(text),
            "words": len(text.split()),
            "sha12": sha_prefix(text),
        }
        if include_text:
            entry["text"] = text
        out[key] = entry
    return out


def append(path: Path, records: Iterable[SessionRecord], allow_text: bool = False) -> int:
    if inside_repo(path):
        raise StoreError(
            f"refusing to write an evidence store inside the repository: {path}. "
            "A draft becomes patient text the moment it is about a patient, "
            "and this tree is public."
        )
    if any(r.text_stored for r in records) and not allow_text:
        raise StoreError(
            "a record carries section text but --allow-text was not given: "
            "storage of clinical text is an explicit decision, not a side effect"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.as_dict(), sort_keys=True) + "\n")
            written += 1
    return written


def read(path: Path) -> list[dict]:
    if inside_repo(path):
        raise StoreError(f"an evidence store must live outside the tree: {path}")
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            schema = record.get("schema")
            if schema != SCHEMA:
                raise StoreError(
                    f"{path}: record schema {schema!r} is not {SCHEMA!r}; "
                    "read it with a migration, do not average across shapes"
                )
            rows.append(record)
    return rows


def real_rows(rows: list[dict]) -> list[dict]:
    """Only records that could support a claim about care.

    A stub answer is a plumbing test with a stopwatch attached. Filtering happens here rather
    than in each report so that no aggregate can quietly become a headline by forgetting the
    filter — which is the same distinction FM4 draws between a measurement and a number.
    """
    return [row for row in rows if not row.get("provenance", {}).get("stub")]


def distribution(values: list[float]) -> dict[str, Any]:
    import statistics

    numbers = [float(v) for v in values if isinstance(v, (int, float))]
    if not numbers:
        return {"n": 0}
    out: dict[str, Any] = {
        "n": len(numbers),
        "mean": round(statistics.fmean(numbers), 3),
        "median": round(statistics.median(numbers), 3),
        "min": round(min(numbers), 3),
        "max": round(max(numbers), 3),
    }
    if len(numbers) > 1:
        out["sd"] = round(statistics.stdev(numbers), 3)
        ordered = sorted(numbers)
        quarter = len(ordered) // 4
        out["p25"] = round(ordered[quarter], 3)
        out["p75"] = round(ordered[min(len(ordered) - 1, 3 * quarter)], 3)
    return out


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
