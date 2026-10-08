"""``python -m futurekind_radiology`` — run the copilot.

The app is built from the environment here and nowhere else, so a container and a
developer's laptop start the same object.
"""

from __future__ import annotations

import uvicorn

from .api import build_app
from .settings import CopilotSettings


def main() -> None:
    settings = CopilotSettings.from_env()
    uvicorn.run(
        build_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
