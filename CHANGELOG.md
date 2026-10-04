# Changelog

## Unreleased

### Added
- README.md covering features, setup, pages, HTTP API, WebSocket events, tests and layout.
- Structured ride-request board: a `jobs` table, `JobPayload` validation (pickup time and locations), and new post/feed pages with forms and live feeds.
- Tests for the job endpoints, a receive-only WebSocket, and `own_only` fetches without a session cookie.

### Changed
- Converted the generic message relay into a ride-request board; `AGENTS.md` URLs and endpoint list updated.
- The `/ws` WebSocket is now receive-only. Jobs are created only through HTTP, which requires a valid pickup time and locations.
- The post page heading is now "Current jobs".

### Fixed
- `GET /api/get_message?own_only=true` no longer returns HTTP 400 without a `session_id` cookie. It creates a session and returns an empty list.
- Malformed `href` on the Back link in `post.html`.

### Removed
- Gemini integration: `google-genai` dependency, `api/genai.py` and `config.ini` (which held a plaintext API key; rotate it if it was live).
- `patch_post.py` (one-off script) and the unused `main.py`.

### Known issues
- No migration from the old `messages` table to `jobs`.
- The HTTP API does not reject empty or whitespace-only locations.
- The Flatpickr form reset may leave stale state.
- A `file:///` console security warning on `/post` appears only in Firefox with extensions enabled; it does not occur in a private window or in Chrome. The app has no `file:` references, so the cause is a Firefox extension and no code change is needed.
