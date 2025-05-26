from typing import Optional, Union, List
from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash
from .models import LnurlUniversal, CreateLnurlUniversalData
from fastapi import HTTPException
from loguru import logger

db = Database("ext_lnurluniversal")

async def create_lnurluniversal(data: LnurlUniversal) -> LnurlUniversal:
    """Create a new LnurlUniversal record."""
    # Ensure fields are initialized
    data.total = 0
    data.uses = 0
    data.state = "payment"
    
    try:
        # Log the data being inserted
        logger.info(f"Attempting to insert data: {data.dict()}")
        
        # Use the pattern from withdraw extension
        await db.insert("lnurluniversal.maintable", data)
        
        logger.info(f"Insert successful for id: {data.id}")
        
    except Exception as e:
        logger.error(f"Error during insert: {type(e).__name__}: {str(e)}")
        logger.error(f"Data type: {type(data)}")
        logger.error(f"Data dict: {data.dict()}")
        raise
    
    # Fetch and return the created record
    return await get_lnurluniversal(data.id)

async def get_lnurluniversal_balance(lnurluniversal_id: str) -> int:
    """Get the balance from record and subtract pending withdrawals"""
    universal = await get_lnurluniversal(lnurluniversal_id)
    if not universal:
        return None
    
    # Get pending withdrawals
    pending = await db.fetchone(
        """
        SELECT COALESCE(SUM(amount), 0) as total
        FROM lnurluniversal.pending_withdrawals
        WHERE universal_id = :universal_id
        AND status = 'pending'
        """,
        {"universal_id": lnurluniversal_id}
    )
    pending_amount = pending["total"] if pending else 0
    available_balance = max(0, universal.total - pending_amount)
    return available_balance

async def get_lnurluniversal(lnurluniversal_id: str) -> Optional[LnurlUniversal]:
    """Get a single LnurlUniversal by ID."""
    try:
        logger.info(f"Fetching lnurluniversal with id: {lnurluniversal_id}")
        row = await db.fetchone(
            "SELECT * FROM lnurluniversal.maintable WHERE id = :id", 
            {"id": lnurluniversal_id}
        )
        logger.info(f"Fetched row: {row}")
        if row:
            logger.info(f"Row type: {type(row)}")
            result = LnurlUniversal(**row)
            logger.info(f"Successfully created LnurlUniversal object")
            return result
        else:
            logger.info("No row found")
            return None
    except Exception as e:
        logger.error(f"Error in get_lnurluniversal: {type(e).__name__}: {str(e)}")
        logger.error(f"Row data: {row if 'row' in locals() else 'Not fetched'}")
        raise

async def get_lnurluniversals(wallet_ids: Union[str, List[str]]) -> List[LnurlUniversal]:
    """Get all LnurlUniversals for given wallet IDs."""
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    
    # Build query with proper placeholders
    placeholders = []
    values = {}
    for i, wallet_id in enumerate(wallet_ids):
        key = f"wallet_{i}"
        placeholders.append(f":{key}")
        values[key] = wallet_id
    
    q = ",".join(placeholders)
    rows = await db.fetchall(
        f"SELECT * FROM lnurluniversal.maintable WHERE wallet IN ({q})",
        values,
        LnurlUniversal
    )
    return rows

async def update_lnurluniversal(data: LnurlUniversal) -> LnurlUniversal:
    """Update an existing LnurlUniversal."""
    logger.info(f"Updating lnurluniversal: {data.id}")
    
    await db.update(
        "lnurluniversal.maintable", 
        data,
        "WHERE id = :id",
        {"id": data.id}
    )
    
    return data

async def delete_lnurluniversal(lnurluniversal_id: str) -> None:
    """Delete a LnurlUniversal."""
    await db.execute(
        "DELETE FROM lnurluniversal.maintable WHERE id = :id", 
        {"id": lnurluniversal_id}
    )

async def get_universal_comments(universal_id: str) -> List[dict]:
    """Get all comments for a universal"""
    rows = await db.fetchall(
        """
        SELECT id, comment, timestamp, amount
        FROM lnurluniversal.invoice_comments
        WHERE universal_id = :universal_id
        ORDER BY timestamp DESC
        """,
        {"universal_id": universal_id}
    )
    return [dict(row) for row in rows]