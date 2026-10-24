#!/usr/bin/env bash
# Build step for Replit: backend dependencies, then the frontend bundle served by FastAPI.
set -euo pipefail
cd "$(dirname "$0")/.."

# Replit points uv at its own environment folder; use ours, so uv sync and uv run agree.
export UV_PROJECT_ENVIRONMENT="$(pwd)/src/backend/.venv"

if ! python -m uv --version >/dev/null 2>&1; then
  python -m pip install uv
fi

(cd src/backend && python -m uv sync --extra llm)
(cd frontend && npm ci && VITE_API_MODE=hybrid npm run build)
