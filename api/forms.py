from fastapi import Request
from fastapi_csrf_protect.flexible import CsrfProtect
from pydantic import BaseModel, Field

from api.config import templates

USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = r"^[A-Za-z0-9_]+$"


class SignupFormData(BaseModel):
    username: str = Field(
        min_length=3, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class LoginFormData(BaseModel):
    username: str = Field(
        min_length=3, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=128)


def template_response_with_csrf(
    request: Request,
    template_name: str,
    context: dict,
    csrf_protect: CsrfProtect,
    status_code: int = 200,
):
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
    response = templates.TemplateResponse(
        request,
        template_name,
        {**context, "csrf_token": csrf_token},
        status_code=status_code,
    )
    csrf_protect.set_csrf_cookie(signed_token, response)
    return response


async def validate_form_csrf(request: Request, csrf_protect: CsrfProtect) -> dict:
    """Validate the csrf_token hidden field of a server-rendered form and return the fields."""

    form = dict(await request.form())

    # Per-request instance; the library declares _token_location as a ClassVar,
    # so setattr (instance attribute) avoids the type error without changing the class
    setattr(csrf_protect, "_token_location", "body")
    await csrf_protect.validate_csrf(request)
    return form


def _echoed_username(value: object) -> str:
    """Cap a submitted username before it is shown again in a re-rendered form."""
    return str(value)[:USERNAME_MAX_LENGTH]


def _auth_page(
    request: Request,
    csrf_protect: CsrfProtect,
    template_name: str,
    error: str = "",
    username: str = "",
    status_code: int = 200,
    **context,
):
    """Render the signup or login page (`signup.html` or `login.html`)."""
    return template_response_with_csrf(
        request,
        template_name,
        {**context, "error": error, "username": _echoed_username(username)},
        csrf_protect,
        status_code,
    )
