from typing import Optional, Union, List
from lnbits.db import Database
from .models import LnurlFlip
from fastapi import HTTPException
from loguru import logger

db = Database("ext_lnurlFlip")

async def create_lnurlflip(data: LnurlFlip) -> LnurlFlip:
    """Create a new LnurlFlip record."""
    # Ensure fields are initialized with valid values
    data.total_msat = 0
    data.uses = 0
    
    try:
        # Use the pattern from withdraw extension
        await db.insert("maintable", data)
        
    except Exception as e:
        logger.error(f"Error creating lnurlFlip {data.id}: {type(e).__name__}: {str(e)}")
        raise
    
    # Fetch and return the created record
    return await get_lnurlFlip(data.id)

async def get_lnurlflip_balance(lnurlflip_id: str) -> int:
    """Get the balance from record and subtract pending withdrawals
    
    Returns:
        The available balance in millisatoshis (msats)
    """
    flip = await get_lnurlFlip(lnurlflip_id)
    if not flip:
        return None
    
    # Get pending withdrawals
    pending = await db.fetchone(
        """
        SELECT COALESCE(SUM(amount_msat), 0) as total
        FROM pending_withdrawals
        WHERE flip_id = :flip_id
        AND status = 'pending'
        """,
        {"flip_id": lnurlflip_id}
    )
    pending_amount_msat = pending["total"] if pending else 0
    # Note: flip.total_msat is in msats, pending_amount_msat is now also in msats
    available_balance_msat = max(0, flip.total_msat - pending_amount_msat)
    return available_balance_msat

async def get_lnurlFlip(lnurlflip_id: str) -> Optional[LnurlFlip]:
    """Get a single LnurlFlip by ID."""
    try:
        row = await db.fetchone(
            "SELECT * FROM maintable WHERE id = :id", 
            {"id": lnurlflip_id}
        )
        if row:
            return LnurlFlip(**row)
        else:
            return None
    except Exception as e:
        logger.error(f"Error in get_lnurlFlip: {type(e).__name__}: {str(e)}")
        logger.error(f"Row data: {row if 'row' in locals() else 'Not fetched'}")
        raise

async def get_lnurlFlips(wallet_ids: Union[str, List[str]]) -> List[LnurlFlip]:
    """Get all LnurlFlips for given wallet IDs."""
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
    query = f"SELECT * FROM maintable WHERE wallet IN ({','.join(placeholders)})"
    
    rows = await db.fetchall(
        query,
        values,
        LnurlFlip
    )
    return rows

async def update_lnurlFlip(data: LnurlFlip) -> LnurlFlip:
    """Update an existing LnurlFlip."""
    logger.info(f"Updating lnurlFlip: {data.id}")
    
    await db.update(
        "maintable", 
        data,
        "WHERE id = :id"
    )
    
    return data

async def delete_lnurlFlip(lnurlflip_id: str) -> None:
    """Delete a LnurlFlip."""
    await db.execute(
        "DELETE FROM maintable WHERE id = :id", 
        {"id": lnurlflip_id}
    )

async def update_lnurlflip_atomic(
    lnurlflip_id: str, 
    amount_delta: int,
    increment_uses: bool = False
) -> Optional[LnurlFlip]:
    """
    Atomically update the balance and optionally increment uses.
    This prevents race conditions by doing the math in the database.
    
    Args:
        lnurlflip_id: The ID of the flip to update
        amount_delta: The amount in msats to add (positive) or subtract (negative)
        increment_uses: Whether to increment the uses counter
    
    Returns:
        The updated LnurlFlip object or None if not found
    """
    logger.info(f"Atomic update for {lnurlflip_id}: delta={amount_delta}, increment_uses={increment_uses}")
    
    # Update balance and optionally increment uses
    uses_increment = ", uses = uses + 1" if increment_uses else ""
    
    # Handle different database types
    if db.type == "SQLITE":
        # SQLite uses MAX instead of GREATEST
        await db.execute(
            f"""
            UPDATE maintable
            SET total_msat = MAX(0, total_msat + :amount_delta){uses_increment}
            WHERE id = :id
            """,
            {"id": lnurlflip_id, "amount_delta": amount_delta}
        )
    else:
        # PostgreSQL and CockroachDB use GREATEST
        await db.execute(
            f"""
            UPDATE maintable
            SET total_msat = GREATEST(0, total_msat + :amount_delta){uses_increment}
            WHERE id = :id
            """,
            {"id": lnurlflip_id, "amount_delta": amount_delta}
        )
    
    # Return the updated record
    updated = await get_lnurlFlip(lnurlflip_id)
    if updated:
        logger.debug(f"Balance updated: {updated.total_msat} msat")
    
    return updated

async def get_flip_comments(flip_id: str) -> List[dict]:
    """Get all comments for a flip"""
    rows = await db.fetchall(
        """
        SELECT id, comment, timestamp, amount_msat
        FROM invoice_comments
        WHERE flip_id = :flip_id
        ORDER BY timestamp DESC
        """,
        {"flip_id": flip_id}
    )
    return [dict(row) for row in rows]


async def check_duplicate_name(name: str, wallet_id: str, exclude_id: Optional[str] = None) -> bool:
    """
    Check if a lnurlFlip with the given name already exists for the wallet.
    
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
            FROM maintable
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
            FROM maintable
            WHERE LOWER(name) = LOWER(:name) 
            AND wallet = :wallet_id
            """,
            {"name": name, "wallet_id": wallet_id}
        )
    
    return result["count"] > 0 if result else False

async def process_payment_with_lock(
    lnurlflip_id: str,
    amount_delta: int,
    increment_uses: bool = False,
    operation_type: str = "payment"
) -> Optional[LnurlFlip]:
    """
    Process payment operations atomically.
    The database handles concurrency through atomic operations.
    
    Args:
        lnurlflip_id: The ID of the flip to update
        amount_delta: The amount in msats to add (positive) or subtract (negative)
        increment_uses: Whether to increment the uses counter
        operation_type: Type of operation ("payment" or "withdrawal")
    
    Returns:
        The updated LnurlFlip object or None if not found
    """
    try:
        # For withdrawals, check balance first
        if amount_delta < 0:  # Withdrawal
            current_balance = await get_lnurlflip_balance(lnurlflip_id)
            if current_balance < abs(amount_delta):
                logger.error(f"Insufficient balance for withdrawal: {current_balance} < {abs(amount_delta)}")
                raise HTTPException(status_code=400, detail="Insufficient balance")
        
        # Perform the atomic update - database handles concurrency
        result = await update_lnurlflip_atomic(
            lnurlflip_id=lnurlflip_id,
            amount_delta=amount_delta,
            increment_uses=increment_uses
        )
        
        return result
    except Exception as e:
        logger.error(f"Error in process_payment_with_lock: {e}")
        raise

