import configparser
import os
import secrets
from pathlib import Path

from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "ui"
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")

CONFIG_PATH = BASE_DIR / "config.ini"


def _load_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if not parser.read(CONFIG_PATH):
        raise RuntimeError(
            f"Missing {CONFIG_PATH}. Copy config.ini.example to config.ini and set the secrets."
        )
    return parser


_config = _load_config()

IS_DEVELOPMENT = _config.getboolean("app", "development", fallback=False)

AUTH_COOKIE = "auth_token"
ACCESS_TOKEN_EXPIRE_SECONDS = 60 * 60 * 24  # 24 hours

# to get new secret run: openssl rand -hex 22
SECRET_KEY = _config.get("auth", "secret_key")
ALGORITHM = "HS256"

# Without CSRF_SECRET a random secret is generated at every start
CSRF_SECRET = os.getenv("CSRF_SECRET", secrets.token_hex(32))
CSRF_COOKIE_SAMESITE = "lax"
CSRF_TOKEN_KEY = "csrf_token"
