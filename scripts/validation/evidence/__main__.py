"""Entry point so the package runs as `python -m evidence` from `scripts/validation`."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
