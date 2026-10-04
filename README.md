# JobHub

JobHub is a lightweight ride-request board. Users can pickup and
drop-off requests, see and follow all requests in a live feed. 
The FastAPI backend stores requests in (for now) SQLite and
broadcasts updates to connected browsers over WebSockets.

## Features

- Publish requests with a pickup time, pickup location, drop-off location, and
  optional note.
- View and delete requests created in the current browser session.
- Watch all requests in the live feed.
- Persist requests locally in `relay.db`.

## Requirements

- Python 3.14 or newer
- [uv](https://docs.astral.sh/uv/)

## Run locally

From the project root, install the locked dependencies and start the server:

```bash
uv sync
uv run python -m api.app
```

Open <http://127.0.0.1:8001/post> (create jobs) or <http://127.0.0.1:8001/feed> (view jobs) in your browser. The server listens on port
`8001`. Stop it with `Ctrl+C`.

For development with automatic reload, set `APP_ENV` to `development` before
starting:

```bash
APP_ENV=development uv run python -m api.app
```

## Application pages

| URL | Description |
| --- | --- |
| `/` | Landing page with a login link (redirects to the account home when logged in) |
| `/account` | Log in or sign up (redirects to the account home when already logged in) |
| `/account/home` | Redirects a logged-in user to their role's account page (`/account` if logged out) |
| `/account/dispatcher` | Dispatcher account page, linking to `/post` (other roles are redirected to their own page) |
| `/account/driver` | Driver account page, linking to `/feed` (other roles are redirected to their own page) |
| `/post` | Dispatchers only: post requests and see and delete all requests (others are redirected) |
| `/feed` | Live feed of all requests (login required; redirects to `/account` otherwise) |
| `/docs` | Interactive FastAPI API documentation |

## Roles

Every account has a role, chosen at sign-up:

- **dispatcher**: can open `/post`, create jobs, and delete any job.
- **driver**: can browse available jobs at `/feed`; cannot create or delete jobs.

Logged-out visitors and drivers get 401 or 403 from the dispatcher-only API endpoints. Accounts created before roles existed become drivers.

## HTTP API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/info` | Service status and WebSocket information |
| `GET` | `/api/get_jobs` | List requests (login required) |
| `POST` | `/api/post_job` | Create a request (dispatchers only) |
| `DELETE` | `/api/delete_job/{message_id}` | Delete any request (dispatchers only) |
| `POST` | `/api/signup` | Create an account and log in (username 3-32 letters, digits or `_`; password 8-128 characters; `role` is `dispatcher` or `driver`) |
| `POST` | `/api/login` | Log in with username and password |
| `POST` | `/api/logout` | Log out and clear the login cookie |

Create a request by sending JSON to `/api/post_job`:

```json
{
  "pickup_time": "2026-10-04T15:30:00",
  "pickup_location": "Airport",
  "dropoff_location": "Downtown",
  "note": "One passenger"
}
```

`pickup_time`, `pickup_location`, and `dropoff_location` are required.
`note` is optional and defaults to an empty string. Only dispatchers can create requests; each request records the
posting account as `user_id`.

## WebSocket

Connect to `/ws` (logged-in users only; others are closed with code 1008) using `ws://` (or `wss://` when served over HTTPS). Clients
can receive JSON events when requests are created or deleted. The WebSocket is
receive-only: client messages are ignored, and requests must be created or
deleted through the HTTP API. A newly created request is broadcast in this
shape:

```json
{
  "type": "message",
  "id": 1,
  "user_id": 1,
  "pickup_time": "2026-10-04T15:30:00",
  "pickup_location": "Airport",
  "dropoff_location": "Downtown",
  "note": "One passenger"
}
```

Deletion events have the form `{"type":"delete","id":1}`.

## Tests

Run the test suite from the project root:

```bash
uv run python -m unittest discover -s tests -q
```

## Project layout

```text
api/
  app.py       FastAPI routes, WebSocket relay, and server startup
  db.py        SQLite persistence
tests/         Backend tests
ui/
  templates/   Jinja2 page templates
  static/      Browser JavaScript, CSS, and icons

```
