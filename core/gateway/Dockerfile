# FutureKind Gateway — the single entry point for every AI request.
#
# Deliberately small and deliberately boring. This image contains the Gateway and
# its catalogue default; it contains no model, no weights and no secrets, because
# `docs/ARCHITECTURE.md:196-198` forbids secrets in deployment artifacts and
# `docs/adr/ADR-0001-Local-First-AI.md` puts the weights on the hospital's own
# hardware. Everything the operator may change is mounted, not baked.
#
# Nothing here has been built or run: this repository has no Docker daemon
# available to it (verified 2026-10-07 — `command -v docker` finds nothing on
# either side of WSL). The Gateway itself is proved over real sockets in
# core/gateway/tests/test_end_to_end.py; what remains unverified is this file.

FROM python:3.12-slim

# A source build only to prove the wheel installs and its entrypoint resolves.
# Build tooling is left in the layer that the final image does not use.
RUN useradd --create-home --uid 10001 gateway

WORKDIR /build

# `readme = "README.md"` in pyproject.toml makes this file part of the build,
# not just documentation — copy it or the install fails with a confusing error.
COPY pyproject.toml README.md ./
COPY src ./src
COPY models.yaml /app/models.yaml

RUN pip install --no-cache-dir .

# The LiteLLM alias list is mounted here by compose, read-only. The Gateway reads
# it once at startup to prove the two files agree (docs/SPECIFICATION.md SPEC-07-03)
# and refuses to start when they do not, so this path is part of the contract.
ENV FK_GATEWAY_HOST=0.0.0.0 \
    FK_GATEWAY_PORT=8100 \
    FK_GATEWAY_MODELS_PATH=/app/models.yaml \
    FK_GATEWAY_LITELLM_CONFIG=/app/configs/litellm/config.yaml

EXPOSE 8100

USER gateway

# /health/ready, not /health: a liveness probe must not restart a container that is
# reporting a problem honestly (docs/architecture/gateway-routing.md), and readiness
# is the question an orchestrator should gate traffic on. A 503 raises in urllib,
# which exits non-zero, which is the answer compose is looking for. python:slim has
# no curl or wget, so this is the smallest thing that can make the request.
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health/ready', timeout=3)"]

CMD ["futurekind-gateway"]
