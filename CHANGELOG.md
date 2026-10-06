# Changelog

## Unreleased

### Added
- `/ws` now accepts only logged-in users; other connections are closed with code 1008.
- Account roles: `dispatcher` and `driver`, chosen at sign-up. Only dispatchers can open `/post`, create jobs and delete any job; the account home shows a role-specific link. Existing accounts default to driver.
- User accounts: sign up, log in and log out with a username and password (`/account`, `/account/signup`, `/account/login`, `/account/logout`). After login the user lands on the account home page (`/account/home`). Passwords are hashed with scrypt and logins use an HttpOnly cookie.
- README.md covering features, setup, pages, HTTP API, WebSocket events, tests and layout.
- Structured ride-request board: a `jobs` table, `JobPayload` validation (pickup time and locations), and new post/feed pages with forms and live feeds.
- Tests for the job endpoints, a receive-only WebSocket.

### Changed
- Removed the JSON `/api/post_job` and `/api/delete_job/{id}` routes; jobs are created and deleted only through the `/post` forms.
- Removed the JSON `/api/signup`, `/api/login` and `/api/logout` routes; accounts use only the `/account/*` form routes.
- Restored the receive-only `/ws` WebSocket in place of `/api/events`; `/api/info` reports `websocket_endpoints`.
- Split the account home into separate dispatcher and driver pages (`/account/dispatcher`, `/account/driver`). `/account/home` now redirects to the page for the user's role, and each page redirects users of the other role.
- Jobs are now tied to the posting account (`jobs.user_id`) instead of the anonymous `session_id` cookie, which is no longer set. Existing databases are migrated automatically; old jobs get a null `user_id`. The `session_id` field in job events is now `user_id`.
- Removed the unused `own_only` option and `my_session_id` field from `GET /api/get_jobs`; it no longer sets the anonymous `session_id` cookie.
- `/feed` and `/api/get_jobs` now require a logged-in user.
- Dispatchers see all jobs on `/post` and can delete any job (previously only the creating session could).
- Converted the generic message relay into a ride-request board; `AGENTS.md` URLs and endpoint list updated.
- The `/ws` WebSocket is now receive-only. Jobs are created only through HTTP, which requires a valid pickup time and locations.
- The post page heading is now "Current jobs".

### Fixed
- Malformed `href` on the Back link in `post.html`.

### Removed
- Gemini integration: `google-genai` dependency, `api/genai.py` and `config.ini` (which held a plaintext API key; rotate it if it was live).
- `patch_post.py` (one-off script) and the unused `main.py`.

### Known issues
- No migration from the old `messages` table to `jobs`.
- The HTTP API does not reject empty or whitespace-only locations.
- The Flatpickr form reset may leave stale state.
- A `file:///` console security warning on `/post` appears only in Firefox with extensions enabled; it does not occur in a private window or in Chrome. The app has no `file:` references, so the cause is a Firefox extension and no code change is needed.
