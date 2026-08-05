# Commands how to run server and execute tests

## Running server

Run the test suite from the project root with:

```bash
uv run python -m api.app
    
```

## Running tests

Run the test suite from the project root with:

```bash
uv run python -m unittest discover -s tests -q
```

This uses the project's configured Python environment and runs all tests under the tests directory.
