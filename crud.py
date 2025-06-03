from typing import Optional, Union, List
from lnbits.db import Database
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
    """Get the balance from record and subtract pending withdrawals
    
    Returns:
        The available balance in millisatoshis (msats)
    """
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
    pending_amount_msat = pending["total"] if pending else 0
    # Note: universal.total is in msats, pending_amount_msat is now also in msats
    available_balance_msat = max(0, universal.total - pending_amount_msat)
    return available_balance_msat

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
    
    # Validate input
    if not wallet_ids:
        return []
    
    # Build query with proper placeholders
    placeholders = []
    values = {}
    for i, wallet_id in enumerate(wallet_ids):
        # Ensure wallet_id is a string to prevent injection
        if not isinstance(wallet_id, str):
            raise ValueError(f"Invalid wallet_id type: {type(wallet_id)}")
        key = f"wallet_{i}"
        placeholders.append(f":{key}")
        values[key] = wallet_id
    
    # Use parameterized query with individually named placeholders
    query = f"SELECT * FROM lnurluniversal.maintable WHERE wallet IN ({','.join(placeholders)})"
    
    rows = await db.fetchall(
        query,
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
        "WHERE id = :id"
    )
    
    return data

async def delete_lnurluniversal(lnurluniversal_id: str) -> None:
    """Delete a LnurlUniversal."""
    await db.execute(
        "DELETE FROM lnurluniversal.maintable WHERE id = :id", 
        {"id": lnurluniversal_id}
    )

async def update_lnurluniversal_atomic(
    lnurluniversal_id: str, 
    amount_delta: int,
    increment_uses: bool = False
) -> Optional[LnurlUniversal]:
    """
    Atomically update the balance and optionally increment uses.
    This prevents race conditions by doing the math in the database.
    
    Args:
        lnurluniversal_id: The ID of the universal to update
        amount_delta: The amount in msats to add (positive) or subtract (negative)
        increment_uses: Whether to increment the uses counter
    
    Returns:
        The updated LnurlUniversal object or None if not found
    """
    logger.info(f"Atomic update for {lnurluniversal_id}: delta={amount_delta}, increment_uses={increment_uses}")
    
    # First do the atomic update
    uses_increment = ", uses = uses + 1" if increment_uses else ""
    
    # Handle different database types
    if db.type == "SQLITE":
        # SQLite uses MAX instead of GREATEST
        await db.execute(
            f"""
            UPDATE lnurluniversal.maintable
            SET total = MAX(0, total + :amount_delta){uses_increment}
            WHERE id = :id
            """,
            {"id": lnurluniversal_id, "amount_delta": amount_delta}
        )
    else:
        # PostgreSQL and CockroachDB use GREATEST
        await db.execute(
            f"""
            UPDATE lnurluniversal.maintable
            SET total = GREATEST(0, total + :amount_delta){uses_increment}
            WHERE id = :id
            """,
            {"id": lnurluniversal_id, "amount_delta": amount_delta}
        )
    
    # Now update the state based on the new total
    universal = await get_lnurluniversal(lnurluniversal_id)
    if universal:
        new_state = "withdraw" if universal.total > 0 else "payment"
        if universal.state != new_state:
            await db.execute(
                """
                UPDATE lnurluniversal.maintable
                SET state = :state
                WHERE id = :id
                """,
                {"id": lnurluniversal_id, "state": new_state}
            )
            universal.state = new_state
    
    return universal

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

async def update_state_if_condition(
    lnurluniversal_id: str,
    new_state: str,
    condition: str = None
) -> bool:
    """
    Atomically update the state if a condition is met.
    This prevents race conditions in state transitions.
    
    Args:
        lnurluniversal_id: The ID of the universal to update
        new_state: The new state to set
        condition: SQL condition to check (e.g., "state = 'payment' AND total = 0")
    
    Returns:
        True if the state was updated, False otherwise
    """
    if condition:
        query = f"""
        UPDATE lnurluniversal.maintable
        SET state = :new_state
        WHERE id = :id AND ({condition})
        """
    else:
        query = """
        UPDATE lnurluniversal.maintable
        SET state = :new_state
        WHERE id = :id
        """
    
    result = await db.execute(
        query,
        {"id": lnurluniversal_id, "new_state": new_state}
    )
    
    # Check if any rows were updated
    return result and hasattr(result, 'rowcount') and result.rowcount > 0

async def check_duplicate_name(name: str, wallet_id: str, exclude_id: Optional[str] = None) -> bool:
    """
    Check if a lnurluniversal with the given name already exists for the wallet.
    
    Args:
        name: The name to check
        wallet_id: The wallet ID to check within
        exclude_id: Optional ID to exclude from the check (for updates)
    
    Returns:
        True if a duplicate exists, False otherwise
    """
    if exclude_id:
        result = await db.fetchone(
            """
            SELECT COUNT(*) as count
            FROM lnurluniversal.maintable
            WHERE LOWER(name) = LOWER(:name) 
            AND wallet = :wallet_id
            AND id != :exclude_id
            """,
            {"name": name, "wallet_id": wallet_id, "exclude_id": exclude_id}
        )
    else:
        result = await db.fetchone(
            """
            SELECT COUNT(*) as count
            FROM lnurluniversal.maintable
            WHERE LOWER(name) = LOWER(:name) 
            AND wallet = :wallet_id
            """,
            {"name": name, "wallet_id": wallet_id}
        )
    
    return result["count"] > 0 if result else False