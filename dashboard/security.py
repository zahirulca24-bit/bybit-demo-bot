
"""Protect dashboard and APIs with HTTP Basic authentication."""

import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse, Response


async def require_dashboard_auth(request: Request, call_next):
    if request.url.path == "/healthz":
        return await call_next(request)

    expected_password = os.getenv("DASHBOARD_PASSWORD", "")
    expected_user = os.getenv("DASHBOARD_USERNAME", "admin")

    if not expected_password:
        return JSONResponse(
            {"detail": "Dashboard authentication not configured"},
            status_code=503,
        )

    import base64

    authorization = request.headers.get("authorization", "")
    supplied_user = ""
    supplied_password = ""

    if authorization.startswith("Basic "):
        try:
            decoded = base64.b64decode(
                authorization[6:], validate=True
            ).decode("utf-8")
            supplied_user, supplied_password = decoded.split(":", 1)
        except (ValueError, UnicodeError):
            pass

    authorized = (
        secrets.compare_digest(supplied_user, expected_user)
        and secrets.compare_digest(
            supplied_password, expected_password
        )
    )

    if not authorized:
        return Response(
            status_code=401,
            headers={
                "WWW-Authenticate": 'Basic realm="Bybit Demo Dashboard"',
                "Cache-Control": "no-store",
            },
        )

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response
