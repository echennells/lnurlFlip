from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from lnbits.settings import settings
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from .crud import get_lnurlFlip
from lnurl import encode as lnurl_encode

lnurlFlip_generic_router = APIRouter()


def lnurlFlip_renderer():
    return template_renderer(["lnurlFlip/templates"])


#######################################
##### ADD YOUR PAGE ENDPOINTS HERE ####
#######################################


# Backend admin page


@lnurlFlip_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return lnurlFlip_renderer().TemplateResponse(
        "lnurlFlip/index.html", {"request": request, "user": user.json()}
    )


# Frontend shareable page


@lnurlFlip_generic_router.get("/{lnurlFlip_id}")
async def lnurlFlip(request: Request, lnurlFlip_id):
    lnurlFlip = await get_lnurlFlip(lnurlFlip_id)
    if not lnurlFlip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlFlip does not exist."
        )
    
    # Generate the full LNURL for the QR code (without lightning: prefix as template adds it)
    base_url = str(request.base_url).rstrip('/')
    redirect_url = f"{base_url}/lnurlFlip/api/v1/redirect/{lnurlFlip_id}"
    lnurl = lnurl_encode(redirect_url)
    
    return lnurlFlip_renderer().TemplateResponse(
        "lnurlFlip/lnurlFlip.html",
        {
            "request": request,
            "lnurlFlip_id": lnurlFlip_id,
            "lnurlpay": lnurlFlip.selectedLnurlp,
            "lnurl": lnurl,
            "web_manifest": f"/lnurlFlip/manifest/{lnurlFlip_id}.webmanifest",
        },
    )


# Manifest for public page, customise or remove manifest completely


@lnurlFlip_generic_router.get("/manifest/{lnurlFlip_id}.webmanifest")
async def manifest(lnurlFlip_id: str):
    lnurlFlip = await get_lnurlFlip(lnurlFlip_id)
    if not lnurlFlip:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="LnurlFlip does not exist."
        )

    return {
        "short_name": settings.lnbits_site_title,
        "name": lnurlFlip.name + " - " + settings.lnbits_site_title,
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
        "start_url": "/lnurlFlip/" + lnurlFlip_id,
        "background_color": "#1F2234",
        "description": "Minimal extension to build on",
        "display": "standalone",
        "scope": "/lnurlFlip/" + lnurlFlip_id,
        "theme_color": "#1F2234",
        "shortcuts": [
            {
                "name": lnurlFlip.name + " - " + settings.lnbits_site_title,
                "short_name": lnurlFlip.name,
                "description": lnurlFlip.name + " - " + settings.lnbits_site_title,
                "url": "/lnurlFlip/" + lnurlFlip_id,
            }
        ],
    }
