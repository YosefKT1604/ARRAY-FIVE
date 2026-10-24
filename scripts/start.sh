#!/usr/bin/env bash
# Run step for Replit: one server for the API and the built frontend.
set -euo pipefail
cd "$(dirname "$0")/../src/backend"

# Replit points uv at its own environment folder; use ours (the one build.sh filled).
export UV_PROJECT_ENVIRONMENT="$(pwd)/.venv"

# Demo clock: a non-secret default, overridable. Set here because the Replit docs do not document a
# deployment-only env table; this works for both Run and published deployments.
export SCDC_DEMO_NOW="${SCDC_DEMO_NOW:-2026-10-20T08:00:00+08:00}"

exec python -m uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
