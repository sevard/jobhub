# Commands how to run server and execute tests

## Running server

Start PostgreSQL and then the server from the project root with:

```bash
docker compose up -d --wait
uv run fastapi run --port 8080
```

For development with hot reload, use `uv run fastapi dev --port 8080`.

Then open http://127.0.0.1:8080/. Health check: `/api/health`.

## Running tests

Before the first run, make sure `config.ini` exists in the project root (the
tests import the app, which refuses to start without it):

```bash
cp config.ini.example config.ini   # set the user and password in the [database] URLs
cp .env.example .env               # set POSTGRES_USER and POSTGRES_PASSWORD to the same values
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

The tests need PostgreSQL (`docker compose up -d --wait`) and use the separate `jobhub_test` database, so they never read or change the development data. Set `[database] test_url` in `config.ini` (or `TEST_DATABASE_URL`) to use another server; its database name must end in `_test`.
