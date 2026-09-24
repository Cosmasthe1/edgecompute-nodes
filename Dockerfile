# EdgeCompute Orchestrator — container image
#
# Builds from the pinned requirements.txt (pip-compile output) so the image
# gets the exact same dependency versions CI tests against.

FROM python:3.11-slim AS base

WORKDIR /app

# System deps kept minimal on purpose — no compiler toolchain needed since
# all runtime deps ship wheels.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator/ ./orchestrator/
COPY agent/ ./agent/
COPY simulator/ ./simulator/

EXPOSE 8000

# A non-root user is good practice for anything that accepts network input.
RUN useradd --create-home --shell /bin/bash edgecompute
USER edgecompute

CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
