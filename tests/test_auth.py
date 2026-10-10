import asyncio
import re
import sqlite3
import sys
import unittest
import warnings
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import api.auth as auth  # noqa: E402
import api.db as db  # noqa: E402
from api.forms import LoginFormData, SignupFormData  # noqa: E402

warnings.filterwarnings("ignore", message=".*httpx.*")
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from api.config import AUTH_COOKIE  # noqa: E402
from api.main import app  # noqa: E402

PASSWORD = "correct-horse"
CSRF_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')


class DatabaseTestCase(unittest.TestCase):
    """Runs each test against a fresh in-memory users database."""

    def setUp(self):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        # auth.py imports CONNECTION by name, so both modules must be patched
        for module in (db, auth):
            patcher = patch.object(module, "CONNECTION", self.connection)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.connection.close)
        db.init_db()

    def stored_user(self, username):
        return self.connection.execute(
            "SELECT username, password_hash, disabled FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    def disable(self, username):
        self.connection.execute(
            "UPDATE users SET disabled = TRUE WHERE username = ?", (username,))
        self.connection.commit()


class PasswordTests(unittest.TestCase):
    def test_hash_verifies_only_the_original_password(self):
        hashed = auth.get_password_hash(PASSWORD)

        self.assertNotEqual(hashed, PASSWORD)
        self.assertTrue(auth.verify_password(PASSWORD, hashed))
        self.assertFalse(auth.verify_password("wrong-password", hashed))

    def test_hashing_is_salted(self):
        self.assertNotEqual(
            auth.get_password_hash(PASSWORD), auth.get_password_hash(PASSWORD))

    def test_empty_password_is_rejected(self):
        with self.assertRaises(ValueError):
            auth.get_password_hash("")


class FormModelTests(unittest.TestCase):
    def test_valid_credentials_are_accepted(self):
        for model in (SignupFormData, LoginFormData):
            with self.subTest(model=model.__name__):
                form = model(username="alice_01", password=PASSWORD)
                self.assertEqual(form.username, "alice_01")

    def test_invalid_credentials_are_rejected(self):
        invalid = [
            {"username": "ab", "password": PASSWORD},
            {"username": "a" * 33, "password": PASSWORD},
            {"username": "bad name!", "password": PASSWORD},
            {"username": "alice", "password": "short"},
            {"username": "alice", "password": "p" * 129},
            {"username": "alice"},
            {"password": PASSWORD},
        ]
        for model in (SignupFormData, LoginFormData):
            for data in invalid:
                with self.subTest(model=model.__name__, data=data):
                    with self.assertRaises(ValidationError):
                        model(**data)


class UserStorageTests(DatabaseTestCase):
    def test_create_user_returns_id_and_stores_hash_not_password(self):
        user_id = auth.create_user("alice", PASSWORD)

        self.assertIsInstance(user_id, int)
        username, password_hash, disabled = self.stored_user("alice")
        self.assertEqual(username, "alice")
        self.assertNotIn(PASSWORD, password_hash)
        self.assertTrue(auth.verify_password(PASSWORD, password_hash))
        self.assertEqual(disabled, 0)

    def test_duplicate_username_returns_none(self):
        auth.create_user("alice", PASSWORD)

        self.assertIsNone(auth.create_user("alice", "another-password"))

    def test_duplicate_username_is_case_insensitive(self):
        auth.create_user("alice", PASSWORD)

        self.assertIsNone(auth.create_user("ALICE", "another-password"))
        count = self.connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        self.assertEqual(count, 1)

    def test_create_user_with_empty_password_raises(self):
        with self.assertRaises(ValueError):
            auth.create_user("alice", "")

    def test_lookup_returns_user_or_none(self):
        auth.create_user("alice", PASSWORD)

        user = auth._get_user_by_username("alice")
        self.assertEqual(user.username, "alice")
        self.assertFalse(user.disabled)
        self.assertIsNone(auth._get_user_by_username("nobody"))


class AuthenticateUserTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        auth.create_user("alice", PASSWORD)

    def test_correct_credentials_return_the_user(self):
        user = auth.authenticate_user("alice", PASSWORD)

        self.assertEqual(user.username, "alice")

    def test_username_match_ignores_case(self):
        self.assertTrue(auth.authenticate_user("ALICE", PASSWORD))

    def test_wrong_password_returns_false(self):
        self.assertFalse(auth.authenticate_user("alice", "wrong-password"))

    def test_unknown_user_returns_false(self):
        self.assertFalse(auth.authenticate_user("nobody", PASSWORD))

    def test_unknown_user_still_runs_a_password_check(self):
        with patch.object(auth, "verify_password", return_value=False) as verify:
            auth.authenticate_user("nobody", PASSWORD)

        verify.assert_called_once_with(PASSWORD, auth.DUMMY_HASH)

    def test_disabled_user_still_authenticates(self):
        self.disable("alice")

        user = auth.authenticate_user("alice", PASSWORD)

        self.assertTrue(user.disabled)


class TokenTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        auth.create_user("alice", PASSWORD)

    def test_token_round_trips_to_the_user(self):
        token = auth.create_access_token({"sub": "alice"})

        self.assertEqual(auth.get_user_from_token(token).username, "alice")

    def test_missing_or_garbage_token_gives_none(self):
        for token in (None, "", "not-a-jwt"):
            with self.subTest(token=token):
                self.assertIsNone(auth.get_user_from_token(token))

    def test_expired_token_gives_none(self):
        token = auth.create_access_token(
            {"sub": "alice"}, expires_delta=timedelta(minutes=-1))

        self.assertIsNone(auth.get_user_from_token(token))

    def test_token_signed_with_another_key_gives_none(self):
        with patch.object(auth, "SECRET_KEY", "some-other-secret-key-0123456789abcdef"):
            token = auth.create_access_token({"sub": "alice"})

        self.assertIsNone(auth.get_user_from_token(token))

    def test_token_without_subject_gives_none(self):
        self.assertIsNone(auth.get_user_from_token(auth.create_access_token({})))

    def test_token_for_deleted_user_gives_none(self):
        token = auth.create_access_token({"sub": "ghost"})

        self.assertIsNone(auth.get_user_from_token(token))

    def test_default_expiry_is_fifteen_minutes(self):
        token = auth.create_access_token({"sub": "alice"})
        payload = auth.jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        remaining = payload["exp"] - auth.datetime.now(auth.timezone.utc).timestamp()

        self.assertTrue(14 * 60 < remaining <= 15 * 60)


class CurrentUserDependencyTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        auth.create_user("alice", PASSWORD)

    def test_get_current_user_returns_user_for_valid_token(self):
        token = auth.create_access_token({"sub": "alice"})

        user = asyncio.run(auth.get_current_user(token))

        self.assertEqual(user.username, "alice")

    def test_get_current_user_raises_401_for_missing_or_bad_token(self):
        for token in (None, "bad-token"):
            with self.subTest(token=token):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(auth.get_current_user(token))
                self.assertEqual(caught.exception.status_code, 401)
                self.assertEqual(
                    caught.exception.headers, {"WWW-Authenticate": "Bearer"})

    def test_get_current_active_user_allows_enabled_user(self):
        user = auth._get_user_by_username("alice")

        self.assertIs(asyncio.run(auth.get_current_active_user(user)), user)

    def test_get_current_active_user_rejects_disabled_user(self):
        self.disable("alice")
        user = auth._get_user_by_username("alice")

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(auth.get_current_active_user(user))
        self.assertEqual(caught.exception.status_code, 400)


class WebTestCase(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app, follow_redirects=False)

    def csrf_token(self, page="/login"):
        match = CSRF_FIELD.search(self.client.get(page).text)
        self.assertIsNotNone(match)
        return match.group(1)

    def post_form(self, url, page=None, **fields):
        token = self.csrf_token(page or url)
        return self.client.post(url, data={"csrf_token": token, **fields})

    def signup(self, username="alice", password=PASSWORD):
        return self.post_form("/signup", username=username, password=password)

    def login(self, username="alice", password=PASSWORD):
        return self.post_form("/login", username=username, password=password)

    def create_and_login(self, username="alice"):
        auth.create_user(username, PASSWORD)
        response = self.login(username)
        self.assertEqual(response.status_code, 303)
        return response


class SignupRouteTests(WebTestCase):
    def test_signup_page_renders_form_with_csrf_token(self):
        response = self.client.get("/signup")

        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/signup"', response.text)
        self.assertRegex(response.text, CSRF_FIELD)

    def test_signup_creates_user_and_redirects_to_login(self):
        response = self.signup()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?created=true")
        self.assertIsNotNone(self.stored_user("alice"))

    def test_signup_does_not_log_the_user_in(self):
        response = self.signup()

        self.assertNotIn(AUTH_COOKIE, response.headers.get("set-cookie", ""))
        self.assertEqual(self.client.get("/account").status_code, 303)

    def test_signup_stores_a_hash_not_the_password(self):
        self.signup()

        self.assertNotIn(PASSWORD, self.stored_user("alice")[1])

    def test_duplicate_username_is_a_conflict_and_keeps_username(self):
        self.signup()

        response = self.signup(password="another-password")

        self.assertEqual(response.status_code, 409)
        self.assertIn("Username is already taken", response.text)
        self.assertIn('value="alice"', response.text)

    def test_duplicate_username_check_ignores_case(self):
        self.signup()

        self.assertEqual(self.signup(username="ALICE").status_code, 409)

    def test_invalid_input_rerenders_form_with_error(self):
        cases = {
            "short username": {"username": "ab", "password": PASSWORD},
            "bad characters": {"username": "bad name!", "password": PASSWORD},
            "short password": {"username": "alice", "password": "short"},
            "long password": {"username": "alice", "password": "p" * 129},
            "missing password": {"username": "alice"},
            "missing username": {"password": PASSWORD},
        }
        for name, fields in cases.items():
            with self.subTest(name):
                response = self.post_form("/signup", **fields)

                self.assertEqual(response.status_code, 422)
                self.assertIn("3-32 letters, digits or underscores", response.text)
                self.assertIsNone(self.stored_user(fields.get("username", "")))

    def test_invalid_signup_keeps_the_submitted_username(self):
        response = self.post_form("/signup", username="bad name!", password=PASSWORD)

        self.assertIn('value="bad name!"', response.text)

    def test_long_username_is_not_echoed_in_full(self):
        response = self.post_form("/signup", username="x" * 500, password=PASSWORD)

        self.assertEqual(response.status_code, 422)
        self.assertIn("x" * 32, response.text)
        self.assertNotIn("x" * 33, response.text)

    def test_bad_csrf_token_is_rejected(self):
        self.client.get("/signup")

        response = self.client.post(
            "/signup",
            data={"csrf_token": "forged", "username": "alice", "password": PASSWORD},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.stored_user("alice"))

    def test_missing_csrf_token_is_rejected(self):
        self.client.get("/signup")

        response = self.client.post(
            "/signup", data={"username": "alice", "password": PASSWORD})

        self.assertGreaterEqual(response.status_code, 400)
        self.assertIsNone(self.stored_user("alice"))


class LoginRouteTests(WebTestCase):
    def test_login_page_renders_form_with_csrf_token(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/login"', response.text)
        self.assertRegex(response.text, CSRF_FIELD)

    def test_login_page_shows_notice_after_signup(self):
        plain = self.client.get("/login")
        created = self.client.get("/login?created=true")

        self.assertNotEqual(plain.text, created.text)

    def test_successful_login_sets_session_cookie_and_redirects(self):
        auth.create_user("alice", PASSWORD)

        response = self.login()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account")
        set_cookie = response.headers["set-cookie"]
        self.assertIn(f"{AUTH_COOKIE}=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=lax", set_cookie)
        self.assertRegex(set_cookie, r"Max-Age=86400")

    def test_session_cookie_holds_a_token_for_the_user(self):
        self.create_and_login()

        token = self.client.cookies.get(AUTH_COOKIE)

        self.assertEqual(auth.get_user_from_token(token).username, "alice")

    def test_login_ignores_username_case(self):
        auth.create_user("alice", PASSWORD)

        self.assertEqual(self.login(username="ALICE").status_code, 303)

    def test_wrong_password_is_unauthorized_and_sets_no_cookie(self):
        auth.create_user("alice", PASSWORD)

        response = self.login(password="wrong-password")

        self.assertEqual(response.status_code, 401)
        self.assertIn("Incorrect username or password", response.text)
        self.assertIn('value="alice"', response.text)
        self.assertNotIn(AUTH_COOKIE, response.headers.get("set-cookie", ""))

    def test_unknown_user_gets_the_same_error_as_wrong_password(self):
        auth.create_user("alice", PASSWORD)

        wrong_password = self.login(password="wrong-password")
        unknown_user = self.login(username="nobody")

        self.assertEqual(unknown_user.status_code, wrong_password.status_code)
        self.assertIn("Incorrect username or password", unknown_user.text)

    def test_invalid_login_input_gets_the_generic_error(self):
        cases = [
            {"username": "alice", "password": "short"},
            {"username": "ab", "password": PASSWORD},
            {"username": "alice"},
            {"password": PASSWORD},
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                response = self.post_form("/login", **fields)

                self.assertEqual(response.status_code, 401)
                self.assertIn("Incorrect username or password", response.text)
                self.assertNotIn(AUTH_COOKIE, response.headers.get("set-cookie", ""))

    def test_long_username_is_not_echoed_in_full(self):
        response = self.login(username="x" * 500)

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("x" * 33, response.text)

    def test_disabled_user_can_still_log_in(self):
        auth.create_user("alice", PASSWORD)
        self.disable("alice")

        response = self.login()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account")
        self.assertEqual(self.client.get("/account").status_code, 200)

    def test_bad_csrf_token_is_rejected(self):
        auth.create_user("alice", PASSWORD)
        self.client.get("/login")

        response = self.client.post(
            "/login",
            data={"csrf_token": "forged", "username": "alice", "password": PASSWORD},
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn(AUTH_COOKIE, response.headers.get("set-cookie", ""))

    def test_logged_in_user_is_redirected_away_from_login_page(self):
        self.create_and_login()

        response = self.client.get("/login")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account")

    def test_invalid_session_cookie_still_shows_login_page(self):
        self.client.cookies.set(AUTH_COOKIE, "not-a-jwt")

        self.assertEqual(self.client.get("/login").status_code, 200)


class LogoutRouteTests(WebTestCase):
    def test_logout_clears_cookie_and_redirects_home(self):
        self.create_and_login()

        response = self.post_form("/logout", page="/account")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        self.assertRegex(response.headers["set-cookie"], rf"{AUTH_COOKIE}=(\"\")?;")
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_account_is_inaccessible_after_logout(self):
        self.create_and_login()

        self.post_form("/logout", page="/account")
        response = self.client.get("/account")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_logout_requires_a_valid_csrf_token(self):
        self.create_and_login()
        self.client.get("/account")

        response = self.client.post("/logout", data={"csrf_token": "forged"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/account").status_code, 200)

    def test_logout_without_a_session_still_redirects_home(self):
        response = self.post_form("/logout", page="/login")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")


class AccountPageTests(WebTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get("/account")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_logged_in_user_sees_their_account(self):
        self.create_and_login()

        response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn("alice", response.text)
        self.assertIn('action="/logout"', response.text)
        self.assertRegex(response.text, CSRF_FIELD)

    def test_invalid_or_expired_cookie_redirects_to_login(self):
        auth.create_user("alice", PASSWORD)
        expired = auth.create_access_token(
            {"sub": "alice"}, expires_delta=timedelta(minutes=-1))
        for token in ("not-a-jwt", expired):
            with self.subTest(token=token[:10]):
                self.client.cookies.set(AUTH_COOKIE, token)

                response = self.client.get("/account")

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/login")

    def test_cookie_for_a_deleted_user_redirects_to_login(self):
        self.create_and_login()
        self.connection.execute("DELETE FROM users")
        self.connection.commit()

        self.assertEqual(self.client.get("/account").status_code, 303)

    def test_landing_page_offers_login_and_signup_to_anonymous_user(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/login"', response.text)
        self.assertIn('href="/signup"', response.text)

    def test_landing_page_redirects_logged_in_user_to_account(self):
        self.create_and_login()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account")

    def test_landing_page_shows_landing_for_invalid_cookie(self):
        self.client.cookies.set(AUTH_COOKIE, "not-a-jwt")

        self.assertEqual(self.client.get("/").status_code, 200)


class TokenEndpointTests(WebTestCase):
    def setUp(self):
        super().setUp()
        auth.create_user("alice", PASSWORD)

    def test_valid_credentials_return_a_bearer_token(self):
        response = self.client.post(
            "/token", data={"username": "alice", "password": PASSWORD})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(
            auth.get_user_from_token(body["access_token"]).username, "alice")

    def test_wrong_credentials_are_unauthorized(self):
        for data in (
            {"username": "alice", "password": "wrong-password"},
            {"username": "nobody", "password": PASSWORD},
        ):
            with self.subTest(data=data):
                response = self.client.post("/token", data=data)

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_missing_fields_are_a_validation_error(self):
        response = self.client.post("/token", data={"username": "alice"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("detail", response.json())

    def test_token_endpoint_does_not_need_a_csrf_token(self):
        response = self.client.post(
            "/token", data={"username": "alice", "password": PASSWORD})

        self.assertEqual(response.status_code, 200)


class HealthTests(unittest.TestCase):
    def test_health_endpoint_reports_ok(self):
        response = TestClient(app).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
