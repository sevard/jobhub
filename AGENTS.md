# AGENTS.md

## Project overview
This repository is a small web app with:
- a Python FastAPI backend in api/app.py
- a frontend in ui/ using Jinja2 templates and CSS, rendered by the backend under /ui

## Build and run rules
- Use Python 3.14+ as declared in pyproject.toml.
- Always use uv for Python package management and project commands.
- In development, use hot reload for the backend.
- Backend entrypoint: api/app.py
- Run the app as a module so absolute imports work correctly:
  - `uv run python -m api.app`
  - then open http://127.0.0.1:8001/ui/index.html

## Architecture guidance
- Keep the backend as a lightweight FastAPI websocket relay.
- Preserve the existing websocket endpoint:
  - `/ws`
- Preserve the existing health and root endpoints.
- Serve the frontend via `from fastapi.templating import Jinja2Templates` rather than a static files mount; use Jinja2 templates for all pages, including loops/conditionals (e.g. message lists), rather than hand-building HTML strings.

## Change guidelines
- Prefer small, targeted changes over large rewrites.
- Do not introduce new frameworks or packages unless necessary.
- If you change API behavior, keep the frontend and backend aligned.
- When adding features, keep the current simple structure intact.

## Validation expectations
- Verify backend changes by starting the app and checking the health endpoint.
- Verify UI changes by opening http://127.0.0.1:8001/ui/index.html after starting the backend.
- After confirming the backend or frontend works, shut the local server down before finishing.
