# Review of `api/app.py`

## Unused functions

None. Functions without a direct call are registered through decorators or
framework hooks:

- `get_csrf_config` (`@CsrfProtect.load_config`)
- `lifespan` (passed to `FastAPI`)
- `revalidate_cached_responses`, `csrf_protect_exception_handler` (decorators)
- all route handlers

Every other helper has at least one caller.

## Pylance diagnostics

| Line | Code | Finding |
| --- | --- | --- |
| 52 | hint | Unused `app` parameter in `lifespan`; required by FastAPI. |
| 131 | hint | Unused `request` parameter in `csrf_protect_exception_handler`; required by the handler signature. Could be renamed `_request`. |
| 161 | `reportAttributeAccessIssue` | `validate_form_csrf` assigns the private `_token_location`, which the type checker treats as a ClassVar. |
| 406 | `reportArgumentType` | `ui_post_submit` passes a possibly-`None` `user` to `_publish_job`. `_dispatcher_redirect` guarantees a user when there is no redirect, but the type checker cannot infer that. |

## `csrf_protect_exception_handler`

The handler is correct: `CsrfProtectError` exposes `status_code` and `message`,
and the handler covers every subclass (400 missing token, 401 invalid token,
422 bad header).

1. **Raw JSON on form failures.** Server-rendered form routes (`/account/*`,
   `/post`, `/post/delete/{id}`) also use this handler, so an expired or missing
   CSRF token shows plain `{"detail": ...}` instead of the page with an error.
   A fix would redirect or re-render for form routes and keep JSON for `/api/*`.
2. **401 for an invalid token.** Chosen by the library; 403 is more conventional
   but would change tested status codes.
3. **`CSRF_SECRET` fallback.** If unset, a random secret is generated per process,
   so tokens fail after a restart (including dev reload) and across multiple
   workers. Set `CSRF_SECRET` in any real deployment.

## WebSocket connection manager

- `active_connections` is a `set[WebSocket]`, which prevents duplicate
  registration. It has no ordering guarantee, which nothing relies on.
- State is in-process memory. Running multiple processes would need a shared
  pub/sub service such as Redis (see the TODO in `ConnectionManager`).
- `broadcast` is called from two places: `ui_post_delete`, `_publish_job`
  (shared by the form create path).
