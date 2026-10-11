from typing import Annotated

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import RedirectResponse

from api.auth import (
    OptionalUserDep,
    UserDep,
    authenticate_user,
    create_session_token,
    create_user,
    set_auth_cookie,
)
from api.db import DbDep
from api.config import AUTH_COOKIE, templates
from api.forms import (
    CsrfDep,
    CsrfFormCheck,
    LoginFormData,
    SignupFormData,
    _auth_page,
    template_response_with_csrf,
)

router = APIRouter(include_in_schema=False)


@router.get("/")
def root(request: Request, user: OptionalUserDep) -> Response:
    """Landing page for visitors; logged-in users are redirected to /account."""
    if user is None:
        return templates.TemplateResponse(request, "index.html")
    return RedirectResponse("/account", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/signup")
def get_signup_page(request: Request, csrf_protect: CsrfDep) -> Response:
    return _auth_page(request, csrf_protect, "signup.html")


@router.post("/signup", dependencies=[CsrfFormCheck])
def post_signup_page(
    request: Request,
    csrf_protect: CsrfDep,
    connection: DbDep,
    form: Annotated[SignupFormData, Form()],
) -> Response:
    if create_user(connection, form.username, form.password) is None:
        return _auth_page(
            request,
            csrf_protect,
            "signup.html",
            error="Username is already taken",
            username=form.username,
            status_code=status.HTTP_409_CONFLICT,
        )
    return RedirectResponse("/login?created=true", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login")
def get_login_page(
    request: Request,
    csrf_protect: CsrfDep,
    user: OptionalUserDep,
    created: bool = False,
) -> Response:
    if user is not None:
        return RedirectResponse("/account", status_code=status.HTTP_303_SEE_OTHER)
    return _auth_page(request, csrf_protect, "login.html", created=created)


@router.post("/login", dependencies=[CsrfFormCheck])
def post_login_page(
    request: Request,
    csrf_protect: CsrfDep,
    connection: DbDep,
    form: Annotated[LoginFormData, Form()],
) -> Response:
    user = authenticate_user(connection, form.username, form.password)
    if not user:
        return _auth_page(
            request,
            csrf_protect,
            "login.html",
            error="Incorrect username or password",
            username=form.username,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    access_token = create_session_token(user.username)
    response = RedirectResponse(
        "/account", status_code=status.HTTP_303_SEE_OTHER)
    set_auth_cookie(response, access_token)
    return response


@router.post("/logout", dependencies=[CsrfFormCheck])
def post_logout() -> Response:
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(AUTH_COOKIE)
    return response


@router.get("/account")
def get_account(
    request: Request, csrf_protect: CsrfDep, user: UserDep
) -> Response:
    return template_response_with_csrf(request, "home.html", {"user": user}, csrf_protect)
