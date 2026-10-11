# Changelog

## Unreleased

### Added
- Admin dashboard at `/admin` where an admin creates ride requests (pickup location, drop-off location, pickup date and time, notes) and sees the list. Rides are stored in a new `rides` table (`api/rides.py`); there is no JSON route for creating them.
- Account roles, `admin` and `driver`. Sign-up always creates a driver; admins are created or promoted with `uv run python -m api.create_admin USERNAME`. Roles are read from the database and enforced with `get_current_admin` and `get_current_driver`.
- Accounts: sign up, log in and log out through server-rendered forms, a logged-in `/account` page, and an OAuth2 `POST /token` login. Passwords are hashed with Argon2 and a login sets an HttpOnly, `SameSite=Lax` `auth_token` cookie holding a 24-hour JWT.
- CSRF protection on every form.
- A receive-only `/ws` WebSocket (nothing is broadcast yet) and `GET /api/health`.
- Configuration in a git-ignored `config.ini` (see `config.ini.example`) for the JWT secret key and the development flag.
- Tests for accounts, roles and ride creation (`uv run python -m unittest discover -s tests -q`).

### Changed
- Reworked the app into a FastAPI service split into `api/main.py`, `auth.py`, `config.py`, `db.py`, `forms.py` and `rides.py`, with Jinja2 templates in `ui/templates/`.
- The server runs on port 8080 by default.
- Split the routes out of `api/main.py` into `APIRouter` modules (`pages.py`, `admin.py`, `endpoints.py`, `ws.py`); the admin router applies the admin check to every route. Pages read the cookie user through `OptionalUserDep` and `UserDep` dependencies instead of calling `get_current_user` by hand.

### Removed
- The earlier dispatcher/driver job board: the `dispatcher` role (replaced by `admin`), the `jobs` table, the `/post`, `/feed` and `/account/*` routes, the `/api/get_jobs` endpoint, the old templates and tests, and scrypt password hashing (replaced by Argon2). There is no migration; delete an old `jobhub.db` after upgrading.
- Unused leftovers from that version: `ui/static/feed.js`, `ui/static/post.js` and `REVIEW-app.md` (a review of the deleted `api/app.py`).

### Known issues
- Ride requests cannot yet be edited, cancelled, taken or cancelled by drivers, or read through an API.
- Nothing is broadcast over `/ws`, and `/ws` does not yet require a logged-in user.
- There are no database migrations.
