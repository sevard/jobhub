# AGENTS.md

## Project overview
This repository is a small ride-request board web app with:
- a Python FastAPI backend in api/app.py
- a frontend in ui/ using Jinja2 templates and CSS, rendered by the backend under /ui

## Build and run rules
- Use Python 3.14+ as declared in pyproject.toml.
- Always use uv for Python package management and project commands.
- In development, use hot reload for the backend.
- Backend entrypoint: api/app.py
- Run the app as a module so absolute imports work correctly:
  - `uv run python -m api.app`
  - then open http://127.0.0.1:8001/ (landing page with login link), http://127.0.0.1:8001/post (create jobs) or http://127.0.0.1:8001/feed (view posted jobs)

## Architecture guidance
- Keep the backend as a lightweight FastAPI app that stores ride requests ("jobs") in SQLite and broadcasts them to clients over WebSockets.
- Preserve the existing WebSocket endpoint:
  - `/ws` (logged-in users only; receive-only: it broadcasts job events to clients and must never accept or store input).
- Preserve the existing backend api endpoints:
  - `/api/health`
  - `/api/info`
  - `/api/get_jobs`
- Jobs are created and deleted only through the dispatcher HTML forms (`POST /post`, `POST /post/delete/{id}`); there are no JSON job-write routes. Creating must require a valid pickup time and locations.
- Roles: every user is a `dispatcher` or a `driver` (set at signup). Only dispatchers may open `/post`, create jobs and delete any job via those forms; logged-out requests are redirected to `/account` and drivers to `/account/home`.
- `/feed` and `/api/get_jobs` require a logged-in user (the page redirects to `/account`, the API returns 401).
- User accounts: the `/account` page with its form routes `/account/signup`, `/account/login` and `/account/logout` (there are no `/api` auth routes), the `/account/home` redirect, and the separate `/account/dispatcher` and `/account/driver` pages. Passwords are hashed with stdlib scrypt in the `users` table; logins use the HttpOnly `auth_token` cookie. Jobs record the posting account in `jobs.user_id`; there is no anonymous session cookie.
- Serve the frontend via `from fastapi.templating import Jinja2Templates` rather than a static files mount; use Jinja2 templates for all pages, including loops/conditionals (e.g. message lists), rather than hand-building HTML strings.

## Change guidelines
- Prefer small, targeted changes over large rewrites.
- Do not introduce new frameworks or packages unless necessary.
- If you change API behavior, keep the frontend and backend aligned.
- When adding features, keep the current simple structure intact.

## Validation expectations
- Run the tests with `uv run python -m unittest discover -s tests -q`.
- Verify backend changes by starting the app and checking the health endpoint.
- Verify UI changes by opening http://127.0.0.1:8001/post and http://127.0.0.1:8001/feed after starting the backend.
- After confirming the backend or frontend works, shut the local server down before finishing.
