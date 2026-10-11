from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_csrf_protect.flexible import CsrfProtect

from api.auth import AdminDep, UserInDB, get_admin_from_cookie
from api.forms import (
    CsrfDep,
    RideFormData,
    template_response_with_csrf,
    validate_form_csrf,
)
from api.rides import create_ride, list_rides

# The admin check runs for every route here, before form validation
router = APIRouter(
    prefix="/admin",
    include_in_schema=False,
    dependencies=[Depends(get_admin_from_cookie)],
)


def admin_page(
    request: Request,
    csrf_protect: CsrfProtect,
    admin: UserInDB,
    error: str = "",
    form: dict | None = None,
    created: bool = False,
    status_code: int = 200,
) -> HTMLResponse:
    return template_response_with_csrf(
        request,
        "admin.html",
        {
            "user": admin,
            "rides": list_rides(),
            "error": error,
            "form": form or {},
            "created": created,
        },
        csrf_protect,
        status_code,
    )


@router.get("")
async def get_admin_page(
    request: Request,
    csrf_protect: CsrfDep,
    admin: AdminDep,
    created: bool = False,
) -> Response:
    """Admin dashboard: the ride request form and the list of ride requests."""
    return admin_page(request, csrf_protect, admin, created=created)


@router.post("/rides")
async def post_ride(
    request: Request,
    csrf_protect: CsrfDep,
    admin: AdminDep,
    form: Annotated[RideFormData, Form()],
) -> Response:
    await validate_form_csrf(request, csrf_protect)
    create_ride(
        form.pickup_location,
        form.dropoff_location,
        form.pickup_time,
        form.notes,
        created_by=admin.id,
    )
    return RedirectResponse("/admin?created=true", status_code=status.HTTP_303_SEE_OTHER)
