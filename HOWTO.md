# Commands how to run server and execute tests

## Running server

Start the server from the project root with:

```bash
uv run python -m api.app
```

Then open http://127.0.0.1:8001/ (publisher at `/post`, feed at `/feed`, health check at `/api/health`).

## Running tests

Run the test suite from the project root with:

```bash
uv run python -m unittest discover -s tests -q
```

This uses the project's configured Python environment and runs all tests under the tests directory.
