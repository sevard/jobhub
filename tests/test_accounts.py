import sqlite3
import sys
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import api.db as db

warnings.filterwarnings("ignore", message=".*httpx.*")
from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        patcher = patch.object(db, "CONNECTION", self.connection)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.connection.close)
        db.init_db()
        self.client = TestClient(app, follow_redirects=False)

    def credentials(self, username="alice", password="s3cretpass", role="driver"):
        return {"username": username, "password": password, "role": role}

    def login_payload(self, username="alice", password="s3cretpass"):
        return {"username": username, "password": password}

    JOB = {"pickup_time": "2030-01-01T10:00:00", "pickup_location": "A", "dropoff_location": "B"}

    def test_signup_logs_user_in_and_shows_account_home(self):
        response = self.client.post("/api/signup", json=self.credentials())

        self.assertEqual(response.status_code, 201)
        self.assertIn("auth_token", response.cookies)
        home = self.client.get("/account/driver")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Welcome, alice", home.text)

    def test_password_is_not_stored_in_plain_text(self):
        self.client.post("/api/signup", json=self.credentials())

        stored = self.connection.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("s3cretpass", stored)

    def test_duplicate_username_is_rejected_case_insensitively(self):
        self.client.post("/api/signup", json=self.credentials())

        response = self.client.post("/api/signup", json=self.credentials("ALICE"))
        self.assertEqual(response.status_code, 409)

    def test_login_with_valid_credentials_redirects_account_page_to_home(self):
        self.client.post("/api/signup", json=self.credentials())
        self.client.cookies.clear()

        response = self.client.post("/api/login", json=self.login_payload())
        self.assertEqual(response.status_code, 200)

        page = self.client.get("/account")
        self.assertEqual(page.status_code, 303)
        self.assertEqual(page.headers["location"], "/account/home")

    def test_login_with_wrong_password_fails(self):
        self.client.post("/api/signup", json=self.credentials())
        self.client.cookies.clear()

        response = self.client.post("/api/login", json=self.login_payload(password="wrongpass1"))
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("auth_token", response.cookies)

    def test_landing_page_redirects_logged_in_user_to_account_home(self):
        self.assertEqual(self.client.get("/").status_code, 200)

        self.client.post("/api/signup", json=self.credentials())
        response = self.client.get("/")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account/home")

    def test_account_home_requires_login(self):
        response = self.client.get("/account/home")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account")

    def test_account_page_shows_login_form_when_logged_out(self):
        response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn("authForm", response.text)

    def test_logout_ends_session(self):
        self.client.post("/api/signup", json=self.credentials())

        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/account/home").status_code, 303)

    def test_invalid_credentials_are_rejected(self):
        for payload in (
            self.credentials(username="ab"),
            self.credentials(username="bad name!"),
            self.credentials(password="short"),
        ):
            response = self.client.post("/api/signup", json=payload)
            self.assertEqual(response.status_code, 422, payload)

    def test_signup_requires_valid_role(self):
        for role in (None, "admin"):
            payload = self.credentials()
            if role is None:
                del payload["role"]
            else:
                payload["role"] = role
            self.assertEqual(self.client.post("/api/signup", json=payload).status_code, 422, role)

    def test_dispatcher_can_create_and_delete_any_job(self):
        self.client.post("/api/signup", json=self.credentials("pub_one", role="dispatcher"))
        job_id = self.client.post("/api/post_job", json=self.JOB).json()["id"]
        self.client.cookies.clear()

        self.client.post("/api/signup", json=self.credentials("pub_two", role="dispatcher"))
        self.assertEqual(self.client.delete(f"/api/delete_job/{job_id}").status_code, 200)

    def test_driver_cannot_create_or_delete_jobs(self):
        self.client.post("/api/signup", json=self.credentials("pub_one", role="dispatcher"))
        job_id = self.client.post("/api/post_job", json=self.JOB).json()["id"]
        self.client.cookies.clear()

        self.client.post("/api/signup", json=self.credentials("driver_one", role="driver"))
        self.assertEqual(self.client.post("/api/post_job", json=self.JOB).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/delete_job/{job_id}").status_code, 403)

    def test_logged_out_user_cannot_create_or_delete_jobs(self):
        self.assertEqual(self.client.post("/api/post_job", json=self.JOB).status_code, 401)
        self.assertEqual(self.client.delete("/api/delete_job/1").status_code, 401)

    def test_feed_and_job_list_require_login(self):
        feed = self.client.get("/feed")
        self.assertEqual(feed.status_code, 303)
        self.assertEqual(feed.headers["location"], "/account")
        self.assertEqual(self.client.get("/api/get_jobs").status_code, 401)

        self.client.post("/api/signup", json=self.credentials("driver_one", role="driver"))
        self.assertEqual(self.client.get("/feed").status_code, 200)
        self.assertEqual(self.client.get("/api/get_jobs").status_code, 200)

    def test_post_page_is_dispatcher_only(self):
        self.assertEqual(self.client.get("/post").headers["location"], "/account")

        self.client.post("/api/signup", json=self.credentials("driver_one", role="driver"))
        response = self.client.get("/post")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account/home")

        self.client.cookies.clear()
        self.client.post("/api/signup", json=self.credentials("pub_one", role="dispatcher"))
        self.assertEqual(self.client.get("/post").status_code, 200)

    def test_account_home_redirects_to_role_page(self):
        self.client.post("/api/signup", json=self.credentials("driver_one", role="driver"))
        self.assertEqual(self.client.get("/account/home").headers["location"], "/account/driver")
        self.assertEqual(self.client.get("/account/dispatcher").headers["location"], "/account/driver")
        page = self.client.get("/account/driver").text
        self.assertIn('href="/feed"', page)
        self.assertNotIn('href="/post"', page)

        self.client.cookies.clear()
        self.assertEqual(self.client.get("/account/driver").headers["location"], "/account")
        self.client.post("/api/signup", json=self.credentials("pub_one", role="dispatcher"))
        self.assertEqual(self.client.get("/account/home").headers["location"], "/account/dispatcher")
        self.assertEqual(self.client.get("/account/driver").headers["location"], "/account/dispatcher")
        page = self.client.get("/account/dispatcher").text
        self.assertIn('href="/post"', page)
        self.assertNotIn('href="/feed"', page)

    def test_existing_users_table_gets_driver_role_column(self):
        legacy = sqlite3.connect(":memory:", check_same_thread=False)
        legacy.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT)")
        legacy.execute("INSERT INTO users (username, password_hash) VALUES ('old', 'x$y')")
        with patch.object(db, "CONNECTION", legacy):
            db.init_db()
            role = legacy.execute("SELECT role FROM users WHERE username = 'old'").fetchone()[0]
        legacy.close()
        self.assertEqual(role, "driver")


if __name__ == "__main__":
    unittest.main()


class WebSocketAuthTests(unittest.TestCase):
    def test_ws_rejects_logged_out_clients(self):
        from starlette.websockets import WebSocketDisconnect
        client = TestClient(app)
        with self.assertRaises(WebSocketDisconnect):
            with client.websocket_connect("/ws"):
                pass
