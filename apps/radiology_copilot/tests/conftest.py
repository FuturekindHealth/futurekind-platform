"""Shared test furniture: a deterministic clock, a stub Gateway, golden fixtures.

Nothing in ``tests/`` except ``test_end_to_end.py`` starts a process, opens a port
or asks a model anything. The clinical behaviour under test is this application's
own — parsing, checking, refusing, reviewing, rendering — and it has to be provable
from a fixture rather than from whatever a deployment happens to say today.

Each golden answer carries the submission it was drafted from. That is not
bookkeeping: the quality checks compare a draft against what was submitted, so a
fixture answer paired with the wrong dictation produces findings about a study
nobody described — a test failure that means nothing.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from futurekind_radiology.copilot import RadiologyCopilot
from futurekind_radiology.gateway import GatewayCompletion
from futurekind_radiology.report import RadiologyReport
from futurekind_radiology.submission import StudySubmission

FIXTURE_DIR = Path(__file__).parent / "fixtures"

#: One frozen instant, so every timestamp in every golden output is comparable.
FROZEN_MOMENT = datetime(2026, 10, 8, 9, 30, tzinfo=UTC)
FROZEN_STAMP = "2026-10-08T09:30:00Z"

#: The policy the shipped catalogue declares for this skill (``models.yaml:54-66``).
#: Tests mutate one key at a time out of this, so a policy change is always explicit.
RADIOLOGY_POLICY = {
    "clinical_risk": "high",
    "approval_required": False,
    "audit_required": True,
    "allow_downgrade": False,
}

#: The study each fixture answer was written for, taken from the matching case in
#: ``docs/product/GOLDEN_DATASET.yaml`` where one exists. The dictated text carries
#: every number the answer quotes, because a fixture that does not would make the
#: measurement check test the fixture rather than the product.
GOLDEN_SUBMISSIONS: dict[str, dict[str, Any]] = {
    "normal_ct_head.json": {},
    "hypertensive_bleed.json": {
        "clinical_indication": "58-year-old, sudden severe headache with vomiting, "
        "declining consciousness",
        "modality": "CT",
        "study": "CT HEAD WITHOUT CONTRAST",
        "findings": "Large hyperdense collection in the left basal ganglia and internal "
        "capsule, 4.5 cm maximum, with intraventricular extension filling the lateral and "
        "third ventricles. Surrounding hypodense oedema, effacement of the left lateral "
        "ventricle, rightward midline shift 9 mm, subfalcine herniation. Basal cisterns "
        "compressed. No extra-axial collection.",
    },
    "nph_hydrocephalus.json": {
        "findings": "Prominent cortical sulci and enlarged lateral ventricles out of "
        "proportion to the sulcal widening at the high convexity. Periventricular and deep "
        "white matter hypodensities of chronic small vessel ischaemic change. A 6 mm lacunar "
        "hypodensity in the right caudate head. No haemorrhage, mass or acute extra-axial "
        "collection.",
    },
    "mri_brain_normal.json": {
        "clinical_indication": "45-year-old, chronic headache, no neurological deficit",
        "modality": "MRI",
        "study": "MRI BRAIN WITH AND WITHOUT CONTRAST",
        "findings": "Normal grey-white matter. No mass, no abnormal enhancement. Normal "
        "ventricular size and morphology. No white matter lesions. Pituitary normal. No "
        "sinus disease. Hippocampi, brainstem and cerebellum normal. No midline shift.",
        "technique": "MRI brain with and without intravenous contrast; axial T2, FLAIR, DWI "
        "and post-contrast T1 sequences.",
    },
    "mri_brain_abscess.json": {
        "clinical_indication": "8-year-old, 5 days fever, headache, left temporo-parietal "
        "swelling, GCS 12",
        "modality": "MRI",
        "study": "MRI BRAIN WITH CONTRAST",
        "findings": "Left mastoid opacification with erosion. 18 mm rim-enhancing left "
        "temporal collection with restricted diffusion, 6 mm adjacent cerebritis, 7 mm "
        "midline shift. Sigmoid sinus not enhancing. Ventricles compressed on the left, "
        "basal cisterns patent.",
        "technique": "MRI brain with contrast; axial T1, T2, FLAIR and DWI with post-contrast "
        "sequences.",
    },
    "mri_brain_epilepsy.json": {
        "clinical_indication": "26-year-old, focal seizures with impaired awareness, "
        "MRI ordered twice",
        "modality": "MRI",
        "study": "MRI BRAIN EPILEPSY PROTOCOL",
        "findings": "Right hippocampus small with increased T2 and FLAIR signal, loss of "
        "internal architecture. Temporal horn mildly asymmetric. No mass. Thin temporal lobe "
        "with a 4 mm focal cortical irregularity on the adjacent gyrus, not certain.",
        "technique": "MRI brain, dedicated epilepsy protocol with thin cut coronal FLAIR and "
        "T1 sequences through the hippocampi.",
        "previous_reports": [
            {
                "reported_on": "4 months ago",
                "modality": "MRI",
                "study": "MRI BRAIN EPILEPSY PROTOCOL",
                "report": "Right hippocampal signal abnormality consistent with sclerosis. "
                "No mass.",
            }
        ],
    },
}


def fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


#: The twelve things a draft must return, in the order the document carries them:
#: the six signed sections, the quality pass and the confidence computed from it,
#: then the record of how the draft was made and governed. This is the product's
#: output contract, spelled out once so a test can fail against the contract rather
#: than against whatever the model happens to have written into `RadiologyReport`.
REQUIRED_OUTPUT = (
    "clinical_indication",
    "technique",
    "findings",
    "impression",
    "recommendations",
    "follow_up",
    "quality",
    "confidence",
    "metadata",
    "model_provenance",
    "skill",
    "policy",
)


def golden(name: str) -> dict[str, str]:
    """A golden answer, as the section dict the model wrote."""
    return json.loads(fixture_text(name))


def completion(content: str, **overrides: Any) -> GatewayCompletion:
    """A completion shaped exactly like ``POST /chat`` answers for this skill."""
    payload: dict[str, Any] = {
        "request_id": "fk-test-request-1",
        "skill": "radiology-report",
        "capability": "reasoning",
        "model": "ollama/qwen3:14b",
        "provider": "litellm",
        "selected_by": "skill",
        "policy": dict(RADIOLOGY_POLICY),
        "attempts": 1,
        "degraded": False,
        "content": content,
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 640, "completion_tokens": 210, "total_tokens": 850},
        "latency_ms": 4200,
    }
    payload.update(overrides)
    return GatewayCompletion(**payload)


class StubGateway:
    """Answers as the Gateway would, and records what was asked of it.

    Deliberately not a subclass of ``GatewayClient``: the copilot's dependency is
    a method signature, and keeping the stub independent means a test cannot pass
    by accident when that signature changes in a way the copilot never notices.
    """

    def __init__(self, *responses: GatewayCompletion | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def complete(self, *, skill: str, messages: Any, temperature: Any = None) -> Any:
        self.requests.append({"skill": skill, "messages": messages, "temperature": temperature})
        if not self.responses:
            raise AssertionError("StubGateway ran out of scripted answers")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def last_request(self) -> dict[str, Any]:
        assert self.requests, "nothing was asked of the Gateway"
        return self.requests[-1]


def make_copilot(*responses: GatewayCompletion | Exception) -> tuple[RadiologyCopilot, StubGateway]:
    stub = StubGateway(*responses)
    return RadiologyCopilot(stub, now=lambda: FROZEN_MOMENT), stub


def submission(**overrides: Any) -> StudySubmission:
    payload: dict[str, Any] = {
        "clinical_indication": "62-year-old with sudden right hemiparesis, onset 3 hours",
        "modality": "CT",
        "study": "CT HEAD WITHOUT CONTRAST",
        "findings": (
            "No haemorrhage. Preserved grey-white differentiation. Ventricles and sulci "
            "normal for age. No midline shift."
        ),
    }
    payload.update(overrides)
    return StudySubmission(**payload)


def submission_for(fixture: str, **overrides: Any) -> StudySubmission:
    """The submission this fixture answer was written for."""
    payload = dict(GOLDEN_SUBMISSIONS.get(fixture, {}))
    payload.update(overrides)
    return submission(**payload)


def drafted_report(
    fixture: str = "normal_ct_head.json",
    *,
    content: str | None = None,
    **overrides: Any,
) -> tuple[RadiologyReport, StubGateway]:
    """A report that has been drafted through the copilot, but not reviewed.

    `content` replaces the model's answer while `fixture` still chooses the study it
    was answered for, because most of these tests are about an answer that does not
    match its own dictation.

    Sync on purpose: the suite drives the coroutine with ``asyncio.run`` rather
    than depending on an asyncio plugin, which is how the Gateway's own tests do it.
    """
    study = overrides.pop("study", None) or submission_for(fixture)
    text = fixture_text(fixture) if content is None else content
    copilot, stub = make_copilot(completion(text, **overrides))
    return asyncio.run(copilot.draft(study)), stub


@pytest.fixture
def ct_submission() -> StudySubmission:
    return submission_for("normal_ct_head.json")


def signed_copy(
    report: RadiologyReport, study: StudySubmission, **kwargs: Any
) -> RadiologyReport:
    """A signed copy of `report`, checked against the submission it came from.

    Every fixture that needs a signature has to supply the study too, which is the
    point: the checks re-run at sign-off, and a test that signed a report against
    nothing would be testing a path the product refuses.
    """
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))
    return copilot.review(
        report, decision="signed", clinician="Dr A. Nair", submission=study, **kwargs
    )


@pytest.fixture
def draft_report(ct_submission: StudySubmission) -> RadiologyReport:
    """The golden draft, assembled for the review and rendering tests."""
    report, _ = drafted_report()
    return report


@pytest.fixture
def signed_report(draft_report: RadiologyReport, ct_submission: StudySubmission) -> RadiologyReport:
    return signed_copy(draft_report, ct_submission)
