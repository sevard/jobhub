import asyncio
import importlib
import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


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
        app_module.save_message("hello from tests")

        response = asyncio.run(app_module.messages())

        self.assertIn("messages", response)
        contents = [message["content"] for message in response["messages"]]
        self.assertIn("hello from tests", contents)

        with sqlite3.connect(app_module.DB_PATH) as connection:
            connection.execute("DELETE FROM messages WHERE content = ?", ("hello from tests",))

    def test_create_message_saves_and_broadcasts(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        with patch.object(app_module, "save_message") as save_mock, \
                patch.object(app_module.manager, "broadcast") as broadcast_mock:
            save_mock.return_value = 42
            payload = app_module.MessagePayload(content="posted message")
            response = asyncio.run(app_module.create_message(payload))

        save_mock.assert_called_once_with("posted message")
        broadcast_mock.assert_called_once_with(
            json.dumps({"type": "message", "id": 42, "content": "posted message"})
        )
        self.assertEqual(response, {"status": "ok", "id": 42})

    def test_delete_message_removes_and_broadcasts(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        with patch.object(app_module, "delete_message", return_value=True) as delete_mock, \
                patch.object(app_module.manager, "broadcast") as broadcast_mock:
            response = asyncio.run(app_module.remove_message(7))

        delete_mock.assert_called_once_with(7)
        broadcast_mock.assert_called_once_with(json.dumps({"type": "delete", "id": 7}))
        self.assertEqual(response, {"status": "ok"})

    def test_delete_message_returns_404_when_missing(self):
        os.environ["APP_ENV"] = "development"
        app_module = importlib.import_module("api.app")

        with patch.object(app_module, "delete_message", return_value=False):
            with self.assertRaises(app_module.HTTPException) as ctx:
                asyncio.run(app_module.remove_message(999))

        self.assertEqual(ctx.exception.status_code, 404)
