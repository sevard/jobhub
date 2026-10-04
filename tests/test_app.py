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

        response = asyncio.run(app_module.messages(_make_request(), _make_response()))

        self.assertIn("messages", response)
        contents = [message["pickup_location"] for message in response["messages"]]
        self.assertIn("LAX", contents)

        with sqlite3.connect(DB_PATH) as connection:
            connection.execute("DELETE FROM jobs WHERE pickup_location = ?", ("LAX",))

    def test_messages_own_only_without_cookie_returns_empty_and_sets_cookie(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        app_module.init_db()
        response = _make_response()

        result = asyncio.run(app_module.messages(_make_request(), response, own_only=True))

        self.assertEqual(result["messages"], [])
        response.set_cookie.assert_called_once()
        self.assertEqual(response.set_cookie.call_args.kwargs["key"], "session_id")

    def test_create_message_saves_and_broadcasts(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        request = _make_request(cookies={"session_id": "session-abc"})
        response = _make_response()

        with patch.object(app_module, "save_job") as save_mock, \
                patch.object(app_module.manager, "broadcast") as broadcast_mock:
            save_mock.return_value = 42
            payload = app_module.JobPayload(
                pickup_time="2026-05-15T12:00:00",
                pickup_location="SFO",
                dropoff_location="San Jose",
                note="Fragile"
            )
            result = asyncio.run(app_module.create_message(payload, request, response))

        save_mock.assert_called_once_with("session-abc", "2026-05-15T12:00:00", "SFO", "San Jose", "Fragile")
        broadcast_mock.assert_called_once_with(
            json.dumps({
                "type": "message",
                "id": 42,
                "session_id": "session-abc",
                "pickup_time": "2026-05-15T12:00:00",
                "pickup_location": "SFO",
                "dropoff_location": "San Jose",
                "note": "Fragile"
            })
        )
        self.assertEqual(result, {"status": "ok", "id": 42})
        response.set_cookie.assert_not_called()

    def test_create_message_assigns_session_cookie_when_missing(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        request = _make_request()
        response = _make_response()

        with patch.object(app_module, "save_job", return_value=1), \
                patch.object(app_module.manager, "broadcast"):
            payload = app_module.JobPayload(
                pickup_time="2026-05-15T12:00",
                pickup_location="SFO",
                dropoff_location="San Jose",
                note=""
            )
            asyncio.run(app_module.create_message(payload, request, response))

        response.set_cookie.assert_called_once()
        self.assertEqual(response.set_cookie.call_args.kwargs["key"], "session_id")

    def test_websocket_input_does_not_save_or_broadcast_messages(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        websocket = MagicMock()
        websocket.accept = AsyncMock()
        websocket.receive = AsyncMock(side_effect=[
            {"type": "websocket.receive", "text": '{"pickup_location":"SFO"}'},
            {"type": "websocket.disconnect", "code": 1000},
        ])

        with patch.object(app_module, "save_job") as save_mock, \
                patch.object(app_module.manager, "broadcast") as broadcast_mock:
            asyncio.run(app_module._websocket_relay_impl(websocket))

        save_mock.assert_not_called()
        broadcast_mock.assert_not_called()
        self.assertNotIn(websocket, app_module.manager.active_connections)

    def test_delete_message_removes_and_broadcasts(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        request = _make_request(cookies={"session_id": "owner-session"})

        with patch.object(app_module, "get_job_session_id", return_value="owner-session"), \
                patch.object(app_module, "delete_job", return_value=True) as delete_mock, \
                patch.object(app_module.manager, "broadcast") as broadcast_mock:
            response = asyncio.run(app_module.remove_message(7, request))

        delete_mock.assert_called_once_with(7)
        broadcast_mock.assert_called_once_with(json.dumps({"type": "delete", "id": 7}))
        self.assertEqual(response, {"status": "ok"})

    def test_delete_message_returns_404_when_missing(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        request = _make_request(cookies={"session_id": "owner-session"})

        with patch.object(app_module, "get_job_session_id", return_value=None):
            with self.assertRaises(app_module.HTTPException) as ctx:
                asyncio.run(app_module.remove_message(999, request))

        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_message_returns_403_when_not_owner(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")
        request = _make_request(cookies={"session_id": "someone-else"})

        with patch.object(app_module, "get_job_session_id", return_value="owner-session"), \
                patch.object(app_module, "delete_job") as delete_mock:
            with self.assertRaises(app_module.HTTPException) as ctx:
                asyncio.run(app_module.remove_message(7, request))

        delete_mock.assert_not_called()
        self.assertEqual(ctx.exception.status_code, 403)
