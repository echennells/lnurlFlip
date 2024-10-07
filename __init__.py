import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import lnurluniversal_generic_router
from .views_api import lnurluniversal_api_router
from .views_lnurl import lnurluniversal_lnurl_router

logger.debug(
    "This logged message is from lnurluniversal/__init__.py, you can debug in your "
    "extension using 'import logger from loguru' and 'logger.debug(<thing-to-log>)'."
)


lnurluniversal_ext: APIRouter = APIRouter(prefix="/lnurluniversal", tags=["LnurlUniversal"])
lnurluniversal_ext.include_router(lnurluniversal_generic_router)
lnurluniversal_ext.include_router(lnurluniversal_api_router)
lnurluniversal_ext.include_router(lnurluniversal_lnurl_router)

lnurluniversal_static_files = [
    {
        "path": "/lnurluniversal/static",
        "name": "lnurluniversal_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []


def lnurluniversal_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def lnurluniversal_start():
    from lnbits.tasks import create_permanent_unique_task

    task = create_permanent_unique_task("ext_lnurluniversal", wait_for_paid_invoices)
    scheduled_tasks.append(task)


__all__ = [
    "db",
    "lnurluniversal_ext",
    "lnurluniversal_static_files",
    "lnurluniversal_start",
    "lnurluniversal_stop",
]
