# AGENTS.md

## Project overview
This repository is a small web app with:
- a Python FastAPI backend in api/app.py
- a static frontend in frontend/relay-ui/ using plain HTML and CSS, served by the backend under /ui

## Build and run rules
- Use Python 3.14+ as declared in pyproject.toml.
- Always use uv for Python package management and project commands.
- In development, use hot reload for the backend.
- Backend entrypoint: api/app.py
- Run the app with:
  - `uv run uvicorn api.app:app --host 0.0.0.0 --port 8001 --reload`
  - then open http://127.0.0.1:8001/ui/index.html

## Architecture guidance
- Keep the backend as a lightweight FastAPI websocket relay.
- Preserve the existing websocket endpoints:
  - `/ws`
  - `/ws/`
- Preserve the existing health and root endpoints.
- The frontend is mounted as static files at /ui; keep it dependency-free and static unless a strong reason requires otherwise.

## Change guidelines
- Prefer small, targeted changes over large rewrites.
- Do not introduce new frameworks or packages unless necessary.
- If you change API behavior, keep the frontend and backend aligned.
- When adding features, keep the current simple structure intact.

## Validation expectations
- Verify backend changes by starting the app and checking the health endpoint.
- Verify UI changes by opening http://127.0.0.1:8001/ui/index.html after starting the backend.
- After confirming the backend or frontend works, shut the local server down before finishing.
