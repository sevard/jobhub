# AGENTS.md

## Project overview
This repository is a small web app with:
- a Python FastAPI backend in api/app.py
- a static frontend in frontend/relay-ui/ using plain HTML and CSS

## Build and run rules
- Use Python 3.14+ as declared in pyproject.toml.
- Always use uv for Python package management and project commands.
- Backend entrypoint: api/app.py
- Run the backend with:
  - `uv run uvicorn api.app:app --host 0.0.0.0 --port 8001 --reload`
- Run the frontend with:
  - `uv run python -m http.server 8000`
  - then open http://127.0.0.1:8000/frontend/relay-ui/

## Architecture guidance
- Keep the backend as a lightweight FastAPI websocket relay.
- Preserve the existing websocket endpoints:
  - `/ws`
  - `/ws/`
- Preserve the existing health and root endpoints.
- Keep the frontend dependency-free and static unless a strong reason requires otherwise.

## Change guidelines
- Prefer small, targeted changes over large rewrites.
- Do not introduce new frameworks or packages unless necessary.
- If you change API behavior, keep the frontend and backend aligned.
- When adding features, keep the current simple structure intact.

## Validation expectations
- Verify backend changes by starting the app and checking the health endpoint.
- Verify UI changes by serving the frontend locally and opening the relay UI page.
- After confirming the backend or frontend works, shut the local server down before finishing.
