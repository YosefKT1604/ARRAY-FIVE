#!/usr/bin/env bash
# Build step for Replit: backend dependencies, then the frontend bundle served by FastAPI.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! python -m uv --version >/dev/null 2>&1; then
  python -m pip install uv
fi

(cd src/backend && python -m uv sync --extra llm)
(cd frontend && npm ci && VITE_API_MODE=hybrid npm run build)
