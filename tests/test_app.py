import asyncio
import importlib
import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from api.db import DB_PATH


def _make_request(cookies=None):
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = {}
    return request


def _make_response():
    return MagicMock()


class DevelopmentModeTests(unittest.TestCase):
    def setUp(self):
        self.original_env = os.environ.get("APP_ENV")
        sys.modules.pop("api.app", None)

    def tearDown(self):
        if self.original_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = self.original_env
        sys.modules.pop("api.app", None)

    def test_development_mode_is_enabled_from_environment(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        self.assertTrue(app_module.is_development)
        self.assertTrue(app_module.app.state.development_mode)

    def test_root_response_reports_development_mode(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        async def get_root():
            response = await app_module.root()
            return response

        response = asyncio.run(get_root())

        self.assertTrue(response["development_mode"])

    def test_info_reports_websocket_endpoint(self):
        app_module = importlib.import_module("api.app")

        response = asyncio.run(app_module.root())

        self.assertEqual(response["websocket_endpoints"], ["/ws"])
        self.assertNotIn("event_stream_endpoints", response)

    def test_run_server_uses_import_string_for_reload(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        with patch("api.app.uvicorn.run") as run_mock:
            app_module.run_server()

        self.assertEqual(run_mock.call_args.args[0], "api.app:app")
        self.assertEqual(run_mock.call_args.kwargs["app_dir"], str(app_module.BASE_DIR))
        self.assertTrue(run_mock.call_args.kwargs["reload"])
        self.assertEqual(run_mock.call_args.kwargs["host"], "0.0.0.0")
        self.assertEqual(run_mock.call_args.kwargs["port"], 8001)

    def test_messages_endpoint_returns_stored_messages(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        app_module.init_db()  # Need to make sure DB is initialized since we deleted it
        app_module.save_job("test-session", "2024-05-15T12:00", "LAX", "San Francisco", "note text")

        with patch.object(app_module, "current_user", return_value={"id": 1, "username": "u", "role": "driver"}):
            response = asyncio.run(app_module.get_jobs(_make_request()))

        self.assertIn("messages", response)
        contents = [message["pickup_location"] for message in response["messages"]]
        self.assertIn("LAX", contents)

        with sqlite3.connect(DB_PATH) as connection:
            connection.execute("DELETE FROM jobs WHERE pickup_location = ?", ("LAX",))

    def test_publish_job_saves_and_broadcasts(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        with patch.object(app_module, "save_job") as save_mock, \
                patch.object(app_module.manager, "broadcast") as broadcast_mock:
            save_mock.return_value = 42
            payload = app_module.JobPayload(
                pickup_time="2026-05-15T12:00:00",
                pickup_location="SFO",
                dropoff_location="San Jose",
                note="Fragile"
            )
            result = asyncio.run(app_module._publish_job({"id": 7}, payload))

        save_mock.assert_called_once_with(7, "2026-05-15T12:00:00", "SFO", "San Jose", "Fragile")
        broadcast_mock.assert_called_once_with(
            json.dumps({
                "type": "message",
                "id": 42,
                "user_id": 7,
                "pickup_time": "2026-05-15T12:00:00",
                "pickup_location": "SFO",
                "dropoff_location": "San Jose",
                "note": "Fragile"
            })
        )
        self.assertEqual(result, 42)

    def _delete_job_via_form(self, app_module, user, job_exists=True):
        with patch.object(app_module, "current_user", return_value=user), \
                patch.object(app_module, "validate_form_csrf", new=AsyncMock()), \
                patch.object(app_module, "delete_job", return_value=job_exists) as delete_mock, \
                patch.object(app_module.manager, "broadcast") as broadcast_mock:
            response = asyncio.run(
                app_module.ui_post_delete(7, _make_request(), MagicMock())
            )
        return response, delete_mock, broadcast_mock

    def test_post_delete_removes_and_broadcasts(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        response, delete_mock, broadcast_mock = self._delete_job_via_form(
            app_module, {"id": 1, "username": "pub", "role": "dispatcher"}
        )

        delete_mock.assert_called_once_with(7)
        broadcast_mock.assert_called_once_with(json.dumps({"type": "delete", "id": 7}))
        self.assertEqual((response.status_code, response.headers["location"]), (303, "/post"))

    def test_post_delete_does_not_broadcast_when_job_is_missing(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        response, _, broadcast_mock = self._delete_job_via_form(
            app_module, {"id": 1, "username": "pub", "role": "dispatcher"}, job_exists=False
        )

        broadcast_mock.assert_not_called()
        self.assertEqual(response.status_code, 303)

    def test_post_delete_redirects_when_not_logged_in(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        response, delete_mock, broadcast_mock = self._delete_job_via_form(app_module, None)

        delete_mock.assert_not_called()
        broadcast_mock.assert_not_called()
        self.assertEqual(response.headers["location"], "/account")
