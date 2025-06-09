from typing import Optional, Union, List
from lnbits.db import Database
from .models import LnurlUniversal
from fastapi import HTTPException
from loguru import logger
import asyncio

db = Database("ext_lnurluniversal")

# Lock manager for payment operations to prevent race conditions
payment_locks = {}

async def create_lnurluniversal(data: LnurlUniversal) -> LnurlUniversal:
    """Create a new LnurlUniversal record."""
    # Ensure fields are initialized with valid values
    data.total_msat = 0
    data.uses = 0
    
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
        SELECT COALESCE(SUM(amount_msat), 0) as total
        FROM lnurluniversal.pending_withdrawals
        WHERE universal_id = :universal_id
        AND status = 'pending'
        """,
        {"universal_id": lnurluniversal_id}
    )
    pending_amount_msat = pending["total"] if pending else 0
    # Note: universal.total_msat is in msats, pending_amount_msat is now also in msats
    available_balance_msat = max(0, universal.total_msat - pending_amount_msat)
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
    
    # Update balance and optionally increment uses
    uses_increment = ", uses = uses + 1" if increment_uses else ""
    
    # Handle different database types
    if db.type == "SQLITE":
        # SQLite uses MAX instead of GREATEST
        await db.execute(
            f"""
            UPDATE lnurluniversal.maintable
            SET total_msat = MAX(0, total_msat + :amount_delta){uses_increment}
            WHERE id = :id
            """,
            {"id": lnurluniversal_id, "amount_delta": amount_delta}
        )
    else:
        # PostgreSQL and CockroachDB use GREATEST
        await db.execute(
            f"""
            UPDATE lnurluniversal.maintable
            SET total_msat = GREATEST(0, total_msat + :amount_delta){uses_increment}
            WHERE id = :id
            """,
            {"id": lnurluniversal_id, "amount_delta": amount_delta}
        )
    
    # Return the updated record
    updated = await get_lnurluniversal(lnurluniversal_id)
    if updated:
        logger.debug(f"Balance updated: {updated.total_msat} msat")
    
    return updated

async def get_universal_comments(universal_id: str) -> List[dict]:
    """Get all comments for a universal"""
    rows = await db.fetchall(
        """
        SELECT id, comment, timestamp, amount_msat
        FROM lnurluniversal.invoice_comments
        WHERE universal_id = :universal_id
        ORDER BY timestamp DESC
        """,
        {"universal_id": universal_id}
    )
    return [dict(row) for row in rows]


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

async def process_payment_with_lock(
    lnurluniversal_id: str,
    amount_delta: int,
    increment_uses: bool = False,
    operation_type: str = "payment"
) -> Optional[LnurlUniversal]:
    """
    Process payment operations with proper locking to prevent race conditions.
    This ensures that concurrent operations on the same universal are serialized.
    
    Args:
        lnurluniversal_id: The ID of the universal to update
        amount_delta: The amount in msats to add (positive) or subtract (negative)
        increment_uses: Whether to increment the uses counter
        operation_type: Type of operation ("payment" or "withdrawal")
    
    Returns:
        The updated LnurlUniversal object or None if not found
    """
    # Get or create a lock for this universal
    if lnurluniversal_id not in payment_locks:
        payment_locks[lnurluniversal_id] = asyncio.Lock()
    
    lock = payment_locks[lnurluniversal_id]
    
    try:
        # Use the lock to ensure atomic operations
        async with lock:
            logger.info(f"Acquired lock for {lnurluniversal_id}, processing {operation_type} with delta {amount_delta}")
            
            
            # For withdrawals, check balance first
            if amount_delta < 0:  # Withdrawal
                current_balance = await get_lnurluniversal_balance(lnurluniversal_id)
                if current_balance < abs(amount_delta):
                    logger.error(f"Insufficient balance for withdrawal: {current_balance} < {abs(amount_delta)}")
                    raise HTTPException(status_code=400, detail="Insufficient balance")
            
            # Perform the atomic update
            result = await update_lnurluniversal_atomic(
                lnurluniversal_id=lnurluniversal_id,
                amount_delta=amount_delta,
                increment_uses=increment_uses
            )
            
            logger.info(f"Released lock for {lnurluniversal_id}, operation completed")
            return result
    finally:
        # Clean up lock if no longer needed (optional - helps with memory)
        # Only clean up if there are many locks and this one is not in use
        if len(payment_locks) > 100:  # Arbitrary threshold
            try:
                if not lock.locked():
                    payment_locks.pop(lnurluniversal_id, None)
            except:
                pass  # Ignore any cleanup errors

