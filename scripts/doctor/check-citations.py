#!/usr/bin/env python3
"""Do the repository's own citations still land?

`docs/DOMAIN_MODEL.md` states the convention this script enforces: a `path:line` pair
points at content that exists as the file was written, and a citation that has since
drifted is a defect in the citing document. The convention is sound and it is also
fragile in exactly one way — inserting a paragraph anywhere shifts every line number
after it, and a release pass that edits prose does that constantly.

So this checks the mechanical half, which is the half no reviewer catches:

* the cited file exists;
* the cited line(s) are inside it;
* and the cited line is not blank.

It deliberately does not try to decide whether the line *says* what the prose claims.
That is a reader's judgement, and a script that guessed would train people to ignore it.

Usage:  python scripts/doctor/check-citations.py [root]
Exit:   0 clean, 1 with problems listed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath

#: `path/to/file.ext:123` or `path/to/file.ext:123-456`, inside backticks.
CITATION = re.compile(
    r"`(?P<file>[A-Za-z0-9_./-]+\.(?:md|py|sh|yaml|yml|toml|json))"
    r":(?P<start>\d+)(?:-(?P<end>\d+))?`"
)

#: Skip the citation conventions and this checker's own examples.
SELF = "scripts/doctor/check-citations.py"

#: Citations into repositories that are not this one.
#:
#: The integration and threat-model documents read CARE ERP, `care-pacs` and the
#: Orthanc deployment as evidence, and cite those files by their paths in *that* tree.
#: They are real citations and they cannot be checked from here, so they are reported
#: as uncheckable rather than silently passing — a list is a promise someone can
#: audit, a skip is not.
FOREIGN = (
    "docker-compose.yml",
    "docker-compose.production.yml",
    "care-pacs/",
    "orthanc/config/",
    "usg-reports/",
    "artifacts/",
    "lib/",
    "bridge-service/",
)


def is_foreign(cited: str) -> bool:
    return cited.startswith(FOREIGN) or cited in {
        "docker-compose.yml",
        "docker-compose.production.yml",
    }


def citation_targets(root: Path) -> list[tuple[str, str, int, int]]:
    """Every (citing file, cited file, first line, last line) pair in the tree."""
    found: list[tuple[str, str, int, int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".py", ".sh", ".yaml", ".yml"}:
            continue
        if path.relative_to(root).as_posix() == SELF:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in CITATION.finditer(text):
            found.append(
                (
                    path.relative_to(root).as_posix(),
                    match.group("file"),
                    int(match.group("start")),
                    int(match.group("end") or match.group("start")),
                )
            )
    return found


def resolve(citing: str, cited: str, root: Path) -> Path | None:
    """Find the file a citation means.

    Prose cites three ways: from the repository root (`docs/ARCHITECTURE.md:106`),
    relative to the citing file (`gateway-policy.md:5`), or by a path written relative
    to some package the reader is already looking at (`observability/logging.py:31`).
    A bare or partial name is matched against the whole tree and accepted only when
    exactly one file carries it — two matches is not a citation, it is a guess.
    """
    for candidate in (root / cited, (root / citing).parent / cited):
        if candidate.is_file():
            return candidate
    wanted = PurePosixPath(cited)
    matches = [
        p
        for p in root.rglob(wanted.name)
        if p.is_file()
        and ".git" not in p.parts
        and (len(wanted.parts) == 1 or p.as_posix().endswith(cited))
    ]
    return matches[0] if len(matches) == 1 else None


def check(root: Path) -> tuple[list[str], int]:
    problems: list[str] = []
    foreign = 0
    for citing, cited, start, end in citation_targets(root):
        if end < start:
            problems.append(f"{citing}: `{cited}:{start}-{end}` range runs backwards")
            continue
        target = resolve(citing, cited, root)
        if target is None:
            if cited in FOREIGN or any(cited.startswith(f) for f in FOREIGN):
                foreign += 1
                continue
            problems.append(f"{citing}: cites `{cited}` which is not in the tree")
            continue
        lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
        if end > len(lines):
            problems.append(
                f"{citing}: `{cited}:{start}-{end}` is past the end ({len(lines)} lines)"
            )
            continue
        window = lines[start - 1 : end]
        if start == end:
            # A single-line citation is a pointer to one statement, so that line has
            # to carry it.
            if not window[0].strip():
                problems.append(
                    f"{citing}: `{cited}:{start}` is a blank line in "
                    f"{target.relative_to(root).as_posix()}"
                )
        elif not any(line.strip() for line in window):
            # A range cites a block. Blocks in these files alternate with blank lines
            # by house style, so the test is whether anything is there at all.
            problems.append(
                f"{citing}: `{cited}:{start}-{end}` is blank for its whole span in "
                f"{target.relative_to(root).as_posix()}"
            )
    return problems, foreign


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    total = len(citation_targets(root))
    problems, foreign = check(root)
    print(f"{total} path:line citations checked against {root.name}")
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print(f"FAIL — {len(problems)} citation(s) no longer point at content")
        return 1
    print(
        f"OK — every in-tree citation resolves to content "
        f"({foreign} citation(s) into other repositories, uncheckable from here)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
