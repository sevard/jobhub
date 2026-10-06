import sqlite3
import re
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

        request = self.client.request
        self.raw_request = request

        def request_with_csrf(method, url, *args, **kwargs):
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                page = request("GET", "/account/home", follow_redirects=True)
                match = re.search(
                    r'name="csrf_token" value="([^"]+)"', page.text
                )
                self.assertIsNotNone(match)
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", match.group(1))
                kwargs["headers"] = headers
                if kwargs.get("json") is None and url.startswith(("/post", "/account")):
                    kwargs["data"] = {"csrf_token": match.group(1), **(kwargs.get("data") or {})}
            return request(method, url, *args, **kwargs)

        self.client.request = request_with_csrf

    def credentials(self, username="alice", password="s3cretpass", role="driver"):
        return {"username": username, "password": password, "role": role}

    def signup(self, *args, **kwargs):
        return self.client.post("/account/signup", data=self.credentials(*args, **kwargs))

    def login_payload(self, username="alice", password="s3cretpass"):
        return {"username": username, "password": password}

    JOB = {"pickup_time": "2030-01-01T10:00:00", "pickup_location": "A", "dropoff_location": "B"}

    def post_job(self):
        return self.client.post("/post", data=self.JOB)

    def job_ids(self):
        return [row[0] for row in self.connection.execute("SELECT id FROM jobs")]

    def test_signup_logs_user_in_and_shows_account_home(self):
        response = self.signup()

        self.assertEqual((response.status_code, response.headers["location"]), (303, "/account/home"))
        self.assertIn("auth_token", response.cookies)
        home = self.client.get("/account/driver")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Welcome, alice", home.text)

    def test_password_is_not_stored_in_plain_text(self):
        self.signup()

        stored = self.connection.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("s3cretpass", stored)

    def test_duplicate_username_is_rejected_case_insensitively(self):
        self.signup()

        response = self.signup("ALICE")
        self.assertEqual(response.status_code, 409)

    def test_login_with_valid_credentials_redirects_account_page_to_home(self):
        self.signup()
        self.client.cookies.clear()

        response = self.client.post("/account/login", data=self.login_payload())
        self.assertEqual(response.status_code, 303)

        page = self.client.get("/account")
        self.assertEqual(page.status_code, 303)
        self.assertEqual(page.headers["location"], "/account/home")

    def test_login_with_wrong_password_fails(self):
        self.signup()
        self.client.cookies.clear()

        response = self.client.post("/account/login", data=self.login_payload(password="wrongpass1"))
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("auth_token", response.cookies)

    def test_landing_page_redirects_logged_in_user_to_account_home(self):
        self.assertEqual(self.client.get("/").status_code, 200)

        self.signup()
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
        self.assertIn('action="/account/login"', response.text)
        self.assertIn("fastapi-csrf-token", response.cookies)

    def test_signup_rejects_missing_or_invalid_csrf_token(self):
        missing = self.raw_request("POST", "/account/signup", data=self.credentials())
        self.assertEqual(missing.status_code, 400)

        page = self.client.get("/account")
        token = re.search(
            r'name="csrf_token" value="([^"]+)"', page.text
        ).group(1)
        invalid = self.raw_request(
            "POST",
            "/account/signup",
            data={**self.credentials(), "csrf_token": f"{token}invalid"},
        )
        self.assertEqual(invalid.status_code, 401)

    def test_logout_ends_session(self):
        self.signup()

        response = self.client.post("/account/logout")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.client.get("/account/home").status_code, 303)

    def test_invalid_credentials_are_rejected(self):
        for payload in (
            self.credentials(username="ab"),
            self.credentials(username="bad name!"),
            self.credentials(password="short"),
        ):
            response = self.client.post("/account/signup", data=payload)
            self.assertEqual(response.status_code, 422, payload)

    def test_signup_requires_valid_role(self):
        for role in (None, "admin"):
            payload = self.credentials()
            if role is None:
                del payload["role"]
            else:
                payload["role"] = role
            self.assertEqual(self.client.post("/account/signup", data=payload).status_code, 422, role)

    def test_dispatcher_can_create_and_delete_any_job(self):
        self.signup("pub_one", role="dispatcher")
        self.assertEqual(self.post_job().status_code, 303)
        job_id = self.job_ids()[0]
        self.client.cookies.clear()

        self.signup("pub_two", role="dispatcher")
        self.assertEqual(self.client.post(f"/post/delete/{job_id}").status_code, 303)
        self.assertEqual(self.job_ids(), [])

    def test_server_rendered_forms_cover_signup_post_delete_and_logout(self):
        form = {"username": "pub_one", "password": "s3cretpass", "role": "dispatcher"}
        response = self.client.post("/account/signup", data=form)
        self.assertEqual((response.status_code, response.headers["location"]), (303, "/account/home"))

        page = self.client.get("/post")
        self.assertIn('action="/post"', page.text)
        job = {"pickup_time": self.JOB["pickup_time"], "pickup_location": " A ", "dropoff_location": "B"}
        response = self.client.post("/post", data=job)
        self.assertEqual((response.status_code, response.headers["location"]), (303, "/post"))
        self.assertIn("/post/delete/1", self.client.get("/post").text)

        bad = self.client.post("/post", data={**job, "pickup_location": " "})
        self.assertEqual(bad.status_code, 422)
        self.assertIn("Locations are required", bad.text)

        self.assertEqual(self.client.post("/post/delete/1").status_code, 303)
        self.assertNotIn("/post/delete/1", self.client.get("/post").text)

        response = self.client.post("/account/logout")
        self.assertEqual(response.headers["location"], "/account")
        self.assertEqual(self.client.get("/account/home").headers["location"], "/account")

    def test_server_rendered_login_errors_and_csrf(self):
        self.client.post("/account/signup", data={"username": "alice", "password": "s3cretpass", "role": "driver"})
        self.client.cookies.clear()
        wrong = self.client.post("/account/login", data={"username": "alice", "password": "wrongpass1"})
        self.assertEqual(wrong.status_code, 401)
        self.assertIn("Invalid username or password", wrong.text)
        ok = self.client.post("/account/login", data={"username": "alice", "password": "s3cretpass"})
        self.assertEqual(ok.status_code, 303)
        self.assertIn("auth_token", ok.cookies)

        missing = self.raw_request("POST", "/account/logout", data={})
        self.assertEqual(missing.status_code, 400)

    def test_driver_cannot_create_or_delete_jobs(self):
        self.signup("pub_one", role="dispatcher")
        self.post_job()
        job_id = self.job_ids()[0]
        self.client.cookies.clear()

        self.signup("driver_one", role="driver")
        for response in (self.post_job(), self.client.post(f"/post/delete/{job_id}")):
            self.assertEqual(
                (response.status_code, response.headers["location"]), (303, "/account/home")
            )
        self.assertEqual(self.job_ids(), [job_id])

    def test_logged_out_user_cannot_create_or_delete_jobs(self):
        self.signup("pub_one", role="dispatcher")
        self.post_job()
        job_id = self.job_ids()[0]
        self.client.cookies.clear()

        for response in (self.post_job(), self.client.post(f"/post/delete/{job_id}")):
            self.assertEqual(
                (response.status_code, response.headers["location"]), (303, "/account")
            )
        self.assertEqual(self.job_ids(), [job_id])

    def test_websocket_requires_login(self):
        from starlette.websockets import WebSocketDisconnect

        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws"):
                pass

    def test_websocket_broadcasts_jobs_and_ignores_client_messages(self):
        self.signup("dispatcher_one", role="dispatcher")

        with self.client.websocket_connect("/ws") as websocket:
            websocket.send_text(
                '{"type":"message","pickup_location":"untrusted client"}'
            )
            self.assertEqual(
                self.client.get("/api/get_jobs").json()["messages"], []
            )

            response = self.post_job()
            self.assertEqual(response.status_code, 303)
            event = websocket.receive_json()
            self.assertEqual(event["type"], "message")
            self.assertEqual(
                event["pickup_location"], self.JOB["pickup_location"]
            )

            response = self.client.post(f"/post/delete/{event['id']}")
            self.assertEqual(response.status_code, 303)
            delete_event = websocket.receive_json()

        self.assertEqual(delete_event, {"type": "delete", "id": event["id"]})

    def test_static_assets_and_api_must_revalidate(self):
        for url in ("/ui/static/feed.js", "/api/health", "/api/get_jobs"):
            self.assertEqual(self.client.get(url).headers["cache-control"], "no-cache")

    def test_feed_and_job_list_require_login(self):
        feed = self.client.get("/feed")
        self.assertEqual(feed.status_code, 303)
        self.assertEqual(feed.headers["location"], "/account")
        self.assertEqual(self.client.get("/api/get_jobs").status_code, 401)

        self.signup("driver_one", role="driver")
        self.assertEqual(self.client.get("/feed").status_code, 200)
        self.assertEqual(self.client.get("/api/get_jobs").status_code, 200)

    def test_post_page_is_dispatcher_only(self):
        self.assertEqual(self.client.get("/post").headers["location"], "/account")

        self.signup("driver_one", role="driver")
        response = self.client.get("/post")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/account/home")

        self.client.cookies.clear()
        self.signup("pub_one", role="dispatcher")
        self.assertEqual(self.client.get("/post").status_code, 200)

    def test_account_home_redirects_to_role_page(self):
        self.signup("driver_one", role="driver")
        self.assertEqual(self.client.get("/account/home").headers["location"], "/account/driver")
        self.assertEqual(self.client.get("/account/dispatcher").headers["location"], "/account/driver")
        page = self.client.get("/account/driver").text
        self.assertIn('href="/feed"', page)
        self.assertNotIn('href="/post"', page)

        self.client.cookies.clear()
        self.assertEqual(self.client.get("/account/driver").headers["location"], "/account")
        self.signup("pub_one", role="dispatcher")
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
