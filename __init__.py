import asyncio
from fastapi import APIRouter
from .crud import db
from .tasks import wait_for_paid_invoices
from .views import lnurlFlip_generic_router
from .views_api import lnurlFlip_api_router

lnurlFlip_ext: APIRouter = APIRouter(prefix="/lnurlFlip", tags=["LnurlFlip"])
lnurlFlip_ext.include_router(lnurlFlip_generic_router)
lnurlFlip_ext.include_router(lnurlFlip_api_router)

lnurlFlip_static_files = [
    {
        "path": "/lnurlFlip/static",
        "name": "lnurlFlip_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []

def lnurlFlip_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception:
            pass

def lnurlFlip_start():
    from lnbits.tasks import create_permanent_unique_task
    
    task = create_permanent_unique_task("ext_lnurlFlip", wait_for_paid_invoices)
    scheduled_tasks.append(task)

__all__ = [
    "db",
    "lnurlFlip_ext",
    "lnurlFlip_static_files",
    "lnurlFlip_start",
    "lnurlFlip_stop",
]
