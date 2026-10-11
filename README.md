# JobHub

JobHub is a lightweight ride-request board built for **drivers**. An admin
publishes a ride request manually, and every eligible driver sees it in real
time, without refreshing the browser. Drivers can take a ride request and
cancel it if an emergency comes up. The FastAPI backend stores data in (for
now) SQLite and is designed to broadcast updates to connected browsers over
WebSockets.

> **Status: early development.** Account handling (sign-up, login, logout) is
> in place. The ride-request features described below are not implemented yet;
> see [Current status](#current-status).

## How it works (target design)

1. An admin publishes a ride request (pickup time, pickup and drop-off
   locations, optional note).
2. All eligible drivers see the request appear instantly in their live feed
   over a WebSocket connection.
3. A driver takes the request.
4. If something comes up, the driver cancels it so another driver can take it.
5. The admin can edit or cancel a published request at any time; drivers see
   the change in real time.

## Current status

Working now:

- Sign up, log in and log out through server-rendered forms.
- A logged-in account page at `/account`.
- Password hashing with Argon2 and login sessions in an HttpOnly cookie.
- CSRF protection on every form.
- Roles stored on every account (`admin` or `driver`). Sign-up always creates a
  driver; admins are created from the command line (see [Roles](#roles)).
- An admin dashboard at `/admin` where an admin creates ride requests (see
  [Ride requests](#ride-requests)).
- A bearer-token login endpoint (`POST /token`) and a health check.
- A `/ws` WebSocket endpoint that accepts connections (see
  [WebSocket](#websocket)).

Not implemented yet:

- Editing and cancelling ride requests, and drivers taking or cancelling them.
- Broadcasting new ride requests over `/ws`: a ride created by an admin is not
  pushed to anyone yet.
- The driver pages and live feed, and any read endpoint for ride requests.
- Limiting visibility to eligible drivers.

## Requirements

- Python 3.14 or newer
- [uv](https://docs.astral.sh/uv/)

## Run locally

From the project root, install the locked dependencies, create your local
config and start the server:

```bash
uv sync
cp config.ini.example config.ini   # then set a real secret_key in config.ini
uv run fastapi run --port 8080
```

Open <http://127.0.0.1:8080/>. Stop the server with `Ctrl+C`. For development
with automatic reload, use:

```bash
uv run fastapi dev --port 8080
```

The app entrypoint (`api.main:app`) is declared under `[tool.fastapi]` in
`pyproject.toml`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `CSRF_SECRET` | Secret used to sign CSRF tokens. If unset, a random one is generated at every start, so open forms stop working after a restart |

The token signing key is read from `config.ini` in the project root (section
`[auth]`, option `secret_key`). `config.ini` is git-ignored, and the app refuses
to start without it. `config.ini.example` is the committed template.

Setting `development = true` under `[app]` turns on development mode
(`app.state.development_mode`). It defaults to `false`; hot reload comes from
`uv run fastapi dev`, not from this setting. The 24-hour session lifetime is set
in [api/config.py](api/config.py).

## Application pages

| URL | Description |
| --- | --- |
| `/` | Landing page with log in and sign up links (redirects to `/account` when logged in) |
| `/signup` | Sign-up form |
| `/login` | Log-in form (redirects to `/account` when already logged in) |
| `/account` | Account page (redirects to `/login` when logged out); admins also see a link to the dashboard |
| `/admin` | Admin dashboard: new ride request form and the list of ride requests (admins only) |
| `/docs` | Interactive FastAPI API documentation |

Form submissions: `POST /signup`, `POST /login`, `POST /logout` and `POST /admin/rides`. Each form
carries a hidden `csrf_token` field that must match the `fastapi-csrf-token`
cookie.

## Accounts

- Username: 3-32 letters, digits or `_` (case-insensitive and unique).
- Password: 8-128 characters, stored as an Argon2 hash.
- A successful login sets an HttpOnly, `SameSite=Lax` `auth_token` cookie
  holding a JWT that expires after 24 hours.
- Sign-up and log-in forms that fail validation are shown again with an error,
  and the log-in page gives the same generic message for any failure.
- Accounts have a `disabled` flag. Disabled accounts can still log in and use
  their account page.

## Roles

Every account is either a `driver` or an `admin`.

- **Sign-up creates drivers only.** The sign-up form has no role field, and a
  `role` value added to the request is ignored.
- **Admins are created from the command line**, never through the website:

  ```bash
  uv run python -m api.create_admin USERNAME            # new admin, prompts for the password
  uv run python -m api.create_admin USERNAME --promote  # make an existing user an admin
  ```

  The password is typed at a hidden prompt, not given as an argument, and
  follows the same rules as sign-up. An existing username is refused unless you
  pass `--promote`, which changes only the role and keeps their password. It
  first asks `Promote 'alice' (driver) to admin? [y/N]` and changes nothing
  unless you answer `y` or `yes`; add `--yes` to skip the question in scripts.
- The role is read from the database on every request, not from the login
  token, so changing it takes effect immediately.
- `get_current_admin` and `get_current_driver` in [api/auth.py](api/auth.py)
  return 403 for the wrong role; they are ready for the admin and driver
  features.
- The `users` table has no migrations. After this change, delete an old
  `jobhub.db` so it is recreated with the `role` column.

## Ride requests

An admin creates a ride request on the dashboard at `/admin`. Each ride request has:

| Field | Rules |
| --- | --- |
| Pickup location | Required, up to 200 characters |
| Drop-off location | Required, up to 200 characters |
| Pickup date and time | Required, a local date and time without a time zone (the form uses a browser date-time picker) |
| Notes | Optional, up to 500 characters |
| Available | Not on the form: set automatically, `true` for a new ride request (a ride a driver can still take) |

Leading and trailing spaces are trimmed. The ride is also stored with the id of
the admin who created it. The dashboard lists all ride requests, earliest pickup
first, with an Available column.

- `GET /admin` and `POST /admin/rides` are for admins only. Logged-out visitors are
  redirected to `/login`, and drivers get a 403.
- Ride requests are created only through the HTML form with CSRF protection;
  there is no JSON route for writing them.
- An invalid submission shows the dashboard again with an error and keeps what
  was typed. Nothing is stored.
- The pickup time is not checked against the current time, so a time in the past
  is accepted.

## HTTP API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `POST` | `/token` | OAuth2 password login; returns a bearer access token |
| `WS` | `/ws` | WebSocket endpoint (currently no events are sent) |

`/api/info` and `/api/get_jobs` from the earlier version no longer exist.

## WebSocket

`/ws` accepts a connection and keeps it open, ignoring anything the client
sends. The `ConnectionManager` in [api/main.py](api/main.py) can broadcast to
all connected clients, but nothing calls it yet, and the endpoint does not check
that the user is logged in. Requiring login and sending ride-request events are
part of the planned work.

## Tests

```bash
uv run python -m unittest discover -s tests -q
```

`tests/test_auth.py` covers the account code: password hashing, user creation,
authentication, tokens, roles, the `create_admin` tool, the current-user
dependencies, the sign-up, log-in and log-out routes, the account page, `/token`
and `/api/health`.

`tests/test_rides.py` covers ride request storage and the admin dashboard: access
control, creating a ride, validation and CSRF.

Both run against an in-memory database.

## Project layout

```text
api/
  main.py      FastAPI app: pages, form routes, token endpoint, WebSocket
  auth.py      Password hashing, JWT tokens, user lookup and creation, role checks
  create_admin.py  Command-line tool to create or promote an admin
  rides.py     Ride request storage (create and list)
  config.py    Shared settings: paths, templates, cookie, token and CSRF values
  db.py        SQLite connection and users and rides table setup
  forms.py     Sign-up, log-in and ride request form models, CSRF form helpers, and the signup/login page helper
tests/         Backend tests
ui/
  templates/   Jinja2 page templates
  static/      CSS and icons (browser JavaScript will live here)
config.ini    Local secrets (not committed; copy from config.ini.example)
jobhub.db      SQLite database, created on first start (not committed)
```
