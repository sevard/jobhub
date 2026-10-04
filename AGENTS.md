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
- Keep the backend as a lightweight FastAPI app that stores ride requests ("jobs") in SQLite and broadcasts them over a websocket.
- Preserve the existing websocket endpoint:
  - `/ws` (logged-in users only; receive-only: it broadcasts events to clients and must never accept or store input)
- Preserve the existing backend api endpoints:
  - `/api/health`
  - `/api/info`
  - `/api/get_jobs`
  - `/api/post_job`
  - `/api/delete_job/{message_id}`
- Jobs are created only via `/api/post_job`, which must require a valid pickup time and locations.
- Roles: every user is a `dispatcher` or a `driver` (set at signup). Only dispatchers may open `/post`, create jobs (`/api/post_job`) and delete any job (`/api/delete_job/{message_id}`); logged-out requests get 401 and drivers get 403.
- `/feed` and `/api/get_jobs` require a logged-in user (the page redirects to `/account`, the API returns 401).
- User accounts: `/api/signup`, `/api/login`, `/api/logout` and the `/account` page, the `/account/home` redirect, and the separate `/account/dispatcher` and `/account/driver` pages. Passwords are hashed with stdlib scrypt in the `users` table; logins use the HttpOnly `auth_token` cookie. Jobs record the posting account in `jobs.user_id`; there is no anonymous session cookie.
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
