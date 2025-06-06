from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from lnbits.settings import settings
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from .crud import get_lnurluniversal
from lnurl import encode as lnurl_encode

lnurluniversal_generic_router = APIRouter()


def lnurluniversal_renderer():
    return template_renderer(["lnurluniversal/templates"])


#######################################
##### ADD YOUR PAGE ENDPOINTS HERE ####
#######################################


# Backend admin page


@lnurluniversal_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return lnurluniversal_renderer().TemplateResponse(
        "lnurluniversal/index.html", {"request": request, "user": user.json()}
    )


# Frontend shareable page


@lnurluniversal_generic_router.get("/{lnurluniversal_id}")
async def lnurluniversal(request: Request, lnurluniversal_id):
    lnurluniversal = await get_lnurluniversal(lnurluniversal_id)
    if not lnurluniversal:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlUniversal does not exist."
        )
    
    # Generate the full LNURL for the QR code (without lightning: prefix as template adds it)
    base_url = str(request.base_url).rstrip('/')
    redirect_url = f"{base_url}/lnurluniversal/api/v1/redirect/{lnurluniversal_id}"
    lnurl = lnurl_encode(redirect_url)
    
    return lnurluniversal_renderer().TemplateResponse(
        "lnurluniversal/lnurluniversal.html",
        {
            "request": request,
            "lnurluniversal_id": lnurluniversal_id,
            "lnurlpay": lnurluniversal.selectedLnurlp,
            "lnurl": lnurl,
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
