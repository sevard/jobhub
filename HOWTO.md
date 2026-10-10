# Commands how to run server and execute tests

## Running server

Start the server from the project root with:

```bash
uv run python -m api.main
```

Then open http://127.0.0.1:8001/post (create jobs) or http://127.0.0.1:8001/feed (view posted jobs). Health check: `/api/health`.

## Running tests

Before the first run, make sure `config.ini` exists in the project root (the
tests import the app, which refuses to start without it):

```bash
cp config.ini.example config.ini
```

Run the whole suite from the project root with:

```bash
uv run python -m unittest discover -s tests -q
```

Drop `-q` for the default progress output, or use `-v` to see each test name and result.
This uses the project's configured Python environment and runs every test
under the `tests` directory. A passing run ends with `OK`.

Run a single file, class or test by its dotted name:

```bash
uv run python -m unittest tests.test_auth
uv run python -m unittest tests.test_auth.LoginRouteTests
uv run python -m unittest tests.test_auth.LoginRouteTests.test_disabled_user_can_still_log_in
```

The tests use an in-memory SQLite database, so they never read or change the data in `jobhub.db`.
