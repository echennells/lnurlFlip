import asyncio
from fastapi import APIRouter
from loguru import logger
from .crud import db
from .tasks import wait_for_paid_invoices
from .views import lnurluniversal_generic_router
from .views_api import lnurluniversal_api_router
from .migrations import (
    m001_initial,
    m002_update_schema,
    m003_add_state,
    m004_add_total,
    m005_add_pending_withdrawals,
    m007_add_uses,
    m008_add_comments,
)

logger.debug(
    "LnurlUniversal extension initialized. Use 'from loguru import logger' "
    "and 'logger.debug(<message>)' for debugging in your extension."
)

migrations = [
    m001_initial,
    m002_update_schema,
    m003_add_state,
    m004_add_total,
    m005_add_pending_withdrawals,
    m007_add_uses,
    m008_add_comments,
]

lnurluniversal_ext: APIRouter = APIRouter(prefix="/lnurluniversal", tags=["LnurlUniversal"])
lnurluniversal_ext.include_router(lnurluniversal_generic_router)
lnurluniversal_ext.include_router(lnurluniversal_api_router)

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
    
    async def run_migrations():
        try:
            logger.info("Running initial migration...")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS maintable (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    wallet TEXT NOT NULL,
                    lnurlwithdrawamount INTEGER,
                    selectedLnurlp TEXT NOT NULL,
                    selectedLnurlw TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'inactive',
                    total INTEGER NOT NULL DEFAULT 0,
                    uses INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            logger.info("Initial migration completed")
            
            logger.info("Creating pending withdrawals table...")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_withdrawals (
                    id TEXT PRIMARY KEY,
                    universal_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_time INTEGER NOT NULL,
                    payment_request TEXT NOT NULL,
                    FOREIGN KEY (universal_id) REFERENCES maintable(id)
                );
                """
            )
            logger.info("Pending withdrawals table created")
            
            logger.info("Creating comments table...")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS invoice_comments (
                    id TEXT PRIMARY KEY,
                    universal_id TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    FOREIGN KEY (universal_id) REFERENCES maintable(id)
                );
                """
            )
            logger.info("Comments table created")
            
        except Exception as e:
            logger.error(f"Migration error: {str(e)}")
            
    # Run the migrations
    asyncio.create_task(run_migrations())
    
    task = create_permanent_unique_task("ext_lnurluniversal", wait_for_paid_invoices)
    scheduled_tasks.append(task)

__all__ = [
    "db",
    "lnurluniversal_ext",
    "lnurluniversal_static_files",
    "lnurluniversal_start",
    "lnurluniversal_stop",
    "migrations",
]
