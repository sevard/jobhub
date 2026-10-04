# JobHub

JobHub is a lightweight ride-request board. Users can publish pickup and
drop-off requests, see their own requests in the publisher view, and follow all
requests in a live feed. The FastAPI backend stores requests in SQLite and
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

Open <http://127.0.0.1:8001/> in your browser. The server listens on port
`8001`. Stop it with `Ctrl+C`.

For development with automatic reload, set `APP_ENV` to `development` before
starting:

```bash
APP_ENV=development uv run python -m api.app
```

## Application pages

| URL | Description |
| --- | --- |
| `/` | Home page with links to the publisher and feed |
| `/post` | Publish a request and manage your own requests |
| `/feed` | Live feed of requests from all sessions |
| `/docs` | Interactive FastAPI API documentation |

## HTTP API

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/info` | Service status and WebSocket information |
| `GET` | `/api/get_message` | List requests; pass `own_only=true` to list only the current session's requests |
| `POST` | `/api/post_message` | Create a request |
| `DELETE` | `/api/delete_message/{message_id}` | Delete a request owned by the current session |

Create a request by sending JSON to `/api/post_message`:

```json
{
  "pickup_time": "2026-10-04T15:30:00",
  "pickup_location": "Airport",
  "dropoff_location": "Downtown",
  "note": "One passenger"
}
```

`pickup_time`, `pickup_location`, and `dropoff_location` are required.
`note` is optional and defaults to an empty string. The API sets a `session_id`
cookie when needed; that cookie is used to scope a user's own requests and to
authorize deletion.

## WebSocket

Connect to `/ws` using `ws://` (or `wss://` when served over HTTPS). Clients
can receive JSON events when requests are created or deleted. The WebSocket is
receive-only: client messages are ignored, and requests must be created or
deleted through the HTTP API. A newly created request is broadcast in this
shape:

```json
{
  "type": "message",
  "id": 1,
  "session_id": "session-id",
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