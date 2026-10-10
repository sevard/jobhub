# AGENTS.md

## Project overview
JobHub is a ride-request board for drivers. An admin publishes ride requests and eligible drivers see them in real time and can take or cancel them (see README.md for the full target design).

The app is in early development. Only account handling exists so far:
- sign up, log in and log out, plus a logged-in `/account` page
- a `/ws` WebSocket endpoint that accepts connections but nothing is broadcast yet
- `/api/health` and an OAuth2 `POST /token` login

Not implemented yet: ride requests ("jobs") and their storage, the admin dashboard and driver pages (roles are stored and enforced by dependencies, but nothing uses them yet), and the driver live feed. Do not assume those exist.

Code layout:
- `api/main.py`: FastAPI app, page and form routes, `/token`, `/ws`
- `api/auth.py`: password hashing (Argon2 via pwdlib), JWT tokens, user lookup and creation, current-user dependencies
- `api/create_admin.py`: command-line tool to create an admin or `--promote` an existing user after a y/N confirmation, which `--yes` skips (`uv run python -m api.create_admin USERNAME`)
- `api/config.py`: shared settings: `BASE_DIR`, `FRONTEND_DIR`, the single `Jinja2Templates` object (import `templates` from here; do not create another), `IS_DEVELOPMENT` (from `[app] development` in `config.ini`), the auth cookie name, token lifetime, JWT `SECRET_KEY` (read from the git-ignored `config.ini`; see `config.ini.example`) and `ALGORITHM`, and the CSRF values. Put new settings and constants here, not in `main.py`
- `api/db.py`: SQLite connection (`jobhub.db`) and the `users` table
- `api/forms.py`: Pydantic models for the signup and login forms, plus the CSRF form helpers and the signup and login page renderer (the CSRF registration, `CsrfProtect.load_config` and its error handler, lives in `api/main.py`, with its values in `api/config.py`)
- `ui/templates/` and `ui/static/`: Jinja2 templates, CSS, JS and icons
- `tests/`

## Build and run rules
- Use Python 3.14+ as declared in pyproject.toml.
- Always use uv for Python package management and project commands.
- Backend entrypoint: `api.main:app` (declared under `[tool.fastapi]` in pyproject.toml).
- Before the first run, copy `config.ini.example` to `config.ini` and set `secret_key`. Never commit `config.ini` or put secrets in source code.
- Start the app with `uv run fastapi run --port 8080`. In development use hot reload: `uv run fastapi dev --port 8080`.
- Then open http://127.0.0.1:8080/ (landing page), http://127.0.0.1:8080/signup, http://127.0.0.1:8080/login or http://127.0.0.1:8080/account.

## Architecture guidance
- Keep the backend a lightweight FastAPI app that stores data in SQLite.
- Current routes:
  - Pages: `GET /`, `GET|POST /signup`, `GET|POST /login`, `POST /logout`, `GET /account`
  - API: `GET /api/health`, `POST /token`, `WS /ws`
- Accounts: usernames are 3-32 letters, digits or `_` (case-insensitive, unique); passwords are 8-128 characters hashed with Argon2 in the `users` table. A login sets the HttpOnly, `SameSite=Lax` `auth_token` cookie holding a JWT that lasts 24 hours (`ACCESS_TOKEN_EXPIRE_SECONDS` in `api/config.py`). There are no `/api` signup routes.
- Roles: `users.role` is `admin` or `driver` (default `driver`). Sign-up must only ever create drivers: never read a role from a request or add a role field to the signup form. Admins are created only with `api/create_admin.py`. Roles are read from the database, not from the JWT. Guard role-specific routes with `get_current_admin` or `get_current_driver` (403 for the wrong role). There are no migrations: delete an old `jobhub.db` after schema changes.
- Disabled users (`users.disabled`) may still log in and use `/account`. The pages use `get_current_user`; use `get_current_active_user` only where a feature must block disabled users.
- Forms: every form carries a hidden `csrf_token` field validated with `validate_form_csrf`. Form routes take a Pydantic model via `Annotated[Model, Form()]` (models live in `api/forms.py`). Validation failures on `/signup` and `/login` are turned into re-rendered pages by the `RequestValidationError` handler in `api/main.py`; login failures always show the same generic message. Add new form routes the same way.
- Pages read the logged-in user with `get_current_user` on the `auth_token` cookie inside `try/except HTTPException`; logged-out requests are redirected (`/account` to `/login`), and logged-in requests to `/` and `/login` are redirected to `/account`.
- Serve pages with `Jinja2Templates` and Jinja2 templates (including loops/conditionals) rather than hand-built HTML strings. `ui/static` is mounted at `/ui/static` for CSS/JS/icon assets only; do not serve pages from it.
- `/ws` is a receive-only event stream: it must never accept or store client input. When job events are added, require a logged-in user and broadcast through `ConnectionManager`.

## Planned features (build toward these)
- Admin publishes, edits and cancels ride requests through an admin dashboard (the earlier `dispatcher` role is the admin).
- Drivers see published requests in real time over `/ws`, take a request, and can cancel a taken request in an emergency, which returns it to the feed.
- Jobs are created, edited and cancelled only through authenticated HTML forms with CSRF; there are no JSON job-write routes. Creating must require a valid pickup time and pickup and drop-off locations.
- Use the existing roles on the server for the admin dashboard and driver features; limit visibility to eligible drivers.
- Job read endpoints (for example `GET /api/get_jobs`) require a logged-in user and return 401 otherwise.

## Leftovers
`ui/static/feed.js` and `ui/static/post.js` come from the earlier dispatcher/driver version and are not used by any page. Reuse or delete them when building the planned features; do not treat them as current behavior.

## Change guidelines
- Ignore the `keep/` folder. It holds old reference copies of code that are not part of the app: do not read, search, edit, run, test or cite it, and do not treat references found there as evidence that something is in use.
- Prefer small, targeted changes over large rewrites.
- Do not introduce new frameworks or packages unless necessary.
- If you change API behavior, keep the frontend and backend aligned.
- When adding features, keep the current simple structure intact.
- Keep the README.md and this file in sync with behavior changes.

## Validation expectations
- Run the tests with `uv run python -m unittest discover -s tests -q`. They use an in-memory database.
- Verify backend changes by starting the app and checking `GET /api/health`.
- Verify UI changes by opening http://127.0.0.1:8080/, `/signup`, `/login` and `/account` after starting the backend.
- After confirming the backend or frontend works, shut the local server down before finishing.
