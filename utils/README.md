# utils

Command-line tools for running JobHub. Run them from the project root with
`uv run python -m utils.<tool>`. They use the same configuration and database
as the app, so PostgreSQL must be running first; see [HOWTO.md](HOWTO.md).

## create_admin

Creates an admin account, or promotes an existing user to admin. Admins cannot
be created through the website: sign-up only ever creates drivers.

```bash
uv run python -m utils.create_admin USERNAME [--promote [--yes]]
```

| Argument | Meaning |
| --- | --- |
| `USERNAME` | The account to create (or, with `--promote`, to promote). Matching is case-insensitive. |
| `--promote` | Make an existing user an admin and keep their password. |
| `--yes` | With `--promote`, skip the `[y/N]` confirmation. |

### What it does

- **Without `--promote`** it creates a new admin. The password is typed at a
  hidden prompt, twice; it is never taken as an argument, so it does not end up
  in the shell history or the process list.
- **With `--promote`** it changes the role of an existing user to `admin` after
  you confirm. Anything other than `y` or `yes` cancels without changes.
- It creates the tables if they are missing (`init_db()`), so it also works
  against a fresh, empty database.
- The username and password follow the sign-up rules: a username of 3-32
  letters, digits or `_`, and a password of 8-128 characters. The password is
  hashed with Argon2, like every other account.

### Results and exit codes

| Situation | Message | Exit code |
| --- | --- | --- |
| Admin created | `Admin 'name' created.` | 0 |
| User promoted | `User 'name' is now an admin.` | 0 |
| User is already an admin | `User 'name' is already an admin.` | 0 |
| Username exists, no `--promote` | `User 'name' already exists. Use --promote to make them an admin.` | 1 |
| `--promote` for an unknown user | `User 'name' does not exist.` | 1 |
| Promotion not confirmed | `Cancelled. No changes made.` | 1 |
| Bad username or password | `Invalid username or password.` | 1 |
| The two passwords differ | `Passwords do not match.` | 1 |

If the database cannot be reached, the tool waits 10 seconds and then stops
with a `PoolTimeout` error; see [HOWTO.md](HOWTO.md#troubleshooting).

### Code

[create_admin.py](create_admin.py) calls `create_user` and `set_user_role` from
[api/auth.py](../api/auth.py). It is the only place that may pass a role to
`create_user`; the sign-up route must never take a role from a request.
