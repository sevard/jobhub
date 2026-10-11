# How to create an admin (PostgreSQL in Docker)

The database runs in a Docker container (see [compose.yaml](../compose.yaml)).
`create_admin` runs on your machine, not in the container, and reaches the
database through the port Docker publishes on `127.0.0.1`. Commands below are
run from the project root.

## 1. One-time setup

```bash
cp config.ini.example config.ini   # set secret_key and the [database] URLs
cp .env.example .env               # set POSTGRES_USER and POSTGRES_PASSWORD
```

The user and password in the `[database] url` of `config.ini` must be the same
as `POSTGRES_USER` and `POSTGRES_PASSWORD` in `.env`, and the port in the URL
must match `POSTGRES_PORT` (default 5432). Both files are git-ignored. You can
use the `DATABASE_URL` environment variable instead of `config.ini`.

## 2. Start PostgreSQL

```bash
docker compose up -d --wait
```

`--wait` returns once the container is healthy. The data lives in the
`jobhub-pgdata` Docker volume, so it survives restarts and `docker compose
down`. Only `docker compose down -v` deletes it.

## 3. Create the first admin

```bash
uv run python -m utils.create_admin alice_admin
```

Type the password twice at the hidden prompts. On success it prints
`Admin 'alice_admin' created.`; log in at <http://127.0.0.1:8080/login> and open
`/admin`.

## Promote an existing driver

```bash
uv run python -m utils.create_admin some_driver --promote        # asks y/N
uv run python -m utils.create_admin some_driver --promote --yes   # no prompt
```

The role is read from the database on every request, so the change applies
immediately, even to a user who is already logged in.

## Check the result inside the container

```bash
docker compose exec db sh -c \
  'psql -U "$POSTGRES_USER" -d jobhub -c "SELECT id, username, role FROM users"'
```

`docker compose exec db` runs the command in the database container, which
already has `POSTGRES_USER` set. You can also connect with pgAdmin to
`127.0.0.1` on the same port, using the same user and password.

## Starting over

Recreate the database, then create the admin again:

```bash
docker compose down -v
docker compose up -d --wait
uv run python -m utils.create_admin alice_admin
```

## Troubleshooting

- **`PoolTimeout: pool initialization incomplete after 10 sec`**: the database
  is unreachable. Check that the container is up (`docker compose ps`), and
  that the host, port, user and password in `config.ini` (or `DATABASE_URL`)
  match `.env`.
- **`password authentication failed`** (logged just before the `PoolTimeout`):
  the user or password in the URL does not match the database. A Postgres
  volume keeps the user and password it was first created with, so after
  changing them in `.env`, recreate the volume with `docker compose down -v`.
- **`Set [database] url in ... or the DATABASE_URL variable`**: `config.ini` is
  missing or has no `[database]` section.
- **`required variable POSTGRES_USER is missing`** (from `docker compose`):
  `.env` is missing; copy `.env.example`.
- **Port 5432 already in use**: set another `POSTGRES_PORT` in `.env`, update
  the port in the `config.ini` URLs, and run `docker compose up -d --wait`
  again.

If the app itself is later run in a container, run the tool inside that
container instead (`docker compose exec <service> python -m utils.create_admin
USERNAME`), and use the database service name `db` as the host in the URL.
