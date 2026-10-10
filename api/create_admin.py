"""Create an admin account, or promote an existing user to admin.

Usage: uv run python -m api.create_admin USERNAME [--promote [--yes]]
"""
import argparse
import getpass
import sys

from pydantic import ValidationError

from api.auth import _get_user_by_username, create_user, set_user_role
from api.db import init_db
from api.forms import SignupFormData


def _read_password(prompt=getpass.getpass) -> str:
    password = prompt("Password: ")
    if prompt("Confirm password: ") != password:
        raise ValueError("Passwords do not match.")
    return password


def _confirmed(question: str, ask=input) -> bool:
    try:
        return ask(f"{question} [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def main(
    argv: list[str] | None = None, prompt=getpass.getpass, ask=input
) -> int:
    parser = argparse.ArgumentParser(
        description="Create an admin account or promote an existing user.")
    parser.add_argument("username")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="make an existing user an admin (keeps their password)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="with --promote, skip the confirmation prompt",
    )
    args = parser.parse_args(argv)

    init_db()
    existing = _get_user_by_username(args.username)

    if args.promote:
        if existing is None:
            print(f"User '{args.username}' does not exist.", file=sys.stderr)
            return 1
        if existing.role == "admin":
            print(f"User '{existing.username}' is already an admin.")
            return 0
        question = f"Promote '{existing.username}' ({existing.role}) to admin?"
        if not args.yes and not _confirmed(question, ask):
            print("Cancelled. No changes made.", file=sys.stderr)
            return 1
        set_user_role(existing.username, "admin")
        print(f"User '{existing.username}' is now an admin.")
        return 0

    if existing is not None:
        print(
            f"User '{existing.username}' already exists. Use --promote to make them an admin.",
            file=sys.stderr,
        )
        return 1

    try:
        password = _read_password(prompt)
        # Same username and password rules as the signup form
        form = SignupFormData(username=args.username, password=password)
    except ValueError as error:
        message = "Invalid username or password." if isinstance(
            error, ValidationError) else str(error)
        print(message, file=sys.stderr)
        return 1

    if create_user(form.username, form.password, role="admin") is None:
        print(f"User '{form.username}' already exists.", file=sys.stderr)
        return 1
    print(f"Admin '{form.username}' created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
