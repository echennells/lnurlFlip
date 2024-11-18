from http import HTTPStatus
from fastapi import APIRouter, Depends, Request
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from lnbits.settings import settings
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from .crud import get_lnurluniversal

lnurluniversal_generic_router = APIRouter()


def lnurluniversal_renderer():
    return template_renderer(["lnurluniversal/templates"])

# Backend admin page


@lnurluniversal_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return lnurluniversal_renderer().TemplateResponse(
        "lnurluniversal/index.html", {"request": request, "user": user.dict()}
    )


# Frontend shareable page


@lnurluniversal_generic_router.get("/{lnurluniversal_id}")
async def lnurluniversal(request: Request, lnurluniversal_id):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
        )
    return lnurluniversal_renderer().TemplateResponse(
        "lnurluniversal/lnurluniversal.html",
        {
            "request": request,
            "lnurluniversal_id": lnurluniversal_id,
            "lnurlpay": lnurluniversal.lnurlpay,
            "web_manifest": f"/lnurluniversal/manifest/{lnurluniversal_id}.webmanifest",
        },
    )


# Manifest for public page, customise or remove manifest completely


@lnurluniversal_generic_router.get("/manifest/{lnurluniversal_id}.webmanifest")
async def manifest(lnurluniversal_id: str):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
        )

    return {
        "short_name": settings.lnbits_site_title,
        "name": lnurluniversal.name + " - " + settings.lnbits_site_title,
        "icons": [
            {
                "src": (
                    settings.lnbits_custom_logo
                    if settings.lnbits_custom_logo
                    else "https://cdn.jsdelivr.net/gh/lnbits/lnbits@0.3.0/docs/logos/lnbits.png"
                ),
                "type": "image/png",
                "sizes": "900x900",
            }
        ],
        "start_url": "/lnurluniversal/" + lnurluniversal_id,
        "background_color": "#1F2234",
        "description": "Minimal extension to build on",
        "display": "standalone",
        "scope": "/lnurluniversal/" + lnurluniversal_id,
        "theme_color": "#1F2234",
        "shortcuts": [
            {
                "name": lnurluniversal.name + " - " + settings.lnbits_site_title,
                "short_name": lnurluniversal.name,
                "description": lnurluniversal.name + " - " + settings.lnbits_site_title,
                "url": "/lnurluniversal/" + lnurluniversal_id,
            }
        ],
    }
